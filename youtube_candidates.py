#!/usr/bin/env python3
"""
Stage 2 of the Shorts-discovery MVP: turn the Stage-1 taste profile into a
ranked pool of *long-form* YouTube candidates you haven't watched yet.

Pipeline:
  1. Read out/taste_profile.json  -> search_queries + topic/channel signals
  2. Read out/watch_events.csv    -> video_ids + channels already seen
  3. YouTube Data API search.list -> raw candidate video IDs per query
  4. YouTube Data API videos.list -> duration, views, publish date, etc.
  5. Filter: drop Shorts (duration < --min-seconds) and already-watched videos
  6. Rank: relevance (lexical or embedding) x channel-affinity x view-velocity
  7. Write out/candidates.json + out/candidates.csv

Auth: a plain API key is enough (these endpoints are public read-only).
  Get one at https://console.cloud.google.com -> APIs & Services -> Credentials,
  enable "YouTube Data API v3", create an API key, then:
      export YT_API_KEY=AIza...
      python3 youtube_candidates.py

Quota: search.list = 100 units/call, videos.list = 1 unit/call. 20 queries is
~2000 units, well under the free 10,000/day.
"""

import argparse
import csv
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import loadenv  # noqa: F401  (auto-loads environment.env: YT_API_KEY etc.)

API_ROOT = "https://www.googleapis.com/youtube/v3"
ISO_DUR_RE = re.compile(
    r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
)
WORD_RE = re.compile(r"[a-z0-9一-鿿]+")


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def api_get(endpoint: str, params: dict, api_key: str, retries: int = 3) -> dict:
    params = {**params, "key": api_key}
    url = f"{API_ROOT}/{endpoint}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (403, 429) and "quota" in body.lower():
                sys.exit(f"\nYouTube API quota exhausted:\n{body}\n")
            if e.code >= 500 and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            sys.exit(f"\nAPI error {e.code} on {endpoint}:\n{body}\n")
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            sys.exit(f"\nNetwork error on {endpoint}: {e}\n")
    return {}


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def iso_duration_seconds(s: str) -> int:
    m = ISO_DUR_RE.fullmatch(s or "")
    if not m:
        return 0
    days, hours, mins, secs = (int(x) if x else 0 for x in m.groups())
    return days * 86400 + hours * 3600 + mins * 60 + secs


def tokens(text: str) -> Counter:
    return Counter(WORD_RE.findall((text or "").lower()))


def parse_published(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Load Stage-1 outputs
# --------------------------------------------------------------------------- #
def load_profile(outdir: Path):
    prof_path = outdir / "taste_profile.json"
    if not prof_path.exists():
        sys.exit(f"Missing {prof_path} - run Stage 1 and generate the taste profile first.")
    profile = json.loads(prof_path.read_text(encoding="utf-8"))

    queries = profile.get("search_queries") or []
    if not queries:
        sys.exit("taste_profile.json has no search_queries.")

    # Build a reference text for relevance scoring from the profile.
    ref_parts = []
    for t in profile.get("interest_topics", []):
        w = {"core": 4, "strong": 2, "casual": 1}.get(t.get("strength"), 1)
        ref_parts += [t.get("topic", "")] * w
    ref_parts += [c.get("channel", "") for c in profile.get("favorite_channels", [])]
    ref_parts += profile.get("current_obsessions", [])
    ref_parts += profile.get("long_term_interests", [])
    ref_text = " ".join(ref_parts)

    fav_channels = {c.get("channel", "").lower() for c in profile.get("favorite_channels", [])}
    return queries, ref_text, fav_channels


def load_history(outdir: Path):
    csv_path = outdir / "watch_events.csv"
    seen_videos, seen_channels = set(), Counter()
    if csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                seen_videos.add(row["video_id"])
                if row["channel"]:
                    seen_channels[row["channel"].lower()] += 1
    return seen_videos, seen_channels


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
def search_candidates(queries, api_key, per_query, region, relevance_lang):
    """search.list per query -> {video_id: {"query":q, "bucket":b}}

    `queries` is a list of (query, bucket) tuples.
    """
    found = {}
    for i, (q, bucket) in enumerate(queries, 1):
        params = {
            "part": "snippet",
            "q": q,
            "type": "video",
            "maxResults": min(per_query, 50),
            "order": "relevance",
            "safeSearch": "none",
        }
        if region:
            params["regionCode"] = region
        if relevance_lang:
            params["relevanceLanguage"] = relevance_lang
        data = api_get("search", params, api_key)
        n_new = 0
        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid and vid not in found:
                found[vid] = {"query": q, "bucket": bucket}
                n_new += 1
        print(f"  [{i:2d}/{len(queries)}] +{n_new:2d} new  | [{bucket}] {q[:46]}")
    return found


def hydrate(video_ids, api_key):
    """videos.list in batches of 50 -> full metadata."""
    out = {}
    ids = list(video_ids)
    for start in range(0, len(ids), 50):
        batch = ids[start:start + 50]
        data = api_get(
            "videos",
            {"part": "snippet,contentDetails,statistics", "id": ",".join(batch)},
            api_key,
        )
        for item in data.get("items", []):
            out[item["id"]] = item
    return out


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #
def build_embedder():
    """Optional: use sentence-transformers if installed, else return None."""
    try:
        from sentence_transformers import SentenceTransformer  # noqa
    except ImportError:
        return None
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    def embed(texts):
        return model.encode(texts, normalize_embeddings=True)

    return embed


CJK_RE = re.compile(r"[一-鿿぀-ゟ゠-ヿ]")


def lang_bucket(text: str) -> str:
    """Crude but effective: anything with CJK characters is 'cjk', else 'latin'."""
    return "cjk" if CJK_RE.search(text or "") else "latin"


def lexical_score(ref_tokens: Counter, text: str) -> float:
    t = tokens(text)
    if not t:
        return 0.0
    overlap = sum(min(ref_tokens[w], c) for w, c in t.items())
    return overlap / math.sqrt(sum(t.values()))


def rank(candidates, ref_text, fav_channels, now, embedder):
    # Split the profile reference text into per-language token buckets so that
    # Chinese candidates are scored against Chinese interest signals (and vice
    # versa) instead of losing to English token overlap.
    ref_by_lang = {"latin": Counter(), "cjk": Counter()}
    for word, cnt in tokens(ref_text).items():
        ref_by_lang[lang_bucket(word)][word] += cnt

    if embedder is not None:
        # A multilingual embedder makes language buckets unnecessary; score globally.
        ref_vec = embedder([ref_text])[0]
        texts = [f"{c['title']} {c['channel']} {c['description'][:300]}" for c in candidates]
        vecs = embedder(texts)
        for c, v in zip(candidates, vecs):
            c["lang"] = lang_bucket(c["title"])
            c["relevance"] = float((ref_vec * v).sum())  # cosine (normalized)
    else:
        for c in candidates:
            c["lang"] = lang_bucket(c["title"])
            c["relevance"] = lexical_score(
                ref_by_lang[c["lang"]], f"{c['title']} {c['channel']} {c['description'][:300]}"
            )

    # Normalize relevance to 0..1 *within each language bucket* so the best
    # Chinese video and the best English video both land near 1.0 and interleave.
    for lang in ("latin", "cjk"):
        rels = [c["relevance"] for c in candidates if c["lang"] == lang] or [0.0]
        lo, hi = min(rels), max(rels)
        span = (hi - lo) or 1.0
        for c in candidates:
            if c["lang"] == lang:
                c["_rel_norm"] = (c["relevance"] - lo) / span

    for c in candidates:
        rel = c["_rel_norm"]
        age_days = max((now - c["published"]).total_seconds() / 86400.0, 1.0)
        velocity = c["views"] / age_days
        c["view_velocity"] = round(velocity, 1)
        # log-compressed velocity prior, capped
        vel_score = min(math.log10(velocity + 1) / 5.0, 1.0)
        affinity = 1.0 if c["channel"].lower() in fav_channels else 0.0
        freshness = math.pow(0.5, age_days / 180.0)  # 6-month half-life
        c["score"] = round(
            0.55 * rel + 0.20 * vel_score + 0.15 * affinity + 0.10 * freshness, 4
        )
    candidates.sort(key=lambda c: -c["score"])
    return candidates


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--outdir", type=Path, default=Path("out"))
    ap.add_argument("--api-key", default=os.environ.get("YT_API_KEY"))
    ap.add_argument("--per-query", type=int, default=25, help="search results per query (<=50)")
    ap.add_argument("--min-seconds", type=int, default=180,
                    help="drop anything shorter than this (Shorts filter)")
    ap.add_argument("--top", type=int, default=60, help="how many ranked candidates to keep")
    ap.add_argument("--max-per-channel", type=int, default=3,
                    help="diversity cap: keep at most N videos per channel")
    ap.add_argument("--english-only", action="store_true",
                    help="drop candidates whose title contains CJK or whose audio lang isn't English")
    ap.add_argument("--queries-file", type=Path, default=None,
                    help="JSON {bucket: [queries]} for discovery mode (frontier/discovery buckets); "
                         "overrides taste_profile search_queries and tags candidates by bucket")
    ap.add_argument("--region", default="", help="optional regionCode bias, e.g. US")
    ap.add_argument("--lang", default="", help="optional relevanceLanguage, e.g. en")
    ap.add_argument("--keep-seen-channels", action="store_true",
                    help="by default we still allow familiar channels; this is a no-op kept for clarity")
    args = ap.parse_args()

    if not args.api_key:
        sys.exit("No API key. Set YT_API_KEY env var or pass --api-key.")

    flat_queries, ref_text, fav_channels = load_profile(args.outdir)
    if args.queries_file:
        buckets = json.loads(args.queries_file.read_text(encoding="utf-8"))
        queries = [(q, b) for b, qs in buckets.items() for q in qs]
        print(f"Discovery mode: {len(queries)} queries across buckets "
              f"{ {b: len(qs) for b, qs in buckets.items()} }")
    else:
        queries = [(q, "taste") for q in flat_queries]
    seen_videos, seen_channels = load_history(args.outdir)
    print(f"History: {len(seen_videos)} watched videos")

    print("\nSearching...")
    found = search_candidates(queries, args.api_key, args.per_query, args.region, args.lang)
    print(f"  raw unique videos: {len(found)}")

    new_ids = [v for v in found if v not in seen_videos]
    print(f"  after de-dup vs history: {len(new_ids)}")

    print("\nHydrating metadata...")
    meta = hydrate(new_ids, args.api_key)

    now = datetime.now(timezone.utc)
    cjk = re.compile(r"[一-鿿぀-ゟ゠-ヿ]")
    candidates, n_short, n_nonenglish = [], 0, 0
    for vid, item in meta.items():
        sn, cd, st = item["snippet"], item["contentDetails"], item.get("statistics", {})
        dur = iso_duration_seconds(cd.get("duration", ""))
        if dur < args.min_seconds:
            n_short += 1
            continue
        if args.english_only:
            audio_lang = (sn.get("defaultAudioLanguage") or sn.get("defaultLanguage") or "").lower()
            if cjk.search(sn.get("title", "")) or (audio_lang and not audio_lang.startswith("en")):
                n_nonenglish += 1
                continue
        candidates.append({
            "video_id": vid,
            "title": sn.get("title", ""),
            "channel": sn.get("channelTitle", ""),
            "description": sn.get("description", ""),
            "published": parse_published(sn.get("publishedAt", "")),
            "duration_s": dur,
            "views": int(st.get("viewCount", 0) or 0),
            "found_by_query": found.get(vid, {}).get("query", ""),
            "bucket": found.get(vid, {}).get("bucket", ""),
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    print(f"  dropped {n_short} short/Shorts (<{args.min_seconds}s)"
          + (f", {n_nonenglish} non-English" if args.english_only else "")
          + f" | long-form candidates: {len(candidates)}")

    embedder = build_embedder()
    print(f"\nRanking ({'embeddings' if embedder else 'lexical, per-language buckets'})...")
    ranked_all = rank(candidates, ref_text, fav_channels, now, embedder)

    # Diversity cap: walk the ranked list and skip a video once its channel is full.
    per_chan, ranked = Counter(), []
    for c in ranked_all:
        if per_chan[c["channel"]] >= args.max_per_channel:
            continue
        per_chan[c["channel"]] += 1
        ranked.append(c)
        if len(ranked) >= args.top:
            break

    # Serialize (datetime -> iso)
    out_json = []
    for c in ranked:
        d = dict(c)
        d["published"] = c["published"].date().isoformat()
        d["duration_min"] = round(c["duration_s"] / 60, 1)
        out_json.append(d)

    stem = "candidates_discovery" if args.queries_file else "candidates"
    (args.outdir / f"{stem}.json").write_text(
        json.dumps(out_json, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with open(args.outdir / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "score", "bucket", "duration_min", "views", "published",
                    "channel", "title", "url", "found_by_query"])
        for i, c in enumerate(out_json, 1):
            w.writerow([i, c["score"], c.get("bucket", ""), c["duration_min"], c["views"],
                        c["published"], c["channel"], c["title"], c["url"], c["found_by_query"]])

    print(f"\nWrote out/{stem}.json + out/{stem}.csv ({len(out_json)} ranked)")
    if args.queries_file:
        bcount = Counter(c.get("bucket", "") for c in out_json)
        print(f"Bucket mix in result: {dict(bcount)}")
    print("\nTop 15:")
    for i, c in enumerate(out_json[:15], 1):
        print(f"  {i:2d}. [{c['score']:.3f}] {c.get('bucket','')[:9]:9} {c['duration_min']:5.1f}m "
              f"[{c['channel'][:18]:18}] {c['title'][:42]}")


if __name__ == "__main__":
    main()
