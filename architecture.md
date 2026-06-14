# Hooked — hosting architecture

Stack verdict: **Vercel + Supabase + Next.js is the right call for the app.** The only
constraint that reshapes things: the **YouTube teaser-generation pipeline cannot run on
Vercel** (datacenter IPs get SABR/403-blocked by YouTube, and ffmpeg/yt-dlp renders are
heavy/long). So we split into a SERVING plane and a GENERATION plane.

```
                          ┌──────────────────────── SERVING PLANE ────────────────────────┐
   husband's phone  ─────▶│  Next.js on Vercel (React + Tailwind + shadcn)                  │
                          │   • teaser feed (vertical swipe), watchlist, tune-feed, onboard │
                          │   • Route Handlers / Server Actions:                            │
                          │       - tune-feed  → Claude (AI SDK / AI Gateway) → update taste│
                          │       - reactions  → write to Supabase                          │
                          │       - watchlist  → YouTube Data API (playlistItems.insert)    │
                          │   • Vercel Cron: lightweight per-user re-rank; arXiv/news fetch │
                          └───────────────┬───────────────────────────────┬────────────────┘
                                          │ reads/writes                   │ OAuth + tokens
                                          ▼                                ▼
                          ┌──────────────────────── SUPABASE ─────────────────────────────┐
                          │  Auth: Google provider w/ YouTube scopes (stores OAuth tokens) │
                          │  Postgres: profiles, feed_items, reactions, watchlist, sources │
                          │            (pgvector later for embedding novelty/dedup)        │
                          │  Storage: teaser .mp4 + thumbnails (CDN-served)                │
                          └───────────────▲───────────────────────────────────────────────┘
                                          │ inserts feed_items + uploads mp4s
                          ┌───────────────┴──────── GENERATION PLANE (NOT on Vercel) ──────┐
                          │  Python worker on a RESIDENTIAL IP (your Mac → later a VPS w/   │
                          │  residential proxy). The existing scripts, on a cron:          │
                          │   taste/expertise → retrieve (YouTube Data API) → transcript   │
                          │   → hook-mine (Claude) → yt-dlp clip (android client) → ffmpeg  │
                          │   + Gemini TTS → upload mp4 to Supabase Storage → insert rows   │
                          └────────────────────────────────────────────────────────────────┘
```

## Who does what
- **Vercel / Next.js (serving):** all UI; light, fast server work only — auth callbacks,
  the NL "tune feed" call (Claude), recording reactions, pushing watchlist to YouTube,
  serving the ranked feed from Supabase. No video work here.
- **Supabase (state):** Auth (Google OAuth + YouTube scopes + token storage), Postgres
  (all app data), Storage (teaser MP4s + thumbs via CDN).
- **Generation worker (off Vercel, residential IP):** the heavy/fragile pipeline. Produces
  teasers offline and writes results to Supabase. The app only ever READS what it produced.

## Important nuance: text sources are different
arXiv / Hacker News / tech-news have **no IP-block and need no ffmpeg** → a text→teaser
card generator (Claude summary) **can** run on **Vercel Cron** and write straight to
`feed_items`. Only the YouTube *video* pipeline needs the residential worker.

## Data model (Supabase Postgres, sketch)
- `profiles(user_id, expertise jsonb, boosted text[], muted text[], novelty_floor, created_at)`
- `feed_items(id, owner_id|null, source_type[youtube|arxiv|news], source_url, video_id,
   speaker_name, speaker_title, affiliation, credibility_badge, title, runtime_sec,
   key_points jsonb, teaser_url, thumb_url, hook_timestamps jsonb, topics text[],
   published_at, created_at)`  ← note the new speaker/credibility fields from the feedback
- `reactions(user_id, item_id, kind[up|down|save|watch_full|watchthrough], value, created_at)`
- `watchlist(user_id, item_id, status[saved|watched], youtube_pushed bool, added_at)`

## Phased path
- **Phase 1 (ship to husband fast):** generation worker = the existing Python scripts run
  **locally on your Mac**, pushing to Supabase. Next.js app on Vercel reads it. YouTube
  OAuth via Supabase Auth; tune-feed via Claude Route Handler. Minimal moving parts.
- **Phase 2:** move the worker to a scheduled VPS + residential proxy (freshness without
  your laptop); add the arXiv text source on Vercel Cron; pgvector for novelty/dedup.

## Flags
- **ToS:** downloading + re-rendering YouTube is ToS-gray — fine for a private tool;
  revisit (licensing / embed-only Track A) before any public launch.
- **Cost:** generation (Claude hook-mining + Gemini TTS + render time) is the spend; it's
  batched offline so it doesn't hit request latency or Vercel function limits.
- **LLM calls on Vercel:** use Vercel AI SDK / AI Gateway with a Claude model for the
  light per-user work (tune-feed, text-teaser summaries).
```
