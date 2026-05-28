# Deployment Plan — `darkpool.davenc.dev`

This document plans the production deployment. **Nothing has been deployed yet** — this is a written-only plan with concrete commands ready to run when you are.

---

## 1. Architecture

```
┌──────────────────────────────┐         ┌────────────────────────────────┐
│  Browser at                  │ HTTPS   │  Vercel (free)                 │
│  darkpool.davenc.dev         │◀────────│  static React build of         │
│                              │         │  frontend/dist                 │
└────────────────┬─────────────┘         └────────────────────────────────┘
                 │
                 │ HTTPS + SSE
                 ▼
┌──────────────────────────────┐         ┌────────────────────────────────┐
│  api.darkpool.davenc.dev     │ wss://  │  Fly.io VM (free tier)         │
│                              │◀────────│  FastAPI + uvicorn             │
│  /api/v1/dashboard/*         │         │  + persistent WS to Massive    │
│  /api/v1/darkpool/*          │         │  + SQLite on a 1GB volume      │
│  /api/v1/backtest/*          │         │                                │
└──────────────────────────────┘         └────────────────────────────────┘
                                                          │
                                                          │ wss:// (delayed feed)
                                                          ▼
                                            ┌─────────────────────────────┐
                                            │  socket.massive.com         │
                                            └─────────────────────────────┘
```

**Why this split:** the backend is *stateful and long-running* (in-memory aggregator + persistent WS subscription). It cannot be deployed serverless. The frontend is static — perfect for Vercel.

---

## 2. Free-tier comparison (backend)

| Platform | Free tier | WS-friendly | SQLite persistence | Notes |
|---|---|---|---|---|
| **Fly.io** ⭐ | 3× shared-cpu-1x VMs, 256MB RAM, 3GB volume | ✅ | ✅ free volume | Recommended. Simplest Dockerfile → deploy. |
| **Oracle Cloud Always-Free** | 2× ARM VMs, 1 vCPU + 6GB RAM each, 200GB storage | ✅ | ✅ unlimited | Most generous overall. Painful signup (credit card + verification). Never expires. |
| **AWS Lightsail** | $3.50/mo (no real free tier) | ✅ | ✅ | Predictable cost, simple UI. |
| **AWS EC2 t2.micro** | 750 hrs/mo for 12 mo, then ~$8/mo | ✅ | ✅ EBS | Free year 1 only. |
| AWS App Runner | None for WS workloads | ❌ scale-to-zero | — | Skip. |
| Render free | Web services idle after 15min | ❌ | ❌ | Skip — would kill WS. |
| Google Cloud Run | Generous but 60min request cap | ⚠️ degrades | — | Skip for SSE/WS. |

**Recommendation: Fly.io.** Easy Docker, free volume for the SQLite cache, single config file.

---

## 3. Repo prep work (required before any deploy)

These changes are needed regardless of platform. None are made yet.

### 3.1 Frontend API base URL
[frontend/src/TickerDashboard.tsx:4](frontend/src/TickerDashboard.tsx:4) and [frontend/src/App.tsx:26](frontend/src/App.tsx:26) both hardcode `http://localhost:8000/api/v1`. Replace with:

```ts
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api/v1";
```

Then add `VITE_API_BASE=https://api.darkpool.davenc.dev/api/v1` as a Vercel project env var (Production scope).

### 3.2 CORS lockdown
[backend/app/main.py:92](backend/app/main.py:92) currently sets `allow_origins=["*"]`. Add a setting:

```python
# backend/app/core/config.py
CORS_ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]
```

Then read it in `main.py`:
```python
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ALLOWED_ORIGINS, ...)
```

In Fly, set the prod env var:
```
CORS_ALLOWED_ORIGINS=["https://darkpool.davenc.dev"]
```

### 3.3 Dockerfile (backend)
Create `Dockerfile` at repo root:

```dockerfile
FROM python:3.11-slim
WORKDIR /app

# System deps for sqlite + healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY backtester ./backtester

# data/ contains the SQLite cache — mounted as a volume in prod
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS http://localhost:8080/ || exit 1

CMD ["python", "-u", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

And `.dockerignore`:
```
.venv
__pycache__
*.pyc
.git
.env
node_modules
frontend
notebooks
data/*.db
.DS_Store
```

### 3.4 Fly config
Create `fly.toml` at repo root:

```toml
app = "darkpool-api"
primary_region = "iad"   # or your nearest region

[build]

[env]
  HOST = "0.0.0.0"
  PORT = "8080"
  DASHBOARD_WS_FEED = "delayed"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = false   # NEVER stop — we need the WS alive
  auto_start_machines = true
  min_machines_running = 1

[[mounts]]
  source = "darkpool_data"
  destination = "/app/data"

[[vm]]
  size = "shared-cpu-1x"
  memory = "256mb"
```

Note `auto_stop_machines = false` — critical so the WS connection stays up.

---

## 4. Deploy steps (when ready)

### 4.1 One-time setup

```bash
# Install fly CLI
brew install flyctl
fly auth signup   # or `fly auth login` if account exists

# Create the app + volume
fly apps create darkpool-api
fly volumes create darkpool_data --size 1 --region iad

# Set secrets (these go into the VM's env)
fly secrets set MASSIVE_API_KEY=...
fly secrets set CORS_ALLOWED_ORIGINS='["https://darkpool.davenc.dev"]'
# Discord is optional
fly secrets set DISCORD_BOT_TOKEN=...
fly secrets set DISCORD_CHANNEL_ID=...
```

### 4.2 Deploy backend

```bash
fly deploy
# Watch logs
fly logs
```

Then set up the custom domain in Fly:
```bash
fly certs create api.darkpool.davenc.dev
fly certs show api.darkpool.davenc.dev   # gives you the DNS records to add
```

### 4.3 Squarespace DNS records

In **Squarespace Domains → davenc.dev → DNS settings**, add:

| Host | Type | Data |
|---|---|---|
| `api.darkpool` | CNAME | `<your-app>.fly.dev` (Fly shows the exact target) |
| `_acme-challenge.api.darkpool` | CNAME | (Fly will give you this for TLS validation) |

For the frontend on Vercel:

| Host | Type | Data |
|---|---|---|
| `darkpool` | CNAME | `cname.vercel-dns.com` |

> Squarespace defaults `@`/root records to their own servers. Don't touch those — just add the two subdomains above.

### 4.4 Deploy frontend

In Vercel:
1. Import the GitHub repo.
2. **Root directory**: `frontend`
3. **Framework preset**: Vite
4. **Build command**: `npm run build`
5. **Output directory**: `dist`
6. **Environment variables (Production)**:
   - `VITE_API_BASE = https://api.darkpool.davenc.dev/api/v1`
7. **Custom domain**: add `darkpool.davenc.dev` in the project's Domains tab.

Vercel auto-deploys on every `main` push.

---

## 5. Post-deploy checks

```bash
# Backend reachable
curl https://api.darkpool.davenc.dev/

# Universe loaded
curl https://api.darkpool.davenc.dev/api/v1/dashboard/universe | jq '.tickers | length'

# Snapshot returns live numbers
curl 'https://api.darkpool.davenc.dev/api/v1/dashboard/snapshot?limit=5'

# SSE stream emits events (during market hours)
curl -N 'https://api.darkpool.davenc.dev/api/v1/dashboard/stream' | head -n 5

# Frontend
open https://darkpool.davenc.dev
```

Browser check: open the dashboard, confirm the table fills in, look at DevTools Network tab — `EventSource` should be `pending` with frames flowing.

---

## 6. Cost & quota notes

- **Fly free tier**: 3× shared-cpu-1x machines × ~256MB. We use 1 machine, so well under. Outbound bandwidth: 160GB/mo free. SSE is text deltas — easily under the cap.
- **Vercel free**: 100GB bandwidth/mo. The dashboard is small JS + HTML — won't be close.
- **Squarespace DNS**: free with the domain.

**Total expected cost: $0/mo.** First budget overrun will most likely be Fly bandwidth if the dashboard becomes public and many people leave it open; switch to a paid Fly plan ($1.94/mo for the same VM unmetered, or scale up) when that becomes a problem.

---

## 7. What this plan does NOT cover

- CI/CD: relies on `fly deploy` from your laptop. Add a GitHub Action later if useful.
- Auth: the dashboard is publicly readable. If you want to lock it down, add a simple bearer-token check in middleware before deploying publicly.
- Observability: Fly's built-in logs are enough for now. Add Logflare/Axiom later if needed.
- Real-time WS upgrade: still on delayed feed. Switch `DASHBOARD_WS_FEED=realtime` in Fly secrets if/when your Massive plan supports it.
- Discord bot deploy: separate concern — the bot is optional and would deploy as its own Fly app or stay local.
