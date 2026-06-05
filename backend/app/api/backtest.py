import asyncio
import traceback
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.app.core.config import settings
from backend.app.services.backtest_rules import run_rule_backtest
from backend.app.services.trading_calendar import has_trading_day_between, is_trading_day

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
    # Input validation — surface obvious user errors as 400 instead of returning
    # a misleading 200 with zero signals (which looks identical to "rule never fired").
    symbols = [s.strip().upper() for s in req.symbols if s and s.strip()]
    if not symbols:
        raise HTTPException(status_code=400, detail="At least one symbol is required.")

    try:
        if not has_trading_day_between(req.start_date, req.end_date):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No US trading days fall between {req.start_date} and {req.end_date}. "
                    "Pick a range that overlaps at least one weekday non-holiday."
                ),
            )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date format (expected YYYY-MM-DD): {exc}")

    rules_store = request.app.state.rules_store
    all_rules = rules_store.as_rules()

    if req.rule_ids:
        rule_map = {r.id: r for r in all_rules}
        rules_to_run = [rule_map[rid] for rid in req.rule_ids if rid in rule_map]
        missing = [rid for rid in req.rule_ids if rid not in rule_map]
        if not rules_to_run:
            raise HTTPException(status_code=404, detail="None of the specified rule IDs were found.")
        # Tell the caller about partial drops so they know not all rules ran.
        if missing:
            print(f"[backtest] dropped {len(missing)} unknown rule_ids: {missing}", flush=True)
    else:
        rules_to_run = [r for r in all_rules if r.enabled]
        if not rules_to_run:
            raise HTTPException(status_code=400, detail="No enabled rules to backtest. Enable at least one rule first.")

    # Flag (but don't reject) when the user picked a non-trading start date —
    # the backtester will still run on the in-range trading days.
    start_warning = None
    if not is_trading_day(req.start_date):
        start_warning = f"{req.start_date} is not a trading day; backtest will start on the next trading day in range."

    try:
        result = await asyncio.to_thread(
            run_rule_backtest,
            symbols=symbols,
            start_date=req.start_date,
            end_date=req.end_date,
            rules=rules_to_run,
            api_key=settings.MASSIVE_API_KEY,
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}")

    if start_warning:
        result["warning"] = start_warning
    return result
