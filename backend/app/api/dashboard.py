import asyncio
import json
from typing import Any, Dict, List, Optional

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
    aggregator = request.app.state.aggregator
    prior_totals: Dict[str, float] = request.app.state.prior_totals
    snap = aggregator.snapshot()
    rows: List[Dict[str, Any]] = []
    for symbol, stats in snap.items():
        total = stats["total_amount"]
        prior = prior_totals.get(symbol, 0.0)
        if prior > 0:
            change_pct = (total - prior) / prior * 100.0
        else:
            change_pct = None
        rows.append({
            "symbol": symbol,
            "total_amount": total,
            "daily_change_pct": change_pct,
            "at_ask": stats["at_ask"],
            "at_bid": stats["at_bid"],
            "net_value": stats["at_ask"] - stats["at_bid"],
            "dp_trades": stats["dp_trades"],
            "block_trades": stats["block_trades"],
        })
    return rows


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
    aggregator = request.app.state.aggregator
    prior_totals: Dict[str, float] = request.app.state.prior_totals

    async def event_generator():
        async for row in aggregator.subscribe():
            if await request.is_disconnected():
                break
            symbol = row["symbol"]
            prior = prior_totals.get(symbol, 0.0)
            change_pct = (row["total_amount"] - prior) / prior * 100.0 if prior > 0 else None
            payload = {
                "symbol": symbol,
                "total_amount": row["total_amount"],
                "daily_change_pct": change_pct,
                "at_ask": row["at_ask"],
                "at_bid": row["at_bid"],
                "net_value": row["at_ask"] - row["at_bid"],
                "dp_trades": row["dp_trades"],
                "block_trades": row["block_trades"],
            }
            yield f"data: {json.dumps(payload)}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.get("/universe")
def get_universe(request: Request):
    aggregator = request.app.state.aggregator
    return {"tickers": aggregator.universe}


@router.get("/config")
def get_public_config():
    """Tunables that affect frontend behavior. Lets the React app match server limits
    instead of hardcoding them."""
    return {
        "default_limit": settings.DASHBOARD_DEFAULT_LIMIT,
        "max_limit": settings.DASHBOARD_MAX_LIMIT,
        "universe_size": settings.DASHBOARD_UNIVERSE_SIZE,
        "block_size_threshold": settings.DASHBOARD_BLOCK_SIZE_THRESHOLD,
        "ws_feed": settings.DASHBOARD_WS_FEED,
    }
