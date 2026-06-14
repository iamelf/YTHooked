-- Hooked — Supabase schema (run in the Supabase SQL editor)
-- Serving plane reads these via RLS; the generation worker writes via the
-- service_role key (which bypasses RLS).

-- ─────────────────────────────────────────────────────────────────────────
-- profiles: per-user taste + novelty bar (1 row per auth user)
-- ─────────────────────────────────────────────────────────────────────────
create table if not exists public.profiles (
  user_id       uuid primary key references auth.users(id) on delete cascade,
  display_name  text,
  expertise     jsonb   not null default '{}'::jsonb,   -- {domain: expert|intermediate|novice}
  boosted       text[]  not null default '{}',           -- topics to surface more
  muted         text[]  not null default '{}',           -- topics to suppress
  novelty_floor text    not null default 'expert',        -- only show >= this bar
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- ─────────────────────────────────────────────────────────────────────────
-- feed_items: one generated teaser (video OR text source)
--   owner_id null  => shared/global pool; else scoped to a user
-- ─────────────────────────────────────────────────────────────────────────
create table if not exists public.feed_items (
  id               uuid primary key default gen_random_uuid(),
  owner_id         uuid references auth.users(id) on delete cascade,  -- null = shared
  external_id      text unique,                 -- our short id (dedupe on re-push)
  source_type      text not null default 'youtube',  -- youtube | arxiv | news
  source_url       text not null,               -- deep link to full video/paper
  video_id         text,

  -- credibility block (the "who/why trust them" the UI must always show)
  speaker_name      text,
  speaker_title     text,
  affiliation       text,
  credibility_badge text,                        -- e.g. "Stanford Lecture", "Google — Head of Research"

  title          text not null,
  runtime_sec    int,                            -- full source length
  key_points     jsonb not null default '[]'::jsonb,   -- ["...", "...", "..."]
  hook_timestamps jsonb not null default '[]'::jsonb,  -- [{start,end}, ...]
  topics         text[] not null default '{}',
  teaser_url     text,                           -- Storage URL of the .mp4
  teaser_seconds numeric,
  thumb_url      text,                           -- Storage URL of cover image
  published_at   timestamptz,
  created_at     timestamptz not null default now()
);
create index if not exists feed_items_owner_created on public.feed_items (owner_id, created_at desc);
create index if not exists feed_items_topics_gin on public.feed_items using gin (topics);

-- ─────────────────────────────────────────────────────────────────────────
-- reactions: engagement signal (drives taste learning)
-- ─────────────────────────────────────────────────────────────────────────
create table if not exists public.reactions (
  id         bigint generated always as identity primary key,
  user_id    uuid not null references auth.users(id) on delete cascade,
  item_id    uuid not null references public.feed_items(id) on delete cascade,
  kind       text not null,   -- up | down | save | watch_full | watchthrough
  value      numeric,         -- e.g. watchthrough fraction 0..1
  created_at timestamptz not null default now(),
  unique (user_id, item_id, kind)
);

-- ─────────────────────────────────────────────────────────────────────────
-- watchlist
-- ─────────────────────────────────────────────────────────────────────────
create table if not exists public.watchlist (
  user_id        uuid not null references auth.users(id) on delete cascade,
  item_id        uuid not null references public.feed_items(id) on delete cascade,
  status         text not null default 'saved',   -- saved | watched
  youtube_pushed boolean not null default false,
  added_at       timestamptz not null default now(),
  primary key (user_id, item_id)
);

-- ─────────────────────────────────────────────────────────────────────────
-- Row Level Security
-- ─────────────────────────────────────────────────────────────────────────
alter table public.profiles   enable row level security;
alter table public.feed_items enable row level security;
alter table public.reactions  enable row level security;
alter table public.watchlist  enable row level security;

create policy "own profile"        on public.profiles  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "read own/shared feed" on public.feed_items for select using (owner_id is null or owner_id = auth.uid());
create policy "own reactions"      on public.reactions for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "own watchlist"      on public.watchlist for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
-- (writes to feed_items come from the worker via service_role, which bypasses RLS)

-- ─────────────────────────────────────────────────────────────────────────
-- Storage bucket for teaser mp4s + thumbnails (public-read; worker writes via service_role)
-- ─────────────────────────────────────────────────────────────────────────
insert into storage.buckets (id, name, public)
values ('teasers', 'teasers', true)
on conflict (id) do nothing;
