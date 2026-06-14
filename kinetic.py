#!/usr/bin/env python3
"""
Kinetic-typography prototype for narrator cards. Renders the card text as
word-by-word centered "beats" (scale-pop + fade), key words highlighted in the
accent color and larger. Pure PIL frame sequence + ffmpeg assemble — works with
any ffmpeg (no libass needed).

Demo:
    python3 kinetic.py "Uber's loyalty system. Zero database rows." \
        --accent zero,database,rows \
        --vo "The team that ran Uber's loyalty system with zero database rows."
"""
import argparse
import re
from pathlib import Path

from PIL import Image, ImageDraw

from make_short import W, H, FPS, gradient_bg, synth_tts, probe_dur, run, font, ACCENT

ACCENT_RGB = ACCENT          # (255,45,85)
WHITE = (255, 255, 255)
BASE_SIZE, ACCENT_SIZE = 150, 196


def is_accent(tok, accent_words):
    w = re.sub(r"[^\w']", "", tok).lower()
    return bool(re.search(r"\d", tok)) or (tok.isupper() and len(tok) > 1) or w in accent_words


def pop_scale(local):
    """55% -> 108% overshoot -> 100% over the first part of a word's beat."""
    if local < 0.25:
        return 0.55 + (1.08 - 0.55) * (local / 0.25)
    if local < 0.40:
        return 1.08 + (1.00 - 1.08) * ((local - 0.25) / 0.15)
    return 1.0


def fade_alpha(local):
    if local < 0.15:
        return local / 0.15
    if local > 0.90:
        return max((1.0 - local) / 0.10, 0.0)
    return 1.0


def render(text, accent_words, vo, out_mp4, tts="macos", voice=None):
    tmp = Path(".kinetic_tmp")
    frames = tmp / "f"
    frames.mkdir(parents=True, exist_ok=True)

    audio = synth_tts(vo, tmp / "vo", tts, voice)
    dur = max(probe_dur(audio) + 0.4, 2.0)

    bg_path = tmp / "bg.png"
    gradient_bg(bg_path)
    bg = Image.open(bg_path).convert("RGBA")

    tokens = text.replace("\n", " ").split()
    n = max(len(tokens), 1)
    head, tail = 0.15, 0.30
    span = max(dur - head - tail, 0.6)
    slice_ = span / n

    total = int(dur * FPS)
    for fi in range(total):
        t = fi / FPS
        frame = bg.copy()
        if t >= head:
            idx = min(int((t - head) / slice_), n - 1)
            local = (t - head - idx * slice_) / slice_
            if 0.0 <= local <= 1.0:
                tok = tokens[idx]
                accent = is_accent(tok, accent_words)
                base = ACCENT_SIZE if accent else BASE_SIZE
                size = max(int(base * pop_scale(local)), 8)
                a = int(255 * fade_alpha(local))
                color = ACCENT_RGB if accent else WHITE
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                d = ImageDraw.Draw(layer)
                d.text((W // 2, H // 2), tok, font=font(size, bold=True),
                       fill=(*color, a), anchor="mm",
                       stroke_width=max(size // 22, 3), stroke_fill=(0, 0, 0, a))
                frame = Image.alpha_composite(frame, layer)
        frame.convert("RGB").save(frames / f"{fi:05d}.png")

    run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", str(frames / "%05d.png"),
         "-i", str(audio), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest", str(out_mp4)])

    for f in frames.glob("*"):
        f.unlink()
    frames.rmdir()
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()
    print(f"  OK -> {out_mp4} ({probe_dur(out_mp4):.1f}s, {total} frames)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("--accent", default="", help="comma-separated key words to highlight")
    ap.add_argument("--vo", default=None)
    ap.add_argument("--tts", default="macos")
    ap.add_argument("-o", "--out", default="out/shorts/_kinetic_demo.mp4")
    args = ap.parse_args()
    accent = {a.strip().lower() for a in args.accent.split(",") if a.strip()}
    render(args.text, accent, args.vo or args.text, Path(args.out), tts=args.tts)


if __name__ == "__main__":
    main()
