import pandas as pd
from typing import Dict, Any, Tuple, List
from backtester.strategy import Strategy

class DarkPoolSpikeStrategy(Strategy):
    def __init__(self, parameters: Dict[str, Any] = None):
        """
        Triggers a Spike signal when dark pool activity (dark_ratio) spikes above a threshold.
        """
        super().__init__(parameters)
        self.threshold = self.parameters.get("dark_ratio_threshold", 0.40)

    def calculate(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        if df.empty:
            return df, []
            
        price_col = 'close' if 'close' in df.columns else 'price'
        
        # If dark_ratio is not in columns, default to 0
        if 'dark_ratio' not in df.columns:
            df['indicator_1'] = 0.0
        else:
            df['indicator_1'] = df['dark_ratio']
            
        df['indicator_2'] = self.threshold # Static Threshold Line
        
        signals = []
        for i in range(len(df)):
            curr_ratio = df['indicator_1'].iloc[i]
            ts = df['timestamp'].iloc[i]
            price = df[price_col].iloc[i]
            
            # Detect Spike signal
            if curr_ratio >= self.threshold:
                signals.append({
                    "timestamp": ts,
                    "type": "SPIKE",
                    "price": float(price),
                    "description": f"Dark Pool Spike: Volume ratio reached {curr_ratio*100:.1f}% (Threshold: {self.threshold*100:.1f}%) at ${price:.2f}"
                })
                
        return df, signals


class SMACrossStrategy(Strategy):
    def __init__(self, parameters: Dict[str, Any] = None):
        """
        Calculates moving averages and flags crossover signals.
        """
        super().__init__(parameters)
        self.fast_period = self.parameters.get("fast_period", 10)
        self.slow_period = self.parameters.get("slow_period", 30)

    def calculate(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        if df.empty:
            return df, []
            
        # Ensure we have price or close
        price_col = 'close' if 'close' in df.columns else 'price'
        
        # Calculate moving averages
        df['indicator_1'] = df[price_col].rolling(window=self.fast_period).mean() # Fast SMA
        df['indicator_2'] = df[price_col].rolling(window=self.slow_period).mean() # Slow SMA
        
        signals = []
        
        # Detect crossovers
        # Fast SMA crossed above Slow SMA: Buy signal (Golden Cross)
        # Fast SMA crossed below Slow SMA: Sell signal (Death Cross)
        for i in range(1, len(df)):
            prev_fast = df['indicator_1'].iloc[i-1]
            prev_slow = df['indicator_2'].iloc[i-1]
            curr_fast = df['indicator_1'].iloc[i]
            curr_slow = df['indicator_2'].iloc[i]
            
            if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
                continue
                
            ts = df['timestamp'].iloc[i]
            price = df[price_col].iloc[i]
            
            if prev_fast <= prev_slow and curr_fast > curr_slow:
                signals.append({
                    "timestamp": ts,
                    "type": "BUY",
                    "price": float(price),
                    "description": f"Golden Cross: Fast SMA ({self.fast_period}d) crossed above Slow SMA ({self.slow_period}d) at ${price:.2f}"
                })
            elif prev_fast >= prev_slow and curr_fast < curr_slow:
                signals.append({
                    "timestamp": ts,
                    "type": "SELL",
                    "price": float(price),
                    "description": f"Death Cross: Fast SMA ({self.fast_period}d) crossed below Slow SMA ({self.slow_period}d) at ${price:.2f}"
                })
                
        return df, signals
