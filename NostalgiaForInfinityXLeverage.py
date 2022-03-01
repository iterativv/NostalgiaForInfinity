import sys
from pathlib import Path
from pandas import DataFrame

sys.path.append(str(Path(__file__).parent))

from NostalgiaForInfinityX import NostalgiaForInfinityX


class NostalgiaForInfinityXLeverage(NostalgiaForInfinityX):
    def leverage(self, pair: str, current_time, current_rate: float, proposed_leverage: float, max_leverage: float, side: str, **kwargs) -> float:
        """
        Customize leverage for each new trade.
        :param pair: Pair that's currently analyzed
        :param current_time: datetime object, containing the current datetime
        :param current_rate: Rate, calculated based on pricing settings in ask_strategy.
        :param proposed_leverage: A leverage proposed by the bot.
        :param max_leverage: Max leverage allowed on this pair
        :param side: 'long' or 'short' - indicating the direction of the proposed trade
        :return: A leverage amount, which is between 1.0 and max_leverage.
        """
        return 2.0

    def informative_pairs(self):
        candle_type = 'futures'

        # get access to all pairs available in whitelist.
        pairs = self.dp.current_whitelist()
        # Assign tf to each pair so they can be downloaded and cached for strategy.
        informative_pairs = [(pair, self.info_timeframe_1h, candle_type) for pair in pairs]
        informative_pairs.extend([(pair, self.info_timeframe_1d, candle_type) for pair in pairs])
        informative_pairs.extend([(pair, self.info_timeframe_15m, candle_type) for pair in pairs])

        if self.config["stake_currency"] in ["USDT", "BUSD", "USDC", "DAI", "TUSD", "PAX", "USD", "EUR", "GBP"]:
            btc_info_pair = f"BTC/{self.config['stake_currency']}"
        else:
            btc_info_pair = "BTC/USDT"

        informative_pairs.append((btc_info_pair, self.timeframe, candle_type))
        informative_pairs.append((btc_info_pair, self.info_timeframe_1d, candle_type))
        informative_pairs.append((btc_info_pair, self.info_timeframe_1h, candle_type))
        informative_pairs.append((btc_info_pair, self.info_timeframe_15m, candle_type))
        return informative_pairs

    # def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
    #     df = super().populate_buy_trend(dataframe, metadata)
    #     return df
