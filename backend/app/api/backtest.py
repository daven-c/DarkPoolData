import asyncio
import traceback
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Body, Request
from pydantic import BaseModel, Field

from backend.app.core.config import settings
from backend.app.services.backtest_rules import run_rule_backtest
from backtester import (
    BacktestEngine,
    APIDataProvider,
    MockDataProvider,
    DarkPoolSpikeStrategy,
    SMACrossStrategy,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Rule-based backtest endpoint (Phase 5)
# ---------------------------------------------------------------------------

class RuleBacktestRequest(BaseModel):
    symbols: List[str] = Field(default=["AAPL"], description="Tickers to replay (1-5 recommended)")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    rule_ids: Optional[List[str]] = Field(None, description="Rule IDs to use. Omit to run all enabled platform rules.")
    notional_per_signal: float = Field(default=settings.BACKTEST_DEFAULT_NOTIONAL, description="Dollar notional per BUY order")
    exit_after_min: float = Field(default=30.0, description="Minutes to hold before time-based exit")


@router.post("/rules")
async def run_rules_backtest(req: RuleBacktestRequest, request: Request):
    """
    Replay historical TRF trades through the platform's rule engine.

    Returns signal log, forward-return stats (+5m/+30m/+1d), equity curve,
    and portfolio metrics (Sharpe, max drawdown, win rate).
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
            notional_per_signal=req.notional_per_signal,
            exit_after_min=req.exit_after_min,
        )
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}")

    return result


# ---------------------------------------------------------------------------
# Legacy indicator-visualizer backtest (unchanged)
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    symbols: List[str] = Field(default=["AAPL"], description="List of symbols to backtest")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    strategy_name: str = Field("dark_pool_spike", description="Either 'dark_pool_spike' or 'sma_cross'")
    strategy_params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for the strategy")
    initial_cash: float = Field(100000.0, description="Starting cash balance (ignored)")

@router.post("/run")
def run_backtest(req: BacktestRequest = Body(...)):
    # Initialize strategy
    if req.strategy_name == "dark_pool_spike":
        strategy = DarkPoolSpikeStrategy(req.strategy_params)
    elif req.strategy_name == "sma_cross":
        strategy = SMACrossStrategy(req.strategy_params)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown strategy name: {req.strategy_name}")

    # Set up data provider.
    api_key_set = bool(settings.MASSIVE_API_KEY and not settings.MASSIVE_API_KEY.startswith("YOUR_"))
    
    if api_key_set:
        data_provider = APIDataProvider(
            api_key=settings.MASSIVE_API_KEY,
            symbols=req.symbols,
            start_date=req.start_date,
            end_date=req.end_date,
            mode="trades" if req.strategy_name == "dark_pool_spike" else "aggs"
        )
        data_source_msg = "Massive.com API"
    else:
        data_provider = MockDataProvider(
            symbols=req.symbols,
            start_date=req.start_date,
            end_date=req.end_date
        )
        data_source_msg = "Mock Data (API key not configured)"

    symbol = req.symbols[0] if req.symbols else "AAPL"
    engine = BacktestEngine(data_provider=data_provider, strategy=strategy, symbol=symbol)

    try:
        results = engine.run()
        return {
            "success": True,
            "data_source": data_source_msg,
            "symbol": symbol,
            "metrics": results["metrics"],
            "series": results["series"],
            "signals": results["signals"]
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Indicator calculation failed: {str(e)}\n{traceback.format_exc()}"
        )

