#!/usr/bin/env python3
"""Turn mined husband combos into DOAC spec files (with credibility fixes)."""
import json
from pathlib import Path

C = json.loads(Path("out/husband/mined_combos.json").read_text(encoding="utf-8"))

DROP = {"w4spcXq5uCw"}  # duplicate Temporal CEO; keep the a16z one (more provocative)
OVERRIDE = {  # fix attribution + clean clunky speaker names
    "ix9lzhk9oDo": {  # was hallucinated as "Spencer Kimball"; it's a Cockroach × Memori webinar
        "speaker_name": "David Joy & Adam",
        "speaker_title": "Cockroach SE × Memori Labs CEO",
        "affiliation": "Cockroach Labs × Memori Labs",
        "credibility_badge": "Cockroach Labs × Memori Labs",
    },
    "MPKd9t_XXOQ": {"speaker_name": "Neo4j architect", "speaker_title": "NODES AI 2026 speaker"},
    "uy6mql0G3Fg": {"speaker_name": "PingCAP / TiDB engineer", "speaker_title": "AGENTICON 2026 speaker"},
}

# tightened clip boundaries (agents left some 25-50s; re-picked to the core claim)
TIGHTEN = {
    "W2HVdB4Jbjs": [(645.1, 659.4), (426.5, 439.8), (740.0, 754.0)],
    "uy6mql0G3Fg": [(827.3, 836.0), (506.5, 519.8), (592.2, 606.0)],
    "E5PHOR7cz2w": [(1476.4, 1485.6), (1419.0, 1430.5), (1616.6, 1625.0)],
}

# agents emitted literal "\n" / escaped quotes — turn them into real characters
def decode(t):
    return t.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'") if isinstance(t, str) else t

# SHORT on-screen cards that echo the VO (agents wrote verbose bullet-lists that diverged from the voiceover)
ONSCREEN = {
    "MPKd9t_XXOQ": ("Agent memory?\n\nMost reach for\nvectors first.\n\nHe says: invert it.",
                    "So who searches?\n\nThe graph —\nfirst.",
                    "3 ways this\nbreaks at scale.\n\nIn the full talk."),
    "W2HVdB4Jbjs": ("Your agent's tools\ndon't belong in\nthe context window.",
                    "Then: what should\nan agent forget?",
                    "His real\nforgetting schema.\n\nIn the full talk."),
    "uy6mql0G3Fg": ("They left\nAurora MySQL.\n\n60 days later,\neverything changed.",
                    "Why the monolith\nbroke.",
                    "Designed for it —\nor blindsided?"),
    "NaIiiON5Sj4": ("Uber's loyalty\nsystem.\n\nZero database\nrows.",
                    "No DB.\n\nSo how do you\nun-corrupt millions?",
                    "The missing piece\nfor agent swarms.\n\nIn the full talk."),
    "E5PHOR7cz2w": ("Microsoft's new\nseparated-storage\nPostgres.\n\nThe numbers:",
                    "Where the speed\ncomes from.",
                    "A full agent —\ninside Postgres.\n\nIn the full talk."),
    "ix9lzhk9oDo": ("What agent traffic\ndoes to your\ndatabase.",
                    "The number\narchitects miss.",
                    "One cluster\nper agent?\n\nIn the full talk."),
}
# fix a VO credibility slip: speaker is a Cockroach SE + Memori CEO, NOT Cockroach's CEO
VO_FIX = {"ix9lzhk9oDo": {"intro_vo": "Cockroach Labs has a blunt prediction about what agent traffic does to your database."}}

specdir = Path("out/shorts/specs")
ids = []
for c in C:
    vid = c["video_id"]
    if vid in DROP:
        continue
    if vid in OVERRIDE:
        c.update(OVERRIDE[vid])
    if vid in TIGHTEN:
        for i, (ns, ne) in enumerate(TIGHTEN[vid]):
            if i < len(c["segments"]):
                c["segments"][i]["clip_start"] = ns
                c["segments"][i]["clip_end"] = ne
    c["segments"] = c["segments"][:2]  # keep the 2 strongest points (user prefers 1-2)
    sid = f"{vid}-db"
    start = min(s["clip_start"] for s in c["segments"])
    spec = {
        "id": sid, "video_id": vid, "channel": c["channel"], "title": c["title"],
        "speaker_name": c["speaker_name"], "speaker_title": c["speaker_title"],
        "affiliation": c["affiliation"], "credibility_badge": c["credibility_badge"],
        "topics": c["topics"],
        "intro_vo": c["intro_vo"], "intro_text": c["intro_text"],
        "segments": [{"clip_start": s["clip_start"], "clip_end": s["clip_end"],
                      "clip_caption": s["clip_caption"], "glue_vo": s["glue_vo"],
                      "glue_text": s["glue_text"]} for s in c["segments"]],
        "outro_vo": c["outro_vo"], "outro_text": c["outro_text"], "outro_cta": c["outro_cta"],
        "watch_url": f"https://www.youtube.com/watch?v={vid}&t={max(int(start) - 5, 0)}s",
    }

    # 1) decode literal escapes everywhere
    for k in ("intro_vo", "intro_text", "outro_vo", "outro_text", "outro_cta"):
        spec[k] = decode(spec[k])
    for s in spec["segments"]:
        for k in ("clip_caption", "glue_vo", "glue_text"):
            s[k] = decode(s[k])
    # 2) replace verbose on-screen cards with short VO-matching text
    if vid in ONSCREEN:
        intro_t, glue_t, outro_t = ONSCREEN[vid]
        spec["intro_text"] = intro_t
        spec["outro_text"] = outro_t
        if len(spec["segments"]) > 1:
            spec["segments"][1]["glue_text"] = glue_t
    # 3) VO credibility fixes
    if vid in VO_FIX:
        spec.update(VO_FIX[vid])

    (specdir / f"{sid}.doac.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    ids.append(sid)
    durs = [round(s["clip_end"] - s["clip_start"], 1) for s in c["segments"]]
    flag = " ⚠LONG" if any(d > 15 for d in durs) else ""
    print(f"  {sid:18s} | {c['speaker_name'][:22]:22} | clips {durs}{flag}")

Path("out/husband/_ids.json").write_text(json.dumps(ids), encoding="utf-8")
print(f"\n{len(ids)} specs written")
