from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from backend.app.core.config import settings
from backtester import (
    BacktestEngine,
    Portfolio,
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
    initial_cash: float = Field(100000.0, description="Starting cash balance")

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
    # Fall back to MockDataProvider if the API key is not set or is empty.
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

    portfolio = Portfolio(initial_cash=req.initial_cash)
    engine = BacktestEngine(data_provider=data_provider, strategy=strategy, portfolio=portfolio)

    try:
        results = engine.run()
        
        # Serialize timestamps for response compatibility
        trades_serializable = []
        for t in portfolio.trades:
            t_copy = t.copy()
            # Convert pd.Timestamp to ISO format string
            t_copy["timestamp"] = t["timestamp"].isoformat()
            trades_serializable.append(t_copy)
            
        equity_serializable = []
        for eq in portfolio.equity_history:
            eq_copy = eq.copy()
            eq_copy["timestamp"] = eq["timestamp"].isoformat()
            equity_serializable.append(eq_copy)

        return {
            "success": True,
            "data_source": data_source_msg,
            "metrics": results,
            "trades": trades_serializable,
            "equity_history": equity_serializable
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Backtest execution failed: {str(e)}\n{traceback.format_exc()}"
        )
