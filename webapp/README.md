# Hooked — web app integration (read-side)

Drop-in data layer for the Next.js app that Claude Design produces. The serving
plane is already live in Supabase (8 teasers in `feed_items` + Storage).

## Setup
1. `npm i @supabase/supabase-js`
2. Copy `.env.local.example` → `.env.local` (publishable key already filled in).
3. Put `lib/` into the app.

## Wire the UI to data
- **Feed:** `const items = await fetchFeed()` → render each `FeedItem` as a card.
  - video: `<video src={item.teaser_url} poster={item.thumb_url} loop muted playsInline />`
  - credibility block (always show): `item.speaker_name`, `item.speaker_title`,
    `item.affiliation`, `item.credibility_badge`
  - key-point chips: `item.key_points` · cost-to-watch: `runtimeLabel(item.runtime_sec)`
  - "Watch full ▶": `item.source_url`
- **Reactions:** `recordReaction(item.id, "up" | "down" | "save" | "watch_full")`
- **Watchlist:** `toggleWatchlist(item.id, true/false)`, list via `fetchWatchlist()`

## Auth
Reads work anonymously (RLS exposes shared rows). Reactions + watchlist need a
signed-in user — enable **Supabase Auth → Google** (add YouTube scopes for the
later watchlist→YouTube push). Until then the write helpers no-op for anon.

## Server-only (Route Handlers, not in this lib)
- `POST /api/tune-feed` → Claude interprets NL → updates `profiles.boosted/muted`
- `POST /api/watchlist/push-youtube` → YouTube Data API `playlistItems.insert`
  using the user's stored Google token (from Supabase Auth)

## Boundaries
- Browser uses the **publishable** key only (this lib).
- The **secret** Supabase key stays in the Python generation worker.
- New teasers appear automatically: the worker upserts `feed_items` + uploads to
  Storage; the app just re-fetches.
