import pandas as pd
import numpy as np
from typing import Dict, List, Any

class Portfolio:
    def __init__(self, initial_cash: float = 100000.0, transaction_fee_rate: float = 0.0005):
        """
        Tracks cash, asset positions, transaction fees, and trades ledger.
        
        :param initial_cash: Starting cash for the portfolio.
        :param transaction_fee_rate: Fee rate as a decimal (e.g. 0.0005 = 0.05% per trade).
        """
        self.initial_cash = initial_cash
        self.current_cash = initial_cash
        self.transaction_fee_rate = transaction_fee_rate
        
        # Mapping: ticker -> {"quantity": float, "avg_price": float}
        self.positions: Dict[str, Dict[str, float]] = {}
        
        # List of executed trades
        self.trades: List[Dict[str, Any]] = []
        
        # Timeseries of portfolio values: [{"timestamp": Timestamp, "cash": float, "market_value": float, "total_value": float}]
        self.equity_history: List[Dict[str, Any]] = []

    def get_position(self, symbol: str) -> float:
        """Returns the number of shares held of a given symbol."""
        return self.positions.get(symbol, {}).get("quantity", 0.0)

    def get_average_cost(self, symbol: str) -> float:
        """Returns the average entry price for a given symbol."""
        return self.positions.get(symbol, {}).get("avg_price", 0.0)

    def buy(self, symbol: str, quantity: float, price: float, timestamp: pd.Timestamp) -> bool:
        """
        Executes a BUY order if cash is sufficient.
        
        :return: True if successful, False otherwise.
        """
        if quantity <= 0 or price <= 0:
            return False
            
        trade_value = quantity * price
        fee = trade_value * self.transaction_fee_rate
        total_cost = trade_value + fee
        
        if total_cost > self.current_cash:
            # Insufficient funds
            return False
            
        self.current_cash -= total_cost
        
        # Update positions
        current_qty = self.get_position(symbol)
        current_avg = self.get_average_cost(symbol)
        
        new_qty = current_qty + quantity
        new_avg = ((current_avg * current_qty) + (price * quantity)) / new_qty
        
        self.positions[symbol] = {
            "quantity": new_qty,
            "avg_price": new_avg
        }
        
        self.trades.append({
            "timestamp": timestamp,
            "symbol": symbol,
            "action": "BUY",
            "quantity": quantity,
            "price": price,
            "value": trade_value,
            "fee": fee,
            "total_cost": total_cost,
            "remaining_cash": self.current_cash
        })
        return True

    def sell(self, symbol: str, quantity: float, price: float, timestamp: pd.Timestamp) -> bool:
        """
        Executes a SELL order if the position exists and is sufficient.
        
        :return: True if successful, False otherwise.
        """
        current_qty = self.get_position(symbol)
        if quantity <= 0 or price <= 0 or current_qty < quantity:
            return False
            
        trade_value = quantity * price
        fee = trade_value * self.transaction_fee_rate
        net_revenue = trade_value - fee
        
        self.current_cash += net_revenue
        
        # Update positions
        new_qty = current_qty - quantity
        if new_qty == 0:
            if symbol in self.positions:
                del self.positions[symbol]
        else:
            self.positions[symbol]["quantity"] = new_qty
            # Average cost remains the same on sales
            
        self.trades.append({
            "timestamp": timestamp,
            "symbol": symbol,
            "action": "SELL",
            "quantity": quantity,
            "price": price,
            "value": trade_value,
            "fee": fee,
            "total_cost": -net_revenue,
            "remaining_cash": self.current_cash
        })
        return True

    def update_equity(self, timestamp: pd.Timestamp, current_prices: Dict[str, float]) -> None:
        """
        Records the current total value of the portfolio based on latest asset prices.
        """
        market_value = 0.0
        for symbol, pos in self.positions.items():
            qty = pos["quantity"]
            price = current_prices.get(symbol, pos["avg_price"])
            market_value += qty * price
            
        total_value = self.current_cash + market_value
        
        self.equity_history.append({
            "timestamp": timestamp,
            "cash": self.current_cash,
            "market_value": market_value,
            "total_value": total_value
        })

    def get_metrics(self) -> Dict[str, Any]:
        """
        Computes various performance metrics based on trade history and equity curve.
        """
        if not self.equity_history:
            return {}
            
        df_equity = pd.DataFrame(self.equity_history)
        df_equity.set_index("timestamp", inplace=True)
        
        total_return = (df_equity["total_value"].iloc[-1] / self.initial_cash) - 1.0
        
        # Calculate daily returns for Sharpe / volatility
        # Resample to daily if data is intraday
        df_daily = df_equity["total_value"].resample("D").last().ffill()
        daily_returns = df_daily.pct_change().dropna()
        
        # Sharpe ratio (assuming risk free rate of 0% for simplicity)
        mean_return = daily_returns.mean()
        std_return = daily_returns.std()
        
        if std_return > 0:
            # Annualized Sharpe (assuming 252 trading days)
            sharpe = (mean_return / std_return) * np.sqrt(252)
        else:
            sharpe = 0.0
            
        # Drawdown calculation
        rolling_max = df_equity["total_value"].cummax()
        drawdown = (df_equity["total_value"] - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        
        # Trade statistics
        buys = [t for t in self.trades if t["action"] == "BUY"]
        sells = [t for t in self.trades if t["action"] == "SELL"]
        
        # Simple match of buys and sells to estimate win rate (fifo/lifo simple estimation or realized profits)
        # For simplicity, let's track the profit/loss of each round trip
        # A simple method: sum net cost of trades
        total_fees = sum(t["fee"] for t in self.trades)
        
        metrics = {
            "initial_cash": self.initial_cash,
            "final_value": df_equity["total_value"].iloc[-1],
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe,
            "total_trades": len(self.trades),
            "buy_trades": len(buys),
            "sell_trades": len(sells),
            "total_fees": total_fees,
            "remaining_cash": self.current_cash,
            "open_positions": self.positions
        }
        return metrics
