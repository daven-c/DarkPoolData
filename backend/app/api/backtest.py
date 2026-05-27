from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from backend.app.core.config import settings
from backtester import (
    BacktestEngine,
    APIDataProvider,
    MockDataProvider,
    DarkPoolSpikeStrategy,
    SMACrossStrategy
)
import traceback

router = APIRouter()

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

