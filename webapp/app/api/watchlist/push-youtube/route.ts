import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

// Pushes saved videos into a "Hooked Watchlist" playlist on the user's YouTube
// account, using the Google OAuth provider token from their Supabase session.
const YT = "https://www.googleapis.com/youtube/v3";
const PLAYLIST_TITLE = "Hooked Watchlist";

async function yt(path: string, token: string, init?: RequestInit) {
  const r = await fetch(`${YT}/${path}`, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function POST(req: NextRequest) {
  let body: any;
  try { body = await req.json(); } catch { return NextResponse.json({ error: "bad json" }, { status: 400 }); }
  const token = body?.providerToken;
  const videoIds: string[] = (body?.videoIds ?? []).filter(Boolean);
  if (!token) return NextResponse.json({ error: "no_youtube_token" }, { status: 401 });
  if (!videoIds.length) return NextResponse.json({ error: "no_videos" }, { status: 400 });

  try {
    // 1. reuse an existing "Hooked Watchlist" playlist, else create one
    const mine = await yt("playlists?part=snippet&mine=true&maxResults=50", token);
    let playlistId: string | undefined =
      mine.items?.find((p: any) => p.snippet?.title === PLAYLIST_TITLE)?.id;
    if (!playlistId) {
      const created = await yt("playlists?part=snippet,status", token, {
        method: "POST",
        body: JSON.stringify({
          snippet: { title: PLAYLIST_TITLE, description: "Saved from Hooked" },
          status: { privacyStatus: "private" },
        }),
      });
      playlistId = created.id;
    }

    // 2. add each video (best-effort; skip dupes/failures)
    let added = 0;
    const errors: string[] = [];
    for (const videoId of videoIds) {
      try {
        await yt("playlistItems?part=snippet", token, {
          method: "POST",
          body: JSON.stringify({
            snippet: { playlistId, resourceId: { kind: "youtube#video", videoId } },
          }),
        });
        added++;
      } catch (e: any) {
        errors.push(`${videoId}: ${e.message?.slice(0, 80)}`);
      }
    }
    return NextResponse.json({
      playlistId,
      added,
      url: `https://www.youtube.com/playlist?list=${playlistId}`,
      errors: errors.length ? errors : undefined,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message ?? "push failed" }, { status: 500 });
  }
}
