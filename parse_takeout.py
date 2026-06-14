#!/usr/bin/env python3
"""
Stage 1 of the Shorts-discovery MVP: parse a Google Takeout YouTube
watch-history.json export into taste signals, and emit an LLM-ready
prompt for generating a structured taste profile.

Usage:
    python3 parse_takeout.py watch-history.json [-o OUTDIR]
                             [--half-life-days 30] [--recent-days 90]

Outputs (in OUTDIR, default ./out):
    watch_events.csv          cleaned event log (video_id, title, channel, ts)
    taste_signals.json        computed stats (rewatches, channel scores, cadence)
    taste_profile_prompt.md   paste-into-Claude prompt (or feed via API) that
                              returns the structured taste profile JSON

Notes on Takeout quirks handled here:
  - Ad impressions (details: "From Google Ads") are dropped.
  - Removed/private videos (no titleUrl) are dropped.
  - Music history (header "YouTube Music") is kept but tagged, since heavy
    music looping otherwise drowns out the rewatch signal.
  - Takeout cannot distinguish Shorts from regular videos; duration must be
    joined later from the Data API in Stage 2.
"""

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

VIDEO_ID_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{11})")


def parse_time(ts: str) -> datetime:
    # Takeout timestamps look like 2024-05-01T12:34:56.789Z (sometimes no millis)
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def load_events(path: Path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    events, dropped_ads, dropped_removed = [], 0, 0
    for item in raw:
        details = item.get("details") or []
        if any(d.get("name") == "From Google Ads" for d in details):
            dropped_ads += 1
            continue

        url = item.get("titleUrl")
        if not url:
            dropped_removed += 1
            continue

        m = VIDEO_ID_RE.search(url)
        video_id = m.group(1) if m else None
        if not video_id:
            dropped_removed += 1
            continue

        title = item.get("title", "")
        if title.startswith("Watched "):
            title = title[len("Watched "):]

        subs = item.get("subtitles") or []
        channel = subs[0].get("name", "") if subs else ""

        try:
            ts = parse_time(item["time"])
        except (KeyError, ValueError):
            continue

        events.append(
            {
                "video_id": video_id,
                "title": title.strip(),
                "channel": channel.strip(),
                "ts": ts,
                "is_music": item.get("header") == "YouTube Music",
            }
        )

    events.sort(key=lambda e: e["ts"])
    return events, dropped_ads, dropped_removed


def decay_weight(ts: datetime, now: datetime, half_life_days: float) -> float:
    age_days = max((now - ts).total_seconds() / 86400.0, 0.0)
    return math.pow(0.5, age_days / half_life_days)


def compute_signals(events, half_life_days: float, recent_days: int):
    now = max(e["ts"] for e in events)
    recent_cutoff = now - timedelta(days=recent_days)
    non_music = [e for e in events if not e["is_music"]]

    # --- rewatches (same video watched on 2+ distinct days) ---
    days_per_video = defaultdict(set)
    title_for, channel_for, last_ts = {}, {}, {}
    for e in non_music:
        days_per_video[e["video_id"]].add(e["ts"].date())
        title_for[e["video_id"]] = e["title"]
        channel_for[e["video_id"]] = e["channel"]
        last_ts[e["video_id"]] = e["ts"]

    rewatched = sorted(
        (
            {
                "video_id": vid,
                "title": title_for[vid],
                "channel": channel_for[vid],
                "distinct_days_watched": len(days),
                "last_watched": last_ts[vid].date().isoformat(),
            }
            for vid, days in days_per_video.items()
            if len(days) >= 2
        ),
        key=lambda r: (-r["distinct_days_watched"], r["last_watched"]),
    )

    # --- channel affinity: raw counts + recency-decayed score ---
    chan_count, chan_decayed, chan_recent = Counter(), Counter(), Counter()
    for e in non_music:
        if not e["channel"]:
            continue
        chan_count[e["channel"]] += 1
        chan_decayed[e["channel"]] += decay_weight(e["ts"], now, half_life_days)
        if e["ts"] >= recent_cutoff:
            chan_recent[e["channel"]] += 1

    top_alltime = [
        {"channel": c, "watches": n} for c, n in chan_count.most_common(30)
    ]
    top_decayed = [
        {"channel": c, "score": round(s, 2)}
        for c, s in chan_decayed.most_common(30)
    ]
    rising = sorted(
        (
            {
                "channel": c,
                "recent_watches": chan_recent[c],
                "alltime_watches": chan_count[c],
                "recent_share": round(chan_recent[c] / chan_count[c], 2),
            }
            for c in chan_recent
            if chan_recent[c] >= 3
        ),
        key=lambda r: (-r["recent_share"], -r["recent_watches"]),
    )[:15]

    # --- recent titles sample (recency-weighted reservoir of sorts) ---
    recent_titles = [
        {"title": e["title"], "channel": e["channel"], "date": e["ts"].date().isoformat()}
        for e in non_music
        if e["ts"] >= recent_cutoff
    ][-400:]

    # --- cadence ---
    by_hour = Counter(e["ts"].hour for e in non_music)
    by_dow = Counter(e["ts"].strftime("%A") for e in non_music)

    return {
        "generated_from": {
            "total_events": len(events),
            "non_music_events": len(non_music),
            "music_events": len(events) - len(non_music),
            "first_event": events[0]["ts"].date().isoformat(),
            "last_event": now.date().isoformat(),
            "recent_window_days": recent_days,
            "half_life_days": half_life_days,
        },
        "rewatched_videos": rewatched[:50],
        "top_channels_alltime": top_alltime,
        "top_channels_recency_weighted": top_decayed,
        "rising_channels": rising,
        "recent_titles_sample": recent_titles,
        "watch_hour_histogram": dict(sorted(by_hour.items())),
        "watch_dow_histogram": dict(by_dow),
    }


PROMPT_TEMPLATE = """You are building a YouTube taste profile that will drive a \
personalized long-form-video discovery feed. Below are signals computed from my \
real watch history. Rewatched videos and recency-weighted channels are the \
strongest signals; the recent-titles sample shows current interests; all-time \
channels show long-term interests.

Return ONLY a JSON object with this shape (no markdown fences, no commentary):
{
  "interest_topics": [
    {"topic": str, "strength": "core|strong|casual",
     "trend": "rising|stable|fading", "evidence": str}
  ],
  "favorite_channels": [{"channel": str, "why": str}],
  "content_formats": [str],          // e.g. "deep technical explainers", "video essays >30min"
  "current_obsessions": [str],       // things heavily watched in the recent window
  "long_term_interests": [str],
  "avoid": [str],                    // patterns conspicuously absent or abandoned
  "search_queries": [str]            // 15-20 diverse YouTube search queries, mixing
                                     // core topics, rising interests, and 2-3
                                     // adjacent-exploration queries
}

Signals:
```json
{SIGNALS}
```
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("history", type=Path, help="Path to Takeout watch-history.json")
    ap.add_argument("-o", "--outdir", type=Path, default=Path("out"))
    ap.add_argument("--half-life-days", type=float, default=30.0)
    ap.add_argument("--recent-days", type=int, default=90)
    args = ap.parse_args()

    events, ads, removed = load_events(args.history)
    if not events:
        sys.exit("No usable watch events found - is this a watch-history.json from Takeout (JSON format)?")

    args.outdir.mkdir(parents=True, exist_ok=True)

    with open(args.outdir / "watch_events.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["video_id", "title", "channel", "timestamp", "is_music"])
        for e in events:
            w.writerow([e["video_id"], e["title"], e["channel"], e["ts"].isoformat(), int(e["is_music"])])

    signals = compute_signals(events, args.half_life_days, args.recent_days)
    with open(args.outdir / "taste_signals.json", "w", encoding="utf-8") as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)

    prompt = PROMPT_TEMPLATE.replace(
        "{SIGNALS}", json.dumps(signals, indent=1, ensure_ascii=False)
    )
    (args.outdir / "taste_profile_prompt.md").write_text(prompt, encoding="utf-8")

    g = signals["generated_from"]
    print(f"Parsed {g['total_events']} events "
          f"({g['non_music_events']} video, {g['music_events']} music; "
          f"dropped {ads} ads, {removed} removed/unparseable)")
    print(f"Span: {g['first_event']} to {g['last_event']}")
    print(f"Rewatched videos: {len(signals['rewatched_videos'])} | "
          f"channels seen: {len(signals['top_channels_alltime'])}+")
    print(f"\nWrote to {args.outdir}/: watch_events.csv, taste_signals.json, taste_profile_prompt.md")
    print("Next: feed taste_profile_prompt.md to Claude (paste or API) to get the taste profile JSON.")


if __name__ == "__main__":
    main()
