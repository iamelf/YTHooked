#!/usr/bin/env python3
"""
Stage 4a: merge all *.hooks.json with candidate metadata into out/feed.json,
one card per hook, ready for the vertical feed UI (feed.html).
"""
import json
from pathlib import Path

OUT = Path("out")
TDIR = OUT / "transcripts"


def main():
    cand_meta = {}
    cpath = OUT / "candidates.json"
    if cpath.exists():
        for c in json.loads(cpath.read_text(encoding="utf-8")):
            cand_meta[c["video_id"]] = c

    cards = []
    for hp in sorted(TDIR.glob("*.hooks.json")):
        h = json.loads(hp.read_text(encoding="utf-8"))
        vid = h["video_id"]
        meta = cand_meta.get(vid, {})
        for j, hook in enumerate(h.get("hooks", [])):
            cards.append({
                "id": f"{vid}-{j}",
                "video_id": vid,
                "title": h.get("title") or meta.get("title", ""),
                "channel": meta.get("channel", ""),
                "duration_min": meta.get("duration_min"),
                "summary": h.get("overall_summary", ""),
                "teaser_text": hook["teaser_text"],
                "why_it_works": hook.get("why_it_works", ""),
                "start_seconds": hook["start_seconds"],
                "end_seconds": hook["end_seconds"],
                "start_mmss": hook["start_mmss"],
                "end_mmss": hook["end_mmss"],
                "span_seconds": hook["end_seconds"] - hook["start_seconds"],
                "watch_full_url": f"https://www.youtube.com/watch?v={vid}&t={hook['start_seconds']}s",
            })

    # Interleave cards from different videos so the feed alternates sources.
    by_vid = {}
    for c in cards:
        by_vid.setdefault(c["video_id"], []).append(c)
    interleaved, i = [], 0
    max_len = max((len(v) for v in by_vid.values()), default=0)
    while i < max_len:
        for vid in by_vid:
            if i < len(by_vid[vid]):
                interleaved.append(by_vid[vid][i])
        i += 1

    (OUT / "feed.json").write_text(
        json.dumps(interleaved, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote out/feed.json with {len(interleaved)} cards "
          f"from {len(by_vid)} videos")
    for c in interleaved:
        print(f"  [{c['span_seconds']:2d}s] {c['video_id']} {c['start_mmss']}-{c['end_mmss']} | {c['teaser_text'][:60]}")


if __name__ == "__main__":
    main()
