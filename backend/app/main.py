import asyncio
import os
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

# Make `python3 backend/app/main.py` work from the repo root by adding the
# project root to sys.path before the `backend.*` imports resolve.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import backtest, darkpool, dashboard
from backend.app.api import alerts as alerts_api
from backend.app.core.config import settings
from backend.app.rules import RuleEngine, default_rules
from backend.app.services.alerts import AlertDispatcher, AlertStore, forward_return_stamper
from backend.app.services.dashboard_store import DashboardStore
from backend.app.services.discord import discord_notifier
from backend.app.services.massive import MassiveService
from backend.app.services.stream import DashboardStreamer


def _prior_trading_day(today: datetime) -> str:
    d = today - timedelta(days=1)
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _seed_prior_totals(
    massive: MassiveService,
    store: DashboardStore,
    engine: RuleEngine,
    universe: list,
    date_str: str,
) -> None:
    """Fetch prior-day dark-pool totals and seed them into the engine's TickerState."""
    cached = store.get_totals(date_str, universe)
    missing = [t for t in universe if t not in cached]
    for sym, total in cached.items():
        engine.set_prior_total(sym, total)
    if not missing:
        print(f"[dashboard] prior-day totals served from cache for {date_str}", flush=True)
        return
    print(f"[dashboard] seeding {len(missing)} prior-day totals for {date_str}...", flush=True)
    fresh = massive.get_prior_day_dark_totals(missing, date_str)
    if fresh:
        store.upsert_totals(date_str, fresh)
        for sym, total in fresh.items():
            engine.set_prior_total(sym, total)
    print(f"[dashboard] prior-day seed complete ({len(cached) + len(fresh)} tickers)", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    massive = MassiveService()
    store = DashboardStore()
    prior_date = _prior_trading_day(datetime.now())

    try:
        universe = massive.get_top_volume_tickers(prior_date, n=settings.DASHBOARD_UNIVERSE_SIZE)
        print(f"[dashboard] universe ready: {len(universe)} tickers for prior_date={prior_date}", flush=True)
    except Exception as e:
        print(f"[dashboard] universe init failed, falling back to empty: {e}", flush=True)
        universe = []

    # -----------------------------------------------------------------------
    # Central RuleEngine — single source of truth for state + signals
    # -----------------------------------------------------------------------
    engine = RuleEngine(
        rules=default_rules(),
        universe=universe,
        block_threshold=settings.DASHBOARD_BLOCK_SIZE_THRESHOLD,
        sse_queue_max=settings.DASHBOARD_SSE_QUEUE_MAX,
    )
    app.state.engine = engine
    app.state.prior_date = prior_date

    # -----------------------------------------------------------------------
    # Alert pipeline — SSE + Discord + SQLite + forward-return stamper
    # -----------------------------------------------------------------------
    alert_store = AlertStore()
    dispatcher = AlertDispatcher(
        store=alert_store,
        discord=discord_notifier,
        sse_queue_max=settings.ALERTS_SSE_QUEUE_MAX,
        discord_enabled=settings.ALERTS_DISCORD_ENABLED,
    )
    await dispatcher.start()
    app.state.alert_store = alert_store
    app.state.alert_dispatcher = dispatcher

    stamper_task = asyncio.create_task(
        forward_return_stamper(alert_store, massive, settings.ALERTS_FORWARD_HORIZONS_MIN),
        name="forward-return-stamper",
    )

    # -----------------------------------------------------------------------
    # WebSocket streamer — feeds engine; fired signals → dispatcher
    # -----------------------------------------------------------------------
    streamer = None
    if universe and settings.MASSIVE_API_KEY:
        streamer = DashboardStreamer(
            settings.MASSIVE_API_KEY,
            universe,
            engine,
            alert_callback=dispatcher.enqueue,
        )
        streamer.start()
        app.state.streamer = streamer

    # -----------------------------------------------------------------------
    # Prior-day totals (background thread — slow REST call)
    # -----------------------------------------------------------------------
    if settings.DASHBOARD_SEED_PRIOR_DAY and universe:
        threading.Thread(
            target=_seed_prior_totals,
            args=(massive, store, engine, universe, prior_date),
            name="dashboard-seed",
            daemon=True,
        ).start()

    try:
        yield
    finally:
        stamper_task.cancel()
        if streamer is not None:
            streamer.stop()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(darkpool.router, prefix=f"{settings.API_V1_STR}/darkpool", tags=["DarkPool"])
app.include_router(backtest.router, prefix=f"{settings.API_V1_STR}/backtest", tags=["Backtester"])
app.include_router(dashboard.router, prefix=f"{settings.API_V1_STR}/dashboard", tags=["Dashboard"])
app.include_router(alerts_api.router, prefix=f"{settings.API_V1_STR}/alerts", tags=["Alerts"])


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "docs_url": "/docs",
    }


if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
