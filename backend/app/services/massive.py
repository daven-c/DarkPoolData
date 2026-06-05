from massive import RESTClient
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

    def get_top_volume_tickers(self, date_str: str, n: int = 100) -> List[str]:
        """
        Returns the top-N tickers ranked by dollar-volume (close * volume) for the given date,
        using Massive's grouped daily aggs (single REST call for all US stocks).
        """
        client = self._get_client()
        try:
            results = client.get_grouped_daily_aggs(date=date_str, adjusted=True)
        except Exception as e:
            print(f"Error fetching grouped daily aggs for {date_str}: {e}")
            raise e

        ranked = []
        for r in results:
            ticker = getattr(r, "ticker", None)
            close = getattr(r, "close", None)
            volume = getattr(r, "volume", None)
            if not ticker or close is None or volume is None:
                continue
            if "." in ticker or "/" in ticker:
                continue  # skip preferred shares, warrants, etc.
            ranked.append((ticker, close * volume))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return [t for t, _ in ranked[:n]]

    def get_prior_day_dark_totals(self, tickers: List[str], date_str: str) -> Dict[str, float]:
        """
        For each ticker, computes total dollar amount of TRF (off-exchange) trades on date_str.
        Used to seed DAILY AMOUNT CHANGE. Hits list_trades per ticker so this is the slow path
        and should only be run once at startup.
        """
        client = self._get_client()
        out: Dict[str, float] = {}
        for ticker in tickers:
            total = 0.0
            try:
                for t in client.list_trades(
                    ticker=ticker,
                    timestamp_gte=f"{date_str}T00:00:00Z",
                    timestamp_lte=f"{date_str}T23:59:59Z",
                    limit=50000,
                ):
                    if getattr(t, "exchange", None) == 4:
                        total += float(t.price) * float(t.size)
            except Exception as e:
                print(f"Error fetching prior-day TRF totals for {ticker}: {e}")
                continue
            out[ticker] = total
        return out

    def get_last_price(self, ticker: str) -> Optional[float]:
        """Return the most recent trade price for a ticker (for forward-return stamping).

        Returns None (rather than raising) when no API key is configured, so the
        forward-return stamper stays quiet during off-hours simulation runs.
        """
        try:
            client = self._get_client()
            result = client.get_last_trade(ticker)
            r = getattr(result, "results", None)
            if r is None:
                return None
            return float(getattr(r, "price", getattr(r, "p", None)))
        except Exception as e:
            print(f"[MassiveService] get_last_price({ticker}) failed: {e}")
            return None

    def get_close_on_date(self, ticker: str, date_str: str) -> Optional[float]:
        """Return closing price for a ticker on a specific date (for +1d stamping).

        Returns None (rather than raising) when no API key is configured.
        """
        try:
            client = self._get_client()
            bars = list(client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="day",
                from_=date_str,
                to=date_str,
                limit=1,
            ))
            if bars:
                return float(bars[0].close)
        except Exception as e:
            print(f"[MassiveService] get_close_on_date({ticker}, {date_str}) failed: {e}")
        return None

    def get_market_status(self) -> Dict[str, Any]:
        """Return the upstream market-status snapshot.

        Shape: {market, server_time, exchanges, currencies}. `market` is one of
        "open" | "closed" | "extended-hours" (per Polygon's /v1/marketstatus/now).
        Returns {"market": "unknown", ...} when the SDK call fails so callers
        don't have to handle exceptions.
        """
        client = self._get_client()
        try:
            result = client.get_market_status()
        except Exception as e:
            print(f"[MassiveService] get_market_status failed: {e}")
            return {"market": "unknown", "server_time": None, "exchanges": {}, "currencies": {}}

        def _to_dict(obj: Any) -> Any:
            if obj is None or isinstance(obj, (str, int, float, bool)):
                return obj
            if isinstance(obj, dict):
                return {k: _to_dict(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_to_dict(v) for v in obj]
            if hasattr(obj, "__dict__"):
                return {k: _to_dict(v) for k, v in vars(obj).items() if not k.startswith("_")}
            return str(obj)

        data = _to_dict(result) if not isinstance(result, dict) else result
        return {
            "market": data.get("market", "unknown"),
            "server_time": data.get("server_time") or data.get("serverTime"),
            "exchanges": data.get("exchanges") or {},
            "currencies": data.get("currencies") or {},
            "early_hours": data.get("early_hours", data.get("earlyHours")),
            "after_hours": data.get("after_hours", data.get("afterHours")),
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
