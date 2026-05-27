from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, Any, Tuple, List

class Strategy(ABC):
    def __init__(self, parameters: Dict[str, Any] = None):
        """
        Base Strategy Class for indicator calculations.
        :param parameters: Dict of strategy parameters (e.g. thresholds, lookbacks).
        """
        self.parameters = parameters or {}

    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        """
        Calculates indicators and signal events on the input historical dataframe.
        
        :param df: DataFrame containing price history and other raw details.
        :return: A tuple of (df_with_indicators, signals_list)
        """
        pass
