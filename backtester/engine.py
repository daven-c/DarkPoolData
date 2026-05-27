import pandas as pd
from typing import Dict, Any, List, Tuple
from backtester.data import DataProvider
from backtester.strategy import Strategy

class BacktestEngine:
    def __init__(self, data_provider: DataProvider, strategy: Strategy, symbol: str):
        """
        Coordinates the indicator calculation process.
        
        :param data_provider: An instance of DataProvider.
        :param strategy: An instance of Strategy containing indicator logic.
        :param symbol: Stock ticker symbol being analyzed.
        """
        self.data_provider = data_provider
        self.strategy = strategy
        self.symbol = symbol

    def run(self) -> Dict[str, Any]:
        """
        Runs the indicator calculations over the dataset.
        
        :return: Dict containing series data, signals, and basic summary metrics.
        """
        records = []
        for event in self.data_provider.get_data():
            ts = event["timestamp"]
            prices = event["prices"]
            indicators = event["indicators"]
            
            if self.symbol in prices:
                record = {"timestamp": ts, "price": prices[self.symbol]}
                if self.symbol in indicators:
                    record.update(indicators[self.symbol])
                records.append(record)
                
        df = pd.DataFrame(records)
        if df.empty:
            return {
                "series": [],
                "signals": [],
                "metrics": {
                    "avg_price": 0.0,
                    "max_indicator": 0.0,
                    "total_signals": 0
                }
            }
            
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
        
        # Check if we need to aggregate high-frequency raw trade ticks to daily bars
        if 'is_dark_pool' in df.columns and 'dark_ratio' not in df.columns:
            df = self._aggregate_trades_to_daily(df)
            
        # Compute strategy indicators & signals
        df_indicators, signals = self.strategy.calculate(df)
        
        price_col = 'close' if 'close' in df_indicators.columns else 'price'
        avg_price = float(df_indicators[price_col].mean()) if not df_indicators.empty else 0.0
        
        # Max of primary indicator (Fast SMA or Dark Ratio)
        max_indicator = 0.0
        if not df_indicators.empty and 'indicator_1' in df_indicators.columns:
            max_indicator = float(df_indicators['indicator_1'].max())
            
        series_data = []
        for _, row in df_indicators.iterrows():
            item = {
                "timestamp": row["timestamp"].isoformat(),
                "price": float(row[price_col]),
                "indicator_1": float(row["indicator_1"]) if not pd.isna(row.get("indicator_1")) else None,
                "indicator_2": float(row["indicator_2"]) if not pd.isna(row.get("indicator_2")) else None,
            }
            series_data.append(item)
            
        # Serialize signal timestamps
        signals_serializable = []
        for s in signals:
            s_copy = s.copy()
            s_copy["timestamp"] = s["timestamp"].isoformat()
            signals_serializable.append(s_copy)
            
        return {
            "series": series_data,
            "signals": signals_serializable,
            "metrics": {
                "avg_price": avg_price,
                "max_indicator": max_indicator,
                "total_signals": len(signals_serializable)
            }
        }

    def _aggregate_trades_to_daily(self, df: pd.DataFrame) -> pd.DataFrame:
        df['date'] = df['timestamp'].dt.date
        grouped = df.groupby('date')
        
        agg_records = []
        for date, group in grouped:
            group = group.sort_values('timestamp')
            last_price = float(group['price'].iloc[-1])
            total_vol = float(group['size'].sum())
            
            dark_vol = 0.0
            if 'is_dark_pool' in group.columns:
                dark_vol = float(group.loc[group['is_dark_pool'] == True, 'size'].sum())
            
            dark_ratio = (dark_vol / total_vol) if total_vol > 0 else 0.0
            
            agg_records.append({
                "timestamp": pd.Timestamp(date),
                "price": last_price,
                "close": last_price,
                "volume": total_vol,
                "dark_volume": dark_vol,
                "dark_ratio": dark_ratio
            })
            
        return pd.DataFrame(agg_records)
