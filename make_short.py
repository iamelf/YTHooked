#!/usr/bin/env python3
"""
Stage 5 (Track B): render a real DOAC-style vertical Short MP4.

Structure:  [generated narrator video + voiceover] -> [real snapped clip] -> [generated narrator video + voiceover]

The narrator segments are a pluggable PROVIDER:
  --narrator local   (default) ffmpeg-animated motion bg + `say` voiceover + captions. No keys.
  --narrator veo     Google Veo b-roll + scripted voiceover. Needs GEMINI_API_KEY w/ billing (stub falls back to local).

Usage:
    python3 make_short.py out/shorts/specs/HaZaFCHdkuk-cost.doac.json
    python3 make_short.py SPEC.json --narrator local --quality 720

Deps: ffmpeg, ffprobe, yt-dlp, Pillow, macOS `say`. Track B downloads a clip
(yt-dlp) -> local-only experiment, crosses YouTube ToS by design.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import loadenv  # noqa: F401  (auto-loads environment.env: GEMINI_API_KEY etc.)

W, H, FPS = 1080, 1920, 30
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
ACCENT = (255, 45, 85)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(f"\n$ {' '.join(map(str, cmd))}\n{r.stderr[-1500:]}\n")
        raise RuntimeError(f"command failed: {cmd[0]}")
    return r


def probe_dur(path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)])
    return float(r.stdout.strip())


def font(size, bold=True):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)


# --------------------------------------------------------------------------- #
# PIL image builders
# --------------------------------------------------------------------------- #
def gradient_bg(path, top=(14, 18, 34), bot=(4, 4, 8)):
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / H
        px_row = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        for x in range(W):
            px[x, y] = px_row
    img.save(path)


def wrap(draw, text, fnt, max_w):
    out = []
    for para in text.split("\n"):
        if para == "":
            out.append("")
            continue
        words, line = para.split(" "), ""
        for w in words:
            test = (line + " " + w).strip()
            if draw.textlength(test, font=fnt) <= max_w:
                line = test
            else:
                if line:
                    out.append(line)
                line = w
        if line:
            out.append(line)
    return out


def narrator_text_png(path, text, kicker="HOOKED", cta=None):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fnt = font(96, bold=True)
    lines = wrap(d, text, fnt, W - 160)
    line_h = 120
    total = len(lines) * line_h
    # nudge the block up a little when there's a CTA so the pill has room
    y = (H - total) // 2 - (110 if cta else 0)
    # kicker bar (skipped when kicker is empty, e.g. glue cards)
    if kicker:
        kf = font(40, bold=True)
        d.rectangle([80, y - 140, 80 + 14, y - 60], fill=ACCENT)
        d.text((110, y - 132), kicker, font=kf, fill=(255, 255, 255, 230))
    for ln in lines:
        w = d.textlength(ln, font=fnt)
        x = (W - w) // 2
        d.text((x + 3, y + 3), ln, font=fnt, fill=(0, 0, 0, 160))  # shadow
        d.text((x, y), ln, font=fnt, fill=(255, 255, 255, 255))
        y += line_h
    if cta:
        cf = font(50, bold=True)
        label = cta.lstrip("▶ ").strip()  # draw our own play triangle (Arial lacks the glyph)
        tw = d.textlength(label, font=cf)
        tri_w, gap, pad_x, pad_y = 34, 22, 50, 28
        content_w = tri_w + gap + tw
        bx0 = (W - content_w) // 2 - pad_x
        by0 = y + 70
        bh = 50 + 2 * pad_y
        d.rounded_rectangle([bx0, by0, bx0 + content_w + 2 * pad_x, by0 + bh],
                            radius=44, fill=ACCENT)
        gx = (W - content_w) // 2
        cy = by0 + bh // 2
        d.polygon([(gx, cy - 21), (gx, cy + 21), (gx + tri_w, cy)], fill=(255, 255, 255, 255))
        d.text((gx + tri_w + gap, by0 + pad_y), label, font=cf, fill=(255, 255, 255, 255))
    img.save(path)


def caption_strip_png(path, text):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fnt = font(64, bold=True)
    lines = wrap(d, text, fnt, W - 140)
    line_h = 84
    block_h = len(lines) * line_h + 80
    y0 = H - 460
    d.rounded_rectangle([50, y0 - 40, W - 50, y0 + block_h - 40], radius=28,
                        fill=(0, 0, 0, 150))
    y = y0
    for ln in lines:
        w = d.textlength(ln, font=fnt)
        x = (W - w) // 2
        d.text((x, y), ln, font=fnt, fill=(255, 255, 255, 255))
        y += line_h
    img.save(path)


# --------------------------------------------------------------------------- #
# Segment renderers
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# TTS providers (pluggable)
# --------------------------------------------------------------------------- #
# Sensible default voices per provider; override with --voice.
DEFAULT_VOICE = {
    "macos": "Daniel",                       # en_GB default; download a Premium voice for big gains
    "elevenlabs": "onwK4e9ZLuTAKqWW03F9",    # "Daniel" deep British narrator
    "gemini": "Charon",                      # informative, measured
}


def synth_tts(text, out_base, provider, voice):
    """Render `text` to an audio file; return the written path (ext varies)."""
    voice = voice or DEFAULT_VOICE[provider]
    if provider == "macos":
        out = out_base.with_suffix(".aiff")
        run(["say", "-v", voice, "-o", str(out), text])
        return out
    if provider == "elevenlabs":
        return _elevenlabs(text, out_base.with_suffix(".mp3"), voice)
    if provider == "gemini":
        return _gemini_tts(text, out_base.with_suffix(".wav"), voice)
    raise ValueError(f"unknown tts provider {provider}")


def _elevenlabs(text, out_mp3, voice_id):
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("ELEVENLABS_API_KEY not set (needed for --tts elevenlabs)")
    body = json.dumps({
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.75, "style": 0.30},
    }).encode()
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        data=body,
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out_mp3.write_bytes(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"ElevenLabs error {e.code}: {e.read().decode('utf-8','replace')[:400]}")
    return out_mp3


def _gemini_tts(text, out_wav, voice_name):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY not set (needed for --tts gemini)")
    model = "gemini-2.5-flash-preview-tts"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = json.dumps({
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice_name}}},
        },
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"Gemini TTS error {e.code}: {e.read().decode('utf-8','replace')[:400]}")
    b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    pcm = base64.b64decode(b64)  # 24kHz, mono, signed 16-bit LE
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(pcm)
    return out_wav


def narrator_local(text_vo, text_overlay, out_mp4, tmp, tag, tts="macos", voice=None,
                   cta=None, kicker="HOOKED"):
    """Motion gradient + voiceover + animated caption -> normalized mp4."""
    aiff = synth_tts(text_vo, tmp / tag, tts, voice)
    dur = max(probe_dur(aiff) + 0.6, 2.5)

    bg = tmp / f"{tag}_bg.png"
    tx = tmp / f"{tag}_tx.png"
    gradient_bg(bg)
    narrator_text_png(tx, text_overlay, kicker=kicker, cta=cta)

    # slow push-in (zoompan) on the gradient, text fades in, voiceover over it
    total_frames = int(dur * FPS)
    vf = (
        f"[0:v]scale=1188:2112,zoompan=z='min(zoom+0.0006,1.12)':"
        f"d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={W}x{H}:fps={FPS}[bg];"
        f"[bg][1:v]overlay=0:0[ov];"
        f"[ov]fade=t=in:st=0:d=0.4,format=yuv420p[v]"
    )
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(bg),
         "-loop", "1", "-i", str(tx), "-i", str(aiff),
         "-filter_complex", vf, "-map", "[v]", "-map", "2:a",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-ar", "44100", "-ac", "2", "-t", f"{dur:.3f}",
         str(out_mp4)])


def narrator_veo(text_vo, text_overlay, out_mp4, tmp, tag, tts="macos", voice=None,
                 cta=None, kicker="HOOKED"):
    """Veo provider slot. Requires GEMINI_API_KEY + billing; falls back to local."""
    if not os.environ.get("GEMINI_API_KEY"):
        print(f"  [veo] no GEMINI_API_KEY -> falling back to local motion for {tag}")
        return narrator_local(text_vo, text_overlay, out_mp4, tmp, tag, tts, voice, cta, kicker)
    # TODO: call Veo (generate ~8s b-roll from a visual prompt), download mp4,
    # then overlay scripted TTS voiceover + caption and normalize to W x H.
    raise NotImplementedError("Veo wiring pending: verify model id + poll long-running op")


# --------------------------------------------------------------------------- #
# Kinetic typography narrator (PIL frame sequence; no libass needed)
# --------------------------------------------------------------------------- #
KIN_BASE, KIN_ACCENT = 150, 196
KIN_PHRASE = 112  # phrase-build is more compact than single-word punch


def _kin_is_accent(tok, accent):
    w = re.sub(r"[^\w']", "", tok).lower()
    return bool(re.search(r"\d", tok)) or (tok.isupper() and len(tok) > 1) or w in accent


def _kin_pop(local):  # 55% -> 108% overshoot -> 100%
    if local < 0.25:
        return 0.55 + (1.08 - 0.55) * (local / 0.25)
    if local < 0.40:
        return 1.08 + (1.0 - 1.08) * ((local - 0.25) / 0.15)
    return 1.0


def _kin_fade(local):
    if local < 0.15:
        return local / 0.15
    if local > 0.90:
        return max((1.0 - local) / 0.10, 0.0)
    return 1.0


def _kin_draw_cta(frame, cta):
    d = ImageDraw.Draw(frame)
    cf = font(50, True)
    label = cta.lstrip("▶ ").strip()
    tw = d.textlength(label, font=cf)
    tri_w, gap, pad_x, pad_y = 34, 22, 50, 28
    content_w = tri_w + gap + tw
    by0, bh = H - 320, 50 + 2 * pad_y
    bx0 = (W - content_w) // 2 - pad_x
    d.rounded_rectangle([bx0, by0, bx0 + content_w + 2 * pad_x, by0 + bh], radius=44, fill=ACCENT)
    gx, cy = (W - content_w) // 2, by0 + bh // 2
    d.polygon([(gx, cy - 21), (gx, cy + 21), (gx + tri_w, cy)], fill=(255, 255, 255))
    d.text((gx + tri_w + gap, by0 + pad_y), label, font=cf, fill=(255, 255, 255))
    return frame


def _kin_render_punch(text, accent, dur, fdir, bg, cta=None):
    toks = text.replace("\n", " ").split()
    n = max(len(toks), 1)
    head, tail = 0.15, 0.30
    slice_ = max(dur - head - tail, 0.6) / n
    for fi in range(int(dur * FPS)):
        t, frame = fi / FPS, bg.copy()
        if t >= head:
            idx = min(int((t - head) / slice_), n - 1)
            local = (t - head - idx * slice_) / slice_
            if 0.0 <= local <= 1.0:
                tok = toks[idx]
                acc = _kin_is_accent(tok, accent)
                size = max(int((KIN_ACCENT if acc else KIN_BASE) * _kin_pop(local)), 8)
                a = int(255 * _kin_fade(local))
                color = ACCENT if acc else (255, 255, 255)
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                ImageDraw.Draw(layer).text((W // 2, H // 2), tok, font=font(size, True),
                    fill=(*color, a), anchor="mm", stroke_width=max(size // 22, 3), stroke_fill=(0, 0, 0, a))
                frame = Image.alpha_composite(frame, layer)
        if cta:
            frame = _kin_draw_cta(frame, cta)
        frame.convert("RGB").save(fdir / f"{fi:05d}.png")


def _kin_layout(text):
    f = font(KIN_PHRASE, True)
    probe = ImageDraw.Draw(Image.new("RGB", (W, H)))
    max_w = W - 120
    lines = []
    for rl in text.split("\n"):
        if rl.strip() == "":
            lines.append([])
            continue
        cur = []
        for w in rl.split():
            if not cur or probe.textlength(" ".join(cur + [w]), font=f) <= max_w:
                cur.append(w)
            else:
                lines.append(cur); cur = [w]
        if cur:
            lines.append(cur)
    line_h = KIN_PHRASE * 1.06
    y0 = (H - len(lines) * line_h) / 2 + line_h / 2
    space_w = probe.textlength(" ", font=f)
    placed = []
    for li, words in enumerate(lines):
        cy = y0 + li * line_h
        widths = [probe.textlength(w, font=f) for w in words]
        lw = (sum(widths) + space_w * (len(words) - 1)) if words else 0
        x = (W - lw) / 2
        for w, wd in zip(words, widths):
            placed.append((w, x + wd / 2, cy))
            x += wd + space_w
    return placed


def _kin_render_phrase(text, accent, dur, fdir, bg, cta=None):
    placed = _kin_layout(text)
    n = max(len(placed), 1)
    head, tail, pop_win = 0.2, 0.4, 0.35
    slice_ = max(dur - head - tail, 0.6) / n
    for fi in range(int(dur * FPS)):
        t = fi / FPS
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for i, (tok, cx, cy) in enumerate(placed):
            appear = head + i * slice_
            if t < appear:
                continue
            age = t - appear
            acc = _kin_is_accent(tok, accent)
            color = ACCENT if acc else (255, 255, 255)
            if age < pop_win:
                p = age / pop_win
                scale = (0.6 + (1.18 - 0.6) * (p / 0.3)) if p < 0.3 else (1.18 - 0.18 * ((p - 0.3) / 0.7))
                alpha = min(age / 0.12, 1.0)
            else:
                scale, alpha = 1.0, 1.0
            size = max(int(KIN_PHRASE * scale), 8)
            d.text((cx, cy), tok, font=font(size, True), fill=(*color, int(255 * alpha)),
                   anchor="mm", stroke_width=max(size // 22, 3), stroke_fill=(0, 0, 0, int(255 * alpha)))
        frame = Image.alpha_composite(bg.copy(), layer)
        if cta:
            frame = _kin_draw_cta(frame, cta)
        frame.convert("RGB").save(fdir / f"{fi:05d}.png")


def narrator_kinetic(text_vo, text_overlay, out_mp4, tmp, tag, tts="macos", voice=None,
                     cta=None, mode="punch", accent=()):
    audio = synth_tts(text_vo, tmp / tag, tts, voice)
    dur = max(probe_dur(audio) + 0.4, 2.0)
    bgp = tmp / f"{tag}_bg.png"
    gradient_bg(bgp)
    bg = Image.open(bgp).convert("RGBA")
    fdir = tmp / f"kf_{tag}"
    fdir.mkdir(exist_ok=True)
    acc = {a.lower() for a in accent}
    (_kin_render_phrase if mode == "phrase" else _kin_render_punch)(text_overlay, acc, dur, fdir, bg, cta)
    run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(fdir / "%05d.png"), "-i", str(audio),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac",
         "-ar", "44100", "-ac", "2", "-t", f"{dur:.3f}", str(out_mp4)])
    for f in fdir.glob("*"):
        f.unlink()
    fdir.rmdir()


def download_clip(video_id, start, end, out_mp4, quality):
    # YouTube forces SABR streaming on the web/tv clients (403 Forbidden on the
    # format URL). The `android` player client still serves direct URLs that
    # ffmpeg can range-download. This is the fragile layer -- expect it to need
    # a different client every few months as YouTube's bot detection evolves.
    section = f"*{max(start, 0):.2f}-{end:.2f}"
    url = f"https://www.youtube.com/watch?v={video_id}"
    run(["yt-dlp", "--no-update", "-q", "--no-warnings",
         "--extractor-args", "youtube:player_client=android",
         "-f", f"best[height<={quality}]/best",
         "--download-sections", section, "--force-keyframes-at-cuts",
         "--recode-video", "mp4", "-o", str(out_mp4), url])


def render_clip_segment(src_mp4, caption, out_mp4, tmp, tag):
    """DOAC vertical: blurred fill bg + centered clip + caption strip."""
    cap = tmp / f"{tag}_cap.png"
    caption_strip_png(cap, caption)
    vf = (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},gblur=sigma=28,eq=brightness=-0.06[bg];"
        f"[0:v]scale={W}:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
        f"[base][1:v]overlay=0:0,format=yuv420p[v]"
    )
    run(["ffmpeg", "-y", "-i", str(src_mp4), "-loop", "1", "-i", str(cap),
         "-filter_complex", vf, "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest",
         str(out_mp4)])


def concat(segments, out_mp4, tmp):
    lst = tmp / "concat.txt"
    lst.write_text("".join(f"file '{s.resolve()}'\n" for s in segments))
    # re-encode on concat to guarantee identical params join cleanly
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-ar", "44100", "-ac", "2", str(out_mp4)])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--narrator", choices=["local", "veo"], default="local")
    ap.add_argument("--tts", choices=["macos", "elevenlabs", "gemini"], default="macos",
                    help="voiceover provider (elevenlabs/gemini need API keys in env)")
    ap.add_argument("--voice", default=None, help="voice name/id override for the chosen --tts")
    ap.add_argument("--kinetic", choices=["none", "punch", "phrase"], default="none",
                    help="kinetic-typography narrator cards (punch=one word at a time, phrase=build-up)")
    ap.add_argument("--quality", type=int, default=720, help="max source height")
    ap.add_argument("-o", "--outdir", type=Path, default=Path("out/shorts"))
    ap.add_argument("--keep-temp", action="store_true")
    args = ap.parse_args()

    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    args.outdir.mkdir(parents=True, exist_ok=True)
    out_mp4 = args.outdir / f"{spec['id']}.mp4"
    narrator = narrator_veo if args.narrator == "veo" else narrator_local

    # Defensive: some specs (esp. LLM-generated) carry literal "\n" / escaped
    # quotes instead of real characters — decode so cards never show raw escapes.
    def _dec(t):
        return t.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'") if isinstance(t, str) else t
    for k in ("intro_vo", "intro_text", "outro_vo", "outro_text", "outro_cta", "clip_caption"):
        if k in spec:
            spec[k] = _dec(spec[k])
    for _s in spec.get("segments", []):
        for k in ("clip_caption", "glue_vo", "glue_text"):
            if k in _s:
                _s[k] = _dec(_s[k])

    # Normalize to a segment list. Multi-clip specs use spec["segments"]; old
    # single-clip specs are wrapped into a one-segment list (backward compatible).
    segments = spec.get("segments") or [{
        "clip_start": spec["clip_start"], "clip_end": spec["clip_end"],
        "clip_caption": spec["clip_caption"], "glue_vo": "", "glue_text": "",
    }]

    accent_words = spec.get("accent", [])
    tmp = Path(tempfile.mkdtemp(prefix="short_"))

    def NARR(vo, text, out, tag, cta=None, kicker="HOOKED"):
        if args.kinetic != "none":
            narrator_kinetic(vo, text, out, tmp, tag, args.tts, args.voice,
                             cta=cta, mode=args.kinetic, accent=accent_words)
        else:
            narrator(vo, text, out, tmp, tag, args.tts, args.voice, cta=cta, kicker=kicker)

    try:
        pieces = []
        print(f"[intro] narrator ({args.narrator}, tts={args.tts}, kinetic={args.kinetic})...")
        intro = tmp / "intro.mp4"
        NARR(spec["intro_vo"], spec["intro_text"], intro, "intro")
        pieces.append(intro)

        for i, seg in enumerate(segments):
            if seg.get("glue_vo"):
                print(f"[glue {i+1}] narrator...")
                g = tmp / f"glue{i}.mp4"
                NARR(seg["glue_vo"], seg.get("glue_text", ""), g, f"glue{i}", kicker="")
                pieces.append(g)
            print(f"[clip {i+1}/{len(segments)}] download {seg['clip_start']}-{seg['clip_end']}s + render...")
            raw = tmp / f"raw{i}.mp4"
            download_clip(spec["video_id"], seg["clip_start"], seg["clip_end"], raw, args.quality)
            clip = tmp / f"clip{i}.mp4"
            render_clip_segment(raw, seg["clip_caption"], clip, tmp, f"clip{i}")
            pieces.append(clip)

        print(f"[outro] narrator...")
        outro = tmp / "outro.mp4"
        NARR(spec["outro_vo"], spec["outro_text"], outro, "outro", cta=spec.get("outro_cta"))
        pieces.append(outro)

        print(f"[concat] {len(pieces)} pieces...")
        concat(pieces, out_mp4, tmp)

        dur = probe_dur(out_mp4)
        size_mb = out_mp4.stat().st_size / 1e6
        print(f"\n  OK -> {out_mp4}  ({dur:.1f}s, {size_mb:.1f} MB, {W}x{H}, {len(segments)} clips)")
    finally:
        if args.keep_temp:
            print(f"  temp kept: {tmp}")
        else:
            for f in tmp.glob("*"):
                f.unlink()
            tmp.rmdir()


if __name__ == "__main__":
    main()
