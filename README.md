# DarkPoolData Platform

An institutional-grade platform to ingest, explore, backtest, and alert on off-exchange (dark pool/TRF) trade data using the **Massive.com** (formerly Polygon.io) market data APIs.

**Current design (v2 — Managed Signals):** a central `RuleEngine` evaluates composable condition trees against every incoming TRF trade. When a rule fires it broadcasts a `Signal` to an in-app SSE feed, a Discord channel, and a SQLite history table. Each persisted alert is later stamped with +5m/+30m/+1d forward returns so signal quality is measurable. Admins compose and iterate rules in a Strategy Lab UI; rule-based backtests are a **signal validator** — they replay historical TRF trades through a fresh engine and answer "did the signal predict the move?" via forward-return hit rates and a price chart with bull/bear markers (no portfolio P&L simulation).

> **New here?** Jump to the [Beginner Setup Guide](#-beginner-setup-guide-non-technical-users) below for a click-by-click walkthrough that assumes no prior coding experience. Developers can skip ahead to [Prerequisites & Setup](#️-prerequisites--setup).

---

## 🧑‍🌾 Beginner Setup Guide (Non-Technical Users)

This walkthrough assumes **zero programming experience**. Allow ~30 minutes for the first run. You'll need a computer (macOS, Windows, or Linux), an internet connection, and a free Massive.com / Polygon.io account.

The platform is two programs that talk to each other: a **backend** (data engine, runs in the background) and a **frontend** (the web dashboard you'll look at). You'll start each in its own terminal window, then open the dashboard in your browser.

### Step 1 — Install the three tools you'll need

Each is free and only installed once.

**1a. Python 3.10 or newer** — the language the backend is written in.
- **macOS**: open the **Terminal** app (press `Cmd+Space`, type `Terminal`, hit Enter). Type `python3 --version` and press Enter. If you see `Python 3.10.x` or higher, you're done. Otherwise download the installer from https://www.python.org/downloads/ and run it.
- **Windows**: open **Command Prompt** (press the Windows key, type `cmd`, hit Enter). Type `python --version`. If missing or too old, install from https://www.python.org/downloads/ and **make sure to check the box "Add python.exe to PATH"** on the first install screen.
- **Linux**: open a terminal and run `python3 --version`. Most distributions already include Python 3.10+.

**1b. Node.js 18 or newer** — runs the web dashboard.
- All platforms: download the **LTS** installer from https://nodejs.org/ and click through with the default options.
- Confirm by opening a **new** terminal window and running `node --version`.

**1c. Git** — downloads the project code.
- **macOS**: Terminal will offer to install Xcode Command Line Tools the first time you run `git --version`. Accept it.
- **Windows**: install from https://git-scm.com/download/win (defaults are fine).
- **Linux**: `sudo apt install git` on Debian/Ubuntu, or use your distro's package manager.

### Step 2 — Download the project

Open a terminal, navigate to wherever you keep projects (your home folder is fine), and run:

```bash
git clone https://github.com/daven-c/DarkPoolData.git
cd DarkPoolData
```

If `git clone` fails, alternative: click the green **Code** button on the GitHub page → **Download ZIP** → unzip it → open a terminal inside the unzipped folder.

### Step 3 — Get a Massive.com / Polygon.io API key

The platform reads market data through Massive.com (formerly Polygon.io).

1. Go to https://polygon.io/ and click **Sign up**.
2. The free **Basic** tier is enough to try everything with 15-minute-delayed data.
3. After signing in, open **Dashboard → API Keys** and copy your key.

Keep the key visible — you'll paste it in the next step.

### Step 4 — Create a settings file (`.env`)

The backend reads its secrets from a file called `.env` (with the leading dot, no extension) at the project root.

1. Inside the `DarkPoolData` folder, create a new plain-text file named exactly `.env`.
   - On macOS/Linux: `nano .env` (or use VS Code, TextEdit, etc.).
   - On Windows: open Notepad → File → Save As → set filename to `.env`, **change "Save as type" to "All Files"**, and save inside the `DarkPoolData` folder. Otherwise Notepad adds a hidden `.txt`.
2. Paste this in:

```env
MASSIVE_API_KEY=paste_your_key_here
DASHBOARD_WS_FEED=delayed
```

3. Replace `paste_your_key_here` with the key you copied. Save.

`delayed` matches the free Polygon plan. If you ever upgrade to a real-time plan, change it to `realtime`.

### Step 5 — Install the backend (one-time)

In the terminal, inside the `DarkPoolData` folder:

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (Command Prompt):**
```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

The `pip install` step downloads a handful of packages — give it 1–3 minutes. When it's done, your terminal prompt should be prefixed with `(.venv)` — that just means Python is using this project's isolated packages.

> If PowerShell blocks the activate script with a "scripts disabled" error, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, answer Yes, then retry.

### Step 6 — Install the frontend (one-time)

In the same terminal:

```bash
npm install --prefix frontend
```

Another 1–3 minutes. Ignore any yellow `npm warn` messages — only red `npm error` lines matter.

### Step 7 — Start the backend

Still in that terminal (the one with `(.venv)` in the prompt):

```bash
python3 backend/app/main.py
```

On Windows, use `python` instead of `python3`. You'll see log lines as the engine starts and connects to Massive. **Leave this window open and running.** When you see `Uvicorn running on http://0.0.0.0:8000`, the backend is ready.

### Step 8 — Start the frontend (in a second terminal)

Open a **new** terminal window or tab (don't close the first one). Navigate back into the project:

```bash
cd DarkPoolData
npm run dev --prefix frontend
```

Within a few seconds you'll see a line like:
```
  ➜  Local:   http://localhost:5173/
```

Click that link (or copy it into your browser). You'll see the **Signals Dashboard** with live engine-health chips, a tracked-universe panel, and a rules table.

### Step 9 — (Optional) Discord notifications

Skip this unless you specifically want signals pushed to a Discord server. Alerts still appear in the web dashboard either way. If you want them, see the Discord configuration block in [Environment Variables](#2-environment-variables-env) below and run `python3 bot/bot.py` in a third terminal.

### Stopping and restarting later

- **To stop**: press `Ctrl+C` in each terminal window.
- **To restart on another day**: open two terminals, `cd` into `DarkPoolData` in each, then:
  - Terminal 1: activate the venv (`source .venv/bin/activate` on macOS/Linux, `.venv\Scripts\activate` on Windows), then `python3 backend/app/main.py`.
  - Terminal 2: `npm run dev --prefix frontend`.

You **do not** need to repeat Steps 5 or 6 unless you pulled new code that changed `requirements.txt` or `frontend/package.json`.

### Troubleshooting

| Symptom | What to try |
|---------|-------------|
| `python3: command not found` (Windows) | Use `python` instead. If that also fails, reinstall Python and check the "Add python.exe to PATH" box. |
| `pip: command not found` | Run `python3 -m pip install -r requirements.txt` instead. |
| `npm: command not found` | Node.js isn't installed or isn't on your PATH. Reinstall from https://nodejs.org/ and open a brand-new terminal. |
| Backend exits with *"Massive.com API key is not configured"* | The `.env` file is missing or in the wrong place. It must be at the project root (same folder as `requirements.txt`) and the line must read exactly `MASSIVE_API_KEY=...`. |
| Backend connects but dashboard stays empty all day | Your Polygon plan is delayed-only but `DASHBOARD_WS_FEED=realtime` is set. Change it to `delayed` in `.env` and restart. |
| Browser says *"This site can't be reached"* | The backend (Step 7) or frontend (Step 8) terminal isn't running anymore. Both must stay open. |
| `Port 8000 already in use` | Another program is holding the port. Quit it, or add `PORT=8001` to `.env` and use http://localhost:8001 in the browser. |
| `Port 5173 already in use` | Run `npm run dev --prefix frontend -- --port 5174` and use the new URL. |
| Notepad saved `.env.txt` instead of `.env` | In Notepad's Save As dialog, set "Save as type" to **All Files**, then re-save as `.env`. Or rename the file in File Explorer (you may need to enable "File name extensions" in the View menu first). |
| PowerShell blocks `.venv\Scripts\Activate.ps1` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, answer Yes, retry. |

If you hit something not on this list, scroll the failing terminal back to the **first** red error line — that's usually the real problem — and search it on Google with "DarkPoolData" appended.

---

## 📂 Project Architecture

```
backend/app/
  api/
    darkpool.py          # TRF trade details + aggregates (single-symbol explorer)
    backtest.py          # POST /backtest/rules (signal validator: forward returns + price series)
    dashboard.py         # Livestream: snapshot + SSE stream + universe + health strip
    alerts.py            # GET /alerts/stream (SSE) · /alerts/recent · /alerts/history
    rules.py             # CRUD /rules · /rules/metrics · /rules/stats · /rules/preview
  rules/
    events.py            # MarketEvent DTO · TickerState (tick-test, running totals, OHLC)
    metrics.py           # 12-metric catalog for condition builder
    conditions.py        # Leaf + Composite (AND/OR/NOT) condition trees
    index.py             # Leaf condition matching indexes (binary search lists + hash maps)
    evaluator.py         # Boolean propagation network compiler (EvalNodes)
    rule.py              # Rule + Signal; JSON round-trip
    engine.py            # RuleEngine: process() · snapshot() · preview() · subscribe() SSE
    builtins.py          # 5 seed rules (Whale Buy, Block, Bullish Sweep, Breakout, Net Flow)
    tests/               # 15 pytest cases (test_engine.py and test_optimized_engine.py)
  services/
    massive.py           # Massive REST client (trades, aggs, last price, daily close)
    stream.py            # Massive WebSocket → MarketEvent → RuleEngine
    alerts.py            # AlertStore (SQLite) · AlertDispatcher (SSE+Discord+DB) · stamper
    rules_store.py       # SQLite rules table · seed builtins · hot-reload helper
    backtest_rules.py    # Signal validator: historical replay → signals + forward returns + price series
    alerts.py            # AlertStore (rule_stats/health) · AlertDispatcher (SSE+Discord+DB) · stamper
    dashboard_store.py   # SQLite cache for prior-day TRF totals (% change column)
    ingestion_stats.py   # Thread-safe 1s-bucketed throughput counter (events/sec, total)
    discord.py           # Webhook broadcaster to bot receiver
  core/
    config.py            # pydantic-settings; reads .env; all tunable knobs
  main.py                # FastAPI app + lifespan (engine · dispatcher · streamer · stamper)

frontend/src/
  App.tsx                # 4-tab shell (Dashboard · Alerts · Strategy Lab · Stock Explorer)
  SignalsDashboard.tsx   # Landing view: engine-health strip + per-rule stats + recent signals
  AlertsFeed.tsx         # Live signal feed (SSE) + history with forward-return columns
  StrategyLab.tsx        # Admin rule builder: conditions, groups, preview, CRUD + inline backtest
  RuleBacktest.tsx       # Signal-validator panel: forward-return stats + price chart w/ markers
  StockExplorer.tsx      # Single-symbol darkpool deep-dive + "rules fired on this symbol" history
  index.css              # Glassmorphic dark mode stylesheet

backtester/
  data.py                # APIDataProvider · CSVDataProvider · MockDataProvider

bot/bot.py               # discord.py client + aiohttp webhook server (:5000 POST /alert)
notebooks/               # Marimo notebooks for ad-hoc exploration
```

---

## 🛠️ Prerequisites & Setup

**Python 3.10+** and **Node 18+** required.

### 1. Virtual Environment (single venv at repo root)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> All Python entry points run from the repo root so that `backend/` and `backtester/` resolve correctly on `sys.path`.

### 2. Environment Variables (`.env`)

```env
# Massive.com API Key (formerly Polygon.io)
MASSIVE_API_KEY=your_key_here

# Discord (optional — signals still fire without this)
DISCORD_BOT_TOKEN=your_token
DISCORD_CHANNEL_ID=your_channel_id
DISCORD_WEBHOOK_URL=http://localhost:5000/alert

# Dashboard (defaults shown)
DASHBOARD_UNIVERSE_SIZE=1000         # Top-N tickers by prior-day DP dollar volume (1000-3000 typical;
                                     #   ceiling = Massive WS per-symbol subscription cap; prior-day
                                     #   seeding cost scales linearly, runs in a background thread)
DASHBOARD_WS_FEED=delayed            # "realtime" or "delayed" (match your plan tier)
DASHBOARD_SEED_PRIOR_DAY=True        # Backfill % change on boot

# Off-hours simulation (opt-in — drives the engine with a synthetic tape)
SIMULATE_STREAM=False                # True → MockStreamer feeds fake trades; works with NO API key
SIMULATE_STREAM_RATE=20              # Target synthetic trades/sec when SIMULATE_STREAM=True
# SIMULATE_UNIVERSE defaults to 10 large-caps; override in .env as a JSON list if desired

# Alerts (defaults shown)
ALERTS_SSE_QUEUE_MAX=1000
ALERTS_DEFAULT_COOLDOWN_S=300        # Per (rule, symbol) cooldown between signals
ALERTS_FORWARD_HORIZONS_MIN=[5,30,1440]  # Horizons stamped on persisted alerts
```

> **Delayed feed note**: if your Massive plan is delayed-only, set `DASHBOARD_WS_FEED=delayed`. Using `realtime` on a delayed-only key authenticates but receives no ticks.

> **No API key**: if `MASSIVE_API_KEY` is unset the backtest endpoints fall back to `MockDataProvider` automatically — all routes remain functional for UI testing.

> **Testing the live engine when the market is closed**: set `SIMULATE_STREAM=True`. Instead of the Massive WebSocket, a `MockStreamer` drives the `RuleEngine` with a synthetic random-walk tape (with occasional block trades) over a fixed 10-ticker universe, so the full ingestion → condition-matching → alert pipeline runs end-to-end with no API key and no open market. This is **opt-in only** — a missing API key never silently switches to simulation, so real misconfigurations stay loud. The dashboard logs `SIMULATE_STREAM on — MockStreamer driving the engine (NOT live data)` on boot.

---

## 🚀 Running the Services

### Quickstart

```bash
# Terminal 1 — backend
source .venv/bin/activate
python3 backend/app/main.py        # http://localhost:8000  (/docs for Swagger)

# Terminal 2 — frontend
npm install --prefix frontend      # first time only
npm run dev --prefix frontend      # http://localhost:5173
```

### Backend startup sequence

On `python3 backend/app/main.py` the lifespan hook:
1. Opens `data/rules.db`, seeds the 5 built-in rules if the table is empty, loads them into `RuleEngine`.
2. Calls `get_grouped_daily_aggs` for the prior trading day, picks top-N by TRF dollar volume, subscribes `T.<ticker>` on the Massive WebSocket.
3. Starts `AlertDispatcher` (SSE fan-out + Discord + SQLite write).
4. Starts the forward-return stamper (runs every 60 s; fetches price at +5m/+30m/+1d and updates `data/alerts.db`).

### Discord bot (optional)

```bash
python3 bot/bot.py    # webhook listener on :5000
```

### Marimo notebooks

```bash
marimo edit notebooks/darkpool_exploration.py
```

---

## 📡 API Endpoints (`/api/v1/…`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/dashboard/snapshot` | Live universe snapshot (sortable, paginated) |
| `GET` | `/dashboard/stream` | SSE — per-trade `TickerState` deltas |
| `GET` | `/dashboard/universe` | Active ticker list |
| `GET` | `/dashboard/health` | Engine-health strip: tickers tracked/active, signals today, last-signal ts, feed tier |
| `GET` | `/darkpool/summary` | Single-symbol TRF aggregates for a date |
| `GET` | `/darkpool/trades` | Raw TRF tick log for a symbol/date |
| `POST` | `/backtest/rules` | Signal-validator backtest → `{signals, signal_count, forward_return_stats, price_series}` |
| `GET` | `/alerts/stream` | SSE — live `Signal` events as they fire |
| `GET` | `/alerts/recent` | Most-recent N alerts (default 100) |
| `GET` | `/alerts/history` | Historical alerts with `+5m/+30m/+1d` returns; `?symbol=&rule_name=&limit=` |
| `GET` | `/rules` | List all admin rules |
| `POST` | `/rules` | Create rule + hot-reload engine |
| `PATCH` | `/rules/{id}` | Partial-update rule + hot-reload engine |
| `DELETE` | `/rules/{id}` | Delete rule + hot-reload engine |
| `GET` | `/rules/metrics` | Metric catalog for the builder UI |
| `GET` | `/rules/stats` | Per-rule lifetime stats: signal counts + +5m/+30m/+1d hit rate & avg return |
| `POST` | `/rules/preview` | Evaluate draft rule against current live `TickerState`s → matched symbols |

---

## 📊 Per-ticker snapshot columns

Served by `GET /dashboard/snapshot` and surfaced in the Dashboard's expandable tracked-universe
panel and the Stock Explorer:

| Column | Source |
|--------|--------|
| **TOTAL AMOUNT** | Σ (price × size) of all TRF trades today (exchange ID 4) |
| **DAILY AMOUNT CHANGE** | `(today − prior_day) / prior_day × 100`; `prior_day` from `data/dashboard_cache.db` |
| **AT ASK / AT BID** | Lee-Ready tick test: uptick → at_ask, downtick → at_bid, equal → prior side |
| **NET VALUE** | `AT ASK − AT BID` |
| **DP TRADES** | Count of TRF trades received today |
| **BLOCK TRADES** | Count where `size ≥ 10 000` |

---

## 🔔 Built-in Signal Rules

| Rule | Logic | Side |
|------|-------|------|
| **Whale Buy** | Single trade notional ≥ $500k AND side = ask | bull |
| **Block Trade** | `is_block = true` (size ≥ 10 000 shares) | neutral |
| **Bullish Sweep** | Ask-side notional in last 5 min ≥ $1M | bull |
| **Price Breakout** | Price move ≥ 1 % in last 10 min | bull |
| **Bearish Net Flow** | Net flow notional in last 15 min ≤ −$500k | bear |

Add or modify rules at runtime via `POST /rules` or the Strategy Lab UI — the engine hot-reloads immediately.

---

## 🧪 Running Tests

```bash
source .venv/bin/activate
python3 -m pytest backend/app/rules/tests    # 15 unit tests for the rule engine (including optimization benchmarks)
```

---

## 🧪 Validating a rule (signal backtest)

The backtest is a **signal-quality tool**, not a P&L simulator. From the Strategy Lab, hit
"Backtest this rule" (or `POST /backtest/rules`) to replay historical TRF trades for up to a
handful of symbols through a fresh `RuleEngine`. The result answers one question — *did the signal
predict the move?*:

- **`signals`** — every fire, with symbol, timestamp, side (bull/bear/neutral), and price.
- **`forward_return_stats`** — per-rule, per-horizon (+5m/+30m/+1d) hit rate, avg/median return,
  best/worst.
- **`price_series`** — a downsampled price path per symbol so the chart can mark each signal.

A fresh engine is used so the backtest never pollutes the live ingestion stats.

---

## 🔭 Roadmap

See `ROADMAP.md` for the full phase-by-phase tracker. Planned (not yet started):
- **Auth** (`AUTH.md`) — Supabase invite-only gate
- **Deployment** (`DEPLOYMENT.md`) — Fly.io backend + Vercel frontend → `darkpool.davenc.dev`
- **Nightly screener service** — full `services/screener.py` with cron scheduling
- **NBBO quote-join** for exact at-bid/at-ask (v1.1; tick-test sufficient for now)
