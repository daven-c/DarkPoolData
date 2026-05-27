# DarkPoolData Platform

An institutional-grade platform to ingest, explore, backtest, and alert on off-exchange (dark pool/TRF) trade data using the **Massive.com** (formerly Polygon.io) market data APIs.

The platform integrates:
- A **livestreaming Ticker Dashboard** powered by the Massive WebSocket feed (TRF trades → per-symbol running totals, AT BID / AT ASK split, block detection).
- A FastAPI backend router with SSE streaming and a SQLite cache for prior-day totals.
- A React + Vite dashboard web app (Recharts + glassmorphic dark mode).
- A custom Python backtesting engine for strategy simulation.
- A Discord gateway announcer for institutional-flow alerts.
- Interactive Marimo notebooks for ad-hoc exploration.

---

## 📂 Project Architecture

```
├── backend/
│   ├── app/
│   │   ├── api/                 # API Router controllers
│   │   │   ├── darkpool.py       # TRF trade details and aggregates (single-symbol scanner)
│   │   │   ├── backtest.py       # Runs historical backtests
│   │   │   └── dashboard.py      # Livestream dashboard: snapshot + SSE stream + universe
│   │   ├── core/
│   │   │   └── config.py         # Configuration variables loader
│   │   ├── services/
│   │   │   ├── massive.py        # Massive REST client (trades, aggs, grouped daily)
│   │   │   ├── aggregator.py     # In-memory running totals + tick-test bid/ask classifier
│   │   │   ├── stream.py         # Massive WebSocket subscriber (T.<ticker>) → aggregator
│   │   │   ├── dashboard_store.py # SQLite cache for prior-day totals (% change column)
│   │   │   └── discord.py        # Broadcaster to bot receiver webhook
│   │   └── main.py              # FastAPI app + lifespan that boots universe/WS/cache
│   └── .env                      # Local API keys and credentials
├── frontend/
│   ├── src/
│   │   ├── App.tsx               # Tab shell + Backtest Engine + Dark Pool Scanner views
│   │   ├── TickerDashboard.tsx   # Livestreaming dashboard (SSE → sortable paginated table)
│   │   ├── index.css             # Premium dark mode glassmorphic stylesheet
│   │   └── main.tsx
│   └── package.json              # Node dependencies (React 19, recharts, lucide-react)
├── backtester/
│   ├── engine.py            # Chronological tick-by-tick simulation loop
│   ├── portfolio.py         # Position management, trade logs, and metrics math
│   ├── data.py              # APIDataProvider, CSVDataProvider, MockDataProvider
│   ├── strategy.py          # Abstract base Strategy class
│   └── strategies.py        # Configurable indicator strategies
├── bot/
│   └── bot.py               # discord.py bot + integrated aiohttp webhook server
├── notebooks/
│   ├── darkpool_exploration.py # Marimo interactive data notebook
│   └── csv_downloader.py        # Marimo utility to download and inspect tick CSVs
└── requirements.txt          # Shared Python dependencies
```

---

## 🛠️ Prerequisites & Environment Setup

Ensure you have **Python 3.10+** and **Node 18+** installed locally.

### 1. Create a Unified Virtual Environment
Since the shared `backtester` code is used by the backend, Discord bot, and notebooks, configure a single virtual environment at the project root:

```bash
# From the project root directory
python3 -m venv .venv
source .venv/bin/activate

# Install shared requirements
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy and fill in your API credentials in the configuration file located at `.env`:

```env
# Massive.com API Key (formerly Polygon.io)
MASSIVE_API_KEY=YOUR_MASSIVE_API_KEY_HERE

# Discord Configuration (Optional)
DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
DISCORD_CHANNEL_ID=YOUR_DISCORD_CHANNEL_ID_HERE

# Dashboard (Optional - defaults shown)
DASHBOARD_UNIVERSE_SIZE=100     # Top-N tickers by prior-day dollar volume
DASHBOARD_WS_FEED=delayed       # "realtime" or "delayed" (your plan tier)
DASHBOARD_SEED_PRIOR_DAY=True   # Backfill % change column on first boot
```

> **Note on data tiers**: the Massive WebSocket has separate URLs for real-time and delayed feeds. If your plan only includes delayed data, keep `DASHBOARD_WS_FEED=delayed` — the backend will otherwise authenticate but receive zero ticks.

---

## 🚀 Running the Services

Activate the virtual environment (`source .venv/bin/activate`) before starting any Python processes.

### Quickstart (Backend + Frontend)

```bash
# Terminal 1 — backend
source .venv/bin/activate
python3 backend/app/main.py

# Terminal 2 — frontend
npm install --prefix frontend     # one-time
npm run dev --prefix frontend
```

Then open **http://localhost:5173**. The **Ticker Dashboard** tab is the default view.

---

### 1. Start the FastAPI Backend Server
The backend handles routing, aggregates TRF metrics from Massive, runs the WebSocket livestream, executes simulations, and triggers alerts.

```bash
python3 backend/app/main.py
```
* The API boots on `http://localhost:8000`.
* On startup, the lifespan hook:
  1. Calls `get_grouped_daily_aggs` for the prior trading day and picks the top-N tickers by dollar volume (configurable, default 100).
  2. Opens a Massive WebSocket connection and subscribes to `T.<ticker>` for that universe.
  3. Kicks off a background thread to backfill prior-day TRF totals into `data/dashboard_cache.db` (powers the **DAILY AMOUNT CHANGE** column).
* Open `http://localhost:8000/docs` for the interactive Swagger documentation.

Key endpoints:
| Endpoint | Purpose |
|---|---|
| `GET /api/v1/dashboard/snapshot` | Paginated, sortable current snapshot of the dashboard universe |
| `GET /api/v1/dashboard/stream` | Server-Sent Events feed of per-trade aggregator deltas |
| `GET /api/v1/dashboard/universe` | Active top-N ticker list |
| `GET /api/v1/darkpool/summary` | Single-symbol TRF aggregates for a given date |
| `GET /api/v1/darkpool/trades` | Raw TRF tick log for a single symbol/date |
| `POST /api/v1/backtest/run` | Run a strategy over historical data |

### 2. Launch the React Web Application
Install the frontend node modules and launch the Vite dev server:

```bash
npm install --prefix frontend
npm run dev --prefix frontend
```
* The glassmorphic dashboard runs at `http://localhost:5173`.
* Three tabs:
  * **Ticker Dashboard** (default) — livestreaming TRF table for the top-N universe with sortable columns, ticker logos, per-row CSV export. Subscribes to `/dashboard/stream` via `EventSource` for live deltas.
  * **Indicator Visualizer** — configure and run a backtesting strategy, view equity curves, push manual alerts to Discord.
  * **Dark Pool Scanner** — single-symbol deep dive: pie chart of lit vs. off-exchange volume, institutional block trade log.

### 3. Start the Discord Alert Bot (Optional)
Starts the bot client and activates its webhook listener:

```bash
python3 bot/bot.py
```
* The bot registers commands (e.g. `!status`, `!ping`) and listens for POST events on `http://localhost:5000/alert` to broadcast trade indicators to your channel.

### 4. Open the Marimo Notebooks
To interactively prototype custom strategies:

```bash
marimo edit notebooks/darkpool_exploration.py
```

To run the utility for downloading trade details to CSV files:

```bash
marimo edit notebooks/csv_downloader.py
```

---

## 📡 Ticker Dashboard internals

The dashboard's columns and how they are computed:

| Column | Source |
|---|---|
| **TOTAL AMOUNT** | Σ (price × size) of all TRF trades today (exchange ID 4) |
| **DAILY AMOUNT CHANGE** | `(today − prior_day) / prior_day × 100` — `prior_day` from SQLite cache at `data/dashboard_cache.db` |
| **AT ASK / AT BID** | Approximated via the Lee-Ready tick test: uptick → at_ask, downtick → at_bid, equal → retain prior side. *No NBBO quote join (v1).* |
| **NET VALUE** | `AT ASK − AT BID` |
| **DP TRADES** | Count of TRF trades |
| **BLOCK TRADES** | Count of TRF trades with `size ≥ 10,000` |

The aggregator runs in-memory inside the FastAPI process. The Massive WebSocket subscriber updates it on every tick and fans out deltas to any open SSE subscribers. State resets on backend restart (today's totals are rebuilt from the live stream as it accumulates).

## 📈 Backtesting Custom Strategies

You can create plug-and-play strategies by subclassing `Strategy` (in `backtester/strategy.py`) and implementing the `on_data` method:

```python
from backtester import Strategy

class MyStrategy(Strategy):
    def on_data(self, current_time, data, portfolio):
        # Fetch indicators
        # Trigger portfolio.buy(symbol, qty, price, current_time) 
        # or portfolio.sell(symbol, qty, price, current_time)
        pass
```

When calling the `/api/v1/backtest/run` endpoint, if the Massive.com API key is not configured, the engine will fallback to the `MockDataProvider` to simulate market environments so you can test integrations instantly.
