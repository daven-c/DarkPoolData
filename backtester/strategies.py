import pandas as pd
from typing import Dict, Any
from backtester.strategy import Strategy
from backtester.portfolio import Portfolio

class DarkPoolSpikeStrategy(Strategy):
    def __init__(self, parameters: Dict[str, Any] = None):
        """
        Triggers a BUY when dark pool activity (dark_ratio) spikes above a threshold.
        Holds for a fixed number of days and then sells.
        """
        super().__init__(parameters)
        self.threshold = self.parameters.get("dark_ratio_threshold", 0.40)
        self.holding_period = self.parameters.get("holding_period", 5)
        
        # Track symbol holdings: ticker -> buy_date
        self.buy_tracker: Dict[str, pd.Timestamp] = {}

    def on_data(self, current_time: pd.Timestamp, data: Dict[str, Any], portfolio: Portfolio) -> None:
        for symbol, info in data.items():
            dark_ratio = info.get("dark_ratio", 0.0)
            price = info.get("price", info.get("close", 0.0))
            
            if price <= 0:
                continue
                
            qty = portfolio.get_position(symbol)
            
            # Entry condition: ratio above threshold and we do not hold a position
            if qty == 0 and dark_ratio >= self.threshold:
                # Buy allocation: Use 20% of current cash
                target_value = portfolio.current_cash * 0.20
                shares_to_buy = int(target_value / price)
                if shares_to_buy > 0:
                    success = portfolio.buy(symbol, shares_to_buy, price, current_time)
                    if success:
                        self.buy_tracker[symbol] = current_time
            
            # Exit condition: held for more than holding_period days
            elif qty > 0 and symbol in self.buy_tracker:
                buy_date = self.buy_tracker[symbol]
                days_held = (current_time - buy_date).days
                if days_held >= self.holding_period:
                    portfolio.sell(symbol, qty, price, current_time)
                    del self.buy_tracker[symbol]


class SMACrossStrategy(Strategy):
    def __init__(self, parameters: Dict[str, Any] = None):
        """
        A standard moving average crossover strategy to serve as a baseline.
        """
        super().__init__(parameters)
        self.fast_period = self.parameters.get("fast_period", 10)
        self.slow_period = self.parameters.get("slow_period", 30)
        
        # Ticker price history windows: ticker -> List of prices
        self.price_history: Dict[str, list] = {}

    def on_data(self, current_time: pd.Timestamp, data: Dict[str, Any], portfolio: Portfolio) -> None:
        for symbol, info in data.items():
            price = info.get("price", info.get("close", 0.0))
            if price <= 0:
                continue
                
            if symbol not in self.price_history:
                self.price_history[symbol] = []
                
            self.price_history[symbol].append(price)
            
            # Keep history only up to slow_period + 2 (just enough for crossover calculation)
            max_needed = self.slow_period + 2
            if len(self.price_history[symbol]) > max_needed:
                self.price_history[symbol].pop(0)
                
            history = self.price_history[symbol]
            
            # Wait until we have enough data to calculate averages
            if len(history) < self.slow_period:
                continue
                
            # Current and previous SMA calculations
            fast_sma_curr = sum(history[-self.fast_period:]) / self.fast_period
            fast_sma_prev = sum(history[-(self.fast_period+1):-1]) / self.fast_period
            
            slow_sma_curr = sum(history[-self.slow_period:]) / self.slow_period
            slow_sma_prev = sum(history[-(self.slow_period+1):-1]) / self.slow_period
            
            qty = portfolio.get_position(symbol)
            
            # Buy signal (Golden Cross)
            if qty == 0 and fast_sma_prev <= slow_sma_prev and fast_sma_curr > slow_sma_curr:
                target_value = portfolio.current_cash * 0.20
                shares_to_buy = int(target_value / price)
                if shares_to_buy > 0:
                    portfolio.buy(symbol, shares_to_buy, price, current_time)
                    
            # Sell signal (Death Cross)
            elif qty > 0 and fast_sma_prev >= slow_sma_prev and fast_sma_curr < slow_sma_curr:
                portfolio.sell(symbol, qty, price, current_time)
