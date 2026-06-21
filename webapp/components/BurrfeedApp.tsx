"use client";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useFeed, type Card } from "@/lib/useFeed";
import { recordReaction, toggleWatchlist, setWatched, markPushed } from "@/lib/feed";
import { supabase } from "@/lib/supabase";
import { signInWithGoogle, signOut, loadProfile, saveProfile, loadReactionState } from "@/lib/account";

/* ── design tokens (light editorial theme, teal accent) ────────────────── */
const ACCENT = "oklch(0.4 0.06 218)";          // teal-blue
const ACCENT_SOFT = "oklch(0.4 0.06 218 / 0.12)";
const ACCENT_LINE = "oklch(0.4 0.06 218 / 0.28)";
const ON_ACCENT = "oklch(0.97 0.014 90)";      // text/icon on accent fills
const TXT = "oklch(0.24 0.012 165)";           // ink (dark text on light)
const DIM = "oklch(0.44 0.012 150)";
const MUTE = "oklch(0.58 0.012 110)";
const DANGER = "oklch(0.55 0.16 33)";
const POS = "oklch(0.5 0.09 168)";
const BG = "oklch(0.92 0.016 86)";             // page
const PAPER = "oklch(0.955 0.014 88)";         // screen background
const CARDBG = "oklch(0.985 0.008 88)";        // surface (cards)
const SURFACE2 = "oklch(0.93 0.016 86)";
const HAIR = "oklch(0.3 0.02 120 / 0.13)";
const LINE2 = "oklch(0.3 0.02 120 / 0.07)";

const DICT = [
  { chip: "Agent memory", kw: ["agent memory", "memory layer", "agent memories", "memory"] },
  { chip: "Persistence layer", kw: ["persistence", "persist"] },
  { chip: "libSQL / Turso", kw: ["libsql", "turso", "sqlite"] },
  { chip: "Postgres-for-AI", kw: ["postgres", "pgvector", "neon", "supabase"] },
  { chip: "Vector databases", kw: ["vector db", "vector database", "vectors", "pinecone"] },
  { chip: "Hybrid retrieval", kw: ["hybrid", "bm25", "retrieval"] },
  { chip: "SQL evolution", kw: ["sql evolution", "sql for ai", "native sql", "first-class vector"] },
  { chip: "Serverless DB", kw: ["serverless", "scale-to-zero", "branching", "edge"] },
  { chip: "Durable execution", kw: ["durable", "temporal", "workflow", "execution"] },
  { chip: "RAG basics", kw: ["rag"] },
  { chip: "LLM hype", kw: ["llm hype", "generic llm", "hype", "generic"] },
  { chip: "NoSQL", kw: ["nosql", "mongodb", "mongo"] },
];
const SUGGEST_BOOST = ["Agent memory", "Persistence layer", "libSQL / Turso", "Postgres-for-AI", "Vector databases", "Hybrid retrieval", "Serverless DB", "Durable execution"];
const SUGGEST_KNOW = ["RAG basics", "LLM hype", "Intro / 101 content"];
const EXAMPLES = [
  "More on agent memory layers and libSQL, less generic LLM hype",
  "Skip RAG basics — I already know them",
  "More Postgres-for-AI and serverless branching",
  "Only primary sources and expert talks",
];

const ms = (icon: string, style?: React.CSSProperties) => <span className="ms" style={style}>{icon}</span>;
function initials(name: string) {
  const drop = ["dr", "prof", "mr", "ms", "mrs", "the"];
  const p = name.replace(/[^A-Za-z, ]/g, "").split(/[ ,]+/).filter(Boolean).filter((w) => !drop.includes(w.toLowerCase()));
  if (p.length >= 2) return (p[0][0] + p[1][0]).toUpperCase();
  if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}
function likeBase(id: string) { let h = 0; for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0; return 200 + (h % 6200); }
function fmtK(n: number) { return n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, "") + "k" : "" + n; }
function fmtTotal(min: number) { const h = Math.floor(min / 60), m = min % 60; return h ? `${h}h ${m ? m + "m" : ""}`.trim() : `${m}m`; }
function chipMatch(chip: string, hay: string) { const e = DICT.find((d) => d.chip === chip); return (e ? e.kw : [chip.toLowerCase()]).some((k) => hay.includes(k)); }

type Tab = "feed" | "tune" | "saved" | "you";
interface CState { liked?: boolean; saved?: boolean; watched?: boolean }

export default function BurrfeedApp() {
  const { cards: allCards, loading } = useFeed();
  const [tab, setTab] = useState<Tab>("feed");
  const [showOnboarding, setShowOnboarding] = useState(true);
  const [muted, setMuted] = useState(true);            // browsers require muted to autoplay
  const [speed, setSpeed] = useState(1.25);            // default a touch faster than 1× for experts
  const soundPref = useRef(false);                     // has the user opted into sound before?
  const [user, setUser] = useState<any>(null);
  const [providerToken, setProviderToken] = useState<string | null>(null);
  const yt = !!user; // signed in with Google (YouTube scope) === "connected"
  const [sourceFilter, setSourceFilter] = useState<"all" | "video" | "paper" | "news">("all");
  const [credFloor, setCredFloor] = useState(false);
  const [boosted, setBoosted] = useState<string[]>([]);
  const [mutedTopics, setMutedTopics] = useState<string[]>([]);
  const [cstate, setCstate] = useState<Record<string, CState>>({});
  const [feedUpdated, setFeedUpdated] = useState(false);
  const [tuneLog, setTuneLog] = useState<{ boost: string[]; mute: string[] } | null>(null);
  const [pushedIds, setPushedIds] = useState<Set<string>>(new Set()); // external_ids already in YouTube
  const [toast, setToast] = useState<string | null>(null);
  const [tuneInput, setTuneInput] = useState("");
  const [obPick, setObPick] = useState<string[]>([]);
  const [obKnow, setObKnow] = useState<string[]>([]);
  const [obInput, setObInput] = useState("");
  const [obAdded, setObAdded] = useState<string[]>([]);
  const toastT = useRef<any>(null);
  const updT = useRef<any>(null);

  const cs = (id: string) => cstate[id] || {};
  const setCS = (id: string, patch: CState) => setCstate((s) => ({ ...s, [id]: { ...(s[id] || {}), ...patch } }));
  const showToast = (m: string) => { setToast(m); clearTimeout(toastT.current); toastT.current = setTimeout(() => setToast(null), 1900); };
  const pulse = () => { setFeedUpdated(true); clearTimeout(updT.current); updT.current = setTimeout(() => setFeedUpdated(false), 2400); };

  // ── auth session ──
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setUser(data.session?.user ?? null);
      if (data.session?.provider_token) setProviderToken(data.session.provider_token);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => {
      setUser(session?.user ?? null);
      if (session?.provider_token) setProviderToken(session.provider_token);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  // ── hydrate persisted taste + reactions once signed in and feed is loaded ──
  useEffect(() => {
    if (!user || !allCards.length) return;
    (async () => {
      const [prof, rx] = await Promise.all([loadProfile(), loadReactionState()]);
      if (prof) { setBoosted(prof.boosted || []); setMutedTopics(prof.muted || []); setCredFloor(prof.novelty_floor === "expert"); }
      const next: Record<string, CState> = {};
      const pushedNext = new Set<string>();
      allCards.forEach((c) => {
        const st = { liked: rx.liked.has(c.dbId), saved: rx.saved.has(c.dbId), watched: rx.watched.has(c.dbId) };
        if (st.liked || st.saved || st.watched) next[c.id] = st;
        if (rx.pushed.has(c.dbId)) pushedNext.add(c.id);
      });
      setCstate(next);
      setPushedIds(pushedNext);
    })();
  }, [user, allCards]); // eslint-disable-line react-hooks/exhaustive-deps

  /* scoring + filtering */
  const scoreCard = (c: Card) => {
    const hay = (c.tags.join(" ") + " " + c.topic + " " + c.title).toLowerCase();
    let s = 0;
    boosted.forEach((b) => { if (chipMatch(b, hay)) s += 10; });
    mutedTopics.forEach((m) => { if (chipMatch(m, hay)) s -= 6; });
    return s;
  };
  const feedCards = useMemo(() => {
    const filtered = allCards.filter((c) => {
      if (sourceFilter === "video" && c.type !== "video") return false;
      if (sourceFilter === "paper" && c.type !== "paper") return false;
      if (sourceFilter === "news" && c.type !== "news") return false;
      if (credFloor && c.type === "news") return false;
      return true;
    });
    return filtered.map((c, i) => ({ c, s: scoreCard(c), i })).sort((a, b) => b.s - a.s || a.i - b.i).map((x) => x.c);
  }, [allCards, sourceFilter, credFloor, boosted, mutedTopics]);

  const savedCards = allCards.filter((c) => cs(c.id).saved);
  const savedMin = savedCards.reduce((a, c) => a + c.runtime, 0);
  const savedVideoCards = savedCards.filter((c) => c.videoId);          // pushable to YouTube
  const unpushed = savedVideoCards.filter((c) => !pushedIds.has(c.id)); // not in the playlist yet

  /* actions — UI state keyed by external_id (c.id); persistence by feed_items.id (c.dbId) */
  const like = (c: Card) => { const n = !cs(c.id).liked; setCS(c.id, { liked: n }); recordReaction(c.dbId, n ? "up" : "down").catch(() => {}); };
  const watchFull = (c: Card) => { recordReaction(c.dbId, "watch_full").catch(() => {}); window.open(c.source_url, "_blank"); showToast(c.hook ? "Opening at hook · " + c.hook : "Opening source…"); };

  const [pushing, setPushing] = useState(false);
  const [playlistUrl, setPlaylistUrl] = useState<string | null>(null);

  // Push given cards' videos to the Burrfeed Watchlist playlist (API dedupes).
  // Returns null if it can't run (no token / no videos). Marks them pushed on success.
  const pushVideos = async (cards: Card[]): Promise<{ added: number; alreadyThere: number } | null> => {
    const vids = cards.map((c) => c.videoId).filter(Boolean) as string[];
    if (!vids.length || !providerToken) return null;
    const res = await fetch("/api/watchlist/push-youtube", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ providerToken, videoIds: vids }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.error || "push failed");
    const pushedCards = cards.filter((c) => c.videoId);
    setPushedIds((s) => { const n = new Set(s); pushedCards.forEach((c) => n.add(c.id)); return n; });
    markPushed(pushedCards.map((c) => c.dbId)).catch(() => {});
    if (data.url) setPlaylistUrl(data.url);
    return { added: data.added ?? 0, alreadyThere: data.alreadyThere ?? 0 };
  };

  const save = (c: Card) => {
    const n = !cs(c.id).saved;
    setCS(c.id, { saved: n });
    toggleWatchlist(c.dbId, n).catch(() => {});
    if (!n) { showToast("Removed from Watchlist"); return; }
    // saved → auto-sync to YouTube if it's a video and we're connected with a live token
    if (c.videoId && yt && providerToken) {
      showToast("Saved · adding to YouTube…");
      pushVideos([c])
        .then((r) => showToast(r?.added ? "Saved · added to YouTube" : "Saved · already in YouTube"))
        .catch(() => showToast("Saved · couldn’t reach YouTube"));
    } else {
      showToast(c.videoId && yt ? "Saved · reconnect YouTube to sync" : "Saved to Watchlist");
    }
  };

  // Manual catch-up: push everything saved-but-not-yet-in-YouTube.
  const syncYouTube = async () => {
    if (pushing) return;
    if (!providerToken) { signInWithGoogle(); return; } // re-grant scope to get a fresh token
    if (!unpushed.length) return;
    setPushing(true);
    try {
      const r = await pushVideos(unpushed);
      if (r) showToast(r.added ? `Synced ${r.added} to “Burrfeed Watchlist”` : "Already in YouTube");
    } catch (e: any) {
      const msg = String(e?.message || "");
      showToast(msg.includes("token") || msg.includes("401") ? "Reconnect YouTube to sync" : "Sync failed — try again");
    } finally {
      setPushing(false);
    }
  };

  /* tune */
  const [tuning, setTuning] = useState(false);
  const persistTaste = (nb: string[], nm: string[], cf: boolean) =>
    saveProfile({ boosted: nb, muted: nm, novelty_floor: cf ? "expert" : "any" }).catch(() => {});

  // offline fallback: local keyword matcher (also used if the API call fails)
  const applyTuneLocal = (raw: string) => {
    const text = raw.toLowerCase();
    const cues = ["less ", "already know", "i know", "skip ", "mute ", "not ", "no more", "enough ", " less"];
    let cut = text.length; cues.forEach((c) => { const i = text.indexOf(c); if (i >= 0 && i < cut) cut = i; });
    const boostPart = text.slice(0, cut), mutePart = text.slice(cut);
    let nb = [...boosted], nm = [...mutedTopics];
    const newB: string[] = [], newM: string[] = [];
    DICT.forEach((d) => {
      if (d.kw.some((k) => boostPart.includes(k))) { if (!nb.includes(d.chip)) nb.push(d.chip); nm = nm.filter((x) => x !== d.chip); newB.push(d.chip); }
      if (d.kw.some((k) => mutePart.includes(k))) { if (!nm.includes(d.chip)) nm.push(d.chip); nb = nb.filter((x) => x !== d.chip); newM.push(d.chip); }
    });
    const cf = /primary source|expert|credible|only experts/.test(text) ? true : credFloor;
    setBoosted(nb); setMutedTopics(nm); setCredFloor(cf);
    setTuneLog({ boost: newB.length ? newB : nb.slice(0, 3), mute: newM.length ? newM : nm.slice(0, 3) });
    persistTaste(nb, nm, cf);
    pulse();
  };

  const submitTune = async () => {
    const raw = tuneInput.trim(); if (!raw || tuning) return;
    setTuneInput(""); setTuning(true);
    try {
      const res = await fetch("/api/tune-feed", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: raw, boosted, muted: mutedTopics }),
      });
      if (!res.ok) throw new Error("tune api");
      const data = await res.json() as { boost?: string[]; mute?: string[]; credibility_floor?: string };
      let nb = [...boosted], nm = [...mutedTopics];
      (data.boost ?? []).forEach((b) => { if (!nb.includes(b)) nb.push(b); nm = nm.filter((x) => x !== b); });
      (data.mute ?? []).forEach((m) => { if (!nm.includes(m)) nm.push(m); nb = nb.filter((x) => x !== m); });
      let cf = credFloor;
      if (data.credibility_floor === "on") cf = true; else if (data.credibility_floor === "off") cf = false;
      setBoosted(nb); setMutedTopics(nm); setCredFloor(cf);
      setTuneLog({ boost: data.boost?.length ? data.boost! : nb.slice(0, 3), mute: data.mute?.length ? data.mute! : nm.slice(0, 3) });
      persistTaste(nb, nm, cf);
      pulse();
    } catch {
      applyTuneLocal(raw); // graceful offline fallback
    } finally {
      setTuning(false);
    }
  };

  const completeOnboarding = () => { setShowOnboarding(false); setTab("feed"); setBoosted([...obPick]); setMutedTopics([...obKnow]); persistTaste([...obPick], [...obKnow], credFloor); };

  // onboarding agent prompt — map free text to taste chips (falls back to the raw phrase)
  const submitObInput = () => {
    const raw = obInput.trim(); if (!raw) return;
    const text = raw.toLowerCase();
    const matched = DICT.filter((d) => d.kw.some((k) => text.includes(k))).map((d) => d.chip);
    const picks = matched.length ? matched : [raw];
    setObPick((s) => Array.from(new Set([...s, ...picks])));
    setObAdded(picks);
    setObInput("");
  };

  /* feed playback: remember position, advance on explicit action only */
  const scroller = useRef<HTMLDivElement>(null);
  const vids = useRef<Record<string, HTMLVideoElement | null>>({});
  const [activeId, setActiveId] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const [ended, setEnded] = useState(false);
  const [progress, setProgress] = useState(0);   // 0..1 of active video
  const [buffering, setBuffering] = useState(false);
  const [burstKey, setBurstKey] = useState(0);    // double-tap heart
  const activeRef = useRef<string | null>(null);
  activeRef.current = activeId;
  const lastTap = useRef(0);
  const tapTimer = useRef<any>(null);

  // observer: switch the active card ONLY when a different card dominates the viewport
  useEffect(() => {
    const io = new IntersectionObserver((ents) => {
      ents.forEach((e) => {
        if (e.isIntersecting && e.intersectionRatio > 0.6) {
          const id = (e.target as HTMLElement).dataset.cid!;
          if (id !== activeRef.current) setActiveId(id);
        }
      });
    }, { threshold: [0, 0.6, 1], root: scroller.current });
    document.querySelectorAll("[data-cid]").forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [feedCards]);

  // active card changed: pause the rest, clear the end-screen, start the new one (from 0 only if fresh)
  useEffect(() => {
    Object.entries(vids.current).forEach(([id, v]) => { if (v && id !== activeId) v.pause(); });
    setPaused(false); setEnded(false); setProgress(0); setBuffering(false);
    const v = activeId ? vids.current[activeId] : null;
    if (v && tab === "feed" && !showOnboarding) { v.muted = muted; v.playbackRate = speed; v.play().catch(() => {}); }
  }, [activeId]); // eslint-disable-line react-hooks/exhaustive-deps

  // pause when the browser tab/window is hidden; resume on return
  useEffect(() => {
    const onVis = () => {
      const v = activeRef.current ? vids.current[activeRef.current] : null;
      if (!v) return;
      if (document.hidden) v.pause();
      else if (tab === "feed" && !showOnboarding && !paused && !ended) v.play().catch(() => {});
    };
    document.addEventListener("visibilitychange", onVis);
    return () => document.removeEventListener("visibilitychange", onVis);
  }, [tab, showOnboarding, paused, ended]);

  // leaving the feed pauses; returning resumes exactly where you were
  useEffect(() => {
    const v = activeId ? vids.current[activeId] : null;
    if (!v) return;
    if (tab === "feed" && !showOnboarding) { if (!paused && !ended) { v.muted = muted; v.playbackRate = speed; v.play().catch(() => {}); } }
    else v.pause();
  }, [tab, showOnboarding]); // eslint-disable-line react-hooks/exhaustive-deps

  // keep the active video's mute + playback rate in sync with state (rate resets on each media load)
  useEffect(() => { const v = activeId ? vids.current[activeId] : null; if (v) { v.muted = muted; v.playbackRate = speed; } }, [muted, speed, activeId]);

  // restore saved speed + sound preference; once the user has opted into sound, auto-unmute on their first tap each load
  useEffect(() => {
    try {
      const s = parseFloat(localStorage.getItem("bf_speed") || "");
      if (s >= 0.5 && s <= 3) setSpeed(s);
      if (localStorage.getItem("bf_sound") === "on") soundPref.current = true;
    } catch {}
    const onFirst = () => { if (soundPref.current) setMuted(false); };
    window.addEventListener("pointerdown", onFirst, { once: true });
    return () => window.removeEventListener("pointerdown", onFirst);
  }, []);

  const SPEEDS = [1, 1.25, 1.5, 2];
  const cycleSpeed = () => setSpeed((s) => { const next = SPEEDS[(SPEEDS.indexOf(s) + 1) % SPEEDS.length]; try { localStorage.setItem("bf_speed", String(next)); } catch {} return next; });
  const toggleSound = () => setMuted((m) => { const nm = !m; soundPref.current = !nm; try { localStorage.setItem("bf_sound", nm ? "off" : "on"); } catch {} return nm; });

  const tapVideo = (id: string) => {
    if (id !== activeRef.current || ended) return;
    const v = vids.current[id]; if (!v) return;
    if (v.paused) { v.play().catch(() => {}); setPaused(false); } else { v.pause(); setPaused(true); }
  };
  const onMediaTap = (c: Card) => {
    const now = Date.now();
    if (now - lastTap.current < 280) {            // double-tap → like
      clearTimeout(tapTimer.current);
      lastTap.current = 0;
      if (!cs(c.id).liked) like(c);
      setBurstKey((k) => k + 1);
    } else {                                       // single-tap → pause/play (deferred to detect double)
      lastTap.current = now;
      clearTimeout(tapTimer.current);
      tapTimer.current = setTimeout(() => tapVideo(c.id), 280);
    }
  };
  const replay = () => { const v = activeId ? vids.current[activeId] : null; if (!v) return; v.currentTime = 0; setEnded(false); setPaused(false); v.play().catch(() => {}); };
  const nextCard = () => {
    const el = activeId ? (document.querySelector(`[data-cid="${activeId}"]`) as HTMLElement) : null;
    const sib = el?.nextElementSibling as HTMLElement | null;
    if (sib) sib.scrollIntoView({ behavior: "smooth" });
    else scroller.current?.scrollBy({ top: scroller.current.clientHeight, behavior: "smooth" });
  };

  /* ── shared bits ── */
  const credToggle = (
    <button onClick={() => { const v = !credFloor; setCredFloor(v); persistTaste(boosted, mutedTopics, v); pulse(); }} style={{ position: "relative", width: 44, height: 25, borderRadius: 999, border: "none", cursor: "pointer", background: credFloor ? ACCENT : "oklch(0.5 0.02 120 / 0.22)", transition: "background .2s", flex: "0 0 auto" }}>
      <span style={{ position: "absolute", top: 3, left: credFloor ? 22 : 3, width: 19, height: 19, borderRadius: "50%", background: "oklch(1 0 0)", transition: "left .2s", boxShadow: "0 1px 3px oklch(0 0 0 / 0.25)" }} />
    </button>
  );

  /* ── FEED ── */
  const renderFeed = () => (
    <div style={{ position: "absolute", inset: 0, background: PAPER }}>
      {/* fixed header — light, blurred */}
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, zIndex: 25, padding: "16px 16px 12px", background: "oklch(1 0 0 / 0.72)", backdropFilter: "blur(14px)", borderBottom: `1px solid ${LINE2}` }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <img src="/burrfeed-mark.svg" alt="" width={22} height={22} style={{ display: "block" }} />
            <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.02em", color: TXT }}>Burrfeed</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button onClick={() => setTab("tune")} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 11px", borderRadius: 999, background: ACCENT_SOFT, border: `1px solid ${ACCENT_LINE}`, color: ACCENT, fontSize: 12, fontWeight: 600, fontFamily: "inherit", cursor: "pointer" }}>
              {ms("auto_awesome", { fontSize: 15, fontVariationSettings: "'FILL' 1" })}Tuned for you
            </button>
            {user ? (
              <button onClick={() => setTab("you")} title="Account" style={{ width: 32, height: 32, borderRadius: "50%", flex: "0 0 auto", border: "1px solid " + ACCENT_LINE, background: `linear-gradient(135deg, ${ACCENT}, oklch(0.32 0.05 218))`, color: ON_ACCENT, fontSize: 13, fontWeight: 700, fontFamily: "inherit", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>{(user.email?.[0] || "•").toUpperCase()}</button>
            ) : (
              <button onClick={() => signInWithGoogle()} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 999, background: ACCENT, border: "none", color: ON_ACCENT, fontSize: 12.5, fontWeight: 700, fontFamily: "inherit", cursor: "pointer", boxShadow: "0 4px 14px oklch(0.42 0.04 218 / 0.3)" }}>
                {ms("login", { fontSize: 15 })}Sign in
              </button>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 7, marginTop: 12 }}>
          {(["all", "video", "paper", "news"] as const).map((f) => {
            const on = sourceFilter === f, lbl = { all: "All", video: "Video", paper: "Papers", news: "News" }[f];
            return <button key={f} onClick={() => setSourceFilter(f)} style={{ padding: "7px 14px", borderRadius: 999, fontSize: 12.5, fontWeight: on ? 700 : 500, fontFamily: "inherit", cursor: "pointer", background: on ? ACCENT : SURFACE2, color: on ? ON_ACCENT : DIM, border: `1px solid ${on ? ACCENT : HAIR}`, transition: "all .15s" }}>{lbl}</button>;
          })}
        </div>
      </div>
      {feedUpdated && (
        <div style={{ position: "absolute", top: 104, left: "50%", zIndex: 34, display: "flex", alignItems: "center", gap: 7, padding: "9px 15px", borderRadius: 999, background: ACCENT, color: ON_ACCENT, fontWeight: 700, fontSize: 13, boxShadow: "0 12px 30px oklch(0.42 0.04 85 / 0.25)", animation: "slideDown .3s ease", transform: "translateX(-50%)" }}>
          {ms("auto_awesome", { fontSize: 17, fontVariationSettings: "'FILL' 1" })}Feed updated
        </div>
      )}
      <div ref={scroller} style={{ position: "absolute", inset: 0, overflowY: "auto", scrollSnapType: "y mandatory" }}>
        {loading && (
          <div style={{ height: "100%", scrollSnapAlign: "start", display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 24px", gap: 14, background: PAPER }}>
            <div style={{ width: "100%", height: "42%", borderRadius: 18, background: `linear-gradient(90deg,${SURFACE2},oklch(0.99 0.004 85),${SURFACE2})`, backgroundSize: "340px 100%", animation: "shimmer 1.3s linear infinite" }} />
            {["50%", "92%", "80%"].map((w, i) => <div key={i} style={{ width: w, height: i === 0 ? 14 : 28, borderRadius: 7, background: `linear-gradient(90deg,${SURFACE2},oklch(0.99 0.004 85),${SURFACE2})`, backgroundSize: "340px 100%", animation: "shimmer 1.3s linear infinite", marginTop: i === 0 ? 6 : 0 }} />)}
          </div>
        )}
        {!loading && feedCards.map((c) => {
          const st = cs(c.id), liked = !!st.liked, saved = !!st.saved;
          const likes = fmtK(likeBase(c.id) + (liked ? 1 : 0));
          const isVid = c.type === "video";
          return (
            <section key={c.id} data-cid={c.id} style={{ position: "relative", height: "100%", width: "100%", flex: "0 0 100%", scrollSnapAlign: "start", scrollSnapStop: "always", overflow: "hidden", display: "flex", flexDirection: "column", paddingTop: 106, background: PAPER, boxSizing: "border-box" }}>
              {/* ── POSTER ── */}
              <div style={{ position: "relative", flex: "0 0 42%", margin: "0 12px", borderRadius: 18, overflow: "hidden", background: isVid ? "oklch(0.12 0.01 230)" : "oklch(0.93 0.02 218)" }}>
                {isVid ? (
                  <div onClick={() => onMediaTap(c)} style={{ position: "absolute", inset: 0, cursor: "pointer" }}>
                    {c.teaser_url ? (
                      <video ref={(el) => { vids.current[c.id] = el; }} src={c.teaser_url} poster={c.thumb_url || undefined} muted={muted} playsInline preload="metadata"
                        onEnded={() => { if (c.id === activeRef.current) setEnded(true); }}
                        onTimeUpdate={(e) => { if (c.id === activeRef.current) { const v = e.currentTarget; setProgress(v.duration ? v.currentTime / v.duration : 0); } }}
                        onWaiting={() => { if (c.id === activeRef.current) setBuffering(true); }}
                        onPlaying={() => { if (c.id === activeRef.current) setBuffering(false); }}
                        onCanPlay={() => { if (c.id === activeRef.current) setBuffering(false); }}
                        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }} />
                    ) : <div style={{ position: "absolute", inset: 0, background: "linear-gradient(158deg, oklch(0.4 0.06 218), oklch(0.28 0.04 230))" }} />}
                  </div>
                ) : (
                  <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 4, padding: "0 40px", textAlign: "center" }}>
                    <div className="serif" style={{ fontSize: 52, fontWeight: 500, letterSpacing: "-0.03em", lineHeight: 0.95, color: ACCENT }}>{c.pullStat}</div>
                    <div style={{ fontSize: 13, color: DIM, maxWidth: 220 }}>{c.pullLabel}</div>
                  </div>
                )}
                {/* teaser eq chip (top-left) */}
                <div style={{ position: "absolute", top: 12, left: 12, display: "flex", alignItems: "center", gap: 7, padding: "5px 11px 5px 9px", borderRadius: 999, background: "oklch(1 0 0 / 0.82)", backdropFilter: "blur(7px)", border: `1px solid ${HAIR}` }}>
                  <div style={{ display: "flex", gap: 2.5, alignItems: "flex-end", height: 11 }}>
                    {[[0.9, 0, "40%"], [1.1, 0.15, "95%"], [0.8, 0.3, "60%"]].map((b, i) => <div key={i} style={{ width: 2.5, background: ACCENT, borderRadius: 2, height: b[2] as string, animation: `eq ${b[0]}s ease-in-out infinite`, animationDelay: `${b[1]}s` }} />)}
                  </div>
                  <span style={{ fontFamily: "'JetBrains Mono'", fontSize: 9.5, letterSpacing: "0.08em", color: DIM, textTransform: "uppercase" }}>{isVid ? `AI teaser${c.hook ? " · " + c.hook : ""}` : (c.type === "paper" ? "Paper" : "News")}</span>
                </div>
                {/* sound + speed (top-right) — video only */}
                {isVid && (
                  <div style={{ position: "absolute", top: 12, right: 12, display: "flex", alignItems: "center", gap: 7 }}>
                    <button onClick={(e) => { e.stopPropagation(); cycleSpeed(); }} title="Speed" style={{ height: 36, padding: "0 10px", borderRadius: 999, border: `1px solid ${HAIR}`, background: "oklch(1 0 0 / 0.82)", backdropFilter: "blur(7px)", cursor: "pointer", display: "flex", alignItems: "center", gap: 4, fontFamily: "inherit", fontWeight: 700, fontSize: 12.5, color: speed !== 1 ? ACCENT : TXT }}>{ms("speed", { fontSize: 16 })}{speed}×</button>
                    <button onClick={(e) => { e.stopPropagation(); toggleSound(); }} title="Sound" style={{ width: 36, height: 36, borderRadius: "50%", border: `1px solid ${HAIR}`, background: "oklch(1 0 0 / 0.82)", backdropFilter: "blur(7px)", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}>{ms(muted ? "volume_off" : "volume_up", { fontSize: 19, color: muted ? TXT : ACCENT })}</button>
                  </div>
                )}
                {/* poster overlays (scoped to poster) */}
                {c.id === activeId && paused && !ended && isVid && (
                  <div onClick={() => tapVideo(c.id)} style={{ position: "absolute", inset: 0, zIndex: 6, display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <span style={{ width: 64, height: 64, borderRadius: "50%", background: "oklch(0.1 0.01 50 / 0.5)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", border: "1px solid oklch(1 0 0 / 0.25)" }}>{ms("play_arrow", { fontSize: 36, color: "oklch(0.99 0 0)", fontVariationSettings: "'FILL' 1" })}</span>
                  </div>
                )}
                {c.id === activeId && buffering && !ended && !paused && isVid && (
                  <div style={{ position: "absolute", inset: 0, zIndex: 5, display: "flex", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
                    <span style={{ width: 40, height: 40, borderRadius: "50%", border: "3px solid oklch(1 0 0 / 0.3)", borderTopColor: "oklch(0.99 0 0)", animation: "spin 0.8s linear infinite" }} />
                  </div>
                )}
                {c.id === activeId && burstKey > 0 && isVid && (
                  <span key={burstKey} className="ms" style={{ position: "absolute", top: "50%", left: "50%", zIndex: 11, fontSize: 88, color: "oklch(0.99 0 0)", fontVariationSettings: "'FILL' 1", pointerEvents: "none", animation: "heartburst .7s ease-out forwards", filter: "drop-shadow(0 4px 16px oklch(0 0 0 / 0.5))" }}>favorite</span>
                )}
                {c.id === activeId && ended && isVid && (
                  <div style={{ position: "absolute", inset: 0, zIndex: 12, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, padding: "0 20px", textAlign: "center", background: "oklch(0.1 0.01 50 / 0.62)", backdropFilter: "blur(3px)" }}>
                    <div style={{ fontFamily: "'JetBrains Mono'", fontSize: 10.5, letterSpacing: "0.12em", textTransform: "uppercase", color: "oklch(0.92 0 0 / 0.9)" }}>Teaser complete</div>
                    <div style={{ display: "flex", gap: 10 }}>
                      <button onClick={replay} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "10px 16px", borderRadius: 12, border: "1px solid oklch(1 0 0 / 0.25)", background: "oklch(1 0 0 / 0.12)", color: "oklch(0.99 0 0)", fontWeight: 700, fontSize: 13.5, fontFamily: "inherit", cursor: "pointer", backdropFilter: "blur(6px)" }}>{ms("replay", { fontSize: 18 })}Replay</button>
                      <button onClick={() => watchFull(c)} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "10px 16px", borderRadius: 12, border: "none", background: ACCENT, color: ON_ACCENT, fontWeight: 800, fontSize: 13.5, fontFamily: "inherit", cursor: "pointer" }}>{ms("play_circle", { fontSize: 18, fontVariationSettings: "'FILL' 1" })}Watch full</button>
                    </div>
                  </div>
                )}
                {/* progress bar on poster bottom edge */}
                {isVid && (
                  <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 3, background: "oklch(0 0 0 / 0.22)", zIndex: 7 }}>
                    <div style={{ height: "100%", background: ACCENT, width: `${Math.round((c.id === activeId ? progress : 0) * 100)}%`, transition: "width .15s linear" }} />
                  </div>
                )}
              </div>

              {/* ── CONTENT ── */}
              <div style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", padding: "16px 20px 80px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "'JetBrains Mono'", fontSize: 10.5, letterSpacing: "0.03em", color: MUTE, textTransform: "uppercase" }}>
                  <span style={{ color: ACCENT, fontWeight: 600 }}>{c.topic}</span>
                  <span style={{ width: 3, height: 3, borderRadius: "50%", background: MUTE, flex: "0 0 auto" }} />
                  {c.runtime > 0 && <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>{ms("schedule", { fontSize: 13 })}{c.runtime}{c.read ? " min read" : " min"}</span>}
                </div>
                <div className="serif" style={{ fontSize: 21, fontWeight: 400, lineHeight: 1.22, letterSpacing: "-0.015em", color: TXT, marginTop: 10, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{c.title}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 15 }}>
                  <div style={{ width: 34, height: 34, borderRadius: "50%", flex: "0 0 auto", background: `linear-gradient(135deg, ${ACCENT}, oklch(0.3 0.05 230))`, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 12, color: ON_ACCENT }}>{initials(c.speaker)}</div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, minWidth: 0 }}>
                      <span style={{ fontWeight: 700, fontSize: 14, color: TXT, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.speaker}</span>
                      {ms("verified", { fontSize: 15, color: ACCENT, fontVariationSettings: "'FILL' 1", flex: "0 0 auto" })}
                    </div>
                    <div style={{ fontSize: 11.5, color: MUTE, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.badge || c.affiliation}</div>
                  </div>
                </div>
                {/* inline actions */}
                <div style={{ display: "flex", alignItems: "center", gap: 9, marginTop: "auto" }}>
                  <button onClick={() => save(c)} style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7, padding: 13, borderRadius: 13, cursor: "pointer", fontFamily: "inherit", fontWeight: 700, fontSize: 14, background: saved ? ACCENT : SURFACE2, color: saved ? ON_ACCENT : TXT, border: `1px solid ${saved ? ACCENT : HAIR}` }}>
                    {ms(saved ? "bookmark_added" : "bookmark", { fontSize: 19, fontVariationSettings: saved ? "'FILL' 1" : "'FILL' 0" })}{saved ? "Saved" : "Save"}
                  </button>
                  <button onClick={() => like(c)} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "0 14px", height: 46, borderRadius: 13, cursor: "pointer", fontFamily: "inherit", fontWeight: 600, fontSize: 13, background: SURFACE2, border: `1px solid ${HAIR}`, color: TXT }}>
                    {ms("favorite", { fontSize: 19, color: liked ? ACCENT : MUTE, fontVariationSettings: liked ? "'FILL' 1" : "'FILL' 0" })}{likes}
                  </button>
                  <button onClick={() => watchFull(c)} title="Watch full" style={{ width: 46, height: 46, borderRadius: 13, cursor: "pointer", background: SURFACE2, border: `1px solid ${HAIR}`, display: "flex", alignItems: "center", justifyContent: "center" }}>{ms("play_circle", { fontSize: 19, color: TXT, fontVariationSettings: "'FILL' 1" })}</button>
                  <button onClick={() => showToast("Link copied")} title="Share" style={{ width: 46, height: 46, borderRadius: 13, cursor: "pointer", background: SURFACE2, border: `1px solid ${HAIR}`, display: "flex", alignItems: "center", justifyContent: "center" }}>{ms("ios_share", { fontSize: 19, color: TXT })}</button>
                </div>
              </div>
            </section>
          );
        })}
        {!loading && feedCards.length > 0 && (
          <section style={{ position: "relative", height: "100%", width: "100%", flex: "0 0 100%", scrollSnapAlign: "start", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 15, padding: "0 40px", textAlign: "center", background: PAPER }}>
            {ms("task_alt", { fontSize: 46, color: ACCENT, fontVariationSettings: "'FILL' 1" })}
            <div className="serif" style={{ fontSize: 29, fontWeight: 400, letterSpacing: "-0.022em", color: TXT }}>You&rsquo;re all caught up</div>
            <div style={{ fontSize: 14, color: DIM, maxWidth: 280 }}>That&rsquo;s every fresh teaser matching your taste. Tune the feed to surface more.</div>
            <div style={{ display: "flex", gap: 10, marginTop: 6 }}>
              <button onClick={() => setTab("tune")} style={primaryBtn}>Tune your feed</button>
              <button onClick={() => scroller.current?.scrollTo({ top: 0, behavior: "smooth" })} style={ghostBtn}>Back to top</button>
            </div>
          </section>
        )}
        {!loading && feedCards.length === 0 && (
          <section style={{ position: "relative", height: "100%", width: "100%", flex: "0 0 100%", scrollSnapAlign: "start", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, padding: "0 40px", textAlign: "center", background: PAPER }}>
            {ms("filter_alt_off", { fontSize: 44, color: MUTE })}
            <div className="serif" style={{ fontSize: 24, fontWeight: 500, letterSpacing: "-0.015em", color: TXT }}>No teasers match those filters</div>
            <div style={{ fontSize: 14, color: DIM, maxWidth: 280 }}>Loosen your filters or tuning to see more.</div>
            <button onClick={() => setTab("tune")} style={{ ...primaryBtn, marginTop: 6 }}>Adjust in Tune</button>
          </section>
        )}
      </div>
    </div>
  );

  /* ── TUNE ── */
  const renderTune = () => (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", background: PAPER }}>
      <div style={{ padding: "54px 20px 20px", borderBottom: `1px solid ${HAIR}` }}>
        <div style={{ fontFamily: "'JetBrains Mono'", fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase", color: ACCENT, display: "flex", alignItems: "center", gap: 7 }}>{ms("auto_awesome", { fontSize: 16, fontVariationSettings: "'FILL' 1" })}Your taste</div>
        <div className="serif" style={{ fontSize: 29, fontWeight: 400, letterSpacing: "-0.022em", marginTop: 8, color: TXT }}>Curated for you</div>
        <div style={{ fontSize: 14, lineHeight: 1.5, color: DIM, marginTop: 9 }}>You&rsquo;re a <b style={{ color: TXT }}>Principal PM on AWS Aurora</b> chasing the cutting edge of databases for agentic AI — not the 101s. Every teaser is screened against the taste below. Retune anytime — just talk.</div>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "18px 20px 200px" }}>
        {tuneLog && (
          <div style={{ padding: "14px 15px", borderRadius: 15, background: ACCENT_SOFT, border: `1px solid ${ACCENT_LINE}`, marginBottom: 22, animation: "floatIn .3s ease" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7, fontWeight: 700, fontSize: 13.5, color: ACCENT }}>{ms("auto_awesome", { fontSize: 18, fontVariationSettings: "'FILL' 1" })}Adjusted your feed</div>
            <div style={{ fontSize: 13, color: DIM, marginTop: 8 }}><b style={{ color: ACCENT }}>Boosting:</b> {tuneLog.boost.join(", ") || "—"}</div>
            <div style={{ fontSize: 13, color: DIM, marginTop: 3 }}><b style={{ color: TXT }}>Muting:</b> {tuneLog.mute.join(", ") || "—"}</div>
            <button onClick={() => setTab("feed")} style={{ marginTop: 11, display: "inline-flex", alignItems: "center", gap: 6, padding: "8px 13px", borderRadius: 10, border: "none", background: ACCENT, color: ON_ACCENT, fontWeight: 700, fontSize: 12.5, fontFamily: "inherit", cursor: "pointer" }}>View feed{ms("arrow_forward", { fontSize: 16 })}</button>
          </div>
        )}
        <SectionLabel>Screening for {boosted.length} topics</SectionLabel>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 11 }}>
          {boosted.length === 0 && <div style={{ fontSize: 13, color: MUTE }}>Nothing boosted yet — try the prompt below.</div>}
          {boosted.map((b) => (
            <div key={b} style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "8px 9px 8px 13px", borderRadius: 999, background: ACCENT_SOFT, border: `1px solid ${ACCENT_LINE}` }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: ACCENT }}>{b}</span>
              <button onClick={() => { const nb = boosted.filter((x) => x !== b); setBoosted(nb); persistTaste(nb, mutedTopics, credFloor); pulse(); }} style={iconBtn}>{ms("close", { fontSize: 17, color: ACCENT })}</button>
            </div>
          ))}
        </div>
        <SectionLabel style={{ marginTop: 26 }}>Skipping the basics on</SectionLabel>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 11 }}>
          {mutedTopics.length === 0 && <div style={{ fontSize: 13, color: MUTE }}>Nothing muted.</div>}
          {mutedTopics.map((m) => (
            <div key={m} style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "8px 9px 8px 13px", borderRadius: 999, background: SURFACE2, border: `1px solid ${HAIR}` }}>
              <span style={{ fontSize: 13, fontWeight: 500, color: MUTE, textDecoration: "line-through" }}>{m}</span>
              <button onClick={() => { const nm = mutedTopics.filter((x) => x !== m); setMutedTopics(nm); persistTaste(boosted, nm, credFloor); pulse(); }} style={iconBtn}>{ms("close", { fontSize: 17, color: MUTE })}</button>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 26, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, padding: 15, borderRadius: 15, background: CARDBG, border: `1px solid ${HAIR}` }}>
          <div>
            <div style={{ fontSize: 14.5, fontWeight: 700, color: TXT }}>Credibility floor</div>
            <div style={{ fontSize: 12.5, color: MUTE, marginTop: 2 }}>Only experts &amp; primary sources</div>
          </div>
          {credToggle}
        </div>
        <SectionLabel style={{ marginTop: 26 }}>Try saying</SectionLabel>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 11 }}>
          {EXAMPLES.map((t) => <button key={t} onClick={() => setTuneInput(t)} style={{ textAlign: "left", padding: "11px 14px", borderRadius: 12, background: CARDBG, border: `1px solid ${HAIR}`, color: DIM, fontSize: 13, fontFamily: "inherit", cursor: "pointer", lineHeight: 1.4 }}>&ldquo;{t}&rdquo;</button>)}
        </div>
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 66, padding: "14px 16px 16px", background: `linear-gradient(transparent, ${PAPER} 42%)` }}>
        <div style={{ borderRadius: 20, background: CARDBG, border: `1px solid ${ACCENT_LINE}`, padding: "12px 12px 13px", boxShadow: "0 -6px 24px oklch(0.45 0.03 90 / 0.1)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "1px 3px 11px" }}>{ms("graphic_eq", { fontSize: 18, color: ACCENT, fontVariationSettings: "'FILL' 1" })}<span style={{ fontSize: 13, fontWeight: 700, color: ACCENT }}>Just tell me — the feed retunes instantly</span></div>
          <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "7px 7px 7px 16px", borderRadius: 14, background: SURFACE2, border: `1px solid ${HAIR}` }}>
            <input value={tuneInput} onChange={(e) => setTuneInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submitTune(); } }} placeholder="“more agent memory, less RAG basics…”" style={{ flex: 1, minWidth: 0, background: "none", border: "none", outline: "none", color: TXT, fontSize: 14, fontFamily: "inherit" }} />
            <button onClick={submitTune} style={{ width: 40, height: 40, borderRadius: 12, border: "none", background: ACCENT, color: ON_ACCENT, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto", boxShadow: "0 4px 14px oklch(0.42 0.04 85 / 0.3)" }}>{ms("arrow_upward", { fontSize: 21, fontVariationSettings: "'FILL' 1" })}</button>
          </div>
        </div>
      </div>
    </div>
  );

  /* ── WATCHLIST ── */
  const renderSaved = () => (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", background: PAPER }}>
      <div style={{ padding: "54px 20px 16px" }}>
        <div className="serif" style={{ fontSize: 29, fontWeight: 400, letterSpacing: "-0.022em", color: TXT }}>Watchlist</div>
        {savedCards.length > 0 && <div style={{ fontSize: 13.5, color: MUTE, marginTop: 3 }}>{savedCards.length} saved · {fmtTotal(savedMin)} to watch</div>}
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "4px 20px 90px" }}>
        {savedCards.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, padding: "70px 30px", textAlign: "center" }}>
            {ms("bookmark_border", { fontSize: 44, color: MUTE })}
            <div className="serif" style={{ fontSize: 21, fontWeight: 500, color: TXT }}>Nothing saved yet</div>
            <div style={{ fontSize: 13.5, color: DIM, maxWidth: 250, lineHeight: 1.5 }}>Tap <b style={{ color: ACCENT }}>Save</b> on anything worth your 30 minutes.</div>
            <button onClick={() => setTab("feed")} style={{ ...primaryBtn, marginTop: 4 }}>Go to feed</button>
          </div>
        ) : (
          <>
            <div style={{ padding: 15, borderRadius: 16, background: CARDBG, border: `1px solid ${HAIR}`, marginBottom: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: yt ? 12 : 4 }}>
                {ms("smart_display", { fontSize: 24, color: yt ? DANGER : MUTE, fontVariationSettings: "'FILL' 1" })}
                <div style={{ fontSize: 13.5, color: TXT }}>{yt ? <><b>YouTube connected</b><span style={{ color: MUTE }}> · burrfeed@aws</span></> : <b style={{ fontWeight: 700 }}>YouTube not connected</b>}</div>
              </div>
              {yt ? (
                savedVideoCards.length === 0 ? (
                  <div style={{ fontSize: 12.5, color: MUTE, lineHeight: 1.45 }}>Save a video and it auto-syncs to your <b>&ldquo;Burrfeed Watchlist&rdquo;</b> playlist.</div>
                ) : unpushed.length === 0 ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "12px 14px", borderRadius: 12, background: "oklch(0.5 0.09 168 / 0.12)", border: "1px solid oklch(0.5 0.09 168 / 0.3)" }}>
                    {ms("check_circle", { fontSize: 21, color: POS, fontVariationSettings: "'FILL' 1" })}
                    <div style={{ fontSize: 13, color: POS, flex: 1 }}>All {savedVideoCards.length} synced to <b>&ldquo;Burrfeed Watchlist&rdquo;</b></div>
                    {playlistUrl && <a href={playlistUrl} target="_blank" rel="noreferrer" style={{ fontSize: 12.5, fontWeight: 700, color: POS, textDecoration: "none", whiteSpace: "nowrap" }}>View →</a>}
                  </div>
                ) : (
                  <button onClick={syncYouTube} disabled={pushing} style={{ width: "100%", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, padding: 13, borderRadius: 13, border: "none", background: ACCENT, color: ON_ACCENT, fontWeight: 700, fontSize: 14, fontFamily: "inherit", cursor: pushing ? "default" : "pointer", opacity: pushing ? 0.7 : 1 }}>{ms("playlist_add", { fontSize: 19 })}{pushing ? "Syncing…" : `Sync ${unpushed.length} to YouTube`}</button>
                )
              ) : (
                <>
                  <div style={{ fontSize: 12.5, color: MUTE, marginBottom: 12, lineHeight: 1.45 }}>Connect to push saves into a &ldquo;Burrfeed Watchlist&rdquo; playlist.</div>
                  <div style={{ display: "flex", gap: 9 }}>
                    <button onClick={() => signInWithGoogle()} style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7, padding: 12, borderRadius: 12, border: "none", background: ACCENT, color: ON_ACCENT, fontWeight: 700, fontSize: 13.5, fontFamily: "inherit", cursor: "pointer" }}>{ms("link", { fontSize: 18 })}Connect</button>
                    <button onClick={() => showToast("Links copied to clipboard")} style={{ padding: "12px 15px", borderRadius: 12, border: `1px solid ${HAIR}`, background: SURFACE2, color: TXT, fontWeight: 600, fontSize: 13.5, fontFamily: "inherit", cursor: "pointer" }}>Copy links</button>
                  </div>
                </>
              )}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 14 }}>
              {savedCards.map((c) => {
                const watched = !!cs(c.id).watched;
                return (
                  <div key={c.id} style={{ display: "flex", gap: 12, padding: 12, borderRadius: 15, background: CARDBG, border: `1px solid ${HAIR}` }}>
                    <div style={{ width: 54, height: 72, borderRadius: 10, flex: "0 0 auto", background: "linear-gradient(150deg, oklch(0.5 0.06 218), oklch(0.34 0.05 230))", display: "flex", alignItems: "center", justifyContent: "center", border: `1px solid ${HAIR}`, overflow: "hidden" }}>
                      {c.thumb_url ? <img src={c.thumb_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : ms(c.type === "video" ? "play_arrow" : c.type === "paper" ? "description" : "newspaper", { fontSize: 24, color: ON_ACCENT, fontVariationSettings: "'FILL' 1" })}
                    </div>
                    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 3 }}>
                      <div style={{ fontSize: 14, fontWeight: 700, lineHeight: 1.25, color: watched ? MUTE : TXT, textDecoration: watched ? "line-through" : "none" }}>{c.title}</div>
                      <div style={{ fontSize: 12, color: MUTE }}>{c.speaker} · {c.affiliation}</div>
                      <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11.5, color: MUTE, fontFamily: "'JetBrains Mono'" }}>{ms("schedule", { fontSize: 13 })}{c.runtime} min<span>· {c.source}</span></div>
                      <div style={{ fontSize: 12, color: DIM, marginTop: 2, fontStyle: "italic" }}>&ldquo;{c.whySaved}&rdquo;</div>
                      <div style={{ display: "flex", gap: 8, marginTop: 7 }}>
                        <button onClick={() => { const w = !watched; setCS(c.id, { watched: w }); setWatched(c.dbId, w).catch(() => {}); }} style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: 9, border: `1px solid ${HAIR}`, background: SURFACE2, color: watched ? POS : MUTE, fontWeight: 600, fontSize: 12, fontFamily: "inherit", cursor: "pointer" }}>{ms(watched ? "check_circle" : "radio_button_unchecked", { fontSize: 15, fontVariationSettings: "'FILL' 1" })}Watched</button>
                        <button onClick={() => { setCS(c.id, { saved: false }); toggleWatchlist(c.dbId, false).catch(() => {}); }} style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: 9, border: `1px solid ${HAIR}`, background: SURFACE2, color: MUTE, fontWeight: 600, fontSize: 12, fontFamily: "inherit", cursor: "pointer" }}>{ms("delete", { fontSize: 15 })}Remove</button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );

  /* ── YOU ── */
  const renderYou = () => (
    <div style={{ position: "absolute", inset: 0, overflowY: "auto", padding: "54px 20px 90px", background: PAPER }}>
      <div className="serif" style={{ fontSize: 29, fontWeight: 400, letterSpacing: "-0.022em", color: TXT }}>You</div>
      <div style={{ display: "flex", alignItems: "center", gap: 13, marginTop: 18, padding: 16, borderRadius: 16, background: CARDBG, border: `1px solid ${HAIR}` }}>
        <div style={{ width: 52, height: 52, borderRadius: "50%", background: `linear-gradient(135deg, ${ACCENT}, oklch(0.3 0.05 230))`, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 18, color: ON_ACCENT }}>PM</div>
        <div><div style={{ fontSize: 16, fontWeight: 700, color: TXT }}>Principal PM · Aurora</div><div style={{ fontSize: 12.5, color: MUTE, marginTop: 2 }}>AWS · databases &amp; agentic AI</div></div>
      </div>
      <div style={{ marginTop: 14, padding: 16, borderRadius: 16, background: CARDBG, border: `1px solid ${HAIR}`, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          {ms("smart_display", { fontSize: 26, color: yt ? DANGER : MUTE, fontVariationSettings: "'FILL' 1" })}
          <div><div style={{ fontSize: 14.5, fontWeight: 700, color: TXT }}>YouTube</div><div style={{ fontSize: 12.5, color: yt ? POS : MUTE, marginTop: 2 }}>{yt ? "Connected · burrfeed@aws" : "Not connected"}</div></div>
        </div>
        <button onClick={() => (yt ? signOut() : signInWithGoogle())} style={yt ? { padding: "9px 14px", borderRadius: 11, border: `1px solid ${HAIR}`, background: SURFACE2, color: MUTE, fontWeight: 600, fontSize: 13, fontFamily: "inherit", cursor: "pointer" } : { padding: "9px 14px", borderRadius: 11, border: `1px solid ${ACCENT_LINE}`, background: ACCENT_SOFT, color: ACCENT, fontWeight: 700, fontSize: 13, fontFamily: "inherit", cursor: "pointer" }}>{yt ? "Disconnect" : "Connect"}</button>
      </div>
      <div style={{ marginTop: 14, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, padding: 16, borderRadius: 16, background: CARDBG, border: `1px solid ${HAIR}` }}>
        <div><div style={{ fontSize: 14.5, fontWeight: 700, color: TXT }}>Credibility floor</div><div style={{ fontSize: 12.5, color: MUTE, marginTop: 2 }}>Only experts &amp; primary sources</div></div>
        {credToggle}
      </div>
      <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
        <div style={{ flex: 1, padding: 16, borderRadius: 15, background: CARDBG, border: `1px solid ${HAIR}`, textAlign: "center" }}><div className="serif" style={{ fontSize: 30, fontWeight: 500, color: ACCENT }}>{savedCards.length}</div><div style={{ fontSize: 11.5, color: MUTE, marginTop: 2 }}>Saved</div></div>
        <div style={{ flex: 1, padding: 16, borderRadius: 15, background: CARDBG, border: `1px solid ${HAIR}`, textAlign: "center" }}><div className="serif" style={{ fontSize: 30, fontWeight: 500, color: TXT }}>{fmtTotal(savedMin)}</div><div style={{ fontSize: 11.5, color: MUTE, marginTop: 2 }}>To watch</div></div>
      </div>
      <button onClick={() => setShowOnboarding(true)} style={{ width: "100%", marginTop: 14, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, padding: 14, borderRadius: 14, border: `1px solid ${HAIR}`, background: CARDBG, color: TXT, fontWeight: 600, fontSize: 14, fontFamily: "inherit", cursor: "pointer" }}>{ms("restart_alt", { fontSize: 19 })}Redo taste setup</button>
      <div style={{ textAlign: "center", fontSize: 11.5, color: MUTE, marginTop: 20, fontFamily: "'JetBrains Mono'" }}>Burrfeed · teaser-feed</div>
    </div>
  );

  /* ── ONBOARDING ── */
  const renderOnboarding = () => (
    <>
      <div style={{ position: "absolute", inset: 0, overflowY: "auto", padding: "56px 24px 124px", background: PAPER }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 34 }}><img src="/burrfeed-mark.svg" alt="" width={26} height={26} style={{ display: "block" }} /><span style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.02em", color: TXT }}>Burrfeed</span></div>
        <div className="serif" style={{ fontSize: 44, fontWeight: 400, lineHeight: 1.04, letterSpacing: "-0.025em", maxWidth: 340, color: TXT }}>Decide what&rsquo;s <span style={{ fontStyle: "italic" }}>worth</span> your 30 minutes.</div>
        <div style={{ fontSize: 15.5, lineHeight: 1.55, color: DIM, marginTop: 18, maxWidth: 320 }}>A 45-second AI teaser stacks the most novel points — you save what earns the watch.</div>
        {/* PRIMARY: talk to the agent */}
        <div style={{ marginTop: 30, borderRadius: 20, background: CARDBG, border: `1px solid ${ACCENT_LINE}`, padding: "15px 15px 16px", boxShadow: "0 10px 30px oklch(0.45 0.03 90 / 0.1)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "1px 2px 12px" }}>{ms("graphic_eq", { fontSize: 19, color: ACCENT, fontVariationSettings: "'FILL' 1" })}<span style={{ fontSize: 14, fontWeight: 700, color: ACCENT }}>Tell me what you want to see</span></div>
          <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "7px 7px 7px 15px", borderRadius: 14, background: SURFACE2, border: `1px solid ${HAIR}` }}>
            <input value={obInput} onChange={(e) => setObInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submitObInput(); } }} placeholder="cutting-edge agent memory, skip the 101s" style={{ flex: 1, minWidth: 0, background: "none", border: "none", outline: "none", color: TXT, fontSize: 13.5, fontFamily: "inherit" }} />
            <button onClick={submitObInput} style={{ width: 40, height: 40, borderRadius: 12, border: "none", background: ACCENT, color: ON_ACCENT, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto", boxShadow: "0 4px 14px oklch(0.42 0.04 85 / 0.3)" }}>{ms("arrow_upward", { fontSize: 21, fontVariationSettings: "'FILL' 1" })}</button>
          </div>
          {obAdded.length > 0 && (
            <div style={{ display: "flex", alignItems: "flex-start", gap: 6, marginTop: 12, padding: "0 2px", fontSize: 12.5, lineHeight: 1.45, color: ACCENT }}>
              {ms("check_circle", { fontSize: 16, color: ACCENT, fontVariationSettings: "'FILL' 1", flex: "0 0 auto" })}
              <span><b>Added:</b> {obAdded.join(", ")}</span>
            </div>
          )}
        </div>
        {/* tap a few to get started */}
        <div style={{ marginTop: 28 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: TXT }}>Or tap a few to start</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 13 }}>
            {SUGGEST_BOOST.map((c) => { const on = obPick.includes(c); return (
              <button key={c} onClick={() => setObPick((s) => on ? s.filter((x) => x !== c) : [...s, c])} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "9px 13px", borderRadius: 999, fontSize: 13, fontWeight: 600, fontFamily: "inherit", cursor: "pointer", background: on ? ACCENT_SOFT : SURFACE2, color: on ? ACCENT : DIM, border: `1px solid ${on ? ACCENT_LINE : HAIR}` }}>{ms(on ? "check" : "add", { fontSize: 15 })}{c}</button>
            ); })}
          </div>
        </div>
        <div style={{ marginTop: 26 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: TXT }}>Already know well?</div>
          <div style={{ fontSize: 12.5, color: MUTE, marginTop: 3 }}>We&rsquo;ll skip the basics so the bar stays high.</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 13 }}>
            {SUGGEST_KNOW.map((c) => { const on = obKnow.includes(c); return (
              <button key={c} onClick={() => setObKnow((s) => on ? s.filter((x) => x !== c) : [...s, c])} style={{ padding: "9px 13px", borderRadius: 999, fontSize: 13, fontWeight: 600, fontFamily: "inherit", cursor: "pointer", background: on ? SURFACE2 : SURFACE2, color: on ? DIM : MUTE, border: `1px solid ${HAIR}`, textDecoration: on ? "line-through" : "none" }}>{c}</button>
            ); })}
          </div>
        </div>
        {/* SECONDARY: import youtube history */}
        <div style={{ marginTop: 30, paddingTop: 24, borderTop: `1px solid ${HAIR}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
            {ms("smart_display", { fontSize: 22, color: yt ? DANGER : MUTE, fontVariationSettings: "'FILL' 1" })}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: TXT }}>Import YouTube history</div>
              <div style={{ fontSize: 11.5, color: MUTE, marginTop: 2, lineHeight: 1.4 }}>Optional · seeds taste faster</div>
            </div>
            {yt ? (
              <div style={{ display: "flex", alignItems: "center", gap: 5, padding: "8px 11px", borderRadius: 11, background: "oklch(0.5 0.09 168 / 0.12)", color: POS, fontWeight: 600, fontSize: 12.5, flex: "0 0 auto" }}>{ms("check_circle", { fontSize: 15, fontVariationSettings: "'FILL' 1" })}Imported</div>
            ) : (
              <button onClick={() => signInWithGoogle()} style={{ padding: "8px 13px", borderRadius: 11, border: `1px solid ${HAIR}`, background: CARDBG, color: DIM, fontWeight: 600, fontSize: 12.5, fontFamily: "inherit", cursor: "pointer", whiteSpace: "nowrap", flex: "0 0 auto" }}>Import</button>
            )}
          </div>
        </div>
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, padding: "18px 24px 28px", background: `linear-gradient(transparent, ${PAPER} 32%)`, display: "flex", alignItems: "center", gap: 14 }}>
        <button onClick={completeOnboarding} style={{ background: "none", border: "none", color: MUTE, fontWeight: 600, fontSize: 14, fontFamily: "inherit", cursor: "pointer", padding: "12px 4px" }}>Skip</button>
        <button onClick={completeOnboarding} style={{ flex: 1, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, padding: 15, borderRadius: 14, border: "none", background: ACCENT, color: ON_ACCENT, fontWeight: 700, fontSize: 15, fontFamily: "inherit", cursor: "pointer", boxShadow: "0 12px 30px oklch(0.42 0.04 85 / 0.27)" }}>Start exploring{ms("arrow_forward", { fontSize: 20, fontVariationSettings: "'wght' 600" })}</button>
      </div>
    </>
  );

  const navItem = (key: Tab, icon: string, label: string) => {
    const on = tab === key;
    return (
      <button key={key} onClick={() => setTab(key)} style={{ flex: 1, background: "none", border: "none", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 3, fontFamily: "inherit", paddingBottom: 6 }}>
        {ms(icon, { fontSize: 24, color: on ? ACCENT : MUTE, fontVariationSettings: on ? "'FILL' 1, 'wght' 500" : "'FILL' 0, 'wght' 400" })}
        <span style={{ fontSize: 10.5, fontWeight: on ? 700 : 500, color: on ? ACCENT : MUTE }}>{label}</span>
      </button>
    );
  };

  return (
    <div style={{ position: "fixed", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", background: BG, overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, background: "radial-gradient(60% 50% at 50% 12%, oklch(0.85 0.04 218 / 0.4), transparent 70%)" }} />
      <div style={{ position: "relative", width: "min(440px,100vw)", height: "100dvh", overflow: "hidden", background: PAPER, boxShadow: `0 0 0 1px ${HAIR}, 0 30px 90px oklch(0.4 0.03 90 / 0.16)`, color: TXT }}>
        {showOnboarding ? renderOnboarding() : (
          <>
            {/* feed stays mounted (hidden) so scroll position + playback are remembered */}
            <div style={{ position: "absolute", inset: 0, display: tab === "feed" ? "block" : "none" }}>{renderFeed()}</div>
            {tab === "tune" && renderTune()}
            {tab === "saved" && renderSaved()}
            {tab === "you" && renderYou()}
            <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 64, zIndex: 40, display: "flex", alignItems: "stretch", background: "oklch(1 0 0 / 0.9)", backdropFilter: "blur(18px)", borderTop: `1px solid ${HAIR}` }}>
              {navItem("feed", "whatshot", "Feed")}{navItem("tune", "tune", "Tune")}{navItem("saved", "bookmark", "Saved")}{navItem("you", "person", "You")}
            </div>
          </>
        )}
        {toast && <div style={{ position: "absolute", bottom: 84, left: "50%", zIndex: 60, padding: "10px 17px", borderRadius: 999, background: "oklch(0.24 0.012 165)", border: `1px solid ${HAIR}`, color: "oklch(0.97 0.008 88)", fontSize: 13, fontWeight: 600, boxShadow: "0 12px 34px oklch(0.4 0.03 90 / 0.24)", whiteSpace: "nowrap", animation: "slideUp .25s ease", transform: "translateX(-50%)" }}>{toast}</div>}
      </div>
    </div>
  );
}

/* ── small style helpers ── */
const railBtnStyle: React.CSSProperties = { background: "none", border: "none", cursor: "pointer", display: "flex", flexDirection: "column", alignItems: "center", gap: 5, fontFamily: "inherit", padding: 0 };
const primaryBtn: React.CSSProperties = { padding: "12px 18px", borderRadius: 13, border: "none", background: ACCENT, color: ON_ACCENT, fontWeight: 700, fontSize: 14, fontFamily: "inherit", cursor: "pointer" };
const ghostBtn: React.CSSProperties = { padding: "12px 18px", borderRadius: 13, border: `1px solid ${HAIR}`, background: CARDBG, color: TXT, fontWeight: 600, fontSize: 14, fontFamily: "inherit", cursor: "pointer" };
const iconBtn: React.CSSProperties = { background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex" };

function SectionLabel({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: MUTE, ...style }}>{children}</div>;
}
