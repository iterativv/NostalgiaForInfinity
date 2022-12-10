import copy
import logging
import rapidjson
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
import talib.abstract as ta
import pandas as pd
import pandas_ta as pta
from freqtrade.strategy.interface import IStrategy
from freqtrade.strategy import merge_informative_pair
from pandas import DataFrame, Series
from functools import reduce, partial
from freqtrade.persistence import Trade
from datetime import datetime, timedelta
import time
from typing import Optional
import warnings

log = logging.getLogger(__name__)
#log.setLevel(logging.DEBUG)
warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)

#############################################################################################################
##                NostalgiaForInfinityX2 by iterativ                                                       ##
##           https://github.com/iterativv/NostalgiaForInfinity                                             ##
##                                                                                                         ##
##    Strategy for Freqtrade https://github.com/freqtrade/freqtrade                                        ##
##                                                                                                         ##
#############################################################################################################
##               GENERAL RECOMMENDATIONS                                                                   ##
##                                                                                                         ##
##   For optimal performance, suggested to use between 4 and 6 open trades, with unlimited stake.          ##
##   A pairlist with 40 to 80 pairs. Volume pairlist works well.                                           ##
##   Prefer stable coin (USDT, BUSDT etc) pairs, instead of BTC or ETH pairs.                              ##
##   Highly recommended to blacklist leveraged tokens (*BULL, *BEAR, *UP, *DOWN etc).                      ##
##   Ensure that you don't override any variables in you config.json. Especially                           ##
##   the timeframe (must be 5m).                                                                           ##
##     use_exit_signal must set to true (or not set at all).                                               ##
##     exit_profit_only must set to false (or not set at all).                                             ##
##     ignore_roi_if_entry_signal must set to true (or not set at all).                                    ##
##                                                                                                         ##
#############################################################################################################
##               DONATIONS                                                                                 ##
##                                                                                                         ##
##   BTC: bc1qvflsvddkmxh7eqhc4jyu5z5k6xcw3ay8jl49sk                                                       ##
##   ETH (ERC20): 0x83D3cFb8001BDC5d2211cBeBB8cB3461E5f7Ec91                                               ##
##   BEP20/BSC (USDT, ETH, BNB, ...): 0x86A0B21a20b39d16424B7c8003E4A7e12d78ABEe                           ##
##   TRC20/TRON (USDT, TRON, ...): TTAa9MX6zMLXNgWMhg7tkNormVHWCoq8Xk                                      ##
##                                                                                                         ##
##               REFERRAL LINKS                                                                            ##
##                                                                                                         ##
##  Binance: https://accounts.binance.com/en/register?ref=C68K26A9 (20% discount on trading fees)          ##
##  Kucoin: https://www.kucoin.com/r/af/QBSSS5J2 (20% lifetime discount on trading fees)                   ##
##  Gate.io: https://www.gate.io/signup/8054544 (20% discount on trading fees)                             ##
##  OKX: https://www.okx.com/join/11749725931 (20% discount on trading fees)                               ##
##  ByBit: https://partner.bybit.com/b/nfi                                                                 ##
##  Huobi: https://www.huobi.com/en-us/v/register/double-invite/?inviter_id=11345710&invite_code=ubpt2223  ##
##         (20% discount on trading fees)                                                                  ##
##  Bitvavo: https://account.bitvavo.com/create?a=D22103A4BC (no fees for the first € 1000)                ##
#############################################################################################################

class NostalgiaForInfinityX2(IStrategy):
    INTERFACE_VERSION = 3

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
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = True

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 480

    # Normal mode bull tags
    normal_mode_bull_tags = ['force_entry', '1', '2', '3', '4', '5', '6']
    # Normal mode bear tags
    normal_mode_bear_tags = ['11', '12', '13', '14', '15', '16']
    # Pump mode bull tags
    pump_mode_bull_tags = ['21']
    # Pump mode bear tags
    pump_mode_bear_tags = ['31']

    #############################################################
    # Buy side configuration

    buy_params = {
        # Enable/Disable conditions
        # -------------------------------------------------------
        "buy_condition_1_enable": True,
        "buy_condition_2_enable": True,
        "buy_condition_3_enable": True,
        "buy_condition_4_enable": True,
        "buy_condition_5_enable": True,
        "buy_condition_6_enable": True,

        "buy_condition_11_enable": True,
        "buy_condition_12_enable": True,
        "buy_condition_13_enable": True,
        "buy_condition_14_enable": True,
        "buy_condition_15_enable": True,
        "buy_condition_16_enable": True,

        "buy_condition_21_enable": True,

        "buy_condition_31_enable": True,
    }

    buy_protection_params = {}

    #############################################################
    # CACHES
    target_profit_cache = None
    #############################################################

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        if (('exit_profit_only' in self.config and self.config['exit_profit_only'])
                or ('sell_profit_only' in self.config and self.config['sell_profit_only'])):
            self.exit_profit_only = True
        if self.target_profit_cache is None:
            bot_name = ""
            if ('bot_name' in self.config):
                bot_name = self.config["bot_name"] + "-"
            self.target_profit_cache = Cache(
                self.config["user_data_dir"] / ("nfix2-profit_max-" + bot_name  + self.config["exchange"]["name"] + "-" + self.config["stake_currency"] +  ("-(backtest)" if (self.config['runmode'].value == 'backtest') else "") + ".json")
            )

        # If the cached data hasn't changed, it's a no-op
        self.target_profit_cache.save()

    def get_ticker_indicator(self):
        return int(self.timeframe[:-1])

    def exit_normal_bull(self, pair: str, current_rate: float, current_profit: float,
                         max_profit: float, max_loss: float,
                         last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5,
                         trade: 'Trade', current_time: 'datetime', enter_tags) -> tuple:
        sell = False

        # Original sell signals
        sell, signal_name = self.exit_normal_bull_signals(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Main sell signals
        if not sell:
            sell, signal_name = self.exit_normal_bull_main(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Williams %R based sells
        if not sell:
            sell, signal_name = self.exit_normal_bull_r(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Stoplosses
        if not sell:
            sell, signal_name = self.exit_normal_bull_stoploss(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Profit Target Signal
        # Check if pair exist on target_profit_cache
        if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
            previous_rate = self.target_profit_cache.data[pair]['rate']
            previous_profit = self.target_profit_cache.data[pair]['profit']
            previous_sell_reason = self.target_profit_cache.data[pair]['sell_reason']
            previous_time_profit_reached = datetime.fromisoformat(self.target_profit_cache.data[pair]['time_profit_reached'])

            sell_max, signal_name_max = self.normal_bull_exit_profit_target(pair, trade, current_time, current_rate, current_profit,
                                                                            last_candle, previous_candle_1,
                                                                            previous_rate, previous_profit, previous_sell_reason,
                                                                            previous_time_profit_reached, enter_tags)
            if sell_max and signal_name_max is not None:
                return True, f"{signal_name_max}_m"
            if (current_profit > (previous_profit + 0.03)):
                # Update the target, raise it.
                mark_pair, mark_signal = self.normal_bull_mark_profit_target(pair, True, previous_sell_reason, trade, current_time, current_rate, current_profit, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)

        # Add the pair to the list, if a sell triggered and conditions met
        if sell and signal_name is not None:
            previous_profit = None
            if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                previous_profit = self.target_profit_cache.data[pair]['profit']
            if (
                    (previous_profit is None)
                    or (previous_profit < current_profit)
            ):
                mark_pair, mark_signal = self.normal_bull_mark_profit_target(pair, sell, signal_name, trade, current_time, current_rate, current_profit, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
        else:
            if (
                    (current_profit >= 0.03)
            ):
                previous_profit = None
                if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                    previous_profit = self.target_profit_cache.data[pair]['profit']
                if (previous_profit is None) or (previous_profit < current_profit):
                    mark_signal = "exit_profit_normal_bull_max"
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)

        if (signal_name not in ["exit_profit_normal_bull_max", "exit_normal_bull_stoploss_doom"]):
            if sell and (signal_name is not None):
                return True, f"{signal_name}"

        return False, None

    def normal_bull_mark_profit_target(self, pair: str, sell: bool, signal_name: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float, last_candle, previous_candle_1) -> tuple:
        if sell and (signal_name is not None):
            return pair, signal_name

        return None, None

    def normal_bull_exit_profit_target(self, pair: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float, last_candle, previous_candle_1, previous_rate, previous_profit,  previous_sell_reason, previous_time_profit_reached, enter_tags) -> tuple:
        if (previous_sell_reason in ["exit_normal_bull_stoploss_doom"]):
            if (current_profit > 0.04):
                # profit is over the threshold, don't exit
                self._remove_profit_target(pair)
                return False, None
            if (current_profit < -0.18):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (current_profit < -0.1):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (current_profit < -0.04):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            else:
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
        elif (previous_sell_reason in ["exit_profit_normal_bull_max"]):
            if (current_profit < 0.01):
                if (current_profit < (previous_profit - 0.01)):
                    return True, previous_sell_reason
            elif (0.01 <= current_profit < 0.02):
                if (current_profit < (previous_profit - 0.02)):
                    return True, previous_sell_reason
            elif (0.02 <= current_profit < 0.03):
                if (current_profit < (previous_profit - 0.03)):
                    return True, previous_sell_reason
            elif (0.03 <= current_profit < 0.05):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (0.05 <= current_profit < 0.08):
                if (current_profit < (previous_profit - 0.05)):
                    return True, previous_sell_reason
            elif (0.08 <= current_profit < 0.12):
                if (current_profit < (previous_profit - 0.06)):
                    return True, previous_sell_reason
            elif (0.12 <= current_profit):
                if (current_profit < (previous_profit - 0.07)):
                    return True, previous_sell_reason
        else:
            return False, None

        return False, None

    def exit_normal_bull_signals(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Sell signal 1
        if (last_candle['rsi_14'] > 79.0) and (last_candle['rsi_14_4h'] > 75.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) and (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']) and (previous_candle_4['close'] > previous_candle_4['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_1_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_1_2_1'

        # Sell signal 2
        elif (last_candle['rsi_14'] > 80.0) and (last_candle['rsi_14_4h'] > 75.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_2_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_2_2_1'

        # Sell signal 3
        elif (last_candle['rsi_14'] > 85.0) and (last_candle['rsi_14_4h'] > 75.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_3_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_3_2_1'

        # Sell signal 4
        elif (last_candle['rsi_14'] > 80.0) and (last_candle['rsi_14_1h'] > 80.0) and (last_candle['rsi_14_4h'] > 75.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_4_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_4_2_1'

        # Sell signal 6
        elif (last_candle['close'] < last_candle['ema_200']) and (last_candle['close'] > last_candle['ema_50']) and (last_candle['rsi_14'] > 79.0):
            if (current_profit > 0.01):
                return True, 'exit_normal_bull_6_1'

        # Sell signal 7
        elif (last_candle['rsi_14_1h'] > 79.0) and (last_candle['crossed_below_ema_12_26']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_7_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_7_2_1'

        # Sell signal 8
        elif (last_candle['rsi_14_4h'] > 75.0) and (last_candle['close'] > last_candle['bb20_2_upp_1h'] * 1.08):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_8_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bull_8_2_1'

        return False, None

    def exit_normal_bull_main(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if (last_candle['close'] > last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 20.0):
                    return True, 'exit_normal_bull_o_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 28.0):
                    return True, 'exit_normal_bull_o_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 30.0):
                    return True, 'exit_normal_bull_o_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 32.0):
                    return True, 'exit_normal_bull_o_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 34.0):
                    return True, 'exit_normal_bull_o_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 36.0):
                    return True, 'exit_normal_bull_o_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 38.0):
                    return True, 'exit_normal_bull_o_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 40.0):
                    return True, 'exit_normal_bull_o_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'exit_normal_bull_o_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_normal_bull_o_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_normal_bull_o_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_normal_bull_o_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'exit_normal_bull_o_12'
        elif (last_candle['close'] < last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 22.0):
                    return True, 'exit_normal_bull_u_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 30.0):
                    return True, 'exit_normal_bull_u_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 32.0):
                    return True, 'exit_normal_bull_u_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 34.0):
                    return True, 'exit_normal_bull_u_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 36.0):
                    return True, 'exit_normal_bull_u_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 38.0):
                    return True, 'exit_normal_bull_u_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 40.0):
                    return True, 'exit_normal_bull_u_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'exit_normal_bull_u_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_normal_bull_u_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_normal_bull_u_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 48.0):
                    return True, 'exit_normal_bull_u_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_normal_bull_u_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_normal_bull_u_12'

        return False, None

    def exit_normal_bull_r(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if 0.01 > current_profit >= 0.001:
            if (last_candle['r_480'] > -0.1):
                return True, 'exit_normal_bull_w_0_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_0_2'
        elif 0.02 > current_profit >= 0.01:
            if (last_candle['r_480'] > -0.2):
                return True, 'exit_normal_bull_w_1_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_1_2'
        elif 0.03 > current_profit >= 0.02:
            if (last_candle['r_480'] > -0.3):
                return True, 'exit_normal_bull_w_2_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_2_2'
        elif 0.04 > current_profit >= 0.03:
            if (last_candle['r_480'] > -0.4):
                return True, 'exit_normal_bull_w_3_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_3_2'
        elif 0.05 > current_profit >= 0.04:
            if (last_candle['r_480'] > -0.5):
                return True, 'exit_normal_bull_w_4_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_4_2'
        elif 0.06 > current_profit >= 0.05:
            if (last_candle['r_480'] > -0.6):
                return True, 'exit_normal_bull_w_5_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_5_2'
        elif 0.07 > current_profit >= 0.06:
            if (last_candle['r_480'] > -0.7):
                return True, 'exit_normal_bull_w_6_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_6_2'
        elif 0.08 > current_profit >= 0.07:
            if (last_candle['r_480'] > -0.8):
                return True, 'exit_normal_bull_w_7_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_7_2'
        elif 0.09 > current_profit >= 0.08:
            if (last_candle['r_480'] > -0.9):
                return True, 'exit_normal_bull_w_8_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_8_2'
        elif 0.1 > current_profit >= 0.09:
            if (last_candle['r_480'] > -1.0):
                return True, 'exit_normal_bull_w_9_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_9_2'
        elif 0.12 > current_profit >= 0.1:
            if (last_candle['r_480'] > -1.1):
                return True, 'exit_normal_bull_w_10_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_10_2'
        elif 0.2 > current_profit >= 0.12:
            if (last_candle['r_480'] > -0.4):
                return True, 'exit_normal_bull_w_11_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bull_w_11_2'
        elif current_profit >= 0.2:
            if (last_candle['r_480'] > -0.2):
                return True, 'exit_normal_bull_w_12_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 80.0):
                return True, 'exit_normal_bull_w_12_2'

        return False, None

    def exit_normal_bull_stoploss(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Stoploss doom
        if (
                (current_profit < -0.1)
        ):
            return True, 'exit_normal_bull_stoploss_doom'

        return False, None

    def exit_normal_bear(self, pair: str, current_rate: float, current_profit: float,
                         max_profit: float, max_loss: float,
                         last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5,
                         trade: 'Trade', current_time: 'datetime', enter_tags) -> tuple:
        sell = False

        # Original sell signals
        sell, signal_name = self.exit_normal_bear_signals(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Main sell signals
        if not sell:
            sell, signal_name = self.exit_normal_bear_main(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Williams %R based sells
        if not sell:
            sell, signal_name = self.exit_normal_bear_r(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Stoplosses
        if not sell:
            sell, signal_name = self.exit_normal_bear_stoploss(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Profit Target Signal
        # Check if pair exist on target_profit_cache
        if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
            previous_rate = self.target_profit_cache.data[pair]['rate']
            previous_profit = self.target_profit_cache.data[pair]['profit']
            previous_sell_reason = self.target_profit_cache.data[pair]['sell_reason']
            previous_time_profit_reached = datetime.fromisoformat(self.target_profit_cache.data[pair]['time_profit_reached'])

            sell_max, signal_name_max = self.normal_bear_exit_profit_target(pair, trade, current_time, current_rate, current_profit,
                                                                            last_candle, previous_candle_1,
                                                                            previous_rate, previous_profit, previous_sell_reason,
                                                                            previous_time_profit_reached, enter_tags)
            if sell_max and signal_name_max is not None:
                return True, f"{signal_name_max}_m"
            if (current_profit > (previous_profit + 0.03)):
                # Update the target, raise it.
                mark_pair, mark_signal = self.normal_bear_mark_profit_target(pair, True, previous_sell_reason, trade, current_time, current_rate, current_profit, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)

        # Add the pair to the list, if a sell triggered and conditions met
        if sell and signal_name is not None:
            previous_profit = None
            if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                previous_profit = self.target_profit_cache.data[pair]['profit']
            if (
                    (previous_profit is None)
                    or (previous_profit < current_profit)
            ):
                mark_pair, mark_signal = self.normal_bear_mark_profit_target(pair, sell, signal_name, trade, current_time, current_rate, current_profit, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
        else:
            if (
                    (current_profit >= 0.03)
            ):
                previous_profit = None
                if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                    previous_profit = self.target_profit_cache.data[pair]['profit']
                if (previous_profit is None) or (previous_profit < current_profit):
                    mark_signal = "exit_profit_normal_bear_max"
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)

        if (signal_name not in ["exit_profit_normal_bear_max", "exit_normal_bear_stoploss_doom"]):
            if sell and (signal_name is not None):
                return True, f"{signal_name}"

        return False, None

    def normal_bear_mark_profit_target(self, pair: str, sell: bool, signal_name: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float, last_candle, previous_candle_1) -> tuple:
        if sell and (signal_name is not None):
            return pair, signal_name

        return None, None

    def normal_bear_exit_profit_target(self, pair: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float, last_candle, previous_candle_1, previous_rate, previous_profit,  previous_sell_reason, previous_time_profit_reached, enter_tags) -> tuple:
        if (previous_sell_reason in ["exit_normal_bear_stoploss_doom"]):
            if (current_profit > 0.04):
                # profit is over the threshold, don't exit
                self._remove_profit_target(pair)
                return False, None
            if (current_profit < -0.18):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (current_profit < -0.1):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (current_profit < -0.04):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            else:
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
        elif (previous_sell_reason in ["exit_profit_normal_bear_max"]):
            if (current_profit < 0.01):
                if (current_profit < (previous_profit - 0.01)):
                    return True, previous_sell_reason
            elif (0.01 <= current_profit < 0.02):
                if (current_profit < (previous_profit - 0.02)):
                    return True, previous_sell_reason
            elif (0.02 <= current_profit < 0.03):
                if (current_profit < (previous_profit - 0.03)):
                    return True, previous_sell_reason
            elif (0.03 <= current_profit < 0.05):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (0.05 <= current_profit < 0.08):
                if (current_profit < (previous_profit - 0.05)):
                    return True, previous_sell_reason
            elif (0.08 <= current_profit < 0.12):
                if (current_profit < (previous_profit - 0.06)):
                    return True, previous_sell_reason
            elif (0.12 <= current_profit):
                if (current_profit < (previous_profit - 0.07)):
                    return True, previous_sell_reason
        else:
            return False, None

        return False, None

    def exit_normal_bear_signals(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Sell signal 1
        if (last_candle['rsi_14'] > 78.0) and (last_candle['rsi_14_4h'] > 75.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) and (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']) and (previous_candle_4['close'] > previous_candle_4['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_1_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_1_2_1'

        # Sell signal 2
        elif (last_candle['rsi_14'] > 79.0) and (last_candle['rsi_14_4h'] > 75.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_2_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_2_2_1'

        # Sell signal 3
        elif (last_candle['rsi_14'] > 84.0) and (last_candle['rsi_14_4h'] > 75.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_3_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_3_2_1'

        # Sell signal 4
        elif (last_candle['rsi_14'] > 79.0) and (last_candle['rsi_14_1h'] > 79.0) and (last_candle['rsi_14_4h'] > 75.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_4_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_4_2_1'

        # Sell signal 6
        elif (last_candle['close'] < last_candle['ema_200']) and (last_candle['close'] > last_candle['ema_50']) and (last_candle['rsi_14'] > 78.5):
            if (current_profit > 0.01):
                return True, 'exit_normal_bear_6_1'

        # Sell signal 7
        elif (last_candle['rsi_14_1h'] > 79.0) and (last_candle['crossed_below_ema_12_26']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_7_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_7_2_1'

        # Sell signal 8
        elif (last_candle['close'] > last_candle['bb20_2_upp_1h'] * 1.07) and (last_candle['rsi_14_4h'] > 75.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_8_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_normal_bear_8_2_1'

        return False, None

    def exit_normal_bear_main(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if (last_candle['close'] > last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 22.0):
                    return True, 'exit_normal_bear_o_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 30.0):
                    return True, 'exit_normal_bear_o_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 32.0):
                    return True, 'exit_normal_bear_o_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 34.0):
                    return True, 'exit_normal_bear_o_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 36.0):
                    return True, 'exit_normal_bear_o_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 38.0):
                    return True, 'exit_normal_bear_o_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 40.0):
                    return True, 'exit_normal_bear_o_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'exit_normal_bear_o_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_normal_bear_o_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_normal_bear_o_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 48.0):
                    return True, 'exit_normal_bear_o_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_normal_bear_o_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_normal_bear_o_12'
        elif (last_candle['close'] < last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 24.0):
                    return True, 'exit_normal_bear_u_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 32.0):
                    return True, 'exit_normal_bear_u_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 34.0):
                    return True, 'exit_normal_bear_u_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 36.0):
                    return True, 'exit_normal_bear_u_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 38.0):
                    return True, 'exit_normal_bear_u_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 40.0):
                    return True, 'exit_normal_bear_u_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'exit_normal_bear_u_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_normal_bear_u_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_normal_bear_u_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 48.0):
                    return True, 'exit_normal_bear_u_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 50.0):
                    return True, 'exit_normal_bear_u_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 48.0):
                    return True, 'exit_normal_bear_u_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_normal_bear_u_12'

        return False, None

    def exit_normal_bear_r(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if 0.01 > current_profit >= 0.001:
            if (last_candle['r_480'] > -0.1):
                return True, 'exit_normal_bear_w_0_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_0_2'
        elif 0.02 > current_profit >= 0.01:
            if (last_candle['r_480'] > -0.2):
                return True, 'exit_normal_bear_w_1_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_1_2'
        elif 0.03 > current_profit >= 0.02:
            if (last_candle['r_480'] > -0.3):
                return True, 'exit_normal_bear_w_2_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_2_2'
        elif 0.04 > current_profit >= 0.03:
            if (last_candle['r_480'] > -0.4):
                return True, 'exit_normal_bear_w_3_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_3_2'
        elif 0.05 > current_profit >= 0.04:
            if (last_candle['r_480'] > -0.5):
                return True, 'exit_normal_bear_w_4_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_4_2'
        elif 0.06 > current_profit >= 0.05:
            if (last_candle['r_480'] > -0.6):
                return True, 'exit_normal_bear_w_5_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_5_2'
        elif 0.07 > current_profit >= 0.06:
            if (last_candle['r_480'] > -0.7):
                return True, 'exit_normal_bear_w_6_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_6_2'
        elif 0.08 > current_profit >= 0.07:
            if (last_candle['r_480'] > -0.8):
                return True, 'exit_normal_bear_w_7_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_7_2'
        elif 0.09 > current_profit >= 0.08:
            if (last_candle['r_480'] > -0.9):
                return True, 'exit_normal_bear_w_8_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_8_2'
        elif 0.1 > current_profit >= 0.09:
            if (last_candle['r_480'] > -1.0):
                return True, 'exit_normal_bear_w_9_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_9_2'
        elif 0.12 > current_profit >= 0.1:
            if (last_candle['r_480'] > -1.1):
                return True, 'exit_normal_bear_w_10_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_10_2'
        elif 0.2 > current_profit >= 0.12:
            if (last_candle['r_480'] > -0.4):
                return True, 'exit_normal_bear_w_11_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_normal_bear_w_11_2'
        elif current_profit >= 0.2:
            if (last_candle['r_480'] > -0.2):
                return True, 'exit_normal_bear_w_12_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 80.0):
                return True, 'exit_normal_bear_w_12_2'

        return False, None

    def exit_normal_bear_stoploss(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Stoploss doom
        if (
                (current_profit < -0.1)
        ):
            return True, 'exit_normal_bear_stoploss_doom'

        return False, None

    def exit_pump_bull(self, pair: str, current_rate: float, current_profit: float,
                         max_profit: float, max_loss: float,
                         last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5,
                         trade: 'Trade', current_time: 'datetime', enter_tags) -> tuple:
        sell = False

        # Original sell signals
        sell, signal_name = self.exit_pump_bull_signals(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Main sell signals
        if not sell:
            sell, signal_name = self.exit_pump_bull_main(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Williams %R based sells
        if not sell:
            sell, signal_name = self.exit_pump_bull_r(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Stoplosses
        if not sell:
            sell, signal_name = self.exit_pump_bull_stoploss(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Profit Target Signal
        # Check if pair exist on target_profit_cache
        if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
            previous_rate = self.target_profit_cache.data[pair]['rate']
            previous_profit = self.target_profit_cache.data[pair]['profit']
            previous_sell_reason = self.target_profit_cache.data[pair]['sell_reason']
            previous_time_profit_reached = datetime.fromisoformat(self.target_profit_cache.data[pair]['time_profit_reached'])

            sell_max, signal_name_max = self.pump_bull_exit_profit_target(pair, trade, current_time, current_rate, current_profit,
                                                                            last_candle, previous_candle_1,
                                                                            previous_rate, previous_profit, previous_sell_reason,
                                                                            previous_time_profit_reached, enter_tags)
            if sell_max and signal_name_max is not None:
                return True, f"{signal_name_max}_m"
            if (current_profit > (previous_profit + 0.03)):
                # Update the target, raise it.
                mark_pair, mark_signal = self.pump_bull_mark_profit_target(pair, True, previous_sell_reason, trade, current_time, current_rate, current_profit, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)

        # Add the pair to the list, if a sell triggered and conditions met
        if sell and signal_name is not None:
            previous_profit = None
            if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                previous_profit = self.target_profit_cache.data[pair]['profit']
            if (
                    (previous_profit is None)
                    or (previous_profit < current_profit)
            ):
                mark_pair, mark_signal = self.pump_bull_mark_profit_target(pair, sell, signal_name, trade, current_time, current_rate, current_profit, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
        else:
            if (
                    (current_profit >= 0.03)
            ):
                previous_profit = None
                if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                    previous_profit = self.target_profit_cache.data[pair]['profit']
                if (previous_profit is None) or (previous_profit < current_profit):
                    mark_signal = "exit_profit_pump_bull_max"
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)

        if (signal_name not in ["exit_profit_pump_bull_max", "exit_pump_bull_stoploss_doom"]):
            if sell and (signal_name is not None):
                return True, f"{signal_name}"

        return False, None

    def pump_bull_mark_profit_target(self, pair: str, sell: bool, signal_name: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float, last_candle, previous_candle_1) -> tuple:
        if sell and (signal_name is not None):
            return pair, signal_name

        return None, None

    def pump_bull_exit_profit_target(self, pair: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float, last_candle, previous_candle_1, previous_rate, previous_profit,  previous_sell_reason, previous_time_profit_reached, enter_tags) -> tuple:
        if (previous_sell_reason in ["exit_pump_bull_stoploss_doom"]):
            if (current_profit > 0.04):
                # profit is over the threshold, don't exit
                self._remove_profit_target(pair)
                return False, None
            if (current_profit < -0.18):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (current_profit < -0.1):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (current_profit < -0.04):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            else:
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
        elif (previous_sell_reason in ["exit_profit_pump_bull_max"]):
            if (current_profit < 0.01):
                if (current_profit < (previous_profit - 0.01)):
                    return True, previous_sell_reason
            elif (0.01 <= current_profit < 0.02):
                if (current_profit < (previous_profit - 0.02)):
                    return True, previous_sell_reason
            elif (0.02 <= current_profit < 0.03):
                if (current_profit < (previous_profit - 0.03)):
                    return True, previous_sell_reason
            elif (0.03 <= current_profit < 0.05):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (0.05 <= current_profit < 0.08):
                if (current_profit < (previous_profit - 0.05)):
                    return True, previous_sell_reason
            elif (0.08 <= current_profit < 0.12):
                if (current_profit < (previous_profit - 0.06)):
                    return True, previous_sell_reason
            elif (0.12 <= current_profit):
                if (current_profit < (previous_profit - 0.07)):
                    return True, previous_sell_reason
        else:
            return False, None

        return False, None

    def exit_pump_bull_signals(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Sell signal 1
        if (last_candle['rsi_14'] > 79.0) and (last_candle['rsi_14_4h'] > 75.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) and (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']) and (previous_candle_4['close'] > previous_candle_4['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_1_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_1_2_1'

        # Sell signal 2
        elif (last_candle['rsi_14'] > 80.0) and (last_candle['rsi_14_4h'] > 75.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_2_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_2_2_1'

        # Sell signal 3
        elif (last_candle['rsi_14'] > 85.0) and (last_candle['rsi_14_4h'] > 75.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_3_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_3_2_1'

        # Sell signal 4
        elif (last_candle['rsi_14'] > 80.0) and (last_candle['rsi_14_1h'] > 80.0) and (last_candle['rsi_14_4h'] > 75.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_4_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_4_2_1'

        # Sell signal 6
        elif (last_candle['close'] < last_candle['ema_200']) and (last_candle['close'] > last_candle['ema_50']) and (last_candle['rsi_14'] > 79.0):
            if (current_profit > 0.01):
                return True, 'exit_pump_bull_6_1'

        # Sell signal 7
        elif (last_candle['rsi_14_1h'] > 79.0) and (last_candle['crossed_below_ema_12_26']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_7_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_7_2_1'

        # Sell signal 8
        elif (last_candle['rsi_14_4h'] > 75.0) and (last_candle['close'] > last_candle['bb20_2_upp_1h'] * 1.08):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_8_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bull_8_2_1'

        return False, None

    def exit_pump_bull_main(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if (last_candle['close'] > last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 20.0):
                    return True, 'exit_pump_bull_o_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 28.0):
                    return True, 'exit_pump_bull_o_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 30.0):
                    return True, 'exit_pump_bull_o_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 32.0):
                    return True, 'exit_pump_bull_o_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 34.0):
                    return True, 'exit_pump_bull_o_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 36.0):
                    return True, 'exit_pump_bull_o_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 38.0):
                    return True, 'exit_pump_bull_o_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 40.0):
                    return True, 'exit_pump_bull_o_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'exit_pump_bull_o_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_pump_bull_o_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_pump_bull_o_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_pump_bull_o_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'exit_pump_bull_o_12'
        elif (last_candle['close'] < last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 22.0):
                    return True, 'exit_pump_bull_u_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 30.0):
                    return True, 'exit_pump_bull_u_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 32.0):
                    return True, 'exit_pump_bull_u_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 34.0):
                    return True, 'exit_pump_bull_u_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 36.0):
                    return True, 'exit_pump_bull_u_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 38.0):
                    return True, 'exit_pump_bull_u_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 40.0):
                    return True, 'exit_pump_bull_u_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'exit_pump_bull_u_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_pump_bull_u_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_pump_bull_u_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 48.0):
                    return True, 'exit_pump_bull_u_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_pump_bull_u_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_pump_bull_u_12'

        return False, None

    def exit_pump_bull_r(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if 0.01 > current_profit >= 0.001:
            if (last_candle['r_480'] > -0.1):
                return True, 'exit_pump_bull_w_0_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_0_2'
        elif 0.02 > current_profit >= 0.01:
            if (last_candle['r_480'] > -0.2):
                return True, 'exit_pump_bull_w_1_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_1_2'
        elif 0.03 > current_profit >= 0.02:
            if (last_candle['r_480'] > -0.3):
                return True, 'exit_pump_bull_w_2_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_2_2'
        elif 0.04 > current_profit >= 0.03:
            if (last_candle['r_480'] > -0.4):
                return True, 'exit_pump_bull_w_3_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_3_2'
        elif 0.05 > current_profit >= 0.04:
            if (last_candle['r_480'] > -0.5):
                return True, 'exit_pump_bull_w_4_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_4_2'
        elif 0.06 > current_profit >= 0.05:
            if (last_candle['r_480'] > -0.6):
                return True, 'exit_pump_bull_w_5_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_5_2'
        elif 0.07 > current_profit >= 0.06:
            if (last_candle['r_480'] > -0.7):
                return True, 'exit_pump_bull_w_6_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_6_2'
        elif 0.08 > current_profit >= 0.07:
            if (last_candle['r_480'] > -0.8):
                return True, 'exit_pump_bull_w_7_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_7_2'
        elif 0.09 > current_profit >= 0.08:
            if (last_candle['r_480'] > -0.9):
                return True, 'exit_pump_bull_w_8_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_8_2'
        elif 0.1 > current_profit >= 0.09:
            if (last_candle['r_480'] > -1.0):
                return True, 'exit_pump_bull_w_9_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_9_2'
        elif 0.12 > current_profit >= 0.1:
            if (last_candle['r_480'] > -1.1):
                return True, 'exit_pump_bull_w_10_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_10_2'
        elif 0.2 > current_profit >= 0.12:
            if (last_candle['r_480'] > -0.4):
                return True, 'exit_pump_bull_w_11_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bull_w_11_2'
        elif current_profit >= 0.2:
            if (last_candle['r_480'] > -0.2):
                return True, 'exit_pump_bull_w_12_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 80.0):
                return True, 'exit_pump_bull_w_12_2'

        return False, None

    def exit_pump_bull_stoploss(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Stoploss doom
        if (
                (current_profit < -0.1)
        ):
            return True, 'exit_pump_bull_stoploss_doom'

        return False, None

    def exit_pump_bear(self, pair: str, current_rate: float, current_profit: float,
                         max_profit: float, max_loss: float,
                         last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5,
                         trade: 'Trade', current_time: 'datetime', enter_tags) -> tuple:
        sell = False

        # Original sell signals
        sell, signal_name = self.exit_pump_bear_signals(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Main sell signals
        if not sell:
            sell, signal_name = self.exit_pump_bear_main(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Williams %R based sells
        if not sell:
            sell, signal_name = self.exit_pump_bear_r(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Stoplosses
        if not sell:
            sell, signal_name = self.exit_pump_bear_stoploss(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Profit Target Signal
        # Check if pair exist on target_profit_cache
        if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
            previous_rate = self.target_profit_cache.data[pair]['rate']
            previous_profit = self.target_profit_cache.data[pair]['profit']
            previous_sell_reason = self.target_profit_cache.data[pair]['sell_reason']
            previous_time_profit_reached = datetime.fromisoformat(self.target_profit_cache.data[pair]['time_profit_reached'])

            sell_max, signal_name_max = self.pump_bear_exit_profit_target(pair, trade, current_time, current_rate, current_profit,
                                                                            last_candle, previous_candle_1,
                                                                            previous_rate, previous_profit, previous_sell_reason,
                                                                            previous_time_profit_reached, enter_tags)
            if sell_max and signal_name_max is not None:
                return True, f"{signal_name_max}_m"
            if (current_profit > (previous_profit + 0.03)):
                # Update the target, raise it.
                mark_pair, mark_signal = self.pump_bear_mark_profit_target(pair, True, previous_sell_reason, trade, current_time, current_rate, current_profit, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)

        # Add the pair to the list, if a sell triggered and conditions met
        if sell and signal_name is not None:
            previous_profit = None
            if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                previous_profit = self.target_profit_cache.data[pair]['profit']
            if (
                    (previous_profit is None)
                    or (previous_profit < current_profit)
            ):
                mark_pair, mark_signal = self.pump_bear_mark_profit_target(pair, sell, signal_name, trade, current_time, current_rate, current_profit, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
        else:
            if (
                    (current_profit >= 0.03)
            ):
                previous_profit = None
                if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                    previous_profit = self.target_profit_cache.data[pair]['profit']
                if (previous_profit is None) or (previous_profit < current_profit):
                    mark_signal = "exit_profit_pump_bear_max"
                    self._set_profit_target(pair, mark_signal, current_rate, current_profit, current_time)

        if (signal_name not in ["exit_profit_pump_bear_max", "exit_pump_bear_stoploss_doom"]):
            if sell and (signal_name is not None):
                return True, f"{signal_name}"

        return False, None

    def pump_bear_mark_profit_target(self, pair: str, sell: bool, signal_name: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float, last_candle, previous_candle_1) -> tuple:
        if sell and (signal_name is not None):
            return pair, signal_name

        return None, None

    def pump_bear_exit_profit_target(self, pair: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float, last_candle, previous_candle_1, previous_rate, previous_profit,  previous_sell_reason, previous_time_profit_reached, enter_tags) -> tuple:
        if (previous_sell_reason in ["exit_pump_bear_stoploss_doom"]):
            if (current_profit > 0.04):
                # profit is over the threshold, don't exit
                self._remove_profit_target(pair)
                return False, None
            if (current_profit < -0.18):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (current_profit < -0.1):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (current_profit < -0.04):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            else:
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
        elif (previous_sell_reason in ["exit_profit_pump_bear_max"]):
            if (current_profit < 0.01):
                if (current_profit < (previous_profit - 0.01)):
                    return True, previous_sell_reason
            elif (0.01 <= current_profit < 0.02):
                if (current_profit < (previous_profit - 0.02)):
                    return True, previous_sell_reason
            elif (0.02 <= current_profit < 0.03):
                if (current_profit < (previous_profit - 0.03)):
                    return True, previous_sell_reason
            elif (0.03 <= current_profit < 0.05):
                if (current_profit < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (0.05 <= current_profit < 0.08):
                if (current_profit < (previous_profit - 0.05)):
                    return True, previous_sell_reason
            elif (0.08 <= current_profit < 0.12):
                if (current_profit < (previous_profit - 0.06)):
                    return True, previous_sell_reason
            elif (0.12 <= current_profit):
                if (current_profit < (previous_profit - 0.07)):
                    return True, previous_sell_reason
        else:
            return False, None

        return False, None

    def exit_pump_bear_signals(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Sell signal 1
        if (last_candle['rsi_14'] > 78.0) and (last_candle['rsi_14_4h'] > 75.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) and (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']) and (previous_candle_4['close'] > previous_candle_4['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_1_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_1_2_1'

        # Sell signal 2
        elif (last_candle['rsi_14'] > 79.0) and (last_candle['rsi_14_4h'] > 75.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_2_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_2_2_1'

        # Sell signal 3
        elif (last_candle['rsi_14'] > 84.0) and (last_candle['rsi_14_4h'] > 75.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_3_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_3_2_1'

        # Sell signal 4
        elif (last_candle['rsi_14'] > 79.0) and (last_candle['rsi_14_1h'] > 79.0) and (last_candle['rsi_14_4h'] > 75.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_4_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_4_2_1'

        # Sell signal 6
        elif (last_candle['close'] < last_candle['ema_200']) and (last_candle['close'] > last_candle['ema_50']) and (last_candle['rsi_14'] > 78.5):
            if (current_profit > 0.01):
                return True, 'exit_pump_bear_6_1'

        # Sell signal 7
        elif (last_candle['rsi_14_1h'] > 79.0) and (last_candle['crossed_below_ema_12_26']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_7_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_7_2_1'

        # Sell signal 8
        elif (last_candle['close'] > last_candle['bb20_2_upp_1h'] * 1.07) and (last_candle['rsi_14_4h'] > 75.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_8_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'exit_pump_bear_8_2_1'

        return False, None

    def exit_pump_bear_main(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if (last_candle['close'] > last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 22.0):
                    return True, 'exit_pump_bear_o_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 30.0):
                    return True, 'exit_pump_bear_o_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 32.0):
                    return True, 'exit_pump_bear_o_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 34.0):
                    return True, 'exit_pump_bear_o_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 36.0):
                    return True, 'exit_pump_bear_o_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 38.0):
                    return True, 'exit_pump_bear_o_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 40.0):
                    return True, 'exit_pump_bear_o_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'exit_pump_bear_o_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_pump_bear_o_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_pump_bear_o_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 48.0):
                    return True, 'exit_pump_bear_o_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_pump_bear_o_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_pump_bear_o_12'
        elif (last_candle['close'] < last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 24.0):
                    return True, 'exit_pump_bear_u_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 32.0):
                    return True, 'exit_pump_bear_u_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 34.0):
                    return True, 'exit_pump_bear_u_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 36.0):
                    return True, 'exit_pump_bear_u_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 38.0):
                    return True, 'exit_pump_bear_u_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 40.0):
                    return True, 'exit_pump_bear_u_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 42.0):
                    return True, 'exit_pump_bear_u_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 44.0):
                    return True, 'exit_pump_bear_u_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_pump_bear_u_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 48.0):
                    return True, 'exit_pump_bear_u_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 50.0):
                    return True, 'exit_pump_bear_u_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 48.0):
                    return True, 'exit_pump_bear_u_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 46.0):
                    return True, 'exit_pump_bear_u_12'

        return False, None

    def exit_pump_bear_r(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if 0.01 > current_profit >= 0.001:
            if (last_candle['r_480'] > -0.1):
                return True, 'exit_pump_bear_w_0_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_0_2'
        elif 0.02 > current_profit >= 0.01:
            if (last_candle['r_480'] > -0.2):
                return True, 'exit_pump_bear_w_1_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_1_2'
        elif 0.03 > current_profit >= 0.02:
            if (last_candle['r_480'] > -0.3):
                return True, 'exit_pump_bear_w_2_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_2_2'
        elif 0.04 > current_profit >= 0.03:
            if (last_candle['r_480'] > -0.4):
                return True, 'exit_pump_bear_w_3_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_3_2'
        elif 0.05 > current_profit >= 0.04:
            if (last_candle['r_480'] > -0.5):
                return True, 'exit_pump_bear_w_4_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_4_2'
        elif 0.06 > current_profit >= 0.05:
            if (last_candle['r_480'] > -0.6):
                return True, 'exit_pump_bear_w_5_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_5_2'
        elif 0.07 > current_profit >= 0.06:
            if (last_candle['r_480'] > -0.7):
                return True, 'exit_pump_bear_w_6_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_6_2'
        elif 0.08 > current_profit >= 0.07:
            if (last_candle['r_480'] > -0.8):
                return True, 'exit_pump_bear_w_7_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_7_2'
        elif 0.09 > current_profit >= 0.08:
            if (last_candle['r_480'] > -0.9):
                return True, 'exit_pump_bear_w_8_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_8_2'
        elif 0.1 > current_profit >= 0.09:
            if (last_candle['r_480'] > -1.0):
                return True, 'exit_pump_bear_w_9_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_9_2'
        elif 0.12 > current_profit >= 0.1:
            if (last_candle['r_480'] > -1.1):
                return True, 'exit_pump_bear_w_10_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_10_2'
        elif 0.2 > current_profit >= 0.12:
            if (last_candle['r_480'] > -0.4):
                return True, 'exit_pump_bear_w_11_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'exit_pump_bear_w_11_2'
        elif current_profit >= 0.2:
            if (last_candle['r_480'] > -0.2):
                return True, 'exit_pump_bear_w_12_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 80.0):
                return True, 'exit_pump_bear_w_12_2'

        return False, None

    def exit_pump_bear_stoploss(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Stoploss doom
        if (
                (current_profit < -0.1)
        ):
            return True, 'exit_pump_bear_stoploss_doom'

        return False, None

    def custom_exit(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                    current_profit: float, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        previous_candle_1 = dataframe.iloc[-2].squeeze()
        previous_candle_2 = dataframe.iloc[-3].squeeze()
        previous_candle_3 = dataframe.iloc[-4].squeeze()
        previous_candle_4 = dataframe.iloc[-5].squeeze()
        previous_candle_5 = dataframe.iloc[-6].squeeze()

        enter_tag = 'empty'
        if hasattr(trade, 'enter_tag') and trade.enter_tag is not None:
            enter_tag = trade.enter_tag
        enter_tags = enter_tag.split()

        profit = current_profit

        max_profit = ((trade.max_rate - trade.open_rate) / trade.open_rate)
        max_loss = ((trade.open_rate - trade.min_rate) / trade.min_rate)

        if hasattr(trade, 'select_filled_orders'):
            filled_entries = trade.select_filled_orders('enter_long')
            count_of_entries = len(filled_entries)
            if count_of_entries > 1:
                initial_entry = filled_entries[0]
                if (initial_entry is not None and initial_entry.average is not None):
                    max_profit = ((trade.max_rate - initial_entry.average) / initial_entry.average)
                    max_loss = ((initial_entry.average - trade.min_rate) / trade.min_rate)

        # Normal mode, bull
        if any(c in self.normal_mode_bull_tags for c in enter_tags):
            sell, signal_name = self.exit_normal_bull(pair, current_rate, profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {enter_tag})"

        # Normal mode, bear
        if any(c in self.normal_mode_bear_tags for c in enter_tags):
            sell, signal_name = self.exit_normal_bear(pair, current_rate, profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {enter_tag})"

        # Pump mpde, bull
        if any(c in self.pump_mode_bull_tags for c in enter_tags):
            sell, signal_name = self.exit_pump_bull(pair, current_rate, profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {enter_tag})"

        # Pump mode, bear
        if any(c in self.pump_mode_bear_tags for c in enter_tags):
            sell, signal_name = self.exit_pump_bear(pair, current_rate, profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {enter_tag})"

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

        informative_4h['rsi_14_max_6'] = informative_4h['rsi_14'].rolling(6).max()

        # EMA
        informative_4h['ema_12'] = ta.EMA(informative_4h, timeperiod=12)
        informative_4h['ema_26'] = ta.EMA(informative_4h, timeperiod=26)
        informative_4h['ema_50'] = ta.EMA(informative_4h, timeperiod=50)
        informative_4h['ema_100'] = ta.EMA(informative_4h, timeperiod=100)
        informative_4h['ema_200'] = ta.EMA(informative_4h, timeperiod=200)

        # SMA
        informative_4h['sma_12'] = ta.SMA(informative_4h, timeperiod=12)
        informative_4h['sma_26'] = ta.SMA(informative_4h, timeperiod=26)
        informative_4h['sma_50'] = ta.SMA(informative_4h, timeperiod=50)
        informative_4h['sma_200'] = ta.SMA(informative_4h, timeperiod=200)

        # Williams %R
        informative_4h['r_14'] = williams_r(informative_4h, period=14)
        informative_4h['r_480'] = williams_r(informative_4h, period=480)

        # CTI
        informative_4h['cti_20'] = pta.cti(informative_4h["close"], length=20)

        # S/R
        res_series = informative_4h['high'].rolling(window = 5, center=True).apply(lambda row: is_resistance(row), raw=True).shift(2)
        sup_series = informative_4h['low'].rolling(window = 5, center=True).apply(lambda row: is_support(row), raw=True).shift(2)
        informative_4h['res_level'] = Series(np.where(res_series, np.where(informative_4h['close'] > informative_4h['open'], informative_4h['close'], informative_4h['open']), float('NaN'))).ffill()
        informative_4h['res_hlevel'] = Series(np.where(res_series, informative_4h['high'], float('NaN'))).ffill()
        informative_4h['sup_level'] = Series(np.where(sup_series, np.where(informative_4h['close'] < informative_4h['open'], informative_4h['close'], informative_4h['open']), float('NaN'))).ffill()

        # Downtrend checks
        informative_4h['not_downtrend'] = ((informative_4h['close'] > informative_4h['close'].shift(2)) | (informative_4h['rsi_14'] > 50.0))

        # Wicks
        informative_4h['top_wick_pct'] = ((informative_4h['high'] - np.maximum(informative_4h['open'], informative_4h['close'])) / np.maximum(informative_4h['open'], informative_4h['close']))

        # Candle change
        informative_4h['change_pct'] = (informative_4h['close'] - informative_4h['open']) / informative_4h['open']

        # Max highs
        informative_4h['high_max_3'] = informative_4h['high'].rolling(3).max()
        informative_4h['high_max_12'] = informative_4h['high'].rolling(12).max()

        informative_4h['pct_change_high_max_1_12'] = (informative_4h['high'] - informative_4h['high_max_12']) / informative_4h['high_max_12']
        informative_4h['pct_change_high_max_3_12'] = (informative_4h['high_max_3'] - informative_4h['high_max_12']) / informative_4h['high_max_12']

        # Volume
        informative_4h['volume_mean_factor_6'] = informative_4h['volume'] / informative_4h['volume'].rolling(6).mean()

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

        # EMA
        informative_1h['ema_12'] = ta.EMA(informative_1h, timeperiod=12)
        informative_1h['ema_26'] = ta.EMA(informative_1h, timeperiod=26)
        informative_1h['ema_50'] = ta.EMA(informative_1h, timeperiod=50)
        informative_1h['ema_100'] = ta.EMA(informative_1h, timeperiod=100)
        informative_1h['ema_200'] = ta.EMA(informative_1h, timeperiod=200)

        # SMA
        informative_1h['sma_12'] = ta.SMA(informative_1h, timeperiod=12)
        informative_1h['sma_26'] = ta.SMA(informative_1h, timeperiod=26)
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

        # CTI
        informative_1h['cti_20'] = pta.cti(informative_1h["close"], length=20)

        # CRSI
        crsi_closechange = informative_1h['close'] / informative_1h['close'].shift(1)
        crsi_updown = np.where(crsi_closechange.gt(1), 1.0, np.where(crsi_closechange.lt(1), -1.0, 0.0))
        informative_1h['crsi'] =  (ta.RSI(informative_1h['close'], timeperiod=3) + ta.RSI(crsi_updown, timeperiod=2) + crsi_closechange.rolling(window=101).apply(lambda x: len(x[x < x.iloc[-1]]) / (len(x)-1))) / 3

        # S/R
        res_series = informative_1h['high'].rolling(window = 5, center=True).apply(lambda row: is_resistance(row), raw=True).shift(2)
        sup_series = informative_1h['low'].rolling(window = 5, center=True).apply(lambda row: is_support(row), raw=True).shift(2)
        informative_1h['res_level'] = Series(np.where(res_series, np.where(informative_1h['close'] > informative_1h['open'], informative_1h['close'], informative_1h['open']), float('NaN'))).ffill()
        informative_1h['res_hlevel'] = Series(np.where(res_series, informative_1h['high'], float('NaN'))).ffill()
        informative_1h['sup_level'] = Series(np.where(sup_series, np.where(informative_1h['close'] < informative_1h['open'], informative_1h['close'], informative_1h['open']), float('NaN'))).ffill()

        # Pump protections
        informative_1h['hl_pct_change_48'] = range_percent_change(self, informative_1h, 'HL', 48)
        informative_1h['hl_pct_change_36'] = range_percent_change(self, informative_1h, 'HL', 36)
        informative_1h['hl_pct_change_24'] = range_percent_change(self, informative_1h, 'HL', 24)
        informative_1h['hl_pct_change_12'] = range_percent_change(self, informative_1h, 'HL', 12)
        informative_1h['hl_pct_change_6'] = range_percent_change(self, informative_1h, 'HL', 6)

        # Downtrend checks
        informative_1h['not_downtrend'] = ((informative_1h['close'] > informative_1h['close'].shift(2)) | (informative_1h['rsi_14'] > 50.0))

        informative_1h['is_downtrend_3'] = ((informative_1h['close'] < informative_1h['open']) & (informative_1h['close'].shift(1) < informative_1h['open'].shift(1)) & (informative_1h['close'].shift(2) < informative_1h['open'].shift(2)))

        informative_1h['is_downtrend_5'] = ((informative_1h['close'] < informative_1h['open']) & (informative_1h['close'].shift(1) < informative_1h['open'].shift(1)) & (informative_1h['close'].shift(2) < informative_1h['open'].shift(2)) & (informative_1h['close'].shift(3) < informative_1h['open'].shift(3)) & (informative_1h['close'].shift(4) < informative_1h['open'].shift(4)))

        # Wicks
        informative_1h['top_wick_pct'] = ((informative_1h['high'] - np.maximum(informative_1h['open'], informative_1h['close'])) / np.maximum(informative_1h['open'], informative_1h['close']))

        # Candle change
        informative_1h['change_pct'] = (informative_1h['close'] - informative_1h['open']) / informative_1h['open']

        # Max highs
        informative_1h['high_max_3'] = informative_1h['high'].rolling(3).max()
        informative_1h['high_max_6'] = informative_1h['high'].rolling(6).max()
        informative_1h['high_max_12'] = informative_1h['high'].rolling(12).max()
        informative_1h['high_max_24'] = informative_1h['high'].rolling(24).max()

        informative_1h['pct_change_high_max_3_12'] = (informative_1h['high_max_3'] - informative_1h['high_max_12']) / informative_1h['high_max_12']
        informative_1h['pct_change_high_max_6_12'] = (informative_1h['high_max_6'] - informative_1h['high_max_12']) / informative_1h['high_max_12']
        informative_1h['pct_change_high_max_6_24'] = (informative_1h['high_max_6'] - informative_1h['high_max_24']) / informative_1h['high_max_24']

        # Volume
        informative_1h['volume_mean_factor_12'] = informative_1h['volume'] / informative_1h['volume'].rolling(12).mean()

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

        # RSI
        informative_15m['rsi_14'] = ta.RSI(informative_15m, timeperiod=14)

        # SMA
        informative_15m['sma_200'] = ta.SMA(informative_15m, timeperiod=200)

        # CTI
        informative_15m['cti_20'] = pta.cti(informative_15m["close"], length=20)

        # CRSI
        crsi_closechange = informative_15m['close'] / informative_15m['close'].shift(1)
        crsi_updown = np.where(crsi_closechange.gt(1), 1.0, np.where(crsi_closechange.lt(1), -1.0, 0.0))
        informative_15m['crsi'] =  (ta.RSI(informative_15m['close'], timeperiod=3) + ta.RSI(crsi_updown, timeperiod=2) + crsi_closechange.rolling(window=101).apply(lambda x: len(x[x < x.iloc[-1]]) / (len(x)-1))) / 3

        # Downtrend check
        informative_15m['not_downtrend'] = ((informative_15m['close'] > informative_15m['open']) | (informative_15m['close'].shift(1) > informative_15m['open'].shift(1)) | (informative_15m['close'].shift(2) > informative_15m['open'].shift(2)) | (informative_15m['rsi_14'] > 50.0) | (informative_15m['crsi'] > 20.0))

        # Volume
        informative_15m['volume_mean_factor_12'] = informative_15m['volume'] / informative_15m['volume'].rolling(12).mean()

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

        dataframe['ema_200_pct_change_144'] = ((dataframe['ema_200'] - dataframe['ema_200'].shift(144)) / dataframe['ema_200'].shift(144))
        dataframe['ema_200_pct_change_288'] = ((dataframe['ema_200'] - dataframe['ema_200'].shift(288)) / dataframe['ema_200'].shift(288))

        # SMA
        dataframe['sma_50'] = ta.SMA(dataframe, timeperiod=50)
        dataframe['sma_200'] = ta.SMA(dataframe, timeperiod=200)

        # BB 20 - STD2
        bb_20_std2 = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb20_2_low'] = bb_20_std2['lower']
        dataframe['bb20_2_mid'] = bb_20_std2['mid']
        dataframe['bb20_2_upp'] = bb_20_std2['upper']

        # BB 40 - STD2
        bb_40_std2 = qtpylib.bollinger_bands(dataframe['close'], window=40, stds=2)
        dataframe['bb40_2_low'] = bb_40_std2['lower']
        dataframe['bb40_2_mid'] = bb_40_std2['mid']
        dataframe['bb40_2_delta'] = (bb_40_std2['mid'] - dataframe['bb40_2_low']).abs()
        dataframe['bb40_2_tail'] = (dataframe['close'] - dataframe['bb40_2_low']).abs()

        # Williams %R
        dataframe['r_14'] = williams_r(dataframe, period=14)
        dataframe['r_480'] = williams_r(dataframe, period=480)

        # Heiken Ashi
        heikinashi = qtpylib.heikinashi(dataframe)
        dataframe['ha_open'] = heikinashi['open']
        dataframe['ha_close'] = heikinashi['close']
        dataframe['ha_high'] = heikinashi['high']
        dataframe['ha_low'] = heikinashi['low']

        # Dip protection
        dataframe['tpct_change_0']   = top_percent_change(self, dataframe, 0)
        dataframe['tpct_change_2']   = top_percent_change(self, dataframe, 2)
        dataframe['tpct_change_12']  = top_percent_change(self, dataframe, 12)
        dataframe['tpct_change_144'] = top_percent_change(self, dataframe, 144)
        # 3 hours, protect against wicks
        dataframe['hl_pct_change_36'] = range_percent_change(self, dataframe, 'HL', 36)
        # 12 hours
        dataframe['hl_pct_change_144'] = range_percent_change(self, dataframe, 'HL', 144)

        # Close max
        dataframe['close_max_48'] = dataframe['close'].rolling(48).max()
        dataframe['close_max_72'] = dataframe['close'].rolling(72).max()
        dataframe['close_max_144'] = dataframe['close'].rolling(144).max()

        dataframe['pct_close_max_48'] = (dataframe['close_max_48'] - dataframe['close']) / dataframe['close']

        # Close delta
        dataframe['close_delta'] = (dataframe['close'] - dataframe['close'].shift()).abs()

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

        # Bull market or not
        btc_info_4h['is_bull'] = btc_info_4h['close'] > btc_info_4h['sma_200']

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

        # RSI
        btc_info_5m['rsi_14'] = ta.RSI(btc_info_5m, timeperiod=14)

        # Close max
        btc_info_5m['close_max_24'] = btc_info_5m['close'].rolling(24).max()
        btc_info_5m['close_max_72'] = btc_info_5m['close'].rolling(72).max()

        btc_info_5m['pct_close_max_24'] = (btc_info_5m['close_max_24'] - btc_info_5m['close']) / btc_info_5m['close']
        btc_info_5m['pct_close_max_72'] = (btc_info_5m['close_max_72'] - btc_info_5m['close']) / btc_info_5m['close']

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

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = []
        dataframe.loc[:, 'enter_tag'] = ''

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
                    item_buy_logic.append(dataframe['btc_is_bull_4h'])
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append((dataframe['tpct_change_2'] < 0.06))
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))
                    item_buy_logic.append(dataframe['hl_pct_change_36'] < 0.3)
                    item_buy_logic.append(dataframe['hl_pct_change_24_1h'] < 3.0)

                    item_buy_logic.append(dataframe['sma_12_4h'] > dataframe['sma_26_4h'])

                    item_buy_logic.append(dataframe['sma_200'] > dataframe['sma_200'].shift(36))

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.85)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['r_480_4h'] < -25.0)

                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append(dataframe['not_downtrend_4h'])

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.016))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 1.0))

                # Condition #2 - Normal mode bull.
                if index == 2:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'])
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))

                    item_buy_logic.append(dataframe['ema_12_4h'] > dataframe['sma_26_4h'])

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.88)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 80.0)

                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.1)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.1)
                                          | (dataframe['rsi_14_4h'].shift(48) < 80.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] > 0.0)
                                          | (dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 4.0))
                                          | (dataframe['rsi_14_4h'] < 50.0))
                    item_buy_logic.append((dataframe['pct_change_high_max_3_12_1h'] > -0.12)
                                          | (dataframe['cti_20_1h'] < 0.8)
                                          | (dataframe['volume_mean_factor_12_1h'] > 0.1))
                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * 0.02))
                    item_buy_logic.append(dataframe['close_delta'].gt(dataframe['close'] * 0.02))
                    item_buy_logic.append(dataframe['bb40_2_tail'].lt(dataframe['bb40_2_delta'] * 0.18))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))

                # Condition #3 - Normal mode bull.
                if index == 3:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'])
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.26))

                    item_buy_logic.append(dataframe['ema_12_1h'] > dataframe['ema_200_1h'])

                    item_buy_logic.append(dataframe['ema_12_4h'] > dataframe['ema_200_4h'])

                    item_buy_logic.append(dataframe['rsi_14_4h'] < 75.0)

                    item_buy_logic.append(dataframe['not_downtrend_15m'])
                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append(dataframe['not_downtrend_4h'])

                    # Logic
                    item_buy_logic.append(dataframe['close'] > (dataframe['ema_200'] * 0.95))
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_200'] * 1.1))
                    item_buy_logic.append(dataframe['rsi_14'] < 36.0)
                    item_buy_logic.append(dataframe['ha_close'] > dataframe['ha_open'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.02))

                # Condition #4 - Normal mode bull.
                if index == 4:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'])
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.36))
                    item_buy_logic.append(dataframe['hl_pct_change_36'] < 0.3)

                    item_buy_logic.append(dataframe['r_480_1h'] < -25.0)
                    item_buy_logic.append(dataframe['r_480_4h'] < -4.0)
                    item_buy_logic.append(dataframe['crsi_15m'] > 14.0)
                    item_buy_logic.append(dataframe['crsi_1h'] > 16.0)

                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.018))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.996))

                # Condition #5 - Normal mode bull.
                if index == 5:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'])
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.36))

                    item_buy_logic.append(dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96))

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.9)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 85.0)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 75.0)

                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.08)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.16))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['rsi_14'] < 36.0)

                # Condition #6 - Normal mode bull.
                if index == 6:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'])
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.36))

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.9)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 85.0)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 75.0)

                    item_buy_logic.append(dataframe['not_downtrend_15m'])
                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)
                    # current 4h red and previous green with long top wick
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.08)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.16))
                    # current 4h red and previous green with high RSI
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.1)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.1)
                                          | (dataframe['rsi_14_4h'].shift(48) < 75.0))
                    # current 4h green and RSI high SMA 200 is negative
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.12)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96)))
                    # curent 4h and previous 4h red and RSI in last 6 4h high,
                    # low volume on current 4h
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['change_pct_4h'].shift(48) > -0.04)
                                          | (dataframe['rsi_14_max_6_4h'] < 80.0)
                                          | (dataframe['volume_mean_factor_6_4h'] > 0.7))
                    # current 4h green with top wick, previous 4h red, 24 pump
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.02)
                                          | (dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 2.0))
                                          | (dataframe['change_pct_4h'].shift(48) > -0.02)
                                          | (dataframe['hl_pct_change_48_1h'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < 0.9)
                                          | (dataframe['cti_20_1h'] < 0.8))
                    item_buy_logic.append((dataframe['cti_20_1h'] < 0.7)
                                          | (dataframe['r_14_4h'] < -25.0)
                                          | (dataframe['sma_200_15m'] > dataframe['sma_200_15m'].shift(12))
                                          | (dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96)))
                    # current 1h red, previous 1h green
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.04)
                                          | (dataframe['change_pct_1h'].shift(12) < 0.04)
                                          |(dataframe['cti_20_1h'].shift(12) < 0.8)
                                          | (dataframe['r_14_1h'].shift(12) < -10.0)
                                          | (dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96)))
                    item_buy_logic.append((dataframe['crsi_15m'] > 10.0)
                                          | (dataframe['sma_200_15m'] > dataframe['sma_200_15m'].shift(12))
                                          | (dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96)))
                    # curent 1h red, previous 1h long green with top wick
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.04) |
                                          (dataframe['change_pct_1h'].shift(12) < 0.08) |
                                          (dataframe['top_wick_pct_1h'].shift(12) < 0.08) |
                                          (dataframe['rsi_14_1h'].shift(12) < 85.0))
                    item_buy_logic.append((dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96))
                                          | (dataframe['volume_mean_factor_12_15m'] > 0.1))
                    # current 1h red and CTI 1h high
                    # current 4h red and CTI 4h high
                    # previous 4h green and CTI 4h high
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.02)
                                          | (dataframe['cti_20_1h'] < 0.85)
                                          | (dataframe['change_pct_4h'] > -0.08)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.08)
                                          | (dataframe['cti_20_4h'].shift(48) < 0.8))
                    # current 4h with very long top wick
                    item_buy_logic.append((dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 20.0)))
                    item_buy_logic.append((dataframe['cti_20_1h'] < 0.8)
                                          | (dataframe['sma_200_15m'] > dataframe['sma_200_15m'].shift(12))
                                          | (dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96)))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_26'] * 0.94))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.996))

                # Condition #11 - Normal mode bear.
                if index == 11:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'] == False)
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))
                    item_buy_logic.append(dataframe['hl_pct_change_24_1h'] < 3.0)

                    item_buy_logic.append(dataframe['sma_200'] > dataframe['sma_200'].shift(36))
                    item_buy_logic.append(dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(48))
                    item_buy_logic.append(dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96))

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.88)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.88)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 80.0)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 80.0)
                    item_buy_logic.append(dataframe['r_14_4h'] < -5.0)

                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append((dataframe['is_downtrend_3_1h'] == False)
                                          | (dataframe['crsi_1h'] > 20.0))
                    item_buy_logic.append(dataframe['is_downtrend_5_1h'] == False)
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)
                    item_buy_logic.append(dataframe['top_wick_pct_4h'] < 0.24)
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < 0.1)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.2)
                                          | (dataframe['top_wick_pct_4h'].shift(96) < 0.2))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.016))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 1.0))

                # Condition #12 - Normal mode bear.
                if index == 12:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'] == False)
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.025)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.025)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))

                    item_buy_logic.append(dataframe['ema_12_1h'] > dataframe['sma_26_1h'])

                    item_buy_logic.append(dataframe['sma_12_4h'] > dataframe['sma_26_4h'])

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.9)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 80.0)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 80.0)

                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append((dataframe['pct_change_high_max_1_12_4h'] > -0.25)
                                          | (dataframe['ema_12_4h'] > dataframe['ema_200_4h']))
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.1)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.1)
                                          | (dataframe['rsi_14_4h'].shift(48) < 80.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.08)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.16))
                    item_buy_logic.append((dataframe['change_pct_4h'] > 0.0)
                                          | (dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 4.0))
                                          | (dataframe['rsi_14_4h'] < 50.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.04)
                                          | (dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 2.0))
                                          | (dataframe['rsi_14_4h'] < 50.0))
                    item_buy_logic.append(dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 8.0))
                    item_buy_logic.append((dataframe['pct_change_high_max_3_12_1h'] > -0.12)
                                          | (dataframe['cti_20_1h'] < 0.8)
                                          | (dataframe['volume_mean_factor_12_1h'] > 0.1))
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.05)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.05)
                                          | (dataframe['rsi_14_4h'].shift(48) < 80.0))

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * 0.04))
                    item_buy_logic.append(dataframe['close_delta'].gt(dataframe['close'] * 0.026))
                    item_buy_logic.append(dataframe['bb40_2_tail'].lt(dataframe['bb40_2_delta'] * 0.4))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))

                # Condition #13 - Normal mode bear.
                if index == 13:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'] == False)
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.025)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.025)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.24))

                    item_buy_logic.append(dataframe['rsi_14_4h'] < 75.0)

                    item_buy_logic.append(dataframe['ema_12_1h'] > dataframe['ema_200_1h'])

                    item_buy_logic.append(dataframe['ema_12_4h'] > dataframe['ema_200_4h'])

                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.1)
                                          | (dataframe['top_wick_pct_4h'] < 0.16)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] > 0.0)
                                          | (dataframe['top_wick_pct_4h'] < 0.1)
                                          | (dataframe['ema_12_4h'] > dataframe['ema_200_4h']))

                    # Logic
                    item_buy_logic.append(dataframe['close'] > (dataframe['ema_200'] * 0.95))
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_200'] * 1.1))
                    item_buy_logic.append(dataframe['rsi_14'] < 36.0)
                    item_buy_logic.append(dataframe['ha_close'] > dataframe['ha_open'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.024))

                # Condition #14 - Normal mode bear.
                if index == 14:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'] == False)
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.36))
                    item_buy_logic.append(dataframe['hl_pct_change_36'] < 0.3)

                    item_buy_logic.append(dataframe['r_480_1h'] < -25.0)
                    item_buy_logic.append(dataframe['r_480_4h'] < -4.0)
                    item_buy_logic.append(dataframe['crsi_15m'] > 14.0)
                    item_buy_logic.append(dataframe['crsi_1h'] > 16.0)

                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.018))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.996))

                # Condition #15 - Normal mode bear.
                if index == 15:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'] == False)
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.36))

                    item_buy_logic.append(dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96))

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.9)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 85.0)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 75.0)

                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.08)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.16))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['rsi_14'] < 36.0)

                # Condition #16 - Normal mode bear.
                if index == 16:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'] == False)
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.36))

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.9)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 85.0)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 75.0)

                    item_buy_logic.append(dataframe['not_downtrend_15m'])
                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)
                    # current 4h red and previous green with long top wick
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.08)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.16))
                    # current 4h red and previous green with high RSI
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.1)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.1)
                                          | (dataframe['rsi_14_4h'].shift(48) < 75.0))
                    # current 4h green and RSI high SMA 200 is negative
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.12)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96)))
                    # curent 4h and previous 4h red and RSI in last 6 4h high,
                    # low volume on current 4h
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['change_pct_4h'].shift(48) > -0.04)
                                          | (dataframe['rsi_14_max_6_4h'] < 80.0)
                                          | (dataframe['volume_mean_factor_6_4h'] > 0.7))
                    # current 4h green with top wick, previous 4h red, 24 pump
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.02)
                                          | (dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 2.0))
                                          | (dataframe['change_pct_4h'].shift(48) > -0.02)
                                          | (dataframe['hl_pct_change_48_1h'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < 0.9)
                                          | (dataframe['cti_20_1h'] < 0.8))
                    item_buy_logic.append((dataframe['cti_20_1h'] < 0.7)
                                          | (dataframe['r_14_4h'] < -25.0)
                                          | (dataframe['sma_200_15m'] > dataframe['sma_200_15m'].shift(12))
                                          | (dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96)))
                    # current 1h red, previous 1h green
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.04)
                                          | (dataframe['change_pct_1h'].shift(12) < 0.04)
                                          |(dataframe['cti_20_1h'].shift(12) < 0.8)
                                          | (dataframe['r_14_1h'].shift(12) < -10.0)
                                          | (dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96)))
                    item_buy_logic.append((dataframe['crsi_15m'] > 10.0)
                                          | (dataframe['sma_200_15m'] > dataframe['sma_200_15m'].shift(12))
                                          | (dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96)))
                    # curent 1h red, previous 1h long green with top wick
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.04) |
                                          (dataframe['change_pct_1h'].shift(12) < 0.08) |
                                          (dataframe['top_wick_pct_1h'].shift(12) < 0.08) |
                                          (dataframe['rsi_14_1h'].shift(12) < 85.0))
                    item_buy_logic.append((dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96))
                                          | (dataframe['volume_mean_factor_12_15m'] > 0.1))
                    # current 1h red and CTI 1h high
                    # current 4h red and CTI 4h high
                    # previous 4h green and CTI 4h high
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.02)
                                          | (dataframe['cti_20_1h'] < 0.85)
                                          | (dataframe['change_pct_4h'] > -0.08)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.08)
                                          | (dataframe['cti_20_4h'].shift(48) < 0.8))
                    # current 4h with very long top wick
                    item_buy_logic.append((dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 20.0)))
                    item_buy_logic.append((dataframe['cti_20_1h'] < 0.8)
                                          | (dataframe['sma_200_15m'] > dataframe['sma_200_15m'].shift(12))
                                          | (dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                                          | (dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96)))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_26'] * 0.94))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.996))

                # Condition #21 - Pump mode bull.
                if index == 21:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'])
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.2))
                    item_buy_logic.append(dataframe['close_max_72'] < (dataframe['close'] * 1.24))
                    item_buy_logic.append(dataframe['close_max_144'] < (dataframe['close'] * 1.3))

                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(96))
                    item_buy_logic.append(dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                    item_buy_logic.append(dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96))

                    item_buy_logic.append(dataframe['close'] > dataframe['ema_200'])

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.9)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 80.0)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 80.0)

                    item_buy_logic.append(dataframe['not_downtrend_15m'])
                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append((dataframe['is_downtrend_3_1h'] == False)
                                          | (dataframe['crsi_1h'] > 20.0))
                    item_buy_logic.append(dataframe['is_downtrend_5_1h'] == False)
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)
                    # current 4h red with top wick, previous 4h long green
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 2.0))
                                          | (dataframe['change_pct_4h'].shift(48) < 0.12))
                    # current 4h red, previous 4h green with wick
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.18)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.08)
                                          | (dataframe['rsi_14_max_6_4h'] < 80.0))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.016))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['rsi_14'] < 40.0)

                # Condition #31 - Pump mode bear.
                if index == 31:
                    # Protections
                    item_buy_logic.append(dataframe['btc_is_bull_4h'] == False)
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.2))
                    item_buy_logic.append(dataframe['close_max_72'] < (dataframe['close'] * 1.24))
                    item_buy_logic.append(dataframe['close_max_144'] < (dataframe['close'] * 1.3))

                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(96))
                    item_buy_logic.append(dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))
                    item_buy_logic.append(dataframe['sma_200_4h'] > dataframe['sma_200_4h'].shift(96))

                    item_buy_logic.append(dataframe['close'] > dataframe['ema_200'])

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.9)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 80.0)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 80.0)

                    item_buy_logic.append(dataframe['not_downtrend_15m'])
                    item_buy_logic.append(dataframe['not_downtrend_1h'])
                    item_buy_logic.append((dataframe['is_downtrend_3_1h'] == False)
                                          | (dataframe['crsi_1h'] > 20.0))
                    item_buy_logic.append(dataframe['is_downtrend_5_1h'] == False)
                    item_buy_logic.append(dataframe['not_downtrend_4h'])
                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)
                    # current 4h red with top wick, previous 4h long green
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 2.0))
                                          | (dataframe['change_pct_4h'].shift(48) < 0.12))
                    # current 4h red, previous 4h green with wick
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.18)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.08)
                                          | (dataframe['rsi_14_max_6_4h'] < 80.0))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.016))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['rsi_14'] < 40.0)

                item_buy_logic.append(dataframe['volume'] > 0)
                item_buy = reduce(lambda x, y: x & y, item_buy_logic)
                dataframe.loc[item_buy, 'enter_tag'] += f"{index} "
                conditions.append(item_buy)
                dataframe.loc[:, 'enter_long'] = item_buy

        if conditions:
            dataframe.loc[:, 'enter_long'] = reduce(lambda x, y: x | y, conditions)

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        dataframe.loc[:, 'exit_short'] = 0

        return dataframe

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float, rate: float,
                            time_in_force: str, current_time: datetime, entry_tag: Optional[str],
                            **kwargs) -> bool:
        # allow force entries
        if (entry_tag == 'force_entry'):
            return True

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

    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: datetime, **kwargs) -> bool:
        # Allow force exits
        if exit_reason != 'force_exit':
            if self.exit_profit_only:
                current_profit = ((rate - trade.open_rate) / trade.open_rate)
                if (current_profit < self.exit_profit_offset):
                    return False

        self._remove_profit_target(pair)
        return True

    def _set_profit_target(self, pair: str, sell_reason: str, rate: float, current_profit: float, current_time: datetime):
        self.target_profit_cache.data[pair] = {
            "rate": rate,
            "profit": current_profit,
            "sell_reason": sell_reason,
            "time_profit_reached": current_time.isoformat()
        }
        self.target_profit_cache.save()

    def _remove_profit_target(self, pair: str):
        if self.target_profit_cache is not None:
            self.target_profit_cache.data.pop(pair, None)
            self.target_profit_cache.save()

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

    # +---------------------------------------------------------------------------+
# |                              Classes                                      |
# +---------------------------------------------------------------------------+

class Cache:

    def __init__(self, path):
        self.path = path
        self.data = {}
        self._mtime = None
        self._previous_data = {}
        try:
            self.load()
        except FileNotFoundError:
            pass

    @staticmethod
    def rapidjson_load_kwargs():
        return {"number_mode": rapidjson.NM_NATIVE}

    @staticmethod
    def rapidjson_dump_kwargs():
        return {"number_mode": rapidjson.NM_NATIVE}

    def load(self):
        if not self._mtime or self.path.stat().st_mtime_ns != self._mtime:
            self._load()

    def save(self):
        if self.data != self._previous_data:
            self._save()

    def process_loaded_data(self, data):
        return data

    def _load(self):
        # This method only exists to simplify unit testing
        with self.path.open("r") as rfh:
            try:
                data = rapidjson.load(
                    rfh,
                    **self.rapidjson_load_kwargs()
                )
            except rapidjson.JSONDecodeError as exc:
                log.error("Failed to load JSON from %s: %s", self.path, exc)
            else:
                self.data = self.process_loaded_data(data)
                self._previous_data = copy.deepcopy(self.data)
                self._mtime = self.path.stat().st_mtime_ns

    def _save(self):
        # This method only exists to simplify unit testing
        rapidjson.dump(
            self.data,
            self.path.open("w"),
            **self.rapidjson_dump_kwargs()
        )
        self._mtime = self.path.stat().st_mtime
        self._previous_data = copy.deepcopy(self.data)
