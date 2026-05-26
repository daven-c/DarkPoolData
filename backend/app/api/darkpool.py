from fastapi import APIRouter, Query, HTTPException, Depends
from backend.app.services.massive import MassiveService
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

router = APIRouter()

# Dependency to get MassiveService
def get_massive_service():
    return MassiveService()

@router.get("/summary")
def get_summary(
    symbol: str = Query(..., description="Stock ticker (e.g. AAPL)"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (defaults to yesterday)")
, service: MassiveService = Depends(get_massive_service)):
    if not date:
        # Default to yesterday
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
    try:
        data = service.get_dark_pool_summary(symbol, date)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch dark pool summary: {str(e)}")

@router.get("/trades")
def get_trades(
    symbol: str = Query(..., description="Stock ticker (e.g. AAPL)"),
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (defaults to yesterday)"),
    limit: int = Query(100, description="Max trades to retrieve")
, service: MassiveService = Depends(get_massive_service)):
    if not date:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
    try:
        data = service.get_darkpool_trades(symbol, date, limit)
        return {"symbol": symbol, "date": date, "trades": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch dark pool trades: {str(e)}")
