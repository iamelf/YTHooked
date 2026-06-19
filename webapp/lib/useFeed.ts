"use client";
import { useEffect, useState } from "react";
import { fetchFeed } from "./feed";
import type { FeedItem } from "./types";

export type CardType = "video" | "paper" | "news";

export interface Card {
  id: string;       // external_id — stable UI key
  dbId: string;     // feed_items.id (uuid) — FK target for reactions/watchlist
  type: CardType;
  topic: string;
  title: string;
  speaker: string;
  role: string;
  affiliation: string;
  badge: string;
  source: string;
  runtime: number;          // minutes
  hook: string | null;      // mm:ss
  points: string[];
  tags: string[];
  whySaved: string;
  teaser_url: string | null;
  thumb_url: string | null;
  source_url: string;
  videoId: string | null;   // YouTube video id, for pushing to a playlist
  read?: boolean;
  pullStat?: string;
  pullLabel?: string;
}

function mmss(sec: number): string {
  const s = Math.floor(sec);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function ytId(url?: string | null): string | null {
  if (!url) return null;
  const m = url.match(/(?:v=|youtu\.be\/|\/embed\/|\/shorts\/)([A-Za-z0-9_-]{11})/);
  return m ? m[1] : null;
}

function pull(item: FeedItem): { stat: string; label: string } {
  const hay = (item.key_points[0] || item.title || "");
  const m = hay.match(/(\$?\d[\d,.]*\s?(?:%|M|B|k|x|GW)?)/);
  if (m) return { stat: m[1].trim(), label: hay.replace(m[1], "").replace(/^[\s—-]+/, "").slice(0, 48) || item.topics[0] || "" };
  return { stat: (item.topics[0] || "New").slice(0, 10), label: item.key_points[0] || "" };
}

export function toCard(item: FeedItem): Card {
  const type: CardType = item.source_type === "arxiv" ? "paper" : item.source_type === "news" ? "news" : "video";
  const hookSec = item.hook_timestamps?.[0]?.start;
  const p = pull(item);
  return {
    id: item.external_id || item.id,
    dbId: item.id,
    type,
    topic: item.topics[0] || "Discovery",
    title: item.title,
    speaker: item.speaker_name || "Speaker",
    role: item.speaker_title || "",
    affiliation: item.affiliation || "",
    badge: item.credibility_badge || "",
    source: type === "paper" ? "arXiv" : type === "news" ? "News" : (item.affiliation || "Talk"),
    runtime: item.runtime_sec ? Math.round(item.runtime_sec / 60) : 0,
    hook: hookSec != null ? mmss(hookSec) : null,
    points: item.key_points || [],
    tags: item.topics || [],
    whySaved: item.key_points?.[0] || "",
    teaser_url: item.teaser_url,
    thumb_url: item.thumb_url,
    source_url: item.source_url,
    videoId: item.video_id || ytId(item.source_url),
    read: type !== "video",
    pullStat: p.stat,
    pullLabel: p.label,
  };
}

export function useFeed() {
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetchFeed(100)
      .then((items) => setCards(items.map(toCard)))
      .catch((e) => console.error("feed load failed", e))
      .finally(() => setLoading(false));
  }, []);
  return { cards, loading };
}
