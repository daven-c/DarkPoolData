import json
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.app.core.config import settings

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
