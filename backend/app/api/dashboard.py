import json
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.app.core.config import settings
from backend.app.services.market_status import get_default_cache as get_market_status_cache

router = APIRouter()

SORTABLE_FIELDS = {
    "symbol",
    "total_amount",
    "daily_change_pct",
    "at_ask",
    "at_bid",
    "net_value",
    "dp_trades",
    "block_trades",
}


def _build_rows(request: Request) -> List[Dict[str, Any]]:
    """Build the full dashboard row list from the engine snapshot.

    Each row comes from TickerState.dashboard_row() which already includes
    daily_change_pct (computed from prior_day_total seeded at startup).
    """
    engine = request.app.state.engine
    snap = engine.snapshot()           # {symbol: dashboard_row_dict}
    return list(snap.values())


@router.get("/snapshot")
def get_snapshot(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(settings.DASHBOARD_DEFAULT_LIMIT, ge=1, le=settings.DASHBOARD_MAX_LIMIT),
    sort: str = Query("total_amount"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    if sort not in SORTABLE_FIELDS:
        raise HTTPException(status_code=400, detail=f"sort must be one of {sorted(SORTABLE_FIELDS)}")

    rows = _build_rows(request)
    reverse = order == "desc"
    rows.sort(key=lambda r: (r.get(sort) is None, r.get(sort) or 0), reverse=reverse)

    total = len(rows)
    start = (page - 1) * limit
    end = start + limit
    return {
        "page": page,
        "limit": limit,
        "total": total,
        "rows": rows[start:end],
    }


@router.get("/stream")
async def stream(request: Request):
    engine = request.app.state.engine

    async def event_generator():
        async for row in engine.subscribe():
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(row)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.get("/health")
async def get_health(request: Request):
    """Compact engine-health summary for the Signals Dashboard strip.

    Composed from cheap sources — no new engine counters:
      - tickers_tracked: size of the active WS universe
      - active_tickers:  universe rows that have logged at least one dark trade
      - signals_today / last_signal_ts: from the alert store
      - ws_feed: configured WS feed tier (delayed/realtime)
      - market_status: upstream US-equities market state (cached, TTL in settings)
    """
    engine = request.app.state.engine
    rows = _build_rows(request)
    active = sum(1 for r in rows if (r.get("dp_trades") or 0) > 0)

    health = {"signals_today": 0, "last_signal_ts": None, "total_signals": 0}
    alert_store = getattr(request.app.state, "alert_store", None)
    if alert_store is not None:
        health = alert_store.health()

    ingest = engine.ingestion_stats()
    market = await get_market_status_cache().get()

    # Boot + runtime diagnostics drive the frontend's degraded-state banner.
    # We fold in last_event_ts and market_status so severity classification can
    # account for "live feed silent during market hours" vs. legitimate quiet.
    diagnostics = getattr(request.app.state, "diagnostics", None)
    diag_payload = (
        diagnostics.snapshot(
            last_event_ts=ingest["last_event_ts"],
            market_status=market.get("market"),
        )
        if diagnostics is not None
        else None
    )

    return {
        "tickers_tracked": len(engine.universe()),
        "active_tickers": active,
        "signals_today": health["signals_today"],
        "last_signal_ts": health["last_signal_ts"],
        "total_signals": health["total_signals"],
        "ws_feed": settings.DASHBOARD_WS_FEED,
        # Live ingestion throughput
        "events_per_sec": ingest["events_per_sec"],
        "events_per_min": ingest["events_per_min"],
        "total_events": ingest["total_events"],
        "last_event_ts": ingest["last_event_ts"],
        # Market status (cached upstream)
        "market_status": market.get("market", "unknown"),
        "market_status_checked_at": market.get("checked_at"),
        "market_server_time": market.get("server_time"),
        # Startup + runtime diagnostics for the degraded-state banner
        "diagnostics": diag_payload,
    }


@router.get("/universe")
def get_universe(request: Request):
    engine = request.app.state.engine
    return {"tickers": engine.universe()}


@router.get("/config")
def get_public_config():
    """Tunables that affect frontend behavior."""
    return {
        "default_limit": settings.DASHBOARD_DEFAULT_LIMIT,
        "max_limit": settings.DASHBOARD_MAX_LIMIT,
        "universe_size": settings.DASHBOARD_UNIVERSE_SIZE,
        "block_size_threshold": settings.DASHBOARD_BLOCK_SIZE_THRESHOLD,
        "ws_feed": settings.DASHBOARD_WS_FEED,
    }
