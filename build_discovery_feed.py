#!/usr/bin/env python3
"""
Stage 2c: apply the (Claude-authored) novelty-gate curation to the discovery
candidate pool and emit an interleaved frontier/discovery feed.

CURATION is the novelty gate's verdict: each entry = (1-based rank in
candidates_discovery.json dump, axis, domain, why-it's-novel-to-YOU).
Everything not listed was judged canon/clickbait/too-basic and dropped.
"""
import json
from pathlib import Path

OUT = Path("out")

# (index, axis, domain, why) -- index is 1-based position in candidates_discovery.json
CURATION = [
    (1,  "frontier",  "ai-economics", "Grad-level economic modeling of AI — the rare intersection of BOTH your expert fields, at academic depth. Not an explainer."),
    (51, "discovery", "longevity",    "Attia on formal models of aging — mechanistic, well past the CGM/insulin talking points you already know."),
    (9,  "frontier",  "ai/ml",        "Days-old, ~0 views: scaling RL compute. Niche enough that even practitioners haven't digested it."),
    (15, "discovery", "history",      "Deep economic-history of Japan 1853–1989 — a domain you don't follow, told rigorously."),
    (55, "frontier",  "ai/ml",        "Causal mechanistic interpretability (Goodfire/Stanford) — a frontier subfield that's actively moving, not canon."),
    (48, "discovery", "biology",      "Adjacency goldmine: the underlying biology you're a layperson in, behind the AI-for-science you love."),
    (41, "frontier",  "finance/ai",   "A $400M fund's CONTRARIAN bet against AI startups — primary-source thesis that cuts against consensus."),
    (19, "discovery", "longevity",    "Recent longevity research front — new enough to update an intermediate."),
    (71, "frontier",  "ai+finance",   "Your exact intersection: building an equity-research agent on Claude. Niche practitioner build, days old."),
    (17, "discovery", "history",      "PBS deep-dive on plantation economics — substantive history that isn't in your feed."),
    (12, "frontier",  "ai-economics", "Stanford 'Economics of Applied AI' — academic, 2k views, the un-popular frontier my old ranker buried."),
    (74, "discovery", "econ-history", "Crisp causal account of the Great Depression — econ history you don't carry."),
    (46, "frontier",  "ai/ml",        "Mechanistic interpretability primer — a genuinely advancing subfield, not a transformer recap."),
    (38, "discovery", "drug-disc",    "Industry view of AI in drug discovery — the science side of your AI-for-science interest."),
    (45, "frontier",  "finance/macro","Non-obvious macro angle: AI power deficits as a market force. Recent, contrarian framing."),
    (64, "discovery", "longevity",    "A longevity claim pitched as overlooked — worth a novelty bet in your intermediate zone."),
]

REJECTED_EXAMPLES = {
    "investing 101 / explainer canon": ["IWT income-level investing", "George Kamel build wealth", "20 AI Concepts in 40 min", "Top 10 AI Skills 2026"],
    "famous-breakthrough recaps you know": ["AlphaFold 'AI Breakthrough'", "Short History of AI", "Intro to LLMs"],
    "clickbait / listicles / sleep content": ["100/101 History Facts", "Greatest Unsolved Mysteries", "3hr WW2 to fall asleep", "Bottom Is IN bull run"],
    "stale (pre-2021) for an expert": ["RAIL 2020", "John Langford 2017", "Wireless ML 2020"],
}


def main():
    pool = json.loads((OUT / "candidates_discovery.json").read_text(encoding="utf-8"))
    feed = []
    for rank, (idx, axis, domain, why) in enumerate(CURATION, 1):
        c = pool[idx - 1]
        feed.append({
            "rank": rank, "axis": axis, "domain": domain, "novelty_why": why,
            "video_id": c["video_id"], "title": c["title"], "channel": c["channel"],
            "duration_min": c["duration_min"], "published": c["published"],
            "views": c["views"], "url": c["url"],
        })
    (OUT / "discovery_feed.json").write_text(
        json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")

    n_f = sum(1 for x in feed if x["axis"] == "frontier")
    print(f"Wrote out/discovery_feed.json: {len(feed)} items "
          f"({n_f} frontier / {len(feed)-n_f} discovery), interleaved\n")
    for x in feed:
        print(f"  {x['rank']:2d}. [{x['axis'][:4]}|{x['domain'][:11]:11}|{x['published'][:7]}] "
              f"{x['channel'][:18]:18} — {x['title'][:42]}")
    print(f"\nDropped {len(pool)-len(feed)} of {len(pool)} as canon/clickbait/stale. Sample rejects:")
    for cat, ex in REJECTED_EXAMPLES.items():
        print(f"  - {cat}: {', '.join(ex[:3])}")


if __name__ == "__main__":
    main()
