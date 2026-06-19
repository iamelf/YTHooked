# Deploying Hooked

**Live:** https://webapp-one-gamma-17.vercel.app (Vercel project
`iamelfs-projects/webapp`, deployed via `vercel --prod` from `webapp/`).
The app loads and anonymous feed reads work today; **sign-in needs the Google
OAuth steps in §1 below** before "Connect" will complete.

The web app lives in `webapp/` (Next.js 14 App Router). Three things have to be
wired before your husband can open it on his phone: **Google sign-in**, **env
vars**, and **the Vercel deploy** itself.

---

## 1. Supabase — Google sign-in (= "Connect YouTube")

Sign-in *is* the YouTube connection: it's Google OAuth requesting the YouTube
scope, so the session carries a `provider_token` we use to push the watchlist.

**a. Google Cloud Console** (console.cloud.google.com)
1. Create / pick a project → **APIs & Services → Library** → enable
   **YouTube Data API v3**.
2. **APIs & Services → Credentials → Create Credentials → OAuth client ID** →
   *Web application*.
3. Authorized redirect URI:
   `https://gxatoazxzoaymgrghizz.supabase.co/auth/v1/callback`
4. **OAuth consent screen**: add scope
   `https://www.googleapis.com/auth/youtube`, and add your husband's Google
   address under **Test users** (no need to publish the app for a personal demo).
5. Copy the **Client ID** and **Client secret**.

**b. Supabase dashboard** → Authentication → Providers → **Google**: enable it,
paste the Client ID + secret, save.

**c. Supabase** → Authentication → URL Configuration:
- **Site URL**: `https://webapp-one-gamma-17.vercel.app`
- **Redirect URLs**: add `https://webapp-one-gamma-17.vercel.app/**` and
  `http://localhost:3000/**` for local dev.

The app already requests the right scope (`lib/account.ts` →
`signInWithGoogle`), so no code change is needed here.

---

## 2. Environment variables

| Var | Where | Notes |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | client | already in `.env.local.example` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | client | the `sb_publishable_…` key — RLS-safe |
| `ANTHROPIC_API_KEY` | **server only** | powers `/api/tune-feed`. Never prefix `NEXT_PUBLIC_`. Without it, Tune falls back to local keyword matching. |

The `sb_secret_…` key is **not** used by the web app — keep it worker-side only.

---

## 3. Per-user feed scoping (Part 2)

After your husband signs in once, run `supabase/scope-feed.sql` in the Supabase
SQL editor (set his email first). It stamps the `-db` teasers with his
`owner_id` so they show only for him; everything with `owner_id = null` stays
shared. RLS does the enforcement — no code change.

---

## 4. Vercel — already deployed

The project is linked and live (see top of file). The two `NEXT_PUBLIC_…`
Supabase vars are already set in Production. To add the Claude key (otherwise
Tune uses the keyword fallback), run it through *your* terminal so the secret
never lands in chat:

```
cd webapp
! vercel env add ANTHROPIC_API_KEY production   # paste the key when prompted
vercel --prod --yes                              # redeploy to pick it up
```

Re-deploy any time with `cd webapp && vercel --prod --yes`. To wire GitHub
auto-deploy instead, connect the repo under the Vercel project's **Settings →
Git** (root directory `webapp`).
