import logging
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
import talib.abstract as ta
from freqtrade.strategy.interface import IStrategy
from freqtrade.strategy import merge_informative_pair
from pandas import DataFrame, Series
from functools import reduce, partial
from freqtrade.persistence import Trade
from datetime import datetime, timedelta
import time

log = logging.getLogger(__name__)
#log.setLevel(logging.DEBUG)

###########################################################################################################
##                NostalgiaForInfinityX2 by iterativ                                                     ##
##           https://github.com/iterativv/NostalgiaForInfinity                                           ##
##                                                                                                       ##
##    Strategy for Freqtrade https://github.com/freqtrade/freqtrade                                      ##
##                                                                                                       ##
###########################################################################################################
##               GENERAL RECOMMENDATIONS                                                                 ##
##                                                                                                       ##
##   For optimal performance, suggested to use between 4 and 6 open trades, with unlimited stake.        ##
##   A pairlist with 40 to 80 pairs. Volume pairlist works well.                                         ##
##   Prefer stable coin (USDT, BUSDT etc) pairs, instead of BTC or ETH pairs.                            ##
##   Highly recommended to blacklist leveraged tokens (*BULL, *BEAR, *UP, *DOWN etc).                    ##
##   Ensure that you don't override any variables in you config.json. Especially                         ##
##   the timeframe (must be 5m).                                                                         ##
##     use_sell_signal must set to true (or not set at all).                                             ##
##     sell_profit_only must set to false (or not set at all).                                           ##
##     ignore_roi_if_buy_signal must set to true (or not set at all).                                    ##
##                                                                                                       ##
###########################################################################################################
##               DONATIONS                                                                               ##
##                                                                                                       ##
##   BTC: bc1qvflsvddkmxh7eqhc4jyu5z5k6xcw3ay8jl49sk                                                     ##
##   ETH (ERC20): 0x83D3cFb8001BDC5d2211cBeBB8cB3461E5f7Ec91                                             ##
##   BEP20/BSC (USDT, ETH, BNB, ...): 0x86A0B21a20b39d16424B7c8003E4A7e12d78ABEe                         ##
##   TRC20/TRON (USDT, TRON, ...): TTAa9MX6zMLXNgWMhg7tkNormVHWCoq8Xk                                    ##
##                                                                                                       ##
##               REFERRAL LINKS                                                                          ##
##                                                                                                       ##
##   Binance: https://accounts.binance.com/en/register?ref=EAZC47FM (5% discount on trading fees)        ##
##   Kucoin: https://www.kucoin.com/r/af/QBSSSPYV (5% discount on trading fees)                          ##
##   Gate.io: https://www.gate.io/signup/8054544 (10% discount on trading fees)                          ##
##   FTX: https://ftx.com/eu/profile#a=100178030 (5% discount on trading fees)                           ##
##   OKX: https://www.okx.com/join/11749725760 (5% discount on trading fees)                             ##
##   Huobi: https://www.huobi.com/en-us/topic/double-reward/?invite_code=ubpt2223                        ##
###########################################################################################################

class NostalgiaForInfinityX2(IStrategy):
    INTERFACE_VERSION = 2

    def version(self) -> str:
        return "v0.0.1"

    # ROI table:
    minimal_roi = {
        "0": 100.0,
    }

    stoploss = -0.99

    # Trailing stoploss (not used)
    trailing_stop = False
    trailing_only_offset_is_reached = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.03

    use_custom_stoploss = False

    # Optimal timeframe for the strategy.
    timeframe = '5m'
    info_timeframes = ['15m','1h','4h','1d']

    # BTC informatives
    btc_info_timeframes = ['5m','15m','1h','4h','1d']

    # Backtest Age Filter emulation
    has_bt_agefilter = False
    bt_min_age_days = 3

    # Exchange Downtime protection
    has_downtime_protection = False

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the "ask_strategy" section in the config.
    use_sell_signal = True
    sell_profit_only = False
    ignore_roi_if_buy_signal = True

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 480

    # Optional order type mapping.
    order_types = {
        'buy': 'limit',
        'sell': 'limit',
        'trailing_stop_loss': 'limit',
        'stoploss': 'limit',
        'stoploss_on_exchange': False,
        'stoploss_on_exchange_interval': 60,
        'stoploss_on_exchange_limit_ratio': 0.99
    }

    #############################################################
    # Buy side configuration

    buy_params = {
        # Enable/Disable conditions
        # -------------------------------------------------------
        "buy_condition_1_enable": True,
    }

    buy_protection_params = {}

    #############################################################

    def get_ticker_indicator(self):
        return int(self.timeframe[:-1])

    def sell_long_bull(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:

        # Original sell signals
        sell, signal_name = self.sell_long_bull_signals(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, buy_tag)
        if sell and (signal_name is not None):
            return True, signal_name

        # Main sell signals
        sell, signal_name = self.sell_long_bull_main(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, buy_tag)
        if sell and (signal_name is not None):
            return True, signal_name

        # Williams %R based sells
        sell, signal_name = self.sell_long_bull_r(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, buy_tag)
        if sell and (signal_name is not None):
            return True, signal_name

        # Stoplosses
        sell, signal_name = self.sell_long_bull_stoploss(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, buy_tag)
        if sell and (signal_name is not None):
            return True, signal_name

        return False, None


    def sell_long_bull_signals(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Sell signal 1
        if (last_candle['rsi_14'] > 78.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) and (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']) and (previous_candle_4['close'] > previous_candle_4['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_1_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_1_2_1'

        # Sell signal 2
        elif (last_candle['rsi_14'] > 79.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_2_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_2_2_1'

        # Sell signal 3
        elif (last_candle['rsi_14'] > 81.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_3_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_3_2_1'

        # Sell signal 4
        elif (last_candle['rsi_14'] > 77.0) and (last_candle['rsi_14_1h'] > 77.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_4_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_4_2_1'

        # Sell signal 6
        elif (last_candle['close'] < last_candle['ema_200']) and (last_candle['close'] > last_candle['ema_50']) and (last_candle['rsi_14'] > 78.5):
            if (current_profit > 0.01):
                return True, 'sell_long_bull_6_1'

        # Sell signal 7
        elif (last_candle['rsi_14_1h'] > 79.0) and (last_candle['crossed_below_ema_12_26']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_7_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_7_2_1'

        # Sell signal 8
        elif (last_candle['close'] > last_candle['bb20_2_upp_1h'] * 1.07):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_8_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_bull_8_2_1'

        return False, None

    def sell_long_bull_main(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if (last_candle['close'] > last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 26.0):
                    return True, 'sell_long_bull_o_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 30.0):
                    return True, 'sell_long_bull_o_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 32.0):
                    return True, 'sell_long_bull_o_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 34.0):
                    return True, 'sell_long_bull_o_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 36.0):
                    return True, 'sell_long_bull_o_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 38.0):
                    return True, 'sell_long_bull_o_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 40.0):
                    return True, 'sell_long_bull_o_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'sell_long_bull_o_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'sell_long_bull_o_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'sell_long_bull_o_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 48.0):
                    return True, 'sell_long_bull_o_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'sell_long_bull_o_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'sell_long_bull_o_12'
        elif (last_candle['close'] < last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 28.0):
                    return True, 'sell_long_bull_u_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 32.0):
                    return True, 'sell_long_bull_u_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 34.0):
                    return True, 'sell_long_bull_u_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 36.0):
                    return True, 'sell_long_bull_u_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 38.0):
                    return True, 'sell_long_bull_u_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 40.0):
                    return True, 'sell_long_bull_u_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'sell_long_bull_u_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'sell_long_bull_u_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'sell_long_bull_u_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 48.0):
                    return True, 'sell_long_bull_u_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 50.0):
                    return True, 'sell_long_bull_u_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 48.0):
                    return True, 'sell_long_bull_u_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'sell_long_bull_u_12'

        return False, None

    def sell_long_bull_r(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if 0.01 > current_profit >= 0.001:
            if (last_candle['r_480'] > -0.1):
                return True, 'sell_long_bull_w_0_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_0_2'
        elif 0.02 > current_profit >= 0.01:
            if (last_candle['r_480'] > -0.2):
                return True, 'sell_long_bull_w_1_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_1_2'
        elif 0.03 > current_profit >= 0.02:
            if (last_candle['r_480'] > -0.3):
                return True, 'sell_long_bull_w_2_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_2_2'
        elif 0.04 > current_profit >= 0.03:
            if (last_candle['r_480'] > -0.4):
                return True, 'sell_long_bull_w_3_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_3_2'
        elif 0.05 > current_profit >= 0.04:
            if (last_candle['r_480'] > -0.5):
                return True, 'sell_long_bull_w_4_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_4_2'
        elif 0.06 > current_profit >= 0.05:
            if (last_candle['r_480'] > -0.6):
                return True, 'sell_long_bull_w_5_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_5_2'
        elif 0.07 > current_profit >= 0.06:
            if (last_candle['r_480'] > -0.7):
                return True, 'sell_long_bull_w_6_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_6_2'
        elif 0.08 > current_profit >= 0.07:
            if (last_candle['r_480'] > -0.8):
                return True, 'sell_long_bull_w_7_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_7_2'
        elif 0.09 > current_profit >= 0.08:
            if (last_candle['r_480'] > -0.9):
                return True, 'sell_long_bull_w_8_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_8_2'
        elif 0.1 > current_profit >= 0.09:
            if (last_candle['r_480'] > -1.0):
                return True, 'sell_long_bull_w_9_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_9_2'
        elif 0.12 > current_profit >= 0.1:
            if (last_candle['r_480'] > -1.1):
                return True, 'sell_long_bull_w_10_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_10_2'
        elif 0.2 > current_profit >= 0.12:
            if (last_candle['r_480'] > -0.4):
                return True, 'sell_long_bull_w_11_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_long_bull_w_11_2'
        elif current_profit >= 0.2:
            if (last_candle['r_480'] > -0.2):
                return True, 'sell_long_bull_w_12_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 80.0):
                return True, 'sell_long_bull_w_12_2'

        return False, None

    def sell_long_bull_stoploss(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Stoploss doom
        if (
                (current_profit < -0.08)
        ):
            return True, 'sell_long_bull_stoploss_doom'

        # Under & near EMA200, local uptrend move
        if (
                (current_profit < -0.025)
                and (last_candle['close'] < last_candle['ema_200'])
                and (((last_candle['ema_200'] - last_candle['close']) / last_candle['close']) < 0.024)
                and last_candle['rsi_14'] > previous_candle_1['rsi_14']
                and (last_candle['rsi_14'] > (last_candle['rsi_14_1h'] + 10.0))
                and (current_time - timedelta(minutes=30) > trade.open_date_utc)
        ):
            return True, 'sell_long_bull_stoploss_u_e_1'

        return False, None

    def custom_sell(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                    current_profit: float, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1]
        previous_candle_1 = dataframe.iloc[-2]
        previous_candle_2 = dataframe.iloc[-3]
        previous_candle_3 = dataframe.iloc[-4]
        previous_candle_4 = dataframe.iloc[-5]
        previous_candle_5 = dataframe.iloc[-6]

        buy_tag = 'empty'
        if hasattr(trade, 'buy_tag') and trade.buy_tag is not None:
            buy_tag = trade.buy_tag
        buy_tags = buy_tag.split()

        max_profit = ((trade.max_rate - trade.open_rate) / trade.open_rate)
        max_loss = ((trade.open_rate - trade.min_rate) / trade.min_rate)

        if hasattr(trade, 'select_filled_orders'):
            filled_buys = trade.select_filled_orders('buy')
            count_of_buys = len(filled_buys)
            if count_of_buys > 1:
                initial_buy = filled_buys[0]
                if (initial_buy is not None and initial_buy.average is not None):
                    max_profit = ((trade.max_rate - initial_buy.average) / initial_buy.average)
                    max_loss = ((initial_buy.average - trade.min_rate) / trade.min_rate)

        # Long mode, bull
        if all(c in ['1'] for c in buy_tags):
            sell, signal_name = self.sell_long_bull(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, buy_tag)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {buy_tag})"

        return None

    def informative_pairs(self):
        # get access to all pairs available in whitelist.
        pairs = self.dp.current_whitelist()
        # Assign tf to each pair so they can be downloaded and cached for strategy.
        informative_pairs = []
        for info_timeframe in self.info_timeframes:
            informative_pairs.extend([(pair, info_timeframe) for pair in pairs])

        if self.config['stake_currency'] in ['USDT','BUSD','USDC','DAI','TUSD','PAX','USD','EUR','GBP']:
            btc_info_pair = f"BTC/{self.config['stake_currency']}"
        else:
            btc_info_pair = "BTC/USDT"

        informative_pairs.extend([(btc_info_pair, btc_info_timeframe) for btc_info_timeframe in self.btc_info_timeframes])

        return informative_pairs

    def informative_1d_indicators(self, metadata: dict, info_timeframe) -> DataFrame:
        tik = time.perf_counter()
        assert self.dp, "DataProvider is required for multiple timeframes."
        # Get the informative pair
        informative_1d = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=info_timeframe)

        # Indicators
        # -----------------------------------------------------------------------------------------
        # RSI
        informative_1d['rsi_14'] = ta.RSI(informative_1d, timeperiod=14)

        # Pivots
        informative_1d['pivot'], informative_1d['res1'], informative_1d['res2'], informative_1d['res3'], informative_1d['sup1'], informative_1d['sup2'], informative_1d['sup3'] = pivot_points(informative_1d, mode='fibonacci')

        # S/R
        res_series = informative_1d['high'].rolling(window = 5, center=True).apply(lambda row: is_resistance(row), raw=True).shift(2)
        sup_series = informative_1d['low'].rolling(window = 5, center=True).apply(lambda row: is_support(row), raw=True).shift(2)
        informative_1d['res_level'] = Series(np.where(res_series, np.where(informative_1d['close'] > informative_1d['open'], informative_1d['close'], informative_1d['open']), float('NaN'))).ffill()
        informative_1d['res_hlevel'] = Series(np.where(res_series, informative_1d['high'], float('NaN'))).ffill()
        informative_1d['sup_level'] = Series(np.where(sup_series, np.where(informative_1d['close'] < informative_1d['open'], informative_1d['close'], informative_1d['open']), float('NaN'))).ffill()

        # Performance logging
        # -----------------------------------------------------------------------------------------
        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] informative_1d_indicators took: {tok - tik:0.4f} seconds.")

        return informative_1d

    def informative_4h_indicators(self, metadata: dict, info_timeframe) -> DataFrame:
        tik = time.perf_counter()
        assert self.dp, "DataProvider is required for multiple timeframes."
        # Get the informative pair
        informative_4h = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=info_timeframe)

        # Indicators
        # -----------------------------------------------------------------------------------------
        # RSI
        informative_4h['rsi_14'] = ta.RSI(informative_4h, timeperiod=14, fillna=True)

        # SMA
        informative_4h['sma_50'] = ta.SMA(informative_4h, timeperiod=50)
        informative_4h['sma_200'] = ta.SMA(informative_4h, timeperiod=200)

        # Williams %R
        informative_4h['r_14'] = williams_r(informative_4h, period=14)
        informative_4h['r_480'] = williams_r(informative_4h, period=480)

        # S/R
        res_series = informative_4h['high'].rolling(window = 5, center=True).apply(lambda row: is_resistance(row), raw=True).shift(2)
        sup_series = informative_4h['low'].rolling(window = 5, center=True).apply(lambda row: is_support(row), raw=True).shift(2)
        informative_4h['res_level'] = Series(np.where(res_series, np.where(informative_4h['close'] > informative_4h['open'], informative_4h['close'], informative_4h['open']), float('NaN'))).ffill()
        informative_4h['res_hlevel'] = Series(np.where(res_series, informative_4h['high'], float('NaN'))).ffill()
        informative_4h['sup_level'] = Series(np.where(sup_series, np.where(informative_4h['close'] < informative_4h['open'], informative_4h['close'], informative_4h['open']), float('NaN'))).ffill()

        # Performance logging
        # -----------------------------------------------------------------------------------------
        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] informative_1d_indicators took: {tok - tik:0.4f} seconds.")

        return informative_4h

    def informative_1h_indicators(self, metadata: dict, info_timeframe) -> DataFrame:
        tik = time.perf_counter()
        assert self.dp, "DataProvider is required for multiple timeframes."
        # Get the informative pair
        informative_1h = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=info_timeframe)

        # Indicators
        # -----------------------------------------------------------------------------------------
        # RSI
        informative_1h['rsi_14'] = ta.RSI(informative_1h, timeperiod=14)

        # SMA
        informative_1h['sma_50'] = ta.SMA(informative_1h, timeperiod=50)
        informative_1h['sma_100'] = ta.SMA(informative_1h, timeperiod=100)
        informative_1h['sma_200'] = ta.SMA(informative_1h, timeperiod=200)

        # BB
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(informative_1h), window=20, stds=2)
        informative_1h['bb20_2_low'] = bollinger['lower']
        informative_1h['bb20_2_mid'] = bollinger['mid']
        informative_1h['bb20_2_upp'] = bollinger['upper']

        # Williams %R
        informative_1h['r_14'] = williams_r(informative_1h, period=14)
        informative_1h['r_480'] = williams_r(informative_1h, period=480)

        # S/R
        res_series = informative_1h['high'].rolling(window = 5, center=True).apply(lambda row: is_resistance(row), raw=True).shift(2)
        sup_series = informative_1h['low'].rolling(window = 5, center=True).apply(lambda row: is_support(row), raw=True).shift(2)
        informative_1h['res_level'] = Series(np.where(res_series, np.where(informative_1h['close'] > informative_1h['open'], informative_1h['close'], informative_1h['open']), float('NaN'))).ffill()
        informative_1h['res_hlevel'] = Series(np.where(res_series, informative_1h['high'], float('NaN'))).ffill()
        informative_1h['sup_level'] = Series(np.where(sup_series, np.where(informative_1h['close'] < informative_1h['open'], informative_1h['close'], informative_1h['open']), float('NaN'))).ffill()

        # Performance logging
        # -----------------------------------------------------------------------------------------
        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] informative_1h_indicators took: {tok - tik:0.4f} seconds.")

        return informative_1h

    def informative_15m_indicators(self, metadata: dict, info_timeframe) -> DataFrame:
        tik = time.perf_counter()
        assert self.dp, "DataProvider is required for multiple timeframes."

        # Get the informative pair
        informative_15m = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=info_timeframe)

        # Indicators
        # -----------------------------------------------------------------------------------------
        informative_15m['rsi_14'] = ta.RSI(informative_15m, timeperiod=14)

        # Performance logging
        # -----------------------------------------------------------------------------------------
        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] informative_15m_indicators took: {tok - tik:0.4f} seconds.")

        return informative_15m

    # Coin Pair Base Timeframe Indicators
    # ---------------------------------------------------------------------------------------------
    def base_tf_5m_indicators(self,  metadata: dict, dataframe: DataFrame) -> DataFrame:
        tik = time.perf_counter()

        # Indicators
        # -----------------------------------------------------------------------------------------
        # RSI
        dataframe['rsi_14'] = ta.RSI(dataframe, timeperiod=14)

        # EMA
        dataframe['ema_12'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['ema_26'] = ta.EMA(dataframe, timeperiod=26)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)

        # SMA
        dataframe['sma_50'] = ta.SMA(dataframe, timeperiod=50)
        dataframe['sma_200'] = ta.SMA(dataframe, timeperiod=200)

        # BB 20 - STD2
        bb_20_std2 = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb20_2_low'] = bb_20_std2['lower']
        dataframe['bb20_2_mid'] = bb_20_std2['mid']
        dataframe['bb20_2_upp'] = bb_20_std2['upper']

        # Williams %R
        dataframe['r_14'] = williams_r(dataframe, period=14)
        dataframe['r_480'] = williams_r(dataframe, period=480)

        # For sell checks
        dataframe['crossed_below_ema_12_26'] = qtpylib.crossed_below(dataframe['ema_12'], dataframe['ema_26'])

        # Global protections
        # -----------------------------------------------------------------------------------------
        if not self.config['runmode'].value in ('live', 'dry_run'):
            # Backtest age filter
            dataframe['bt_agefilter_ok'] = False
            dataframe.loc[dataframe.index > (12 * 24 * self.bt_min_age_days),'bt_agefilter_ok'] = True
        else:
            # Exchange downtime protection
            dataframe['live_data_ok'] = (dataframe['volume'].rolling(window=72, min_periods=72).min() > 0)

        # Performance logging
        # -----------------------------------------------------------------------------------------
        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] base_tf_5m_indicators took: {tok - tik:0.4f} seconds.")

        return dataframe

    # Coin Pair Indicator Switch Case
    # ---------------------------------------------------------------------------------------------
    def info_switcher(self, metadata: dict, info_timeframe) -> DataFrame:
        if info_timeframe == '1d':
            return self.informative_1d_indicators(metadata, info_timeframe)
        elif info_timeframe == '4h':
            return self.informative_4h_indicators(metadata, info_timeframe)
        elif info_timeframe == '1h':
            return self.informative_1h_indicators(metadata, info_timeframe)
        elif info_timeframe == '15m':
            return self.informative_15m_indicators(metadata, info_timeframe)
        else:
            raise RuntimeError(f"{info_timeframe} not supported as informative timeframe for BTC pair.")

    # BTC 1D Indicators
    # ---------------------------------------------------------------------------------------------
    def btc_info_1d_indicators(self, btc_info_pair, btc_info_timeframe, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        btc_info_1d = self.dp.get_pair_dataframe(btc_info_pair, btc_info_timeframe)
        # Indicators
        # -----------------------------------------------------------------------------------------
        btc_info_1d['rsi_14'] = ta.RSI(btc_info_1d, timeperiod=14)
        #btc_info_1d['pivot'], btc_info_1d['res1'], btc_info_1d['res2'], btc_info_1d['res3'], btc_info_1d['sup1'], btc_info_1d['sup2'], btc_info_1d['sup3'] = pivot_points(btc_info_1d, mode='fibonacci')

        # Add prefix
        # -----------------------------------------------------------------------------------------
        ignore_columns = ['date']
        btc_info_1d.rename(columns=lambda s: f"btc_{s}" if s not in ignore_columns else s, inplace=True)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] btc_info_1d_indicators took: {tok - tik:0.4f} seconds.")

        return btc_info_1d

    # BTC 4h Indicators
    # ---------------------------------------------------------------------------------------------
    def btc_info_4h_indicators(self, btc_info_pair, btc_info_timeframe, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        btc_info_4h = self.dp.get_pair_dataframe(btc_info_pair, btc_info_timeframe)
        # Indicators
        # -----------------------------------------------------------------------------------------
        # RSI
        btc_info_4h['rsi_14'] = ta.RSI(btc_info_4h, timeperiod=14)

        # SMA
        btc_info_4h['sma_200'] = ta.SMA(btc_info_4h, timeperiod=200)

        # Add prefix
        # -----------------------------------------------------------------------------------------
        ignore_columns = ['date']
        btc_info_4h.rename(columns=lambda s: f"btc_{s}" if s not in ignore_columns else s, inplace=True)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] btc_info_4h_indicators took: {tok - tik:0.4f} seconds.")

        return btc_info_4h

    # BTC 1h Indicators
    # ---------------------------------------------------------------------------------------------
    def btc_info_1h_indicators(self, btc_info_pair, btc_info_timeframe, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        btc_info_1h = self.dp.get_pair_dataframe(btc_info_pair, btc_info_timeframe)
        # Indicators
        # -----------------------------------------------------------------------------------------
        # RSI
        btc_info_1h['rsi_14'] = ta.RSI(btc_info_1h, timeperiod=14)

        btc_info_1h['not_downtrend'] = ((btc_info_1h['close'] > btc_info_1h['close'].shift(2)) | (btc_info_1h['rsi_14'] > 50))

        # Add prefix
        # -----------------------------------------------------------------------------------------
        ignore_columns = ['date']
        btc_info_1h.rename(columns=lambda s: f"btc_{s}" if s not in ignore_columns else s, inplace=True)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] btc_info_1h_indicators took: {tok - tik:0.4f} seconds.")

        return btc_info_1h

    # BTC 15m Indicators
    # ---------------------------------------------------------------------------------------------
    def btc_info_15m_indicators(self, btc_info_pair, btc_info_timeframe, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        btc_info_15m = self.dp.get_pair_dataframe(btc_info_pair, btc_info_timeframe)
        # Indicators
        # -----------------------------------------------------------------------------------------
        btc_info_15m['rsi_14'] = ta.RSI(btc_info_15m, timeperiod=14)

        # Add prefix
        # -----------------------------------------------------------------------------------------
        ignore_columns = ['date']
        btc_info_15m.rename(columns=lambda s: f"btc_{s}" if s not in ignore_columns else s, inplace=True)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] btc_info_15m_indicators took: {tok - tik:0.4f} seconds.")

        return btc_info_15m

    # BTC 5m Indicators
    # ---------------------------------------------------------------------------------------------
    def btc_info_5m_indicators(self, btc_info_pair, btc_info_timeframe, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        btc_info_5m = self.dp.get_pair_dataframe(btc_info_pair, btc_info_timeframe)
        # Indicators
        # -----------------------------------------------------------------------------------------
        btc_info_5m['rsi_14'] = ta.RSI(btc_info_5m, timeperiod=14)

        # Add prefix
        # -----------------------------------------------------------------------------------------
        ignore_columns = ['date']
        btc_info_5m.rename(columns=lambda s: f"btc_{s}" if s not in ignore_columns else s, inplace=True)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] btc_info_5m_indicators took: {tok - tik:0.4f} seconds.")

        return btc_info_5m

    # BTC Indicator Switch Case
    # ---------------------------------------------------------------------------------------------
    def btc_info_switcher(self, btc_info_pair, btc_info_timeframe, metadata: dict) -> DataFrame:
        if btc_info_timeframe == '1d':
            return self.btc_info_1d_indicators(btc_info_pair, btc_info_timeframe, metadata)
        elif btc_info_timeframe == '4h':
            return self.btc_info_4h_indicators(btc_info_pair, btc_info_timeframe, metadata)
        elif btc_info_timeframe == '1h':
            return self.btc_info_1h_indicators(btc_info_pair, btc_info_timeframe, metadata)
        elif btc_info_timeframe == '15m':
            return self.btc_info_15m_indicators(btc_info_pair, btc_info_timeframe, metadata)
        elif btc_info_timeframe == '5m':
            return self.btc_info_5m_indicators(btc_info_pair, btc_info_timeframe, metadata)
        else:
            raise RuntimeError(f"{btc_info_timeframe} not supported as informative timeframe for BTC pair.")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        '''
        --> BTC informative indicators
        ___________________________________________________________________________________________
        '''
        if self.config['stake_currency'] in ['USDT','BUSD','USDC','DAI','TUSD','PAX','USD','EUR','GBP']:
            btc_info_pair = f"BTC/{self.config['stake_currency']}"
        else:
            btc_info_pair = "BTC/USDT"

        for btc_info_timeframe in self.btc_info_timeframes:
            btc_informative = self.btc_info_switcher(btc_info_pair, btc_info_timeframe, metadata)
            dataframe = merge_informative_pair(dataframe, btc_informative, self.timeframe, btc_info_timeframe, ffill=True)
            # Customize what we drop - in case we need to maintain some BTC informative ohlcv data
            # Default drop all
            drop_columns = {
                '1d':   [f"btc_{s}_{btc_info_timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']],
                '4h':   [f"btc_{s}_{btc_info_timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']],
                '1h':   [f"btc_{s}_{btc_info_timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']],
                '15m':  [f"btc_{s}_{btc_info_timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']],
                '5m':   [f"btc_{s}_{btc_info_timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']],
            }.get(btc_info_timeframe,[f"{s}_{btc_info_timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']])
            drop_columns.append(f"date_{btc_info_timeframe}")
            dataframe.drop(columns=dataframe.columns.intersection(drop_columns), inplace=True)

        '''
        --> Indicators on informative timeframes
        ___________________________________________________________________________________________
        '''
        for info_timeframe in self.info_timeframes:
            info_indicators = self.info_switcher(metadata, info_timeframe)
            dataframe = merge_informative_pair(dataframe, info_indicators, self.timeframe, info_timeframe, ffill=True)
            # Customize what we drop - in case we need to maintain some informative timeframe ohlcv data
            # Default drop all except base timeframe ohlcv data
            drop_columns = {
                '1d':   [f"{s}_{info_timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']],
                '4h':   [f"{s}_{info_timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']],
                '1h':   [f"{s}_{info_timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']],
                '15m':  [f"{s}_{info_timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']]
            }.get(info_timeframe,[f"{s}_{info_timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']])
            dataframe.drop(columns=dataframe.columns.intersection(drop_columns), inplace=True)

        '''
        --> The indicators for the base timeframe  (5m)
        ___________________________________________________________________________________________
        '''
        dataframe = self.base_tf_5m_indicators(metadata, dataframe)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] Populate indicators took a total of: {tok - tik:0.4f} seconds.")

        return dataframe

    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = []
        dataframe.loc[:, 'buy_tag'] = ''

        for buy_enable in self.buy_params:
            index = int(buy_enable.split('_')[2])
            item_buy_protection_list = [True]
            if self.buy_params[f'{buy_enable}']:

                # Buy conditions
                # -----------------------------------------------------------------------------------------
                item_buy_logic = []
                item_buy_logic.append(reduce(lambda x, y: x & y, item_buy_protection_list))

                # Condition #1 - Long mode bull. Uptrend.
                if index == 1:
                    # Protections
                    item_buy_logic.append(dataframe['close'] > dataframe['sma_200_4h'])
                    item_buy_logic.append(dataframe['sma_50'] > dataframe['sma_200'])
                    item_buy_logic.append(dataframe['sma_50_1h'] > dataframe['sma_200_1h'])
                    item_buy_logic.append(dataframe['sma_50_4h'] > dataframe['sma_200_4h'])
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_4h'] * 0.9))
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_1h'] * 0.9))
                    item_buy_logic.append(dataframe['close'] > dataframe['sup3_1d'])
                    item_buy_logic.append(dataframe['close'] < dataframe['res3_1d'])

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.01))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 50.0)

                item_buy_logic.append(dataframe['volume'] > 0)
                item_buy = reduce(lambda x, y: x & y, item_buy_logic)
                dataframe.loc[item_buy, 'buy_tag'] += f"{index} "
                conditions.append(item_buy)
                dataframe.loc[:, 'buy'] = item_buy

        if conditions:
            dataframe.loc[:, 'buy'] = reduce(lambda x, y: x | y, conditions)

        return dataframe

    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'sell'] = 0

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, **kwargs) -> bool:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)

        if(len(dataframe) < 1):
            return False

        dataframe = dataframe.iloc[-1].squeeze()

        if ((rate > dataframe['close'])):
            slippage = ((rate / dataframe['close']) - 1.0)

            if slippage < 0.038:
                return True
            else:
                log.warning(
                    "Cancelling buy for %s due to slippage %s",
                    pair, slippage
                )
                return False

        return True

# +---------------------------------------------------------------------------+
# |                              Custom Indicators                            |
# +---------------------------------------------------------------------------+

# Range midpoint acts as Support
def is_support(row_data) -> bool:
    conditions = []
    for row in range(len(row_data)-1):
        if row < len(row_data)//2:
            conditions.append(row_data[row] > row_data[row+1])
        else:
            conditions.append(row_data[row] < row_data[row+1])
    result = reduce(lambda x, y: x & y, conditions)
    return result

# Range midpoint acts as Resistance
def is_resistance(row_data) -> bool:
    conditions = []
    for row in range(len(row_data)-1):
        if row < len(row_data)//2:
            conditions.append(row_data[row] < row_data[row+1])
        else:
            conditions.append(row_data[row] > row_data[row+1])
    result = reduce(lambda x, y: x & y, conditions)
    return result

# Elliot Wave Oscillator
def ewo(dataframe, sma1_length=5, sma2_length=35):
    sma1 = ta.EMA(dataframe, timeperiod=sma1_length)
    sma2 = ta.EMA(dataframe, timeperiod=sma2_length)
    smadif = (sma1 - sma2) / dataframe['close'] * 100
    return smadif

# Chaikin Money Flow
def chaikin_money_flow(dataframe, n=20, fillna=False) -> Series:
    """Chaikin Money Flow (CMF)
    It measures the amount of Money Flow Volume over a specific period.
    http://stockcharts.com/school/doku.php?id=chart_school:technical_indicators:chaikin_money_flow_cmf
    Args:
        dataframe(pandas.Dataframe): dataframe containing ohlcv
        n(int): n period.
        fillna(bool): if True, fill nan values.
    Returns:
        pandas.Series: New feature generated.
    """
    mfv = ((dataframe['close'] - dataframe['low']) - (dataframe['high'] - dataframe['close'])) / (dataframe['high'] - dataframe['low'])
    mfv = mfv.fillna(0.0)  # float division by zero
    mfv *= dataframe['volume']
    cmf = (mfv.rolling(n, min_periods=0).sum()
           / dataframe['volume'].rolling(n, min_periods=0).sum())
    if fillna:
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)
    return Series(cmf, name='cmf')

# Williams %R
def williams_r(dataframe: DataFrame, period: int = 14) -> Series:
    """Williams %R, or just %R, is a technical analysis oscillator showing the current closing price in relation to the high and low
        of the past N days (for a given N). It was developed by a publisher and promoter of trading materials, Larry Williams.
        Its purpose is to tell whether a stock or commodity market is trading near the high or the low, or somewhere in between,
        of its recent trading range.
        The oscillator is on a negative scale, from −100 (lowest) up to 0 (highest).
    """

    highest_high = dataframe["high"].rolling(center=False, window=period).max()
    lowest_low = dataframe["low"].rolling(center=False, window=period).min()

    WR = Series(
        (highest_high - dataframe["close"]) / (highest_high - lowest_low),
        name=f"{period} Williams %R",
        )

    return WR * -100

# Volume Weighted Moving Average
def vwma(dataframe: DataFrame, length: int = 10):
    """Indicator: Volume Weighted Moving Average (VWMA)"""
    # Calculate Result
    pv = dataframe['close'] * dataframe['volume']
    vwma = Series(ta.SMA(pv, timeperiod=length) / ta.SMA(dataframe['volume'], timeperiod=length))
    vwma = vwma.fillna(0, inplace=True)
    return vwma

# Exponential moving average of a volume weighted simple moving average
def ema_vwma_osc(dataframe, len_slow_ma):
    slow_ema = Series(ta.EMA(vwma(dataframe, len_slow_ma), len_slow_ma))
    return ((slow_ema - slow_ema.shift(1)) / slow_ema.shift(1)) * 100

def t3_average(dataframe, length=5):
    """
    T3 Average by HPotter on Tradingview
    https://www.tradingview.com/script/qzoC9H1I-T3-Average/
    """
    df = dataframe.copy()

    df['xe1'] = ta.EMA(df['close'], timeperiod=length)
    df['xe1'].fillna(0, inplace=True)
    df['xe2'] = ta.EMA(df['xe1'], timeperiod=length)
    df['xe2'].fillna(0, inplace=True)
    df['xe3'] = ta.EMA(df['xe2'], timeperiod=length)
    df['xe3'].fillna(0, inplace=True)
    df['xe4'] = ta.EMA(df['xe3'], timeperiod=length)
    df['xe4'].fillna(0, inplace=True)
    df['xe5'] = ta.EMA(df['xe4'], timeperiod=length)
    df['xe5'].fillna(0, inplace=True)
    df['xe6'] = ta.EMA(df['xe5'], timeperiod=length)
    df['xe6'].fillna(0, inplace=True)
    b = 0.7
    c1 = -b * b * b
    c2 = 3 * b * b + 3 * b * b * b
    c3 = -6 * b * b - 3 * b - 3 * b * b * b
    c4 = 1 + 3 * b + b * b * b + 3 * b * b
    df['T3Average'] = c1 * df['xe6'] + c2 * df['xe5'] + c3 * df['xe4'] + c4 * df['xe3']

    return df['T3Average']

# Pivot Points - 3 variants - daily recommended
def pivot_points(dataframe: DataFrame, mode = 'fibonacci') -> Series:
    if mode == 'simple':
        hlc3_pivot = (dataframe['high'] + dataframe['low'] + dataframe['close']).shift(1) / 3
        res1 = hlc3_pivot * 2 - dataframe['low'].shift(1)
        sup1 = hlc3_pivot * 2 - dataframe['high'].shift(1)
        res2 = hlc3_pivot + (dataframe['high'] - dataframe['low']).shift()
        sup2 = hlc3_pivot - (dataframe['high'] - dataframe['low']).shift()
        res3 = hlc3_pivot * 2 + (dataframe['high'] - 2 * dataframe['low']).shift()
        sup3 = hlc3_pivot * 2 - (2 * dataframe['high'] - dataframe['low']).shift()
        return hlc3_pivot, res1, res2, res3, sup1, sup2, sup3
    elif mode == 'fibonacci':
        hlc3_pivot = (dataframe['high'] + dataframe['low'] + dataframe['close']).shift(1) / 3
        hl_range = (dataframe['high'] - dataframe['low']).shift(1)
        res1 = hlc3_pivot + 0.382 * hl_range
        sup1 = hlc3_pivot - 0.382 * hl_range
        res2 = hlc3_pivot + 0.618 * hl_range
        sup2 = hlc3_pivot - 0.618 * hl_range
        res3 = hlc3_pivot + 1 * hl_range
        sup3 = hlc3_pivot - 1 * hl_range
        return hlc3_pivot, res1, res2, res3, sup1, sup2, sup3
    elif mode == 'DeMark':
        demark_pivot_lt = (dataframe['low'] * 2 + dataframe['high'] + dataframe['close'])
        demark_pivot_eq = (dataframe['close'] * 2 + dataframe['low'] + dataframe['high'])
        demark_pivot_gt = (dataframe['high'] * 2 + dataframe['low'] + dataframe['close'])
        demark_pivot = np.where((dataframe['close'] < dataframe['open']), demark_pivot_lt, np.where((dataframe['close'] > dataframe['open']), demark_pivot_gt, demark_pivot_eq))
        dm_pivot = demark_pivot / 4
        dm_res = demark_pivot / 2 - dataframe['low']
        dm_sup = demark_pivot / 2 - dataframe['high']
        return dm_pivot, dm_res, dm_sup

# Heikin Ashi candles
def heikin_ashi(dataframe, smooth_inputs = False, smooth_outputs = False, length = 10):
    df = dataframe[['open','close','high','low']].copy().fillna(0)
    if smooth_inputs:
        df['open_s']  = ta.EMA(df['open'], timeframe = length)
        df['high_s']  = ta.EMA(df['high'], timeframe = length)
        df['low_s']   = ta.EMA(df['low'],  timeframe = length)
        df['close_s'] = ta.EMA(df['close'],timeframe = length)

        open_ha  = (df['open_s'].shift(1) + df['close_s'].shift(1)) / 2
        high_ha  = df.loc[:, ['high_s', 'open_s', 'close_s']].max(axis=1)
        low_ha   = df.loc[:, ['low_s', 'open_s', 'close_s']].min(axis=1)
        close_ha = (df['open_s'] + df['high_s'] + df['low_s'] + df['close_s'])/4
    else:
        open_ha  = (df['open'].shift(1) + df['close'].shift(1)) / 2
        high_ha  = df.loc[:, ['high', 'open', 'close']].max(axis=1)
        low_ha   = df.loc[:, ['low', 'open', 'close']].min(axis=1)
        close_ha = (df['open'] + df['high'] + df['low'] + df['close'])/4

    open_ha = open_ha.fillna(0)
    high_ha = high_ha.fillna(0)
    low_ha  = low_ha.fillna(0)
    close_ha = close_ha.fillna(0)

    if smooth_outputs:
        open_sha  = ta.EMA(open_ha, timeframe = length)
        high_sha  = ta.EMA(high_ha, timeframe = length)
        low_sha   = ta.EMA(low_ha, timeframe = length)
        close_sha = ta.EMA(close_ha, timeframe = length)

        return open_sha, close_sha, low_sha
    else:
        return open_ha, close_ha, low_ha

# Peak Percentage Change
def range_percent_change(self, dataframe: DataFrame, method, length: int) -> float:
    """
    Rolling Percentage Change Maximum across interval.

    :param dataframe: DataFrame The original OHLC dataframe
    :param method: High to Low / Open to Close
    :param length: int The length to look back
    """
    if method == 'HL':
        return (dataframe['high'].rolling(length).max() - dataframe['low'].rolling(length).min()) / dataframe['low'].rolling(length).min()
    elif method == 'OC':
        return (dataframe['open'].rolling(length).max() - dataframe['close'].rolling(length).min()) / dataframe['close'].rolling(length).min()
    else:
        raise ValueError(f"Method {method} not defined!")

# Percentage distance to top peak
def top_percent_change(self, dataframe: DataFrame, length: int) -> float:
    """
    Percentage change of the current close from the range maximum Open price

    :param dataframe: DataFrame The original OHLC dataframe
    :param length: int The length to look back
    """
    if length == 0:
        return (dataframe['open'] - dataframe['close']) / dataframe['close']
    else:
        return (dataframe['open'].rolling(length).max() - dataframe['close']) / dataframe['close']
