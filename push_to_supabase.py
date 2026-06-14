#!/usr/bin/env python3
"""
Generation-plane → Supabase push. For each rendered teaser (spec + .mp4):
  1. extract a cover thumbnail (ffmpeg)
  2. upload <id>.mp4 and <id>.jpg to Supabase Storage bucket 'teasers'
  3. upsert a row into public.feed_items (keyed on external_id = spec id)

Env required:
    SUPABASE_URL=https://<project>.supabase.co
    SUPABASE_SECRET_KEY=sb_secret_...           # server-side key (new) — bypasses RLS
        (legacy service_role JWT also works; SUPABASE_SERVICE_KEY is still accepted)
    HOOKED_OWNER_ID=<auth user uuid>            # optional; omit for a shared feed

Usage:
    python3 push_to_supabase.py                 # all combos (ids containing 'combo')
    python3 push_to_supabase.py --ids a,b,c
    python3 push_to_supabase.py --match combo
"""
import argparse
import json
import mimetypes
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import loadenv  # noqa: F401  (auto-loads environment.env)

OUT = Path("out")
SHORTS = OUT / "shorts"
SPECS = SHORTS / "specs"
BUCKET = "teasers"


def http(method, url, headers, data=None):
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def storage_upload(base, key, local_path, dest_path):
    data = local_path.read_bytes()
    ctype = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
    status, body = http(
        "POST", f"{base}/storage/v1/object/{BUCKET}/{dest_path}",
        {"Authorization": f"Bearer {key}", "apikey": key,
         "Content-Type": ctype, "x-upsert": "true"}, data)
    if status not in (200, 201):
        raise RuntimeError(f"storage upload {dest_path} failed {status}: {body[:300]}")
    return f"{base}/storage/v1/object/public/{BUCKET}/{dest_path}"


def upsert_row(base, key, row):
    status, body = http(
        "POST", f"{base}/rest/v1/feed_items?on_conflict=external_id",
        {"Authorization": f"Bearer {key}", "apikey": key,
         "Content-Type": "application/json",
         "Prefer": "resolution=merge-duplicates,return=representation"},
        json.dumps(row).encode())
    if status not in (200, 201):
        raise RuntimeError(f"feed_items upsert failed {status}: {body[:400]}")


def probe_dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return round(float(r.stdout.strip()), 1)
    except ValueError:
        return None


def make_thumb(mp4, out_jpg):
    # grab a frame ~2s into the first real clip (skip the intro card)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "11", "-i", str(mp4),
                    "-frames:v", "1", "-q:v", "3", str(out_jpg)], check=False)
    if not out_jpg.exists():  # fallback: first frame
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mp4),
                        "-frames:v", "1", str(out_jpg)], check=False)


def source_runtime(video_id):
    j = OUT / "transcripts" / f"{video_id}.json"
    if j.exists():
        segs = json.loads(j.read_text(encoding="utf-8")).get("segments") or []
        if segs:
            return int(segs[-1]["start"] + segs[-1]["dur"])
    return None


def spec_to_row(spec, teaser_url, thumb_url, teaser_seconds, owner_id):
    segs = spec.get("segments") or [{
        "clip_start": spec.get("clip_start"), "clip_end": spec.get("clip_end"),
        "clip_caption": spec.get("clip_caption", "")}]
    return {
        "external_id": spec["id"],
        "owner_id": owner_id,
        "source_type": spec.get("source_type", "youtube"),
        "source_url": spec.get("watch_url", ""),
        "video_id": spec.get("video_id"),
        "speaker_name": spec.get("speaker_name"),
        "speaker_title": spec.get("speaker_title"),
        "affiliation": spec.get("affiliation"),
        "credibility_badge": spec.get("credibility_badge"),
        "title": spec.get("title", ""),
        "runtime_sec": source_runtime(spec.get("video_id", "")),
        "key_points": [s.get("clip_caption", "") for s in segs],
        "hook_timestamps": [{"start": s.get("clip_start"), "end": s.get("clip_end")} for s in segs],
        "topics": spec.get("topics", []),
        "teaser_url": teaser_url,
        "teaser_seconds": teaser_seconds,
        "thumb_url": thumb_url,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", default="", help="comma-separated spec ids")
    ap.add_argument("--match", default="combo", help="include specs whose id contains this")
    args = ap.parse_args()

    base = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    owner = os.environ.get("HOOKED_OWNER_ID") or None
    if not base or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SECRET_KEY (the sb_secret_... key) env vars.")
    if key.startswith("sb_publishable_"):
        sys.exit("That's the PUBLISHABLE key (client-side, RLS-enforced). The worker needs the "
                 "sb_secret_... key (Project Settings → API Keys → secret).")

    ids = {s.strip() for s in args.ids.split(",") if s.strip()}
    specs = []
    for sp in sorted(SPECS.glob("*.doac.json")):
        spec = json.loads(sp.read_text(encoding="utf-8"))
        sid = spec["id"]
        if ids and sid not in ids:
            continue
        if not ids and args.match and args.match not in sid:
            continue
        if (SHORTS / f"{sid}.mp4").exists():
            specs.append(spec)

    print(f"Pushing {len(specs)} teasers to {base}")
    ok = 0
    for spec in specs:
        sid = spec["id"]
        mp4 = SHORTS / f"{sid}.mp4"
        thumb = SHORTS / f"{sid}.jpg"
        try:
            make_thumb(mp4, thumb)
            teaser_url = storage_upload(base, key, mp4, f"{sid}.mp4")
            thumb_url = storage_upload(base, key, thumb, f"{sid}.jpg") if thumb.exists() else None
            row = spec_to_row(spec, teaser_url, thumb_url, probe_dur(mp4), owner)
            upsert_row(base, key, row)
            print(f"  ✓ {sid}")
            ok += 1
        except Exception as e:
            print(f"  ✗ {sid}: {e}")
    print(f"\nDone: {ok}/{len(specs)} pushed.")


if __name__ == "__main__":
    main()
