# AGENTS.md

Canonical guide for AI agents (Claude Code et al.) working in this repo. (Formerly `CLAUDE.md`.) See `README.md` for human-facing setup and usage docs, and **`ROADMAP.md` for the live, checkbox-tracked status of the in-progress redesign** — always read ROADMAP.md first so you can resume mid-flight work.

## Project overview

DarkPoolData is a platform for ingesting, exploring, backtesting, and alerting on off-exchange (TRF/dark pool) trade data sourced from the Massive.com (formerly Polygon.io) APIs. It is composed of cooperating pieces that share a Python package and a single `.env`:

- **`backend/`** — FastAPI service (entry: `backend/app/main.py`) exposing `/api/v1/darkpool/*`, `/api/v1/backtest/*`, `/api/v1/dashboard/*`, and (in the redesign) `/api/v1/alerts/*` and `/api/v1/rules/*`. Configuration is loaded by `backend/app/core/config.py` (pydantic-settings, reads `.env`, `backend/.env`, or `../.env`).
- **`backend/app/rules/`** *(redesign)* — the platform's core: a `RuleEngine` that evaluates composable `Condition` trees against a stream of `MarketEvent`s, producing `Signal`s. The **same engine runs live** (WS stream → alerts) **and in backtest** (historical replay → signal-quality + Portfolio P&L). This is the load-bearing abstraction; see ROADMAP.md Part A.
- **`backtester/`** — Pure-Python simulation library imported by the backend, the Discord bot, and the notebooks. Public surface is re-exported from `backtester/__init__.py`: `Strategy`, `Portfolio`, `DataProvider`, `CSVDataProvider`, `APIDataProvider`, `MockDataProvider`, `BacktestEngine`, `DarkPoolSpikeStrategy`, `SMACrossStrategy`. NOTE: `Portfolio` was historically orphaned (the legacy `BacktestEngine` never used it); the redesign wires it into rule-based P&L backtesting.
- **`bot/bot.py`** — `discord.py` client with an embedded `aiohttp` webhook server on port `5000` (`POST /alert`) that the backend pushes alerts to.
- **`frontend/`** — React 19 + Vite + TypeScript SPA. `src/App.tsx` is the tab shell; tabs include Ticker Dashboard, Alerts feed, Strategy Lab, Rule Backtest, Indicator Visualizer, Scanner.
- **`notebooks/`** — Marimo notebooks (`darkpool_exploration.py`, `csv_downloader.py`) for ad-hoc analysis. Reuse `backtester` rather than duplicating logic.

## Conventions

- **One venv at the repo root** (`.venv/`). The backend, bot, and notebooks all import from `backtester/`, so they must run with the project root on `sys.path`. Run Python entry points from the repo root (e.g. `python3 backend/app/main.py`, not from inside `backend/`).
- **Imports are absolute from the repo root**, e.g. `from backend.app.core.config import settings`, `from backtester import Strategy`. Match this when adding new modules.
- **Secrets live only in `.env`** (gitignored). Never hardcode the Massive API key or Discord token. Add new config keys to `Settings` in `backend/app/core/config.py` so they have defaults and type-checking.
- **CSV/parquet/sqlite files are gitignored** — they are local data artifacts, not source. Don't commit them.
- **Python SDK is `massive`** (renamed from `polygon-api-client` on 2025-10-30 when Polygon.io rebranded). Import as `from massive import RESTClient, WebSocketClient` and `from massive.websocket.models import Feed, Market`. The upstream rename was a drop-in: methods, models, enums, and `T.<ticker>` subscription strings are unchanged.

## Adding a new backtest strategy

Subclass `Strategy` in `backtester/strategies.py` (or a new file in that package) and implement `calculate(df) -> (df_with_indicators, signals_list)`. Re-export it from `backtester/__init__.py` if it should be importable as `from backtester import …`. The engine in `backtester/engine.py` drives it.

## Running things

See the README for full commands. Quick reference:

- Backend: `python3 backend/app/main.py` → `http://localhost:8000` (`/docs` for Swagger)
- Frontend: `npm run dev --prefix frontend` → `http://localhost:5173`
- Bot: `python3 bot/bot.py` (webhook on `:5000`)
- Notebooks: `marimo edit notebooks/<file>.py`

If `MASSIVE_API_KEY` is unset, the backtest engine falls back to `MockDataProvider`, so backend/backtest endpoints work without credentials.

## API endpoint reference (`/api/v1/…`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/dashboard/snapshot` | Paginated, sortable current state of the WS universe (reads `engine.snapshot()`) |
| `GET` | `/dashboard/stream` | SSE feed of per-trade `TickerState` deltas (subscribes to `engine.subscribe()`) |
| `GET` | `/dashboard/universe` | Active top-N ticker list |
| `GET` | `/darkpool/summary` | Single-symbol TRF aggregates for a date |
| `GET` | `/darkpool/trades` | Raw TRF tick log for a symbol/date |
| `POST` | `/backtest/run` | Legacy indicator-strategy backtest (Recharts equity curve) |
| `POST` | `/backtest/rules` | Rule-based backtest: forward-return stats + Portfolio P&L + equity curve |
| `GET` | `/alerts/stream` | SSE fan-out of live `Signal` events |
| `GET` | `/alerts/recent` | Most-recent N alerts (default 100) |
| `GET` | `/alerts/history` | Historical alerts with stamped `+5m/+30m/+1d` returns; filter by `symbol`, `rule_name`, `limit` |
| `GET` | `/rules` | List all admin-defined rules |
| `POST` | `/rules` | Create a rule + hot-reload engine |
| `PATCH` | `/rules/{id}` | Partial-update a rule + hot-reload engine |
| `DELETE` | `/rules/{id}` | Delete a rule + hot-reload engine |
| `GET` | `/rules/metrics` | Metric catalog for the Strategy Lab builder UI |
| `POST` | `/rules/preview` | Evaluate a draft rule against current `TickerState`s → matched symbols |

## Rule engine (`backend/app/rules/`)

The core abstraction for the redesign. Key files:

| File | Contents |
|------|---------|
| `events.py` | `MarketEvent` (trade event DTO), `TickerState` (per-symbol running totals, Lee-Ready tick test, session OHLC, recent-trades deque) |
| `metrics.py` | 12-metric catalog (`trade_notional`, `side`, `is_block`, `net_flow_notional`, `block_count`, `price_move_pct(w)`, etc.); `METRICS` registry + `catalog()` |
| `conditions.py` | `Leaf` (metric ▸ cmp ▸ value ▸ window_s) + `Composite` (AND/OR/NOT); `compile_condition()`, `evaluate()`, `validate_logic()` |
| `index.py` | `RuleIndex`: 1D index utilizing sorted lists + binary search (`bisect`) for range inequalities and Hash Maps for equality; includes 2-decimal rounding leaf deduplication. |
| `evaluator.py` | `compile_evaluator()` + `EvalNode` tree subclasses; flattens condition trees for fast boolean short-circuit evaluation. |
| `rule.py` | `Rule` (id, name, enabled, severity, side_label, kind, cooldown_s, logic) + `Signal`; JSON round-trip |
| `engine.py` | `RuleEngine`: per-ticker `TickerState` + active rules; `process(event)` utilizing eager metric caching and indexed evaluation; `set_rules()` (hot-reload); `snapshot()` (dashboard feed); `preview()` (match current state without mutating); SSE `subscribe()` async generator |
| `builtins.py` | 5 seed rules: Whale Buy, Block Trade, Bullish Sweep, Price Breakout, Bearish Net Flow |
| `tests/` | 15 pytest cases (test_engine.py and test_optimized_engine.py) — run with `python3 -m pytest backend/app/rules/tests` |

**Multi-Tenant Engine Principle**: The rule engine utilizes dynamic condition indexing (sorted threshold search trees) and leaf condition deduplication to scale rule evaluations. Processing time for 1,000 active user rules is under **0.6ms** per market event, making multi-tenant custom user alerts highly scalable.

## Notes for edits

- The shared package layout is load-bearing — moving `backtester/` or renaming its public symbols breaks all four consumers at once. Update the re-exports in `backtester/__init__.py` and the README architecture diagram together with any such change.
- CORS in `backend/app/main.py` is intentionally permissive (`allow_origins=["*"]`) for local development. Don't tighten it without confirming the deployment story.
- When adding a new metric to `metrics.py`, also add a test case in `backend/app/rules/tests/` and verify the metric appears in `GET /rules/metrics`.
