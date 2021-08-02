from freqtrade.strategy.interface import IStrategy
from freqtrade.strategy import DecimalParameter 
from pandas.core.frame import DataFrame


class Strategy1(IStrategy):
    INTERFACE_VERSION = 2

    buy_32_ma_offset = 0.946
    
    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if self.buy_32_ma_offset > 0.90:
            pass
        return super().populate_buy_trend(dataframe, metadata)

    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return super().populate_sell_trend(dataframe, metadata)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return super().populate_indicators(dataframe, metadata)
