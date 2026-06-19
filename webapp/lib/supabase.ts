// Burrfeed — browser Supabase client.
// Uses the PUBLISHABLE key (sb_publishable_...). It is RLS-enforced and safe to
// ship to the browser. Never put the sb_secret_... key here — that's worker-only.

import { createClient } from "@supabase/supabase-js";

export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, // the sb_publishable_... key
  { auth: { persistSession: true, autoRefreshToken: true } },
);
