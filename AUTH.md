# Authentication Plan — Supabase Auth (invite-only)

This document plans the auth integration. **Nothing has been implemented yet.** Goal: gate the dashboard to a manually-invited list of ≤5 users today, set up the right foundation for per-user features (watchlists, alerts) later.

---

## 1. Architecture

```
┌──────────────────────────────┐
│  Browser                     │
│  ┌────────────────────────┐  │      ┌──────────────────────────────┐
│  │  AuthGate (React)      │──┼─────▶│  Supabase Auth (managed)     │
│  │  signs in via email    │  │      │  - issues JWT                 │
│  │  magic link or OAuth   │  │◀─────│  - hosts user table           │
│  └─────────┬──────────────┘  │      │  - allowlist via invite       │
│            │                 │      └──────────────────────────────┘
│            │ session token   │
│            ▼                 │
│  ┌────────────────────────┐  │
│  │  TickerDashboard       │  │
│  └─────────┬──────────────┘  │
└────────────┼─────────────────┘
             │ Authorization: Bearer <JWT>   (and ?token=… on SSE)
             ▼
┌──────────────────────────────┐
│  FastAPI (Fly.io)            │
│  ┌──────────────────────┐    │
│  │  verify_supabase_jwt │ ◀──┼──── verifies signature against
│  │  (FastAPI dependency)│    │     Supabase's JWT secret (HS256)
│  └──────────┬───────────┘    │
│             ▼                │
│  /api/v1/dashboard/*  (gated)│
│  /api/v1/darkpool/*   (gated)│
│  /api/v1/backtest/*   (gated)│
│  GET /                (open) │
└──────────────────────────────┘
```

**Why Supabase Auth specifically:**
- Free tier covers 50k MAU.
- Hosted login UI (`@supabase/auth-ui-react`) means no custom forms to build.
- Magic-link email out of the box; OAuth providers (Google, GitHub) one click to enable.
- Signups can be disabled — only invited emails get in.
- JWT is HS256-signed with a shared secret you can verify in FastAPI in a few lines.
- Decouples *auth* from *data*. You can keep SQLite for now and migrate to Supabase Postgres later only if you want.

---

## 2. Supabase setup (one-time, ~15 min)

1. Create project at supabase.com → free tier → choose a region near Fly's (e.g. `us-east-1`).
2. **Project Settings → API**: copy `Project URL` (becomes `SUPABASE_URL`) and `anon` public key (becomes `SUPABASE_ANON_KEY`). These are safe to ship in the frontend bundle.
3. **Project Settings → API → JWT Settings**: copy the `JWT Secret` (becomes `SUPABASE_JWT_SECRET` — backend only, treat as a secret).
4. **Authentication → Providers**: enable **Email** with "Confirm email" on. Optionally enable Google or GitHub.
5. **Authentication → Settings**:
   - **Disable signups** → toggle "Allow new users to sign up" OFF.
   - Set the **Site URL** to `https://darkpool.davenc.dev`.
   - Add `http://localhost:5173` to **Redirect URLs** for local dev.
6. **Authentication → Users → Invite**: invite the 5 emails. They each get a one-time link to set up access.

That's it on the Supabase side. No tables to create, no SQL to write — until you add per-user features.

---

## 3. Repo changes (plan, not done)

### 3.1 Frontend

**Install:**
```bash
npm install --prefix frontend @supabase/supabase-js @supabase/auth-ui-react @supabase/auth-ui-shared
```

**New file: `frontend/src/supabase.ts`** — single Supabase client instance.
```ts
import { createClient } from "@supabase/supabase-js";

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL!,
  import.meta.env.VITE_SUPABASE_ANON_KEY!
);
```

**New file: `frontend/src/AuthGate.tsx`** — wraps `App`. If no session, render the Supabase Auth UI; otherwise render children. Listens to `onAuthStateChange` for sign-in/sign-out.

```tsx
import { useEffect, useState } from "react";
import { Auth } from "@supabase/auth-ui-react";
import { ThemeSupa } from "@supabase/auth-ui-shared";
import { supabase } from "./supabase";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  if (loading) return null;
  if (!session) {
    return (
      <div className="glass-panel" style={{ maxWidth: 380, margin: "10vh auto", padding: 32 }}>
        <h2 className="gradient-text" style={{ marginBottom: 16 }}>DarkPoolData</h2>
        <Auth
          supabaseClient={supabase}
          appearance={{ theme: ThemeSupa }}
          providers={["google"]}        // or [] for email-only
          magicLink={true}
          showLinks={false}             // hides "Sign up" — invite-only
          theme="dark"
        />
      </div>
    );
  }
  return <>{children}</>;
}
```

**Edit `frontend/src/main.tsx`** — wrap `<App />` with `<AuthGate>`.

**Edit fetch / EventSource calls in [TickerDashboard.tsx](frontend/src/TickerDashboard.tsx) and [App.tsx](frontend/src/App.tsx)** — attach the JWT. Add a small helper:

```ts
async function authedFetch(url: string, init: RequestInit = {}) {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return fetch(url, {
    ...init,
    headers: { ...(init.headers || {}), Authorization: `Bearer ${token}` },
  });
}

// For SSE — EventSource can't set headers, so pass token via query string.
async function authedEventSource(url: string) {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return new EventSource(`${url}?token=${encodeURIComponent(token || "")}`);
}
```

Replace each plain `fetch(...)` / `new EventSource(...)` call with these helpers.

**Edit `frontend/.env.example`** (create it):
```
VITE_API_BASE=http://localhost:8000/api/v1
VITE_SUPABASE_URL=https://YOUR-PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
```

### 3.2 Backend

**Install:**
```
pyjwt>=2.8.0
```
(add to `requirements.txt`)

**Edit `backend/app/core/config.py`** — add:
```python
SUPABASE_JWT_SECRET: str = ""
SUPABASE_JWT_AUDIENCE: str = "authenticated"   # Supabase default
AUTH_REQUIRED: bool = True                     # set False locally if you want to bypass
```

**New file: `backend/app/core/auth.py`**:
```python
import jwt
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from backend.app.core.config import settings

bearer = HTTPBearer(auto_error=False)

def _decode(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience=settings.SUPABASE_JWT_AUDIENCE,
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {e}")

def require_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    if not settings.AUTH_REQUIRED:
        return {"sub": "local-dev", "email": "dev@localhost"}
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return _decode(creds.credentials)

def require_user_query(
    token: str = Query(None),
) -> dict:
    """SSE variant — EventSource can't set headers, so accept ?token=..."""
    if not settings.AUTH_REQUIRED:
        return {"sub": "local-dev", "email": "dev@localhost"}
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="missing token query param")
    return _decode(token)
```

**Edit [backend/app/api/dashboard.py](backend/app/api/dashboard.py)** — apply the dependency:
```python
from backend.app.core.auth import require_user, require_user_query

@router.get("/snapshot")
def get_snapshot(request: Request, ..., user: dict = Depends(require_user)):
    ...

@router.get("/stream")
async def stream(request: Request, user: dict = Depends(require_user_query)):
    ...

# Apply require_user to /universe and /config too; keep `/` open for health checks.
```

Apply `require_user` similarly to [darkpool.py](backend/app/api/darkpool.py) and [backtest.py](backend/app/api/backtest.py).

### 3.3 Local dev

Set `AUTH_REQUIRED=False` in your `.env` for development, so you can keep `localhost:5173` working without signing in. Production env (Fly secrets) leaves it `True`.

---

## 4. Deployment env-var checklist

When you actually deploy (per [DEPLOYMENT.md](DEPLOYMENT.md)), set:

**Vercel (frontend, Production scope):**
- `VITE_API_BASE = https://api.darkpool.davenc.dev/api/v1`
- `VITE_SUPABASE_URL = https://YOUR-PROJECT.supabase.co`
- `VITE_SUPABASE_ANON_KEY = eyJ...`

**Fly (backend secrets):**
- `MASSIVE_API_KEY=...`
- `SUPABASE_JWT_SECRET=...` ← never commit
- `AUTH_REQUIRED=True`
- `CORS_ALLOWED_ORIGINS=["https://darkpool.davenc.dev"]`

**Supabase project Authentication → URL Configuration:**
- Site URL: `https://darkpool.davenc.dev`
- Additional redirect URLs: `http://localhost:5173` (dev) and any Vercel preview URLs you care about.

---

## 5. Inviting users

From the Supabase dashboard:

**Authentication → Users → Invite User** → enter email → they receive a one-time link.

That's it. To remove access, delete the user row. No code change ever needed for membership changes.

---

## 6. Migration path for per-user features

When you're ready to add watchlists / per-user alerts / saved searches, you have two options:

**Option A — Keep SQLite, add a `user_id` column.**
- Get the `sub` (UUID) from the verified JWT in every authed request.
- Scope queries by `user_id`.
- Pros: no new infra. Cons: no RLS, you have to be careful in every query.

**Option B — Move app data into Supabase Postgres.**
- Create tables in Supabase.
- Enable RLS with policies like `auth.uid() = user_id`.
- Frontend reads/writes via the Supabase JS client directly — bypasses your FastAPI for that data.
- Pros: row-level security comes for free; less backend code. Cons: harder to keep server-side aggregation logic close to data; SQLite still needed for the dashboard cache anyway.

For the dashboard's running totals specifically (which are global, not per-user), SQLite stays. Per-user features should likely live in Supabase Postgres with RLS. That's a Q3+ decision.

---

## 7. What this plan does NOT do

- **Refresh-token handling**: `@supabase/supabase-js` does this automatically — JWT is refreshed in the background. No code needed.
- **Logout button**: trivial to add (`await supabase.auth.signOut()`) but not part of this gate — add when you want.
- **Profile page**: not needed for invite-only mode. Add when you add per-user features.
- **Admin UI**: invites are done via Supabase dashboard. Build an admin page only when you outgrow that.
- **Email branding**: Supabase's default invite email is fine. You can customize templates later if needed.
- **CF Access fallback**: skipped. If you ever want to add a second layer (e.g. to gate even unauthenticated traffic at the edge), it's drop-in additive.

---

## 8. Estimated implementation time

| Step | Time |
|---|---|
| Supabase project + invites | 15 min |
| Backend: deps, settings, auth.py, apply dependency | 1 hr |
| Frontend: install, supabase.ts, AuthGate, fetch helpers | 1.5 hr |
| Wire env vars locally + smoke test | 30 min |
| Deploy + Vercel/Fly env vars | 30 min |
| **Total** | **~4 hrs** |
