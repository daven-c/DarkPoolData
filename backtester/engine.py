from backtester.data import DataProvider
from backtester.strategy import Strategy
from backtester.portfolio import Portfolio
from typing import Dict, Any

class BacktestEngine:
    def __init__(self, data_provider: DataProvider, strategy: Strategy, portfolio: Portfolio):
        """
        Coordinates the backtesting process.
        
        :param data_provider: An instance of DataProvider.
        :param strategy: An instance of Strategy containing trading rules.
        :param portfolio: An instance of Portfolio to track assets and trades.
        """
        self.data_provider = data_provider
        self.strategy = strategy
        self.portfolio = portfolio

    def run(self) -> Dict[str, Any]:
        """
        Runs the simulation loop over all data yielded by the provider.
        
        :return: Final performance summary from the portfolio.
        """
        current_prices = {}
        
        for event in self.data_provider.get_data():
            timestamp = event["timestamp"]
            prices = event["prices"]
            indicators = event["indicators"]
            
            # Update latest known prices for portfolio valuation
            current_prices.update(prices)
            
            # Run strategy logic
            self.strategy.on_data(timestamp, indicators, self.portfolio)
            
            # Record portfolio equity snapshot for this timestamp
            self.portfolio.update_equity(timestamp, current_prices)
            
        return self.portfolio.get_metrics()
