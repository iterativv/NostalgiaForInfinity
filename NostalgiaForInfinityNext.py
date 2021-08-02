import logging
import pathlib
import rapidjson
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
import talib.abstract as ta
from freqtrade.misc import json_load
from freqtrade.strategy.interface import IStrategy
from freqtrade.strategy import merge_informative_pair, timeframe_to_minutes
from freqtrade.strategy import DecimalParameter, IntParameter, CategoricalParameter
from freqtrade.exchange import timeframe_to_prev_date
from pandas import DataFrame, Series, concat
from functools import reduce
import math
from freqtrade.persistence import Trade
from datetime import datetime, timedelta
from technical.util import resample_to_interval, resampled_merge
from technical.indicators import zema, VIDYA
import pandas_ta as pta

log = logging.getLogger(__name__)


###########################################################################################################
##                NostalgiaForInfinityV8 by iterativ                                                     ##
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
##               HOLD SUPPORT                                                                            ##
##   In case you want to have SOME of the trades to only be sold when on profit, add a file named        ##
##   "hold-trades.json" in the same directory as this strategy.                                          ##
##                                                                                                       ##
##   The contents should be similar to:                                                                  ##
##                                                                                                       ##
##   {"trade_ids": [1, 3, 7], "profit_ratio": 0.005}                                                     ##
##                                                                                                       ##
##   Or, for individual profit ratios(Notice the trade ID's as strings:                                  ##
##                                                                                                       ##
##   {"trade_ids": {"1": 0.001, "3": -0.005, "7": 0.05}}                                                 ##
##                                                                                                       ##
##   NOTE:                                                                                               ##
##    * `trade_ids` is a list of integers, the trade ID's, which you can get from the logs or from the   ##
##      output of the telegram status command.                                                           ##
##    * Regardless of the defined profit ratio(s), the strategy MUST still produce a SELL signal for the ##
##      HOLD support logic to run                                                                        ##
##                                                                                                       ##
###########################################################################################################
##               DONATIONS                                                                               ##
##                                                                                                       ##
##   Absolutely not required. However, will be accepted as a token of appreciation.                      ##
##                                                                                                       ##
##   BTC: bc1qvflsvddkmxh7eqhc4jyu5z5k6xcw3ay8jl49sk                                                     ##
##   ETH (ERC20): 0x83D3cFb8001BDC5d2211cBeBB8cB3461E5f7Ec91                                             ##
##   BEP20/BSC (ETH, BNB, ...): 0x86A0B21a20b39d16424B7c8003E4A7e12d78ABEe                               ##
##                                                                                                       ##
###########################################################################################################


class NostalgiaForInfinityNext(IStrategy):
    INTERFACE_VERSION = 2

    # # ROI table:
    minimal_roi = {
        "0": 10,
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
    res_timeframe = 'none'
    info_timeframe = '1h'

    # BTC informative
    has_BTC_base_tf = False
    has_BTC_info_tf = True

    # Backtest Age Filter emulation
    has_bt_agefilter = False
    bt_min_age_days = 7

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
        'stoploss_on_exchange': False
    }

    #############################################################

    buy_params = {
        #############
        # Enable/Disable conditions
        "buy_condition_1_enable": True,
        "buy_condition_2_enable": True,
        "buy_condition_3_enable": True,
        "buy_condition_4_enable": True,
        "buy_condition_5_enable": True,
        "buy_condition_6_enable": True,
        "buy_condition_7_enable": True,
        "buy_condition_8_enable": True,
        "buy_condition_9_enable": True,
        "buy_condition_10_enable": True,
        "buy_condition_11_enable": True,
        "buy_condition_12_enable": True,
        "buy_condition_13_enable": True,
        "buy_condition_14_enable": True,
        "buy_condition_15_enable": True,
        "buy_condition_16_enable": True,
        "buy_condition_17_enable": True,
        "buy_condition_18_enable": True,
        "buy_condition_19_enable": True,
        "buy_condition_20_enable": True,
        "buy_condition_21_enable": True,
        "buy_condition_22_enable": True,
        "buy_condition_23_enable": True,
        "buy_condition_24_enable": True,
        "buy_condition_25_enable": True,
        "buy_condition_26_enable": True,
        "buy_condition_27_enable": True,
        "buy_condition_28_enable": True,
        "buy_condition_29_enable": True,
        "buy_condition_30_enable": True,
        "buy_condition_31_enable": True,
        "buy_condition_32_enable": True,
        "buy_condition_33_enable": True,
        "buy_condition_34_enable": True,
        "buy_condition_35_enable": True,
        "buy_condition_36_enable": True,
        "buy_condition_37_enable": True,
        "buy_condition_38_enable": True,
        #############
    }

    sell_params = {
        #############
        # Enable/Disable conditions
        "sell_condition_1_enable": True,
        "sell_condition_2_enable": True,
        "sell_condition_3_enable": True,
        "sell_condition_4_enable": True,
        "sell_condition_5_enable": True,
        "sell_condition_6_enable": True,
        "sell_condition_7_enable": True,
        "sell_condition_8_enable": True,
        #############
    }

    #############################################################

    buy_protection_params = {
        1: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="26", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="28", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="80", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="70", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        2: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="20", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        3: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="80", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="36", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        4: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="20", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="110", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="48", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        5: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["50","100","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="130", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="30", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="36", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        6: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="20", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="36", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        7: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="12", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        8: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="12", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="120", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        9: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        10: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="24", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        11: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        12: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="24", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        13: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="24", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="20", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        14: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="70", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        15: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="130", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="20", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="36", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        16: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="50", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        17: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="120", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        18: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="44", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="72", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="60", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        19: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="36", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        20: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        21: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="90", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        22: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="110", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        23: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        24: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="200", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="36", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="20", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        25: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="20", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="20", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        26: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="60", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="48", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        27: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="36", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True)
        },
        28: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="110", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="36", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True)
        },
        29: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="110", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="36", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        30: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="200", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="50", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="110", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="36", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        31: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="100", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="110", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="48", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        32: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="100", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="20", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="48", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        33: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="100", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        34: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="100", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        34: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="100", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        35: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="100", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        36: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="100", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="24", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        37: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="100", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="48", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        },
        38: {
            "enable"                    : CategoricalParameter([True, False], default=True, space='buy', optimize=False, load=True),
            "ema_fast"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_fast_len"              : CategoricalParameter(["26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "ema_slow"                  : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "ema_slow_len"              : CategoricalParameter(["26","50","100","200"], default="100", space='buy', optimize=False, load=True),
            "close_above_ema_fast"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_fast_len"  : CategoricalParameter(["12","20","26","50","100","200"], default="50", space='buy', optimize=False, load=True),
            "close_above_ema_slow"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "close_above_ema_slow_len"  : CategoricalParameter(["15","50","200"], default="100", space='buy', optimize=False, load=True),
            "sma200_rising"             : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_rising_val"         : CategoricalParameter(["20","30","36","44","50"], default="30", space='buy', optimize=False, load=True),
            "sma200_1h_rising"          : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "sma200_1h_rising_val"      : CategoricalParameter(["20","30","36","44","50"], default="50", space='buy', optimize=False, load=True),
            "safe_dips"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_dips_type"            : CategoricalParameter(["10","50","100"], default="100", space='buy', optimize=False, load=True),
            "safe_pump"                 : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True),
            "safe_pump_type"            : CategoricalParameter(["10","50","100"], default="10", space='buy', optimize=False, load=True),
            "safe_pump_period"          : CategoricalParameter(["24","36","48"], default="36", space='buy', optimize=False, load=True),
            "btc_1h_not_downtrend"      : CategoricalParameter([True, False], default=False, space='buy', optimize=False, load=True)
        }
    }

    buy_condition_1_enable = buy_protection_params[1]["enable"]
    buy_1_protection__ema_fast                 = buy_protection_params[1]["ema_fast"]
    buy_1_protection__ema_fast_len             = buy_protection_params[1]["ema_fast_len"]
    buy_1_protection__ema_slow                 = buy_protection_params[1]["ema_slow"]
    buy_1_protection__ema_slow_len             = buy_protection_params[1]["ema_slow_len"]
    buy_1_protection__close_above_ema_fast     = buy_protection_params[1]["close_above_ema_fast"]
    buy_1_protection__close_above_ema_fast_len = buy_protection_params[1]["close_above_ema_fast_len"]
    buy_1_protection__close_above_ema_slow     = buy_protection_params[1]["close_above_ema_slow"]
    buy_1_protection__close_above_ema_slow_len = buy_protection_params[1]["close_above_ema_slow_len"]
    buy_1_protection__sma200_rising            = buy_protection_params[1]["sma200_rising"]
    buy_1_protection__sma200_rising_val        = buy_protection_params[1]["sma200_rising_val"]
    buy_1_protection__sma200_1h_rising         = buy_protection_params[1]["sma200_1h_rising"]
    buy_1_protection__sma200_1h_rising_val     = buy_protection_params[1]["sma200_1h_rising_val"]
    buy_1_protection__safe_dips                = buy_protection_params[1]["safe_dips"]
    buy_1_protection__safe_dips_type           = buy_protection_params[1]["safe_dips_type"]
    buy_1_protection__safe_pump                = buy_protection_params[1]["safe_pump"]
    buy_1_protection__safe_pump_type           = buy_protection_params[1]["safe_pump_type"]
    buy_1_protection__safe_pump_period         = buy_protection_params[1]["safe_pump_period"]
    buy_1_protection__btc_1h_not_downtrend     = buy_protection_params[1]["btc_1h_not_downtrend"]

    buy_condition_2_enable = buy_protection_params[2]["enable"]
    buy_2_protection__ema_fast                 = buy_protection_params[2]["ema_fast"]
    buy_2_protection__ema_fast_len             = buy_protection_params[2]["ema_fast_len"]
    buy_2_protection__ema_slow                 = buy_protection_params[2]["ema_slow"]
    buy_2_protection__ema_slow_len             = buy_protection_params[2]["ema_slow_len"]
    buy_2_protection__close_above_ema_fast     = buy_protection_params[2]["close_above_ema_fast"]
    buy_2_protection__close_above_ema_fast_len = buy_protection_params[2]["close_above_ema_fast_len"]
    buy_2_protection__close_above_ema_slow     = buy_protection_params[2]["close_above_ema_slow"]
    buy_2_protection__close_above_ema_slow_len = buy_protection_params[2]["close_above_ema_slow_len"]
    buy_2_protection__sma200_rising            = buy_protection_params[2]["sma200_rising"]
    buy_2_protection__sma200_rising_val        = buy_protection_params[2]["sma200_rising_val"]
    buy_2_protection__sma200_1h_rising         = buy_protection_params[2]["sma200_1h_rising"]
    buy_2_protection__sma200_1h_rising_val     = buy_protection_params[2]["sma200_1h_rising_val"]
    buy_2_protection__safe_dips                = buy_protection_params[2]["safe_dips"]
    buy_2_protection__safe_dips_type           = buy_protection_params[2]["safe_dips_type"]
    buy_2_protection__safe_pump                = buy_protection_params[2]["safe_pump"]
    buy_2_protection__safe_pump_type           = buy_protection_params[2]["safe_pump_type"]
    buy_2_protection__safe_pump_period         = buy_protection_params[2]["safe_pump_period"]
    buy_2_protection__btc_1h_not_downtrend     = buy_protection_params[2]["btc_1h_not_downtrend"]

    buy_condition_3_enable = buy_protection_params[3]["enable"]
    buy_3_protection__ema_fast                 = buy_protection_params[3]["ema_fast"]
    buy_3_protection__ema_fast_len             = buy_protection_params[3]["ema_fast_len"]
    buy_3_protection__ema_slow                 = buy_protection_params[3]["ema_slow"]
    buy_3_protection__ema_slow_len             = buy_protection_params[3]["ema_slow_len"]
    buy_3_protection__close_above_ema_fast     = buy_protection_params[3]["close_above_ema_fast"]
    buy_3_protection__close_above_ema_fast_len = buy_protection_params[3]["close_above_ema_fast_len"]
    buy_3_protection__close_above_ema_slow     = buy_protection_params[3]["close_above_ema_slow"]
    buy_3_protection__close_above_ema_slow_len = buy_protection_params[3]["close_above_ema_slow_len"]
    buy_3_protection__sma200_rising            = buy_protection_params[3]["sma200_rising"]
    buy_3_protection__sma200_rising_val        = buy_protection_params[3]["sma200_rising_val"]
    buy_3_protection__sma200_1h_rising         = buy_protection_params[3]["sma200_1h_rising"]
    buy_3_protection__sma200_1h_rising_val     = buy_protection_params[3]["sma200_1h_rising_val"]
    buy_3_protection__safe_dips                = buy_protection_params[3]["safe_dips"]
    buy_3_protection__safe_dips_type           = buy_protection_params[3]["safe_dips_type"]
    buy_3_protection__safe_pump                = buy_protection_params[3]["safe_pump"]
    buy_3_protection__safe_pump_type           = buy_protection_params[3]["safe_pump_type"]
    buy_3_protection__safe_pump_period         = buy_protection_params[3]["safe_pump_period"]
    buy_3_protection__btc_1h_not_downtrend     = buy_protection_params[3]["btc_1h_not_downtrend"]

    buy_condition_4_enable = buy_protection_params[4]["enable"]
    buy_4_protection__ema_fast                 = buy_protection_params[4]["ema_fast"]
    buy_4_protection__ema_fast_len             = buy_protection_params[4]["ema_fast_len"]
    buy_4_protection__ema_slow                 = buy_protection_params[4]["ema_slow"]
    buy_4_protection__ema_slow_len             = buy_protection_params[4]["ema_slow_len"]
    buy_4_protection__close_above_ema_fast     = buy_protection_params[4]["close_above_ema_fast"]
    buy_4_protection__close_above_ema_fast_len = buy_protection_params[4]["close_above_ema_fast_len"]
    buy_4_protection__close_above_ema_slow     = buy_protection_params[4]["close_above_ema_slow"]
    buy_4_protection__close_above_ema_slow_len = buy_protection_params[4]["close_above_ema_slow_len"]
    buy_4_protection__sma200_rising            = buy_protection_params[4]["sma200_rising"]
    buy_4_protection__sma200_rising_val        = buy_protection_params[4]["sma200_rising_val"]
    buy_4_protection__sma200_1h_rising         = buy_protection_params[4]["sma200_1h_rising"]
    buy_4_protection__sma200_1h_rising_val     = buy_protection_params[4]["sma200_1h_rising_val"]
    buy_4_protection__safe_dips                = buy_protection_params[4]["safe_dips"]
    buy_4_protection__safe_dips_type           = buy_protection_params[4]["safe_dips_type"]
    buy_4_protection__safe_pump                = buy_protection_params[4]["safe_pump"]
    buy_4_protection__safe_pump_type           = buy_protection_params[4]["safe_pump_type"]
    buy_4_protection__safe_pump_period         = buy_protection_params[4]["safe_pump_period"]
    buy_4_protection__btc_1h_not_downtrend     = buy_protection_params[4]["btc_1h_not_downtrend"]

    buy_condition_5_enable = buy_protection_params[5]["enable"]
    buy_5_protection__ema_fast                 = buy_protection_params[5]["ema_fast"]
    buy_5_protection__ema_fast_len             = buy_protection_params[5]["ema_fast_len"]
    buy_5_protection__ema_slow                 = buy_protection_params[5]["ema_slow"]
    buy_5_protection__ema_slow_len             = buy_protection_params[5]["ema_slow_len"]
    buy_5_protection__close_above_ema_fast     = buy_protection_params[5]["close_above_ema_fast"]
    buy_5_protection__close_above_ema_fast_len = buy_protection_params[5]["close_above_ema_fast_len"]
    buy_5_protection__close_above_ema_slow     = buy_protection_params[5]["close_above_ema_slow"]
    buy_5_protection__close_above_ema_slow_len = buy_protection_params[5]["close_above_ema_slow_len"]
    buy_5_protection__sma200_rising            = buy_protection_params[5]["sma200_rising"]
    buy_5_protection__sma200_rising_val        = buy_protection_params[5]["sma200_rising_val"]
    buy_5_protection__sma200_1h_rising         = buy_protection_params[5]["sma200_1h_rising"]
    buy_5_protection__sma200_1h_rising_val     = buy_protection_params[5]["sma200_1h_rising_val"]
    buy_5_protection__safe_dips                = buy_protection_params[5]["safe_dips"]
    buy_5_protection__safe_dips_type           = buy_protection_params[5]["safe_dips_type"]
    buy_5_protection__safe_pump                = buy_protection_params[5]["safe_pump"]
    buy_5_protection__safe_pump_type           = buy_protection_params[5]["safe_pump_type"]
    buy_5_protection__safe_pump_period         = buy_protection_params[5]["safe_pump_period"]
    buy_5_protection__btc_1h_not_downtrend     = buy_protection_params[5]["btc_1h_not_downtrend"]

    buy_condition_6_enable = buy_protection_params[6]["enable"]
    buy_6_protection__ema_fast                 = buy_protection_params[6]["ema_fast"]
    buy_6_protection__ema_fast_len             = buy_protection_params[6]["ema_fast_len"]
    buy_6_protection__ema_slow                 = buy_protection_params[6]["ema_slow"]
    buy_6_protection__ema_slow_len             = buy_protection_params[6]["ema_slow_len"]
    buy_6_protection__close_above_ema_fast     = buy_protection_params[6]["close_above_ema_fast"]
    buy_6_protection__close_above_ema_fast_len = buy_protection_params[6]["close_above_ema_fast_len"]
    buy_6_protection__close_above_ema_slow     = buy_protection_params[6]["close_above_ema_slow"]
    buy_6_protection__close_above_ema_slow_len = buy_protection_params[6]["close_above_ema_slow_len"]
    buy_6_protection__sma200_rising            = buy_protection_params[6]["sma200_rising"]
    buy_6_protection__sma200_rising_val        = buy_protection_params[6]["sma200_rising_val"]
    buy_6_protection__sma200_1h_rising         = buy_protection_params[6]["sma200_1h_rising"]
    buy_6_protection__sma200_1h_rising_val     = buy_protection_params[6]["sma200_1h_rising_val"]
    buy_6_protection__safe_dips                = buy_protection_params[6]["safe_dips"]
    buy_6_protection__safe_dips_type           = buy_protection_params[6]["safe_dips_type"]
    buy_6_protection__safe_pump                = buy_protection_params[6]["safe_pump"]
    buy_6_protection__safe_pump_type           = buy_protection_params[6]["safe_pump_type"]
    buy_6_protection__safe_pump_period         = buy_protection_params[6]["safe_pump_period"]
    buy_6_protection__btc_1h_not_downtrend     = buy_protection_params[6]["btc_1h_not_downtrend"]

    buy_condition_7_enable = buy_protection_params[7]["enable"]
    buy_7_protection__ema_fast                 = buy_protection_params[7]["ema_fast"]
    buy_7_protection__ema_fast_len             = buy_protection_params[7]["ema_fast_len"]
    buy_7_protection__ema_slow                 = buy_protection_params[7]["ema_slow"]
    buy_7_protection__ema_slow_len             = buy_protection_params[7]["ema_slow_len"]
    buy_7_protection__close_above_ema_fast     = buy_protection_params[7]["close_above_ema_fast"]
    buy_7_protection__close_above_ema_fast_len = buy_protection_params[7]["close_above_ema_fast_len"]
    buy_7_protection__close_above_ema_slow     = buy_protection_params[7]["close_above_ema_slow"]
    buy_7_protection__close_above_ema_slow_len = buy_protection_params[7]["close_above_ema_slow_len"]
    buy_7_protection__sma200_rising            = buy_protection_params[7]["sma200_rising"]
    buy_7_protection__sma200_rising_val        = buy_protection_params[7]["sma200_rising_val"]
    buy_7_protection__sma200_1h_rising         = buy_protection_params[7]["sma200_1h_rising"]
    buy_7_protection__sma200_1h_rising_val     = buy_protection_params[7]["sma200_1h_rising_val"]
    buy_7_protection__safe_dips                = buy_protection_params[7]["safe_dips"]
    buy_7_protection__safe_dips_type           = buy_protection_params[7]["safe_dips_type"]
    buy_7_protection__safe_pump                = buy_protection_params[7]["safe_pump"]
    buy_7_protection__safe_pump_type           = buy_protection_params[7]["safe_pump_type"]
    buy_7_protection__safe_pump_period         = buy_protection_params[7]["safe_pump_period"]
    buy_7_protection__btc_1h_not_downtrend     = buy_protection_params[7]["btc_1h_not_downtrend"]

    buy_condition_8_enable = buy_protection_params[8]["enable"]
    buy_8_protection__ema_fast                 = buy_protection_params[8]["ema_fast"]
    buy_8_protection__ema_fast_len             = buy_protection_params[8]["ema_fast_len"]
    buy_8_protection__ema_slow                 = buy_protection_params[8]["ema_slow"]
    buy_8_protection__ema_slow_len             = buy_protection_params[8]["ema_slow_len"]
    buy_8_protection__close_above_ema_fast     = buy_protection_params[8]["close_above_ema_fast"]
    buy_8_protection__close_above_ema_fast_len = buy_protection_params[8]["close_above_ema_fast_len"]
    buy_8_protection__close_above_ema_slow     = buy_protection_params[8]["close_above_ema_slow"]
    buy_8_protection__close_above_ema_slow_len = buy_protection_params[8]["close_above_ema_slow_len"]
    buy_8_protection__sma200_rising            = buy_protection_params[8]["sma200_rising"]
    buy_8_protection__sma200_rising_val        = buy_protection_params[8]["sma200_rising_val"]
    buy_8_protection__sma200_1h_rising         = buy_protection_params[8]["sma200_1h_rising"]
    buy_8_protection__sma200_1h_rising_val     = buy_protection_params[8]["sma200_1h_rising_val"]
    buy_8_protection__safe_dips                = buy_protection_params[8]["safe_dips"]
    buy_8_protection__safe_dips_type           = buy_protection_params[8]["safe_dips_type"]
    buy_8_protection__safe_pump                = buy_protection_params[8]["safe_pump"]
    buy_8_protection__safe_pump_type           = buy_protection_params[8]["safe_pump_type"]
    buy_8_protection__safe_pump_period         = buy_protection_params[8]["safe_pump_period"]
    buy_8_protection__btc_1h_not_downtrend     = buy_protection_params[8]["btc_1h_not_downtrend"]

    buy_condition_9_enable = buy_protection_params[9]["enable"]
    buy_9_protection__ema_fast                 = buy_protection_params[9]["ema_fast"]
    buy_9_protection__ema_fast_len             = buy_protection_params[9]["ema_fast_len"]
    buy_9_protection__ema_slow                 = buy_protection_params[9]["ema_slow"]
    buy_9_protection__ema_slow_len             = buy_protection_params[9]["ema_slow_len"]
    buy_9_protection__close_above_ema_fast     = buy_protection_params[9]["close_above_ema_fast"]
    buy_9_protection__close_above_ema_fast_len = buy_protection_params[9]["close_above_ema_fast_len"]
    buy_9_protection__close_above_ema_slow     = buy_protection_params[9]["close_above_ema_slow"]
    buy_9_protection__close_above_ema_slow_len = buy_protection_params[9]["close_above_ema_slow_len"]
    buy_9_protection__sma200_rising            = buy_protection_params[9]["sma200_rising"]
    buy_9_protection__sma200_rising_val        = buy_protection_params[9]["sma200_rising_val"]
    buy_9_protection__sma200_1h_rising         = buy_protection_params[9]["sma200_1h_rising"]
    buy_9_protection__sma200_1h_rising_val     = buy_protection_params[9]["sma200_1h_rising_val"]
    buy_9_protection__safe_dips                = buy_protection_params[9]["safe_dips"]
    buy_9_protection__safe_dips_type           = buy_protection_params[9]["safe_dips_type"]
    buy_9_protection__safe_pump                = buy_protection_params[9]["safe_pump"]
    buy_9_protection__safe_pump_type           = buy_protection_params[9]["safe_pump_type"]
    buy_9_protection__safe_pump_period         = buy_protection_params[9]["safe_pump_period"]
    buy_9_protection__btc_1h_not_downtrend     = buy_protection_params[9]["btc_1h_not_downtrend"]

    buy_condition_10_enable = buy_protection_params[10]["enable"]
    buy_10_protection__ema_fast                 = buy_protection_params[10]["ema_fast"]
    buy_10_protection__ema_fast_len             = buy_protection_params[10]["ema_fast_len"]
    buy_10_protection__ema_slow                 = buy_protection_params[10]["ema_slow"]
    buy_10_protection__ema_slow_len             = buy_protection_params[10]["ema_slow_len"]
    buy_10_protection__close_above_ema_fast     = buy_protection_params[10]["close_above_ema_fast"]
    buy_10_protection__close_above_ema_fast_len = buy_protection_params[10]["close_above_ema_fast_len"]
    buy_10_protection__close_above_ema_slow     = buy_protection_params[10]["close_above_ema_slow"]
    buy_10_protection__close_above_ema_slow_len = buy_protection_params[10]["close_above_ema_slow_len"]
    buy_10_protection__sma200_rising            = buy_protection_params[10]["sma200_rising"]
    buy_10_protection__sma200_rising_val        = buy_protection_params[10]["sma200_rising_val"]
    buy_10_protection__sma200_1h_rising         = buy_protection_params[10]["sma200_1h_rising"]
    buy_10_protection__sma200_1h_rising_val     = buy_protection_params[10]["sma200_1h_rising_val"]
    buy_10_protection__safe_dips                = buy_protection_params[10]["safe_dips"]
    buy_10_protection__safe_dips_type           = buy_protection_params[10]["safe_dips_type"]
    buy_10_protection__safe_pump                = buy_protection_params[10]["safe_pump"]
    buy_10_protection__safe_pump_type           = buy_protection_params[10]["safe_pump_type"]
    buy_10_protection__safe_pump_period         = buy_protection_params[10]["safe_pump_period"]
    buy_10_protection__btc_1h_not_downtrend     = buy_protection_params[10]["btc_1h_not_downtrend"]

    buy_condition_11_enable = buy_protection_params[11]["enable"]
    buy_11_protection__ema_fast                 = buy_protection_params[11]["ema_fast"]
    buy_11_protection__ema_fast_len             = buy_protection_params[11]["ema_fast_len"]
    buy_11_protection__ema_slow                 = buy_protection_params[11]["ema_slow"]
    buy_11_protection__ema_slow_len             = buy_protection_params[11]["ema_slow_len"]
    buy_11_protection__close_above_ema_fast     = buy_protection_params[11]["close_above_ema_fast"]
    buy_11_protection__close_above_ema_fast_len = buy_protection_params[11]["close_above_ema_fast_len"]
    buy_11_protection__close_above_ema_slow     = buy_protection_params[11]["close_above_ema_slow"]
    buy_11_protection__close_above_ema_slow_len = buy_protection_params[11]["close_above_ema_slow_len"]
    buy_11_protection__sma200_rising            = buy_protection_params[11]["sma200_rising"]
    buy_11_protection__sma200_rising_val        = buy_protection_params[11]["sma200_rising_val"]
    buy_11_protection__sma200_1h_rising         = buy_protection_params[11]["sma200_1h_rising"]
    buy_11_protection__sma200_1h_rising_val     = buy_protection_params[11]["sma200_1h_rising_val"]
    buy_11_protection__safe_dips                = buy_protection_params[11]["safe_dips"]
    buy_11_protection__safe_dips_type           = buy_protection_params[11]["safe_dips_type"]
    buy_11_protection__safe_pump                = buy_protection_params[11]["safe_pump"]
    buy_11_protection__safe_pump_type           = buy_protection_params[11]["safe_pump_type"]
    buy_11_protection__safe_pump_period         = buy_protection_params[11]["safe_pump_period"]
    buy_11_protection__btc_1h_not_downtrend     = buy_protection_params[11]["btc_1h_not_downtrend"]

    buy_condition_12_enable = buy_protection_params[12]["enable"]
    buy_12_protection__ema_fast                 = buy_protection_params[12]["ema_fast"]
    buy_12_protection__ema_fast_len             = buy_protection_params[12]["ema_fast_len"]
    buy_12_protection__ema_slow                 = buy_protection_params[12]["ema_slow"]
    buy_12_protection__ema_slow_len             = buy_protection_params[12]["ema_slow_len"]
    buy_12_protection__close_above_ema_fast     = buy_protection_params[12]["close_above_ema_fast"]
    buy_12_protection__close_above_ema_fast_len = buy_protection_params[12]["close_above_ema_fast_len"]
    buy_12_protection__close_above_ema_slow     = buy_protection_params[12]["close_above_ema_slow"]
    buy_12_protection__close_above_ema_slow_len = buy_protection_params[12]["close_above_ema_slow_len"]
    buy_12_protection__sma200_rising            = buy_protection_params[12]["sma200_rising"]
    buy_12_protection__sma200_rising_val        = buy_protection_params[12]["sma200_rising_val"]
    buy_12_protection__sma200_1h_rising         = buy_protection_params[12]["sma200_1h_rising"]
    buy_12_protection__sma200_1h_rising_val     = buy_protection_params[12]["sma200_1h_rising_val"]
    buy_12_protection__safe_dips                = buy_protection_params[12]["safe_dips"]
    buy_12_protection__safe_dips_type           = buy_protection_params[12]["safe_dips_type"]
    buy_12_protection__safe_pump                = buy_protection_params[12]["safe_pump"]
    buy_12_protection__safe_pump_type           = buy_protection_params[12]["safe_pump_type"]
    buy_12_protection__safe_pump_period         = buy_protection_params[12]["safe_pump_period"]
    buy_12_protection__btc_1h_not_downtrend     = buy_protection_params[12]["btc_1h_not_downtrend"]

    buy_condition_13_enable = buy_protection_params[13]["enable"]
    buy_13_protection__ema_fast                 = buy_protection_params[13]["ema_fast"]
    buy_13_protection__ema_fast_len             = buy_protection_params[13]["ema_fast_len"]
    buy_13_protection__ema_slow                 = buy_protection_params[13]["ema_slow"]
    buy_13_protection__ema_slow_len             = buy_protection_params[13]["ema_slow_len"]
    buy_13_protection__close_above_ema_fast     = buy_protection_params[13]["close_above_ema_fast"]
    buy_13_protection__close_above_ema_fast_len = buy_protection_params[13]["close_above_ema_fast_len"]
    buy_13_protection__close_above_ema_slow     = buy_protection_params[13]["close_above_ema_slow"]
    buy_13_protection__close_above_ema_slow_len = buy_protection_params[13]["close_above_ema_slow_len"]
    buy_13_protection__sma200_rising            = buy_protection_params[13]["sma200_rising"]
    buy_13_protection__sma200_rising_val        = buy_protection_params[13]["sma200_rising_val"]
    buy_13_protection__sma200_1h_rising         = buy_protection_params[13]["sma200_1h_rising"]
    buy_13_protection__sma200_1h_rising_val     = buy_protection_params[13]["sma200_1h_rising_val"]
    buy_13_protection__safe_dips                = buy_protection_params[13]["safe_dips"]
    buy_13_protection__safe_dips_type           = buy_protection_params[13]["safe_dips_type"]
    buy_13_protection__safe_pump                = buy_protection_params[13]["safe_pump"]
    buy_13_protection__safe_pump_type           = buy_protection_params[13]["safe_pump_type"]
    buy_13_protection__safe_pump_period         = buy_protection_params[13]["safe_pump_period"]
    buy_13_protection__btc_1h_not_downtrend     = buy_protection_params[13]["btc_1h_not_downtrend"]

    buy_condition_14_enable = buy_protection_params[14]["enable"]
    buy_14_protection__ema_fast                 = buy_protection_params[14]["ema_fast"]
    buy_14_protection__ema_fast_len             = buy_protection_params[14]["ema_fast_len"]
    buy_14_protection__ema_slow                 = buy_protection_params[14]["ema_slow"]
    buy_14_protection__ema_slow_len             = buy_protection_params[14]["ema_slow_len"]
    buy_14_protection__close_above_ema_fast     = buy_protection_params[14]["close_above_ema_fast"]
    buy_14_protection__close_above_ema_fast_len = buy_protection_params[14]["close_above_ema_fast_len"]
    buy_14_protection__close_above_ema_slow     = buy_protection_params[14]["close_above_ema_slow"]
    buy_14_protection__close_above_ema_slow_len = buy_protection_params[14]["close_above_ema_slow_len"]
    buy_14_protection__sma200_rising            = buy_protection_params[14]["sma200_rising"]
    buy_14_protection__sma200_rising_val        = buy_protection_params[14]["sma200_rising_val"]
    buy_14_protection__sma200_1h_rising         = buy_protection_params[14]["sma200_1h_rising"]
    buy_14_protection__sma200_1h_rising_val     = buy_protection_params[14]["sma200_1h_rising_val"]
    buy_14_protection__safe_dips                = buy_protection_params[14]["safe_dips"]
    buy_14_protection__safe_dips_type           = buy_protection_params[14]["safe_dips_type"]
    buy_14_protection__safe_pump                = buy_protection_params[14]["safe_pump"]
    buy_14_protection__safe_pump_type           = buy_protection_params[14]["safe_pump_type"]
    buy_14_protection__safe_pump_period         = buy_protection_params[14]["safe_pump_period"]
    buy_14_protection__btc_1h_not_downtrend     = buy_protection_params[14]["btc_1h_not_downtrend"]

    buy_condition_15_enable = buy_protection_params[15]["enable"]
    buy_15_protection__ema_fast                 = buy_protection_params[15]["ema_fast"]
    buy_15_protection__ema_fast_len             = buy_protection_params[15]["ema_fast_len"]
    buy_15_protection__ema_slow                 = buy_protection_params[15]["ema_slow"]
    buy_15_protection__ema_slow_len             = buy_protection_params[15]["ema_slow_len"]
    buy_15_protection__close_above_ema_fast     = buy_protection_params[15]["close_above_ema_fast"]
    buy_15_protection__close_above_ema_fast_len = buy_protection_params[15]["close_above_ema_fast_len"]
    buy_15_protection__close_above_ema_slow     = buy_protection_params[15]["close_above_ema_slow"]
    buy_15_protection__close_above_ema_slow_len = buy_protection_params[15]["close_above_ema_slow_len"]
    buy_15_protection__sma200_rising            = buy_protection_params[15]["sma200_rising"]
    buy_15_protection__sma200_rising_val        = buy_protection_params[15]["sma200_rising_val"]
    buy_15_protection__sma200_1h_rising         = buy_protection_params[15]["sma200_1h_rising"]
    buy_15_protection__sma200_1h_rising_val     = buy_protection_params[15]["sma200_1h_rising_val"]
    buy_15_protection__safe_dips                = buy_protection_params[15]["safe_dips"]
    buy_15_protection__safe_dips_type           = buy_protection_params[15]["safe_dips_type"]
    buy_15_protection__safe_pump                = buy_protection_params[15]["safe_pump"]
    buy_15_protection__safe_pump_type           = buy_protection_params[15]["safe_pump_type"]
    buy_15_protection__safe_pump_period         = buy_protection_params[15]["safe_pump_period"]
    buy_15_protection__btc_1h_not_downtrend     = buy_protection_params[15]["btc_1h_not_downtrend"]

    buy_condition_16_enable = buy_protection_params[16]["enable"]
    buy_16_protection__ema_fast                 = buy_protection_params[16]["ema_fast"]
    buy_16_protection__ema_fast_len             = buy_protection_params[16]["ema_fast_len"]
    buy_16_protection__ema_slow                 = buy_protection_params[16]["ema_slow"]
    buy_16_protection__ema_slow_len             = buy_protection_params[16]["ema_slow_len"]
    buy_16_protection__close_above_ema_fast     = buy_protection_params[16]["close_above_ema_fast"]
    buy_16_protection__close_above_ema_fast_len = buy_protection_params[16]["close_above_ema_fast_len"]
    buy_16_protection__close_above_ema_slow     = buy_protection_params[16]["close_above_ema_slow"]
    buy_16_protection__close_above_ema_slow_len = buy_protection_params[16]["close_above_ema_slow_len"]
    buy_16_protection__sma200_rising            = buy_protection_params[16]["sma200_rising"]
    buy_16_protection__sma200_rising_val        = buy_protection_params[16]["sma200_rising_val"]
    buy_16_protection__sma200_1h_rising         = buy_protection_params[16]["sma200_1h_rising"]
    buy_16_protection__sma200_1h_rising_val     = buy_protection_params[16]["sma200_1h_rising_val"]
    buy_16_protection__safe_dips                = buy_protection_params[16]["safe_dips"]
    buy_16_protection__safe_dips_type           = buy_protection_params[16]["safe_dips_type"]
    buy_16_protection__safe_pump                = buy_protection_params[16]["safe_pump"]
    buy_16_protection__safe_pump_type           = buy_protection_params[16]["safe_pump_type"]
    buy_16_protection__safe_pump_period         = buy_protection_params[16]["safe_pump_period"]
    buy_16_protection__btc_1h_not_downtrend     = buy_protection_params[16]["btc_1h_not_downtrend"]

    buy_condition_17_enable = buy_protection_params[17]["enable"]
    buy_17_protection__ema_fast                 = buy_protection_params[17]["ema_fast"]
    buy_17_protection__ema_fast_len             = buy_protection_params[17]["ema_fast_len"]
    buy_17_protection__ema_slow                 = buy_protection_params[17]["ema_slow"]
    buy_17_protection__ema_slow_len             = buy_protection_params[17]["ema_slow_len"]
    buy_17_protection__close_above_ema_fast     = buy_protection_params[17]["close_above_ema_fast"]
    buy_17_protection__close_above_ema_fast_len = buy_protection_params[17]["close_above_ema_fast_len"]
    buy_17_protection__close_above_ema_slow     = buy_protection_params[17]["close_above_ema_slow"]
    buy_17_protection__close_above_ema_slow_len = buy_protection_params[17]["close_above_ema_slow_len"]
    buy_17_protection__sma200_rising            = buy_protection_params[17]["sma200_rising"]
    buy_17_protection__sma200_rising_val        = buy_protection_params[17]["sma200_rising_val"]
    buy_17_protection__sma200_1h_rising         = buy_protection_params[17]["sma200_1h_rising"]
    buy_17_protection__sma200_1h_rising_val     = buy_protection_params[17]["sma200_1h_rising_val"]
    buy_17_protection__safe_dips                = buy_protection_params[17]["safe_dips"]
    buy_17_protection__safe_dips_type           = buy_protection_params[17]["safe_dips_type"]
    buy_17_protection__safe_pump                = buy_protection_params[17]["safe_pump"]
    buy_17_protection__safe_pump_type           = buy_protection_params[17]["safe_pump_type"]
    buy_17_protection__safe_pump_period         = buy_protection_params[17]["safe_pump_period"]
    buy_17_protection__btc_1h_not_downtrend     = buy_protection_params[17]["btc_1h_not_downtrend"]

    buy_condition_18_enable = buy_protection_params[18]["enable"]
    buy_18_protection__ema_fast                 = buy_protection_params[18]["ema_fast"]
    buy_18_protection__ema_fast_len             = buy_protection_params[18]["ema_fast_len"]
    buy_18_protection__ema_slow                 = buy_protection_params[18]["ema_slow"]
    buy_18_protection__ema_slow_len             = buy_protection_params[18]["ema_slow_len"]
    buy_18_protection__close_above_ema_fast     = buy_protection_params[18]["close_above_ema_fast"]
    buy_18_protection__close_above_ema_fast_len = buy_protection_params[18]["close_above_ema_fast_len"]
    buy_18_protection__close_above_ema_slow     = buy_protection_params[18]["close_above_ema_slow"]
    buy_18_protection__close_above_ema_slow_len = buy_protection_params[18]["close_above_ema_slow_len"]
    buy_18_protection__sma200_rising            = buy_protection_params[18]["sma200_rising"]
    buy_18_protection__sma200_rising_val        = buy_protection_params[18]["sma200_rising_val"]
    buy_18_protection__sma200_1h_rising         = buy_protection_params[18]["sma200_1h_rising"]
    buy_18_protection__sma200_1h_rising_val     = buy_protection_params[18]["sma200_1h_rising_val"]
    buy_18_protection__safe_dips                = buy_protection_params[18]["safe_dips"]
    buy_18_protection__safe_dips_type           = buy_protection_params[18]["safe_dips_type"]
    buy_18_protection__safe_pump                = buy_protection_params[18]["safe_pump"]
    buy_18_protection__safe_pump_type           = buy_protection_params[18]["safe_pump_type"]
    buy_18_protection__safe_pump_period         = buy_protection_params[18]["safe_pump_period"]
    buy_18_protection__btc_1h_not_downtrend     = buy_protection_params[18]["btc_1h_not_downtrend"]

    buy_condition_19_enable = buy_protection_params[19]["enable"]
    buy_19_protection__ema_fast                 = buy_protection_params[19]["ema_fast"]
    buy_19_protection__ema_fast_len             = buy_protection_params[19]["ema_fast_len"]
    buy_19_protection__ema_slow                 = buy_protection_params[19]["ema_slow"]
    buy_19_protection__ema_slow_len             = buy_protection_params[19]["ema_slow_len"]
    buy_19_protection__close_above_ema_fast     = buy_protection_params[19]["close_above_ema_fast"]
    buy_19_protection__close_above_ema_fast_len = buy_protection_params[19]["close_above_ema_fast_len"]
    buy_19_protection__close_above_ema_slow     = buy_protection_params[19]["close_above_ema_slow"]
    buy_19_protection__close_above_ema_slow_len = buy_protection_params[19]["close_above_ema_slow_len"]
    buy_19_protection__sma200_rising            = buy_protection_params[19]["sma200_rising"]
    buy_19_protection__sma200_rising_val        = buy_protection_params[19]["sma200_rising_val"]
    buy_19_protection__sma200_1h_rising         = buy_protection_params[19]["sma200_1h_rising"]
    buy_19_protection__sma200_1h_rising_val     = buy_protection_params[19]["sma200_1h_rising_val"]
    buy_19_protection__safe_dips                = buy_protection_params[19]["safe_dips"]
    buy_19_protection__safe_dips_type           = buy_protection_params[19]["safe_dips_type"]
    buy_19_protection__safe_pump                = buy_protection_params[19]["safe_pump"]
    buy_19_protection__safe_pump_type           = buy_protection_params[19]["safe_pump_type"]
    buy_19_protection__safe_pump_period         = buy_protection_params[19]["safe_pump_period"]
    buy_19_protection__btc_1h_not_downtrend     = buy_protection_params[19]["btc_1h_not_downtrend"]

    buy_condition_20_enable = buy_protection_params[20]["enable"]
    buy_20_protection__ema_fast                 = buy_protection_params[20]["ema_fast"]
    buy_20_protection__ema_fast_len             = buy_protection_params[20]["ema_fast_len"]
    buy_20_protection__ema_slow                 = buy_protection_params[20]["ema_slow"]
    buy_20_protection__ema_slow_len             = buy_protection_params[20]["ema_slow_len"]
    buy_20_protection__close_above_ema_fast     = buy_protection_params[20]["close_above_ema_fast"]
    buy_20_protection__close_above_ema_fast_len = buy_protection_params[20]["close_above_ema_fast_len"]
    buy_20_protection__close_above_ema_slow     = buy_protection_params[20]["close_above_ema_slow"]
    buy_20_protection__close_above_ema_slow_len = buy_protection_params[20]["close_above_ema_slow_len"]
    buy_20_protection__sma200_rising            = buy_protection_params[20]["sma200_rising"]
    buy_20_protection__sma200_rising_val        = buy_protection_params[20]["sma200_rising_val"]
    buy_20_protection__sma200_1h_rising         = buy_protection_params[20]["sma200_1h_rising"]
    buy_20_protection__sma200_1h_rising_val     = buy_protection_params[20]["sma200_1h_rising_val"]
    buy_20_protection__safe_dips                = buy_protection_params[20]["safe_dips"]
    buy_20_protection__safe_dips_type           = buy_protection_params[20]["safe_dips_type"]
    buy_20_protection__safe_pump                = buy_protection_params[20]["safe_pump"]
    buy_20_protection__safe_pump_type           = buy_protection_params[20]["safe_pump_type"]
    buy_20_protection__safe_pump_period         = buy_protection_params[20]["safe_pump_period"]
    buy_20_protection__btc_1h_not_downtrend     = buy_protection_params[20]["btc_1h_not_downtrend"]

    buy_condition_21_enable = buy_protection_params[21]["enable"]
    buy_21_protection__ema_fast                 = buy_protection_params[21]["ema_fast"]
    buy_21_protection__ema_fast_len             = buy_protection_params[21]["ema_fast_len"]
    buy_21_protection__ema_slow                 = buy_protection_params[21]["ema_slow"]
    buy_21_protection__ema_slow_len             = buy_protection_params[21]["ema_slow_len"]
    buy_21_protection__close_above_ema_fast     = buy_protection_params[21]["close_above_ema_fast"]
    buy_21_protection__close_above_ema_fast_len = buy_protection_params[21]["close_above_ema_fast_len"]
    buy_21_protection__close_above_ema_slow     = buy_protection_params[21]["close_above_ema_slow"]
    buy_21_protection__close_above_ema_slow_len = buy_protection_params[21]["close_above_ema_slow_len"]
    buy_21_protection__sma200_rising            = buy_protection_params[21]["sma200_rising"]
    buy_21_protection__sma200_rising_val        = buy_protection_params[21]["sma200_rising_val"]
    buy_21_protection__sma200_1h_rising         = buy_protection_params[21]["sma200_1h_rising"]
    buy_21_protection__sma200_1h_rising_val     = buy_protection_params[21]["sma200_1h_rising_val"]
    buy_21_protection__safe_dips                = buy_protection_params[21]["safe_dips"]
    buy_21_protection__safe_dips_type           = buy_protection_params[21]["safe_dips_type"]
    buy_21_protection__safe_pump                = buy_protection_params[21]["safe_pump"]
    buy_21_protection__safe_pump_type           = buy_protection_params[21]["safe_pump_type"]
    buy_21_protection__safe_pump_period         = buy_protection_params[21]["safe_pump_period"]
    buy_21_protection__btc_1h_not_downtrend     = buy_protection_params[21]["btc_1h_not_downtrend"]

    buy_condition_22_enable = buy_protection_params[22]["enable"]
    buy_22_protection__ema_fast                 = buy_protection_params[22]["ema_fast"]
    buy_22_protection__ema_fast_len             = buy_protection_params[22]["ema_fast_len"]
    buy_22_protection__ema_slow                 = buy_protection_params[22]["ema_slow"]
    buy_22_protection__ema_slow_len             = buy_protection_params[22]["ema_slow_len"]
    buy_22_protection__close_above_ema_fast     = buy_protection_params[22]["close_above_ema_fast"]
    buy_22_protection__close_above_ema_fast_len = buy_protection_params[22]["close_above_ema_fast_len"]
    buy_22_protection__close_above_ema_slow     = buy_protection_params[22]["close_above_ema_slow"]
    buy_22_protection__close_above_ema_slow_len = buy_protection_params[22]["close_above_ema_slow_len"]
    buy_22_protection__sma200_rising            = buy_protection_params[22]["sma200_rising"]
    buy_22_protection__sma200_rising_val        = buy_protection_params[22]["sma200_rising_val"]
    buy_22_protection__sma200_1h_rising         = buy_protection_params[22]["sma200_1h_rising"]
    buy_22_protection__sma200_1h_rising_val     = buy_protection_params[22]["sma200_1h_rising_val"]
    buy_22_protection__safe_dips                = buy_protection_params[22]["safe_dips"]
    buy_22_protection__safe_dips_type           = buy_protection_params[22]["safe_dips_type"]
    buy_22_protection__safe_pump                = buy_protection_params[22]["safe_pump"]
    buy_22_protection__safe_pump_type           = buy_protection_params[22]["safe_pump_type"]
    buy_22_protection__safe_pump_period         = buy_protection_params[22]["safe_pump_period"]
    buy_22_protection__btc_1h_not_downtrend     = buy_protection_params[22]["btc_1h_not_downtrend"]

    buy_condition_23_enable = buy_protection_params[23]["enable"]
    buy_23_protection__ema_fast                 = buy_protection_params[23]["ema_fast"]
    buy_23_protection__ema_fast_len             = buy_protection_params[23]["ema_fast_len"]
    buy_23_protection__ema_slow                 = buy_protection_params[23]["ema_slow"]
    buy_23_protection__ema_slow_len             = buy_protection_params[23]["ema_slow_len"]
    buy_23_protection__close_above_ema_fast     = buy_protection_params[23]["close_above_ema_fast"]
    buy_23_protection__close_above_ema_fast_len = buy_protection_params[23]["close_above_ema_fast_len"]
    buy_23_protection__close_above_ema_slow     = buy_protection_params[23]["close_above_ema_slow"]
    buy_23_protection__close_above_ema_slow_len = buy_protection_params[23]["close_above_ema_slow_len"]
    buy_23_protection__sma200_rising            = buy_protection_params[23]["sma200_rising"]
    buy_23_protection__sma200_rising_val        = buy_protection_params[23]["sma200_rising_val"]
    buy_23_protection__sma200_1h_rising         = buy_protection_params[23]["sma200_1h_rising"]
    buy_23_protection__sma200_1h_rising_val     = buy_protection_params[23]["sma200_1h_rising_val"]
    buy_23_protection__safe_dips                = buy_protection_params[23]["safe_dips"]
    buy_23_protection__safe_dips_type           = buy_protection_params[23]["safe_dips_type"]
    buy_23_protection__safe_pump                = buy_protection_params[23]["safe_pump"]
    buy_23_protection__safe_pump_type           = buy_protection_params[23]["safe_pump_type"]
    buy_23_protection__safe_pump_period         = buy_protection_params[23]["safe_pump_period"]
    buy_23_protection__btc_1h_not_downtrend     = buy_protection_params[23]["btc_1h_not_downtrend"]

    buy_condition_24_enable = buy_protection_params[24]["enable"]
    buy_24_protection__ema_fast                 = buy_protection_params[24]["ema_fast"]
    buy_24_protection__ema_fast_len             = buy_protection_params[24]["ema_fast_len"]
    buy_24_protection__ema_slow                 = buy_protection_params[24]["ema_slow"]
    buy_24_protection__ema_slow_len             = buy_protection_params[24]["ema_slow_len"]
    buy_24_protection__close_above_ema_fast     = buy_protection_params[24]["close_above_ema_fast"]
    buy_24_protection__close_above_ema_fast_len = buy_protection_params[24]["close_above_ema_fast_len"]
    buy_24_protection__close_above_ema_slow     = buy_protection_params[24]["close_above_ema_slow"]
    buy_24_protection__close_above_ema_slow_len = buy_protection_params[24]["close_above_ema_slow_len"]
    buy_24_protection__sma200_rising            = buy_protection_params[24]["sma200_rising"]
    buy_24_protection__sma200_rising_val        = buy_protection_params[24]["sma200_rising_val"]
    buy_24_protection__sma200_1h_rising         = buy_protection_params[24]["sma200_1h_rising"]
    buy_24_protection__sma200_1h_rising_val     = buy_protection_params[24]["sma200_1h_rising_val"]
    buy_24_protection__safe_dips                = buy_protection_params[24]["safe_dips"]
    buy_24_protection__safe_dips_type           = buy_protection_params[24]["safe_dips_type"]
    buy_24_protection__safe_pump                = buy_protection_params[24]["safe_pump"]
    buy_24_protection__safe_pump_type           = buy_protection_params[24]["safe_pump_type"]
    buy_24_protection__safe_pump_period         = buy_protection_params[24]["safe_pump_period"]
    buy_24_protection__btc_1h_not_downtrend     = buy_protection_params[24]["btc_1h_not_downtrend"]

    buy_condition_25_enable = buy_protection_params[25]["enable"]
    buy_25_protection__ema_fast                 = buy_protection_params[25]["ema_fast"]
    buy_25_protection__ema_fast_len             = buy_protection_params[25]["ema_fast_len"]
    buy_25_protection__ema_slow                 = buy_protection_params[25]["ema_slow"]
    buy_25_protection__ema_slow_len             = buy_protection_params[25]["ema_slow_len"]
    buy_25_protection__close_above_ema_fast     = buy_protection_params[25]["close_above_ema_fast"]
    buy_25_protection__close_above_ema_fast_len = buy_protection_params[25]["close_above_ema_fast_len"]
    buy_25_protection__close_above_ema_slow     = buy_protection_params[25]["close_above_ema_slow"]
    buy_25_protection__close_above_ema_slow_len = buy_protection_params[25]["close_above_ema_slow_len"]
    buy_25_protection__sma200_rising            = buy_protection_params[25]["sma200_rising"]
    buy_25_protection__sma200_rising_val        = buy_protection_params[25]["sma200_rising_val"]
    buy_25_protection__sma200_1h_rising         = buy_protection_params[25]["sma200_1h_rising"]
    buy_25_protection__sma200_1h_rising_val     = buy_protection_params[25]["sma200_1h_rising_val"]
    buy_25_protection__safe_dips                = buy_protection_params[25]["safe_dips"]
    buy_25_protection__safe_dips_type           = buy_protection_params[25]["safe_dips_type"]
    buy_25_protection__safe_pump                = buy_protection_params[25]["safe_pump"]
    buy_25_protection__safe_pump_type           = buy_protection_params[25]["safe_pump_type"]
    buy_25_protection__safe_pump_period         = buy_protection_params[25]["safe_pump_period"]
    buy_25_protection__btc_1h_not_downtrend     = buy_protection_params[25]["btc_1h_not_downtrend"]

    buy_condition_26_enable = buy_protection_params[26]["enable"]
    buy_26_protection__ema_fast                 = buy_protection_params[26]["ema_fast"]
    buy_26_protection__ema_fast_len             = buy_protection_params[26]["ema_fast_len"]
    buy_26_protection__ema_slow                 = buy_protection_params[26]["ema_slow"]
    buy_26_protection__ema_slow_len             = buy_protection_params[26]["ema_slow_len"]
    buy_26_protection__close_above_ema_fast     = buy_protection_params[26]["close_above_ema_fast"]
    buy_26_protection__close_above_ema_fast_len = buy_protection_params[26]["close_above_ema_fast_len"]
    buy_26_protection__close_above_ema_slow     = buy_protection_params[26]["close_above_ema_slow"]
    buy_26_protection__close_above_ema_slow_len = buy_protection_params[26]["close_above_ema_slow_len"]
    buy_26_protection__sma200_rising            = buy_protection_params[26]["sma200_rising"]
    buy_26_protection__sma200_rising_val        = buy_protection_params[26]["sma200_rising_val"]
    buy_26_protection__sma200_1h_rising         = buy_protection_params[26]["sma200_1h_rising"]
    buy_26_protection__sma200_1h_rising_val     = buy_protection_params[26]["sma200_1h_rising_val"]
    buy_26_protection__safe_dips                = buy_protection_params[26]["safe_dips"]
    buy_26_protection__safe_dips_type           = buy_protection_params[26]["safe_dips_type"]
    buy_26_protection__safe_pump                = buy_protection_params[26]["safe_pump"]
    buy_26_protection__safe_pump_type           = buy_protection_params[26]["safe_pump_type"]
    buy_26_protection__safe_pump_period         = buy_protection_params[26]["safe_pump_period"]
    buy_26_protection__btc_1h_not_downtrend     = buy_protection_params[26]["btc_1h_not_downtrend"]

    buy_condition_27_enable = buy_protection_params[27]["enable"]
    buy_27_protection__ema_fast                 = buy_protection_params[27]["ema_fast"]
    buy_27_protection__ema_fast_len             = buy_protection_params[27]["ema_fast_len"]
    buy_27_protection__ema_slow                 = buy_protection_params[27]["ema_slow"]
    buy_27_protection__ema_slow_len             = buy_protection_params[27]["ema_slow_len"]
    buy_27_protection__close_above_ema_fast     = buy_protection_params[27]["close_above_ema_fast"]
    buy_27_protection__close_above_ema_fast_len = buy_protection_params[27]["close_above_ema_fast_len"]
    buy_27_protection__close_above_ema_slow     = buy_protection_params[27]["close_above_ema_slow"]
    buy_27_protection__close_above_ema_slow_len = buy_protection_params[27]["close_above_ema_slow_len"]
    buy_27_protection__sma200_rising            = buy_protection_params[27]["sma200_rising"]
    buy_27_protection__sma200_rising_val        = buy_protection_params[27]["sma200_rising_val"]
    buy_27_protection__sma200_1h_rising         = buy_protection_params[27]["sma200_1h_rising"]
    buy_27_protection__sma200_1h_rising_val     = buy_protection_params[27]["sma200_1h_rising_val"]
    buy_27_protection__safe_dips                = buy_protection_params[27]["safe_dips"]
    buy_27_protection__safe_dips_type           = buy_protection_params[27]["safe_dips_type"]
    buy_27_protection__safe_pump                = buy_protection_params[27]["safe_pump"]
    buy_27_protection__safe_pump_type           = buy_protection_params[27]["safe_pump_type"]
    buy_27_protection__safe_pump_period         = buy_protection_params[27]["safe_pump_period"]
    buy_27_protection__btc_1h_not_downtrend     = buy_protection_params[27]["btc_1h_not_downtrend"]

    buy_condition_28_enable = buy_protection_params[28]["enable"]
    buy_28_protection__ema_fast                 = buy_protection_params[28]["ema_fast"]
    buy_28_protection__ema_fast_len             = buy_protection_params[28]["ema_fast_len"]
    buy_28_protection__ema_slow                 = buy_protection_params[28]["ema_slow"]
    buy_28_protection__ema_slow_len             = buy_protection_params[28]["ema_slow_len"]
    buy_28_protection__close_above_ema_fast     = buy_protection_params[28]["close_above_ema_fast"]
    buy_28_protection__close_above_ema_fast_len = buy_protection_params[28]["close_above_ema_fast_len"]
    buy_28_protection__close_above_ema_slow     = buy_protection_params[28]["close_above_ema_slow"]
    buy_28_protection__close_above_ema_slow_len = buy_protection_params[28]["close_above_ema_slow_len"]
    buy_28_protection__sma200_rising            = buy_protection_params[28]["sma200_rising"]
    buy_28_protection__sma200_rising_val        = buy_protection_params[28]["sma200_rising_val"]
    buy_28_protection__sma200_1h_rising         = buy_protection_params[28]["sma200_1h_rising"]
    buy_28_protection__sma200_1h_rising_val     = buy_protection_params[28]["sma200_1h_rising_val"]
    buy_28_protection__safe_dips                = buy_protection_params[28]["safe_dips"]
    buy_28_protection__safe_dips_type           = buy_protection_params[28]["safe_dips_type"]
    buy_28_protection__safe_pump                = buy_protection_params[28]["safe_pump"]
    buy_28_protection__safe_pump_type           = buy_protection_params[28]["safe_pump_type"]
    buy_28_protection__safe_pump_period         = buy_protection_params[28]["safe_pump_period"]
    buy_28_protection__btc_1h_not_downtrend     = buy_protection_params[28]["btc_1h_not_downtrend"]

    buy_condition_29_enable = buy_protection_params[29]["enable"]
    buy_29_protection__ema_fast                 = buy_protection_params[29]["ema_fast"]
    buy_29_protection__ema_fast_len             = buy_protection_params[29]["ema_fast_len"]
    buy_29_protection__ema_slow                 = buy_protection_params[29]["ema_slow"]
    buy_29_protection__ema_slow_len             = buy_protection_params[29]["ema_slow_len"]
    buy_29_protection__close_above_ema_fast     = buy_protection_params[29]["close_above_ema_fast"]
    buy_29_protection__close_above_ema_fast_len = buy_protection_params[29]["close_above_ema_fast_len"]
    buy_29_protection__close_above_ema_slow     = buy_protection_params[29]["close_above_ema_slow"]
    buy_29_protection__close_above_ema_slow_len = buy_protection_params[29]["close_above_ema_slow_len"]
    buy_29_protection__sma200_rising            = buy_protection_params[29]["sma200_rising"]
    buy_29_protection__sma200_rising_val        = buy_protection_params[29]["sma200_rising_val"]
    buy_29_protection__sma200_1h_rising         = buy_protection_params[29]["sma200_1h_rising"]
    buy_29_protection__sma200_1h_rising_val     = buy_protection_params[29]["sma200_1h_rising_val"]
    buy_29_protection__safe_dips                = buy_protection_params[29]["safe_dips"]
    buy_29_protection__safe_dips_type           = buy_protection_params[29]["safe_dips_type"]
    buy_29_protection__safe_pump                = buy_protection_params[29]["safe_pump"]
    buy_29_protection__safe_pump_type           = buy_protection_params[29]["safe_pump_type"]
    buy_29_protection__safe_pump_period         = buy_protection_params[29]["safe_pump_period"]
    buy_29_protection__btc_1h_not_downtrend     = buy_protection_params[29]["btc_1h_not_downtrend"]

    buy_condition_30_enable = buy_protection_params[30]["enable"]
    buy_30_protection__ema_fast                 = buy_protection_params[30]["ema_fast"]
    buy_30_protection__ema_fast_len             = buy_protection_params[30]["ema_fast_len"]
    buy_30_protection__ema_slow                 = buy_protection_params[30]["ema_slow"]
    buy_30_protection__ema_slow_len             = buy_protection_params[30]["ema_slow_len"]
    buy_30_protection__close_above_ema_fast     = buy_protection_params[30]["close_above_ema_fast"]
    buy_30_protection__close_above_ema_fast_len = buy_protection_params[30]["close_above_ema_fast_len"]
    buy_30_protection__close_above_ema_slow     = buy_protection_params[30]["close_above_ema_slow"]
    buy_30_protection__close_above_ema_slow_len = buy_protection_params[30]["close_above_ema_slow_len"]
    buy_30_protection__sma200_rising            = buy_protection_params[30]["sma200_rising"]
    buy_30_protection__sma200_rising_val        = buy_protection_params[30]["sma200_rising_val"]
    buy_30_protection__sma200_1h_rising         = buy_protection_params[30]["sma200_1h_rising"]
    buy_30_protection__sma200_1h_rising_val     = buy_protection_params[30]["sma200_1h_rising_val"]
    buy_30_protection__safe_dips                = buy_protection_params[30]["safe_dips"]
    buy_30_protection__safe_dips_type           = buy_protection_params[30]["safe_dips_type"]
    buy_30_protection__safe_pump                = buy_protection_params[30]["safe_pump"]
    buy_30_protection__safe_pump_type           = buy_protection_params[30]["safe_pump_type"]
    buy_30_protection__safe_pump_period         = buy_protection_params[30]["safe_pump_period"]
    buy_30_protection__btc_1h_not_downtrend     = buy_protection_params[30]["btc_1h_not_downtrend"]

    buy_condition_31_enable = buy_protection_params[31]["enable"]
    buy_31_protection__ema_fast                 = buy_protection_params[31]["ema_fast"]
    buy_31_protection__ema_fast_len             = buy_protection_params[31]["ema_fast_len"]
    buy_31_protection__ema_slow                 = buy_protection_params[31]["ema_slow"]
    buy_31_protection__ema_slow_len             = buy_protection_params[31]["ema_slow_len"]
    buy_31_protection__close_above_ema_fast     = buy_protection_params[31]["close_above_ema_fast"]
    buy_31_protection__close_above_ema_fast_len = buy_protection_params[31]["close_above_ema_fast_len"]
    buy_31_protection__close_above_ema_slow     = buy_protection_params[31]["close_above_ema_slow"]
    buy_31_protection__close_above_ema_slow_len = buy_protection_params[31]["close_above_ema_slow_len"]
    buy_31_protection__sma200_rising            = buy_protection_params[31]["sma200_rising"]
    buy_31_protection__sma200_rising_val        = buy_protection_params[31]["sma200_rising_val"]
    buy_31_protection__sma200_1h_rising         = buy_protection_params[31]["sma200_1h_rising"]
    buy_31_protection__sma200_1h_rising_val     = buy_protection_params[31]["sma200_1h_rising_val"]
    buy_31_protection__safe_dips                = buy_protection_params[31]["safe_dips"]
    buy_31_protection__safe_dips_type           = buy_protection_params[31]["safe_dips_type"]
    buy_31_protection__safe_pump                = buy_protection_params[31]["safe_pump"]
    buy_31_protection__safe_pump_type           = buy_protection_params[31]["safe_pump_type"]
    buy_31_protection__safe_pump_period         = buy_protection_params[31]["safe_pump_period"]
    buy_31_protection__btc_1h_not_downtrend     = buy_protection_params[31]["btc_1h_not_downtrend"]

    buy_condition_32_enable = buy_protection_params[32]["enable"]
    buy_32_protection__ema_fast                 = buy_protection_params[32]["ema_fast"]
    buy_32_protection__ema_fast_len             = buy_protection_params[32]["ema_fast_len"]
    buy_32_protection__ema_slow                 = buy_protection_params[32]["ema_slow"]
    buy_32_protection__ema_slow_len             = buy_protection_params[32]["ema_slow_len"]
    buy_32_protection__close_above_ema_fast     = buy_protection_params[32]["close_above_ema_fast"]
    buy_32_protection__close_above_ema_fast_len = buy_protection_params[32]["close_above_ema_fast_len"]
    buy_32_protection__close_above_ema_slow     = buy_protection_params[32]["close_above_ema_slow"]
    buy_32_protection__close_above_ema_slow_len = buy_protection_params[32]["close_above_ema_slow_len"]
    buy_32_protection__sma200_rising            = buy_protection_params[32]["sma200_rising"]
    buy_32_protection__sma200_rising_val        = buy_protection_params[32]["sma200_rising_val"]
    buy_32_protection__sma200_1h_rising         = buy_protection_params[32]["sma200_1h_rising"]
    buy_32_protection__sma200_1h_rising_val     = buy_protection_params[32]["sma200_1h_rising_val"]
    buy_32_protection__safe_dips                = buy_protection_params[32]["safe_dips"]
    buy_32_protection__safe_dips_type           = buy_protection_params[32]["safe_dips_type"]
    buy_32_protection__safe_pump                = buy_protection_params[32]["safe_pump"]
    buy_32_protection__safe_pump_type           = buy_protection_params[32]["safe_pump_type"]
    buy_32_protection__safe_pump_period         = buy_protection_params[32]["safe_pump_period"]
    buy_32_protection__btc_1h_not_downtrend     = buy_protection_params[32]["btc_1h_not_downtrend"]

    buy_condition_33_enable = buy_protection_params[33]["enable"]
    buy_33_protection__ema_fast                 = buy_protection_params[33]["ema_fast"]
    buy_33_protection__ema_fast_len             = buy_protection_params[33]["ema_fast_len"]
    buy_33_protection__ema_slow                 = buy_protection_params[33]["ema_slow"]
    buy_33_protection__ema_slow_len             = buy_protection_params[33]["ema_slow_len"]
    buy_33_protection__close_above_ema_fast     = buy_protection_params[33]["close_above_ema_fast"]
    buy_33_protection__close_above_ema_fast_len = buy_protection_params[33]["close_above_ema_fast_len"]
    buy_33_protection__close_above_ema_slow     = buy_protection_params[33]["close_above_ema_slow"]
    buy_33_protection__close_above_ema_slow_len = buy_protection_params[33]["close_above_ema_slow_len"]
    buy_33_protection__sma200_rising            = buy_protection_params[33]["sma200_rising"]
    buy_33_protection__sma200_rising_val        = buy_protection_params[33]["sma200_rising_val"]
    buy_33_protection__sma200_1h_rising         = buy_protection_params[33]["sma200_1h_rising"]
    buy_33_protection__sma200_1h_rising_val     = buy_protection_params[33]["sma200_1h_rising_val"]
    buy_33_protection__safe_dips                = buy_protection_params[33]["safe_dips"]
    buy_33_protection__safe_dips_type           = buy_protection_params[33]["safe_dips_type"]
    buy_33_protection__safe_pump                = buy_protection_params[33]["safe_pump"]
    buy_33_protection__safe_pump_type           = buy_protection_params[33]["safe_pump_type"]
    buy_33_protection__safe_pump_period         = buy_protection_params[33]["safe_pump_period"]
    buy_33_protection__btc_1h_not_downtrend     = buy_protection_params[33]["btc_1h_not_downtrend"]

    buy_condition_34_enable = buy_protection_params[34]["enable"]
    buy_34_protection__ema_fast                 = buy_protection_params[34]["ema_fast"]
    buy_34_protection__ema_fast_len             = buy_protection_params[34]["ema_fast_len"]
    buy_34_protection__ema_slow                 = buy_protection_params[34]["ema_slow"]
    buy_34_protection__ema_slow_len             = buy_protection_params[34]["ema_slow_len"]
    buy_34_protection__close_above_ema_fast     = buy_protection_params[34]["close_above_ema_fast"]
    buy_34_protection__close_above_ema_fast_len = buy_protection_params[34]["close_above_ema_fast_len"]
    buy_34_protection__close_above_ema_slow     = buy_protection_params[34]["close_above_ema_slow"]
    buy_34_protection__close_above_ema_slow_len = buy_protection_params[34]["close_above_ema_slow_len"]
    buy_34_protection__sma200_rising            = buy_protection_params[34]["sma200_rising"]
    buy_34_protection__sma200_rising_val        = buy_protection_params[34]["sma200_rising_val"]
    buy_34_protection__sma200_1h_rising         = buy_protection_params[34]["sma200_1h_rising"]
    buy_34_protection__sma200_1h_rising_val     = buy_protection_params[34]["sma200_1h_rising_val"]
    buy_34_protection__safe_dips                = buy_protection_params[34]["safe_dips"]
    buy_34_protection__safe_dips_type           = buy_protection_params[34]["safe_dips_type"]
    buy_34_protection__safe_pump                = buy_protection_params[34]["safe_pump"]
    buy_34_protection__safe_pump_type           = buy_protection_params[34]["safe_pump_type"]
    buy_34_protection__safe_pump_period         = buy_protection_params[34]["safe_pump_period"]
    buy_34_protection__btc_1h_not_downtrend     = buy_protection_params[34]["btc_1h_not_downtrend"]

    buy_condition_35_enable = buy_protection_params[35]["enable"]
    buy_35_protection__ema_fast                 = buy_protection_params[35]["ema_fast"]
    buy_35_protection__ema_fast_len             = buy_protection_params[35]["ema_fast_len"]
    buy_35_protection__ema_slow                 = buy_protection_params[35]["ema_slow"]
    buy_35_protection__ema_slow_len             = buy_protection_params[35]["ema_slow_len"]
    buy_35_protection__close_above_ema_fast     = buy_protection_params[35]["close_above_ema_fast"]
    buy_35_protection__close_above_ema_fast_len = buy_protection_params[35]["close_above_ema_fast_len"]
    buy_35_protection__close_above_ema_slow     = buy_protection_params[35]["close_above_ema_slow"]
    buy_35_protection__close_above_ema_slow_len = buy_protection_params[35]["close_above_ema_slow_len"]
    buy_35_protection__sma200_rising            = buy_protection_params[35]["sma200_rising"]
    buy_35_protection__sma200_rising_val        = buy_protection_params[35]["sma200_rising_val"]
    buy_35_protection__sma200_1h_rising         = buy_protection_params[35]["sma200_1h_rising"]
    buy_35_protection__sma200_1h_rising_val     = buy_protection_params[35]["sma200_1h_rising_val"]
    buy_35_protection__safe_dips                = buy_protection_params[35]["safe_dips"]
    buy_35_protection__safe_dips_type           = buy_protection_params[35]["safe_dips_type"]
    buy_35_protection__safe_pump                = buy_protection_params[35]["safe_pump"]
    buy_35_protection__safe_pump_type           = buy_protection_params[35]["safe_pump_type"]
    buy_35_protection__safe_pump_period         = buy_protection_params[35]["safe_pump_period"]
    buy_35_protection__btc_1h_not_downtrend     = buy_protection_params[35]["btc_1h_not_downtrend"]

    buy_condition_36_enable = buy_protection_params[36]["enable"]
    buy_36_protection__ema_fast                 = buy_protection_params[36]["ema_fast"]
    buy_36_protection__ema_fast_len             = buy_protection_params[36]["ema_fast_len"]
    buy_36_protection__ema_slow                 = buy_protection_params[36]["ema_slow"]
    buy_36_protection__ema_slow_len             = buy_protection_params[36]["ema_slow_len"]
    buy_36_protection__close_above_ema_fast     = buy_protection_params[36]["close_above_ema_fast"]
    buy_36_protection__close_above_ema_fast_len = buy_protection_params[36]["close_above_ema_fast_len"]
    buy_36_protection__close_above_ema_slow     = buy_protection_params[36]["close_above_ema_slow"]
    buy_36_protection__close_above_ema_slow_len = buy_protection_params[36]["close_above_ema_slow_len"]
    buy_36_protection__sma200_rising            = buy_protection_params[36]["sma200_rising"]
    buy_36_protection__sma200_rising_val        = buy_protection_params[36]["sma200_rising_val"]
    buy_36_protection__sma200_1h_rising         = buy_protection_params[36]["sma200_1h_rising"]
    buy_36_protection__sma200_1h_rising_val     = buy_protection_params[36]["sma200_1h_rising_val"]
    buy_36_protection__safe_dips                = buy_protection_params[36]["safe_dips"]
    buy_36_protection__safe_dips_type           = buy_protection_params[36]["safe_dips_type"]
    buy_36_protection__safe_pump                = buy_protection_params[36]["safe_pump"]
    buy_36_protection__safe_pump_type           = buy_protection_params[36]["safe_pump_type"]
    buy_36_protection__safe_pump_period         = buy_protection_params[36]["safe_pump_period"]
    buy_36_protection__btc_1h_not_downtrend     = buy_protection_params[36]["btc_1h_not_downtrend"]

    buy_condition_37_enable = buy_protection_params[37]["enable"]
    buy_37_protection__ema_fast                 = buy_protection_params[37]["ema_fast"]
    buy_37_protection__ema_fast_len             = buy_protection_params[37]["ema_fast_len"]
    buy_37_protection__ema_slow                 = buy_protection_params[37]["ema_slow"]
    buy_37_protection__ema_slow_len             = buy_protection_params[37]["ema_slow_len"]
    buy_37_protection__close_above_ema_fast     = buy_protection_params[37]["close_above_ema_fast"]
    buy_37_protection__close_above_ema_fast_len = buy_protection_params[37]["close_above_ema_fast_len"]
    buy_37_protection__close_above_ema_slow     = buy_protection_params[37]["close_above_ema_slow"]
    buy_37_protection__close_above_ema_slow_len = buy_protection_params[37]["close_above_ema_slow_len"]
    buy_37_protection__sma200_rising            = buy_protection_params[37]["sma200_rising"]
    buy_37_protection__sma200_rising_val        = buy_protection_params[37]["sma200_rising_val"]
    buy_37_protection__sma200_1h_rising         = buy_protection_params[37]["sma200_1h_rising"]
    buy_37_protection__sma200_1h_rising_val     = buy_protection_params[37]["sma200_1h_rising_val"]
    buy_37_protection__safe_dips                = buy_protection_params[37]["safe_dips"]
    buy_37_protection__safe_dips_type           = buy_protection_params[37]["safe_dips_type"]
    buy_37_protection__safe_pump                = buy_protection_params[37]["safe_pump"]
    buy_37_protection__safe_pump_type           = buy_protection_params[37]["safe_pump_type"]
    buy_37_protection__safe_pump_period         = buy_protection_params[37]["safe_pump_period"]
    buy_37_protection__btc_1h_not_downtrend     = buy_protection_params[37]["btc_1h_not_downtrend"]

    buy_condition_38_enable = buy_protection_params[38]["enable"]
    buy_38_protection__ema_fast                 = buy_protection_params[38]["ema_fast"]
    buy_38_protection__ema_fast_len             = buy_protection_params[38]["ema_fast_len"]
    buy_38_protection__ema_slow                 = buy_protection_params[38]["ema_slow"]
    buy_38_protection__ema_slow_len             = buy_protection_params[38]["ema_slow_len"]
    buy_38_protection__close_above_ema_fast     = buy_protection_params[38]["close_above_ema_fast"]
    buy_38_protection__close_above_ema_fast_len = buy_protection_params[38]["close_above_ema_fast_len"]
    buy_38_protection__close_above_ema_slow     = buy_protection_params[38]["close_above_ema_slow"]
    buy_38_protection__close_above_ema_slow_len = buy_protection_params[38]["close_above_ema_slow_len"]
    buy_38_protection__sma200_rising            = buy_protection_params[38]["sma200_rising"]
    buy_38_protection__sma200_rising_val        = buy_protection_params[38]["sma200_rising_val"]
    buy_38_protection__sma200_1h_rising         = buy_protection_params[38]["sma200_1h_rising"]
    buy_38_protection__sma200_1h_rising_val     = buy_protection_params[38]["sma200_1h_rising_val"]
    buy_38_protection__safe_dips                = buy_protection_params[38]["safe_dips"]
    buy_38_protection__safe_dips_type           = buy_protection_params[38]["safe_dips_type"]
    buy_38_protection__safe_pump                = buy_protection_params[38]["safe_pump"]
    buy_38_protection__safe_pump_type           = buy_protection_params[38]["safe_pump_type"]
    buy_38_protection__safe_pump_period         = buy_protection_params[38]["safe_pump_period"]
    buy_38_protection__btc_1h_not_downtrend     = buy_protection_params[38]["btc_1h_not_downtrend"]

    # Strict dips - level 10
    buy_dip_threshold_10_1 = DecimalParameter(0.001, 0.05, default=0.015, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_10_2 = DecimalParameter(0.01, 0.2, default=0.1, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_10_3 = DecimalParameter(0.1, 0.3, default=0.24, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_10_4 = DecimalParameter(0.3, 0.5, default=0.42, space='buy', decimals=3, optimize=False, load=True)
    # Strict dips - level 20
    buy_dip_threshold_20_1 = DecimalParameter(0.001, 0.05, default=0.016, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_20_2 = DecimalParameter(0.01, 0.2, default=0.11, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_20_3 = DecimalParameter(0.1, 0.4, default=0.26, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_20_4 = DecimalParameter(0.36, 0.56, default=0.44, space='buy', decimals=3, optimize=False, load=True)
    # Strict dips - level 30
    buy_dip_threshold_30_1 = DecimalParameter(0.001, 0.05, default=0.018, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_30_2 = DecimalParameter(0.01, 0.2, default=0.12, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_30_3 = DecimalParameter(0.1, 0.4, default=0.28, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_30_4 = DecimalParameter(0.36, 0.56, default=0.46, space='buy', decimals=3, optimize=False, load=True)
    # Strict dips - level 40
    buy_dip_threshold_40_1 = DecimalParameter(0.001, 0.05, default=0.019, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_40_2 = DecimalParameter(0.01, 0.2, default=0.13, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_40_3 = DecimalParameter(0.1, 0.4, default=0.3, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_40_4 = DecimalParameter(0.36, 0.56, default=0.48, space='buy', decimals=3, optimize=False, load=True)
    # Normal dips - level 50
    buy_dip_threshold_50_1 = DecimalParameter(0.001, 0.05, default=0.02, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_50_2 = DecimalParameter(0.01, 0.2, default=0.14, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_50_3 = DecimalParameter(0.05, 0.4, default=0.32, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_50_4 = DecimalParameter(0.2, 0.5, default=0.5, space='buy', decimals=3, optimize=False, load=True)
    # Normal dips - level 60
    buy_dip_threshold_60_1 = DecimalParameter(0.001, 0.05, default=0.022, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_60_2 = DecimalParameter(0.1, 0.22, default=0.18, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_60_3 = DecimalParameter(0.2, 0.4, default=0.34, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_60_4 = DecimalParameter(0.4, 0.6, default=0.56, space='buy', decimals=3, optimize=False, load=True)
    # Normal dips - level 70
    buy_dip_threshold_70_1 = DecimalParameter(0.001, 0.05, default=0.023, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_70_2 = DecimalParameter(0.16, 0.28, default=0.2, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_70_3 = DecimalParameter(0.2, 0.4, default=0.36, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_70_4 = DecimalParameter(0.5, 0.7, default=0.6, space='buy', decimals=3, optimize=False, load=True)
    # Normal dips - level 80
    buy_dip_threshold_80_1 = DecimalParameter(0.001, 0.05, default=0.024, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_80_2 = DecimalParameter(0.16, 0.28, default=0.22, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_80_3 = DecimalParameter(0.2, 0.4, default=0.38, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_80_4 = DecimalParameter(0.5, 0.7, default=0.66, space='buy', decimals=3, optimize=False, load=True)
    # Normal dips - level 70
    buy_dip_threshold_90_1 = DecimalParameter(0.001, 0.05, default=0.025, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_90_2 = DecimalParameter(0.16, 0.28, default=0.23, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_90_3 = DecimalParameter(0.3, 0.5, default=0.4, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_90_4 = DecimalParameter(0.6, 0.8, default=0.7, space='buy', decimals=3, optimize=False, load=True)
    # Loose dips - level 100
    buy_dip_threshold_100_1 = DecimalParameter(0.001, 0.05, default=0.026, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_100_2 = DecimalParameter(0.16, 0.3, default=0.24, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_100_3 = DecimalParameter(0.3, 0.5, default=0.42, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_100_4 = DecimalParameter(0.6, 1.0, default=0.8, space='buy', decimals=3, optimize=False, load=True)
    # Loose dips - level 110
    buy_dip_threshold_110_1 = DecimalParameter(0.001, 0.05, default=0.027, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_110_2 = DecimalParameter(0.16, 0.3, default=0.26, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_110_3 = DecimalParameter(0.3, 0.5, default=0.44, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_110_4 = DecimalParameter(0.6, 1.0, default=0.84, space='buy', decimals=3, optimize=False, load=True)
    # Loose dips - level 120
    buy_dip_threshold_120_1 = DecimalParameter(0.001, 0.05, default=0.028, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_120_2 = DecimalParameter(0.16, 0.3, default=0.28, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_120_3 = DecimalParameter(0.3, 0.5, default=0.46, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_120_4 = DecimalParameter(0.6, 1.0, default=0.86, space='buy', decimals=3, optimize=False, load=True)
    # Loose dips - level 130
    buy_dip_threshold_130_1 = DecimalParameter(0.001, 0.05, default=0.028, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_130_2 = DecimalParameter(0.16, 0.34, default=0.3, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_130_3 = DecimalParameter(0.36, 0.56, default=0.48, space='buy', decimals=3, optimize=False, load=True)
    buy_dip_threshold_130_4 = DecimalParameter(0.6, 1.0, default=0.9, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 10
    buy_pump_pull_threshold_10_24 = DecimalParameter(1.5, 3.0, default=2.2, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_10_24 = DecimalParameter(0.4, 1.0, default=0.42, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 10
    buy_pump_pull_threshold_10_36 = DecimalParameter(1.5, 3.0, default=2.0, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_10_36 = DecimalParameter(0.4, 1.0, default=0.58, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 10
    buy_pump_pull_threshold_10_48 = DecimalParameter(1.5, 3.0, default=2.0, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_10_48 = DecimalParameter(0.4, 1.0, default=0.8, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 20
    buy_pump_pull_threshold_20_24 = DecimalParameter(1.5, 3.0, default=2.2, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_20_24 = DecimalParameter(0.4, 1.0, default=0.46, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 20
    buy_pump_pull_threshold_20_36 = DecimalParameter(1.5, 3.0, default=2.0, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_20_36 = DecimalParameter(0.4, 1.0, default=0.6, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 20
    buy_pump_pull_threshold_20_48 = DecimalParameter(1.5, 3.0, default=2.0, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_20_48 = DecimalParameter(0.4, 1.0, default=0.81, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 30
    buy_pump_pull_threshold_30_24 = DecimalParameter(1.5, 3.0, default=2.2, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_30_24 = DecimalParameter(0.4, 1.0, default=0.5, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 30
    buy_pump_pull_threshold_30_36 = DecimalParameter(1.5, 3.0, default=2.0, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_30_36 = DecimalParameter(0.4, 1.0, default=0.62, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 30
    buy_pump_pull_threshold_30_48 = DecimalParameter(1.5, 3.0, default=2.0, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_30_48 = DecimalParameter(0.4, 1.0, default=0.82, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 40
    buy_pump_pull_threshold_40_24 = DecimalParameter(1.5, 3.0, default=2.2, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_40_24 = DecimalParameter(0.4, 1.0, default=0.54, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 40
    buy_pump_pull_threshold_40_36 = DecimalParameter(1.5, 3.0, default=2.0, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_40_36 = DecimalParameter(0.4, 1.0, default=0.63, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 40
    buy_pump_pull_threshold_40_48 = DecimalParameter(1.5, 3.0, default=2.0, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_40_48 = DecimalParameter(0.4, 1.0, default=0.84, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 50
    buy_pump_pull_threshold_50_24 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_50_24 = DecimalParameter(0.4, 1.0, default=0.6, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 50
    buy_pump_pull_threshold_50_36 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_50_36 = DecimalParameter(0.4, 1.0, default=0.64, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 50
    buy_pump_pull_threshold_50_48 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_50_48 = DecimalParameter(0.4, 1.0, default=0.85, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 60
    buy_pump_pull_threshold_60_24 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_60_24 = DecimalParameter(0.4, 1.0, default=0.62, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 60
    buy_pump_pull_threshold_60_36 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_60_36 = DecimalParameter(0.4, 1.0, default=0.66, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 60
    buy_pump_pull_threshold_60_48 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_60_48 = DecimalParameter(0.4, 1.0, default=0.9, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 70
    buy_pump_pull_threshold_70_24 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_70_24 = DecimalParameter(0.4, 1.0, default=0.63, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 70
    buy_pump_pull_threshold_70_36 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_70_36 = DecimalParameter(0.4, 1.0, default=0.67, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 70
    buy_pump_pull_threshold_70_48 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_70_48 = DecimalParameter(0.4, 1.0, default=0.95, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 80
    buy_pump_pull_threshold_80_24 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_80_24 = DecimalParameter(0.4, 1.0, default=0.64, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 80
    buy_pump_pull_threshold_80_36 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_80_36 = DecimalParameter(0.4, 1.0, default=0.68, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 80
    buy_pump_pull_threshold_80_48 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_80_48 = DecimalParameter(0.8, 1.1, default=1.0, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 90
    buy_pump_pull_threshold_90_24 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_90_24 = DecimalParameter(0.4, 1.0, default=0.65, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 90
    buy_pump_pull_threshold_90_36 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_90_36 = DecimalParameter(0.4, 1.0, default=0.69, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 90
    buy_pump_pull_threshold_90_48 = DecimalParameter(1.5, 3.0, default=1.75, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_90_48 = DecimalParameter(0.8, 1.2, default=1.1, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 100
    buy_pump_pull_threshold_100_24 = DecimalParameter(1.5, 3.0, default=1.7, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_100_24 = DecimalParameter(0.4, 1.0, default=0.66, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 100
    buy_pump_pull_threshold_100_36 = DecimalParameter(1.5, 3.0, default=1.7, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_100_36 = DecimalParameter(0.4, 1.0, default=0.7, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 100
    buy_pump_pull_threshold_100_48 = DecimalParameter(1.3, 2.0, default=1.4, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_100_48 = DecimalParameter(0.4, 1.8, default=1.6, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 110
    buy_pump_pull_threshold_110_24 = DecimalParameter(1.5, 3.0, default=1.7, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_110_24 = DecimalParameter(0.4, 1.0, default=0.7, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 110
    buy_pump_pull_threshold_110_36 = DecimalParameter(1.5, 3.0, default=1.7, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_110_36 = DecimalParameter(0.4, 1.0, default=0.74, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 110
    buy_pump_pull_threshold_110_48 = DecimalParameter(1.3, 2.0, default=1.4, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_110_48 = DecimalParameter(1.4, 2.0, default=1.8, space='buy', decimals=3, optimize=False, load=True)

    # 24 hours - level 120
    buy_pump_pull_threshold_120_24 = DecimalParameter(1.5, 3.0, default=1.7, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_120_24 = DecimalParameter(0.4, 1.0, default=0.78, space='buy', decimals=3, optimize=False, load=True)
    # 36 hours - level 120
    buy_pump_pull_threshold_120_36 = DecimalParameter(1.5, 3.0, default=1.7, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_120_36 = DecimalParameter(0.4, 1.0, default=0.78, space='buy', decimals=3, optimize=False, load=True)
    # 48 hours - level 120
    buy_pump_pull_threshold_120_48 = DecimalParameter(1.3, 2.0, default=1.4, space='buy', decimals=2, optimize=False, load=True)
    buy_pump_threshold_120_48 = DecimalParameter(1.4, 2.8, default=2.0, space='buy', decimals=3, optimize=False, load=True)

    # 5 hours - level 10
    buy_dump_protection_10_5 = DecimalParameter(0.3, 0.8, default=0.4, space='buy', decimals=2, optimize=False, load=True)

    # 5 hours - level 20
    buy_dump_protection_20_5 = DecimalParameter(0.3, 0.8, default=0.44, space='buy', decimals=2, optimize=False, load=True)

    # 5 hours - level 30
    buy_dump_protection_30_5 = DecimalParameter(0.3, 0.8, default=0.50, space='buy', decimals=2, optimize=False, load=True)

    # 5 hours - level 40
    buy_dump_protection_40_5 = DecimalParameter(0.3, 0.8, default=0.58, space='buy', decimals=2, optimize=False, load=True)

    # 5 hours - level 50
    buy_dump_protection_50_5 = DecimalParameter(0.3, 0.8, default=0.66, space='buy', decimals=2, optimize=False, load=True)

    # 5 hours - level 60
    buy_dump_protection_60_5 = DecimalParameter(0.3, 0.8, default=0.74, space='buy', decimals=2, optimize=False, load=True)

    buy_min_inc_1 = DecimalParameter(0.01, 0.05, default=0.021, space='buy', decimals=3, optimize=False, load=True)
    buy_rsi_1h_min_1 = DecimalParameter(25.0, 40.0, default=20.0, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_1h_max_1 = DecimalParameter(70.0, 90.0, default=84.0, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_1 = DecimalParameter(20.0, 40.0, default=35.4, space='buy', decimals=1, optimize=False, load=True)
    buy_mfi_1 = DecimalParameter(20.0, 40.0, default=50.0, space='buy', decimals=1, optimize=False, load=True)
    buy_cti_1 = DecimalParameter(-0.99, -0.5, default=-0.87, space='buy', decimals=2, optimize=False, load=True)

    buy_rsi_1h_min_2 = DecimalParameter(30.0, 40.0, default=32.0, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_1h_max_2 = DecimalParameter(70.0, 95.0, default=84.0, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_1h_diff_2 = DecimalParameter(30.0, 50.0, default=38.8, space='buy', decimals=1, optimize=False, load=True)
    buy_mfi_2 = DecimalParameter(30.0, 56.0, default=49.0, space='buy', decimals=1, optimize=False, load=True)
    buy_bb_offset_2 = DecimalParameter(0.97, 0.999, default=0.983, space='buy', decimals=3, optimize=False, load=True)
    buy_volume_2 = DecimalParameter(0.6, 6.0, default=1.6, space='buy', decimals=1, optimize=False, load=True)

    buy_bb40_bbdelta_close_3 = DecimalParameter(0.005, 0.06, default=0.045, space='buy', optimize=False, load=True)
    buy_bb40_closedelta_close_3 = DecimalParameter(0.01, 0.03, default=0.022, space='buy', optimize=False, load=True)
    buy_bb40_tail_bbdelta_3 = DecimalParameter(0.15, 0.45, default=0.418, space='buy', optimize=False, load=True)
    buy_ema_rel_3 = DecimalParameter(0.97, 0.999, default=0.986, space='buy', decimals=3, optimize=False, load=True)
    buy_cti_3 = DecimalParameter(-0.99, -0.5, default=-0.9, space='buy', decimals=2, optimize=False, load=True)

    buy_bb20_close_bblowerband_4 = DecimalParameter(0.96, 0.99, default=0.979, space='buy', optimize=False, load=True)
    buy_bb20_volume_4 = DecimalParameter(1.0, 20.0, default=10.0, space='buy', decimals=2, optimize=False, load=True)
    buy_cti_4 = DecimalParameter(-0.99, -0.5, default=-0.68, space='buy', decimals=2, optimize=False, load=True)

    buy_ema_open_mult_5 = DecimalParameter(0.016, 0.03, default=0.018, space='buy', decimals=3, optimize=False, load=True)
    buy_bb_offset_5 = DecimalParameter(0.98, 1.0, default=0.996, space='buy', decimals=3, optimize=False, load=True)
    buy_ema_rel_5 = DecimalParameter(0.97, 0.999, default=0.938, space='buy', decimals=3, optimize=False, load=True)
    buy_cti_5 = DecimalParameter(-0.99, -0.5, default=-0.84, space='buy', decimals=2, optimize=False, load=True)
    buy_volume_5 = DecimalParameter(0.6, 6.0, default=1.8, space='buy', decimals=1, optimize=False, load=True)

    buy_ema_open_mult_6 = DecimalParameter(0.02, 0.03, default=0.021, space='buy', decimals=3, optimize=False, load=True)
    buy_bb_offset_6 = DecimalParameter(0.98, 0.999, default=0.984, space='buy', decimals=3, optimize=False, load=True)

    buy_ema_open_mult_7 = DecimalParameter(0.02, 0.04, default=0.031, space='buy', decimals=3, optimize=False, load=True)
    buy_cti_7 = DecimalParameter(-0.99, -0.5, default=-0.89, space='buy', decimals=2, optimize=False, load=True)

    buy_cti_8 = DecimalParameter(-0.99, -0.5, default=-0.88, space='buy', decimals=2, optimize=False, load=True)
    buy_rsi_8 = DecimalParameter(20.0, 50.0, default=40.0, space='buy', decimals=1, optimize=False, load=True)
    buy_bb_offset_8 = DecimalParameter(0.98, 1.0, default=0.99, space='buy', decimals=3, optimize=False, load=True)
    buy_rsi_1h_8 = DecimalParameter(40.0, 66.0, default=64.0, space='buy', decimals=1, optimize=False, load=True)
    buy_volume_8 = DecimalParameter(0.6, 6.0, default=1.8, space='buy', decimals=1, optimize=False, load=True)

    buy_ma_offset_9 = DecimalParameter(0.91, 0.94, default=0.922, space='buy', decimals=3, optimize=False, load=True)
    buy_bb_offset_9 = DecimalParameter(0.96, 0.98, default=0.942, space='buy', decimals=3, optimize=False, load=True)
    buy_rsi_1h_min_9 = DecimalParameter(26.0, 40.0, default=20.0, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_1h_max_9 = DecimalParameter(70.0, 90.0, default=88.0, space='buy', decimals=1, optimize=False, load=True)
    buy_mfi_9 = DecimalParameter(36.0, 56.0, default=50.0, space='buy', decimals=1, optimize=False, load=True)

    buy_ma_offset_10 = DecimalParameter(0.93, 0.97, default=0.948, space='buy', decimals=3, optimize=False, load=True)
    buy_bb_offset_10 = DecimalParameter(0.97, 0.99, default=0.985, space='buy', decimals=3, optimize=False, load=True)
    buy_rsi_1h_10 = DecimalParameter(20.0, 40.0, default=37.0, space='buy', decimals=1, optimize=False, load=True)

    buy_ma_offset_11 = DecimalParameter(0.93, 0.99, default=0.934, space='buy', decimals=3, optimize=False, load=True)
    buy_min_inc_11 = DecimalParameter(0.005, 0.05, default=0.02, space='buy', decimals=3, optimize=False, load=True)
    buy_rsi_1h_min_11 = DecimalParameter(40.0, 60.0, default=55.0, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_1h_max_11 = DecimalParameter(70.0, 90.0, default=84.0, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_11 = DecimalParameter(34.0, 50.0, default=44.0, space='buy', decimals=1, optimize=False, load=True)
    buy_mfi_11 = DecimalParameter(30.0, 46.0, default=36.0, space='buy', decimals=1, optimize=False, load=True)

    buy_ma_offset_12 = DecimalParameter(0.93, 0.97, default=0.907, space='buy', decimals=3, optimize=False, load=True)
    buy_rsi_12 = DecimalParameter(26.0, 40.0, default=34.0, space='buy', decimals=1, optimize=False, load=True)
    buy_ewo_12 = DecimalParameter(1.0, 6.0, default=1.8, space='buy', decimals=1, optimize=False, load=True)

    buy_ma_offset_13 = DecimalParameter(0.93, 0.98, default=0.99, space='buy', decimals=3, optimize=False, load=True)
    buy_cti_13 = DecimalParameter(-0.99, -0.5, default=-0.74, space='buy', decimals=2, optimize=False, load=True)
    buy_ewo_13 = DecimalParameter(-14.0, -7.0, default=-9.6, space='buy', decimals=1, optimize=False, load=True)

    buy_ema_open_mult_14 = DecimalParameter(0.01, 0.03, default=0.014, space='buy', decimals=3, optimize=False, load=True)
    buy_bb_offset_14 = DecimalParameter(0.98, 1.0, default=0.988, space='buy', decimals=3, optimize=False, load=True)
    buy_ma_offset_14 = DecimalParameter(0.93, 0.99, default=0.98, space='buy', decimals=3, optimize=False, load=True)
    buy_cti_14 = DecimalParameter(-0.99, -0.5, default=-0.86, space='buy', decimals=2, optimize=False, load=True)

    buy_ema_open_mult_15 = DecimalParameter(0.01, 0.03, default=0.024, space='buy', decimals=3, optimize=False, load=True)
    buy_ma_offset_15 = DecimalParameter(0.93, 0.99, default=0.96, space='buy', decimals=3, optimize=False, load=True)
    buy_rsi_15 = DecimalParameter(20.0, 36.0, default=28.0, space='buy', decimals=1, optimize=False, load=True)
    buy_ema_rel_15 = DecimalParameter(0.97, 0.999, default=0.977, space='buy', decimals=3, optimize=False, load=True)

    buy_ma_offset_16 = DecimalParameter(0.93, 0.97, default=0.952, space='buy', decimals=3, optimize=False, load=True)
    buy_rsi_16 = DecimalParameter(26.0, 50.0, default=31.0, space='buy', decimals=1, optimize=False, load=True)
    buy_ewo_16 = DecimalParameter(2.0, 6.0, default=2.8, space='buy', decimals=1, optimize=False, load=True)
    buy_cti_16 = DecimalParameter(-0.99, -0.5, default=-0.84, space='buy', decimals=2, optimize=False, load=True)

    buy_ma_offset_17 = DecimalParameter(0.93, 0.98, default=0.94, space='buy', decimals=3, optimize=False, load=True)
    buy_ewo_17 = DecimalParameter(-18.0, -10.0, default=-12.4, space='buy', decimals=1, optimize=False, load=True)
    buy_cti_17 = DecimalParameter(-0.99, -0.5, default=-0.92, space='buy', decimals=2, optimize=False, load=True)
    buy_volume_17 = DecimalParameter(0.6, 6.0, default=2.0, space='buy', decimals=1, optimize=False, load=True)

    buy_rsi_18 = DecimalParameter(16.0, 32.0, default=30.0, space='buy', decimals=1, optimize=False, load=True)
    buy_bb_offset_18 = DecimalParameter(0.98, 1.0, default=0.985, space='buy', decimals=3, optimize=False, load=True)
    buy_volume_18 = DecimalParameter(0.6, 6.0, default=2.0, space='buy', decimals=1, optimize=False, load=True)
    buy_cti_18 = DecimalParameter(-0.99, -0.5, default=-0.82, space='buy', decimals=2, optimize=False, load=True)

    buy_rsi_1h_min_19 = DecimalParameter(40.0, 70.0, default=30.0, space='buy', decimals=1, optimize=False, load=True)
    buy_chop_min_19 = DecimalParameter(20.0, 60.0, default=23.0, space='buy', decimals=1, optimize=False, load=True)

    buy_rsi_20 = DecimalParameter(20.0, 36.0, default=36.0, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_1h_20 = DecimalParameter(14.0, 30.0, default=16.0, space='buy', decimals=1, optimize=False, load=True)
    buy_cti_20 = DecimalParameter(-0.99, -0.5, default=-0.9, space='buy', decimals=2, optimize=False, load=True)
    buy_volume_20 = DecimalParameter(0.6, 6.0, default=2.0, space='buy', decimals=1, optimize=False, load=True)

    buy_rsi_21 = DecimalParameter(10.0, 28.0, default=14.0, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_1h_21 = DecimalParameter(18.0, 40.0, default=28.0, space='buy', decimals=1, optimize=False, load=True)
    buy_cti_21 = DecimalParameter(-0.99, -0.4, default=-0.9, space='buy', decimals=2, optimize=False, load=True)
    buy_volume_21 = DecimalParameter(0.6, 6.0, default=2.0, space='buy', decimals=1, optimize=False, load=True)

    buy_volume_22 = DecimalParameter(0.5, 6.0, default=2.0, space='buy', decimals=1, optimize=False, load=True)
    buy_bb_offset_22 = DecimalParameter(0.98, 1.0, default=0.984, space='buy', decimals=3, optimize=False, load=True)
    buy_ma_offset_22 = DecimalParameter(0.93, 0.98, default=0.946, space='buy', decimals=3, optimize=False, load=True)
    buy_ewo_22 = DecimalParameter(2.0, 10.0, default=6.2, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_22 = DecimalParameter(26.0, 56.0, default=37.0, space='buy', decimals=1, optimize=False, load=True)

    buy_bb_offset_23 = DecimalParameter(0.97, 1.0, default=0.983, space='buy', decimals=3, optimize=False, load=True)
    buy_ewo_23 = DecimalParameter(2.0, 10.0, default=7.0, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_23 = DecimalParameter(20.0, 40.0, default=30.0, space='buy', decimals=1, optimize=False, load=True)
    buy_rsi_1h_23 = DecimalParameter(60.0, 80.0, default=70.0, space='buy', decimals=1, optimize=False, load=True)

    buy_24_rsi_max = DecimalParameter(26.0, 60.0, default=50.0, space='buy', decimals=1, optimize=False, load=True)
    buy_24_rsi_1h_min = DecimalParameter(40.0, 90.0, default=66.9, space='buy', decimals=1, optimize=False, load=True)

    buy_25_ma_offset = DecimalParameter(0.90, 0.99, default=0.922, space='buy', optimize=False, load=True)
    buy_25_rsi_4 = DecimalParameter(26.0, 40.0, default=38.0, space='buy', decimals=1, optimize=False, load=True)
    buy_25_cti = DecimalParameter(-0.99, -0.4, default=-0.76, space='buy', decimals=2, optimize=False, load=True)

    buy_26_zema_low_offset = DecimalParameter(0.90, 0.99, default=0.932, space='buy', optimize=False, load=True)
    buy_26_cti = DecimalParameter(-0.99, -0.4, default=-0.8, space='buy', decimals=2, optimize=False, load=True)
    buy_26_volume = DecimalParameter(0.6, 6.0, default=1.2, space='buy', decimals=1, optimize=False, load=True)

    buy_27_wr_max = DecimalParameter(95, 99, default=99.0, space='buy', decimals=1, optimize=False, load=True)
    buy_27_wr_1h_max = DecimalParameter(90, 99, default=97.6, space='buy', decimals=1, optimize=False, load=True)
    buy_27_rsi_max = DecimalParameter(40, 70, default=50, space='buy', decimals=0, optimize=False, load=True)
    buy_27_cti = DecimalParameter(-0.99, -0.4, default=-0.9, space='buy', decimals=2, optimize=False, load=True)
    buy_27_volume = DecimalParameter(0.6, 6.0, default=2.0, space='buy', decimals=1, optimize=False, load=True)

    buy_28_ma_offset = DecimalParameter(0.90, 0.99, default=0.96, space='buy', optimize=False, load=True)
    buy_28_ewo = DecimalParameter(2.0, 14.0, default=12.2, space='buy', decimals=1, optimize=False, load=True)
    buy_28_rsi = DecimalParameter(24.0, 44.0, default=40.0, space='buy', decimals=1, optimize=False, load=True)
    buy_28_cti = DecimalParameter(-0.99, -0.4, default=-0.84, space='buy', decimals=2, optimize=False, load=True)

    buy_29_ma_offset = DecimalParameter(0.90, 0.99, default=0.94, space='buy', optimize=False, load=True)
    buy_29_ewo = DecimalParameter(-14.0, -2.0, default=-4.0, space='buy', decimals=1, optimize=False, load=True)
    buy_29_cti = DecimalParameter(-0.99, -0.4, default=-0.95, space='buy', decimals=2, optimize=False, load=True)

    buy_30_ma_offset = DecimalParameter(0.90, 0.99, default=0.97, space='buy', optimize=False, load=True)
    buy_30_ewo = DecimalParameter(2.0, 14.0, default=7.8, space='buy', decimals=1, optimize=False, load=True)
    buy_30_rsi = DecimalParameter(24.0, 48.0, default=42.0, space='buy', decimals=1, optimize=False, load=True)
    buy_30_cti = DecimalParameter(-0.99, -0.4, default=-0.8, space='buy', decimals=2, optimize=False, load=True)

    buy_31_ma_offset = DecimalParameter(0.90, 0.99, default=0.94, space='buy', optimize=False, load=True)
    buy_31_ewo = DecimalParameter(-22.0, -8.0, default=-19.0, space='buy', decimals=1, optimize=False, load=True)
    buy_31_wr = DecimalParameter(-99.9, -95.0, default=-98.4, space='buy', decimals=1, optimize=False, load=True)

    buy_32_ma_offset = DecimalParameter(0.90, 0.99, default=0.946, space='buy', optimize=False, load=True)
    buy_32_dip = DecimalParameter(0.001, 0.02, default=0.005, space='buy', decimals=3, optimize=False, load=True)
    buy_32_rsi = DecimalParameter(24.0, 50.0, default=46.0, space='buy', decimals=1, optimize=False, load=True)
    buy_32_cti = DecimalParameter(-0.99, -0.4, default=-0.8, space='buy', decimals=2, optimize=False, load=True)

    buy_33_ma_offset = DecimalParameter(0.90, 0.99, default=0.974, space='buy', optimize=False, load=True)
    buy_33_rsi = DecimalParameter(24.0, 50.0, default=32.0, space='buy', decimals=1, optimize=False, load=True)
    buy_33_cti = DecimalParameter(-0.99, -0.4, default=-0.9, space='buy', decimals=2, optimize=False, load=True)
    buy_33_ewo = DecimalParameter(2.0, 14.0, default=9.0, space='buy', decimals=1, optimize=False, load=True)
    buy_33_volume = DecimalParameter(0.6, 6.0, default=2.0, space='buy', decimals=1, optimize=False, load=True)

    buy_34_ma_offset = DecimalParameter(0.90, 0.99, default=0.968, space='buy', optimize=False, load=True)
    buy_34_dip = DecimalParameter(0.001, 0.02, default=0.002, space='buy', decimals=3, optimize=False, load=True)
    buy_34_ewo = DecimalParameter(-24.0, -8.0, default=-20.0, space='buy', decimals=1, optimize=False, load=True)
    buy_34_cti = DecimalParameter(-0.99, -0.4, default=-0.88, space='buy', decimals=2, optimize=False, load=True)
    buy_34_volume = DecimalParameter(0.6, 6.0, default=1.1, space='buy', decimals=1, optimize=False, load=True)

    # Sell

    sell_condition_1_enable = CategoricalParameter([True, False], default=True, space='sell', optimize=False, load=True)
    sell_condition_2_enable = CategoricalParameter([True, False], default=True, space='sell', optimize=False, load=True)
    sell_condition_3_enable = CategoricalParameter([True, False], default=True, space='sell', optimize=False, load=True)
    sell_condition_4_enable = CategoricalParameter([True, False], default=True, space='sell', optimize=False, load=True)
    sell_condition_5_enable = CategoricalParameter([True, False], default=True, space='sell', optimize=False, load=True)
    sell_condition_6_enable = CategoricalParameter([True, False], default=True, space='sell', optimize=False, load=True)
    sell_condition_7_enable = CategoricalParameter([True, False], default=True, space='sell', optimize=False, load=True)
    sell_condition_8_enable = CategoricalParameter([True, False], default=True, space='sell', optimize=False, load=True)

    # 48h for pump sell checks
    sell_pump_threshold_48_1 = DecimalParameter(0.5, 1.2, default=0.9, space='sell', decimals=2, optimize=False, load=True)
    sell_pump_threshold_48_2 = DecimalParameter(0.4, 0.9, default=0.7, space='sell', decimals=2, optimize=False, load=True)
    sell_pump_threshold_48_3 = DecimalParameter(0.3, 0.7, default=0.5, space='sell', decimals=2, optimize=False, load=True)

    # 36h for pump sell checks
    sell_pump_threshold_36_1 = DecimalParameter(0.5, 0.9, default=0.72, space='sell', decimals=2, optimize=False, load=True)
    sell_pump_threshold_36_2 = DecimalParameter(3.0, 6.0, default=4.0, space='sell', decimals=2, optimize=False, load=True)
    sell_pump_threshold_36_3 = DecimalParameter(0.8, 1.6, default=1.0, space='sell', decimals=2, optimize=False, load=True)

    # 24h for pump sell checks
    sell_pump_threshold_24_1 = DecimalParameter(0.5, 0.9, default=0.68, space='sell', decimals=2, optimize=False, load=True)
    sell_pump_threshold_24_2 = DecimalParameter(0.3, 0.6, default=0.62, space='sell', decimals=2, optimize=False, load=True)
    sell_pump_threshold_24_3 = DecimalParameter(0.2, 0.5, default=0.88, space='sell', decimals=2, optimize=False, load=True)

    sell_rsi_bb_1 = DecimalParameter(60.0, 80.0, default=79.5, space='sell', decimals=1, optimize=False, load=True)

    sell_rsi_bb_2 = DecimalParameter(72.0, 90.0, default=81, space='sell', decimals=1, optimize=False, load=True)

    sell_rsi_main_3 = DecimalParameter(77.0, 90.0, default=82, space='sell', decimals=1, optimize=False, load=True)

    sell_dual_rsi_rsi_4 = DecimalParameter(72.0, 84.0, default=73.4, space='sell', decimals=1, optimize=False, load=True)
    sell_dual_rsi_rsi_1h_4 = DecimalParameter(78.0, 92.0, default=79.6, space='sell', decimals=1, optimize=False, load=True)

    sell_ema_relative_5 = DecimalParameter(0.005, 0.05, default=0.024, space='sell', optimize=False, load=True)
    sell_rsi_diff_5 = DecimalParameter(0.0, 20.0, default=4.4, space='sell', optimize=False, load=True)

    sell_rsi_under_6 = DecimalParameter(72.0, 90.0, default=79.0, space='sell', decimals=1, optimize=False, load=True)

    sell_rsi_1h_7 = DecimalParameter(80.0, 95.0, default=81.7, space='sell', decimals=1, optimize=False, load=True)

    sell_bb_relative_8 = DecimalParameter(1.05, 1.3, default=1.1, space='sell', decimals=3, optimize=False, load=True)

    # Profit over EMA200
    sell_custom_profit_0 = DecimalParameter(0.01, 0.1, default=0.012, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_0 = DecimalParameter(30.0, 40.0, default=34.0, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_profit_1 = DecimalParameter(0.01, 0.1, default=0.02, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_1 = DecimalParameter(30.0, 50.0, default=35.0, space='sell', decimals=2, optimize=False, load=True)
    sell_custom_profit_2 = DecimalParameter(0.01, 0.1, default=0.03, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_2 = DecimalParameter(30.0, 50.0, default=37.0, space='sell', decimals=2, optimize=False, load=True)
    sell_custom_profit_3 = DecimalParameter(0.01, 0.1, default=0.04, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_3 = DecimalParameter(30.0, 50.0, default=42.0, space='sell', decimals=2, optimize=False, load=True)
    sell_custom_profit_4 = DecimalParameter(0.01, 0.1, default=0.05, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_4 = DecimalParameter(35.0, 50.0, default=43.0, space='sell', decimals=2, optimize=False, load=True)
    sell_custom_profit_5 = DecimalParameter(0.01, 0.1, default=0.06, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_5 = DecimalParameter(35.0, 50.0, default=45.0, space='sell', decimals=2, optimize=False, load=True)
    sell_custom_profit_6 = DecimalParameter(0.01, 0.1, default=0.07, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_6 = DecimalParameter(38.0, 55.0, default=52.0, space='sell', decimals=2, optimize=False, load=True)
    sell_custom_profit_7 = DecimalParameter(0.01, 0.1, default=0.08, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_7 = DecimalParameter(40.0, 58.0, default=54.0, space='sell', decimals=2, optimize=False, load=True)
    sell_custom_profit_8 = DecimalParameter(0.06, 0.1, default=0.09, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_8 = DecimalParameter(40.0, 50.0, default=55.0, space='sell', decimals=2, optimize=False, load=True)
    sell_custom_profit_9 = DecimalParameter(0.05, 0.14, default=0.1, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_9 = DecimalParameter(40.0, 60.0, default=54.0, space='sell', decimals=2, optimize=False, load=True)
    sell_custom_profit_10 = DecimalParameter(0.1, 0.14, default=0.12, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_10 = DecimalParameter(38.0, 50.0, default=42.0, space='sell', decimals=2, optimize=False, load=True)
    sell_custom_profit_11 = DecimalParameter(0.16, 0.45, default=0.20, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_rsi_11 = DecimalParameter(28.0, 40.0, default=34.0, space='sell', decimals=2, optimize=False, load=True)

    # Profit under EMA200
    sell_custom_under_profit_0 = DecimalParameter(0.01, 0.4, default=0.01, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_0 = DecimalParameter(28.0, 40.0, default=38.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_under_profit_1 = DecimalParameter(0.01, 0.10, default=0.02, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_1 = DecimalParameter(36.0, 60.0, default=56.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_under_profit_2 = DecimalParameter(0.01, 0.10, default=0.03, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_2 = DecimalParameter(46.0, 66.0, default=57.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_under_profit_3 = DecimalParameter(0.01, 0.10, default=0.04, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_3 = DecimalParameter(50.0, 68.0, default=58.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_under_profit_4 = DecimalParameter(0.02, 0.1, default=0.05, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_4 = DecimalParameter(50.0, 68.0, default=59.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_under_profit_5 = DecimalParameter(0.02, 0.1, default=0.06, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_5 = DecimalParameter(46.0, 62.0, default=60.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_under_profit_6 = DecimalParameter(0.03, 0.1, default=0.07, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_6 = DecimalParameter(44.0, 60.0, default=56.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_under_profit_7 = DecimalParameter(0.04, 0.1, default=0.08, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_7 = DecimalParameter(46.0, 60.0, default=54.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_under_profit_8 = DecimalParameter(0.06, 0.12, default=0.09, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_8 = DecimalParameter(40.0, 58.0, default=55.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_under_profit_9 = DecimalParameter(0.08, 0.14, default=0.1, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_9 = DecimalParameter(40.0, 60.0, default=54.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_under_profit_10 = DecimalParameter(0.1, 0.16, default=0.12, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_10 = DecimalParameter(30.0, 50.0, default=42.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_under_profit_11 = DecimalParameter(0.16, 0.3, default=0.2, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_under_rsi_11 = DecimalParameter(24.0, 40.0, default=34.0, space='sell', decimals=1, optimize=False, load=True)

    # Profit targets for pumped pairs 48h 1
    sell_custom_pump_profit_1_1 = DecimalParameter(0.01, 0.03, default=0.01, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_1_1 = DecimalParameter(26.0, 40.0, default=34.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_1_2 = DecimalParameter(0.01, 0.6, default=0.02, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_1_2 = DecimalParameter(36.0, 50.0, default=40.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_1_3 = DecimalParameter(0.02, 0.10, default=0.04, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_1_3 = DecimalParameter(38.0, 50.0, default=42.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_1_4 = DecimalParameter(0.06, 0.12, default=0.1, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_1_4 = DecimalParameter(36.0, 48.0, default=42.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_1_5 = DecimalParameter(0.14, 0.24, default=0.2, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_1_5 = DecimalParameter(20.0, 40.0, default=34.0, space='sell', decimals=1, optimize=False, load=True)

    # Profit targets for pumped pairs 36h 1
    sell_custom_pump_profit_2_1 = DecimalParameter(0.01, 0.03, default=0.01, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_2_1 = DecimalParameter(26.0, 40.0, default=34.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_2_2 = DecimalParameter(0.01, 0.6, default=0.02, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_2_2 = DecimalParameter(36.0, 50.0, default=40.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_2_3 = DecimalParameter(0.02, 0.10, default=0.04, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_2_3 = DecimalParameter(38.0, 50.0, default=40.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_2_4 = DecimalParameter(0.06, 0.12, default=0.1, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_2_4 = DecimalParameter(36.0, 48.0, default=42.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_2_5 = DecimalParameter(0.14, 0.24, default=0.2, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_2_5 = DecimalParameter(20.0, 40.0, default=34.0, space='sell', decimals=1, optimize=False, load=True)

    # Profit targets for pumped pairs 24h 1
    sell_custom_pump_profit_3_1 = DecimalParameter(0.01, 0.03, default=0.01, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_3_1 = DecimalParameter(26.0, 40.0, default=34.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_3_2 = DecimalParameter(0.01, 0.6, default=0.02, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_3_2 = DecimalParameter(34.0, 50.0, default=40.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_3_3 = DecimalParameter(0.02, 0.10, default=0.04, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_3_3 = DecimalParameter(38.0, 50.0, default=40.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_3_4 = DecimalParameter(0.06, 0.12, default=0.1, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_3_4 = DecimalParameter(36.0, 48.0, default=42.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_profit_3_5 = DecimalParameter(0.14, 0.24, default=0.2, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_rsi_3_5 = DecimalParameter(20.0, 40.0, default=34.0, space='sell', decimals=1, optimize=False, load=True)

    # SMA descending
    sell_custom_dec_profit_min_1 = DecimalParameter(0.01, 0.10, default=0.05, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_dec_profit_max_1 = DecimalParameter(0.06, 0.16, default=0.12, space='sell', decimals=3, optimize=False, load=True)

    # Under EMA100
    sell_custom_dec_profit_min_2 = DecimalParameter(0.05, 0.12, default=0.07, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_dec_profit_max_2 = DecimalParameter(0.06, 0.2, default=0.16, space='sell', decimals=3, optimize=False, load=True)

    # Trail 1
    sell_trail_profit_min_1 = DecimalParameter(0.1, 0.2, default=0.03, space='sell', decimals=2, optimize=False, load=True)
    sell_trail_profit_max_1 = DecimalParameter(0.4, 0.7, default=0.05, space='sell', decimals=2, optimize=False, load=True)
    sell_trail_down_1 = DecimalParameter(0.01, 0.08, default=0.05, space='sell', decimals=3, optimize=False, load=True)
    sell_trail_rsi_min_1 = DecimalParameter(16.0, 36.0, default=10.0, space='sell', decimals=1, optimize=False, load=True)
    sell_trail_rsi_max_1 = DecimalParameter(30.0, 50.0, default=20.0, space='sell', decimals=1, optimize=False, load=True)

    # Trail 2
    sell_trail_profit_min_2 = DecimalParameter(0.08, 0.16, default=0.1, space='sell', decimals=3, optimize=False, load=True)
    sell_trail_profit_max_2 = DecimalParameter(0.3, 0.5, default=0.4, space='sell', decimals=2, optimize=False, load=True)
    sell_trail_down_2 = DecimalParameter(0.02, 0.08, default=0.03, space='sell', decimals=3, optimize=False, load=True)
    sell_trail_rsi_min_2 = DecimalParameter(16.0, 36.0, default=20.0, space='sell', decimals=1, optimize=False, load=True)
    sell_trail_rsi_max_2 = DecimalParameter(30.0, 50.0, default=50.0, space='sell', decimals=1, optimize=False, load=True)

    # Trail 3
    sell_trail_profit_min_3 = DecimalParameter(0.01, 0.12, default=0.06, space='sell', decimals=3, optimize=False, load=True)
    sell_trail_profit_max_3 = DecimalParameter(0.1, 0.3, default=0.2, space='sell', decimals=2, optimize=False, load=True)
    sell_trail_down_3 = DecimalParameter(0.01, 0.06, default=0.05, space='sell', decimals=3, optimize=False, load=True)

    # Trail 4
    sell_trail_profit_min_4 = DecimalParameter(0.01, 0.12, default=0.03, space='sell', decimals=3, optimize=False, load=True)
    sell_trail_profit_max_4 = DecimalParameter(0.02, 0.1, default=0.06, space='sell', decimals=2, optimize=False, load=True)
    sell_trail_down_4 = DecimalParameter(0.01, 0.06, default=0.02, space='sell', decimals=3, optimize=False, load=True)

    # Under & near EMA200, accept profit
    sell_custom_profit_under_profit_min_1 = DecimalParameter(0.0, 0.01, default=0.0, space='sell', optimize=False, load=True)
    sell_custom_profit_under_profit_max_1 = DecimalParameter(0.0, 0.05, default=0.02, space='sell', optimize=False, load=True)
    sell_custom_profit_under_rel_1 = DecimalParameter(0.01, 0.04, default=0.024, space='sell', optimize=False, load=True)
    sell_custom_profit_under_rsi_diff_1 = DecimalParameter(0.0, 20.0, default=4.4, space='sell', optimize=False, load=True)

    sell_custom_profit_under_profit_2 = DecimalParameter(0.0, 0.05, default=0.03, space='sell', optimize=False, load=True)
    sell_custom_profit_under_rel_2 = DecimalParameter(0.01, 0.04, default=0.024, space='sell', optimize=False, load=True)
    sell_custom_profit_under_rsi_diff_2 = DecimalParameter(0.0, 20.0, default=4.4, space='sell', optimize=False, load=True)

    # Under & near EMA200, take the loss
    sell_custom_stoploss_under_rel_1 = DecimalParameter(0.001, 0.02, default=0.002, space='sell', optimize=False, load=True)
    sell_custom_stoploss_under_rsi_diff_1 = DecimalParameter(0.0, 20.0, default=10.0, space='sell', optimize=False, load=True)

    # Long duration/recover stoploss 1
    sell_custom_stoploss_long_profit_min_1 = DecimalParameter(-0.1, -0.02, default=-0.08, space='sell', optimize=False, load=True)
    sell_custom_stoploss_long_profit_max_1 = DecimalParameter(-0.06, -0.01, default=-0.04, space='sell', optimize=False, load=True)
    sell_custom_stoploss_long_recover_1 = DecimalParameter(0.05, 0.15, default=0.14, space='sell', optimize=False, load=True)
    sell_custom_stoploss_long_rsi_diff_1 = DecimalParameter(0.0, 20.0, default=4.0, space='sell', optimize=False, load=True)

    # Long duration/recover stoploss 2
    sell_custom_stoploss_long_recover_2 = DecimalParameter(0.03, 0.15, default=0.06, space='sell', optimize=False, load=True)
    sell_custom_stoploss_long_rsi_diff_2 = DecimalParameter(30.0, 50.0, default=40.0, space='sell', optimize=False, load=True)

    # Pumped, descending SMA
    sell_custom_pump_dec_profit_min_1 = DecimalParameter(0.001, 0.04, default=0.005, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_dec_profit_max_1 = DecimalParameter(0.03, 0.08, default=0.05, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_dec_profit_min_2 = DecimalParameter(0.01, 0.08, default=0.04, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_dec_profit_max_2 = DecimalParameter(0.04, 0.1, default=0.06, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_dec_profit_min_3 = DecimalParameter(0.02, 0.1, default=0.06, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_dec_profit_max_3 = DecimalParameter(0.06, 0.12, default=0.09, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_dec_profit_min_4 = DecimalParameter(0.01, 0.05, default=0.02, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_dec_profit_max_4 = DecimalParameter(0.02, 0.1, default=0.04, space='sell', decimals=3, optimize=False, load=True)

    # Pumped 48h 1, under EMA200
    sell_custom_pump_under_profit_min_1 = DecimalParameter(0.02, 0.06, default=0.04, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_under_profit_max_1 = DecimalParameter(0.04, 0.1, default=0.09, space='sell', decimals=3, optimize=False, load=True)

    # Pumped trail 1
    sell_custom_pump_trail_profit_min_1 = DecimalParameter(0.01, 0.12, default=0.05, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_trail_profit_max_1 = DecimalParameter(0.06, 0.16, default=0.07, space='sell', decimals=2, optimize=False, load=True)
    sell_custom_pump_trail_down_1 = DecimalParameter(0.01, 0.06, default=0.05, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_pump_trail_rsi_min_1 = DecimalParameter(16.0, 36.0, default=20.0, space='sell', decimals=1, optimize=False, load=True)
    sell_custom_pump_trail_rsi_max_1 = DecimalParameter(30.0, 50.0, default=70.0, space='sell', decimals=1, optimize=False, load=True)

    # Stoploss, pumped, 48h 1
    sell_custom_stoploss_pump_max_profit_1 = DecimalParameter(0.01, 0.04, default=0.01, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_stoploss_pump_min_1 = DecimalParameter(-0.1, -0.01, default=-0.02, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_stoploss_pump_max_1 = DecimalParameter(-0.1, -0.01, default=-0.01, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_stoploss_pump_ma_offset_1 = DecimalParameter(0.7, 0.99, default=0.94, space='sell', decimals=2, optimize=False, load=True)

    # Stoploss, pumped, 48h 1
    sell_custom_stoploss_pump_max_profit_2 = DecimalParameter(0.01, 0.04, default=0.025, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_stoploss_pump_loss_2 = DecimalParameter(-0.1, -0.01, default=-0.05, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_stoploss_pump_ma_offset_2 = DecimalParameter(0.7, 0.99, default=0.92, space='sell', decimals=2, optimize=False, load=True)

    # Stoploss, pumped, 36h 3
    sell_custom_stoploss_pump_max_profit_3 = DecimalParameter(0.01, 0.04, default=0.008, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_stoploss_pump_loss_3 = DecimalParameter(-0.16, -0.06, default=-0.12, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_stoploss_pump_ma_offset_3 = DecimalParameter(0.7, 0.99, default=0.88, space='sell', decimals=2, optimize=False, load=True)

    # Recover
    sell_custom_recover_profit_1 = DecimalParameter(0.01, 0.06, default=0.06, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_recover_min_loss_1 = DecimalParameter(0.06, 0.16, default=0.12, space='sell', decimals=3, optimize=False, load=True)

    sell_custom_recover_profit_min_2 = DecimalParameter(0.01, 0.04, default=0.01, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_recover_profit_max_2 = DecimalParameter(0.02, 0.08, default=0.05, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_recover_min_loss_2 = DecimalParameter(0.04, 0.16, default=0.06, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_recover_rsi_2 = DecimalParameter(32.0, 52.0, default=46.0, space='sell', decimals=1, optimize=False, load=True)

    # Profit for long duration trades
    sell_custom_long_profit_min_1 = DecimalParameter(0.01, 0.04, default=0.03, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_long_profit_max_1 = DecimalParameter(0.02, 0.08, default=0.04, space='sell', decimals=3, optimize=False, load=True)
    sell_custom_long_duration_min_1 = IntParameter(700, 2000, default=900, space='sell', optimize=False, load=True)

    #############################################################

    hold_trade_ids = None

    @staticmethod
    def get_hold_trades_config_file():
        strat_file_path = pathlib.Path(__file__)
        hold_trades_config_file_resolve = strat_file_path.resolve().parent / "hold-trades.json"
        if hold_trades_config_file_resolve.is_file():
            return hold_trades_config_file_resolve

        # The resolved path does not exist, is it a symlink?
        hold_trades_config_file_absolute = strat_file_path.absolute().parent / "hold-trades.json"
        if hold_trades_config_file_absolute.is_file():
            return hold_trades_config_file_absolute

        if hold_trades_config_file_resolve != hold_trades_config_file_absolute:
            looked_in = f"'{hold_trades_config_file_resolve}' and '{hold_trades_config_file_absolute}'"
        else:
            looked_in = f"'{hold_trades_config_file_resolve}'"
        log.warning(
            "The 'hold-trades.json' file was not found. Looked in %s. HOLD support disabled.",
            looked_in
        )

    def load_hold_trades_config(self):
        if self.hold_trade_ids is not None:
            # Already loaded
            return

        # Default Values
        self.hold_trade_ids = {}

        # Update values from config file, if it exists
        hold_trades_config_file = NostalgiaForInfinityNext.get_hold_trades_config_file()
        if not hold_trades_config_file:
            return

        with hold_trades_config_file.open('r') as f:
            trade_ids = None
            hold_trades_config = None
            try:
                hold_trades_config = json_load(f)
            except rapidjson.JSONDecodeError as exc:
                log.error("Failed to load JSON from %s: %s", hold_trades_config_file, exc)
            else:
                trade_ids = hold_trades_config.get("trade_ids")

            if not trade_ids:
                return

            open_trades = {
                trade.id: trade for trade in Trade.get_trades_proxy(is_open=True)
            }

            if isinstance(trade_ids, dict):
                # New syntax
                for trade_id, profit_ratio in trade_ids.items():
                    try:
                        trade_id = int(trade_id)
                    except ValueError:
                        log.error(
                            "The trade_id(%s) defined under 'trade_ids' in %s is not an integer",
                            trade_id, hold_trades_config_file
                        )
                        continue
                    if not isinstance(profit_ratio, float):
                        log.error(
                            "The 'profit_ratio' config value(%s) for trade_id %s in %s is not a float",
                            profit_ratio,
                            trade_id,
                            hold_trades_config_file
                        )
                    if trade_id in open_trades:
                        formatted_profit_ratio = "{}%".format(profit_ratio * 100)
                        log.warning(
                            "The trade %s is configured to HOLD until the profit ratio of %s is met",
                            open_trades[trade_id],
                            formatted_profit_ratio
                        )
                        self.hold_trade_ids[trade_id] = profit_ratio
                    else:
                        log.warning(
                            "The trade_id(%s) is no longer open. Please remove it from 'trade_ids' in %s",
                            trade_id,
                            hold_trades_config_file
                        )
            else:
                # Initial Syntax
                profit_ratio = hold_trades_config.get("profit_ratio")
                if profit_ratio:
                    if not isinstance(profit_ratio, float):
                        log.error(
                            "The 'profit_ratio' config value(%s) in %s is not a float",
                            profit_ratio,
                            hold_trades_config_file
                        )
                else:
                    profit_ratio = 0.005
                formatted_profit_ratio = "{}%".format(profit_ratio * 100)
                for trade_id in trade_ids:
                    if not isinstance(trade_id, int):
                        log.error(
                            "The trade_id(%s) defined under 'trade_ids' in %s is not an integer",
                            trade_id, hold_trades_config_file
                        )
                        continue
                    if trade_id in open_trades:
                        log.warning(
                            "The trade %s is configured to HOLD until the profit ratio of %s is met",
                            open_trades[trade_id],
                            formatted_profit_ratio
                        )
                        self.hold_trade_ids[trade_id] = profit_ratio
                    else:
                        log.warning(
                            "The trade_id(%s) is no longer open. Please remove it from 'trade_ids' in %s",
                            trade_id,
                            hold_trades_config_file
                        )

    def bot_loop_start(self, **kwargs) -> None:
        """
        Called at the start of the bot iteration (one loop).
        Might be used to perform pair-independent tasks
        (e.g. gather some remote resource for comparison)
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """
        if self.config['runmode'].value in ('live', 'dry_run'):
            self.load_hold_trades_config()
        return super().bot_loop_start(**kwargs)

    def get_ticker_indicator(self):
        return int(self.timeframe[:-1])

    def sell_over_main(self, current_profit: float, last_candle) -> tuple:
        if last_candle['close'] > last_candle['ema_200']:
            if current_profit > self.sell_custom_profit_11.value:
                if last_candle['rsi'] < self.sell_custom_rsi_11.value:
                    return True, 'signal_profit_11'
            elif self.sell_custom_profit_11.value > current_profit > self.sell_custom_profit_10.value:
                if last_candle['rsi'] < self.sell_custom_rsi_10.value:
                    return True, 'signal_profit_10'
            elif self.sell_custom_profit_10.value > current_profit > self.sell_custom_profit_9.value:
                if last_candle['rsi'] < self.sell_custom_rsi_9.value:
                    return True, 'signal_profit_9'
            elif self.sell_custom_profit_9.value > current_profit > self.sell_custom_profit_8.value:
                if last_candle['rsi'] < self.sell_custom_rsi_8.value:
                    return True, 'signal_profit_8'
            elif self.sell_custom_profit_8.value > current_profit > self.sell_custom_profit_7.value:
                if (last_candle['rsi'] < self.sell_custom_rsi_7.value) & (last_candle['cmf'] < 0.0) :
                    return True, 'signal_profit_7'
            elif self.sell_custom_profit_7.value > current_profit > self.sell_custom_profit_6.value:
                if (last_candle['rsi'] < self.sell_custom_rsi_6.value) & (last_candle['cmf'] < 0.0):
                    return True, 'signal_profit_6'
            elif self.sell_custom_profit_6.value > current_profit > self.sell_custom_profit_5.value:
                if (last_candle['rsi'] < self.sell_custom_rsi_5.value) & (last_candle['cmf'] < 0.0):
                    return True, 'signal_profit_5'
            elif self.sell_custom_profit_5.value > current_profit > self.sell_custom_profit_4.value:
                if (last_candle['rsi'] < self.sell_custom_rsi_4.value) & (last_candle['cmf'] < 0.0) :
                    return True, 'signal_profit_4'
            elif self.sell_custom_profit_4.value > current_profit > self.sell_custom_profit_3.value:
                if (last_candle['rsi'] < self.sell_custom_rsi_3.value) & (last_candle['cmf'] < 0.0):
                    return True, 'signal_profit_3'
            elif self.sell_custom_profit_3.value > current_profit > self.sell_custom_profit_2.value:
                if (last_candle['rsi'] < self.sell_custom_rsi_2.value) & (last_candle['cmf'] < 0.0):
                    return True, 'signal_profit_2'
            elif self.sell_custom_profit_2.value > current_profit > self.sell_custom_profit_1.value:
                if (last_candle['rsi'] < self.sell_custom_rsi_1.value) & (last_candle['cmf'] < 0.0):
                    return True, 'signal_profit_1'
            elif self.sell_custom_profit_1.value > current_profit > self.sell_custom_profit_0.value:
                if (last_candle['rsi'] < self.sell_custom_rsi_0.value) & (last_candle['cmf'] < 0.0):
                    return True, 'signal_profit_0'
        return False, None

    def sell_under_main(self, current_profit: float, last_candle) -> tuple:
        if last_candle['close'] < last_candle['ema_200']:
            if current_profit > self.sell_custom_under_profit_11.value:
                if last_candle['rsi'] < self.sell_custom_under_rsi_11.value:
                    return True, 'signal_profit_u_11'
            elif self.sell_custom_under_profit_11.value > current_profit > self.sell_custom_under_profit_10.value:
                if last_candle['rsi'] < self.sell_custom_under_rsi_10.value:
                    return True, 'signal_profit_u_10'
            elif self.sell_custom_under_profit_10.value > current_profit > self.sell_custom_under_profit_9.value:
                if last_candle['rsi'] < self.sell_custom_under_rsi_9.value:
                    return True, 'signal_profit_u_9'
            elif self.sell_custom_under_profit_9.value > current_profit > self.sell_custom_under_profit_8.value:
                if last_candle['rsi'] < self.sell_custom_under_rsi_8.value:
                    return True, 'signal_profit_u_8'
            elif self.sell_custom_under_profit_8.value > current_profit > self.sell_custom_under_profit_7.value:
                if last_candle['rsi'] < self.sell_custom_under_rsi_7.value:
                    return True, 'signal_profit_u_7'
            elif self.sell_custom_under_profit_7.value > current_profit > self.sell_custom_under_profit_6.value:
                if last_candle['rsi'] < self.sell_custom_under_rsi_6.value:
                    return True, 'signal_profit_u_6'
            elif self.sell_custom_under_profit_6.value > current_profit > self.sell_custom_under_profit_5.value:
                if last_candle['rsi'] < self.sell_custom_under_rsi_5.value:
                    return True, 'signal_profit_u_5'
            elif self.sell_custom_under_profit_5.value > current_profit > self.sell_custom_under_profit_4.value:
                if last_candle['rsi'] < self.sell_custom_under_rsi_4.value:
                    return True, 'signal_profit_u_4'
            elif self.sell_custom_under_profit_4.value > current_profit > self.sell_custom_under_profit_3.value:
                if last_candle['rsi'] < self.sell_custom_under_rsi_3.value:
                    return True, 'signal_profit_u_3'
            elif self.sell_custom_under_profit_3.value > current_profit > self.sell_custom_under_profit_2.value:
                if last_candle['rsi'] < self.sell_custom_under_rsi_2.value:
                    return True, 'signal_profit_u_2'
            elif self.sell_custom_under_profit_2.value > current_profit > self.sell_custom_under_profit_1.value:
                if last_candle['rsi'] < self.sell_custom_under_rsi_1.value:
                    return True, 'signal_profit_u_1'
            elif self.sell_custom_under_profit_1.value > current_profit > self.sell_custom_under_profit_0.value:
                if (last_candle['rsi'] < self.sell_custom_under_rsi_0.value) & (last_candle['cmf'] < 0.0):
                    return True, 'signal_profit_u_0'

        return False, None

    def sell_pump_main(self, current_profit: float, last_candle) -> tuple:
        if last_candle['sell_pump_48_1_1h']:
            if current_profit > self.sell_custom_pump_profit_1_5.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_1_5.value:
                    return True, 'signal_profit_p_1_5'
            elif self.sell_custom_pump_profit_1_5.value > current_profit > self.sell_custom_pump_profit_1_4.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_1_4.value:
                    return True, 'signal_profit_p_1_4'
            elif self.sell_custom_pump_profit_1_4.value > current_profit > self.sell_custom_pump_profit_1_3.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_1_3.value:
                    return True, 'signal_profit_p_1_3'
            elif self.sell_custom_pump_profit_1_3.value > current_profit > self.sell_custom_pump_profit_1_2.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_1_2.value:
                    return True, 'signal_profit_p_1_2'
            elif self.sell_custom_pump_profit_1_2.value > current_profit > self.sell_custom_pump_profit_1_1.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_1_1.value:
                    return True, 'signal_profit_p_1_1'

        elif last_candle['sell_pump_36_1_1h']:
            if current_profit > self.sell_custom_pump_profit_2_5.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_2_5.value:
                    return True, 'signal_profit_p_2_5'
            elif self.sell_custom_pump_profit_2_5.value > current_profit > self.sell_custom_pump_profit_2_4.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_2_4.value:
                    return True, 'signal_profit_p_2_4'
            elif self.sell_custom_pump_profit_2_4.value > current_profit > self.sell_custom_pump_profit_2_3.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_2_3.value:
                    return True, 'signal_profit_p_2_3'
            elif self.sell_custom_pump_profit_2_3.value > current_profit > self.sell_custom_pump_profit_2_2.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_2_2.value:
                    return True, 'signal_profit_p_2_2'
            elif self.sell_custom_pump_profit_2_2.value > current_profit > self.sell_custom_pump_profit_2_1.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_2_1.value:
                    return True, 'signal_profit_p_2_1'

        elif last_candle['sell_pump_24_1_1h']:
            if current_profit > self.sell_custom_pump_profit_3_5.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_3_5.value:
                    return True, 'signal_profit_p_3_5'
            elif self.sell_custom_pump_profit_3_5.value > current_profit > self.sell_custom_pump_profit_3_4.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_3_4.value:
                    return True, 'signal_profit_p_3_4'
            elif self.sell_custom_pump_profit_3_4.value > current_profit > self.sell_custom_pump_profit_3_3.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_3_3.value:
                    return True, 'signal_profit_p_3_3'
            elif self.sell_custom_pump_profit_3_3.value > current_profit > self.sell_custom_pump_profit_3_2.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_3_2.value:
                    return True, 'signal_profit_p_3_2'
            elif self.sell_custom_pump_profit_3_2.value > current_profit > self.sell_custom_pump_profit_3_1.value:
                if last_candle['rsi'] < self.sell_custom_pump_rsi_3_1.value:
                    return True, 'signal_profit_p_3_1'

        return False, None

    def sell_dec_main(self, current_profit: float, last_candle) -> tuple:
        if (self.sell_custom_dec_profit_max_1.value > current_profit > self.sell_custom_dec_profit_min_1.value) & (last_candle['sma_200_dec_20']):
            return True, 'signal_profit_d_1'
        elif (self.sell_custom_dec_profit_max_2.value > current_profit > self.sell_custom_dec_profit_min_2.value) & (last_candle['close'] < last_candle['ema_100']):
            return True, 'signal_profit_d_2'

        return False, None

    def sell_trail_main(self, current_profit: float, last_candle, max_profit: float) -> tuple:
        if (self.sell_trail_profit_max_1.value > current_profit > self.sell_trail_profit_min_1.value) & (self.sell_trail_rsi_min_1.value < last_candle['rsi'] < self.sell_trail_rsi_max_1.value) & (max_profit > (current_profit + self.sell_trail_down_1.value)) & (last_candle['moderi_96'] == False):
            return True, 'signal_profit_t_1'
        elif (self.sell_trail_profit_max_2.value > current_profit > self.sell_trail_profit_min_2.value) & (self.sell_trail_rsi_min_2.value < last_candle['rsi'] < self.sell_trail_rsi_max_2.value) & (max_profit > (current_profit + self.sell_trail_down_2.value)) & (last_candle['ema_25'] < last_candle['ema_50']):
            return True, 'signal_profit_t_2'
        elif (self.sell_trail_profit_max_3.value > current_profit > self.sell_trail_profit_min_3.value) & (max_profit > (current_profit + self.sell_trail_down_3.value)) & (last_candle['sma_200_dec_20_1h']):
            return True, 'signal_profit_t_3'
        elif (self.sell_trail_profit_max_4.value > current_profit > self.sell_trail_profit_min_4.value) & (max_profit > (current_profit + self.sell_trail_down_4.value)) & (last_candle['sma_200_dec_24']) & (last_candle['cmf'] < 0.0):
            return True, 'signal_profit_t_4'

        return False, None

    def sell_duration_main(self, current_profit: float, last_candle, trade: 'Trade', current_time: 'datetime') -> tuple:
        # Pumped pair, short duration
        if (last_candle['sell_pump_24_1_1h']) & (0.2 > current_profit > 0.07) & (current_time - timedelta(minutes=30) < trade.open_date_utc):
            return True, 'signal_profit_p_s_1'

        elif (self.sell_custom_long_profit_min_1.value < current_profit < self.sell_custom_long_profit_max_1.value) & (current_time - timedelta(minutes=self.sell_custom_long_duration_min_1.value) > trade.open_date_utc):
            return True, 'signal_profit_l_1'

        return False, None

    def sell_under_min(self, current_profit: float, last_candle) -> tuple:
        if ((last_candle['moderi_96']) == False):
            # Downtrend
            if (self.sell_custom_profit_under_profit_max_1.value > current_profit > self.sell_custom_profit_under_profit_min_1.value) & (last_candle['close'] < last_candle['ema_200']) & (((last_candle['ema_200'] - last_candle['close']) / last_candle['close']) < self.sell_custom_profit_under_rel_1.value) & (last_candle['rsi'] > last_candle['rsi_1h'] + self.sell_custom_profit_under_rsi_diff_1.value):
                return True, 'signal_profit_u_e_1'
        else:
            # Uptrend
            if (current_profit > self.sell_custom_profit_under_profit_2.value) & (last_candle['close'] < last_candle['ema_200']) & (((last_candle['ema_200'] - last_candle['close']) / last_candle['close']) < self.sell_custom_profit_under_rel_2.value) & (last_candle['rsi'] > last_candle['rsi_1h'] + self.sell_custom_profit_under_rsi_diff_2.value):
                return True, 'signal_profit_u_e_2'

        return False, None

    def sell_stoploss(self, current_profit: float, last_candle, trade: 'Trade', current_time: 'datetime', max_loss: float, max_profit: float) -> tuple:
        if (current_profit < -0.0) & (last_candle['close'] < last_candle['ema_200']) & (((last_candle['ema_200'] - last_candle['close']) / last_candle['close']) < self.sell_custom_stoploss_under_rel_1.value) & (last_candle['rsi'] > last_candle['rsi_1h'] + self.sell_custom_stoploss_under_rsi_diff_1.value) & (last_candle['cmf'] < -0.2) & (last_candle['sma_200_dec_24']) & (current_time - timedelta(minutes=720) > trade.open_date_utc):
            return True, 'signal_stoploss_u_1'

        # Under EMA200, pair & BTC negative, low max rate
        elif (-0.1 > current_profit > -0.14) & (last_candle['btc_not_downtrend_1h'] == False) & (last_candle['moderi_32'] == False) & (last_candle['moderi_64'] == False) & (max_profit < 0.005) & (max_loss < 0.14) & (last_candle['sma_200_dec_24']) & (last_candle['cmf'] < -0.0) & (last_candle['close'] < last_candle['ema_200']) & (last_candle['ema_25'] < last_candle['ema_50']) & (last_candle['cti'] < -0.8) & (last_candle['r_480'] < -50.0):
            return True, 'signal_stoploss_u_b_1'

        # Under EMA200, pair & BTC negative, CTI, Elder Ray Index negative, normal max rate
        elif (-0.1 > current_profit > -0.2) & (last_candle['btc_not_downtrend_1h'] == False) & (last_candle['moderi_32'] == False) & (last_candle['moderi_64'] == False) & (last_candle['moderi_96'] == False) & (max_profit < 0.05) & (max_loss < 0.2) & (last_candle['sma_200_dec_24'])& (last_candle['sma_200_dec_20_1h']) & (last_candle['cmf'] < -0.45) & (last_candle['close'] < last_candle['ema_200']) & (last_candle['ema_25'] < last_candle['ema_50']) & (last_candle['cti'] < -0.8) & (last_candle['r_480'] < -97.0):
            return True, 'signal_stoploss_u_b_2'

        elif (self.sell_custom_stoploss_long_profit_min_1.value < current_profit < self.sell_custom_stoploss_long_profit_max_1.value) & (current_profit > (-max_loss + self.sell_custom_stoploss_long_recover_1.value)) & (last_candle['cmf'] < 0.0) & (last_candle['close'] < last_candle['ema_200'])  & (last_candle['rsi'] > last_candle['rsi_1h'] + self.sell_custom_stoploss_long_rsi_diff_1.value) & (last_candle['sma_200_dec_24']) & (current_time - timedelta(minutes=1200) > trade.open_date_utc):
            return True, 'signal_stoploss_l_r_u_1'

        elif (current_profit < -0.0) & (current_profit > (-max_loss + self.sell_custom_stoploss_long_recover_2.value)) & (last_candle['close'] < last_candle['ema_200']) & (last_candle['cmf'] < 0.0) & (last_candle['rsi'] > last_candle['rsi_1h'] + self.sell_custom_stoploss_long_rsi_diff_2.value) & (last_candle['sma_200_dec_24']) & (current_time - timedelta(minutes=1200) > trade.open_date_utc):
            return True, 'signal_stoploss_l_r_u_2'

        elif (max_profit < self.sell_custom_stoploss_pump_max_profit_2.value) & (current_profit < self.sell_custom_stoploss_pump_loss_2.value) & (last_candle['sell_pump_48_1_1h']) & (last_candle['cmf'] < 0.0) & (last_candle['sma_200_dec_20_1h']) & (last_candle['close'] < (last_candle['ema_200'] * self.sell_custom_stoploss_pump_ma_offset_2.value)):
            return True, 'signal_stoploss_p_2'

        elif (max_profit < self.sell_custom_stoploss_pump_max_profit_3.value) & (current_profit < self.sell_custom_stoploss_pump_loss_3.value) & (last_candle['sell_pump_36_3_1h']) & (last_candle['close'] < (last_candle['ema_200'] * self.sell_custom_stoploss_pump_ma_offset_3.value)):
            return True, 'signal_stoploss_p_3'

        return False, None

    def sell_pump_dec(self, current_profit: float, last_candle) -> tuple:
        if (self.sell_custom_pump_dec_profit_max_1.value > current_profit > self.sell_custom_pump_dec_profit_min_1.value) & (last_candle['sell_pump_48_1_1h']) & (last_candle['sma_200_dec_20']) & (last_candle['close'] < last_candle['ema_200']):
            return True, 'signal_profit_p_d_1'
        elif (self.sell_custom_pump_dec_profit_max_2.value > current_profit > self.sell_custom_pump_dec_profit_min_2.value) & (last_candle['sell_pump_48_2_1h']) & (last_candle['sma_200_dec_20']) & (last_candle['close'] < last_candle['ema_200']):
            return True, 'signal_profit_p_d_2'
        elif (self.sell_custom_pump_dec_profit_max_3.value > current_profit > self.sell_custom_pump_dec_profit_min_3.value) & (last_candle['sell_pump_48_3_1h']) & (last_candle['sma_200_dec_20']) & (last_candle['close'] < last_candle['ema_200']):
            return True, 'signal_profit_p_d_3'
        elif (self.sell_custom_pump_dec_profit_max_4.value > current_profit > self.sell_custom_pump_dec_profit_min_4.value) & (last_candle['sma_200_dec_20']) & (last_candle['sell_pump_24_2_1h']):
            return True, 'signal_profit_p_d_4'

        return False, None

    def sell_pump_extra(self, current_profit: float, last_candle, max_profit: float) -> tuple:
        # Pumped 48h 1, under EMA200
        if (self.sell_custom_pump_under_profit_max_1.value > current_profit > self.sell_custom_pump_under_profit_min_1.value) & (last_candle['sell_pump_48_1_1h']) & (last_candle['close'] < last_candle['ema_200']):
            return True, 'signal_profit_p_u_1'

            # Pumped 36h 2, trail 1
        elif (last_candle['sell_pump_36_2_1h']) & (self.sell_custom_pump_trail_profit_max_1.value > current_profit > self.sell_custom_pump_trail_profit_min_1.value) & (self.sell_custom_pump_trail_rsi_min_1.value < last_candle['rsi'] < self.sell_custom_pump_trail_rsi_max_1.value) & (max_profit > (current_profit + self.sell_custom_pump_trail_down_1.value)):
            return True, 'signal_profit_p_t_1'

        return False, None

    def sell_recover(self, current_profit: float, last_candle, max_loss: float) -> tuple:
        if (max_loss > self.sell_custom_recover_min_loss_1.value) & (current_profit > self.sell_custom_recover_profit_1.value):
            return True, 'signal_profit_r_1'

        elif (max_loss > self.sell_custom_recover_min_loss_2.value) & (self.sell_custom_recover_profit_max_2.value > current_profit > self.sell_custom_recover_profit_min_2.value) & (last_candle['rsi'] < self.sell_custom_recover_rsi_2.value) & (last_candle['ema_25'] < last_candle['ema_50']):
            return True, 'signal_profit_r_2'

        return False, None

    def sell_r_1(self, current_profit: float, last_candle) -> tuple:
        if 0.02 > current_profit > 0.012:
            if last_candle['r_480'] > -1.0:
                return True, 'signal_profit_w_1_1'
        elif 0.03 > current_profit > 0.02:
            if last_candle['r_480'] > -1.2:
                return True, 'signal_profit_w_1_2'
        elif 0.04 > current_profit > 0.03:
            if last_candle['r_480'] > -1.4:
                return True, 'signal_profit_w_1_3'
        elif 0.05 > current_profit > 0.04:
            if last_candle['r_480'] > -1.6:
                return True, 'signal_profit_w_1_4'
        elif 0.06 > current_profit > 0.05:
            if last_candle['r_480'] > -1.8:
                return True, 'signal_profit_w_1_5'
        elif 0.07 > current_profit > 0.06:
            if last_candle['r_480'] > -2.0:
                return True, 'signal_profit_w_1_6'
        elif 0.08 > current_profit > 0.07:
            if last_candle['r_480'] > -2.2:
                return True, 'signal_profit_w_1_7'
        elif 0.09 > current_profit > 0.08:
            if last_candle['r_480'] > -2.4:
                return True, 'signal_profit_w_1_8'
        elif 0.1 > current_profit > 0.09:
            if last_candle['r_480'] > -2.6:
                return True, 'signal_profit_w_1_9'
        elif 0.12 > current_profit > 0.1:
            if (last_candle['r_480'] > -8.0) & (last_candle['rsi'] > 72.0):
                return True, 'signal_profit_w_1_10'
        elif 0.2 > current_profit > 0.12:
            if (last_candle['r_480'] > -1.5) & (last_candle['rsi'] > 78.0):
                return True, 'signal_profit_w_1_11'
        elif current_profit > 0.2:
            if (last_candle['r_480'] > -1.0) & (last_candle['rsi'] > 80.0):
                return True, 'signal_profit_w_1_12'

        return False, None

    def sell_r_2(self, current_profit: float, last_candle) -> tuple:
        if 0.02 > current_profit > 0.012:
            if (last_candle['r_480'] > -2.0) & (last_candle['rsi'] > 79.0) & (last_candle['stochrsi_fastk_96'] > 99.0) & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_1'
        elif 0.03 > current_profit > 0.02:
            if (last_candle['r_480'] > -2.1) & (last_candle['rsi'] > 79.0) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_2'
        elif 0.04 > current_profit > 0.03:
            if (last_candle['r_480'] > -2.2) & (last_candle['rsi'] > 79.0) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_3'
        elif 0.05 > current_profit > 0.04:
            if (last_candle['r_480'] > -2.3) & (last_candle['rsi'] > 79.0) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_4'
        elif 0.06 > current_profit > 0.05:
            if (last_candle['r_480'] > -2.4) & (last_candle['rsi'] > 79.0) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_5'
        elif 0.07 > current_profit > 0.06:
            if (last_candle['r_480'] > -2.5) & (last_candle['rsi'] > 79.0) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_6'
        elif 0.08 > current_profit > 0.07:
            if (last_candle['r_480'] > -34.0) & (last_candle['rsi'] > 80.0) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_7'
        elif 0.09 > current_profit > 0.08:
            if (last_candle['r_480'] > -3.0) & (last_candle['rsi'] > 80.5) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_8'
        elif 0.1 > current_profit > 0.09:
            if (last_candle['r_480'] > -2.8) & (last_candle['rsi'] > 80.5) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_9'
        elif 0.12 > current_profit > 0.1:
            if (last_candle['r_480'] > -2.4) & (last_candle['rsi'] > 80.5) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_10'
        elif 0.2 > current_profit > 0.12:
            if (last_candle['r_480'] > -2.2) & (last_candle['rsi'] > 81.0) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_11'
        elif current_profit > 0.2:
            if (last_candle['r_480'] > -2.0) & (last_candle['rsi'] > 81.5) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_12'

        return False, None

    def sell_r_3(self, current_profit: float, last_candle) -> tuple:
        if 0.02 > current_profit > 0.012:
            if (last_candle['r_480'] > -6.0) & (last_candle['rsi'] > 74.0) & (last_candle['stochrsi_fastk_96'] > 99.0) & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_3_1'
        elif 0.03 > current_profit > 0.02:
            if (last_candle['r_480'] > -8.0) & (last_candle['rsi'] > 74.0) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_3_2'
        elif 0.04 > current_profit > 0.03:
            if (last_candle['r_480'] > -29.0) & (last_candle['rsi'] > 74.0) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_3_3'
        elif 0.05 > current_profit > 0.04:
            if (last_candle['r_480'] > -30.0) & (last_candle['rsi'] > 79.0) & (last_candle['stochrsi_fastk_96'] > 99.0)  & (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_3_4'

        return False, None

    def sell_r_4(self, current_profit: float, last_candle) -> tuple:
        if (0.02 > current_profit > 0.012):
            if (last_candle['r_480'] > -3.0) & (last_candle['rsi'] > 68.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_1'
        elif (0.03 > current_profit > 0.02):
            if (last_candle['r_480'] > -3.5) & (last_candle['rsi'] > 68.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_2'
        elif (0.04 > current_profit > 0.03):
            if (last_candle['r_480'] > -4.0) & (last_candle['rsi'] > 68.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_3'
        elif (0.05 > current_profit > 0.04):
            if (last_candle['r_480'] > -4.5) & (last_candle['rsi'] > 68.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_4'
        elif (0.06 > current_profit > 0.05):
            if (last_candle['r_480'] > -24.0) & (last_candle['rsi'] > 68.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_5'
        elif (0.07 > current_profit > 0.06):
            if (last_candle['r_480'] > -26.0) & (last_candle['rsi'] > 79.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_6'
        elif (0.08 > current_profit > 0.07):
            if (last_candle['r_480'] > -20.0) & (last_candle['rsi'] > 79.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_7'
        elif (0.09 > current_profit > 0.08):
            if (last_candle['r_480'] > -18.0) & (last_candle['rsi'] > 79.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_8'
        elif (0.1 > current_profit > 0.09):
            if (last_candle['r_480'] > -16.0) & (last_candle['rsi'] > 79.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_9'
        elif (0.12 > current_profit > 0.1):
            if (last_candle['r_480'] > -4.0) & (last_candle['rsi'] > 79.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_10'
        elif (0.2 > current_profit > 0.12):
            if (last_candle['r_480'] > -3.0) & (last_candle['rsi'] > 80.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_11'
        elif (current_profit > 0.2):
            if (last_candle['r_480'] > -2.0) & (last_candle['rsi'] > 80.0) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_12'

        return False, None

    def sell_quick_mode(self, current_profit: float, max_profit:float, last_candle, previous_candle_1, buy_signal_candle) -> tuple:
        if buy_signal_candle['buy_condition_32'] or buy_signal_candle['buy_condition_33'] or buy_signal_candle['buy_condition_34'] or buy_signal_candle['buy_condition_35'] or buy_signal_candle['buy_condition_36'] or buy_signal_candle['buy_condition_37'] or buy_signal_candle['buy_condition_38']:
            if (0.06 > current_profit > 0.02) & (last_candle['rsi'] > 79.0):
                return True, 'signal_profit_q_1'

            if (0.06 > current_profit > 0.02) & (last_candle['cti'] > 0.9):
                return True, 'signal_profit_q_2'

            if (current_profit < -0.1):
                return True, 'signal_stoploss_q_1'

            if(last_candle['close'] < last_candle['atr_high_thresh']) & (previous_candle_1['close'] > previous_candle_1['atr_high_thresh']):
                return True, 'signal_stoploss_q_atr'

            if (current_profit > 0.0):
                if (last_candle['pm'] <= last_candle['pmax_thresh']) & (last_candle['close'] > last_candle['sma_21'] * 1.039):
                    return True, 'signal_profit_q_pmax_bull'
                if (last_candle['pm'] > last_candle['pmax_thresh']) & (last_candle['close'] > last_candle['sma_21'] * 1.012):
                    return True, 'signal_profit_q_pmax_bear'
                if (last_candle['pm'] > last_candle['pmax_thresh']) & (last_candle['crsi'] >= 70):
                    return True, 'signal_profit_q_pmax_c'

        return False, None

    def custom_sell(self, pair: str, trade: 'Trade', current_time: 'datetime', current_rate: float,
                    current_profit: float, **kwargs):
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        previous_candle_1 = dataframe.iloc[-2].squeeze()
        previous_candle_2 = dataframe.iloc[-3].squeeze()
        previous_candle_3 = dataframe.iloc[-4].squeeze()
        previous_candle_4 = dataframe.iloc[-5].squeeze()
        previous_candle_5 = dataframe.iloc[-6].squeeze()

        trade_open_date = timeframe_to_prev_date(self.timeframe, trade.open_date_utc)
        buy_signal = dataframe.loc[dataframe['date'] < trade_open_date]
        if not buy_signal.empty:
            buy_signal_candle = buy_signal.iloc[-1].squeeze()

        max_profit = ((trade.max_rate - trade.open_rate) / trade.open_rate)
        max_loss = ((trade.open_rate - trade.min_rate) / trade.min_rate)

        # Quick sell mode
        if not buy_signal.empty:
            sell, signal_name = self.sell_quick_mode(current_profit, max_profit, last_candle, previous_candle_1, buy_signal_candle)
            if sell and (signal_name is not None):
                return signal_name

        # Over EMA200, main profit targets
        sell, signal_name = self.sell_over_main(current_profit, last_candle)
        if sell and (signal_name is not None):
            return signal_name

        # Under EMA200, main profit targets
        sell, signal_name = self.sell_under_main(current_profit, last_candle)
        if sell and (signal_name is not None):
            return signal_name

        # The pair is pumped
        sell, signal_name = self.sell_pump_main(current_profit, last_candle)
        if sell and (signal_name is not None):
            return signal_name

        # The pair is descending
        sell, signal_name = self.sell_dec_main(current_profit, last_candle)
        if sell and (signal_name is not None):
            return signal_name

        # Trailing
        sell, signal_name = self.sell_trail_main(current_profit, last_candle, max_profit)
        if sell and (signal_name is not None):
            return signal_name

        # Duration based
        sell, signal_name = self.sell_duration_main(current_profit, last_candle, trade, current_time)
        if sell and (signal_name is not None):
            return signal_name

        # Under EMA200, exit with any profit
        sell, signal_name = self.sell_under_min(current_profit, last_candle)
        if sell and (signal_name is not None):
            return signal_name

        # Stoplosses
        sell, signal_name = self.sell_stoploss(current_profit, last_candle, trade, current_time, max_loss, max_profit)
        if sell and (signal_name is not None):
            return signal_name

        # Pumped descending pairs
        sell, signal_name = self.sell_pump_dec(current_profit, last_candle)
        if sell and (signal_name is not None):
            return signal_name

        # Extra sells for pumped pairs
        sell, signal_name = self.sell_pump_extra(current_profit, last_candle, max_profit)
        if sell and (signal_name is not None):
            return signal_name

        # Extra sells for trades that recovered
        sell, signal_name = self.sell_recover(current_profit, last_candle, max_loss)
        if sell and (signal_name is not None):
            return signal_name

        # Williams %R based sell 1
        sell, signal_name = self.sell_r_1(current_profit, last_candle)
        if sell and (signal_name is not None):
            return signal_name

        # Williams %R based sell 2
        sell, signal_name = self.sell_r_2(current_profit, last_candle)
        if sell and (signal_name is not None):
            return signal_name

        # Williams %R based sell 3
        sell, signal_name = self.sell_r_3(current_profit, last_candle)
        if sell and (signal_name is not None):
            return signal_name

        # Williams %R based sell 4, plus CTI
        sell, signal_name = self.sell_r_4(current_profit, last_candle)
        if (sell) and (signal_name is not None):
            return signal_name

        # Sell signal 1
        if self.sell_condition_1_enable.value & (last_candle['rsi'] > self.sell_rsi_bb_1.value) & (last_candle['close'] > last_candle['bb20_2_upp']) & (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) & (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) & (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']) & (previous_candle_4['close'] > previous_candle_4['bb20_2_upp']) & (previous_candle_5['close'] > previous_candle_5['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.0):
                    return 'sell_signal_1_1_1'
                elif (max_loss > 0.1):
                    return 'sell_signal_1_1_2'
            else:
                return 'sell_signal_1_2'

        # Sell signal 2
        elif (self.sell_condition_2_enable.value) & (last_candle['rsi'] > self.sell_rsi_bb_2.value) & (last_candle['close'] > last_candle['bb20_2_upp']) & (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) & (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.0):
                    return 'sell_signal_2_1_1'
                elif (max_loss > 0.07):
                    return 'sell_signal_2_1_2'
            else:
                if (current_profit > 0.0):
                    return 'sell_signal_2_2_1'
                elif (max_loss > 0.07):
                    return 'sell_signal_2_2_2'

        # Sell signal 4
        elif self.sell_condition_4_enable.value & (last_candle['rsi'] > self.sell_dual_rsi_rsi_4.value) & (last_candle['rsi_1h'] > self.sell_dual_rsi_rsi_1h_4.value):
            return 'sell_signal_4'

        # Sell signal 6
        elif self.sell_condition_6_enable.value & (last_candle['close'] < last_candle['ema_200']) & (last_candle['close'] > last_candle['ema_50']) & (last_candle['rsi'] > self.sell_rsi_under_6.value):
            if (current_profit > 0.0):
                    return 'sell_signal_6_1'
            elif (max_loss > 0.08):
                return 'sell_signal_6_2'

        # Sell signal 7
        elif self.sell_condition_7_enable.value & (last_candle['rsi_1h'] > self.sell_rsi_1h_7.value) & (last_candle['crossed_below_ema_12_26']):
            return 'sell_signal_7'

        # Sell signal 8
        elif self.sell_condition_8_enable.value & (last_candle['close'] > last_candle['bb20_2_upp_1h'] * self.sell_bb_relative_8.value):
            return 'sell_signal_8'

        return None

    def range_percent_change(self, dataframe: DataFrame, method, length: int) -> float:
        """
        Rolling Percentage Change Maximum across interval.

        :param dataframe: DataFrame The original OHLC dataframe
        :param method: High to Low / Open to Close
        :param length: int The length to look back
        """
        df = dataframe.copy()
        if method == 'HL':
            return (df['high'].rolling(length).max() - df['low'].rolling(length).min()) / df['low'].rolling(length).min()
        elif method == 'OC':
            return (df['open'].rolling(length).max() - df['close'].rolling(length).min()) / df['close'].rolling(length).min()
        else:
            raise ValueError(f"Method {method} not defined!")

    def top_percent_change(self, dataframe: DataFrame, length: int) -> float:
        """
        Percentage change of the current close from the range maximum Open price

        :param dataframe: DataFrame The original OHLC dataframe
        :param length: int The length to look back
        """
        df = dataframe.copy()
        if length == 0:
            return (df['open'] - df['close']) / df['close']
        else:
            return (df['open'].rolling(length).max() - df['close']) / df['close']

    def range_maxgap(self, dataframe: DataFrame, length: int) -> float:
        """
        Maximum Price Gap across interval.

        :param dataframe: DataFrame The original OHLC dataframe
        :param length: int The length to look back
        """
        df = dataframe.copy()
        return df['open'].rolling(length).max() - df['close'].rolling(length).min()

    def range_maxgap_adjusted(self, dataframe: DataFrame, length: int, adjustment: float) -> float:
        """
        Maximum Price Gap across interval adjusted.

        :param dataframe: DataFrame The original OHLC dataframe
        :param length: int The length to look back
        :param adjustment: int The adjustment to be applied
        """
        return self.range_maxgap(dataframe, length) / adjustment

    def range_height(self, dataframe: DataFrame, length: int) -> float:
        """
        Current close distance to range bottom.

        :param dataframe: DataFrame The original OHLC dataframe
        :param length: int The length to look back
        """
        df = dataframe.copy()
        return df['close'] - df['close'].rolling(length).min()

    def safe_pump(self, dataframe: DataFrame, length: int, thresh: float, pull_thresh: float) -> bool:
        """
        Determine if entry after a pump is safe.

        :param dataframe: DataFrame The original OHLC dataframe
        :param length: int The length to look back
        :param thresh: int Maximum percentage change threshold
        :param pull_thresh: int Pullback from interval maximum threshold
        """
        df = dataframe.copy()
        return (df[f'oc_pct_change_{length}'] < thresh) | (self.range_maxgap_adjusted(df, length, pull_thresh) > self.range_height(df, length))

    def safe_dips(self, dataframe: DataFrame, thresh_0, thresh_2, thresh_12, thresh_144) -> bool:
        """
        Determine if dip is safe to enter.

        :param dataframe: DataFrame The original OHLC dataframe
        :param thresh_0: Threshold value for 0 length top pct change
        :param thresh_2: Threshold value for 2 length top pct change
        :param thresh_12: Threshold value for 12 length top pct change
        :param thresh_144: Threshold value for 144 length top pct change
        """
        return ((dataframe['tpct_change_0'] < thresh_0) &
                (dataframe['tpct_change_2'] < thresh_2) &
                (dataframe['tpct_change_12'] < thresh_12) &
                (dataframe['tpct_change_144'] < thresh_144))

    def informative_pairs(self):
        # get access to all pairs available in whitelist.
        pairs = self.dp.current_whitelist()
        # Assign tf to each pair so they can be downloaded and cached for strategy.
        informative_pairs = [(pair, self.info_timeframe) for pair in pairs]
        informative_pairs.append(('BTC/USDT', self.timeframe))
        informative_pairs.append(('BTC/USDT', self.info_timeframe))
        return informative_pairs

    def informative_1h_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        assert self.dp, "DataProvider is required for multiple timeframes."
        # Get the informative pair
        informative_1h = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=self.info_timeframe)

        # EMA
        informative_1h['ema_12'] = ta.EMA(informative_1h, timeperiod=12)
        informative_1h['ema_15'] = ta.EMA(informative_1h, timeperiod=15)
        informative_1h['ema_20'] = ta.EMA(informative_1h, timeperiod=20)
        informative_1h['ema_25'] = ta.EMA(informative_1h, timeperiod=25)
        informative_1h['ema_26'] = ta.EMA(informative_1h, timeperiod=26)
        informative_1h['ema_35'] = ta.EMA(informative_1h, timeperiod=35)
        informative_1h['ema_50'] = ta.EMA(informative_1h, timeperiod=50)
        informative_1h['ema_100'] = ta.EMA(informative_1h, timeperiod=100)
        informative_1h['ema_200'] = ta.EMA(informative_1h, timeperiod=200)

        # SMA
        informative_1h['sma_200'] = ta.SMA(informative_1h, timeperiod=200)
        informative_1h['sma_200_dec_20'] = informative_1h['sma_200'] < informative_1h['sma_200'].shift(20)

        # RSI
        informative_1h['rsi'] = ta.RSI(informative_1h, timeperiod=14)

        # BB
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(informative_1h), window=20, stds=2)
        informative_1h['bb20_2_low'] = bollinger['lower']
        informative_1h['bb20_2_mid'] = bollinger['mid']
        informative_1h['bb20_2_upp'] = bollinger['upper']

        # Chaikin Money Flow
        informative_1h['cmf'] = chaikin_money_flow(informative_1h, 20)

        # Williams %R
        informative_1h['r_480'] = williams_r(informative_1h, period=480)

        # Pump protections
        informative_1h['hl_pct_change_48'] = self.range_percent_change(informative_1h, 'HL', 48)
        informative_1h['hl_pct_change_36'] = self.range_percent_change(informative_1h, 'HL', 36)
        informative_1h['hl_pct_change_24'] = self.range_percent_change(informative_1h, 'HL', 24)

        informative_1h['oc_pct_change_48'] = self.range_percent_change(informative_1h, 'OC', 48)
        informative_1h['oc_pct_change_36'] = self.range_percent_change(informative_1h, 'OC', 36)
        informative_1h['oc_pct_change_24'] = self.range_percent_change(informative_1h, 'OC', 24)

        informative_1h['hl_pct_change_5'] = self.range_percent_change(informative_1h, 'HL', 5)
        informative_1h['low_5'] = informative_1h['low'].shift().rolling(5).min()

        informative_1h['safe_pump_24_10'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_10_24.value, self.buy_pump_pull_threshold_10_24.value)
        informative_1h['safe_pump_36_10'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_10_36.value, self.buy_pump_pull_threshold_10_36.value)
        informative_1h['safe_pump_48_10'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_10_48.value, self.buy_pump_pull_threshold_10_48.value)

        informative_1h['safe_pump_24_20'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_20_24.value, self.buy_pump_pull_threshold_20_24.value)
        informative_1h['safe_pump_36_20'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_20_36.value, self.buy_pump_pull_threshold_20_36.value)
        informative_1h['safe_pump_48_20'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_20_48.value, self.buy_pump_pull_threshold_20_48.value)

        informative_1h['safe_pump_24_30'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_30_24.value, self.buy_pump_pull_threshold_30_24.value)
        informative_1h['safe_pump_36_30'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_30_36.value, self.buy_pump_pull_threshold_30_36.value)
        informative_1h['safe_pump_48_30'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_30_48.value, self.buy_pump_pull_threshold_30_48.value)

        informative_1h['safe_pump_24_40'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_40_24.value, self.buy_pump_pull_threshold_40_24.value)
        informative_1h['safe_pump_36_40'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_40_36.value, self.buy_pump_pull_threshold_40_36.value)
        informative_1h['safe_pump_48_40'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_40_48.value, self.buy_pump_pull_threshold_40_48.value)

        informative_1h['safe_pump_24_50'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_50_24.value, self.buy_pump_pull_threshold_50_24.value)
        informative_1h['safe_pump_36_50'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_50_36.value, self.buy_pump_pull_threshold_50_36.value)
        informative_1h['safe_pump_48_50'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_50_48.value, self.buy_pump_pull_threshold_50_48.value)

        informative_1h['safe_pump_24_60'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_60_24.value, self.buy_pump_pull_threshold_60_24.value)
        informative_1h['safe_pump_36_60'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_60_36.value, self.buy_pump_pull_threshold_60_36.value)
        informative_1h['safe_pump_48_60'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_60_48.value, self.buy_pump_pull_threshold_60_48.value)

        informative_1h['safe_pump_24_70'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_70_24.value, self.buy_pump_pull_threshold_70_24.value)
        informative_1h['safe_pump_36_70'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_70_36.value, self.buy_pump_pull_threshold_70_36.value)
        informative_1h['safe_pump_48_70'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_70_48.value, self.buy_pump_pull_threshold_70_48.value)

        informative_1h['safe_pump_24_80'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_80_24.value, self.buy_pump_pull_threshold_80_24.value)
        informative_1h['safe_pump_36_80'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_80_36.value, self.buy_pump_pull_threshold_80_36.value)
        informative_1h['safe_pump_48_80'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_80_48.value, self.buy_pump_pull_threshold_80_48.value)

        informative_1h['safe_pump_24_90'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_90_24.value, self.buy_pump_pull_threshold_90_24.value)
        informative_1h['safe_pump_36_90'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_90_36.value, self.buy_pump_pull_threshold_90_36.value)
        informative_1h['safe_pump_48_90'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_90_48.value, self.buy_pump_pull_threshold_90_48.value)

        informative_1h['safe_pump_24_100'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_100_24.value, self.buy_pump_pull_threshold_100_24.value)
        informative_1h['safe_pump_36_100'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_100_36.value, self.buy_pump_pull_threshold_100_36.value)
        informative_1h['safe_pump_48_100'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_100_48.value, self.buy_pump_pull_threshold_100_48.value)

        informative_1h['safe_pump_24_110'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_110_24.value, self.buy_pump_pull_threshold_110_24.value)
        informative_1h['safe_pump_36_110'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_110_36.value, self.buy_pump_pull_threshold_110_36.value)
        informative_1h['safe_pump_48_110'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_110_48.value, self.buy_pump_pull_threshold_110_48.value)

        informative_1h['safe_pump_24_120'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_120_24.value, self.buy_pump_pull_threshold_120_24.value)
        informative_1h['safe_pump_36_120'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_120_36.value, self.buy_pump_pull_threshold_120_36.value)
        informative_1h['safe_pump_48_120'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_120_48.value, self.buy_pump_pull_threshold_120_48.value)

        informative_1h['safe_dump_10'] = ((informative_1h['hl_pct_change_5'] < self.buy_dump_protection_10_5.value) | (informative_1h['close'] < informative_1h['low_5']) | (informative_1h['close'] > informative_1h['open']))
        informative_1h['safe_dump_20'] = ((informative_1h['hl_pct_change_5'] < self.buy_dump_protection_20_5.value) | (informative_1h['close'] < informative_1h['low_5']) | (informative_1h['close'] > informative_1h['open']))
        informative_1h['safe_dump_30'] = ((informative_1h['hl_pct_change_5'] < self.buy_dump_protection_30_5.value) | (informative_1h['close'] < informative_1h['low_5']) | (informative_1h['close'] > informative_1h['open']))
        informative_1h['safe_dump_40'] = ((informative_1h['hl_pct_change_5'] < self.buy_dump_protection_40_5.value) | (informative_1h['close'] < informative_1h['low_5']) | (informative_1h['close'] > informative_1h['open']))
        informative_1h['safe_dump_50'] = ((informative_1h['hl_pct_change_5'] < self.buy_dump_protection_50_5.value) | (informative_1h['close'] < informative_1h['low_5']) | (informative_1h['close'] > informative_1h['open']))
        informative_1h['safe_dump_60'] = ((informative_1h['hl_pct_change_5'] < self.buy_dump_protection_60_5.value) | (informative_1h['close'] < informative_1h['low_5']) | (informative_1h['close'] > informative_1h['open']))

        informative_1h['sell_pump_48_1'] = (informative_1h['hl_pct_change_48'] > self.sell_pump_threshold_48_1.value)
        informative_1h['sell_pump_48_2'] = (informative_1h['hl_pct_change_48'] > self.sell_pump_threshold_48_2.value)
        informative_1h['sell_pump_48_3'] = (informative_1h['hl_pct_change_48'] > self.sell_pump_threshold_48_3.value)

        informative_1h['sell_pump_36_1'] = (informative_1h['hl_pct_change_36'] > self.sell_pump_threshold_36_1.value)
        informative_1h['sell_pump_36_2'] = (informative_1h['hl_pct_change_36'] > self.sell_pump_threshold_36_2.value)
        informative_1h['sell_pump_36_3'] = (informative_1h['hl_pct_change_36'] > self.sell_pump_threshold_36_3.value)

        informative_1h['sell_pump_24_1'] = (informative_1h['hl_pct_change_24'] > self.sell_pump_threshold_24_1.value)
        informative_1h['sell_pump_24_2'] = (informative_1h['hl_pct_change_24'] > self.sell_pump_threshold_24_2.value)
        informative_1h['sell_pump_24_3'] = (informative_1h['hl_pct_change_24'] > self.sell_pump_threshold_24_3.value)

        return informative_1h.copy()

    def normal_tf_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # BB 40 - STD2
        bb_40_std2 = qtpylib.bollinger_bands(dataframe['close'], window=40, stds=2)
        dataframe['bb40_2_low']= bb_40_std2['lower']
        dataframe['bb40_2_mid'] = bb_40_std2['mid']
        dataframe['bb40_2_delta'] = (bb_40_std2['mid'] - dataframe['bb40_2_low']).abs()
        dataframe['closedelta'] = (dataframe['close'] - dataframe['close'].shift()).abs()
        dataframe['tail'] = (dataframe['close'] - dataframe['bb40_2_low']).abs()

        # BB 20 - STD2
        bb_20_std2 = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb20_2_low'] = bb_20_std2['lower']
        dataframe['bb20_2_mid'] = bb_20_std2['mid']
        dataframe['bb20_2_upp'] = bb_20_std2['upper']

        # EMA 200
        dataframe['ema_12'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['ema_13'] = ta.EMA(dataframe, timeperiod=13)
        dataframe['ema_15'] = ta.EMA(dataframe, timeperiod=15)
        dataframe['ema_20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema_25'] = ta.EMA(dataframe, timeperiod=25)
        dataframe['ema_26'] = ta.EMA(dataframe, timeperiod=26)
        dataframe['ema_35'] = ta.EMA(dataframe, timeperiod=35)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_100'] = ta.EMA(dataframe, timeperiod=100)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)

        # SMA
        dataframe['sma_5'] = ta.SMA(dataframe, timeperiod=5)
        dataframe['sma_15'] = ta.SMA(dataframe, timeperiod=15)
        dataframe['sma_20'] = ta.SMA(dataframe, timeperiod=20)
        dataframe['sma_30'] = ta.SMA(dataframe, timeperiod=30)
        dataframe['sma_200'] = ta.SMA(dataframe, timeperiod=200)

        dataframe['sma_200_dec_20'] = dataframe['sma_200'] < dataframe['sma_200'].shift(20)
        dataframe['sma_200_dec_24'] = dataframe['sma_200'] < dataframe['sma_200'].shift(24)

        # MFI
        dataframe['mfi'] = ta.MFI(dataframe)

        # CMF
        dataframe['cmf'] = chaikin_money_flow(dataframe, 20)

        # EWO
        dataframe['ewo'] = ewo(dataframe, 50, 200)

        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_4'] = ta.RSI(dataframe, timeperiod=4)
        dataframe['rsi_20'] = ta.RSI(dataframe, timeperiod=20)

        # Chopiness
        dataframe['chop']= qtpylib.chopiness(dataframe, 14)

        # Zero-Lag EMA
        dataframe['zema_61'] = zema(dataframe, period=61)

        # Williams %R
        dataframe['r_480'] = williams_r(dataframe, period=480)

        # Stochastic RSI
        stochrsi = ta.STOCHRSI(dataframe, timeperiod=96, fastk_period=3, fastd_period=3, fastd_matype=0)
        dataframe['stochrsi_fastk_96'] = stochrsi['fastk']
        dataframe['stochrsi_fastd_96'] = stochrsi['fastd']

        # Modified Elder Ray Index
        dataframe['moderi_32'] = moderi(dataframe, 32)
        dataframe['moderi_64'] = moderi(dataframe, 64)
        dataframe['moderi_96'] = moderi(dataframe, 96)

        # TSI
        dataframe['tsi_slow'] = tsi(dataframe, window_slow=20, window_fast=5)
        dataframe['tsi_ema_slow'] = ta.EMA(dataframe['tsi_slow'], timeperiod=5)

        dataframe['tsi_fast'] = tsi(dataframe, window_slow=4, window_fast=2)
        dataframe['tsi_ema_fast'] = ta.EMA(dataframe['tsi_fast'], timeperiod=2)

        # hull
        dataframe['hull_75'] = hull(dataframe, 75)

        # zlema
        dataframe['zlema_68'] = zlema(dataframe, 68)

        # CTI
        dataframe['cti'] = pta.cti(dataframe["close"], length=20)

        # For sell checks
        dataframe['crossed_below_ema_12_26'] = qtpylib.crossed_below(dataframe['ema_12'], dataframe['ema_26'])

        # Heiken Ashi
        heikinashi = qtpylib.heikinashi(dataframe)
        heikinashi["volume"] = dataframe["volume"]

        # Profit Maximizer - PMAX
        dataframe['pm'], dataframe['pmx'] = pmax(heikinashi, MAtype=1, length=9, multiplier=27, period=10, src=3)
        dataframe['source'] = (dataframe['high'] + dataframe['low'] + dataframe['open'] + dataframe['close'])/4
        dataframe['pmax_thresh'] = ta.EMA(dataframe['source'], timeperiod=9)

        dataframe['sma_21'] = ta.SMA(dataframe, timeperiod=21)
        dataframe['sma_68'] = ta.SMA(dataframe, timeperiod=68)
        dataframe['sma_75'] = ta.SMA(dataframe, timeperiod=75)

        # ATR
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_high_thresh'] = (dataframe['high'] - (dataframe['atr'] * 2.83))

        dataframe['rsi_5'] = ta.RSI(dataframe, 5)
        dataframe['streak'] = calc_streaks(dataframe["close"])
        dataframe['srsi'] = ta.RSI(dataframe['streak'], 2)
        dataframe['roc'] = ta.ROC(dataframe, 5)
        dataframe['crsi'] = (dataframe['rsi_5'] + dataframe['srsi'] + dataframe['roc']) / 3

        # Dip protection
        dataframe['tpct_change_0']   = self.top_percent_change(dataframe,0)
        dataframe['tpct_change_2']   = self.top_percent_change(dataframe,2)
        dataframe['tpct_change_12']  = self.top_percent_change(dataframe,12)
        dataframe['tpct_change_144'] = self.top_percent_change(dataframe,144)

        dataframe['safe_dips_10']  = self.safe_dips(dataframe, self.buy_dip_threshold_10_1.value, self.buy_dip_threshold_10_2.value, self.buy_dip_threshold_10_3.value, self.buy_dip_threshold_10_4.value)
        dataframe['safe_dips_20']  = self.safe_dips(dataframe, self.buy_dip_threshold_20_1.value, self.buy_dip_threshold_20_2.value, self.buy_dip_threshold_20_3.value, self.buy_dip_threshold_20_4.value)
        dataframe['safe_dips_30']  = self.safe_dips(dataframe, self.buy_dip_threshold_30_1.value, self.buy_dip_threshold_30_2.value, self.buy_dip_threshold_30_3.value, self.buy_dip_threshold_30_4.value)
        dataframe['safe_dips_40']  = self.safe_dips(dataframe, self.buy_dip_threshold_40_1.value, self.buy_dip_threshold_40_2.value, self.buy_dip_threshold_40_3.value, self.buy_dip_threshold_40_4.value)
        dataframe['safe_dips_50']  = self.safe_dips(dataframe, self.buy_dip_threshold_50_1.value, self.buy_dip_threshold_50_2.value, self.buy_dip_threshold_50_3.value, self.buy_dip_threshold_50_4.value)
        dataframe['safe_dips_60']  = self.safe_dips(dataframe, self.buy_dip_threshold_60_1.value, self.buy_dip_threshold_60_2.value, self.buy_dip_threshold_60_3.value, self.buy_dip_threshold_60_4.value)
        dataframe['safe_dips_70']  = self.safe_dips(dataframe, self.buy_dip_threshold_70_1.value, self.buy_dip_threshold_70_2.value, self.buy_dip_threshold_70_3.value, self.buy_dip_threshold_70_4.value)
        dataframe['safe_dips_80']  = self.safe_dips(dataframe, self.buy_dip_threshold_80_1.value, self.buy_dip_threshold_80_2.value, self.buy_dip_threshold_80_3.value, self.buy_dip_threshold_80_4.value)
        dataframe['safe_dips_90']  = self.safe_dips(dataframe, self.buy_dip_threshold_90_1.value, self.buy_dip_threshold_90_2.value, self.buy_dip_threshold_90_3.value, self.buy_dip_threshold_90_4.value)
        dataframe['safe_dips_100'] = self.safe_dips(dataframe, self.buy_dip_threshold_100_1.value, self.buy_dip_threshold_100_2.value, self.buy_dip_threshold_100_3.value, self.buy_dip_threshold_100_4.value)
        dataframe['safe_dips_110'] = self.safe_dips(dataframe, self.buy_dip_threshold_110_1.value, self.buy_dip_threshold_110_2.value, self.buy_dip_threshold_110_3.value, self.buy_dip_threshold_110_4.value)
        dataframe['safe_dips_120'] = self.safe_dips(dataframe, self.buy_dip_threshold_120_1.value, self.buy_dip_threshold_120_2.value, self.buy_dip_threshold_120_3.value, self.buy_dip_threshold_120_4.value)
        dataframe['safe_dips_130'] = self.safe_dips(dataframe, self.buy_dip_threshold_130_1.value, self.buy_dip_threshold_130_2.value, self.buy_dip_threshold_130_3.value, self.buy_dip_threshold_130_4.value)

        # Volume
        dataframe['volume_mean_4'] = dataframe['volume'].rolling(4).mean().shift(1)
        dataframe['volume_mean_30'] = dataframe['volume'].rolling(30).mean()

        if not self.config['runmode'].value in ('live', 'dry_run'):
            # Backtest age filter
            dataframe['bt_agefilter_ok'] = False
            dataframe.loc[dataframe.index > (12 * 24 * self.bt_min_age_days),'bt_agefilter_ok'] = True
        else:
            # Exchange downtime protection
            dataframe['live_data_ok'] = (dataframe['volume'].rolling(window=72, min_periods=72).min() > 0)

        return dataframe.copy()

    def resampled_tf_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Indicators
        # -----------------------------------------------------------------------------------------
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)

        return dataframe

    def base_tf_btc_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Indicators
        # -----------------------------------------------------------------------------------------
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)

        # Add prefix
        # -----------------------------------------------------------------------------------------
        ignore_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        dataframe.rename(columns=lambda s: "btc_" + s  if (not s in ignore_columns) else s, inplace=True)

        return dataframe

    def info_tf_btc_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Indicators
        # -----------------------------------------------------------------------------------------
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['not_downtrend'] = ((dataframe['close'] > dataframe['close'].shift(2)) | (dataframe['rsi'] > 50))

        # Add prefix
        # -----------------------------------------------------------------------------------------
        ignore_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        dataframe.rename(columns=lambda s: "btc_" + s if (not s in ignore_columns) else s, inplace=True)

        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        '''
        --> BTC informative (5m/1h)
        ___________________________________________________________________________________________
        '''
        if self.has_BTC_base_tf:
            btc_base_tf = self.dp.get_pair_dataframe("BTC/USDT", self.timeframe)
            btc_base_tf = self.base_tf_btc_indicators(btc_base_tf, metadata)
            dataframe = merge_informative_pair(dataframe, btc_base_tf, self.timeframe, self.timeframe, ffill=True)
            drop_columns = [(s + "_" + self.timeframe) for s in ['date', 'open', 'high', 'low', 'close', 'volume']]
            dataframe.drop(columns=dataframe.columns.intersection(drop_columns), inplace=True)

        if self.has_BTC_info_tf:
            btc_info_tf = self.dp.get_pair_dataframe("BTC/USDT", self.info_timeframe)
            btc_info_tf = self.info_tf_btc_indicators(btc_info_tf, metadata)
            dataframe = merge_informative_pair(dataframe, btc_info_tf, self.timeframe, self.info_timeframe, ffill=True)
            drop_columns = [(s + "_" + self.info_timeframe) for s in ['date', 'open', 'high', 'low', 'close', 'volume']]
            dataframe.drop(columns=dataframe.columns.intersection(drop_columns), inplace=True)

        '''
        --> Informative timeframe
        ___________________________________________________________________________________________
        '''
        if self.info_timeframe != 'none':
            informative_1h = self.informative_1h_indicators(dataframe, metadata)
            dataframe = merge_informative_pair(dataframe, informative_1h, self.timeframe, self.info_timeframe, ffill=True)
            drop_columns = [(s + "_" + self.info_timeframe) for s in ['date']]
            dataframe.drop(columns=dataframe.columns.intersection(drop_columns), inplace=True)

        '''
        --> Resampled to another timeframe
        ___________________________________________________________________________________________
        '''
        if self.res_timeframe != 'none':
            resampled = resample_to_interval(dataframe, timeframe_to_minutes(self.res_timeframe))
            resampled = self.resampled_tf_indicators(resampled, metadata)
            # Merge resampled info dataframe
            dataframe = resampled_merge(dataframe, resampled, fill_na=True)
            dataframe.rename(columns=lambda s: s+"_{}".format(self.res_timeframe) if "resample_" in s else s, inplace=True)
            dataframe.rename(columns=lambda s: s.replace("resample_{}_".format(self.res_timeframe.replace("m","")), ""), inplace=True)
            drop_columns = [(s + "_" + self.res_timeframe) for s in ['date']]
            dataframe.drop(columns=dataframe.columns.intersection(drop_columns), inplace=True)

        '''
        --> The indicators for the normal (5m) timeframe
        ___________________________________________________________________________________________
        '''
        dataframe = self.normal_tf_indicators(dataframe, metadata)
        return dataframe


    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = []
        buy_protection_list = []

        # Protections [STANDARD] - Common to every condition
        for index in self.buy_protection_params:
            item_buy_protection_list = [True]
            global_buy_protection_params = self.buy_protection_params[index]
            if global_buy_protection_params["ema_fast"].value:
                item_buy_protection_list.append(dataframe[f"ema_{global_buy_protection_params['ema_fast_len'].value}"] > dataframe['ema_200'])
            if global_buy_protection_params["ema_slow"].value:
                item_buy_protection_list.append(dataframe[f"ema_{global_buy_protection_params['ema_slow_len'].value}_1h"] > dataframe['ema_200_1h'])
            if global_buy_protection_params["close_above_ema_fast"].value:
                item_buy_protection_list.append(dataframe['close'] > dataframe[f"ema_{global_buy_protection_params['close_above_ema_fast_len'].value}"])
            if global_buy_protection_params["close_above_ema_slow"].value:
                item_buy_protection_list.append(dataframe['close'] > dataframe[f"ema_{global_buy_protection_params['close_above_ema_slow_len'].value}_1h"])
            if global_buy_protection_params["sma200_rising"].value:
                item_buy_protection_list.append(dataframe['sma_200'] > dataframe['sma_200'].shift(int(global_buy_protection_params['sma200_rising_val'].value)))
            if global_buy_protection_params["sma200_1h_rising"].value:
                item_buy_protection_list.append(dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(int(global_buy_protection_params['sma200_1h_rising_val'].value)))
            if global_buy_protection_params["safe_dips"].value:
                item_buy_protection_list.append(dataframe[f"safe_dips_{global_buy_protection_params['safe_dips_type'].value}"])
            if global_buy_protection_params["safe_pump"].value:
                item_buy_protection_list.append(dataframe[f"safe_pump_{global_buy_protection_params['safe_pump_period'].value}_{global_buy_protection_params['safe_pump_type'].value}_1h"])
            if global_buy_protection_params['btc_1h_not_downtrend'].value:
                item_buy_protection_list.append(dataframe['btc_not_downtrend_1h'])
            if not self.config['runmode'].value in ('live', 'dry_run'):
                if self.has_bt_agefilter:
                    item_buy_protection_list.append(dataframe['bt_agefilter_ok'])
            else:
                if self.has_downtime_protection:
                    item_buy_protection_list.append(dataframe['live_data_ok'])
            buy_protection_list.append(item_buy_protection_list)

        # Buy Condition #1
        dataframe.loc[:,'buy_condition_1'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_1_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[0]))
            item_buy_logic.append(((dataframe['close'] - dataframe['open'].rolling(36).min()) / dataframe['open'].rolling(36).min()) > self.buy_min_inc_1.value)
            item_buy_logic.append(dataframe['rsi_1h'] > self.buy_rsi_1h_min_1.value)
            item_buy_logic.append(dataframe['rsi_1h'] < self.buy_rsi_1h_max_1.value)
            item_buy_logic.append(dataframe['rsi'] < self.buy_rsi_1.value)
            item_buy_logic.append(dataframe['mfi'] < self.buy_mfi_1.value)
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_1.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_1'] = True

        # Buy Condition #2
        dataframe.loc[:,'buy_condition_2'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_2_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[1]))
            item_buy_logic.append(dataframe['rsi'] < dataframe['rsi_1h'] - self.buy_rsi_1h_diff_2.value)
            item_buy_logic.append(dataframe['mfi'] < self.buy_mfi_2.value)
            item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_bb_offset_2.value))
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_volume_2.value))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_2'] = True

        # Buy Condition #3
        dataframe.loc[:,'buy_condition_3'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_3_enable']:
            # Non-Standard protections (add below)
            buy_protection_list[2].append(dataframe['close'] > (dataframe['ema_200_1h'] * self.buy_ema_rel_3.value))

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[2]))
            item_buy_logic.append(dataframe['bb40_2_low'].shift().gt(0))
            item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * self.buy_bb40_bbdelta_close_3.value))
            item_buy_logic.append(dataframe['closedelta'].gt(dataframe['close'] * self.buy_bb40_closedelta_close_3.value))
            item_buy_logic.append(dataframe['tail'].lt(dataframe['bb40_2_delta'] * self.buy_bb40_tail_bbdelta_3.value))
            item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
            item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_3.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_3'] = True

        # Buy Condition #4
        dataframe.loc[:,'buy_condition_4'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_4_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[3]))
            item_buy_logic.append(dataframe['close'] < dataframe['ema_50'])
            item_buy_logic.append(dataframe['close'] < self.buy_bb20_close_bblowerband_4.value * dataframe['bb20_2_low'])
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_30'].shift(1) * self.buy_bb20_volume_4.value))
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_4.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_4'] = True

        # Buy Condition #5
        dataframe.loc[:,'buy_condition_5'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_5_enable']:
            # Non-Standard protections (add below)
            buy_protection_list[4].append(dataframe['close'] > (dataframe['ema_200_1h'] * self.buy_ema_rel_5.value))

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[4]))
            item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
            item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_ema_open_mult_5.value))
            item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
            item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_bb_offset_5.value))
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_5.value)
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_volume_5.value))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_5'] = True

        # Buy Condition #6
        dataframe.loc[:,'buy_condition_6'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_6_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[5]))
            item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
            item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_ema_open_mult_6.value))
            item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
            item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_bb_offset_6.value))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_6'] = True

        # Buy Condition #7
        dataframe.loc[:,'buy_condition_7'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_7_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[6]))
            item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
            item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_ema_open_mult_7.value))
            item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_7.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_7'] = True

        # Buy Condition #8
        dataframe.loc[:,'buy_condition_8'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_8_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[7]))
            item_buy_logic.append(dataframe['moderi_96'])
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_8.value)
            item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_bb_offset_8.value))
            item_buy_logic.append(dataframe['rsi_1h'] < self.buy_rsi_1h_8.value)
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_volume_8.value))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_8'] = True

        # Buy Condition #9
        dataframe.loc[:,'buy_condition_9'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_9_enable']:
            # Non-Standard protections (add below)
            buy_protection_list[8].append(dataframe['ema_50'] > dataframe['ema_200'])

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[8]))
            item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * self.buy_ma_offset_9.value)
            item_buy_logic.append(dataframe['close'] < dataframe['bb20_2_low'] * self.buy_bb_offset_9.value)
            item_buy_logic.append(dataframe['rsi_1h'] > self.buy_rsi_1h_min_9.value)
            item_buy_logic.append(dataframe['rsi_1h'] < self.buy_rsi_1h_max_9.value)
            item_buy_logic.append(dataframe['mfi'] < self.buy_mfi_9.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_9'] = True

        # Buy Condition #10
        dataframe.loc[:,'buy_condition_10'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_10_enable']:
            # Non-Standard protections (add below)
            buy_protection_list[9].append(dataframe['ema_50_1h'] > dataframe['ema_100_1h'])

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[9]))
            item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_ma_offset_10.value)
            item_buy_logic.append(dataframe['close'] < dataframe['bb20_2_low'] * self.buy_bb_offset_10.value)
            item_buy_logic.append(dataframe['rsi_1h'] < self.buy_rsi_1h_10.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_10'] = True

        # Buy Condition #11
        dataframe.loc[:,'buy_condition_11'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_11_enable']:
            # Non-Standard protections (add below)
            buy_protection_list[10].append(dataframe['ema_50_1h'] > dataframe['ema_100_1h'])

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[10]))
            item_buy_logic.append(((dataframe['close'] - dataframe['open'].rolling(36).min()) / dataframe['open'].rolling(36).min()) > self.buy_min_inc_11.value)
            item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_ma_offset_11.value)
            item_buy_logic.append(dataframe['rsi_1h'] > self.buy_rsi_1h_min_11.value)
            item_buy_logic.append(dataframe['rsi_1h'] < self.buy_rsi_1h_max_11.value)
            item_buy_logic.append(dataframe['rsi'] < self.buy_rsi_11.value)
            item_buy_logic.append(dataframe['mfi'] < self.buy_mfi_11.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_11'] = True

        # Buy Condition #12
        dataframe.loc[:,'buy_condition_12'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_12_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[11]))
            item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_ma_offset_12.value)
            item_buy_logic.append(dataframe['ewo'] > self.buy_ewo_12.value)
            item_buy_logic.append(dataframe['rsi'] < self.buy_rsi_12.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_12'] = True

        # Buy Condition #13
        dataframe.loc[:,'buy_condition_13'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_13_enable']:
            # Non-Standard protections (add below)
            buy_protection_list[12].append(dataframe['ema_50_1h'] > dataframe['ema_100_1h'])

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[12]))
            item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_ma_offset_13.value)
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_13.value)
            item_buy_logic.append(dataframe['ewo'] < self.buy_ewo_13.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_13'] = True

        # Buy Condition #14
        dataframe.loc[ :,'buy_condition_14'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_14_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[13]))
            item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
            item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_ema_open_mult_14.value))
            item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
            item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_bb_offset_14.value))
            item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * self.buy_ma_offset_14.value)
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_14.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_14'] = True

        # Buy Condition #15
        dataframe.loc[:,'buy_condition_15'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_15_enable']:
            # Non-Standard protections (add below)
            buy_protection_list[14].append(dataframe['close'] > dataframe['ema_200_1h'] * self.buy_ema_rel_15.value)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[14]))
            item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
            item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_ema_open_mult_15.value))
            item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
            item_buy_logic.append(dataframe['rsi'] < self.buy_rsi_15.value)
            item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * self.buy_ma_offset_15.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_15'] = True

        # Buy Condition #16
        dataframe.loc[:,'buy_condition_16'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_16_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[15]))
            item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * self.buy_ma_offset_16.value)
            item_buy_logic.append(dataframe['ewo'] > self.buy_ewo_16.value)
            item_buy_logic.append(dataframe['rsi'] < self.buy_rsi_16.value)
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_16.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_16'] = True

        # Buy Condition #17
        dataframe.loc[:,'buy_condition_17'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_17_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[16]))
            item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * self.buy_ma_offset_17.value)
            item_buy_logic.append(dataframe['ewo'] < self.buy_ewo_17.value)
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_17.value)
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_volume_17.value))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_17'] = True

        # Buy Condition #18
        dataframe.loc[:,'buy_condition_18'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_18_enable']:
            # Non-Standard protections (add below)
            buy_protection_list[17].append(dataframe['sma_200'] > dataframe['sma_200'].shift(20))
            buy_protection_list[17].append(dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(36))

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[17]))
            item_buy_logic.append(dataframe['rsi'] < self.buy_rsi_18.value)
            item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_bb_offset_18.value))
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_volume_18.value))
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_18.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_18'] = True

        # Buy Condition #19
        dataframe.loc[:,'buy_condition_19'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_19_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[18]))
            item_buy_logic.append(dataframe['close'].shift(1) > dataframe['ema_100_1h'])
            item_buy_logic.append(dataframe['low'] < dataframe['ema_100_1h'])
            item_buy_logic.append(dataframe['close'] > dataframe['ema_100_1h'])
            item_buy_logic.append(dataframe['rsi_1h'] > self.buy_rsi_1h_min_19.value)
            item_buy_logic.append(dataframe['chop'] < self.buy_chop_min_19.value)
            item_buy_logic.append(dataframe['moderi_32'] == True)
            item_buy_logic.append(dataframe['moderi_64'] == True)
            item_buy_logic.append(dataframe['moderi_96'] == True)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_19'] = True

        # Buy Condition #20
        dataframe.loc[:,'buy_condition_20'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_20_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[19]))
            item_buy_logic.append(dataframe['rsi'] < self.buy_rsi_20.value)
            item_buy_logic.append(dataframe['rsi_1h'] < self.buy_rsi_1h_20.value)
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_20.value)
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_volume_20.value))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_20'] = True

        # Buy Condition #21
        dataframe.loc[:,'buy_condition_21'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_21_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[20]))
            item_buy_logic.append(dataframe['rsi'] < self.buy_rsi_21.value)
            item_buy_logic.append(dataframe['rsi_1h'] < self.buy_rsi_1h_21.value)
            item_buy_logic.append(dataframe['cti'] < self.buy_cti_21.value)
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_volume_21.value))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_21'] = True

        # Buy Condition #22
        dataframe.loc[:,'buy_condition_22'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_22_enable']:
            # Non-Standard protections (add below)
            buy_protection_list[21].append(dataframe['ema_100_1h'] > dataframe['ema_100_1h'].shift(12))
            buy_protection_list[21].append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(36))

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[21]))
            item_buy_logic.append((dataframe['volume_mean_4'] * self.buy_volume_22.value) > dataframe['volume'])
            item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_ma_offset_22.value)
            item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_bb_offset_22.value))
            item_buy_logic.append(dataframe['ewo'] > self.buy_ewo_22.value)
            item_buy_logic.append(dataframe['rsi'] < self.buy_rsi_22.value)
            item_buy_logic.append(dataframe['safe_dump_20_1h'])
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_22'] = True

        # Buy Condition #23
        dataframe.loc[:,'buy_condition_23'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_23_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[22]))
            item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_bb_offset_23.value))
            item_buy_logic.append(dataframe['ewo'] > self.buy_ewo_23.value)
            item_buy_logic.append(dataframe['rsi'] < self.buy_rsi_23.value)
            item_buy_logic.append(dataframe['rsi_1h'] < self.buy_rsi_1h_23.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_23'] = True

        # Buy Condition #24
        dataframe.loc[:,'buy_condition_24'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_24_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[23]))
            item_buy_logic.append(dataframe['ema_12_1h'].shift(12) < dataframe['ema_35_1h'].shift(12))
            item_buy_logic.append(dataframe['ema_12_1h'] > dataframe['ema_35_1h'])
            item_buy_logic.append(dataframe['cmf_1h'].shift(12) < 0)
            item_buy_logic.append(dataframe['cmf_1h'] > 0)
            item_buy_logic.append(dataframe['rsi'] < self.buy_24_rsi_max.value)
            item_buy_logic.append(dataframe['rsi_1h'] > self.buy_24_rsi_1h_min.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_24'] = True

        # Buy Condition #25
        dataframe.loc[:,'buy_condition_25'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_25_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[24]))
            item_buy_logic.append(dataframe['rsi_20'] < dataframe['rsi_20'].shift())
            item_buy_logic.append(dataframe['rsi_4'] < self.buy_25_rsi_4.value)
            item_buy_logic.append(dataframe['ema_20_1h'] > dataframe['ema_26_1h'])
            item_buy_logic.append(dataframe['close'] < (dataframe['sma_20'] * self.buy_25_ma_offset.value))
            item_buy_logic.append(dataframe['open'] > (dataframe['sma_20'] * self.buy_25_ma_offset.value))
            item_buy_logic.append(
                (dataframe['open'] < dataframe['ema_20_1h']) & (dataframe['low'] < dataframe['ema_20_1h']) |
                (dataframe['open'] > dataframe['ema_20_1h']) & (dataframe['low'] > dataframe['ema_20_1h'])
            )
            item_buy_logic.append(dataframe['cti'] < self.buy_25_cti.value)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_25'] = True

        # Buy Condition #26
        dataframe.loc[:,'buy_condition_26'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_26_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[25]))
            item_buy_logic.append(dataframe['close'] < (dataframe['zema_61'] * self.buy_26_zema_low_offset.value))
            item_buy_logic.append(dataframe['cti'] < self.buy_26_cti.value)
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_26_volume.value))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_26'] = True

        # Buy Condition #27
        dataframe.loc[:,'buy_condition_27'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_27_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[26]))
            item_buy_logic.append(dataframe['r_480'] < -self.buy_27_wr_max.value)
            item_buy_logic.append(dataframe['r_480_1h'] < -self.buy_27_wr_1h_max.value)
            item_buy_logic.append(dataframe['rsi_1h'] + dataframe['rsi'] < self.buy_27_rsi_max.value)
            item_buy_logic.append(dataframe['cti'] < self.buy_27_cti.value)
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_27_volume.value))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_27'] = True

        # Buy Condition #28
        dataframe.loc[:,'buy_condition_28'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_28_enable']:
            # Non-Standard protections (add below)

            # Logic
            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[27]))
            item_buy_logic.append(dataframe['moderi_64'] == True)
            item_buy_logic.append(dataframe['close'] < dataframe['hull_75'] * self.buy_28_ma_offset.value)
            item_buy_logic.append(dataframe['ewo'] > self.buy_28_ewo.value)
            item_buy_logic.append(dataframe['rsi'] < self.buy_28_rsi.value)
            item_buy_logic.append(dataframe['cti'] < self.buy_28_cti.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_28'] = True

        # Buy Condition #29
        dataframe.loc[:,'buy_condition_29'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_29_enable']:
            # Non-Standard protections (add below)

            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[28]))
            item_buy_logic.append(dataframe['moderi_64'] == True)
            item_buy_logic.append(dataframe['close'] < dataframe['hull_75'] * self.buy_29_ma_offset.value)
            item_buy_logic.append(dataframe['ewo'] < self.buy_29_ewo.value)
            item_buy_logic.append(dataframe['cti'] < self.buy_29_cti.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_29'] = True

        # Buy Condition #30
        dataframe.loc[:,'buy_condition_30'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_30_enable']:
            # Non-Standard protections (add below)

            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[29]))
            item_buy_logic.append(dataframe['moderi_64'] == False)
            item_buy_logic.append(dataframe['close'] < dataframe['zlema_68'] * self.buy_30_ma_offset.value)
            item_buy_logic.append(dataframe['ewo'] > self.buy_30_ewo.value)
            item_buy_logic.append(dataframe['rsi'] < self.buy_30_rsi.value)
            item_buy_logic.append(dataframe['cti'] < self.buy_30_cti.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_30'] = True

        # Buy Condition #31
        dataframe.loc[:,'buy_condition_31'] = False
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_31_enable']:
            # Non-Standard protections (add below)

            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[30]))
            item_buy_logic.append(dataframe['moderi_64'] == False)
            item_buy_logic.append(dataframe['close'] < dataframe['zlema_68'] * self.buy_31_ma_offset.value )
            item_buy_logic.append(dataframe['ewo'] < self.buy_31_ewo.value)
            item_buy_logic.append(dataframe['r_480'] < self.buy_31_wr.value)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_31'] = True

        # Buy Condition #32
        dataframe.loc[:,'buy_condition_32'] = False
        # Quick mode buy
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_32_enable']:
            # Non-Standard protections (add below)

            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[31]))
            item_buy_logic.append(dataframe['moderi_32'])
            item_buy_logic.append(dataframe['moderi_64'])
            item_buy_logic.append(dataframe['moderi_96'])
            item_buy_logic.append(dataframe['cti'] < self.buy_32_cti.value)
            item_buy_logic.append(dataframe['rsi_20'] < dataframe['rsi_20'].shift(1))
            item_buy_logic.append(dataframe['rsi_4'] < self.buy_32_rsi.value)
            item_buy_logic.append(dataframe['ema_20_1h'] > dataframe['ema_25_1h'])
            item_buy_logic.append((dataframe['open'] - dataframe['close']) / dataframe['close'] < self.buy_32_dip.value)
            item_buy_logic.append(dataframe['close'] < (dataframe['sma_15'] * self.buy_32_ma_offset.value))
            item_buy_logic.append(
                ((dataframe['open'] < dataframe['ema_20_1h']) & (dataframe['low'] < dataframe['ema_20_1h'])) |
                ((dataframe['open'] > dataframe['ema_20_1h']) & (dataframe['low'] > dataframe['ema_20_1h'])))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_32'] = True

        # Buy Condition #33
        dataframe.loc[:,'buy_condition_33'] = False
        # Quick mode buy
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_33_enable']:
            # Non-Standard protections (add below)

            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[32]))
            item_buy_logic.append(dataframe['moderi_96'])
            item_buy_logic.append(dataframe['cti'] < self.buy_33_cti.value)
            item_buy_logic.append(dataframe['close'] < (dataframe['ema_13'] * self.buy_33_ma_offset.value))
            item_buy_logic.append(dataframe['ewo'] > self.buy_33_ewo.value)
            item_buy_logic.append(dataframe['rsi'] < self.buy_33_rsi.value)
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_33_volume.value))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_33'] = True

        # Buy Condition #34
        dataframe.loc[:,'buy_condition_34'] = False
        # Quick mode buy
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_34_enable']:
            # Non-Standard protections (add below)

            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[33]))
            item_buy_logic.append(dataframe['cti'] < self.buy_34_cti.value)
            item_buy_logic.append((dataframe['open'] - dataframe['close']) / dataframe['close'] < self.buy_34_dip.value)
            item_buy_logic.append(dataframe['close'] < dataframe['ema_13'] * self.buy_34_ma_offset.value)
            item_buy_logic.append(dataframe['ewo'] < self.buy_34_ewo.value)
            item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_34_volume.value))
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_34'] = True

        # Buy Condition #35
        # PMAX0 buy
        # -----------------------------------------------------------------------------------------
        dataframe.loc[:,'buy_condition_35'] = False
        if self.buy_params['buy_condition_35_enable']:
            # Non-Standard protections (add below)

            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[34]))
            item_buy_logic.append(dataframe['pm'] <= dataframe['pmax_thresh'])
            item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * 0.98)
            item_buy_logic.append(dataframe['ewo'] > 8.2)
            item_buy_logic.append(dataframe['rsi'] < 32.0)
            item_buy_logic.append(dataframe['cti'] < -0.5)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_35'] = True

        # Buy Condition #36
        dataframe.loc[:,'buy_condition_36'] = False
        # PMAX1 buy
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_36_enable']:
            # Non-Standard protections (add below)

            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[35]))
            item_buy_logic.append(dataframe['pm'] <= dataframe['pmax_thresh'])
            item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * 0.98)
            item_buy_logic.append(dataframe['ewo'] < -8.0)
            item_buy_logic.append(dataframe['cti'] < -0.8)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_36'] = True

        # Buy Condition #37
        dataframe.loc[:,'buy_condition_37'] = False
        # PMAX2 buy
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_37_enable']:
            # Non-Standard protections (add below)

            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[36]))
            item_buy_logic.append(dataframe['pm'] > dataframe['pmax_thresh'])
            item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * 0.93)
            item_buy_logic.append(dataframe['ewo'] > 8.0)
            item_buy_logic.append(dataframe['rsi'] < 56.0)
            item_buy_logic.append(dataframe['cti'] < -0.84)
            item_buy_logic.append(dataframe['safe_dump_50_1h'])
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_37'] = True

        # Buy Condition #38
        dataframe.loc[:,'buy_condition_38'] = False
        # PMAX3 buy
        # -----------------------------------------------------------------------------------------
        if self.buy_params['buy_condition_38_enable']:
            # Non-Standard protections (add below)

            item_buy_logic = []
            item_buy_logic.append(reduce(lambda x, y: x & y, buy_protection_list[37]))
            item_buy_logic.append(dataframe['pm'] > dataframe['pmax_thresh'])
            item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * 0.7)
            item_buy_logic.append(dataframe['ewo'] < -2.0)
            item_buy_logic.append(dataframe['cti'] < -0.86)
            item_buy_logic.append(dataframe['volume'] > 0)
            item_buy = reduce(lambda x, y: x & y, item_buy_logic)
            conditions.append(item_buy)

            dataframe.loc[item_buy,'buy_condition_38'] = True

        if conditions:
            dataframe.loc[:, 'buy'] = reduce(lambda x, y: x | y, conditions)

        return dataframe

    def populate_sell_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'sell'] = 0
        return dataframe

    def confirm_trade_exit(self, pair: str, trade: "Trade", order_type: str, amount: float,
                           rate: float, time_in_force: str, sell_reason: str, **kwargs) -> bool:
        """
        Called right before placing a regular sell order.
        Timing for this function is critical, so avoid doing heavy computations or
        network requests in this method.

        For full documentation please go to https://www.freqtrade.io/en/latest/strategy-advanced/

        When not implemented by a strategy, returns True (always confirming).

        :param pair: Pair that's about to be sold.
        :param trade: trade object.
        :param order_type: Order type (as configured in order_types). usually limit or market.
        :param amount: Amount in quote currency.
        :param rate: Rate that's going to be used when using limit orders
        :param time_in_force: Time in force. Defaults to GTC (Good-til-cancelled).
        :param sell_reason: Sell reason.
            Can be any of ['roi', 'stop_loss', 'stoploss_on_exchange', 'trailing_stop_loss',
                           'sell_signal', 'force_sell', 'emergency_sell']
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        :return bool: When True is returned, then the sell-order is placed on the exchange.
            False aborts the process
        """
        # Just to be sure our hold data is loaded, should be a no-op call after the first bot loop
        if self.config['runmode'].value in ('live', 'dry_run'):
            self.load_hold_trades_config()

            if not self.hold_trade_ids:
                # We have no pairs we want to hold until profit, sell
                return True

            if trade.id not in self.hold_trade_ids:
                # This pair is not on the list to hold until profit, sell
                return True

            trade_profit_ratio = self.hold_trade_ids[trade.id]
            current_profit_ratio = trade.calc_profit_ratio(rate)
            if sell_reason == "force_sell":
                formatted_profit_ratio = "{}%".format(trade_profit_ratio * 100)
                formatted_current_profit_ratio = "{}%".format(current_profit_ratio * 100)
                log.warning(
                    "Force selling %s even though the current profit of %s < %s",
                    trade, formatted_current_profit_ratio, formatted_profit_ratio
                )
                return True
            elif current_profit_ratio >= trade_profit_ratio:
                # This pair is on the list to hold, and we reached minimum profit, sell
                return True

            # This pair is on the list to hold, and we haven't reached minimum profit, hold
            return False
        else:
            return True

# Elliot Wave Oscillator
def ewo(dataframe, sma1_length=5, sma2_length=35):
    df = dataframe.copy()
    sma1 = ta.EMA(df, timeperiod=sma1_length)
    sma2 = ta.EMA(df, timeperiod=sma2_length)
    smadif = (sma1 - sma2) / df['close'] * 100
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
    df = dataframe.copy()
    mfv = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low'])
    mfv = mfv.fillna(0.0)  # float division by zero
    mfv *= df['volume']
    cmf = (mfv.rolling(n, min_periods=0).sum()
           / df['volume'].rolling(n, min_periods=0).sum())
    if fillna:
        cmf = cmf.replace([np.inf, -np.inf], np.nan).fillna(0)
    return Series(cmf, name='cmf')


def tsi(dataframe: DataFrame, window_slow: int, window_fast: int, fillna=False) -> Series:
    """
    Indicator: True Strength Index (TSI)
    :param dataframe: DataFrame The original OHLC dataframe
    :param window_slow: slow smoothing period
    :param window_fast: fast smoothing period
    :param fillna: If True fill NaN values
    """
    df = dataframe.copy()

    min_periods_slow = 0 if fillna else window_slow
    min_periods_fast = 0 if fillna else window_fast

    close_diff            = df['close'].diff()
    close_diff_abs        = close_diff.abs()
    smooth_close_diff     = close_diff.ewm(span=window_slow, min_periods=min_periods_slow, adjust=False).mean().ewm(span=window_fast, min_periods=min_periods_fast, adjust=False).mean()
    smooth_close_diff_abs = close_diff_abs.ewm(span=window_slow, min_periods=min_periods_slow, adjust=False).mean().ewm(span=window_fast, min_periods=min_periods_fast, adjust=False).mean()

    tsi = smooth_close_diff / smooth_close_diff_abs * 100

    if fillna:
        tsi = tsi.replace([np.inf, -np.inf], np.nan).fillna(0)

    return tsi


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
        name="{0} Williams %R".format(period),
    )

    return WR * -100


# Volume Weighted Moving Average
def vwma(dataframe: DataFrame, length: int = 10):
    """Indicator: Volume Weighted Moving Average (VWMA)"""
    # Calculate Result
    pv = dataframe['close'] * dataframe['volume']
    vwma = Series(ta.SMA(pv, timeperiod=length) / ta.SMA(dataframe['volume'], timeperiod=length))
    return vwma


# Modified Elder Ray Index
def moderi(dataframe: DataFrame, len_slow_ma: int = 32) -> Series:
    slow_ma = Series(ta.EMA(vwma(dataframe, length=len_slow_ma), timeperiod=len_slow_ma))
    return slow_ma >= slow_ma.shift(1)  # we just need true & false for ERI trend


# zlema
def zlema(dataframe, timeperiod):
    lag =  int(math.floor((timeperiod - 1) / 2) )
    if isinstance(dataframe, Series):
        ema_data = dataframe  + (dataframe  - dataframe.shift(lag))
    else:
        ema_data = dataframe['close']  + (dataframe['close']  - dataframe['close'] .shift(lag))
    return ta.EMA(ema_data, timeperiod = timeperiod)


# zlhull
def zlhull(dataframe, timeperiod):
    lag =  int(math.floor((timeperiod - 1) / 2) )
    if isinstance(dataframe, Series):
        wma_data = dataframe + (dataframe  - dataframe.shift(lag))
    else:
        wma_data = dataframe['close'] + (dataframe['close']  - dataframe['close'] .shift(lag))

    return  ta.WMA(
        2 * ta.WMA(wma_data, int(math.floor(timeperiod/2))) - ta.WMA(wma_data, timeperiod), int(round(np.sqrt(timeperiod)))
    )


# hull
def hull(dataframe, timeperiod):
    if isinstance(dataframe, Series):
        return  ta.WMA(
            2 * ta.WMA(dataframe, int(math.floor(timeperiod/2))) - ta.WMA(dataframe, timeperiod), int(round(np.sqrt(timeperiod)))
        )
    else:
        return  ta.WMA(
            2 * ta.WMA(dataframe['close'], int(math.floor(timeperiod/2))) - ta.WMA(dataframe['close'], timeperiod), int(round(np.sqrt(timeperiod)))
        )


# PMAX
def pmax(df, period, multiplier, length, MAtype, src):

    period = int(period)
    multiplier = int(multiplier)
    length = int(length)
    MAtype = int(MAtype)
    src = int(src)

    mavalue = 'MA_' + str(MAtype) + '_' + str(length)
    atr = 'ATR_' + str(period)
    pm = 'pm_' + str(period) + '_' + str(multiplier) + '_' + str(length) + '_' + str(MAtype)
    pmx = 'pmX_' + str(period) + '_' + str(multiplier) + '_' + str(length) + '_' + str(MAtype)

    # MAtype==1 --> EMA
    # MAtype==2 --> DEMA
    # MAtype==3 --> T3
    # MAtype==4 --> SMA
    # MAtype==5 --> VIDYA
    # MAtype==6 --> TEMA
    # MAtype==7 --> WMA
    # MAtype==8 --> VWMA
    # MAtype==9 --> zema
    if src == 1:
        masrc = df["close"]
    elif src == 2:
        masrc = (df["high"] + df["low"]) / 2
    elif src == 3:
        masrc = (df["high"] + df["low"] + df["close"] + df["open"]) / 4

    if MAtype == 1:
        mavalue = ta.EMA(masrc, timeperiod=length)
    elif MAtype == 2:
        mavalue = ta.DEMA(masrc, timeperiod=length)
    elif MAtype == 3:
        mavalue = ta.T3(masrc, timeperiod=length)
    elif MAtype == 4:
        mavalue = ta.SMA(masrc, timeperiod=length)
    elif MAtype == 5:
        mavalue = VIDYA(df, length=length)
    elif MAtype == 6:
        mavalue = ta.TEMA(masrc, timeperiod=length)
    elif MAtype == 7:
        mavalue = ta.WMA(df, timeperiod=length)
    elif MAtype == 8:
        mavalue = vwma(df, length)
    elif MAtype == 9:
        mavalue = zema(df, period=length)

    df[atr] = ta.ATR(df, timeperiod=period)
    df['basic_ub'] = mavalue + ((multiplier/10) * df[atr])
    df['basic_lb'] = mavalue - ((multiplier/10) * df[atr])


    basic_ub = df['basic_ub'].values
    final_ub = np.full(len(df), 0.00)
    basic_lb = df['basic_lb'].values
    final_lb = np.full(len(df), 0.00)

    for i in range(period, len(df)):
        final_ub[i] = basic_ub[i] if (
            basic_ub[i] < final_ub[i - 1]
            or mavalue[i - 1] > final_ub[i - 1]) else final_ub[i - 1]
        final_lb[i] = basic_lb[i] if (
            basic_lb[i] > final_lb[i - 1]
            or mavalue[i - 1] < final_lb[i - 1]) else final_lb[i - 1]

    df['final_ub'] = final_ub
    df['final_lb'] = final_lb

    pm_arr = np.full(len(df), 0.00)
    for i in range(period, len(df)):
        pm_arr[i] = (
            final_ub[i] if (pm_arr[i - 1] == final_ub[i - 1]
                                    and mavalue[i] <= final_ub[i])
        else final_lb[i] if (
            pm_arr[i - 1] == final_ub[i - 1]
            and mavalue[i] > final_ub[i]) else final_lb[i]
        if (pm_arr[i - 1] == final_lb[i - 1]
            and mavalue[i] >= final_lb[i]) else final_ub[i]
        if (pm_arr[i - 1] == final_lb[i - 1]
            and mavalue[i] < final_lb[i]) else 0.00)

    pm = Series(pm_arr)

    # Mark the trend direction up/down
    pmx = np.where((pm_arr > 0.00), np.where((mavalue < pm_arr), 'down',  'up'), np.NaN)

    return pm, pmx


def calc_streaks(series: Series):
    # logic tables
    geq = series >= series.shift(1)  # True if rising
    eq = series == series.shift(1)  # True if equal
    logic_table = concat([geq, eq], axis=1)

    streaks = [0]  # holds the streak duration, starts with 0

    for row in logic_table.iloc[1:].itertuples():  # iterate through logic table
        if row[2]:  # same value as before
            streaks.append(0)
            continue
        last_value = streaks[-1]
        if row[1]:  # higher value than before
            streaks.append(last_value + 1 if last_value >=
                                             0 else 1)  # increase or reset to +1
        else:  # lower value than before
            streaks.append(last_value - 1 if last_value <
                                             0 else -1)  # decrease or reset to -1

    return streaks
