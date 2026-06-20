"use client";
import { supabase } from "./supabase";
import type { Profile } from "./types";

/* ── auth ─────────────────────────────────────────────────────────────── */
// Sign-in IS "Connect YouTube": Google OAuth requesting the YouTube scope,
// so the session's provider_token can push the watchlist to a playlist.
export async function signInWithGoogle() {
  await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      scopes: "https://www.googleapis.com/auth/youtube openid email profile",
      queryParams: { access_type: "offline", prompt: "consent" },
      redirectTo: typeof window !== "undefined" ? window.location.origin : undefined,
    },
  });
}
export async function signOut() {
  await supabase.auth.signOut();
}

/* ── profile (taste) ──────────────────────────────────────────────────── */
export async function loadProfile(): Promise<Profile | null> {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return null;
  const { data } = await supabase.from("profiles").select("*").eq("user_id", user.id).maybeSingle();
  return (data as Profile) ?? null;
}
export async function saveProfile(patch: { boosted?: string[]; muted?: string[]; novelty_floor?: string }) {
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return;
  await supabase.from("profiles").upsert(
    { user_id: user.id, ...patch, updated_at: new Date().toISOString() },
    { onConflict: "user_id" },
  );
}

/* ── persisted reactions + watchlist (keyed by feed_items.id uuid) ──────── */
export async function loadReactionState(): Promise<{ liked: Set<string>; saved: Set<string>; watched: Set<string>; pushed: Set<string> }> {
  const liked = new Set<string>(), saved = new Set<string>(), watched = new Set<string>(), pushed = new Set<string>();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return { liked, saved, watched, pushed };
  const [{ data: rx }, { data: wl }] = await Promise.all([
    supabase.from("reactions").select("item_id, kind").eq("user_id", user.id),
    supabase.from("watchlist").select("item_id, status, youtube_pushed").eq("user_id", user.id),
  ]);
  (rx ?? []).forEach((r: any) => { if (r.kind === "up") liked.add(r.item_id); });
  (wl ?? []).forEach((w: any) => { saved.add(w.item_id); if (w.status === "watched") watched.add(w.item_id); if (w.youtube_pushed) pushed.add(w.item_id); });
  return { liked, saved, watched, pushed };
}
