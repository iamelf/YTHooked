#!/usr/bin/env python3
"""
Stage 3a: fetch a candidate video's transcript and emit a hook-detection prompt.

Run this from your home / residential IP -- at low volume YouTube won't block it.
Deployed cloud IPs (AWS/GCP/Azure) will hit RequestBlocked; that's the known
fragile layer flagged in the feasibility eval.

Usage:
    python3 fetch_transcript.py VIDEO_ID [VIDEO_ID ...]
    python3 fetch_transcript.py --from-candidates 3      # top 3 from out/candidates.json

Outputs per video (in out/transcripts/):
    <vid>.json            raw segments [{start, dur, text}] + language used
    <vid>.timestamped.txt compact [mm:ss] transcript for eyeballing
    <vid>.hook_prompt.md  LLM prompt to extract cliffhanger span(s)
"""

import argparse
import json
import sys
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

# Try these languages in order; auto-generated counts. Covers your EN + CJK mix.
PREF_LANGS = ["en", "en-US", "en-GB", "zh-Hant", "zh-Hans", "zh-TW", "zh-CN", "zh"]


def mmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


def fetch_one(api: YouTubeTranscriptApi, vid: str):
    """Return (segments, language, kind) or raise."""
    # Inspect available tracks so we can report manual vs auto-generated.
    try:
        tl = api.list(vid)
    except (TranscriptsDisabled, VideoUnavailable) as e:
        raise RuntimeError(f"no transcript list: {type(e).__name__}")

    available = [(t.language_code, t.is_generated) for t in tl]

    # Prefer a manual track in a preferred language, then auto-generated, then anything.
    pick = None
    for code in PREF_LANGS:
        for t in tl:
            if t.language_code == code and not t.is_generated:
                pick = t
                break
        if pick:
            break
    if pick is None:
        for code in PREF_LANGS:
            for t in tl:
                if t.language_code == code:
                    pick = t
                    break
            if pick:
                break
    if pick is None:
        # last resort: first track, translated to English if possible
        first = next(iter(tl), None)
        if first is None:
            raise RuntimeError("transcript list empty")
        pick = first

    fetched = pick.fetch()
    segments = [
        {"start": round(s.start, 2), "dur": round(s.duration, 2), "text": s.text.replace("\n", " ").strip()}
        for s in fetched
    ]
    kind = "auto-generated" if pick.is_generated else "manual"
    return segments, pick.language_code, kind, available


def compact_transcript(segments, window=15.0):
    """Group segments into ~window-second lines with [mm:ss] anchors."""
    lines, buf, buf_start = [], [], None
    for seg in segments:
        if buf_start is None:
            buf_start = seg["start"]
        buf.append(seg["text"])
        if seg["start"] + seg["dur"] - buf_start >= window:
            lines.append(f"[{mmss(buf_start)}] {' '.join(buf)}")
            buf, buf_start = [], None
    if buf:
        lines.append(f"[{mmss(buf_start)}] {' '.join(buf)}")
    return "\n".join(lines)


HOOK_PROMPT = """You are the "cliffhanger editor" for a Shorts-style discovery feed
that teases long-form YouTube videos. Below is a timestamped transcript of one
candidate video. Your job: find the 1-3 spans (each 15-45 seconds) that would make
a viewer most desperate to watch the full video, using the editing instincts of a
great YouTuber.

Rules for a good hook span:
  - Opens mid-tension or on a concrete, surprising claim with stakes.
  - Ends right BEFORE the payoff/answer is given (maximum open loop).
  - Self-contained enough to understand, incomplete enough to itch.
  - Prefer spans with a number, a reversal, a secret, or a bold promise.

Return ONLY JSON (no fences):
{
  "video_id": "{VID}",
  "language": "{LANG}",
  "overall_summary": "1 sentence on what the full video delivers",
  "hooks": [
    {
      "start_mmss": "MM:SS",
      "end_mmss": "MM:SS",
      "start_seconds": int,
      "end_seconds": int,
      "teaser_text": "the 1-line on-screen hook you'd overlay (curiosity gap, no spoiler)",
      "why_it_works": "1 line on the editing logic",
      "transcript_excerpt": "the exact words in this span"
    }
  ]
}

Video: {VID}  (transcript language: {LANG}, {KIND})
Title hint: {TITLE}

Transcript:
{TRANSCRIPT}
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video_ids", nargs="*")
    ap.add_argument("--from-candidates", type=int, default=0,
                    help="instead of ids, take top N from out/candidates.json")
    ap.add_argument("-o", "--outdir", type=Path, default=Path("out"))
    args = ap.parse_args()

    titles = {}
    ids = list(args.video_ids)
    if args.from_candidates:
        cands = json.loads((args.outdir / "candidates.json").read_text(encoding="utf-8"))
        for c in cands[:args.from_candidates]:
            ids.append(c["video_id"])
            titles[c["video_id"]] = c["title"]
    if not ids:
        sys.exit("Give VIDEO_IDs or --from-candidates N")

    tdir = args.outdir / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    api = YouTubeTranscriptApi()

    for vid in ids:
        print(f"\n=== {vid} ===")
        try:
            segments, lang, kind, available = fetch_one(api, vid)
        except Exception as e:
            print(f"  FAILED: {e}")
            print(f"  (this is the fragile layer -- some videos have captions disabled)")
            continue

        total_min = (segments[-1]["start"] + segments[-1]["dur"]) / 60 if segments else 0
        print(f"  {len(segments)} segments | {lang} | {kind} | ~{total_min:.0f} min")
        print(f"  tracks available: {available}")

        (tdir / f"{vid}.json").write_text(
            json.dumps({"video_id": vid, "language": lang, "kind": kind,
                        "segments": segments}, ensure_ascii=False, indent=1),
            encoding="utf-8")

        compact = compact_transcript(segments)
        (tdir / f"{vid}.timestamped.txt").write_text(compact, encoding="utf-8")

        prompt = (HOOK_PROMPT
                  .replace("{VID}", vid)
                  .replace("{LANG}", lang)
                  .replace("{KIND}", kind)
                  .replace("{TITLE}", titles.get(vid, "(unknown)"))
                  .replace("{TRANSCRIPT}", compact))
        (tdir / f"{vid}.hook_prompt.md").write_text(prompt, encoding="utf-8")
        print(f"  wrote {vid}.json / .timestamped.txt / .hook_prompt.md")


if __name__ == "__main__":
    main()
