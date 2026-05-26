from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any, List, Generator, Optional
from polygon import RESTClient  # Massive client library uses 'polygon' namespaces as fallback or direct import

class DataProvider(ABC):
    @abstractmethod
    def get_data(self) -> Generator[Dict[str, Any], None, None]:
        """
        Yields market events chronologically.
        Each yield is a dictionary representing the market state at a specific timestamp:
        {
            "timestamp": pd.Timestamp,
            "prices": Dict[str, float],      # Ticker -> current market price
            "indicators": Dict[str, Any]    # Ticker -> data payload (bars/trades/darkpool status)
        }
        """
        pass


class CSVDataProvider(DataProvider):
    def __init__(self, csv_filepath: str, symbol: str):
        """
        Loads data from a local CSV file.
        CSV columns expected: timestamp, price, volume, is_dark_pool (optional), size (optional)
        
        :param csv_filepath: Path to the CSV file.
        :param symbol: Ticker symbol the data belongs to.
        """
        self.csv_filepath = csv_filepath
        self.symbol = symbol
        self.df = pd.read_csv(csv_filepath)
        self.df["timestamp"] = pd.to_datetime(self.df["timestamp"])
        self.df.sort_values("timestamp", inplace=True)

    def get_data(self) -> Generator[Dict[str, Any], None, None]:
        for _, row in self.df.iterrows():
            timestamp = row["timestamp"]
            price = float(row["price"])
            
            # Additional indicators (e.g. block size, dark pool flags)
            indicators = {
                "price": price,
                "volume": float(row.get("volume", 0)),
                "is_dark_pool": bool(row.get("is_dark_pool", False)),
                "size": float(row.get("size", 0))
            }
            
            yield {
                "timestamp": timestamp,
                "prices": {self.symbol: price},
                "indicators": {self.symbol: indicators}
            }


class APIDataProvider(DataProvider):
    def __init__(self, api_key: str, symbols: List[str], start_date: str, end_date: str, mode: str = "aggs"):
        """
        Fetches data chronologically using the Massive.com REST API.
        
        :param api_key: Massive.com (Polygon) API key.
        :param symbols: List of symbols to fetch.
        :param start_date: Start date string (YYYY-MM-DD).
        :param end_date: End date string (YYYY-MM-DD).
        :param mode: "aggs" (aggregate bars) or "trades" (individual ticks, including TRF dark pools).
        """
        self.client = RESTClient(api_key=api_key)
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.mode = mode

    def get_data(self) -> Generator[Dict[str, Any], None, None]:
        # Fetch data for all symbols and align chronologically
        events = []
        
        for symbol in self.symbols:
            if self.mode == "aggs":
                # Fetch daily/minute bars
                try:
                    aggs = self.client.list_aggs(
                        ticker=symbol,
                        multiplier=1,
                        timespan="day",
                        from_=self.start_date,
                        to=self.end_date
                    )
                    for bar in aggs:
                        # bar.timestamp is Unix millisecond timestamp
                        ts = pd.to_datetime(bar.timestamp, unit="ms", utc=True).tz_convert("US/Eastern")
                        events.append({
                            "timestamp": ts,
                            "symbol": symbol,
                            "price": bar.close,
                            "indicators": {
                                "open": bar.open,
                                "high": bar.high,
                                "low": bar.low,
                                "close": bar.close,
                                "volume": bar.volume,
                                "vwap": bar.vwap
                            }
                        })
                except Exception as e:
                    print(f"Error fetching aggs for {symbol}: {e}")
                    
            elif self.mode == "trades":
                # Fetch tick-by-tick trades (includes dark pool TRF execution)
                try:
                    # Note: list_trades queries using ISO date strings or nanoseconds
                    trades = self.client.list_trades(
                        ticker=symbol,
                        timestamp_gte=self.start_date,
                        timestamp_lte=self.end_date,
                        limit=50000
                    )
                    for trade in trades:
                        # trade.sip_timestamp or trade.participant_timestamp in nanoseconds
                        ts = pd.to_datetime(trade.participant_timestamp, unit="ns", utc=True).tz_convert("US/Eastern")
                        
                        # exchange=4 represents FINRA TRF (Trade Reporting Facility, off-exchange/dark pool)
                        is_dark_pool = (trade.exchange == 4)
                        
                        events.append({
                            "timestamp": ts,
                            "symbol": symbol,
                            "price": trade.price,
                            "indicators": {
                                "price": trade.price,
                                "size": trade.size,
                                "is_dark_pool": is_dark_pool,
                                "trf_id": getattr(trade, "trf_id", None),
                                "conditions": getattr(trade, "conditions", [])
                            }
                        })
                except Exception as e:
                    print(f"Error fetching trades for {symbol}: {e}")
                    
        # Sort all combined events chronologically
        events.sort(key=lambda x: x["timestamp"])
        
        # Stream aligned events
        for event in events:
            yield {
                "timestamp": event["timestamp"],
                "prices": {event["symbol"]: event["price"]},
                "indicators": {event["symbol"]: event["indicators"]}
            }


class MockDataProvider(DataProvider):
    def __init__(self, symbols: List[str], start_date: str, end_date: str):
        """
        Generates mock market bars and dark pool statistics. Useful for tests.
        """
        self.symbols = symbols
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)

    def get_data(self) -> Generator[Dict[str, Any], None, None]:
        import random
        # Generate daily entries
        date_range = pd.date_range(self.start_date, self.end_date, freq="D")
        
        # Initial prices
        prices = {s: random.uniform(50.0, 250.0) for s in self.symbols}
        
        for dt in date_range:
            # Skip weekends
            if dt.dayofweek >= 5:
                continue
                
            indicators = {}
            current_prices = {}
            
            for s in self.symbols:
                # Random walk step
                prices[s] = max(1.0, prices[s] * (1.0 + random.uniform(-0.02, 0.02)))
                current_prices[s] = prices[s]
                
                # Random dark pool metrics
                dark_ratio = random.uniform(0.15, 0.55)
                indicators[s] = {
                    "price": prices[s],
                    "close": prices[s],
                    "volume": float(random.randint(500000, 10000000)),
                    "is_dark_pool": random.random() > 0.5,
                    "dark_ratio": dark_ratio,
                    "avg_dark_price": prices[s] * (1.0 + random.uniform(-0.002, 0.002))
                }
                
            yield {
                "timestamp": dt,
                "prices": current_prices,
                "indicators": indicators
            }

