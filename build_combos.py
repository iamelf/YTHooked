#!/usr/bin/env python3
"""Author one multi-point DOAC combo spec per source video (best 2-3 hooks, escalating)."""
import json
from pathlib import Path

H = json.load(open("out/mined_hooks.json", encoding="utf-8"))

def k(i):  # pull a mined hook's clip
    x = H[i]
    return {"clip_start": x["clip_start"], "clip_end": x["clip_end"], "clip_caption": x["clip_caption"]}

def man(s, e, cap):  # a manually-timed clip
    return {"clip_start": s, "clip_end": e, "clip_caption": cap}

def seg(clip, glue_vo="", glue_text=""):
    return {**clip, "glue_vo": glue_vo, "glue_text": glue_text}

COMBOS = [
  { "id": "7yNvz-combo", "video_id": "7yNvz_0Q1eQ", "channel": "Peter Attia MD",
    "title": "A new era of longevity science: models of aging (Brian Kennedy)",
    "intro_vo": "A scientist who's run aging labs for decades drops three things about longevity that even the wellness crowd gets wrong.",
    "intro_text": "Decades of\naging labs.\n\n3 things even\nexperts get\nwrong.",
    "segments": [
      seg(k(0)),
      seg(man(909.0, 917.5, "Almost every intervention that extends lifespan does one thing: lowers chronic inflammation."),
          "Ask him what actually moves the needle, and it keeps coming back to one thing.", "What actually\nmoves the\nneedle?"),
      seg(k(2), "And that biological-age test you were about to buy?", "That bio-age\ntest you\nwanted?"),
    ],
    "outro_vo": "In the full conversation, he names the one clock, built from ordinary blood markers, that actually predicts when you'll die.",
    "outro_text": "One test\nactually works.\n\nIt's not\nwhat you think.",
    "outro_cta": "▶ Full conversation", "watch_t": 3890 },

  { "id": "78Xa8-combo", "video_id": "78Xa8VkH7-g", "channel": "Goodfire",
    "title": "Causal Mechanistic Interpretability (Stanford lecture)",
    "intro_vo": "An interpretability researcher who takes models apart for a living quietly contradicts two things the A.I. field treats as settled.",
    "intro_text": "He takes AI\nmodels apart.\n\n2 'settled'\nideas he\nrejects.",
    "segments": [
      seg(k(3)),
      seg(k(5), "And that old 'it's just a giant lookup table' argument?", "'Just a giant\nlookup\ntable'?"),
    ],
    "outro_vo": "In the full lecture, he shows the two almost embarrassingly simple methods that beat every fancy technique for steering a model.",
    "outro_text": "What actually\nsteers a model?\n\n2 boring\nmethods win.",
    "outro_cta": "▶ Full lecture", "watch_t": 460 },

  { "id": "4_T4a-combo", "video_id": "4_T4aTLWtwY", "channel": "Stanford Digital Economy",
    "title": "Suproteem Sarkar: Economics of Applied AI",
    "intro_vo": "A finance professor got the raw data from a hundred thousand developers using A.I. Three findings jumped out.",
    "intro_text": "Data from\n100,000 devs.\n\n3 findings\nthat surprised\nhim.",
    "segments": [
      seg(k(6)),
      seg(k(8), "It's not just who adopted it. The output itself changed.", "And the\noutput?"),
      seg(k(7), "But the strangest part was who benefits most.", "Who wins\nmost? Not who\nyou'd think."),
    ],
    "outro_vo": "In the full talk, he breaks down how fast it all flipped once the models crossed a threshold, faster than he predicted.",
    "outro_text": "How fast did\nit flip?\n\nFaster than\nhe predicted.",
    "outro_cta": "▶ Full talk", "watch_t": 400 },

  { "id": "0LRJN-combo", "video_id": "0LRJN5bB8HU", "channel": "Deal Makers & Fakers",
    "title": "A $400M Fund's Contrarian Bet Against AI Startups",
    "intro_vo": "He's reviewed eleven thousand startups and bet against A.I. Here's the thinking behind it.",
    "intro_text": "11,000 startups.\nBet against AI.\n\nHis reasoning:",
    "segments": [
      seg(man(484.0, 491.0, "The moats aren't coming from the technology — they're coming from industry insider knowledge.")),
      seg(man(814.7, 824.0, "If you think this funding wave continues — no. We've already passed the peak."),
          "And the boom everyone's celebrating?", "The boom\neveryone\ncelebrates?"),
      seg(k(9), "He says even the money itself works nothing like it used to.", "Even the money\nchanged."),
    ],
    "outro_vo": "In the full interview, he names the unglamorous industries he's quietly buying into instead.",
    "outro_text": "So what's he\nbuying instead?\n\nHe names\nthem all.",
    "outro_cta": "▶ Full interview", "watch_t": 480 },

  { "id": "oRjLzxg8-combo", "video_id": "oRjLzxg8q6A", "channel": "Kent C. Dodds",
    "title": "Software architecture, human judgment, and AI",
    "intro_vo": "A veteran engineer who lives in A.I. coding tools all day says three things you won't hear from the people selling them.",
    "intro_text": "He lives in\nAI coding\ntools.\n\n3 blunt takes.",
    "segments": [
      seg(k(18)),
      seg(k(19), "He's also clear-eyed about what these models even are.", "What are these\nmodels,\nreally?"),
      seg(k(17), "And their shape? It's not about intelligence at all.", "Why shaped\nthis way?"),
    ],
    "outro_vo": "In the full talk, he draws the line on where human judgment still beats the model, and where it doesn't.",
    "outro_text": "Where do\nhumans still\nwin?\n\nHe draws\nthe line.",
    "outro_cta": "▶ Full talk", "watch_t": 1000 },

  { "id": "FPBwadTe-combo", "video_id": "FPBwadTeph0", "channel": "Google for Developers",
    "title": "Yossi Matias on the golden age of research",
    "intro_vo": "The head of research at Google shares three results that sound like science fiction but already happened.",
    "intro_text": "Google's\nhead of research.\n\n3 results that\nsound fake.",
    "segments": [
      seg(k(21)),
      seg(k(22), "That's software. Then there's the hardware.", "That's software.\nThen the\nhardware —"),
      seg(k(20), "And sometimes a single algorithm changes everything overnight.", "And one\nalgorithm —"),
    ],
    "outro_vo": "In the full talk, he explains how A.I. is starting to compress decades of scientific work into days, across field after field.",
    "outro_text": "Decades into\ndays.\n\nField after\nfield.",
    "outro_cta": "▶ Full talk", "watch_t": 1730 },
]

# credibility block (the "who / why trust them" the UI must always show) + topic tags
CRED = {
  "7yNvz-combo":    ("Brian Kennedy", "Aging biologist", "interviewed by Peter Attia", "Longevity researcher · Attia's guest", ["longevity", "aging", "metabolic health"]),
  "78Xa8-combo":    ("Goodfire research team", "Mechanistic interpretability", "Goodfire", "Stanford lecture", ["AI interpretability", "LLMs"]),
  "4_T4a-combo":    ("Suproteem Sarkar", "Economist", "Stanford Digital Economy Lab", "Stanford · 100k-developer study", ["AI economics", "developer productivity"]),
  "0LRJN-combo":    ("Denis Kalyshkin", "Principal", "I2BF Global Ventures ($400M)", "VC · reviewed 11,000 startups", ["venture capital", "AI startups", "deep tech"]),
  "oRjLzxg8-combo": ("Kent C. Dodds", "Engineer & educator", "epicweb.dev", "Veteran engineer", ["AI coding", "software architecture"]),
  "FPBwadTe-combo": ("Yossi Matias", "VP & Head of Research", "Google", "Google · Head of Research", ["AI research", "science", "quantum"]),
}

specdir = Path("out/shorts/specs")
for c in COMBOS:
    cred = CRED.get(c["id"], (None, None, None, None, []))
    spec = {
        "id": c["id"], "video_id": c["video_id"], "channel": c["channel"], "title": c["title"],
        "speaker_name": cred[0], "speaker_title": cred[1], "affiliation": cred[2],
        "credibility_badge": cred[3], "topics": cred[4],
        "intro_vo": c["intro_vo"], "intro_text": c["intro_text"],
        "segments": c["segments"],
        "outro_vo": c["outro_vo"], "outro_text": c["outro_text"], "outro_cta": c["outro_cta"],
        "watch_url": f"https://www.youtube.com/watch?v={c['video_id']}&t={c['watch_t']}s",
    }
    (specdir / f"{c['id']}.doac.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  {c['id']:18s} {len(c['segments'])} clips  [{c['channel']}]")

Path("out/_combo_ids.json").write_text(json.dumps([c["id"] for c in COMBOS]), encoding="utf-8")
print(f"\nwrote {len(COMBOS)} combo specs (+ existing robotics & novartis = 8 total)")
