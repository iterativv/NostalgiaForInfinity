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
