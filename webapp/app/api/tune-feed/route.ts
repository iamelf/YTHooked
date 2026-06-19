import Anthropic from "@anthropic-ai/sdk";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const client = new Anthropic(); // reads ANTHROPIC_API_KEY

const SYSTEM = `You tune a personalized "discovery feed" for an expert. Convert a free-text instruction into feed adjustments.
- "boost": topics/keywords the user wants MORE of (surface in the feed).
- "mute": topics the user already knows or wants LESS of (skip the basics).
- "credibility_floor": "on" if they ask for only experts/primary sources, "off" if they relax it, else "unchanged".
- "summary": one short sentence describing what changed, e.g. "Boosting agent memory + libSQL; muting RAG basics."
Use concise topic phrases (2-4 words), Title Case, matching how a feed would tag content. Do not invent topics the user didn't imply.`;

const SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    boost: { type: "array", items: { type: "string" } },
    mute: { type: "array", items: { type: "string" } },
    credibility_floor: { type: "string", enum: ["on", "off", "unchanged"] },
    summary: { type: "string" },
  },
  required: ["boost", "mute", "credibility_floor", "summary"],
};

export async function POST(req: NextRequest) {
  let body: any;
  try { body = await req.json(); } catch { return NextResponse.json({ error: "bad json" }, { status: 400 }); }
  const text = (body?.text ?? "").toString().trim();
  if (!text) return NextResponse.json({ error: "empty" }, { status: 400 });

  try {
    const resp = await client.messages.create({
      model: "claude-opus-4-8",
      max_tokens: 1024,
      system: SYSTEM,
      messages: [{
        role: "user",
        content: `Currently boosted: ${JSON.stringify(body.boosted ?? [])}\n` +
                 `Currently muted: ${JSON.stringify(body.muted ?? [])}\n\n` +
                 `Instruction: "${text}"`,
      }],
      output_config: { format: { type: "json_schema", schema: SCHEMA } },
    } as any);
    const out = (resp.content.find((b: any) => b.type === "text") as any)?.text ?? "{}";
    return NextResponse.json(JSON.parse(out));
  } catch (e: any) {
    return NextResponse.json({ error: e?.message ?? "tune failed" }, { status: 500 });
  }
}
