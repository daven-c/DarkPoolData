from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any

class Strategy(ABC):
    def __init__(self, parameters: Dict[str, Any] = None):
        """
        Base Strategy Class.
        :param parameters: Dict of strategy parameters (e.g. thresholds, lookbacks).
        """
        self.parameters = parameters or {}

    @abstractmethod
    def on_data(self, current_time: pd.Timestamp, data: Dict[str, Any], portfolio) -> None:
        """
        This method is invoked chronologically at each timestamp in the backtest.
        
        :param current_time: The current timestamp.
        :param data: Dictionary mapping tickers to their current bar/trade/darkpool data.
        :param portfolio: The Portfolio object which allows executing buy/sell orders.
        """
        pass
