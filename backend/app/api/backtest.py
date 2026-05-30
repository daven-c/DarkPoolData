import asyncio
import traceback
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.core.config import settings
from backend.app.services.backtest_rules import run_rule_backtest

router = APIRouter()

# ---------------------------------------------------------------------------
# Rule-based backtest endpoint — replays historical TRF trades through the
# platform's live RuleEngine to validate signal quality (forward returns).
# ---------------------------------------------------------------------------

class RuleBacktestRequest(BaseModel):
    symbols: List[str] = Field(default=["AAPL"], description="Tickers to replay (1-5 recommended)")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    rule_ids: Optional[List[str]] = Field(None, description="Rule IDs to use. Omit to run all enabled platform rules.")


@router.post("/rules")
async def run_rules_backtest(req: RuleBacktestRequest, request: Request):
    """
    Replay historical TRF trades through the platform's rule engine.

    Returns signal log, forward-return stats (+5m/+30m/+1d), and a downsampled
    price series per symbol for marking each signal on the price graph.
    """
    rules_store = request.app.state.rules_store
    all_rules = rules_store.as_rules()

    if req.rule_ids:
        rule_map = {r.id: r for r in all_rules}
        rules_to_run = [rule_map[rid] for rid in req.rule_ids if rid in rule_map]
        if not rules_to_run:
            raise HTTPException(status_code=404, detail="None of the specified rule IDs were found")
    else:
        rules_to_run = [r for r in all_rules if r.enabled]

    try:
        result = await asyncio.to_thread(
            run_rule_backtest,
            symbols=req.symbols,
            start_date=req.start_date,
            end_date=req.end_date,
            rules=rules_to_run,
            api_key=settings.MASSIVE_API_KEY,
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}")

    return result
