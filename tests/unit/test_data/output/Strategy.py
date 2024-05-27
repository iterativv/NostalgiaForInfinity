# fmt: off
from freqtrade.strategy.interface import IStrategy
from pandas.core.frame import DataFrame


class Strategy(IStrategy):
    INTERFACE_VERSION = 2

    buy_32_ma_offset = 0.946

    buy_33_ma_offset = 0.988
    buy_33_rsi = 32.0
    buy_33_cti = -0.9
    buy_33_ewo = 7.6
    buy_33_volume = 2.0

    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if (self.buy_32_ma_offset > self.buy_33_ma_offset) and (self.buy_33_cti < self.buy_33_ewo):
            pass
        elif (self.buy_33_rsi < self.buy_33_volume) or (self.buy_33_ewo > self.buy_33_rsi):
            pass
        return super().populate_buy_trend(dataframe, metadata)

    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return super().populate_sell_trend(dataframe, metadata)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return super().populate_indicators(dataframe, metadata)
