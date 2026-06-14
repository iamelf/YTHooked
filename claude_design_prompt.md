# Claude Design prompt — "Hooked" teaser-feed web app

Design and build an interactive, **mobile-first responsive web app** called **Hooked** — a personalized *teaser feed* that helps a busy expert decide which long-form video (or paper) is worth their time. Build it as a modern React + Tailwind app (Next.js App Router) with clean, production-quality components and realistic mock data. Use shadcn/ui where helpful.

## The concept (read this first)
Inspired by RedNote / Xiaohongshu: instead of guessing from a YouTube thumbnail whether a 30-minute video is worth it, the user watches a **30–60s AI-generated teaser** that stacks the 2–3 most novel, provoking points from the long video, then decides whether to save it. The whole product is a *decision aid for what to watch next* — bite-size, scannable, trustworthy, time-respecting. Every screen should reduce the "is this worth my 30 minutes?" anxiety.

## The user (design the mock content for him)
A **principal product manager at AWS (Aurora / relational databases)**. He wants **cutting-edge, not 101** knowledge on: the memory & persistence layer for agentic AI, how SQL/NoSQL databases evolve for AI-native apps, and competitors/peers (e.g. Supabase, libSQL/Turso, Postgres-for-AI, vector DBs). He is time-poor and **credibility-sensitive** — he needs to instantly see *who* is talking and *why they're worth trusting*.

## Screen 1 — The Teaser Feed (primary)
Full-screen **vertical swipe feed** (TikTok/Reels style, scroll-snap, one card per viewport, mobile-first; on desktop center the column at ~480px on a dark canvas).

Each card = ONE long-form source, represented by its vertical 9:16 teaser video (autoplay muted on focus, loop, tap to unmute). Overlaid, RedNote-style "informative cover" metadata that is ALWAYS visible:
- **Credibility block (top priority):** speaker **name**, **title**, **affiliation**, and a prominent **credibility badge** (e.g. "Stanford Lecture", "Google — Head of Research", "AWS Principal Engineer", "Author, 200 papers"). This is the single most important UI element — never hide who's talking or why they're credible.
- **Source + cost-to-watch:** channel/source name, full-length runtime ("◷ 47 min"), and a topic tag.
- **What's inside:** 2–3 short "key point" chips summarizing the teaser's stacked points (so the value is scannable even with sound off).
- **Right action rail:** 👍 / 👎 (reaction), 🔖 Save to Watchlist, 🔊 mute, ⤴ share.
- **Primary CTA:** "▶ Watch full" (deep-links to the source at the hook timestamp).
- Thin progress bar across the top of the feed.

Capture engagement implicitly per card: 👍/👎, save, watch-full click, and teaser watch-through vs early-swipe (used to learn taste).

## Screen 2 — Watchlist
Everything the user 🔖'd. Each row: cover thumbnail, title, the credibility block, runtime, and a one-line "why you saved this". Actions:
- **"Send to YouTube"** — pushes saved videos to an auto-created "Hooked Watchlist" playlist on his connected YouTube account (assume an OAuth connection exists; show connected state + a fallback "copy links" if not connected).
- Mark watched / remove. Show a small "3 saved · 1h 58m to watch" summary.

## Screen 3 — Tune Your Feed (natural-language control)
A conversational control surface so he steers the feed in plain English:
- A persistent **prompt/chat input** ("Tune your feed…"). He types things like *"more on agent memory layers and libSQL, less generic LLM hype, I already know RAG basics."*
- The app **confirms how it adjusted** ("Boosting: agent memory, persistence layer, Postgres-for-AI · Muting: intro-level LLM content") and the feed visibly refreshes.
- Show current taste as **editable filter chips** (boosted topics in accent, muted topics struck-through) he can tap to remove/flip.
- A "credibility floor" toggle (e.g. "only show experts / primary sources").

## Screen 4 — Onboarding / Connect
- Connect YouTube (for watchlist push) and a quick taste setup: paste interests or pick from suggested cutting-edge DB/AI topics, plus an optional "what do you already know well? (so we skip the basics)" — encoding the novelty bar.

## Cross-cutting
- **Sources:** design the feed to blend multiple source types — YouTube video teasers AND **text-source teaser cards** (research papers from arXiv, company/funding items, tech-news). Text teasers are a card variant: same credibility block + key-point chips, but a generated summary visual instead of a video. Include a source-filter (All / Video / Papers / News).
- **Visual language:** clean, information-dense yet elegant; dark feed canvas; bold readable type; credibility badges visually prominent; one confident accent color for actions; trustworthy and calm (not clickbaity). Bite-size and scannable above all.
- **States:** loading, empty, "feed updated", connected/disconnected YouTube, end-of-feed.

## Deliverable
A working, clickable front-end prototype with mock data reflecting the DB/agentic-AI persona above (real-sounding speakers + credibility), wired interactions (swipe, 👍/👎, save→watchlist, NL tune→chips update), and responsive mobile + desktop layouts. Components should be cleanly separated so a real feed API can replace the mock data later.
