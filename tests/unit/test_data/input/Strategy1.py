# fmt: off
from freqtrade.strategy import DecimalParameter
from freqtrade.strategy.interface import IStrategy
from pandas.core.frame import DataFrame


class Strategy1(IStrategy):
    INTERFACE_VERSION = 2

    buy_32_ma_offset = DecimalParameter(0.90, 0.99, default=0.946, space='buy', optimize=False, load=True)

    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if self.buy_32_ma_offset.value > 0.90:
            pass
        return super().populate_buy_trend(dataframe, metadata)

    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return super().populate_sell_trend(dataframe, metadata)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return super().populate_indicators(dataframe, metadata)
