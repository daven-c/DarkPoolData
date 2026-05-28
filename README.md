# DarkPoolData Platform

An institutional-grade platform to ingest, explore, backtest, and alert on off-exchange (dark pool/TRF) trade data using the **Massive.com** (formerly Polygon.io) market data APIs.

**Current design (v2 — Managed Signals):** a central `RuleEngine` evaluates composable condition trees against every incoming TRF trade. When a rule fires it broadcasts a `Signal` to an in-app SSE feed, a Discord channel, and a SQLite history table. Each persisted alert is later stamped with +5m/+30m/+1d forward returns so signal quality is measurable. Admins compose and iterate rules in a Strategy Lab UI; rule-based backtests produce portfolio P&L alongside forward-return hit rates.

---

## 📂 Project Architecture

```
backend/app/
  api/
    darkpool.py          # TRF trade details + aggregates (single-symbol scanner)
    backtest.py          # POST /backtest/run (indicator viz) + POST /backtest/rules (rule P&L)
    dashboard.py         # Livestream: snapshot + SSE stream + universe list
    alerts.py            # GET /alerts/stream (SSE) · /alerts/recent · /alerts/history
    rules.py             # CRUD /rules · /rules/metrics · /rules/preview
  rules/
    events.py            # MarketEvent DTO · TickerState (tick-test, running totals, OHLC)
    metrics.py           # 12-metric catalog for condition builder
    conditions.py        # Leaf + Composite (AND/OR/NOT) condition trees
    rule.py              # Rule + Signal; JSON round-trip
    engine.py            # RuleEngine: process() · snapshot() · preview() · subscribe() SSE
    builtins.py          # 5 seed rules (Whale Buy, Block, Bullish Sweep, Breakout, Net Flow)
    tests/               # 11 pytest cases
  services/
    massive.py           # Massive REST client (trades, aggs, last price, daily close)
    stream.py            # Massive WebSocket → MarketEvent → RuleEngine
    alerts.py            # AlertStore (SQLite) · AlertDispatcher (SSE+Discord+DB) · stamper
    rules_store.py       # SQLite rules table · seed builtins · hot-reload helper
    backtest_rules.py    # Historical trade replay → signals + forward returns + Portfolio P&L
    dashboard_store.py   # SQLite cache for prior-day TRF totals (% change column)
    discord.py           # Webhook broadcaster to bot receiver
  core/
    config.py            # pydantic-settings; reads .env; all tunable knobs
  main.py                # FastAPI app + lifespan (engine · dispatcher · streamer · stamper)

frontend/src/
  App.tsx                # 6-tab shell
  TickerDashboard.tsx    # Livestreaming TRF table (SSE → sortable paginated table)
  AlertsFeed.tsx         # Live signal feed (SSE) + history with forward-return columns
  StrategyLab.tsx        # Admin rule builder: conditions, groups, preview, CRUD
  RuleBacktest.tsx       # Rule backtest: portfolio cards + return stats + equity curve
  index.css              # Glassmorphic dark mode stylesheet

backtester/
  engine.py              # Chronological tick-by-tick simulation loop
  portfolio.py           # Position management, trade logs, Sharpe/drawdown metrics
  data.py                # APIDataProvider · CSVDataProvider · MockDataProvider
  strategy.py            # Abstract base Strategy
  strategies.py          # DarkPoolSpikeStrategy, SMACrossStrategy

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
DASHBOARD_UNIVERSE_SIZE=100          # Top-N tickers by prior-day DP dollar volume
DASHBOARD_WS_FEED=delayed            # "realtime" or "delayed" (match your plan tier)
DASHBOARD_SEED_PRIOR_DAY=True        # Backfill % change on boot

# Alerts (defaults shown)
ALERTS_SSE_QUEUE_MAX=1000
ALERTS_DEFAULT_COOLDOWN_S=300        # Per (rule, symbol) cooldown between signals
ALERTS_FORWARD_HORIZONS_MIN=[5,30,1440]  # Horizons stamped on persisted alerts

# Backtest (defaults shown)
BACKTEST_DEFAULT_NOTIONAL=10000      # Notional per signal in rule backtest
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
| `GET` | `/darkpool/summary` | Single-symbol TRF aggregates for a date |
| `GET` | `/darkpool/trades` | Raw TRF tick log for a symbol/date |
| `POST` | `/backtest/run` | Indicator-strategy backtest (equity curve + trade log) |
| `POST` | `/backtest/rules` | Rule-based backtest → `{signals, forward_return_stats, equity_curve, portfolio_metrics}` |
| `GET` | `/alerts/stream` | SSE — live `Signal` events as they fire |
| `GET` | `/alerts/recent` | Most-recent N alerts (default 100) |
| `GET` | `/alerts/history` | Historical alerts with `+5m/+30m/+1d` returns; `?symbol=&rule_name=&limit=` |
| `GET` | `/rules` | List all admin rules |
| `POST` | `/rules` | Create rule + hot-reload engine |
| `PATCH` | `/rules/{id}` | Partial-update rule + hot-reload engine |
| `DELETE` | `/rules/{id}` | Delete rule + hot-reload engine |
| `GET` | `/rules/metrics` | Metric catalog for the builder UI |
| `POST` | `/rules/preview` | Evaluate draft rule against current live `TickerState`s → matched symbols |

---

## 📊 Dashboard columns

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

| Rule | Logic | Severity |
|------|-------|----------|
| **Whale Buy** | Single trade notional ≥ $500k AND side = ask | critical |
| **Block Trade** | `is_block = true` (size ≥ 10 000 shares) | warning |
| **Bullish Sweep** | Ask-side notional in last 5 min ≥ $1M | warning |
| **Price Breakout** | Price move ≥ 1 % in last 10 min | info |
| **Bearish Net Flow** | Net flow notional in last 15 min ≤ −$500k | warning |

Add or modify rules at runtime via `POST /rules` or the Strategy Lab UI — the engine hot-reloads immediately.

---

## 🧪 Running Tests

```bash
source .venv/bin/activate
python3 -m pytest backend/app/rules/tests    # 11 unit tests for the rule engine
```

---

## 📈 Extending with a new strategy (legacy backtester)

Subclass `Strategy` in `backtester/strategies.py` and implement `calculate(df)`:

```python
from backtester import Strategy

class MyStrategy(Strategy):
    def calculate(self, df):
        # compute indicators, return (df_with_indicators, signals_list)
        return df, []
```

Re-export from `backtester/__init__.py` and call via `POST /backtest/run`.

---

## 🔭 Roadmap

See `ROADMAP.md` for the full phase-by-phase tracker. Planned (not yet started):
- **Auth** (`AUTH.md`) — Supabase invite-only gate
- **Deployment** (`DEPLOYMENT.md`) — Fly.io backend + Vercel frontend → `darkpool.davenc.dev`
- **Nightly screener service** — full `services/screener.py` with cron scheduling
- **NBBO quote-join** for exact at-bid/at-ask (v1.1; tick-test sufficient for now)
