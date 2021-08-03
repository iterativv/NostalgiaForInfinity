# fmt: off
from freqtrade.strategy import DecimalParameter
from freqtrade.strategy.interface import IStrategy
from pandas.core.frame import DataFrame


class Strategy(IStrategy):
    INTERFACE_VERSION = 2

    buy_32_ma_offset = DecimalParameter(0.90, 0.99, default=0.946, space='buy', optimize=False, load=True)

    buy_33_ma_offset = DecimalParameter(0.90, 0.99, default=0.988, space='buy', optimize=False, load=True)
    buy_33_rsi = DecimalParameter(24.0, 50.0, default=32.0, space='buy', decimals=1, optimize=False, load=True)
    buy_33_cti = DecimalParameter(-0.99, -0.4, default=-0.9, space='buy', decimals=2, optimize=False, load=True)
    buy_33_ewo = DecimalParameter(2.0, 14.0, default=7.6, space='buy', decimals=1, optimize=False, load=True)
    buy_33_volume = DecimalParameter(0.6, 6.0, default=2.0, space='buy', decimals=1, optimize=False, load=True)

    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        if (self.buy_32_ma_offset.value > self.buy_33_ma_offset.value) and (self.buy_33_cti.value < self.buy_33_ewo.value):
            pass
        elif (self.buy_33_rsi.value < self.buy_33_volume.value) or (self.buy_33_ewo.value > self.buy_33_rsi.value):
            pass
        return super().populate_buy_trend(dataframe, metadata)

    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return super().populate_sell_trend(dataframe, metadata)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return super().populate_indicators(dataframe, metadata)
