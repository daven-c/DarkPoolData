# DarkPoolData Platform

An institutional-grade platform to ingest, explore, backtest, and alert on off-exchange (dark pool/TRF) trade data using the **Massive.com** (formerly Polygon.io) market data APIs.

**Current design (v2 — Managed Signals):** a central `RuleEngine` evaluates composable condition trees against every incoming TRF trade. When a rule fires it broadcasts a `Signal` to an in-app SSE feed, a Discord channel, and a SQLite history table. Each persisted alert is later stamped with +5m/+30m/+1d forward returns so signal quality is measurable. Admins compose and iterate rules in a Strategy Lab UI; rule-based backtests are a **signal validator** — they replay historical TRF trades through a fresh engine and answer "did the signal predict the move?" via forward-return hit rates and a price chart with bull/bear markers (no portfolio P&L simulation).

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

# Alerts (defaults shown)
ALERTS_SSE_QUEUE_MAX=1000
ALERTS_DEFAULT_COOLDOWN_S=300        # Per (rule, symbol) cooldown between signals
ALERTS_FORWARD_HORIZONS_MIN=[5,30,1440]  # Horizons stamped on persisted alerts
```

> **Delayed feed note**: if your Massive plan is delayed-only, set `DASHBOARD_WS_FEED=delayed`. Using `realtime` on a delayed-only key authenticates but receives no ticks.

> **No API key**: if `MASSIVE_API_KEY` is unset the backtest endpoints fall back to `MockDataProvider` automatically — all routes remain functional for UI testing.

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
