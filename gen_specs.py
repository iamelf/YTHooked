#!/usr/bin/env python3
"""Turn selected mined hooks into DOAC spec files for rendering."""
import json
from pathlib import Path

hooks = json.loads(Path("out/mined_hooks.json").read_text(encoding="utf-8"))

# selected indices (variety-weighted toward fresh axes vs the existing 5 shorts)
SELECTED = [0, 3, 5, 6, 8, 9, 12, 15, 16, 18, 21, 22]

specdir = Path("out/shorts/specs")
specdir.mkdir(parents=True, exist_ok=True)

written = []
for idx in SELECTED:
    h = hooks[idx]
    vid = h["video_id"]
    sid = f"{vid[:8]}-{h['axis']}-{idx}"
    start = float(h["clip_start"])
    spec = {
        "id": sid,
        "video_id": vid,
        "channel": h["channel"],
        "title": h["title"],
        "clip_start": round(start, 2),
        "clip_end": round(float(h["clip_end"]), 2),
        "clip_caption": h["clip_caption"],
        "intro_vo": h["intro_vo"],
        "intro_text": h["intro_text"],
        "outro_vo": h["outro_vo"],
        "outro_text": h["outro_text"],
        "outro_cta": h.get("outro_cta", "▶ Full interview"),
        "watch_url": f"https://www.youtube.com/watch?v={vid}&t={max(int(start)-5,0)}s",
    }
    (specdir / f"{sid}.doac.json").write_text(
        json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    written.append(sid)
    print(f"  {sid:28s} [{h['axis']}] {h['clip_caption'][:48]}")

print(f"\nwrote {len(written)} specs")
Path("out/_batch_ids.json").write_text(json.dumps(written), encoding="utf-8")
