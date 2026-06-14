// Hooked — shared types (mirror of the Supabase schema)

export type SourceType = "youtube" | "arxiv" | "news";
export type ReactionKind = "up" | "down" | "save" | "watch_full" | "watchthrough";

export interface HookSpan {
  start: number;
  end: number;
}

/** One teaser card in the feed (public.feed_items). */
export interface FeedItem {
  id: string;
  external_id: string;
  source_type: SourceType;
  source_url: string;          // deep link to the full video/paper
  video_id: string | null;

  // credibility block — the UI must always surface who/why-trust-them
  speaker_name: string | null;
  speaker_title: string | null;
  affiliation: string | null;
  credibility_badge: string | null;

  title: string;
  runtime_sec: number | null;  // full source length
  key_points: string[];        // the 2-3 stacked points
  hook_timestamps: HookSpan[];
  topics: string[];

  teaser_url: string | null;   // Storage URL of the vertical .mp4
  teaser_seconds: number | null;
  thumb_url: string | null;    // Storage URL of the cover image
  published_at: string | null;
  created_at: string;
}

export interface Profile {
  user_id: string;
  display_name: string | null;
  expertise: Record<string, "expert" | "intermediate" | "novice">;
  boosted: string[];
  muted: string[];
  novelty_floor: string;
}
