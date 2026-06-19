// Hooked — feed data access. Drop these into the Claude Design app; the UI
// components just call these and render FeedItem[]. Reads work for anyone
// (shared rows are RLS-readable by anon); reactions/watchlist require auth.

import { supabase } from "./supabase";
import type { FeedItem, ReactionKind } from "./types";

/** The teaser feed (shared pool today; per-user once owner_id is set). */
export async function fetchFeed(limit = 50): Promise<FeedItem[]> {
  const { data, error } = await supabase
    .from("feed_items")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(limit);
  if (error) throw error;
  return (data ?? []) as FeedItem[];
}

/** 👍 / 👎 / save / watch_full / watchthrough — one row per (user,item,kind). */
export async function recordReaction(itemId: string, kind: ReactionKind, value?: number) {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return; // anonymous: skip (or prompt sign-in)
  const { error } = await supabase
    .from("reactions")
    .upsert({ user_id: user.id, item_id: itemId, kind, value }, { onConflict: "user_id,item_id,kind" });
  if (error) throw error;
}

/** Add/remove from the watchlist. */
export async function toggleWatchlist(itemId: string, on: boolean) {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return;
  if (on) {
    const { error } = await supabase.from("watchlist").upsert({ user_id: user.id, item_id: itemId });
    if (error) throw error;
  } else {
    const { error } = await supabase.from("watchlist").delete().match({ user_id: user.id, item_id: itemId });
    if (error) throw error;
  }
}

/** Mark a saved item watched / unwatched (no-op if it isn't on the watchlist). */
export async function setWatched(itemId: string, watched: boolean) {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return;
  const { error } = await supabase
    .from("watchlist")
    .update({ status: watched ? "watched" : "saved" })
    .match({ user_id: user.id, item_id: itemId });
  if (error) throw error;
}

/** The saved watchlist, hydrated with each item's full FeedItem. */
export async function fetchWatchlist(): Promise<FeedItem[]> {
  const { data, error } = await supabase
    .from("watchlist")
    .select("added_at, item:feed_items(*)")
    .order("added_at", { ascending: false });
  if (error) throw error;
  return (data ?? []).map((r: any) => r.item as FeedItem);
}

/** Helper: "◷ 47 min" style label for a card. */
export function runtimeLabel(sec: number | null): string {
  if (!sec) return "";
  const m = Math.round(sec / 60);
  return m >= 60 ? `◷ ${Math.floor(m / 60)}h ${m % 60}m` : `◷ ${m} min`;
}
