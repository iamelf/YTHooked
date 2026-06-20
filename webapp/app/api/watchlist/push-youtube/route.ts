import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

// Pushes saved videos into a "Burrfeed Watchlist" playlist on the user's
// YouTube account, using the Google OAuth provider token from their Supabase session.
const YT = "https://www.googleapis.com/youtube/v3";
const PLAYLIST_TITLE = "Burrfeed Watchlist";

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
    // 1. reuse an existing "Burrfeed Watchlist" playlist, else create one
    const mine = await yt("playlists?part=snippet&mine=true&maxResults=50", token);
    let playlistId: string | undefined =
      mine.items?.find((p: any) => p.snippet?.title === PLAYLIST_TITLE)?.id;
    if (!playlistId) {
      const created = await yt("playlists?part=snippet,status", token, {
        method: "POST",
        body: JSON.stringify({
          snippet: { title: PLAYLIST_TITLE, description: "Saved from Burrfeed" },
          status: { privacyStatus: "private" },
        }),
      });
      playlistId = created.id;
    }

    // 2. list videos already in the playlist so we never insert duplicates
    const existing = new Set<string>();
    let pageToken = "";
    for (let i = 0; i < 4; i++) { // up to ~200 items
      const page = await yt(
        `playlistItems?part=contentDetails&playlistId=${playlistId}&maxResults=50${pageToken ? `&pageToken=${pageToken}` : ""}`,
        token,
      );
      (page.items || []).forEach((it: any) => { const v = it.contentDetails?.videoId; if (v) existing.add(v); });
      if (!page.nextPageToken) break;
      pageToken = page.nextPageToken;
    }

    // 3. add only the videos not already present (best-effort)
    let added = 0, alreadyThere = 0;
    const errors: string[] = [];
    for (const videoId of videoIds) {
      if (existing.has(videoId)) { alreadyThere++; continue; }
      try {
        await yt("playlistItems?part=snippet", token, {
          method: "POST",
          body: JSON.stringify({
            snippet: { playlistId, resourceId: { kind: "youtube#video", videoId } },
          }),
        });
        existing.add(videoId);
        added++;
      } catch (e: any) {
        errors.push(`${videoId}: ${e.message?.slice(0, 80)}`);
      }
    }
    return NextResponse.json({
      playlistId,
      added,
      alreadyThere,
      url: `https://www.youtube.com/playlist?list=${playlistId}`,
      errors: errors.length ? errors : undefined,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e?.message ?? "push failed" }, { status: 500 });
  }
}
