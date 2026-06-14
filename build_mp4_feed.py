#!/usr/bin/env python3
"""
Stage 6: assemble all rendered DOAC Shorts (out/shorts/*.mp4) into a feed
manifest for the vertical swipe player (mp4_feed.html).

Reads each out/shorts/specs/*.doac.json that has a matching rendered .mp4.
Pass --exclude id1,id2 to drop specific shorts (e.g. canon ones).
"""
import argparse
import json
from pathlib import Path

OUT = Path("out")
SHORTS = OUT / "shorts"
SPECS = SHORTS / "specs"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exclude", default="", help="comma-separated short ids to skip")
    ap.add_argument("--only", default="", help="only include ids containing this substring (e.g. 'combo')")
    args = ap.parse_args()
    skip = {s.strip() for s in args.exclude.split(",") if s.strip()}

    cards = []
    for sp in sorted(SPECS.glob("*.doac.json")):
        spec = json.loads(sp.read_text(encoding="utf-8"))
        sid = spec["id"]
        if sid in skip:
            continue
        if args.only and args.only not in sid:
            continue
        mp4 = SHORTS / f"{sid}.mp4"
        if not mp4.exists():
            continue
        cards.append({
            "id": sid,
            "mp4": f"out/shorts/{sid}.mp4",
            "title": spec.get("title", ""),
            "channel": spec.get("channel", ""),
            "teaser": spec.get("clip_caption", ""),
            "watch_url": spec.get("watch_url", ""),
        })

    (OUT / "shorts_feed.json").write_text(
        json.dumps(cards, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote out/shorts_feed.json with {len(cards)} Shorts:")
    for c in cards:
        print(f"  - {c['id']}  ({c['channel']})")


if __name__ == "__main__":
    main()
