from polygon import RESTClient
from backend.app.core.config import settings
from typing import List, Dict, Any, Optional
import pandas as pd
from datetime import datetime, date as dt_date

class MassiveService:
    def __init__(self, api_key: Optional[str] = None):
        """
        Service to interact with Massive.com (Polygon.io) APIs.
        """
        self.api_key = api_key or settings.MASSIVE_API_KEY
        # If API key is empty/placeholder, RESTClient will raise an error on calls
        self.client = RESTClient(api_key=self.api_key) if self.api_key else None

    def _get_client(self) -> RESTClient:
        if not self.client:
            raise ValueError("Massive.com API key is not configured. Please add MASSIVE_API_KEY to your .env file.")
        return self.client

    def get_darkpool_trades(self, ticker: str, date_str: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Retrieves detailed individual trades from off-exchange Trade Reporting Facilities (TRFs).
        
        :param ticker: Stock ticker (e.g., AAPL).
        :param date_str: Target date in format YYYY-MM-DD.
        :param limit: Maximum number of records to return.
        """
        client = self._get_client()
        trades = []
        try:
            # Query trades within the day boundary
            results = client.list_trades(
                ticker=ticker,
                timestamp_gte=f"{date_str}T00:00:00Z",
                timestamp_lte=f"{date_str}T23:59:59Z",
                limit=50000
            )
            
            for t in results:
                # Exchange 4 represents FINRA TRFs (off-exchange)
                if t.exchange == 4:
                    ts_ns = getattr(t, "participant_timestamp", getattr(t, "sip_timestamp", 0))
                    # Convert to datetime string
                    ts = pd.to_datetime(ts_ns, unit="ns", utc=True).tz_convert("US/Eastern").strftime("%Y-%m-%d %H:%M:%S.%f")
                    
                    trades.append({
                        "timestamp": ts,
                        "price": t.price,
                        "size": t.size,
                        "conditions": getattr(t, "conditions", []),
                        "trf_id": getattr(t, "trf_id", None)
                    })
                    if len(trades) >= limit:
                        break
        except Exception as e:
            print(f"Error fetching trades for {ticker} on {date_str}: {e}")
            raise e
            
        return trades

    def get_dark_pool_summary(self, ticker: str, date_str: str) -> Dict[str, Any]:
        """
        Aggregates lit exchange trade volume and off-exchange dark pool volume to construct
        an institutional block activity report.
        
        :param ticker: Stock ticker (e.g., AAPL).
        :param date_str: Target date in format YYYY-MM-DD.
        """
        client = self._get_client()
        
        total_volume = 0.0
        dark_volume = 0.0
        total_trades_count = 0
        dark_trades_count = 0
        dark_prices = []
        block_trades = []  # Trades > 10,000 shares
        
        try:
            results = client.list_trades(
                ticker=ticker,
                timestamp_gte=f"{date_str}T00:00:00Z",
                timestamp_lte=f"{date_str}T23:59:59Z",
                limit=50000
            )
            
            for t in results:
                total_volume += t.size
                total_trades_count += 1
                
                # Check for off-exchange (exchange ID 4)
                if t.exchange == 4:
                    dark_volume += t.size
                    dark_trades_count += 1
                    dark_prices.append(t.price)
                    
                    # Track large block sizes
                    if t.size >= 5000:  # Custom threshold for institutional scale
                        ts_ns = getattr(t, "participant_timestamp", getattr(t, "sip_timestamp", 0))
                        ts_str = pd.to_datetime(ts_ns, unit="ns", utc=True).tz_convert("US/Eastern").strftime("%H:%M:%S")
                        block_trades.append({
                            "time": ts_str,
                            "price": t.price,
                            "size": t.size,
                            "value": t.price * t.size
                        })
                        
        except Exception as e:
            print(f"Error running darkpool aggregation for {ticker} on {date_str}: {e}")
            raise e
            
        dark_ratio = (dark_volume / total_volume) if total_volume > 0 else 0.0
        avg_dark_price = sum(dark_prices) / len(dark_prices) if dark_prices else 0.0
        
        # Sort block trades by value descending
        block_trades.sort(key=lambda x: x["value"], reverse=True)
        
        return {
            "symbol": ticker,
            "date": date_str,
            "total_volume": total_volume,
            "dark_volume": dark_volume,
            "dark_ratio": dark_ratio,
            "total_trades": total_trades_count,
            "dark_trades": dark_trades_count,
            "avg_dark_price": avg_dark_price,
            "large_block_trades": block_trades[:20]  # Return top 20 blocks
        }

    def get_daily_aggs(self, ticker: str, from_date: str, to_date: str) -> List[Dict[str, Any]]:
        """
        Fetches general daily bars.
        """
        client = self._get_client()
        bars = []
        try:
            results = client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="day",
                from_=from_date,
                to=to_date
            )
            for b in results:
                ts = pd.to_datetime(b.timestamp, unit="ms", utc=True).tz_convert("US/Eastern").strftime("%Y-%m-%d")
                bars.append({
                    "date": ts,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                    "vwap": b.vwap
                })
        except Exception as e:
            print(f"Error loading aggs for {ticker}: {e}")
            raise e
        return bars
