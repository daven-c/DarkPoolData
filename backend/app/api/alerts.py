"""Alerts API — signal stream, recent alerts, and historical profitability.

Endpoints
---------
GET /alerts/stream      — SSE stream; each event is a JSON-encoded Signal dict
GET /alerts/recent      — last N alerts (newest first)
GET /alerts/history     — filterable history with forward-return columns
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from backend.app.core.config import settings

router = APIRouter()


@router.get("/stream")
async def stream_alerts(request: Request):
    """Server-Sent Events stream. Each `data:` line is a JSON Signal dict."""
    dispatcher = request.app.state.alert_dispatcher

    async def event_generator():
        async for payload_json in dispatcher.subscribe():
            if await request.is_disconnected():
                break
            yield f"data: {payload_json}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.get("/recent")
def get_recent_alerts(
    request: Request,
    limit: int = Query(settings.ALERTS_RECENT_LIMIT, ge=1, le=1000),
):
    """Return the most recent N alerts (newest first)."""
    store = request.app.state.alert_store
    return {"alerts": store.get_recent(limit=limit)}


@router.get("/history")
def get_alert_history(
    request: Request,
    symbol: str = Query(None),
    rule_name: str = Query(None),
    limit: int = Query(500, ge=1, le=5000),
):
    """
    Filterable alert history. Includes forward-return columns once stamped:
    - forward_5m  — % return at T+5min
    - forward_30m — % return at T+30min
    - forward_1d  — % return at T+1 trading day

    Use these to measure signal profitability over time.
    """
    store = request.app.state.alert_store
    rows = store.get_history(symbol=symbol, rule_name=rule_name, limit=limit)
    return {
        "total": len(rows),
        "filters": {"symbol": symbol, "rule_name": rule_name},
        "alerts": rows,
    }
