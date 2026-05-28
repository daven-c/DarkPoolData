# CLAUDE.md

Guidance for Claude Code when working in this repo. See `README.md` for human-facing setup and usage docs.

## Project overview

DarkPoolData is a platform for ingesting, exploring, backtesting, and alerting on off-exchange (TRF/dark pool) trade data sourced from the Massive.com (formerly Polygon.io) APIs. It is composed of four cooperating pieces that share a Python package and a single `.env`:

- **`backend/`** — FastAPI service (entry: `backend/app/main.py`) exposing `/api/v1/darkpool/*` and `/api/v1/backtest/*`. Configuration is loaded by `backend/app/core/config.py` (pydantic-settings, reads `.env`, `backend/.env`, or `../.env`).
- **`backtester/`** — Pure-Python simulation library imported by the backend, the Discord bot, and the notebooks. Public surface is re-exported from `backtester/__init__.py`: `Strategy`, `Portfolio`, `DataProvider`, `CSVDataProvider`, `APIDataProvider`, `MockDataProvider`, `BacktestEngine`, `DarkPoolSpikeStrategy`, `SMACrossStrategy`.
- **`bot/bot.py`** — `discord.py` client with an embedded `aiohttp` webhook server on port `5000` (`POST /alert`) that the backend pushes alerts to.
- **`frontend/`** — React 19 + Vite + TypeScript SPA. `src/App.tsx` is the single-page dashboard (Backtest Engine and Dark Pool Scanner tabs).
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

## Notes for edits

- The shared package layout is load-bearing — moving `backtester/` or renaming its public symbols breaks all four consumers at once. Update the re-exports in `backtester/__init__.py` and the README architecture diagram together with any such change.
- CORS in `backend/app/main.py` is intentionally permissive (`allow_origins=["*"]`) for local development. Don't tighten it without confirming the deployment story.
