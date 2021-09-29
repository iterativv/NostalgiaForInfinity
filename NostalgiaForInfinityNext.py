import copy
import logging
import pathlib
import rapidjson
import freqtrade.vendor.qtpylib.indicators as qtpylib
import numpy as np
import talib.abstract as ta
from freqtrade.strategy.interface import IStrategy
from freqtrade.strategy import merge_informative_pair, timeframe_to_minutes
from freqtrade.exchange import timeframe_to_prev_date
from pandas import DataFrame, Series, concat
from functools import reduce
import math
from typing import Dict
from freqtrade.persistence import Trade
from datetime import datetime, timedelta
from technical.util import resample_to_interval, resampled_merge
from technical.indicators import zema, VIDYA, ichimoku
import time

log = logging.getLogger(__name__)
#log.setLevel(logging.DEBUG)


try:
    import pandas_ta as pta
except ImportError:
    log.error(
        "IMPORTANT - please install the pandas_ta python module which is needed for this strategy. "
        "If you're running Docker, add RUN pip install pandas_ta to your Dockerfile, otherwise run: "
        "pip install pandas_ta"
    )
else:
    log.info("pandas_ta successfully imported")


###########################################################################################################
##                NostalgiaForInfinityV8 by iterativ                                                     ##
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
##               HOLD SUPPORT                                                                            ##
##                                                                                                       ##
## -------- SPECIFIC TRADES ---------------------------------------------------------------------------- ##
##   In case you want to have SOME of the trades to only be sold when on profit, add a file named        ##
##   "nfi-hold-trades.json" in the user_data directory                                                   ##
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
##    * This feature can be completely disabled with the holdSupportEnabled class attribute              ##
##                                                                                                       ##
## -------- SPECIFIC PAIRS ----------------------------------------------------------------------------- ##
##   In case you want to have some pairs to always be on held until a specific profit, using the same    ##
##   "hold-trades.json" file add something like:                                                         ##
##                                                                                                       ##
##   {"trade_pairs": {"BTC/USDT": 0.001, "ETH/USDT": -0.005}}                                            ##
##                                                                                                       ##
## -------- SPECIFIC TRADES AND PAIRS ------------------------------------------------------------------ ##
##   It is also valid to include specific trades and pairs on the holds file, for example:               ##
##                                                                                                       ##
##   {"trade_ids": {"1": 0.001}, "trade_pairs": {"BTC/USDT": 0.001}}                                     ##
###########################################################################################################
##               DONATIONS                                                                               ##
##                                                                                                       ##
##   Absolutely not required. However, will be accepted as a token of appreciation.                      ##
##                                                                                                       ##
##   BTC: bc1qvflsvddkmxh7eqhc4jyu5z5k6xcw3ay8jl49sk                                                     ##
##   ETH (ERC20): 0x83D3cFb8001BDC5d2211cBeBB8cB3461E5f7Ec91                                             ##
##   BEP20/BSC (ETH, BNB, ...): 0x86A0B21a20b39d16424B7c8003E4A7e12d78ABEe                               ##
##                                                                                                       ##
##               REFERRAL LINKS                                                                          ##
##                                                                                                       ##
##  Binance: https://accounts.binance.com/en/register?ref=37365811                                       ##
##  Kucoin: https://www.kucoin.com/ucenter/signup?rcode=rJTLZ9K                                          ##
##  Huobi: https://www.huobi.com/en-us/topic/double-reward/?invite_code=ubpt2223                         ##
###########################################################################################################


class NostalgiaForInfinityNext(IStrategy):
    INTERFACE_VERSION = 2

    # ROI table:
    minimal_roi = {
        "0": 10,
    }

    stoploss = -0.50

    # Trailing stoploss (not used)
    trailing_stop = False
    trailing_only_offset_is_reached = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.03

    use_custom_stoploss = False

    # Optimal timeframe for the strategy.
    timeframe = '5m'
    res_timeframe = 'none'
    info_timeframe_1h = '1h'
    info_timeframe_1d = '1d'

    # BTC informative
    has_BTC_base_tf = False
    has_BTC_info_tf = True
    has_BTC_daily_tf = False

    # Backtest Age Filter emulation
    has_bt_agefilter = False
    bt_min_age_days = 3

    # Exchange Downtime protection
    has_downtime_protection = False

    # Do you want to use the hold feature? (with hold-trades.json)
    holdSupportEnabled = True

    # Coin Metrics
    coin_metrics = {}
    coin_metrics['top_traded_enabled'] = False
    coin_metrics['top_traded_updated'] = False
    coin_metrics['top_traded_len'] = 10
    coin_metrics['tt_dataframe'] = DataFrame()
    coin_metrics['top_grossing_enabled'] = False
    coin_metrics['top_grossing_updated'] = False
    coin_metrics['top_grossing_len'] = 20
    coin_metrics['tg_dataframe'] = DataFrame()
    coin_metrics['current_whitelist'] = []

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
        "buy_condition_35_enable": False,
        "buy_condition_36_enable": False,
        "buy_condition_37_enable": True,
        "buy_condition_38_enable": True,
        "buy_condition_39_enable": True,
        "buy_condition_40_enable": True,
        "buy_condition_41_enable": True,
        "buy_condition_42_enable": True,
        "buy_condition_43_enable": True,
        "buy_condition_44_enable": True,
        "buy_condition_45_enable": True,
        "buy_condition_46_enable": True,
        "buy_condition_47_enable": True,
        "buy_condition_48_enable": True,
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

    profit_target_params = {
        #############
        # Enable/Disable conditions
        "profit_target_1_enable": False,
        #############
    }

    #############################################################

    buy_protection_params = {
        1: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "26",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "28",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : False,
            "safe_pump_type"            : "70",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        2: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "20",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "48",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : False,
            "safe_pump_type"            : "20",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.4
        },
        3: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "100",
            "ema_slow"                  : False,
            "ema_slow_len"              : "100",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump"                 : True,
            "safe_pump_type"            : "110",
            "safe_pump_period"          : "36",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        4: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "20",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : False,
            "safe_pump_type"            : "110",
            "safe_pump_period"          : "48",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        5: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "100",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "100",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "36",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        6: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "100",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "36",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        7: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "100",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "80",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        8: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "12",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : True,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "36",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "20",
            "safe_dips_threshold_0"     : 0.016,
            "safe_dips_threshold_2"     : 0.11,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.05
        },
        9: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "100",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump"                 : False,
            "safe_pump_type"            : "100",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.1
        },
        10: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "35",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.016,
            "safe_dips_threshold_2"     : 0.11,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.6
        },
        11: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "20",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : 0.022,
            "safe_dips_threshold_2"     : 0.18,
            "safe_dips_threshold_12"    : 0.34,
            "safe_dips_threshold_144"   : 0.56,
            "safe_pump"                 : False,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "36",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        12: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.3
        },
        13: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : False,
            "safe_pump_type"            : "50",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        14: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : True,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : False,
            "safe_pump_type"            : "100",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.5
        },
        15: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "80",
            "safe_pump_period"          : "36",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        16: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "50",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.027,
            "safe_dips_threshold_2"     : 0.26,
            "safe_dips_threshold_12"    : 0.44,
            "safe_dips_threshold_144"   : 0.84,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        17: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : False,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        18: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "100",
            "ema_slow"                  : True,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : True,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : True,
            "sma200_rising_val"         : "44",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "72",
            "safe_dips_threshold_0"     : 0.026,
            "safe_dips_threshold_2"     : 0.24,
            "safe_dips_threshold_12"    : 0.42,
            "safe_dips_threshold_144"   : 0.8,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        19: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "100",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "36",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : False,
            "safe_pump_type"            : "50",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        20: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump"                 : False,
            "safe_pump_type"            : "50",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        21: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.025,
            "safe_dips_threshold_2"     : 0.23,
            "safe_dips_threshold_12"    : 0.4,
            "safe_dips_threshold_144"   : 0.7,
            "safe_pump"                 : False,
            "safe_pump_type"            : "50",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        22: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "110",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.6
        },
        23: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "15",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : True,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.022,
            "safe_dips_threshold_2"     : 0.1,
            "safe_dips_threshold_12"    : 0.3,
            "safe_dips_threshold_144"   : 0.84,
            "safe_pump"                 : True,
            "safe_pump_type"            : "100",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        24: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : 0.016,
            "safe_dips_threshold_2"     : 0.11,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump"                 : False,
            "safe_pump_type"            : "10",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        25: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "100",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "50",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "20",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : 0.024,
            "safe_dips_threshold_2"     : 0.22,
            "safe_dips_threshold_12"    : 0.38,
            "safe_dips_threshold_144"   : 0.66,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "pivot", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.98,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.4
        },
        26: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "100",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.016,
            "safe_dips_threshold_2"     : 0.1,
            "safe_dips_threshold_12"    : 0.11,
            "safe_dips_threshold_144"   : 0.22,
            "safe_pump"                 : True,
            "safe_pump_type"            : "100",
            "safe_pump_period"          : "36",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.35
        },
        27: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "100",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "50",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "50",
            "safe_pump_period"          : "36",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        28: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "50",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "36",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.99,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.32
        },
        29: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "100",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "50",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump"                 : False,
            "safe_pump_type"            : "110",
            "safe_pump_period"          : "36",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "pivot", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.01
        },
        30: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump"                 : False,
            "safe_pump_type"            : "110",
            "safe_pump_period"          : "36",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        31: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "100",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "50",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "100",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.02,
            "safe_dips_threshold_2"     : 0.14,
            "safe_dips_threshold_12"    : 0.32,
            "safe_dips_threshold_144"   : 0.5,
            "safe_pump"                 : False,
            "safe_pump_type"            : "10",
            "safe_pump_period"          : "48",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "sup3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.98,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        32: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "50",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "100",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "80",
            "safe_pump_period"          : "48",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        33: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "50",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "100",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        34: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "100",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "50",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "100",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : False,
            "safe_pump_type"            : "10",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.99,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        35: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "50",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "100",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.1
        },
        36: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "100",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "50",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "100",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump"                 : False,
            "safe_pump_type"            : "10",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        37: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "100",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "48",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.5
        },
        38: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "100",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "50",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "100",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : False,
            "safe_pump_type"            : "10",
            "safe_pump_period"          : "36",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        39: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "100",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "100",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "20",
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump"                 : False,
            "safe_pump_type"            : "50",
            "safe_pump_period"          : "48",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        40: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : True,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "20",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : True,
            "safe_pump_type"            : "100",
            "safe_pump_period"          : "48",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.2
        },
        41: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "20",
            "safe_dips_threshold_0"     : 0.015,
            "safe_dips_threshold_2"     : 0.1,
            "safe_dips_threshold_12"    : 0.24,
            "safe_dips_threshold_144"   : 0.42,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        42: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "20",
            "safe_dips_threshold_0"     : 0.027,
            "safe_dips_threshold_2"     : 0.26,
            "safe_dips_threshold_12"    : 0.44,
            "safe_dips_threshold_144"   : 0.84,
            "safe_pump"                 : True,
            "safe_pump_type"            : "10",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        43: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "20",
            "safe_dips_threshold_0"     : 0.024,
            "safe_dips_threshold_2"     : 0.22,
            "safe_dips_threshold_12"    : 0.38,
            "safe_dips_threshold_144"   : 0.66,
            "safe_pump"                 : False,
            "safe_pump_type"            : "100",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        44: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "20",
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump"                 : False,
            "safe_pump_type"            : "100",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        45: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "15",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "20",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "20",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.3,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump"                 : False,
            "safe_pump_type"            : "100",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        46: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "20",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.06,
            "safe_dips_threshold_12"    : 0.25,
            "safe_dips_threshold_144"   : 0.26,
            "safe_pump"                 : False,
            "safe_pump_type"            : "100",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 2.0
        },
        47: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.025,
            "safe_dips_threshold_2"     : 0.05,
            "safe_dips_threshold_12"    : 0.25,
            "safe_dips_threshold_144"   : 0.5,
            "safe_pump"                 : True,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        48: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "12",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : True,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : True,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : True,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump"                 : False,
            "safe_pump_type"            : "120",
            "safe_pump_period"          : "24",
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0

        }
    }

    # 24 hours - level 10
    buy_pump_pull_threshold_10_24 = 2.2
    buy_pump_threshold_10_24 = 0.42
    # 36 hours - level 10
    buy_pump_pull_threshold_10_36 = 2.0
    buy_pump_threshold_10_36 = 0.58
    # 48 hours - level 10
    buy_pump_pull_threshold_10_48 = 2.0
    buy_pump_threshold_10_48 = 0.8

    # 24 hours - level 20
    buy_pump_pull_threshold_20_24 = 2.2
    buy_pump_threshold_20_24 = 0.46
    # 36 hours - level 20
    buy_pump_pull_threshold_20_36 = 2.0
    buy_pump_threshold_20_36 = 0.6
    # 48 hours - level 20
    buy_pump_pull_threshold_20_48 = 2.0
    buy_pump_threshold_20_48 = 0.81

    # 24 hours - level 30
    buy_pump_pull_threshold_30_24 = 2.2
    buy_pump_threshold_30_24 = 0.5
    # 36 hours - level 30
    buy_pump_pull_threshold_30_36 = 2.0
    buy_pump_threshold_30_36 = 0.62
    # 48 hours - level 30
    buy_pump_pull_threshold_30_48 = 2.0
    buy_pump_threshold_30_48 = 0.82

    # 24 hours - level 40
    buy_pump_pull_threshold_40_24 = 2.2
    buy_pump_threshold_40_24 = 0.54
    # 36 hours - level 40
    buy_pump_pull_threshold_40_36 = 2.0
    buy_pump_threshold_40_36 = 0.63
    # 48 hours - level 40
    buy_pump_pull_threshold_40_48 = 2.0
    buy_pump_threshold_40_48 = 0.84

    # 24 hours - level 50
    buy_pump_pull_threshold_50_24 = 1.75
    buy_pump_threshold_50_24 = 0.6
    # 36 hours - level 50
    buy_pump_pull_threshold_50_36 = 1.75
    buy_pump_threshold_50_36 = 0.64
    # 48 hours - level 50
    buy_pump_pull_threshold_50_48 = 1.75
    buy_pump_threshold_50_48 = 0.85

    # 24 hours - level 60
    buy_pump_pull_threshold_60_24 = 1.75
    buy_pump_threshold_60_24 = 0.62
    # 36 hours - level 60
    buy_pump_pull_threshold_60_36 = 1.75
    buy_pump_threshold_60_36 = 0.66
    # 48 hours - level 60
    buy_pump_pull_threshold_60_48 = 1.75
    buy_pump_threshold_60_48 = 0.9

    # 24 hours - level 70
    buy_pump_pull_threshold_70_24 = 1.75
    buy_pump_threshold_70_24 = 0.63
    # 36 hours - level 70
    buy_pump_pull_threshold_70_36 = 1.75
    buy_pump_threshold_70_36 = 0.67
    # 48 hours - level 70
    buy_pump_pull_threshold_70_48 = 1.75
    buy_pump_threshold_70_48 = 0.95

    # 24 hours - level 80
    buy_pump_pull_threshold_80_24 = 1.75
    buy_pump_threshold_80_24 = 0.64
    # 36 hours - level 80
    buy_pump_pull_threshold_80_36 = 1.75
    buy_pump_threshold_80_36 = 0.68
    # 48 hours - level 80
    buy_pump_pull_threshold_80_48 = 1.75
    buy_pump_threshold_80_48 = 1.0

    # 24 hours - level 90
    buy_pump_pull_threshold_90_24 = 1.75
    buy_pump_threshold_90_24 = 0.65
    # 36 hours - level 90
    buy_pump_pull_threshold_90_36 = 1.75
    buy_pump_threshold_90_36 = 0.69
    # 48 hours - level 90
    buy_pump_pull_threshold_90_48 = 1.75
    buy_pump_threshold_90_48 = 1.1

    # 24 hours - level 100
    buy_pump_pull_threshold_100_24 = 1.7
    buy_pump_threshold_100_24 = 0.66
    # 36 hours - level 100
    buy_pump_pull_threshold_100_36 = 1.7
    buy_pump_threshold_100_36 = 0.7
    # 48 hours - level 100
    buy_pump_pull_threshold_100_48 = 1.4
    buy_pump_threshold_100_48 = 1.6

    # 24 hours - level 110
    buy_pump_pull_threshold_110_24 = 1.7
    buy_pump_threshold_110_24 = 0.7
    # 36 hours - level 110
    buy_pump_pull_threshold_110_36 = 1.7
    buy_pump_threshold_110_36 = 0.74
    # 48 hours - level 110
    buy_pump_pull_threshold_110_48 = 1.4
    buy_pump_threshold_110_48 = 1.8

    # 24 hours - level 120
    buy_pump_pull_threshold_120_24 = 1.7
    buy_pump_threshold_120_24 = 0.78
    # 36 hours - level 120
    buy_pump_pull_threshold_120_36 = 1.7
    buy_pump_threshold_120_36 = 0.78
    # 48 hours - level 120
    buy_pump_pull_threshold_120_48 = 1.4
    buy_pump_threshold_120_48 = 2.0

    # 5 hours - level 10
    buy_dump_protection_10_5 = 0.4

    # 5 hours - level 20
    buy_dump_protection_20_5 = 0.44

    # 5 hours - level 30
    buy_dump_protection_30_5 = 0.50

    # 5 hours - level 40
    buy_dump_protection_40_5 = 0.58

    # 5 hours - level 50
    buy_dump_protection_50_5 = 0.66

    # 5 hours - level 60
    buy_dump_protection_60_5 = 0.74

    buy_1_min_inc = 0.022
    buy_1_rsi_max = 32.0
    buy_2_r_14_max = -75.0
    buy_1_mfi_max = 46.0
    buy_1_rsi_1h_min = 30.0
    buy_1_rsi_1h_max = 84.0

    buy_2_rsi_1h_diff = 39.0
    buy_2_mfi = 49.0
    buy_2_cti_max = -0.9
    buy_2_r_480_min = -95.0
    buy_2_r_480_max = -46.0
    buy_2_cti_1h_max = 0.9
    buy_2_volume = 2.0

    buy_3_bb40_bbdelta_close = 0.057
    buy_3_bb40_closedelta_close = 0.023
    buy_3_bb40_tail_bbdelta = 0.418
    buy_3_cti_max = -0.5
    buy_3_cci_36_osc_min = -0.25
    buy_3_crsi_1h_min = 20.0
    buy_3_r_480_1h_min = -48.0
    buy_3_cti_1h_max = 0.82

    buy_4_bb20_close_bblowerband = 0.98
    buy_4_bb20_volume = 10.0
    buy_4_cti_max = -0.8

    buy_5_ema_rel = 0.84
    buy_5_ema_open_mult = 0.02
    buy_5_bb_offset = 0.999
    buy_5_cti_max = -0.5
    buy_5_r_14_max = -94.0
    buy_5_rsi_14_min = 25.0
    buy_5_mfi_min = 18.0
    buy_5_crsi_1h_min = 12.0
    buy_5_volume = 1.6

    buy_6_ema_open_mult = 0.019
    buy_6_bb_offset = 0.984
    buy_6_r_14_max = -85.0
    buy_6_crsi_1h_min = 15.0
    buy_6_cti_1h_min = 0.0

    buy_7_ema_open_mult = 0.031
    buy_7_ma_offset = 0.978
    buy_7_cti_max = -0.9
    buy_7_rsi_max = 45.0

    buy_8_bb_offset = 0.986
    buy_8_r_14_max = -98.0
    buy_8_cti_1h_max = 0.95
    buy_8_r_480_1h_max = -18.0
    buy_8_volume = 1.8

    buy_9_ma_offset = 0.968
    buy_9_bb_offset = 0.982
    buy_9_mfi_max = 50.0
    buy_9_cti_max = -0.85
    buy_9_r_14_max = -94.0
    buy_9_rsi_1h_min = 20.0
    buy_9_rsi_1h_max = 88.0
    buy_9_crsi_1h_min = 21.0

    buy_10_ma_offset_high = 0.94
    buy_10_bb_offset = 0.984
    buy_10_r_14_max = -88.0
    buy_10_cti_1h_min = -0.5
    buy_10_cti_1h_max = 0.94

    buy_11_ma_offset = 0.956
    buy_11_min_inc = 0.022
    buy_11_rsi_max = 37.0
    buy_11_mfi_max = 46.0
    buy_11_cci_max = -120.0
    buy_11_r_480_max = -32.0
    buy_11_rsi_1h_min = 30.0
    buy_11_rsi_1h_max = 84.0
    buy_11_cti_1h_max = 0.91
    buy_11_r_480_1h_max = -25.0
    buy_11_crsi_1h_min = 26.0

    buy_12_ma_offset = 0.927
    buy_12_ewo_min = 2.0
    buy_12_rsi_max = 32.0
    buy_12_cti_max = -0.9

    buy_13_ma_offset = 0.99
    buy_13_cti_max = -0.92
    buy_13_ewo_max = -6.0
    buy_13_cti_1h_max = -0.88
    buy_13_crsi_1h_min = 10.0

    buy_14_ema_open_mult = 0.014
    buy_14_bb_offset = 0.989
    buy_14_ma_offset = 0.945
    buy_14_cti_max = -0.85

    buy_15_ema_open_mult = 0.0238
    buy_15_ma_offset = 0.958
    buy_15_rsi_min = 28.0
    buy_15_cti_1h_min = -0.2

    buy_16_ma_offset = 0.942
    buy_16_ewo_min = 2.0
    buy_16_rsi_max = 36.0
    buy_16_cti_max = -0.9

    buy_17_ma_offset = 0.999
    buy_17_ewo_max = -7.0
    buy_17_cti_max = -0.96
    buy_17_crsi_1h_min = 12.0
    buy_17_volume = 2.0

    buy_18_bb_offset = 0.986
    buy_18_rsi_max = 33.5
    buy_18_cti_max = -0.85
    buy_18_cti_1h_max = 0.91
    buy_18_volume = 2.0

    buy_19_rsi_1h_min = 30.0
    buy_19_chop_max = 21.3

    buy_20_rsi_14_max = 36.0
    buy_20_rsi_14_1h_max = 16.0
    buy_20_cti_max = -0.84
    buy_20_volume = 2.0

    buy_21_rsi_14_max = 14.0
    buy_21_rsi_14_1h_max = 28.0
    buy_21_cti_max = -0.902
    buy_21_volume = 2.0

    buy_22_volume = 2.0
    buy_22_bb_offset = 0.984
    buy_22_ma_offset = 0.98
    buy_22_ewo_min = 5.6
    buy_22_rsi_14_max = 36.0
    buy_22_cti_max = -0.54
    buy_22_r_480_max = -40.0
    buy_22_cti_1h_min = -0.5

    buy_23_bb_offset = 0.984
    buy_23_ewo_min = 3.4
    buy_23_rsi_14_max = 28.0
    buy_23_cti_max = -0.74
    buy_23_rsi_14_1h_max = 80.0
    buy_23_r_480_1h_min = -95.0
    buy_23_cti_1h_max = 0.92

    buy_24_rsi_14_max = 50.0
    buy_24_rsi_14_1h_min = 66.9

    buy_25_ma_offset = 0.953
    buy_25_rsi_4_max = 30.0
    buy_25_cti_max = -0.78
    buy_25_cci_max = -200.0

    buy_26_zema_low_offset = 0.9405
    buy_26_cti_max = -0.72
    buy_26_cci_max = -166.0
    buy_26_r_14_max = -98.0
    buy_26_cti_1h_max = 0.95
    buy_26_volume = 2.0

    buy_27_wr_max = -95.0
    buy_27_r_14 = -100.0
    buy_27_wr_1h_max = -90.0
    buy_27_rsi_max = 46.0
    buy_27_volume = 2.0

    buy_28_ma_offset = 0.928
    buy_28_ewo_min = 2.0
    buy_28_rsi_14_max = 33.4
    buy_28_cti_max = -0.84
    buy_28_r_14_max = -97.0
    buy_28_cti_1h_max = 0.95

    buy_29_ma_offset = 0.984
    buy_29_ewo_max = -4.2
    buy_29_cti_max = -0.96

    buy_30_ma_offset = 0.962
    buy_30_ewo_min = 6.4
    buy_30_rsi_14_max = 34.0
    buy_30_cti_max = -0.87
    buy_30_r_14_max = -97.0

    buy_31_ma_offset = 0.962
    buy_31_ewo_max = -5.2
    buy_31_r_14_max = -94.0
    buy_31_cti_max = -0.9

    buy_32_ma_offset = 0.942
    buy_32_rsi_4_max = 46.0
    buy_32_cti_max = -0.86
    buy_32_rsi_14_min = 19.0
    buy_32_crsi_1h_min = 10.0
    buy_32_crsi_1h_max = 60.0

    buy_33_ma_offset = 0.988
    buy_33_ewo_min = 9.0
    buy_33_rsi_max = 32.0
    buy_33_cti_max = -0.88
    buy_33_r_14_max = -98.0
    buy_33_cti_1h_max = 0.92
    buy_33_volume = 2.0

    buy_34_ma_offset = 0.97
    buy_34_ewo_max = -4.0
    buy_34_cti_max = -0.95
    buy_34_r_14_max = -99.9
    buy_34_crsi_1h_min = 8.0
    buy_34_volume = 2.0

    buy_35_ma_offset = 0.984
    buy_35_ewo_min = 7.8
    buy_35_rsi_max = 32.0
    buy_35_cti_max = -0.8
    buy_35_r_14_max = -95.0

    buy_36_ma_offset = 0.98
    buy_36_ewo_max = -5.0
    buy_36_cti_max = -0.82
    buy_36_r_14_max = -97.0
    buy_36_crsi_1h_min = 12.0

    buy_37_ma_offset = 0.984
    buy_37_ewo_min = 8.3
    buy_37_ewo_max = 11.1
    buy_37_rsi_14_min = 26.0
    buy_37_rsi_14_max = 46.0
    buy_37_crsi_1h_min = 12.0
    buy_37_crsi_1h_max = 56.0
    buy_37_cti_max = -0.85
    buy_37_cti_1h_max = 0.92
    buy_37_r_14_max = -97.0
    buy_37_close_1h_max = 0.1

    buy_38_ma_offset = 0.98
    buy_38_ewo_max = -4.4
    buy_38_cti_max = -0.95
    buy_38_r_14_max = -97.0
    buy_38_crsi_1h_min = 0.5

    buy_39_cti_max = -0.1
    buy_39_r_1h_max = -22.0
    buy_39_cti_1h_min = -0.1
    buy_39_cti_1h_max = 0.4

    buy_40_cci_max = -150.0
    buy_40_rsi_max = 30.0
    buy_40_r_14_max = -99.9
    buy_40_cti_max = -0.8

    buy_41_ma_offset_high = 0.95
    buy_41_cti_max = -0.95
    buy_41_cci_max = -178.0
    buy_41_ewo_1h_min = 0.5
    buy_41_r_480_1h_max = -14.0
    buy_41_crsi_1h_min = 14.0

    buy_42_ema_open_mult = 0.018
    buy_42_bb_offset = 0.992
    buy_42_ewo_1h_min = 2.8
    buy_42_cti_1h_min = -0.5
    buy_42_cti_1h_max = 0.88
    buy_42_r_480_1h_max = -12.0

    buy_43_bb40_bbdelta_close = 0.045
    buy_43_bb40_closedelta_close = 0.02
    buy_43_bb40_tail_bbdelta = 0.5
    buy_43_cti_max = -0.75
    buy_43_r_480_min = -94.0
    buy_43_cti_1h_min = -0.75
    buy_43_cti_1h_max = 0.45
    buy_43_r_480_1h_min = -80.0

    buy_44_ma_offset = 0.982
    buy_44_ewo_max = -18.0
    buy_44_cti_max = -0.73
    buy_44_crsi_1h_min = 8.0

    buy_45_bb40_bbdelta_close = 0.039
    buy_45_bb40_closedelta_close = 0.0231
    buy_45_bb40_tail_bbdelta = 0.24
    buy_45_ma_offset = 0.948
    buy_45_ewo_min = 2.0
    buy_45_ewo_1h_min = 2.0
    buy_45_cti_1h_max = 0.76
    buy_45_r_480_1h_max = -20.0

    buy_46_ema_open_mult = 0.0332
    buy_46_ewo_1h_min = 0.5
    buy_46_cti_1h_min = -0.9
    buy_46_cti_1h_max = 0.5

    buy_47_ewo_min = 3.2
    buy_47_ma_offset = 0.952
    buy_47_rsi_14_max = 46.0
    buy_47_cti_max = -0.93
    buy_47_r_14_max = -97.0
    buy_47_ewo_1h_min = 2.0
    buy_47_cti_1h_min = -0.9
    buy_47_cti_1h_max = 0.3

    buy_48_ewo_min = 8.5
    buy_48_ewo_1h_min = 14.0
    buy_48_r_480_min = -25.0
    buy_48_r_480_1h_min = -50.0
    buy_48_r_480_1h_max = -10.0
    buy_48_cti_1h_min = 0.5
    buy_48_crsi_1h_min = 10.0

    # Sell

    sell_condition_1_enable = True
    sell_condition_2_enable = True
    sell_condition_3_enable = True
    sell_condition_4_enable = True
    sell_condition_5_enable = True
    sell_condition_6_enable = True
    sell_condition_7_enable = True
    sell_condition_8_enable = True

    # 48h for pump sell checks
    sell_pump_threshold_48_1 = 0.9
    sell_pump_threshold_48_2 = 0.7
    sell_pump_threshold_48_3 = 0.5

    # 36h for pump sell checks
    sell_pump_threshold_36_1 = 0.72
    sell_pump_threshold_36_2 = 4.0
    sell_pump_threshold_36_3 = 1.0

    # 24h for pump sell checks
    sell_pump_threshold_24_1 = 0.68
    sell_pump_threshold_24_2 = 0.62
    sell_pump_threshold_24_3 = 0.88

    sell_rsi_bb_1 = 79.0

    sell_rsi_bb_2 = 80.0

    sell_rsi_main_3 = 83.0

    sell_dual_rsi_rsi_4 = 73.4
    sell_dual_rsi_rsi_1h_4 = 79.6

    sell_ema_relative_5 = 0.024
    sell_rsi_diff_5 = 4.4

    sell_rsi_under_6 = 79.0

    sell_rsi_1h_7 = 81.7

    sell_bb_relative_8 = 1.1

    # Profit over EMA200
    sell_custom_profit_bull_0 = 0.012
    sell_custom_rsi_under_bull_0 = 34.0
    sell_custom_profit_bull_1 = 0.02
    sell_custom_rsi_under_bull_1 = 35.0
    sell_custom_profit_bull_2 = 0.03
    sell_custom_rsi_under_bull_2 = 36.0
    sell_custom_profit_bull_3 = 0.04
    sell_custom_rsi_under_bull_3 = 44.0
    sell_custom_profit_bull_4 = 0.05
    sell_custom_rsi_under_bull_4 = 45.0
    sell_custom_profit_bull_5 = 0.06
    sell_custom_rsi_under_bull_5 = 49.0
    sell_custom_profit_bull_6 = 0.07
    sell_custom_rsi_under_bull_6 = 50.0
    sell_custom_profit_bull_7 = 0.08
    sell_custom_rsi_under_bull_7 = 57.0
    sell_custom_profit_bull_8 = 0.09
    sell_custom_rsi_under_bull_8 = 50.0
    sell_custom_profit_bull_9 = 0.1
    sell_custom_rsi_under_bull_9 = 46.0
    sell_custom_profit_bull_10 = 0.12
    sell_custom_rsi_under_bull_10 = 42.0
    sell_custom_profit_bull_11 = 0.20
    sell_custom_rsi_under_bull_11 = 30.0

    sell_custom_profit_bear_0 = 0.012
    sell_custom_rsi_under_bear_0 = 34.0
    sell_custom_profit_bear_1 = 0.02
    sell_custom_rsi_under_bear_1 = 35.0
    sell_custom_profit_bear_2 = 0.03
    sell_custom_rsi_under_bear_2 = 37.0
    sell_custom_profit_bear_3 = 0.04
    sell_custom_rsi_under_bear_3 = 44.0
    sell_custom_profit_bear_4 = 0.05
    sell_custom_rsi_under_bear_4 = 48.0
    sell_custom_profit_bear_5 = 0.06
    sell_custom_rsi_under_bear_5 = 50.0
    sell_custom_rsi_over_bear_5 = 78.0
    sell_custom_profit_bear_6 = 0.07
    sell_custom_rsi_under_bear_6 = 52.0
    sell_custom_rsi_over_bear_6 = 78.0
    sell_custom_profit_bear_7 = 0.08
    sell_custom_rsi_under_bear_7 = 57.0
    sell_custom_rsi_over_bear_7 = 77.0
    sell_custom_profit_bear_8 = 0.09
    sell_custom_rsi_under_bear_8 = 55.0
    sell_custom_rsi_over_bear_8 = 75.5
    sell_custom_profit_bear_9 = 0.1
    sell_custom_rsi_under_bear_9 = 46.0
    sell_custom_profit_bear_10 = 0.12
    sell_custom_rsi_under_bear_10 = 42.0
    sell_custom_profit_bear_11 = 0.20
    sell_custom_rsi_under_bear_11 = 30.0

    # Profit under EMA200
    sell_custom_under_profit_bull_0 = 0.01
    sell_custom_under_rsi_under_bull_0 = 38.0
    sell_custom_under_profit_bull_1 = 0.02
    sell_custom_under_rsi_under_bull_1 = 46.0
    sell_custom_under_profit_bull_2 = 0.03
    sell_custom_under_rsi_under_bull_2 = 47.0
    sell_custom_under_profit_bull_3 = 0.04
    sell_custom_under_rsi_under_bull_3 = 48.0
    sell_custom_under_profit_bull_4 = 0.05
    sell_custom_under_rsi_under_bull_4 = 49.0
    sell_custom_under_profit_bull_5 = 0.06
    sell_custom_under_rsi_under_bull_5 = 50.0
    sell_custom_under_profit_bull_6 = 0.07
    sell_custom_under_rsi_under_bull_6 = 52.0
    sell_custom_under_profit_bull_7 = 0.08
    sell_custom_under_rsi_under_bull_7 = 57.0
    sell_custom_under_profit_bull_8 = 0.09
    sell_custom_under_rsi_under_bull_8 = 50.0
    sell_custom_under_profit_bull_9 = 0.1
    sell_custom_under_rsi_under_bull_9 = 46.0
    sell_custom_under_profit_bull_10 = 0.12
    sell_custom_under_rsi_under_bull_10 = 42.0
    sell_custom_under_profit_bull_11 = 0.2
    sell_custom_under_rsi_under_bull_11 = 30.0

    sell_custom_under_profit_bear_0 = 0.01
    sell_custom_under_rsi_under_bear_0 = 38.0
    sell_custom_under_profit_bear_1 = 0.02
    sell_custom_under_rsi_under_bear_1 = 56.0
    sell_custom_under_profit_bear_2 = 0.03
    sell_custom_under_rsi_under_bear_2 = 57.0
    sell_custom_under_profit_bear_3 = 0.04
    sell_custom_under_rsi_under_bear_3 = 57.0
    sell_custom_under_profit_bear_4 = 0.05
    sell_custom_under_rsi_under_bear_4 = 57.0
    sell_custom_under_profit_bear_5 = 0.06
    sell_custom_under_rsi_under_bear_5 = 57.0
    sell_custom_under_rsi_over_bear_5 = 78.0
    sell_custom_under_profit_bear_6 = 0.07
    sell_custom_under_rsi_under_bear_6 = 57.0
    sell_custom_under_rsi_over_bear_6 = 78.0
    sell_custom_under_profit_bear_7 = 0.08
    sell_custom_under_rsi_under_bear_7 = 57.0
    sell_custom_under_rsi_over_bear_7 = 80.0
    sell_custom_under_profit_bear_8 = 0.09
    sell_custom_under_rsi_under_bear_8 = 50.0
    sell_custom_under_rsi_over_bear_8 = 82.0
    sell_custom_under_profit_bear_9 = 0.1
    sell_custom_under_rsi_under_bear_9 = 46.0
    sell_custom_under_profit_bear_10 = 0.12
    sell_custom_under_rsi_under_bear_10 = 42.0
    sell_custom_under_profit_bear_11 = 0.2
    sell_custom_under_rsi_under_bear_11 = 30.0

    # SMA descending
    sell_custom_dec_profit_min_1 = 0.05
    sell_custom_dec_profit_max_1 = 0.12

    # Under EMA100
    sell_custom_dec_profit_min_2 = 0.07
    sell_custom_dec_profit_max_2 = 0.16

    # Trail 1
    sell_trail_profit_min_1 = 0.03
    sell_trail_profit_max_1 = 0.05
    sell_trail_down_1 = 0.05
    sell_trail_rsi_min_1 = 10.0
    sell_trail_rsi_max_1 = 20.0

    # Trail 2
    sell_trail_profit_min_2 = 0.1
    sell_trail_profit_max_2 = 0.4
    sell_trail_down_2 = 0.03
    sell_trail_rsi_min_2 = 20.0
    sell_trail_rsi_max_2 = 50.0

    # Trail 3
    sell_trail_profit_min_3 = 0.06
    sell_trail_profit_max_3 = 0.2
    sell_trail_down_3 = 0.05

    # Trail 4
    sell_trail_profit_min_4 = 0.03
    sell_trail_profit_max_4 = 0.06
    sell_trail_down_4 = 0.02

    # Under & near EMA200, accept profit
    sell_custom_profit_under_profit_min_1 = 0.001
    sell_custom_profit_under_profit_max_1 = 0.008
    sell_custom_profit_under_rel_1 = 0.024
    sell_custom_profit_under_rsi_diff_1 = 4.4

    sell_custom_profit_under_profit_2 = 0.03
    sell_custom_profit_under_rel_2 = 0.024
    sell_custom_profit_under_rsi_diff_2 = 4.4

    # Under & near EMA200, take the loss
    sell_custom_stoploss_under_rel_1 = 0.002
    sell_custom_stoploss_under_rsi_diff_1 = 10.0

    # Long duration/recover stoploss 1
    sell_custom_stoploss_long_profit_min_1 = -0.08
    sell_custom_stoploss_long_profit_max_1 = -0.04
    sell_custom_stoploss_long_recover_1 = 0.14
    sell_custom_stoploss_long_rsi_diff_1 = 4.0

    # Long duration/recover stoploss 2
    sell_custom_stoploss_long_recover_2 = 0.06
    sell_custom_stoploss_long_rsi_diff_2 = 40.0

    # Pumped 48h 1, under EMA200
    sell_custom_pump_under_profit_min_1 = 0.04
    sell_custom_pump_under_profit_max_1 = 0.09

    # Pumped trail 1
    sell_custom_pump_trail_profit_min_1 = 0.05
    sell_custom_pump_trail_profit_max_1 = 0.07
    sell_custom_pump_trail_down_1 = 0.05
    sell_custom_pump_trail_rsi_min_1 = 20.0
    sell_custom_pump_trail_rsi_max_1 = 70.0

    # Stoploss, pumped, 48h 1
    sell_custom_stoploss_pump_max_profit_1 = 0.01
    sell_custom_stoploss_pump_min_1 = -0.02
    sell_custom_stoploss_pump_max_1 = -0.01
    sell_custom_stoploss_pump_ma_offset_1 = 0.94

    # Stoploss, pumped, 48h 1
    sell_custom_stoploss_pump_max_profit_2 = 0.025
    sell_custom_stoploss_pump_loss_2 = -0.05
    sell_custom_stoploss_pump_ma_offset_2 = 0.92

    # Stoploss, pumped, 36h 3
    sell_custom_stoploss_pump_max_profit_3 = 0.008
    sell_custom_stoploss_pump_loss_3 = -0.12
    sell_custom_stoploss_pump_ma_offset_3 = 0.88

    # Recover
    sell_custom_recover_profit_1 = 0.06
    sell_custom_recover_min_loss_1 = 0.12

    sell_custom_recover_profit_min_2 = 0.01
    sell_custom_recover_profit_max_2 = 0.05
    sell_custom_recover_min_loss_2 = 0.06
    sell_custom_recover_rsi_2 = 46.0

    # Profit for long duration trades
    sell_custom_long_profit_min_1 = 0.03
    sell_custom_long_profit_max_1 = 0.04
    sell_custom_long_duration_min_1 = 900

    # Profit Target Signal
    profit_target_1_enable = False
    #############################################################

    plot_config = {
        'main_plot': {
            'ema_12_1h': { 'color': 'rgba(200,200,100,0.4)' },
            'ema_15_1h': { 'color': 'rgba(200,180,100,0.4)' },
            'ema_20_1h': { 'color': 'rgba(200,160,100,0.4)' },
            'ema_25_1h': { 'color': 'rgba(200,140,100,0.4)' },
            'ema_26_1h': { 'color': 'rgba(200,120,100,0.4)' },
            'ema_35_1h': { 'color': 'rgba(200,100,100,0.4)' },
            'ema_50_1h': { 'color': 'rgba(200,80,100,0.4)' },
            'ema_100_1h': { 'color': 'rgba(200,60,100,0.4)' },
            'ema_200_1h': { 'color': 'rgba(200,40,100,0.4)' },
            'sma_200_1h': { 'color': 'rgba(150,20,100,0.4)' },
            'pm': { 'color': 'rgba(100,20,100,0.5)' }
        },
        'subplots': {
            'buy tag': { 'buy_tag': {'color': 'green'} },
            'RSI/BTC': {
                'btc_not_downtrend_1h': { 'color': 'yellow' },
                'btc_rsi_14_1h': { 'color': 'green' },
                'rsi_14_1h': { 'color': '#f41cd1' },
                'crsi': {'color': 'blue' }
            },
            'pump': {
                'cti_1h': {'color': 'pink' },
                'safe_pump_24_10_1h': {'color': '#481110' },
                'safe_pump_24_20_1h': {'color': '#481120' },
                'safe_pump_24_30_1h': {'color': '#481130' },
                'safe_pump_24_40_1h': {'color': '#481140' },
                'safe_pump_24_50_1h': {'color': '#481150' },
                'safe_pump_24_60_1h': {'color': '#481160' },
                'safe_pump_24_70_1h': {'color': '#481170' },
                'safe_pump_24_80_1h': {'color': '#481180' },
                'safe_pump_24_90_1h': {'color': '#481190' },
                'safe_pump_24_100_1h': {'color': '#4811A0' },
                'safe_pump_24_120_1h': {'color': '#4811C0' },
                'safe_pump_36_10_1h': {'color': '#721110' },
                'safe_pump_36_20_1h': {'color': '#721120' },
                'safe_pump_36_30_1h': {'color': '#721130' },
                'safe_pump_36_40_1h': {'color': '#721140' },
                'safe_pump_36_50_1h': {'color': '#721150' },
                'safe_pump_36_60_1h': {'color': '#721160' },
                'safe_pump_36_70_1h': {'color': '#721170' },
                'safe_pump_36_80_1h': {'color': '#721180' },
                'safe_pump_36_90_1h': {'color': '#721190' },
                'safe_pump_36_100_1h': {'color': '#7211A0' },
                'safe_pump_36_120_1h': {'color': '#7211C0' },
                'safe_pump_48_10_1h': {'color': '#961110' },
                'safe_pump_48_20_1h': {'color': '#961120' },
                'safe_pump_48_30_1h': {'color': '#961130' },
                'safe_pump_48_40_1h': {'color': '#961140' },
                'safe_pump_48_50_1h': {'color': '#961150' },
                'safe_pump_48_60_1h': {'color': '#961160' },
                'safe_pump_48_70_1h': {'color': '#961170' },
                'safe_pump_48_80_1h': {'color': '#961180' },
                'safe_pump_48_90_1h': {'color': '#961190' },
                'safe_pump_48_100_1h': {'color': '#9611A0' },
                'safe_pump_48_120_1h': {'color': '#9611C0' }
            }
        }
    }

    #############################################################
    # CACHES

    hold_trades_cache = None
    target_profit_cache = None
    #############################################################

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        if self.target_profit_cache is None:
            self.target_profit_cache = Cache(
                self.config["user_data_dir"] / "data-nfi-profit_target_by_pair.json"
            )

        # If the cached data hasn't changed, it's a no-op
        self.target_profit_cache.save()

    def get_hold_trades_config_file(self):
        proper_holds_file_path = self.config["user_data_dir"].resolve() / "nfi-hold-trades.json"
        if proper_holds_file_path.is_file():
            return proper_holds_file_path

        strat_file_path = pathlib.Path(__file__)
        hold_trades_config_file_resolve = strat_file_path.resolve().parent / "hold-trades.json"
        if hold_trades_config_file_resolve.is_file():
            log.warning(
                "Please move %s to %s which is now the expected path for the holds file",
                hold_trades_config_file_resolve,
                proper_holds_file_path,
            )
            return hold_trades_config_file_resolve

        # The resolved path does not exist, is it a symlink?
        hold_trades_config_file_absolute = strat_file_path.absolute().parent / "hold-trades.json"
        if hold_trades_config_file_absolute.is_file():
            log.warning(
                "Please move %s to %s which is now the expected path for the holds file",
                hold_trades_config_file_absolute,
                proper_holds_file_path,
            )
            return hold_trades_config_file_absolute

    def load_hold_trades_config(self):
        if self.hold_trades_cache is None:
            hold_trades_config_file = self.get_hold_trades_config_file()
            if hold_trades_config_file:
                log.warning("Loading hold support data from %s", hold_trades_config_file)
                self.hold_trades_cache = HoldsCache(hold_trades_config_file)

        if self.hold_trades_cache:
            self.hold_trades_cache.load()

    def whitelist_tracker(self):
        if sorted(self.coin_metrics['current_whitelist']) != sorted(self.dp.current_whitelist()):
            log.info("Whitelist has changed...")
            self.coin_metrics['top_traded_updated'] = False
            self.coin_metrics['top_grossing_updated'] = False

            # Update pairlist
            self.coin_metrics['current_whitelist'] = self.dp.current_whitelist()

            # Move up BTC for largest data footprint
            self.coin_metrics['current_whitelist'].insert(0, self.coin_metrics['current_whitelist'].pop(self.coin_metrics['current_whitelist'].index(f"BTC/{self.config['stake_currency']}")))

    def top_traded_list(self):
        log.info("Updating top traded pairlist...")
        tik = time.perf_counter()

        self.coin_metrics['tt_dataframe'] = DataFrame()

        # Build traded volume dataframe
        for coin_pair in self.coin_metrics['current_whitelist']:
            coin = coin_pair.split('/')[0]

            # Get the volume for the daily informative timeframe and name the column for the coin
            pair_dataframe = self.dp.get_pair_dataframe(pair=coin_pair, timeframe=self.info_timeframe_1d)
            pair_dataframe.set_index('date')

            if self.config['runmode'].value in ('live', 'dry_run'):
                pair_dataframe = pair_dataframe.iloc[-7:,:]

            # Set the date index of the self.coin_metrics['tt_dataframe'] once
            if not 'date' in self.coin_metrics['tt_dataframe']:
                self.coin_metrics['tt_dataframe']['date'] = pair_dataframe['date']
                self.coin_metrics['tt_dataframe'].set_index('date')

            # Calculate daily traded volume
            pair_dataframe[coin] = pair_dataframe['volume'] * qtpylib.typical_price(pair_dataframe)

            # Drop the columns we don't need
            pair_dataframe.drop(columns=['open', 'high', 'low', 'close', 'volume'], inplace=True)

            # Merge it in on the date key
            self.coin_metrics['tt_dataframe'] = self.coin_metrics['tt_dataframe'].merge(pair_dataframe, on='date', how='left')

        # Forward fill empty cells (due to different df shapes)
        self.coin_metrics['tt_dataframe'].fillna(0, inplace=True)

        # Store and drop date column for value sorting
        pair_dates = self.coin_metrics['tt_dataframe']['date']
        self.coin_metrics['tt_dataframe'].drop(columns=['date'], inplace=True)

        # Build columns and top traded coins
        column_names = [f"Coin #{i}" for i in range(1, self.coin_metrics['top_traded_len'] + 1)]
        self.coin_metrics['tt_dataframe'][column_names] = self.coin_metrics['tt_dataframe'].apply(lambda x: x.nlargest(self.coin_metrics['top_traded_len']).index.values, axis=1, result_type='expand')
        self.coin_metrics['tt_dataframe'].drop(columns=[col for col in self.coin_metrics['tt_dataframe'] if col not in column_names], inplace=True)

        # Re-add stored date column
        self.coin_metrics['tt_dataframe'].insert(loc = 0, column = 'date', value = pair_dates)
        self.coin_metrics['tt_dataframe'].set_index('date')
        self.coin_metrics['top_traded_updated'] = True
        log.info("Updated top traded pairlist (tail-5):")
        log.info(f"\n{self.coin_metrics['tt_dataframe'].tail(5)}")

        tok = time.perf_counter()
        log.info(f"Updating top traded pairlist took {tok - tik:0.4f} seconds...")

    def top_grossing_list(self):
        log.info("Updating top grossing pairlist...")
        tik = time.perf_counter()

        self.coin_metrics['tg_dataframe'] = DataFrame()

        # Build grossing volume dataframe
        for coin_pair in self.coin_metrics['current_whitelist']:
            coin = coin_pair.split('/')[0]

            # Get the volume for the daily informative timeframe and name the column for the coin
            pair_dataframe = self.dp.get_pair_dataframe(pair=coin_pair, timeframe=self.info_timeframe_1d)
            pair_dataframe.set_index('date')

            if self.config['runmode'].value in ('live', 'dry_run'):
                pair_dataframe = pair_dataframe.iloc[-7:,:]

            # Set the date index of the self.coin_metrics['tg_dataframe'] once
            if not 'date' in self.coin_metrics['tg_dataframe']:
                self.coin_metrics['tg_dataframe']['date'] = pair_dataframe['date']
                self.coin_metrics['tg_dataframe'].set_index('date')

            # Calculate daily grossing rate
            pair_dataframe[coin] = pair_dataframe['close'].pct_change() * 100

            # Drop the columns we don't need
            pair_dataframe.drop(columns=['open', 'high', 'low', 'close', 'volume'], inplace=True)

            # Merge it in on the date key
            self.coin_metrics['tg_dataframe'] = self.coin_metrics['tg_dataframe'].merge(pair_dataframe, on='date', how='left')

        # Forward fill empty cells (due to different df shapes)
        self.coin_metrics['tg_dataframe'].fillna(0, inplace=True)

        self.coin_metrics['tg_dataframe'].to_html('pct_df.html')

        # Store and drop date column for value sorting
        pair_dates = self.coin_metrics['tg_dataframe']['date']
        self.coin_metrics['tg_dataframe'].drop(columns=['date'], inplace=True)

        # Build columns and top grossing coins
        column_names = [f"Coin #{i}" for i in range(1, self.coin_metrics['top_grossing_len'] + 1)]
        self.coin_metrics['tg_dataframe'][column_names] = self.coin_metrics['tg_dataframe'].apply(lambda x: x.nlargest(self.coin_metrics['top_grossing_len']).index.values, axis=1, result_type='expand')
        self.coin_metrics['tg_dataframe'].drop(columns=[col for col in self.coin_metrics['tg_dataframe'] if col not in column_names], inplace=True)

        # Re-add stored date column
        self.coin_metrics['tg_dataframe'].insert(loc = 0, column = 'date', value = pair_dates)
        self.coin_metrics['tg_dataframe'].set_index('date')
        self.coin_metrics['top_grossing_updated'] = True
        log.info("Updated top grossing pairlist (tail-5):")
        log.info(f"\n{self.coin_metrics['tg_dataframe'].tail(5)}")

        tok = time.perf_counter()
        log.info(f"Updating top grossing pairlist took {tok - tik:0.4f} seconds...")

    def is_top_coin(self, coin_pair, row_data, top_length) -> bool:
        return coin_pair.split('/')[0] in row_data.loc['Coin #1':f"Coin #{top_length}"].values

    def bot_loop_start(self, **kwargs) -> None:
        """
        Called at the start of the bot iteration (one loop).
        Might be used to perform pair-independent tasks
        (e.g. gather some remote resource for comparison)
        :param **kwargs: Ensure to keep this here so updates to this won't break your strategy.
        """

        # Coin metrics mechanism
        if self.coin_metrics['top_traded_enabled'] or self.coin_metrics['top_grossing_enabled']:
            self.whitelist_tracker()
        if self.coin_metrics['top_traded_enabled'] and not self.coin_metrics['top_traded_updated']:
            self.top_traded_list()
        if self.coin_metrics['top_grossing_enabled'] and not self.coin_metrics['top_grossing_updated']:
            self.top_grossing_list()

        if self.config["runmode"].value not in ("live", "dry_run"):
            return super().bot_loop_start(**kwargs)

        if self.holdSupportEnabled:
            self.load_hold_trades_config()

        return super().bot_loop_start(**kwargs)

    def get_ticker_indicator(self):
        return int(self.timeframe[:-1])

    def sell_over_main(self, current_profit: float, last_candle) -> tuple:
        if last_candle['close'] > last_candle['ema_200']:
            if (last_candle['moderi_96']):
                if current_profit >= 0.20:
                    if last_candle['rsi_14'] < 30.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_12_1'
                    elif (last_candle['rsi_14'] < 27.0):
                        return True, 'signal_profit_o_bull_12_9'
                elif 0.20 > current_profit >= 0.12:
                    if last_candle['rsi_14'] < 42.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_11_1'
                    elif (last_candle['rsi_14'] < 39.0):
                        return True, 'signal_profit_o_bull_11_9'
                elif 0.12 > current_profit >= 0.1:
                    if last_candle['rsi_14'] < 46.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_10_1'
                    elif (last_candle['rsi_14'] < 48.0):
                        return True, 'signal_profit_o_bull_10_9'
                elif 0.1 > current_profit >= 0.09:
                    if last_candle['rsi_14'] < 50.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_9_1'
                    elif (last_candle['rsi_14'] < 49.0):
                        return True, 'signal_profit_o_bull_9_9'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 57.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_8_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bull_8_3'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bull_8_4'
                    elif (last_candle['rsi_14'] < 48.0):
                        return True, 'signal_profit_o_bull_8_9'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_7_1'
                    if last_candle['rsi_14'] > 83.0 and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bull_7_2'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bull_7_3'
                    elif (last_candle['rsi_14'] < 55.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bull_7_4'
                    elif (last_candle['rsi_14'] < 45.0):
                        return True, 'signal_profit_o_bull_7_9'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_6_1'
                    if last_candle['rsi_14'] > 82.0 and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bull_6_2'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bull_6_3'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bull_6_4'
                    elif (last_candle['cti'] > 0.95):
                        return True, 'signal_profit_o_bull_6_5'
                    elif (last_candle['rsi_14'] < 42.0):
                        return True, 'signal_profit_o_bull_6_9'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_5_1'
                    if last_candle['rsi_14'] > 80.0 and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bull_5_2'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bull_5_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bull_5_4'
                    elif (last_candle['cti'] > 0.952):
                        return True, 'signal_profit_o_bull_5_5'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_5_6'
                    elif (last_candle['rsi_14'] < 41.0):
                        return True, 'signal_profit_o_bull_5_9'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_4_1'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bull_4_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bull_4_4'
                    elif (last_candle['cti'] > 0.954):
                        return True, 'signal_profit_o_bull_4_5'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_4_6'
                    elif (last_candle['rsi_14'] < 40.0):
                        return True, 'signal_profit_o_bull_4_9'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_3_1'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bull_3_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bull_3_4'
                    elif (last_candle['cti'] > 0.956):
                        return True, 'signal_profit_o_bull_3_5'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_3_6'
                    elif (last_candle['rsi_14'] < 35.0):
                        return True, 'signal_profit_o_bull_3_9'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_2_1'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bull_2_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bull_2_4'
                    elif (last_candle['cti'] > 0.958):
                        return True, 'signal_profit_o_bull_2_5'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_2_6'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf_1h'] < -0.05) and (last_candle['cti_1h'] > 0.85):
                        return True, 'signal_profit_o_bull_2_7'
                    elif last_candle['rsi_14'] < 40.0 and (last_candle['cmf'] < -0.25):
                        return True, 'signal_profit_o_bull_2_8'
                    elif (last_candle['rsi_14'] < 34.0):
                        return True, 'signal_profit_o_bull_2_9'
                elif 0.02 > current_profit >= 0.012:
                    if (last_candle['rsi_14'] < 34.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_1_1'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bull_1_3'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bull_1_4'
                    elif (last_candle['cti'] > 0.96):
                        return True, 'signal_profit_o_bull_1_5'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bull_1_6'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf_1h'] < -0.05) and (last_candle['cti_1h'] > 0.85):
                        return True, 'signal_profit_o_bull_1_7'
                    elif last_candle['rsi_14'] < 39.0 and (last_candle['cmf'] < -0.25):
                        return True, 'signal_profit_o_bull_1_8'
                    elif (last_candle['rsi_14'] < 32.0):
                        return True, 'signal_profit_o_bull_1_9'
            else:
                if current_profit >= 0.20:
                    if last_candle['rsi_14'] < 30.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_12_1'
                    elif (last_candle['rsi_14'] < 28.0):
                        return True, 'signal_profit_o_bear_12_9'
                elif 0.20 > current_profit >= 0.12:
                    if last_candle['rsi_14'] < 42.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_11_1'
                    elif (last_candle['rsi_14'] < 40.0):
                        return True, 'signal_profit_o_bear_11_9'
                elif 0.12 > current_profit >= 0.10:
                    if last_candle['rsi_14'] < 46.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_10_1'
                    elif (last_candle['rsi_14'] < 49.0):
                        return True, 'signal_profit_o_bear_10_9'
                elif 0.10 > current_profit >= 0.09:
                    if last_candle['rsi_14'] < 55.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_9_1'
                    elif (last_candle['rsi_14'] > 75.5):
                        return True, 'signal_profit_o_bear_9_2'
                    elif (last_candle['rsi_14'] < 50.0):
                        return True, 'signal_profit_o_bear_9_9'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 57.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_8_1'
                    elif (last_candle['rsi_14'] > 77.0):
                        return True, 'signal_profit_o_bear_8_2'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bear_8_3'
                    elif (last_candle['rsi_14'] < 59.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bear_8_4'
                    elif (last_candle['rsi_14'] < 49.0):
                        return True, 'signal_profit_o_bear_8_9'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_7_1'
                    elif (last_candle['rsi_14'] > 78.0):
                        return True, 'signal_profit_o_bear_7_2'
                    elif (last_candle['rsi_14'] < 55.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bear_7_3'
                    elif (last_candle['rsi_14'] < 57.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bear_7_4'
                    elif (last_candle['rsi_14'] < 46.0):
                        return True, 'signal_profit_o_bear_7_9'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_6_1'
                    elif (last_candle['rsi_14'] > 78.0):
                        return True, 'signal_profit_o_bear_6_2'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bear_6_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bear_6_4'
                    elif (last_candle['cti'] > 0.94):
                        return True, 'signal_profit_o_bear_6_5'
                    elif (last_candle['rsi_14'] < 43.0):
                        return True, 'signal_profit_o_bear_6_9'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_5_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bear_5_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bear_5_4'
                    elif (last_candle['cti'] > 0.942):
                        return True, 'signal_profit_o_bear_5_5'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_5_6'
                    elif (last_candle['rsi_14'] < 42.0):
                        return True, 'signal_profit_o_bear_5_9'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_4_1'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bear_4_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bear_4_4'
                    elif (last_candle['cti'] > 0.944):
                        return True, 'signal_profit_o_bear_4_5'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_4_6'
                    elif (last_candle['rsi_14'] < 41.0):
                        return True, 'signal_profit_o_bear_4_9'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_3_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bear_3_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bear_3_4'
                    elif (last_candle['cti'] > 0.946):
                        return True, 'signal_profit_o_bear_3_5'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_3_6'
                    elif (last_candle['rsi_14'] < 36.0):
                        return True, 'signal_profit_o_bear_3_9'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_2_1'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_o_bear_2_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bear_2_4'
                    elif (last_candle['cti'] > 0.948):
                        return True, 'signal_profit_o_bear_2_5'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_2_6'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf_1h'] < -0.05) and (last_candle['cti_1h'] > 0.85):
                        return True, 'signal_profit_o_bear_2_7'
                    elif (last_candle['rsi_14'] < 35.0):
                        return True, 'signal_profit_o_bear_2_9'
                elif 0.02 > current_profit >= 0.012:
                    if (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_1_1'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_o_bear_1_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_o_bear_1_4'
                    elif (last_candle['cti'] > 0.95):
                        return True, 'signal_profit_o_bear_1_5'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_o_bear_1_6'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf_1h'] < -0.05) and (last_candle['cti_1h'] > 0.85):
                        return True, 'signal_profit_o_bear_1_7'
                    elif (last_candle['rsi_14'] < 33.0):
                        return True, 'signal_profit_o_bear_1_9'

        return False, None

    def sell_under_main(self, current_profit: float, last_candle) -> tuple:
        if last_candle['close'] < last_candle['ema_200']:
            if (last_candle['moderi_96']):
                if current_profit >= 0.20:
                    if last_candle['rsi_14'] < 30.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_12_1'
                    elif (last_candle['rsi_14'] < 28.0):
                        return True, 'signal_profit_u_bull_12_9'
                elif 0.20 > current_profit >= 0.12:
                    if last_candle['rsi_14'] < 42.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_11_1'
                    elif (last_candle['rsi_14'] < 43.0):
                        return True, 'signal_profit_u_bull_11_9'
                elif 0.12 > current_profit >= 0.10:
                    if last_candle['rsi_14'] < 46.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_10_1'
                    elif (last_candle['rsi_14'] < 49.0):
                        return True, 'signal_profit_u_bull_10_9'
                elif 0.10 > current_profit >= 0.09:
                    if last_candle['rsi_14'] < 50.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_9_1'
                    elif (last_candle['rsi_14'] < 50.0):
                        return True, 'signal_profit_u_bull_9_9'
                elif 0.09 > current_profit >= 0.08:
                    if last_candle['rsi_14'] < 57.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_8_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_u_bull_8_3'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bull_8_4'
                    elif (last_candle['rsi_14'] < 49.0):
                        return True, 'signal_profit_u_bull_8_9'
                elif 0.08 > current_profit >= 0.07:
                    if last_candle['rsi_14'] < 52.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_7_1'
                    if last_candle['rsi_14'] > 83.0 and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bull_7_2'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_u_bull_7_3'
                    elif (last_candle['rsi_14'] < 55.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bull_7_4'
                    elif (last_candle['rsi_14'] < 46.0):
                        return True, 'signal_profit_u_bull_7_9'
                elif 0.07 > current_profit >= 0.06:
                    if last_candle['rsi_14'] < 50.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_6_1'
                    if last_candle['rsi_14'] > 82.0 and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bull_6_2'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_u_bull_6_3'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bull_6_4'
                    elif (last_candle['cti'] > 0.95):
                        return True, 'signal_profit_u_bull_6_5'
                    elif (last_candle['rsi_14'] < 43.0):
                        return True, 'signal_profit_u_bull_6_9'
                elif 0.06 > current_profit >= 0.05:
                    if last_candle['rsi_14'] < 48.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_5_1'
                    if last_candle['rsi_14'] > 80.0 and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bull_5_2'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_u_bull_5_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bull_5_4'
                    elif (last_candle['cti'] > 0.952):
                        return True, 'signal_profit_u_bull_5_5'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_5_6'
                    elif (last_candle['rsi_14'] < 42.0):
                        return True, 'signal_profit_u_bull_5_9'
                elif 0.05 > current_profit >= 0.04:
                    if last_candle['rsi_14'] < 47.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_4_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_u_bull_4_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bull_4_4'
                    elif (last_candle['cti'] > 0.954):
                        return True, 'signal_profit_u_bull_4_5'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_4_6'
                    elif (last_candle['rsi_14'] < 41.0):
                        return True, 'signal_profit_u_bull_4_9'
                elif 0.04 > current_profit >= 0.03:
                    if last_candle['rsi_14'] < 46.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_3_1'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_u_bull_3_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bull_3_4'
                    elif (last_candle['cti'] > 0.956):
                        return True, 'signal_profit_u_bull_3_5'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_3_6'
                    elif (last_candle['rsi_14'] < 36.0):
                        return True, 'signal_profit_u_bull_3_9'
                elif 0.03 > current_profit >= 0.02:
                    if last_candle['rsi_14'] < 45.0 and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_2_1'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_u_bull_2_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bull_2_4'
                    elif (last_candle['cti'] > 0.958):
                        return True, 'signal_profit_u_bull_2_5'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_2_6'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf_1h'] < -0.05) and (last_candle['cti_1h'] > 0.85):
                        return True, 'signal_profit_u_bull_2_7'
                    elif last_candle['rsi_14'] < 41.0 and (last_candle['cmf'] < -0.25):
                        return True, 'signal_profit_u_bull_2_8'
                    elif (last_candle['rsi_14'] < 35.0):
                        return True, 'signal_profit_u_bull_2_9'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_1_1'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.4):
                        return True, 'signal_profit_u_bull_1_3'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bull_1_4'
                    elif (last_candle['cti'] > 0.96):
                        return True, 'signal_profit_u_bull_1_5'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bull_1_6'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf_1h'] < -0.05) and (last_candle['cti_1h'] > 0.85):
                        return True, 'signal_profit_u_bull_1_7'
                    elif last_candle['rsi_14'] < 40.0 and (last_candle['cmf'] < -0.25):
                        return True, 'signal_profit_u_bull_1_8'
                    elif (last_candle['rsi_14'] < 33.0):
                        return True, 'signal_profit_u_bull_1_9'
            else:
                if current_profit >= 0.20:
                    if last_candle['rsi_14'] < 30.0:
                        return True, 'signal_profit_u_bear_12_1'
                elif 0.20 > current_profit >= 0.12:
                    if last_candle['rsi_14'] < 42.0:
                        return True, 'signal_profit_u_bear_11_1'
                elif 0.12 > current_profit >= 0.10:
                    if last_candle['rsi_14'] < 46.0:
                        return True, 'signal_profit_u_bear_10_1'
                elif 0.10 > current_profit >= 0.09:
                    if last_candle['rsi_14'] < 50.0:
                        return True, 'signal_profit_u_bear_9_1'
                    elif (last_candle['rsi_14'] > 82.0):
                        return True, 'signal_profit_u_bear_9_2'
                elif 0.09 > current_profit >= 0.08:
                    if last_candle['rsi_14'] < 57.0:
                        return True, 'signal_profit_u_bear_8_1'
                    elif (last_candle['rsi_14'] > 80.0):
                        return True, 'signal_profit_u_bear_8_2'
                elif 0.08 > current_profit >= 0.07:
                    if last_candle['rsi_14'] < 56.0:
                        return True, 'signal_profit_u_bear_7_1'
                    elif (last_candle['rsi_14'] > 78.0):
                        return True, 'signal_profit_u_bear_7_2'
                elif 0.07 > current_profit >= 0.06:
                    if last_candle['rsi_14'] < 54.0:
                        return True, 'signal_profit_u_bear_6_1'
                    elif (last_candle['rsi_14'] > 78.0):
                        return True, 'signal_profit_u_bear_6_2'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_u_bear_6_3'
                    elif (last_candle['cti'] > 0.94):
                        return True, 'signal_profit_u_bear_6_5'
                elif 0.06 > current_profit >= 0.05:
                    if last_candle['rsi_14'] < 52.0:
                        return True, 'signal_profit_u_bear_5_1'
                    elif (last_candle['rsi_14'] < 57.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_u_bear_5_3'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bear_5_4'
                    elif (last_candle['cti'] > 0.942):
                        return True, 'signal_profit_u_bear_5_5'
                    elif (last_candle['rsi_14'] < 57.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bear_5_6'
                elif 0.05 > current_profit >= 0.04:
                    if last_candle['rsi_14'] < 50.0:
                        return True, 'signal_profit_u_bear_4_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.05):
                        return True, 'signal_profit_u_bear_4_3'
                    elif (last_candle['rsi_14'] < 57.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bear_4_4'
                    elif (last_candle['cti'] > 0.944):
                        return True, 'signal_profit_u_bear_4_5'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bear_4_6'
                elif 0.04 > current_profit >= 0.03:
                    if last_candle['rsi_14'] < 48.0:
                        return True, 'signal_profit_u_bear_3_1'
                    elif (last_candle['rsi_14'] < 55.0) and (last_candle['cmf'] < -0.05):
                        return True, 'signal_profit_u_bear_3_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bear_3_4'
                    elif (last_candle['cti'] > 0.946):
                        return True, 'signal_profit_u_bear_3_5'
                    elif (last_candle['rsi_14'] < 55.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bear_3_6'
                elif 0.03 > current_profit >= 0.02:
                    if last_candle['rsi_14'] < 55.0: #46
                        return True, 'signal_profit_u_bear_2_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.05):
                        return True, 'signal_profit_u_bear_2_3'
                    elif (last_candle['rsi_14'] < 55.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bear_2_4'
                    elif (last_candle['cti'] > 0.948):
                        return True, 'signal_profit_u_bear_2_5'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bear_2_6'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf_1h'] < -0.05) and (last_candle['cti_1h'] > 0.85):
                        return True, 'signal_profit_u_bear_2_7'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bear_1_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.05):
                        return True, 'signal_profit_u_bear_1_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0.0):
                        return True, 'signal_profit_u_bear_1_4'
                    elif (last_candle['cti'] > 0.95):
                        return True, 'signal_profit_u_bear_1_5'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_u_bear_1_6'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf_1h'] < -0.05) and (last_candle['cti_1h'] > 0.85):
                        return True, 'signal_profit_u_bear_1_7'
                    elif (last_candle['rsi_14'] < 34.0):
                        return True, 'signal_profit_u_bear_1_9'

        return False, None

    def sell_pump_main(self, current_profit: float, last_candle) -> tuple:
        if last_candle['sell_pump_48_1_1h']:
            if (last_candle['moderi_96']):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 30.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 42.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 46.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 50.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 57.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bull_48_6_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_48_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bull_48_5_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_48_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bull_48_4_3'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_48_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_3_1'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bull_48_3_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_48_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_2_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bull_48_2_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_48_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_48_1_1'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bull_48_1_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_48_1_4'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 30.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 42.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 46.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 50.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 57.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 53.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bear_48_6_3'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_48_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bear_48_5_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_48_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bear_48_4_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_48_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_3_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bear_48_3_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_48_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_2_1'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bear_48_2_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_48_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_48_1_1'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.12):
                        return True, 'signal_profit_p_bear_48_1_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_48_1_4'

        elif last_candle['sell_pump_36_1_1h']:
            if (last_candle['moderi_96']):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 30.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 42.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 46.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 50.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 57.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bull_36_6_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_36_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bull_36_5_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_36_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bull_36_4_3'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_36_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_3_1'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bull_36_3_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_36_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_2_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bull_36_2_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_36_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_36_1_1'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bull_36_1_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_36_1_4'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 30.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 42.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 46.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 50.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 57.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 53.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bear_36_6_3'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_36_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bear_36_5_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_36_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bear_36_4_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_36_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_3_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bear_36_3_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_36_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_2_1'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bear_36_2_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_36_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_36_1_1'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.2):
                        return True, 'signal_profit_p_bear_36_1_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_36_1_4'

        elif last_candle['sell_pump_24_1_1h']:
            if (last_candle['moderi_96']):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 30.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 42.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 46.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 50.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 57.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bull_24_6_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_24_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bull_24_5_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_24_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bull_24_4_3'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_24_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_3_1'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bull_24_3_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_24_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_2_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bull_24_2_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_24_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bull_24_1_1'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bull_24_1_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bull_24_1_4'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 30.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 42.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 46.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 50.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 57.5) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 53.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bear_24_6_3'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_24_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bear_24_5_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_24_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bear_24_4_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_24_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_3_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bear_24_3_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_24_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_2_1'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bear_24_2_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_24_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < 0.0):
                        return True, 'signal_profit_p_bear_24_1_1'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.3):
                        return True, 'signal_profit_p_bear_24_1_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'signal_profit_p_bear_24_1_4'

        return False, None

    def sell_dec_main(self, current_profit: float, last_candle) -> tuple:
        if (self.sell_custom_dec_profit_max_1 > current_profit >= self.sell_custom_dec_profit_min_1) and (last_candle['sma_200_dec_20']):
            return True, 'signal_profit_d_1'
        elif (self.sell_custom_dec_profit_max_2 > current_profit >= self.sell_custom_dec_profit_min_2) and (last_candle['close'] < last_candle['ema_100']):
            return True, 'signal_profit_d_2'

        return False, None

    def sell_trail_main(self, current_profit: float, last_candle, max_profit: float) -> tuple:
        if (self.sell_trail_profit_max_1 > current_profit >= self.sell_trail_profit_min_1) and (self.sell_trail_rsi_min_1 < last_candle['rsi_14'] < self.sell_trail_rsi_max_1) and (max_profit > (current_profit + self.sell_trail_down_1)) and (last_candle['moderi_96'] == False):
            return True, 'signal_profit_t_1'
        elif (self.sell_trail_profit_max_2 > current_profit >= self.sell_trail_profit_min_2) and (self.sell_trail_rsi_min_2 < last_candle['rsi_14'] < self.sell_trail_rsi_max_2) and (max_profit > (current_profit + self.sell_trail_down_2)) and (last_candle['ema_25'] < last_candle['ema_50']):
            return True, 'signal_profit_t_2'
        elif (self.sell_trail_profit_max_3 > current_profit >= self.sell_trail_profit_min_3) and (max_profit > (current_profit + self.sell_trail_down_3)) and (last_candle['sma_200_dec_20_1h']):
            return True, 'signal_profit_t_3'
        elif (self.sell_trail_profit_max_4 > current_profit >= self.sell_trail_profit_min_4) and (max_profit > (current_profit + self.sell_trail_down_4)) and (last_candle['sma_200_dec_24']) and (last_candle['cmf'] < 0.0):
            return True, 'signal_profit_t_4'

        return False, None

    def sell_duration_main(self, current_profit: float, last_candle, trade: 'Trade', current_time: 'datetime') -> tuple:
        # Pumped pair, short duration
        if (last_candle['sell_pump_24_1_1h']) and (0.2 > current_profit >= 0.07) and (current_time - timedelta(minutes=30) < trade.open_date_utc):
            return True, 'signal_profit_p_s_1'

        elif (self.sell_custom_long_profit_min_1 < current_profit < self.sell_custom_long_profit_max_1) and (current_time - timedelta(minutes=self.sell_custom_long_duration_min_1) > trade.open_date_utc):
            return True, 'signal_profit_l_1'

        return False, None

    def sell_under_min(self, current_profit: float, last_candle) -> tuple:
        if ((last_candle['moderi_96']) == False):
            # Downtrend
            if (self.sell_custom_profit_under_profit_max_1 > current_profit >= self.sell_custom_profit_under_profit_min_1) and (last_candle['close'] < last_candle['ema_200']) and (((last_candle['ema_200'] - last_candle['close']) / last_candle['close']) < self.sell_custom_profit_under_rel_1) and (last_candle['rsi_14'] > last_candle['rsi_14_1h'] + self.sell_custom_profit_under_rsi_diff_1):
                return True, 'signal_profit_u_e_1'
        else:
            # Uptrend
            if (current_profit >= self.sell_custom_profit_under_profit_2) and (last_candle['close'] < last_candle['ema_200']) and (((last_candle['ema_200'] - last_candle['close']) / last_candle['close']) < self.sell_custom_profit_under_rel_2) and (last_candle['rsi_14'] > last_candle['rsi_14_1h'] + self.sell_custom_profit_under_rsi_diff_2):
                return True, 'signal_profit_u_e_2'

        return False, None

    def sell_stoploss(self, current_profit: float, max_profit: float, max_loss: float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        # Under & near EMA200, local uptrend move
        if (
            current_profit < -0.05
            and last_candle['close'] < last_candle['ema_200']
            and last_candle['cmf'] < 0.0
            and (last_candle['ema_200'] - last_candle['close']) / last_candle['close'] < 0.004
            and last_candle['rsi_14'] > previous_candle_1['rsi_14']
            and last_candle['rsi_14'] > last_candle['rsi_14_1h'] + 10.0
            and last_candle['sma_200_dec_24']
            and current_time - timedelta(minutes=2880) > trade.open_date_utc
        ):
            return True, 'signal_stoploss_u_e_1'

        # Under EMA200, local strong uptrend move
        if (
            current_profit < -0.08
            and last_candle['close'] < last_candle['ema_200']
            and last_candle['cmf'] < 0.0
            and last_candle['rsi_14'] > previous_candle_1['rsi_14']
            and last_candle['rsi_14'] > last_candle['rsi_14_1h'] + 24.0
            and last_candle['sma_200_dec_20']
            and last_candle['sma_200_dec_24']
            and current_time - timedelta(minutes=2880) > trade.open_date_utc
        ):
            return True, 'signal_stoploss_u_e_2'

        # Under EMA200, pair negative, low max rate
        if (
            -0.04 > current_profit > -0.08
            and max_profit < 0.005
            and max_loss < 0.08
            and last_candle['close'] < last_candle['ema_200']
            and last_candle['ema_25'] < last_candle['ema_50']
            and last_candle['ema_vwma_osc_32'] < 0
            and last_candle['ema_vwma_osc_64'] < 0
            and last_candle['ema_vwma_osc_96'] < 0
            and last_candle['cmf'] < -0.0
            and current_time - timedelta(minutes=30) > trade.open_date_utc
        ):
            return True, 'signal_stoploss_u_e_3'

        # Under EMA200, pair and BTC negative, low max rate
        if (
            -0.05 > current_profit > -0.09
            and not last_candle['btc_not_downtrend_1h']
            and last_candle['ema_vwma_osc_32'] < 0
            and last_candle['ema_vwma_osc_64'] < 0
            and max_profit < 0.005
            and max_loss < 0.09
            and last_candle['sma_200_dec_24']
            and last_candle['cmf'] < -0.0
            and last_candle['close'] < last_candle['ema_200']
            and last_candle['ema_25'] < last_candle['ema_50']
            and last_candle['cti'] < -0.8
            and last_candle['r_480'] < -50.0
        ):
            return True, 'signal_stoploss_u_e_b_1'

        # Under EMA200, pair & BTC negative, CTI, downtrend, normal max rate
        if (
            -0.1 > current_profit > -0.2
            and not last_candle['btc_not_downtrend_1h']
            and last_candle['ema_vwma_osc_32'] < 0
            and last_candle['ema_vwma_osc_64'] < 0
            and last_candle['ema_vwma_osc_96'] < 0
            and max_profit < 0.05
            and max_loss < 0.2
            and last_candle['sma_200_dec_24']
            and last_candle['sma_200_dec_20_1h']
            and last_candle['cmf'] < -0.45
            and last_candle['close'] < last_candle['ema_200']
            and last_candle['ema_25'] < last_candle['ema_50']
            and last_candle['cti'] < -0.8
            and last_candle['r_480'] < -97.0
        ):
            return True, 'signal_stoploss_u_e_b_2'

        # Under EMA200, pair and BTC negative, low max rate
        if (
            -0.04 > current_profit > -0.07
            and last_candle['ema_vwma_osc_32'] < 0
            and last_candle['ema_vwma_osc_64'] < 0
            and max_profit < 0.005
            and max_loss < 0.07
            and last_candle['sma_200_dec_24']
            and last_candle['close'] < last_candle['ema_200']
            and last_candle['ema_25'] < last_candle['ema_50']
            and last_candle['cmf'] < -0.0
            and last_candle['r_480'] < -50.0
            and not last_candle['btc_not_downtrend_1h']
        ):
            return True, 'signal_stoploss_u_e_b_3'

        return False, None

    def sell_pump_dec(self, current_profit: float, last_candle) -> tuple:
        if (0.03 > current_profit >= 0.005) and (last_candle['sell_pump_48_1_1h']) and (last_candle['sma_200_dec_20']) and (last_candle['close'] < last_candle['ema_200']):
            return True, 'signal_profit_p_d_1'
        elif (0.06 > current_profit >= 0.04) and (last_candle['sell_pump_48_2_1h']) and (last_candle['sma_200_dec_20']) and (last_candle['close'] < last_candle['ema_200']):
            return True, 'signal_profit_p_d_2'
        elif (0.09 > current_profit >= 0.06) and (last_candle['sell_pump_48_3_1h']) and (last_candle['sma_200_dec_20']) and (last_candle['close'] < last_candle['ema_200']):
            return True, 'signal_profit_p_d_3'
        elif (0.04 > current_profit >= 0.02) and (last_candle['sma_200_dec_20']) and (last_candle['sell_pump_24_2_1h']):
            return True, 'signal_profit_p_d_4'

        return False, None

    def sell_pump_extra(self, current_profit: float, last_candle, max_profit: float) -> tuple:
        # Pumped 48h 1, under EMA200
        if (self.sell_custom_pump_under_profit_max_1 > current_profit >= self.sell_custom_pump_under_profit_min_1) and (last_candle['sell_pump_48_1_1h']) and (last_candle['close'] < last_candle['ema_200']):
            return True, 'signal_profit_p_u_1'

            # Pumped 36h 2, trail 1
        elif (last_candle['sell_pump_36_2_1h']) and (self.sell_custom_pump_trail_profit_max_1 > current_profit >= self.sell_custom_pump_trail_profit_min_1) and (self.sell_custom_pump_trail_rsi_min_1 < last_candle['rsi_14'] < self.sell_custom_pump_trail_rsi_max_1) and (max_profit > (current_profit + self.sell_custom_pump_trail_down_1)):
            return True, 'signal_profit_p_t_1'

        return False, None

    def sell_recover(self, current_profit: float, last_candle, max_loss: float) -> tuple:
        if (max_loss > self.sell_custom_recover_min_loss_1) and (current_profit >= self.sell_custom_recover_profit_1):
            return True, 'signal_profit_r_1'

        elif (max_loss > self.sell_custom_recover_min_loss_2) and (self.sell_custom_recover_profit_max_2 > current_profit >= self.sell_custom_recover_profit_min_2) and (last_candle['rsi_14'] < self.sell_custom_recover_rsi_2) and (last_candle['ema_25'] < last_candle['ema_50']):
            return True, 'signal_profit_r_2'

        return False, None

    def sell_r_1(self, current_profit: float, last_candle) -> tuple:
        if 0.02 > current_profit >= 0.012:
            if last_candle['r_480'] > -0.4:
                return True, 'signal_profit_w_1_1'
        elif 0.03 > current_profit >= 0.02:
            if last_candle['r_480'] > -0.5:
                return True, 'signal_profit_w_1_2'
        elif 0.04 > current_profit >= 0.03:
            if last_candle['r_480'] > -0.6:
                return True, 'signal_profit_w_1_3'
        elif 0.05 > current_profit >= 0.04:
            if last_candle['r_480'] > -0.7:
                return True, 'signal_profit_w_1_4'
        elif 0.06 > current_profit >= 0.05:
            if last_candle['r_480'] > -1.0:
                return True, 'signal_profit_w_1_5'
        elif 0.07 > current_profit >= 0.06:
            if last_candle['r_480'] > -2.0:
                return True, 'signal_profit_w_1_6'
        elif 0.08 > current_profit >= 0.07:
            if last_candle['r_480'] > -2.2:
                return True, 'signal_profit_w_1_7'
        elif 0.09 > current_profit >= 0.08:
            if last_candle['r_480'] > -2.4:
                return True, 'signal_profit_w_1_8'
        elif 0.1 > current_profit >= 0.09:
            if last_candle['r_480'] > -2.6:
                return True, 'signal_profit_w_1_9'
        elif 0.12 > current_profit >= 0.1:
            if (last_candle['r_480'] > -2.5) and (last_candle['rsi_14'] > 72.0):
                return True, 'signal_profit_w_1_10'
        elif 0.2 > current_profit >= 0.12:
            if (last_candle['r_480'] > -2.0) and (last_candle['rsi_14'] > 78.0):
                return True, 'signal_profit_w_1_11'
        elif current_profit >= 0.2:
            if (last_candle['r_480'] > -1.0) and (last_candle['rsi_14'] > 80.0):
                return True, 'signal_profit_w_1_12'

        return False, None

    def sell_r_2(self, current_profit: float, last_candle) -> tuple:
        if 0.02 > current_profit >= 0.012:
            if (last_candle['r_480'] > -4.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['stochrsi_fastk_96'] > 99.0) and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_1'
        elif 0.03 > current_profit >= 0.02:
            if (last_candle['r_480'] > -4.1) and (last_candle['rsi_14'] > 79.0) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_2'
        elif 0.04 > current_profit >= 0.03:
            if (last_candle['r_480'] > -4.2) and (last_candle['rsi_14'] > 79.0) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_3'
        elif 0.05 > current_profit >= 0.04:
            if (last_candle['r_480'] > -4.3) and (last_candle['rsi_14'] > 79.0) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_4'
        elif 0.06 > current_profit >= 0.05:
            if (last_candle['r_480'] > -4.4) and (last_candle['rsi_14'] > 79.0) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_5'
        elif 0.07 > current_profit >= 0.06:
            if (last_candle['r_480'] > -4.5) and (last_candle['rsi_14'] > 79.0) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_6'
        elif 0.08 > current_profit >= 0.07:
            if (last_candle['r_480'] > -5.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_7'
        elif 0.09 > current_profit >= 0.08:
            if (last_candle['r_480'] > -5.0) and (last_candle['rsi_14'] > 80.5) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_8'
        elif 0.1 > current_profit >= 0.09:
            if (last_candle['r_480'] > -4.8) and (last_candle['rsi_14'] > 80.5) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_9'
        elif 0.12 > current_profit >= 0.1:
            if (last_candle['r_480'] > -4.4) and (last_candle['rsi_14'] > 80.5) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_10'
        elif 0.2 > current_profit >= 0.12:
            if (last_candle['r_480'] > -3.2) and (last_candle['rsi_14'] > 81.0) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_11'
        elif current_profit >= 0.2:
            if (last_candle['r_480'] > -3.0) and (last_candle['rsi_14'] > 81.5) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_2_12'

        return False, None

    def sell_r_3(self, current_profit: float, last_candle) -> tuple:
        if 0.02 > current_profit >= 0.012:
            if (last_candle['r_480'] > -3.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['stochrsi_fastk_96'] > 99.0) and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_3_1'
        elif 0.03 > current_profit >= 0.02:
            if (last_candle['r_480'] > -3.5) and (last_candle['rsi_14'] > 74.0) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_3_2'
        elif 0.04 > current_profit >= 0.03:
            if (last_candle['r_480'] > -4.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_3_3'
        elif 0.05 > current_profit >= 0.04:
            if (last_candle['r_480'] > -4.5) and (last_candle['rsi_14'] > 79.0) and (last_candle['stochrsi_fastk_96'] > 99.0)  and (last_candle['stochrsi_fastd_96'] > 99.0):
                return True, 'signal_profit_w_3_4'

        return False, None

    def sell_r_4(self, current_profit: float, last_candle) -> tuple:
        if (0.02 > current_profit >= 0.012):
            if (last_candle['r_480'] > -2.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_1'
        elif (0.03 > current_profit >= 0.02):
            if (last_candle['r_480'] > -2.5) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_2'
        elif (0.04 > current_profit >= 0.03):
            if (last_candle['r_480'] > -3.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_3'
        elif (0.05 > current_profit >= 0.04):
            if (last_candle['r_480'] > -3.5) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_4'
        elif (0.06 > current_profit >= 0.05):
            if (last_candle['r_480'] > -4.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_5'
        elif (0.07 > current_profit >= 0.06):
            if (last_candle['r_480'] > -4.5) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_6'
        elif (0.08 > current_profit >= 0.07):
            if (last_candle['r_480'] > -5.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_7'
        elif (0.09 > current_profit >= 0.08):
            if (last_candle['r_480'] > -5.5) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_8'
        elif (0.1 > current_profit >= 0.09):
            if (last_candle['r_480'] > -4.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_9'
        elif (0.12 > current_profit >= 0.1):
            if (last_candle['r_480'] > -3.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_10'
        elif (0.2 > current_profit >= 0.12):
            if (last_candle['r_480'] > -2.5) and (last_candle['rsi_14'] > 80.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_11'
        elif (current_profit >= 0.2):
            if (last_candle['r_480'] > -2.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['cti'] > 0.9):
                return True, 'signal_profit_w_4_12'

        return False, None

    def sell_r_5(self, current_profit: float, last_candle) -> tuple:
        if (0.02 > current_profit >= 0.012):
            if (last_candle['r_480'] > -1.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_1'
        elif (0.03 > current_profit >= 0.02):
            if (last_candle['r_480'] > -1.5) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_2'
        elif (0.04 > current_profit >= 0.03):
            if (last_candle['r_480'] > -2.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_3'
        elif (0.05 > current_profit >= 0.04):
            if (last_candle['r_480'] > -2.5) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_4'
        elif (0.06 > current_profit >= 0.05):
            if (last_candle['r_480'] > -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_5'
        elif (0.07 > current_profit >= 0.06):
            if (last_candle['r_480'] > -3.5) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_6'
        elif (0.08 > current_profit >= 0.07):
            if (last_candle['r_480'] > -4.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_7'
        elif (0.09 > current_profit >= 0.08):
            if (last_candle['r_480'] > -4.5) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_8'
        elif (0.1 > current_profit >= 0.09):
            if (last_candle['r_480'] > -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_9'
        elif (0.12 > current_profit >= 0.1):
            if (last_candle['r_480'] > -2.5) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_10'
        elif (0.2 > current_profit >= 0.12):
            if (last_candle['r_480'] > -2.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_11'
        elif (current_profit >= 0.2):
            if (last_candle['r_480'] > -1.5) and (last_candle['rsi_14'] > 80.0) and (last_candle['cti_1h'] > 0.92):
                return True, 'signal_profit_w_5_12'

        return False, None

    def sell_r_6(self, current_profit: float, last_candle) -> tuple:
        if (0.02 > current_profit >= 0.012):
            if (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_1'
        elif (0.03 > current_profit >= 0.02):
            if (last_candle['r_14'] > -0.2) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_2'
        elif (0.04 > current_profit >= 0.03):
            if (last_candle['r_14'] > -0.3) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_3'
        elif (0.05 > current_profit >= 0.04):
            if (last_candle['r_14'] > -0.4) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_4'
        elif (0.06 > current_profit >= 0.05):
            if (last_candle['r_14'] > -0.5) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_5'
        elif (0.07 > current_profit >= 0.06):
            if (last_candle['r_14'] > -0.6) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_6'
        elif (0.08 > current_profit >= 0.07):
            if (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_7'
        elif (0.09 > current_profit >= 0.08):
            if (last_candle['r_14'] > -1.5) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_8'
        elif (0.1 > current_profit >= 0.09):
            if (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_9'
        elif (0.12 > current_profit >= 0.1):
            if (last_candle['r_14'] > -0.75) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_10'
        elif (0.2 > current_profit >= 0.12):
            if (last_candle['r_14'] > -0.5) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_11'
        elif (current_profit >= 0.2):
            if (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.8) and (last_candle['cci'] > 200.0):
                return True, 'signal_profit_w_6_12'

        return False, None

    def mark_profit_target(self, pair: str, trade: "Trade", current_time: "datetime", current_rate: float, current_profit: float, last_candle, previous_candle_1) -> tuple:
        # if self.profit_target_1_enable:
        #     if (current_profit > 0) and (last_candle['zlema_4_lowKF'] > last_candle['lowKF']) and (previous_candle_1['zlema_4_lowKF'] < previous_candle_1['lowKF']) and (last_candle['cci'] > -100) and (last_candle['hrsi'] > 70):
        #         return pair, "mark_profit_target_01"
        return None, None

    def sell_profit_target(self, pair: str, trade: "Trade", current_time: "datetime", current_rate: float, current_profit: float, last_candle, previous_candle_1, previous_rate, previous_sell_reason, previous_time_profit_reached) -> tuple:
        # if self.profit_target_1_enable and previous_sell_reason == "mark_profit_target_01":
        #     if (current_profit > 0) and (current_rate < (previous_rate - 0.005)):
        #         return True, 'sell_profit_target_01'

        return False, None

    def sell_quick_mode(self, current_profit: float, max_profit:float, last_candle, previous_candle_1) -> tuple:
        if (0.06 > current_profit > 0.02) and (last_candle['rsi_14'] > 80.0):
            return True, 'signal_profit_q_1'

        if (0.06 > current_profit > 0.02) and (last_candle['cti'] > 0.95):
            return True, 'signal_profit_q_2'

        if (0.04 > current_profit > 0.02) and (last_candle['pm'] <= last_candle['pmax_thresh']) and (last_candle['close'] > last_candle['sma_21'] * 1.1):
            return True, 'signal_profit_q_pmax_bull'
        if (0.045 > current_profit > 0.005) and (last_candle['pm'] > last_candle['pmax_thresh']) and (last_candle['close'] > last_candle['sma_21'] * 1.016):
            return True, 'signal_profit_q_pmax_bear'

        if (last_candle['momdiv_sell_1h'] == True) and (current_profit > 0.02):
            return True, 'signal_profit_q_momdiv_1h'
        if (last_candle['momdiv_sell'] == True) and (current_profit > 0.02):
            return True, 'signal_profit_q_momdiv'
        if (last_candle['momdiv_coh'] == True) and (current_profit > 0.02):
            return True, 'signal_profit_q_momdiv_coh'

        return False, None

    def sell_ichi(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if (0.0 < current_profit < 0.05) and (current_time - timedelta(minutes=1440) > trade.open_date_utc) and (last_candle['rsi_14'] > 78.0):
            return True, 'signal_profit_ichi_u'

        elif (max_loss > 0.07) and (current_profit > 0.02):
            return True, 'signal_profit_ichi_r_0'
        elif (max_loss > 0.06) and (current_profit > 0.03):
            return True, 'signal_profit_ichi_r_1'
        elif (max_loss > 0.05) and (current_profit > 0.04):
            return True, 'signal_profit_ichi_r_2'
        elif (max_loss > 0.04) and (current_profit > 0.05):
            return True, 'signal_profit_ichi_r_3'
        elif (max_loss > 0.03) and (current_profit > 0.06):
            return True, 'signal_profit_ichi_r_4'

        elif (0.05 < current_profit < 0.1) and (current_time - timedelta(minutes=720) > trade.open_date_utc):
            return True, 'signal_profit_ichi_slow'

        elif (0.07 < current_profit < 0.1) and (max_profit-current_profit > 0.025) and (max_profit > 0.1):
            return True, 'signal_profit_ichi_t'

        return False, None

    def sell_long_mode(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Sell signal 1
        if (last_candle['rsi_14'] > 78.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) and (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']) and (previous_candle_4['close'] > previous_candle_4['bb20_2_upp']) and (previous_candle_5['close'] > previous_candle_5['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_1_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_1_2_1'

        # Sell signal 2
        elif (last_candle['rsi_14'] > 79.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_2_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_2_2_1'

        # Sell signal 3
        elif (last_candle['rsi_14'] > 82.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_3_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_3_2_1'

        # Sell signal 4
        elif (last_candle['rsi_14'] > 78.0) and (last_candle['rsi_14_1h'] > 80.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_4_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_4_2_1'

        # Sell signal 6
        elif (last_candle['close'] < last_candle['ema_200']) and (last_candle['close'] > last_candle['ema_50']) and (last_candle['rsi_14'] > 79.5):
            if (current_profit > 0.01):
                return True, 'sell_long_6_1'

        # Sell signal 7
        elif (last_candle['rsi_14_1h'] > 82.0) and (last_candle['crossed_below_ema_12_26']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_7_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_7_2_1'

        # Sell signal 8
        elif (last_candle['close'] > last_candle['bb20_2_upp_1h'] * 1.05):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_long_8_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_long_8_2_1'

        elif (0.02 < current_profit <= 0.06) and (max_profit - current_profit > 0.04) and (last_candle['cmf'] < 0.0) and (last_candle['sma_200_dec_24']):
            return True, 'sell_long_t_1'
        elif (0.06 < current_profit <= 0.12) and (max_profit - current_profit > 0.06) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_2'
        elif (0.12 < current_profit <= 0.24) and (max_profit - current_profit > 0.08) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_3'
        elif (0.24 < current_profit <= 0.5) and (max_profit - current_profit > 0.09) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_4'
        elif (0.5 < current_profit <= 0.9) and (max_profit - current_profit > 0.1) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_5'

        elif (0.03 < current_profit <= 0.06) and (current_time - timedelta(minutes=720) > trade.open_date_utc) and (last_candle['r_480'] > -20.0):
            return True, 'sell_long_l_1'

        return self.sell_stoploss(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)

    def sell_pivot(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if (last_candle['close'] > (last_candle['res3_1d'] * 2.2)):
            if (0.02 > current_profit >= 0.012):
                if (last_candle['r_14'] >= -0.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['r_480'] > -3.0):
                    return True, 'signal_profit_pv_1_1_1'
            elif (0.03 > current_profit >= 0.02):
                if (last_candle['r_14'] > -0.4) and (last_candle['rsi_14'] > 76.0) and (last_candle['r_480'] > -5.0):
                    return True, 'signal_profit_pv_1_2_1'
            elif (0.04 > current_profit >= 0.03):
                if (last_candle['r_14'] > -0.8) and (last_candle['rsi_14'] > 74.0) and (last_candle['r_480'] > -10.0):
                    return True, 'signal_profit_pv_1_3_1'
            elif (0.05 > current_profit >= 0.04):
                if (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['r_480'] > -15.0):
                    return True, 'signal_profit_pv_1_4_1'
            elif (0.06 > current_profit >= 0.05):
                if (last_candle['r_14'] > -1.2) and (last_candle['rsi_14'] > 66.0) and (last_candle['r_480'] > -20.0):
                    return True, 'signal_profit_pv_1_5_1'
            elif (0.07 > current_profit >= 0.06):
                if (last_candle['r_14'] > -1.6) and (last_candle['rsi_14'] > 60.0) and (last_candle['r_480'] > -25.0):
                    return True, 'signal_profit_pv_1_6_1'
            elif (0.08 > current_profit >= 0.07):
                if (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 56.0) and (last_candle['r_480'] > -30.0):
                    return True, 'signal_profit_pv_1_7_1'

        elif (last_candle['close'] > (last_candle['res3_1d'] * 1.3)):
            if (0.02 > current_profit >= 0.012):
                if (last_candle['rsi_14'] > 80.0) and (last_candle['cti_1h'] > 0.84) and (last_candle['cmf'] < 0.0) and (last_candle['cci'] > 200.0):
                    return True, 'signal_profit_pv_2_1_1'
                elif (last_candle['rsi_14'] > 79.0) and (last_candle['r_14'] > -1.0) and (last_candle['cti'] > 0.9):
                    return True, 'signal_profit_pv_2_1_2'
            elif (0.03 > current_profit >= 0.02):
                if (last_candle['rsi_14'] > 78.0) and (last_candle['cti_1h'] > 0.84) and (last_candle['cmf'] < 0.0) and (last_candle['cci'] > 200.0):
                    return True, 'signal_profit_pv_2_2_1'
                elif (last_candle['rsi_14'] > 77.0) and (last_candle['r_14'] > -3.0) and (last_candle['cti'] > 0.9):
                    return True, 'signal_profit_pv_2_2_2'
            elif (0.04 > current_profit >= 0.03):
                if (last_candle['rsi_14'] > 76.0) and (last_candle['cti_1h'] > 0.84) and (last_candle['cmf'] < 0.0) and (last_candle['cci'] > 200.0):
                    return True, 'signal_profit_pv_2_3_1'
                elif (last_candle['rsi_14'] > 75.0) and (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.9):
                    return True, 'signal_profit_pv_2_3_2'
            elif (0.05 > current_profit >= 0.04):
                if (last_candle['rsi_14'] > 72.0) and (last_candle['cti_1h'] > 0.84) and (last_candle['cmf'] < 0.0) and (last_candle['cci'] > 200.0):
                    return True, 'signal_profit_pv_2_4_1'
                elif (last_candle['rsi_14'] > 71.0) and (last_candle['r_14'] > -7.0) and (last_candle['cti'] > 0.9):
                    return True, 'signal_profit_pv_2_4_2'
            elif (0.06 > current_profit >= 0.05):
                if (last_candle['rsi_14'] > 68.0) and (last_candle['cti_1h'] > 0.84) and (last_candle['cmf'] < 0.0) and (last_candle['cci'] > 200.0):
                    return True, 'signal_profit_pv_2_5_1'
                elif (last_candle['rsi_14'] > 67.0) and (last_candle['r_14'] > -9.0) and (last_candle['cti'] > 0.9):
                    return True, 'signal_profit_pv_2_5_2'
            elif (0.07 > current_profit >= 0.06):
                if (last_candle['rsi_14'] > 60.0) and (last_candle['cti_1h'] > 0.84) and (last_candle['cmf'] < 0.0) and (last_candle['cci'] > 200.0):
                    return True, 'signal_profit_pv_2_6_1'
                elif (last_candle['rsi_14'] > 59.0) and (last_candle['r_14'] > -9.0) and (last_candle['cti'] > 0.9):
                    return True, 'signal_profit_pv_2_6_2'
            elif (0.08 > current_profit >= 0.07):
                if (last_candle['rsi_14'] > 58.0) and (last_candle['cti_1h'] > 0.84) and (last_candle['cmf'] < 0.0) and (last_candle['cci'] > 200.0):
                    return True, 'signal_profit_pv_2_7_1'
                elif (last_candle['rsi_14'] > 57.0) and (last_candle['r_14'] > -9.0) and (last_candle['cti'] > 0.9):
                    return True, 'signal_profit_pv_2_7_2'

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

        buy_tag = trade.buy_tag if not None else 'empty'
        buy_tags = buy_tag.split()
        max_profit = ((trade.max_rate - trade.open_rate) / trade.open_rate)
        max_loss = ((trade.open_rate - trade.min_rate) / trade.min_rate)

        # Long mode
        if all(c in ['45', '46', '47'] for c in buy_tags):
            sell, signal_name = self.sell_long_mode(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, buy_tag)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {buy_tag})"
            # Skip remaining sell logic for long mode
            return None

        # Quick sell mode
        if all(c in ['empty', '32', '33', '34', '35', '36', '37', '38', '40'] for c in buy_tags):
            sell, signal_name = self.sell_quick_mode(current_profit, max_profit, last_candle, previous_candle_1)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {buy_tag})"

        # Ichi Trade management
        if all(c in ['39'] for c in buy_tags):
            sell, signal_name = self.sell_ichi(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {buy_tag})"

        # Over EMA200, main profit targets
        sell, signal_name = self.sell_over_main(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Under EMA200, main profit targets
        sell, signal_name = self.sell_under_main(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # The pair is pumped
        sell, signal_name = self.sell_pump_main(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # The pair is descending
        sell, signal_name = self.sell_dec_main(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Trailing
        sell, signal_name = self.sell_trail_main(current_profit, last_candle, max_profit)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Duration based
        sell, signal_name = self.sell_duration_main(current_profit, last_candle, trade, current_time)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Under EMA200, exit with any profit
        sell, signal_name = self.sell_under_min(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Stoplosses
        sell, signal_name = self.sell_stoploss(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Pumped descending pairs
        sell, signal_name = self.sell_pump_dec(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Extra sells for pumped pairs
        sell, signal_name = self.sell_pump_extra(current_profit, last_candle, max_profit)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Extra sells for trades that recovered
        sell, signal_name = self.sell_recover(current_profit, last_candle, max_loss)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Williams %R based sell 1
        sell, signal_name = self.sell_r_1(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Williams %R based sell 2
        sell, signal_name = self.sell_r_2(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Williams %R based sell 3
        sell, signal_name = self.sell_r_3(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Williams %R based sell 4, plus CTI
        sell, signal_name = self.sell_r_4(current_profit, last_candle)
        if (sell) and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Williams %R based sell 5, plus  RSI and CTI 1h
        sell, signal_name = self.sell_r_5(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Williams %R based sell 6, plus  RSI, CTI, CCI
        sell, signal_name = self.sell_r_6(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Pivot points based sells
        sell, signal_name = self.sell_pivot(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Profit Target Signal
        # Check if pair exist on target_profit_cache
        if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
            previous_rate = self.target_profit_cache.data[pair]['rate']
            previous_sell_reason = self.target_profit_cache.data[pair]['sell_reason']
            previous_time_profit_reached = datetime.fromisoformat(self.target_profit_cache.data[pair]['time_profit_reached'])

            sell, signal_name = self.sell_profit_target(pair, trade, current_time, current_rate, current_profit, last_candle, previous_candle_1, previous_rate, previous_sell_reason, previous_time_profit_reached)
            if sell and signal_name is not None:
                return f"{signal_name} ( {buy_tag})"

        pair, mark_signal = self.mark_profit_target(pair, trade, current_time, current_rate, current_profit, last_candle, previous_candle_1)
        if pair:
            self._set_profit_target(pair, mark_signal, current_rate, current_time)

        # Sell signal 1
        if self.sell_condition_1_enable and (last_candle['rsi_14'] > self.sell_rsi_bb_1) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) and (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']) and (previous_candle_4['close'] > previous_candle_4['bb20_2_upp']) and (previous_candle_5['close'] > previous_candle_5['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return f"sell_signal_1_1_1 ( {buy_tag})"
            else:
                if (current_profit > 0.01):
                    return f"sell_signal_1_2_1 ( {buy_tag})"
                elif (max_loss > 0.5):
                    return f"sell_signal_1_2_2 ( {buy_tag})"

        # Sell signal 2
        elif (self.sell_condition_2_enable) and (last_candle['rsi_14'] > self.sell_rsi_bb_2) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return f"sell_signal_2_1_1 ( {buy_tag})"
            else:
                if (current_profit > 0.01):
                    return f"sell_signal_2_2_1 ( {buy_tag})"
                elif (max_loss > 0.5):
                    return f"sell_signal_2_2_2 ( {buy_tag})"

        # Sell signal 3
        elif (self.sell_condition_3_enable) and (last_candle['rsi_14'] > self.sell_rsi_main_3):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return f"sell_signal_3_1_1 ( {buy_tag})"
            else:
                if (current_profit > 0.01):
                    return f"sell_signal_3_2_1 ( {buy_tag})"
                elif (max_loss > 0.5):
                    return f"sell_signal_3_2_2 ( {buy_tag})"

        # Sell signal 4
        elif self.sell_condition_4_enable and (last_candle['rsi_14'] > self.sell_dual_rsi_rsi_4) and (last_candle['rsi_14_1h'] > self.sell_dual_rsi_rsi_1h_4):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return f"sell_signal_4_1_1 ( {buy_tag})"
            else:
                if (current_profit > 0.01):
                    return f"sell_signal_4_2_1 ( {buy_tag})"
                elif (max_loss > 0.5):
                    return f"sell_signal_4_2_2 ( {buy_tag})"

        # Sell signal 6
        elif self.sell_condition_6_enable and (last_candle['close'] < last_candle['ema_200']) and (last_candle['close'] > last_candle['ema_50']) and (last_candle['rsi_14'] > self.sell_rsi_under_6):
            if (current_profit > 0.01):
                return f"sell_signal_6_1 ( {buy_tag})"
            elif (max_loss > 0.5):
                return f"sell_signal_6_2 ( {buy_tag})"

        # Sell signal 7
        elif self.sell_condition_7_enable and (last_candle['rsi_14_1h'] > self.sell_rsi_1h_7) and (last_candle['crossed_below_ema_12_26']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return f"sell_signal_7_1_1 ( {buy_tag})"
            else:
                if (current_profit > 0.01):
                    return f"sell_signal_7_2_1 ( {buy_tag})"
                elif (max_loss > 0.5):
                    return f"sell_signal_7_2_2 ( {buy_tag})"

        # Sell signal 8
        elif self.sell_condition_8_enable and (last_candle['close'] > last_candle['bb20_2_upp_1h'] * self.sell_bb_relative_8):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return f"sell_signal_8_1_1 ( {buy_tag})"
            else:
                if (current_profit > 0.01):
                    return f"sell_signal_8_2_1 ( {buy_tag})"
                elif (max_loss > 0.5):
                    return f"sell_signal_8_2_2 ( {buy_tag})"

        return None

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

    def range_maxgap(self, dataframe: DataFrame, length: int) -> float:
        """
        Maximum Price Gap across interval.

        :param dataframe: DataFrame The original OHLC dataframe
        :param length: int The length to look back
        """
        return dataframe['open'].rolling(length).max() - dataframe['close'].rolling(length).min()

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
        return dataframe['close'] - dataframe['close'].rolling(length).min()

    def safe_pump(self, dataframe: DataFrame, length: int, thresh: float, pull_thresh: float) -> bool:
        """
        Determine if entry after a pump is safe.

        :param dataframe: DataFrame The original OHLC dataframe
        :param length: int The length to look back
        :param thresh: int Maximum percentage change threshold
        :param pull_thresh: int Pullback from interval maximum threshold
        """
        return (dataframe[f'oc_pct_change_{length}'] < thresh) | (self.range_maxgap_adjusted(dataframe, length, pull_thresh) > self.range_height(dataframe, length))

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
        informative_pairs = [(pair, self.info_timeframe_1h) for pair in pairs]
        informative_pairs.extend([(pair, self.info_timeframe_1d) for pair in pairs])

        if self.config['stake_currency'] in ['USDT','BUSD','USDC','DAI','TUSD','PAX','USD','EUR','GBP']:
            btc_info_pair = f"BTC/{self.config['stake_currency']}"
        else:
            btc_info_pair = "BTC/USDT"

        informative_pairs.append((btc_info_pair, self.timeframe))
        informative_pairs.append((btc_info_pair, self.info_timeframe_1h))
        informative_pairs.append((btc_info_pair, self.info_timeframe_1d))
        return informative_pairs

    def informative_1d_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        assert self.dp, "DataProvider is required for multiple timeframes."
        # Get the informative pair
        informative_1d = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=self.info_timeframe_1d)

        # Top traded coins
        if self.coin_metrics['top_traded_enabled']:
            informative_1d = informative_1d.merge(self.coin_metrics['tt_dataframe'], on='date', how='left')
            informative_1d['is_top_traded'] = informative_1d.apply(lambda row: self.is_top_coin(metadata['pair'], row, self.coin_metrics['top_traded_len']), axis=1)
            column_names = [f"Coin #{i}" for i in range(1, self.coin_metrics['top_traded_len'] + 1)]
            informative_1d.drop(columns = column_names, inplace=True)
        # Top grossing coins
        if self.coin_metrics['top_grossing_enabled']:
            informative_1d = informative_1d.merge(self.coin_metrics['tg_dataframe'], on='date', how='left')
            informative_1d['is_top_grossing'] = informative_1d.apply(lambda row: self.is_top_coin(metadata['pair'], row, self.coin_metrics['top_grossing_len']), axis=1)
            column_names = [f"Coin #{i}" for i in range(1, self.coin_metrics['top_grossing_len'] + 1)]
            informative_1d.drop(columns = column_names, inplace=True)

        # Pivots
        informative_1d['pivot'], informative_1d['res1'], informative_1d['res2'], informative_1d['res3'], informative_1d['sup1'], informative_1d['sup2'], informative_1d['sup3'] = pivot_points(informative_1d, mode='fibonacci')

        # Smoothed Heikin-Ashi
        informative_1d['open_sha'], informative_1d['close_sha'], informative_1d['low_sha'] = HeikinAshi(informative_1d, smooth_inputs=True, smooth_outputs=False, length=10)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] informative_1d_indicators took: {tok - tik:0.4f} seconds.")

        return informative_1d

    def informative_1h_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        assert self.dp, "DataProvider is required for multiple timeframes."
        # Get the informative pair
        informative_1h = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=self.info_timeframe_1h)

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
        informative_1h['rsi_14'] = ta.RSI(informative_1h, timeperiod=14)

        # EWO
        informative_1h['ewo_sma'] = ewo_sma(informative_1h, 50, 200)

        # BB
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(informative_1h), window=20, stds=2)
        informative_1h['bb20_2_low'] = bollinger['lower']
        informative_1h['bb20_2_mid'] = bollinger['mid']
        informative_1h['bb20_2_upp'] = bollinger['upper']

        # Chaikin Money Flow
        informative_1h['cmf'] = chaikin_money_flow(informative_1h, 20)

        # Williams %R
        informative_1h['r_480'] = williams_r(informative_1h, period=480)

        # CTI
        informative_1h['cti'] = pta.cti(informative_1h["close"], length=20)

        # CRSI (3, 2, 100)
        crsi_closechange = informative_1h['close'] / informative_1h['close'].shift(1)
        crsi_updown = np.where(crsi_closechange.gt(1), 1.0, np.where(crsi_closechange.lt(1), -1.0, 0.0))
        informative_1h['crsi'] =  (ta.RSI(informative_1h['close'], timeperiod=3) + ta.RSI(crsi_updown, timeperiod=2) + ta.ROC(informative_1h['close'], 100)) / 3

        # Ichimoku
        ichi = ichimoku(informative_1h, conversion_line_period=20, base_line_periods=60, laggin_span=120, displacement=30)
        informative_1h['chikou_span'] = ichi['chikou_span']
        informative_1h['tenkan_sen'] = ichi['tenkan_sen']
        informative_1h['kijun_sen'] = ichi['kijun_sen']
        informative_1h['senkou_a'] = ichi['senkou_span_a']
        informative_1h['senkou_b'] = ichi['senkou_span_b']
        informative_1h['leading_senkou_span_a'] = ichi['leading_senkou_span_a']
        informative_1h['leading_senkou_span_b'] = ichi['leading_senkou_span_b']
        informative_1h['chikou_span_greater'] = (informative_1h['chikou_span'] > informative_1h['senkou_a']).shift(30).fillna(False)
        informative_1h.loc[:, 'cloud_top'] = informative_1h.loc[:, ['senkou_a', 'senkou_b']].max(axis=1)

        # SSL
        ssl_down, ssl_up = SSLChannels(informative_1h, 10)
        informative_1h['ssl_down'] = ssl_down
        informative_1h['ssl_up'] = ssl_up

        # MOMDIV
        mom = momdiv(informative_1h)
        informative_1h['momdiv_buy'] = mom['momdiv_buy']
        informative_1h['momdiv_sell'] = mom['momdiv_sell']
        informative_1h['momdiv_coh'] = mom['momdiv_coh']
        informative_1h['momdiv_col'] = mom['momdiv_col']

        # Pump protections
        informative_1h['hl_pct_change_48'] = self.range_percent_change(informative_1h, 'HL', 48)
        informative_1h['hl_pct_change_36'] = self.range_percent_change(informative_1h, 'HL', 36)
        informative_1h['hl_pct_change_24'] = self.range_percent_change(informative_1h, 'HL', 24)

        informative_1h['oc_pct_change_48'] = self.range_percent_change(informative_1h, 'OC', 48)
        informative_1h['oc_pct_change_36'] = self.range_percent_change(informative_1h, 'OC', 36)
        informative_1h['oc_pct_change_24'] = self.range_percent_change(informative_1h, 'OC', 24)

        informative_1h['hl_pct_change_5'] = self.range_percent_change(informative_1h, 'HL', 5)
        informative_1h['low_5'] = informative_1h['low'].shift().rolling(5).min()

        informative_1h['safe_pump_24_10'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_10_24, self.buy_pump_pull_threshold_10_24)
        informative_1h['safe_pump_36_10'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_10_36, self.buy_pump_pull_threshold_10_36)
        informative_1h['safe_pump_48_10'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_10_48, self.buy_pump_pull_threshold_10_48)

        informative_1h['safe_pump_24_20'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_20_24, self.buy_pump_pull_threshold_20_24)
        informative_1h['safe_pump_36_20'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_20_36, self.buy_pump_pull_threshold_20_36)
        informative_1h['safe_pump_48_20'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_20_48, self.buy_pump_pull_threshold_20_48)

        informative_1h['safe_pump_24_30'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_30_24, self.buy_pump_pull_threshold_30_24)
        informative_1h['safe_pump_36_30'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_30_36, self.buy_pump_pull_threshold_30_36)
        informative_1h['safe_pump_48_30'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_30_48, self.buy_pump_pull_threshold_30_48)

        informative_1h['safe_pump_24_40'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_40_24, self.buy_pump_pull_threshold_40_24)
        informative_1h['safe_pump_36_40'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_40_36, self.buy_pump_pull_threshold_40_36)
        informative_1h['safe_pump_48_40'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_40_48, self.buy_pump_pull_threshold_40_48)

        informative_1h['safe_pump_24_50'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_50_24, self.buy_pump_pull_threshold_50_24)
        informative_1h['safe_pump_36_50'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_50_36, self.buy_pump_pull_threshold_50_36)
        informative_1h['safe_pump_48_50'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_50_48, self.buy_pump_pull_threshold_50_48)

        informative_1h['safe_pump_24_60'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_60_24, self.buy_pump_pull_threshold_60_24)
        informative_1h['safe_pump_36_60'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_60_36, self.buy_pump_pull_threshold_60_36)
        informative_1h['safe_pump_48_60'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_60_48, self.buy_pump_pull_threshold_60_48)

        informative_1h['safe_pump_24_70'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_70_24, self.buy_pump_pull_threshold_70_24)
        informative_1h['safe_pump_36_70'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_70_36, self.buy_pump_pull_threshold_70_36)
        informative_1h['safe_pump_48_70'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_70_48, self.buy_pump_pull_threshold_70_48)

        informative_1h['safe_pump_24_80'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_80_24, self.buy_pump_pull_threshold_80_24)
        informative_1h['safe_pump_36_80'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_80_36, self.buy_pump_pull_threshold_80_36)
        informative_1h['safe_pump_48_80'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_80_48, self.buy_pump_pull_threshold_80_48)

        informative_1h['safe_pump_24_90'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_90_24, self.buy_pump_pull_threshold_90_24)
        informative_1h['safe_pump_36_90'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_90_36, self.buy_pump_pull_threshold_90_36)
        informative_1h['safe_pump_48_90'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_90_48, self.buy_pump_pull_threshold_90_48)

        informative_1h['safe_pump_24_100'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_100_24, self.buy_pump_pull_threshold_100_24)
        informative_1h['safe_pump_36_100'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_100_36, self.buy_pump_pull_threshold_100_36)
        informative_1h['safe_pump_48_100'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_100_48, self.buy_pump_pull_threshold_100_48)

        informative_1h['safe_pump_24_110'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_110_24, self.buy_pump_pull_threshold_110_24)
        informative_1h['safe_pump_36_110'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_110_36, self.buy_pump_pull_threshold_110_36)
        informative_1h['safe_pump_48_110'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_110_48, self.buy_pump_pull_threshold_110_48)

        informative_1h['safe_pump_24_120'] = self.safe_pump(informative_1h, 24, self.buy_pump_threshold_120_24, self.buy_pump_pull_threshold_120_24)
        informative_1h['safe_pump_36_120'] = self.safe_pump(informative_1h, 36, self.buy_pump_threshold_120_36, self.buy_pump_pull_threshold_120_36)
        informative_1h['safe_pump_48_120'] = self.safe_pump(informative_1h, 48, self.buy_pump_threshold_120_48, self.buy_pump_pull_threshold_120_48)

        informative_1h['sell_pump_48_1'] = (informative_1h['hl_pct_change_48'] > self.sell_pump_threshold_48_1)
        informative_1h['sell_pump_48_2'] = (informative_1h['hl_pct_change_48'] > self.sell_pump_threshold_48_2)
        informative_1h['sell_pump_48_3'] = (informative_1h['hl_pct_change_48'] > self.sell_pump_threshold_48_3)

        informative_1h['sell_pump_36_1'] = (informative_1h['hl_pct_change_36'] > self.sell_pump_threshold_36_1)
        informative_1h['sell_pump_36_2'] = (informative_1h['hl_pct_change_36'] > self.sell_pump_threshold_36_2)
        informative_1h['sell_pump_36_3'] = (informative_1h['hl_pct_change_36'] > self.sell_pump_threshold_36_3)

        informative_1h['sell_pump_24_1'] = (informative_1h['hl_pct_change_24'] > self.sell_pump_threshold_24_1)
        informative_1h['sell_pump_24_2'] = (informative_1h['hl_pct_change_24'] > self.sell_pump_threshold_24_2)
        informative_1h['sell_pump_24_3'] = (informative_1h['hl_pct_change_24'] > self.sell_pump_threshold_24_3)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] informative_1h_indicators took: {tok - tik:0.4f} seconds.")

        return informative_1h

    def normal_tf_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        # BB 40 - STD2
        bb_40_std2 = qtpylib.bollinger_bands(dataframe['close'], window=40, stds=2)
        dataframe['bb40_2_low'] = bb_40_std2['lower']
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
        dataframe['ema_16'] = ta.EMA(dataframe, timeperiod=16)
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
        dataframe['ewo_sma'] = ewo_sma(dataframe, 50, 200)

        # RSI
        dataframe['rsi_4'] = ta.RSI(dataframe, timeperiod=4)
        dataframe['rsi_14'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['rsi_20'] = ta.RSI(dataframe, timeperiod=20)

        # Chopiness
        dataframe['chop']= qtpylib.chopiness(dataframe, 14)

        # Zero-Lag EMA
        dataframe['zema_61'] = zema(dataframe, period=61)

        # Williams %R
        dataframe['r_14'] = williams_r(dataframe, period=14)
        dataframe['r_480'] = williams_r(dataframe, period=480)

        # Stochastic RSI
        stochrsi = ta.STOCHRSI(dataframe, timeperiod=96, fastk_period=3, fastd_period=3, fastd_matype=0)
        dataframe['stochrsi_fastk_96'] = stochrsi['fastk']
        dataframe['stochrsi_fastd_96'] = stochrsi['fastd']

        # Modified Elder Ray Index
        dataframe['moderi_32'] = moderi(dataframe, 32)
        dataframe['moderi_64'] = moderi(dataframe, 64)
        dataframe['moderi_96'] = moderi(dataframe, 96)

        # EMA of VWMA Oscillator
        dataframe['ema_vwma_osc_32'] = ema_vwma_osc(dataframe, 32)
        dataframe['ema_vwma_osc_64'] = ema_vwma_osc(dataframe, 64)
        dataframe['ema_vwma_osc_96'] = ema_vwma_osc(dataframe, 96)

        # hull
        dataframe['hull_75'] = hull(dataframe, 75)

        # CRSI (3, 2, 100)
        crsi_closechange = dataframe['close'] / dataframe['close'].shift(1)
        crsi_updown = np.where(crsi_closechange.gt(1), 1.0, np.where(crsi_closechange.lt(1), -1.0, 0.0))
        dataframe['crsi'] =  (ta.RSI(dataframe['close'], timeperiod=3) + ta.RSI(crsi_updown, timeperiod=2) + ta.ROC(dataframe['close'], 100)) / 3

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

        # HLC3
        dataframe['hlc3'] = (dataframe['high'] + dataframe['low'] + dataframe['close']) / 3

        # CCI
        dataframe['cci'] = ta.CCI(dataframe, source='hlc3', timeperiod=20)

        # CCI Oscillator
        cci_36 = ta.CCI(dataframe, timeperiod=36)
        cci_36_max = cci_36.rolling(self.startup_candle_count).max()
        cci_36_min = cci_36.rolling(self.startup_candle_count).min()
        dataframe['cci_36_osc'] = (cci_36 / cci_36_max).where(cci_36 > 0, -cci_36 / cci_36_min)

        # MOMDIV
        mom = momdiv(dataframe)
        dataframe['momdiv_buy'] = mom['momdiv_buy']
        dataframe['momdiv_sell'] = mom['momdiv_sell']
        dataframe['momdiv_coh'] = mom['momdiv_coh']
        dataframe['momdiv_col'] = mom['momdiv_col']

        # Dip protection
        dataframe['tpct_change_0']   = self.top_percent_change(dataframe,0)
        dataframe['tpct_change_2']   = self.top_percent_change(dataframe,2)
        dataframe['tpct_change_12']  = self.top_percent_change(dataframe,12)
        dataframe['tpct_change_144'] = self.top_percent_change(dataframe,144)

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

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] normal_tf_indicators took: {tok - tik:0.4f} seconds.")

        return dataframe

    def resampled_tf_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Indicators
        # -----------------------------------------------------------------------------------------
        dataframe['rsi_14'] = ta.RSI(dataframe, timeperiod=14)

        return dataframe

    def base_tf_btc_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        # Indicators
        # -----------------------------------------------------------------------------------------
        dataframe['rsi_14'] = ta.RSI(dataframe, timeperiod=14)

        # Add prefix
        # -----------------------------------------------------------------------------------------
        ignore_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        dataframe.rename(columns=lambda s: f"btc_{s}" if s not in ignore_columns else s, inplace=True)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] base_tf_btc_indicators took: {tok - tik:0.4f} seconds.")

        return dataframe

    def info_tf_btc_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        # Indicators
        # -----------------------------------------------------------------------------------------
        dataframe['rsi_14'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['not_downtrend'] = ((dataframe['close'] > dataframe['close'].shift(2)) | (dataframe['rsi_14'] > 50))

        # Add prefix
        # -----------------------------------------------------------------------------------------
        ignore_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        dataframe.rename(columns=lambda s: f"btc_{s}" if s not in ignore_columns else s, inplace=True)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] info_tf_btc_indicators took: {tok - tik:0.4f} seconds.")

        return dataframe

    def daily_tf_btc_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        # Indicators
        # -----------------------------------------------------------------------------------------
        dataframe['pivot'], dataframe['res1'], dataframe['res2'], dataframe['res3'], dataframe['sup1'], dataframe['sup2'], dataframe['sup3'] = pivot_points(dataframe, mode='fibonacci')

        # Add prefix
        # -----------------------------------------------------------------------------------------
        ignore_columns = ['date', 'open', 'high', 'low', 'close', 'volume']
        dataframe.rename(columns=lambda s: f"btc_{s}" if s not in ignore_columns else s, inplace=True)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] daily_tf_btc_indicators took: {tok - tik:0.4f} seconds.")

        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        '''
        --> BTC informative (5m/1h)
        ___________________________________________________________________________________________
        '''
        if self.config['stake_currency'] in ['USDT','BUSD','USDC','DAI','TUSD','PAX','USD','EUR','GBP']:
            btc_info_pair = f"BTC/{self.config['stake_currency']}"
        else:
            btc_info_pair = "BTC/USDT"

        if self.has_BTC_daily_tf:
            btc_daily_tf = self.dp.get_pair_dataframe(btc_info_pair, '1d')
            btc_daily_tf = self.daily_tf_btc_indicators(btc_daily_tf, metadata)
            dataframe = merge_informative_pair(dataframe, btc_daily_tf, self.timeframe, '1d', ffill=True)
            drop_columns = [f"{s}_1d" for s in ['date', 'open', 'high', 'low', 'close', 'volume']]
            dataframe.drop(columns=dataframe.columns.intersection(drop_columns), inplace=True)

        if self.has_BTC_info_tf:
            btc_info_tf = self.dp.get_pair_dataframe(btc_info_pair, self.info_timeframe_1h)
            btc_info_tf = self.info_tf_btc_indicators(btc_info_tf, metadata)
            dataframe = merge_informative_pair(dataframe, btc_info_tf, self.timeframe, self.info_timeframe_1h, ffill=True)
            drop_columns = [f"{s}_{self.info_timeframe_1h}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']]
            dataframe.drop(columns=dataframe.columns.intersection(drop_columns), inplace=True)

        if self.has_BTC_base_tf:
            btc_base_tf = self.dp.get_pair_dataframe(btc_info_pair, self.timeframe)
            btc_base_tf = self.base_tf_btc_indicators(btc_base_tf, metadata)
            dataframe = merge_informative_pair(dataframe, btc_base_tf, self.timeframe, self.timeframe, ffill=True)
            drop_columns = [f"{s}_{self.timeframe}" for s in ['date', 'open', 'high', 'low', 'close', 'volume']]
            dataframe.drop(columns=dataframe.columns.intersection(drop_columns), inplace=True)

        '''
        --> Informative timeframe
        ___________________________________________________________________________________________
        '''
        if self.info_timeframe_1d != 'none':
            informative_1d = self.informative_1d_indicators(dataframe, metadata)
            dataframe = merge_informative_pair(dataframe, informative_1d, self.timeframe, self.info_timeframe_1d, ffill=True)
            drop_columns = [f"{s}_{self.info_timeframe_1d}" for s in ['date','open', 'high', 'low', 'close', 'volume']]
            dataframe.drop(columns=dataframe.columns.intersection(drop_columns), inplace=True)

        if self.info_timeframe_1h != 'none':
            informative_1h = self.informative_1h_indicators(dataframe, metadata)
            dataframe = merge_informative_pair(dataframe, informative_1h, self.timeframe, self.info_timeframe_1h, ffill=True)
            drop_columns = [f"{s}_{self.info_timeframe_1h}" for s in ['date']]
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
            dataframe.rename(columns=lambda s: f"{s}_{self.res_timeframe}" if "resample_" in s else s, inplace=True)
            dataframe.rename(columns=lambda s: s.replace("resample_{}_".format(self.res_timeframe.replace("m","")), ""), inplace=True)
            drop_columns = [f"{s}_{self.res_timeframe}" for s in ['date']]
            dataframe.drop(columns=dataframe.columns.intersection(drop_columns), inplace=True)

        '''
        --> The indicators for the normal (5m) timeframe
        ___________________________________________________________________________________________
        '''
        dataframe = self.normal_tf_indicators(dataframe, metadata)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] Populate indicators took a total of: {tok - tik:0.4f} seconds.")

        return dataframe

    def populate_buy_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = []
        dataframe.loc[:, 'buy_tag'] = ''

        for index in self.buy_protection_params:
            item_buy_protection_list = [True]
            global_buy_protection_params = self.buy_protection_params[index]

            if self.buy_params[f"buy_condition_{index}_enable"]:
                # Standard protections - Common to every condition
                # -----------------------------------------------------------------------------------------
                if global_buy_protection_params["ema_fast"]:
                    item_buy_protection_list.append(dataframe[f"ema_{global_buy_protection_params['ema_fast_len']}"] > dataframe['ema_200'])
                if global_buy_protection_params["ema_slow"]:
                    item_buy_protection_list.append(dataframe[f"ema_{global_buy_protection_params['ema_slow_len']}_1h"] > dataframe['ema_200_1h'])
                if global_buy_protection_params["close_above_ema_fast"]:
                    item_buy_protection_list.append(dataframe['close'] > dataframe[f"ema_{global_buy_protection_params['close_above_ema_fast_len']}"])
                if global_buy_protection_params["close_above_ema_slow"]:
                    item_buy_protection_list.append(dataframe['close'] > dataframe[f"ema_{global_buy_protection_params['close_above_ema_slow_len']}_1h"])
                if global_buy_protection_params["sma200_rising"]:
                    item_buy_protection_list.append(dataframe['sma_200'] > dataframe['sma_200'].shift(int(global_buy_protection_params['sma200_rising_val'])))
                if global_buy_protection_params["sma200_1h_rising"]:
                    item_buy_protection_list.append(dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(int(global_buy_protection_params['sma200_1h_rising_val'])))
                if global_buy_protection_params["safe_dips_threshold_0"] is not None:
                    item_buy_protection_list.append(dataframe['tpct_change_0'] < global_buy_protection_params["safe_dips_threshold_0"])
                if global_buy_protection_params["safe_dips_threshold_2"] is not None:
                    item_buy_protection_list.append(dataframe['tpct_change_2'] < global_buy_protection_params["safe_dips_threshold_2"])
                if global_buy_protection_params["safe_dips_threshold_12"] is not None:
                    item_buy_protection_list.append(dataframe['tpct_change_12'] < global_buy_protection_params["safe_dips_threshold_12"])
                if global_buy_protection_params["safe_dips_threshold_144"] is not None:
                    item_buy_protection_list.append(dataframe['tpct_change_144'] < global_buy_protection_params["safe_dips_threshold_144"])
                if global_buy_protection_params["safe_pump"]:
                    item_buy_protection_list.append(dataframe[f"safe_pump_{global_buy_protection_params['safe_pump_period']}_{global_buy_protection_params['safe_pump_type']}_1h"])
                if global_buy_protection_params['btc_1h_not_downtrend']:
                    item_buy_protection_list.append(dataframe['btc_not_downtrend_1h'])
                if global_buy_protection_params['close_over_pivot_type'] != 'none':
                    item_buy_protection_list.append(dataframe['close'] > dataframe[f"{global_buy_protection_params['close_over_pivot_type']}_1d"] * global_buy_protection_params['close_over_pivot_offset'])
                if global_buy_protection_params['close_under_pivot_type'] != 'none':
                    item_buy_protection_list.append(dataframe['close'] < dataframe[f"{global_buy_protection_params['close_under_pivot_type']}_1d"] * global_buy_protection_params['close_under_pivot_offset'])
                if not self.config['runmode'].value in ('live', 'dry_run'):
                    if self.has_bt_agefilter:
                        item_buy_protection_list.append(dataframe['bt_agefilter_ok'])
                else:
                    if self.has_downtime_protection:
                        item_buy_protection_list.append(dataframe['live_data_ok'])

                # Buy conditions
                # -----------------------------------------------------------------------------------------
                item_buy_logic = []
                item_buy_logic.append(reduce(lambda x, y: x & y, item_buy_protection_list))

                # Condition #1
                if index == 1:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(((dataframe['close'] - dataframe['open'].rolling(12).min()) / dataframe['open'].rolling(12).min()) > self.buy_1_min_inc)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_1_rsi_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_2_r_14_max)
                    item_buy_logic.append(dataframe['mfi'] < self.buy_1_mfi_max)
                    item_buy_logic.append(dataframe['rsi_14_1h'] > self.buy_1_rsi_1h_min)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < self.buy_1_rsi_1h_max)

                # Condition #2
                elif index == 2:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['rsi_14'] < dataframe['rsi_14_1h'] - self.buy_2_rsi_1h_diff)
                    item_buy_logic.append(dataframe['mfi'] < self.buy_2_mfi)
                    item_buy_logic.append(dataframe['cti'] < self.buy_2_cti_max)
                    item_buy_logic.append(dataframe['r_480'] > self.buy_2_r_480_min)
                    item_buy_logic.append(dataframe['r_480'] < self.buy_2_r_480_max)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_2_cti_1h_max)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_2_volume))

                # Condition #3
                elif index == 3:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_low'].shift().gt(0))
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * self.buy_3_bb40_bbdelta_close))
                    item_buy_logic.append(dataframe['closedelta'].gt(dataframe['close'] * self.buy_3_bb40_closedelta_close))
                    item_buy_logic.append(dataframe['tail'].lt(dataframe['bb40_2_delta'] * self.buy_3_bb40_tail_bbdelta))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))
                    item_buy_logic.append(dataframe['cci_36_osc'] > self.buy_3_cci_36_osc_min)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_3_crsi_1h_min)
                    item_buy_logic.append(dataframe['r_480_1h'] > self.buy_3_r_480_1h_min)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_3_cti_1h_max)

                # Condition #4
                elif index == 4:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_50'])
                    item_buy_logic.append(dataframe['close'] < self.buy_4_bb20_close_bblowerband * dataframe['bb20_2_low'])
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_30'].shift(1) * self.buy_4_bb20_volume))
                    item_buy_logic.append(dataframe['cti'] < self.buy_4_cti_max)

                # Condition #5
                elif index == 5:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['close'] > (dataframe['ema_200_1h'] * self.buy_5_ema_rel))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_5_ema_open_mult))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_5_bb_offset))
                    item_buy_logic.append(dataframe['cti'] < self.buy_5_cti_max)
                    item_buy_logic.append(dataframe['rsi_14'] > self.buy_5_rsi_14_min)
                    item_buy_logic.append(dataframe['mfi'] > self.buy_5_mfi_min)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_5_r_14_max)
                    item_buy_logic.append(dataframe['r_14'].shift(1) < self.buy_5_r_14_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_5_crsi_1h_min)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_5_volume))

                # Condition #6
                elif index == 6:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_6_ema_open_mult))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_6_bb_offset))
                    item_buy_logic.append(dataframe['r_14'] < self.buy_6_r_14_max)
                    item_buy_logic.append(dataframe['cti_1h'] > self.buy_6_cti_1h_min)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_6_crsi_1h_min)

                # Condition #7
                elif index == 7:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_7_ema_open_mult))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_7_ma_offset)
                    item_buy_logic.append(dataframe['cti'] < self.buy_7_cti_max)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_7_rsi_max)

                # Condition #8
                elif index == 8:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_20'] > dataframe['ema_50'])
                    item_buy_logic.append(dataframe['ema_15'] > dataframe['ema_100'])
                    item_buy_logic.append(dataframe['ema_200'] > dataframe['sma_200'])

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_8_bb_offset))
                    item_buy_logic.append(dataframe['r_14'] < self.buy_8_r_14_max)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_8_cti_1h_max)
                    item_buy_logic.append(dataframe['r_480_1h'] < self.buy_8_r_480_1h_max)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_8_volume))

                # Condition #9
                elif index == 9:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_50'] > dataframe['ema_200'])

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * self.buy_9_ma_offset)
                    item_buy_logic.append(dataframe['close'] < dataframe['bb20_2_low'] * self.buy_9_bb_offset)
                    item_buy_logic.append(dataframe['mfi'] < self.buy_9_mfi_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_9_cti_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_9_r_14_max)
                    item_buy_logic.append(dataframe['rsi_14_1h'] > self.buy_9_rsi_1h_min)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < self.buy_9_rsi_1h_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_9_crsi_1h_min)

                # Condition #10
                elif index == 10:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_50_1h'] > dataframe['ema_100_1h'])

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_10_ma_offset_high)
                    item_buy_logic.append(dataframe['close'] < dataframe['bb20_2_low'] * self.buy_10_bb_offset)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_10_r_14_max)
                    item_buy_logic.append(dataframe['cti_1h'] > self.buy_10_cti_1h_min)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_10_cti_1h_max)

                # Condition #11
                elif index == 11:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(((dataframe['close'] - dataframe['open'].rolling(6).min()) / dataframe['open'].rolling(6).min()) > self.buy_11_min_inc)
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_11_ma_offset)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_11_rsi_max)
                    item_buy_logic.append(dataframe['mfi'] < self.buy_11_mfi_max)
                    item_buy_logic.append(dataframe['cci'] < self.buy_11_cci_max)
                    item_buy_logic.append(dataframe['rsi_14_1h'] > self.buy_11_rsi_1h_min)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < self.buy_11_rsi_1h_max)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_11_cti_1h_max)
                    item_buy_logic.append(dataframe['r_480_1h'] < self.buy_11_r_480_1h_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_11_crsi_1h_min)

                # Condition #12
                elif index == 12:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_12_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_12_ewo_min)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_12_rsi_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_12_cti_max)

                # Condition #13
                elif index == 13:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_50_1h'] > dataframe['ema_100_1h'])

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_13_ma_offset)
                    item_buy_logic.append(dataframe['cti'] < self.buy_13_cti_max)
                    item_buy_logic.append(dataframe['ewo_sma'] < self.buy_13_ewo_max)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_13_cti_1h_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_13_crsi_1h_min)

                # Condition #14
                elif index == 14:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_14_ema_open_mult))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_14_bb_offset))
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * self.buy_14_ma_offset)
                    item_buy_logic.append(dataframe['cti'] < self.buy_14_cti_max)

                # Condition #15
                elif index == 15:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_15_ema_open_mult))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_15_rsi_min)
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * self.buy_15_ma_offset)
                    item_buy_logic.append(dataframe['cti_1h'] > self.buy_15_cti_1h_min)

                # Condition #16
                elif index == 16:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * self.buy_16_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_16_ewo_min)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_16_rsi_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_16_cti_max)

                # Condition #17
                elif index == 17:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * self.buy_17_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] < self.buy_17_ewo_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_17_cti_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_17_crsi_1h_min)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_17_volume))

                # Condition #18
                elif index == 18:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['sma_200'] > dataframe['sma_200'].shift(20))
                    item_buy_logic.append(dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(36))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_18_bb_offset))
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_18_rsi_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_18_cti_max)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_18_cti_1h_max)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_18_volume))

                # Condition #19
                elif index == 19:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['moderi_32'] == True)
                    item_buy_logic.append(dataframe['moderi_64'] == True)
                    item_buy_logic.append(dataframe['moderi_96'] == True)

                    # Logic
                    item_buy_logic.append(dataframe['close'].shift(1) > dataframe['ema_100_1h'])
                    item_buy_logic.append(dataframe['low'] < dataframe['ema_100_1h'])
                    item_buy_logic.append(dataframe['close'] > dataframe['ema_100_1h'])
                    item_buy_logic.append(dataframe['chop'] < self.buy_19_chop_max)
                    item_buy_logic.append(dataframe['rsi_14_1h'] > self.buy_19_rsi_1h_min)

                # Condition #20
                elif index == 20:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_20_rsi_14_max)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < self.buy_20_rsi_14_1h_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_20_cti_max)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_20_volume))

                # Condition #21
                elif index == 21:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_21_rsi_14_max)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < self.buy_21_rsi_14_1h_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_21_cti_max)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_21_volume))

                # Condition #22
                elif index == 22:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_100_1h'] > dataframe['ema_100_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(36))

                    # Logic
                    item_buy_logic.append((dataframe['volume_mean_4'] * self.buy_22_volume) > dataframe['volume'])
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_22_ma_offset)
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_22_bb_offset))
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_22_ewo_min)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_22_rsi_14_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_22_cti_max)
                    item_buy_logic.append(dataframe['r_480'] < self.buy_22_r_480_max)
                    item_buy_logic.append(dataframe['cti_1h'] > self.buy_22_cti_1h_min)

                # Condition #23
                elif index == 23:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_23_bb_offset))
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_23_ewo_min)
                    item_buy_logic.append(dataframe['cti'] < self.buy_23_cti_max)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_23_rsi_14_max)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < self.buy_23_rsi_14_1h_max)
                    item_buy_logic.append(dataframe['r_480_1h'] > self.buy_23_r_480_1h_min)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.92)

                # Condition #24
                elif index == 24:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_12_1h'].shift(12) < dataframe['ema_35_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_12_1h'] > dataframe['ema_35_1h'])
                    item_buy_logic.append(dataframe['cmf_1h'].shift(12) < 0)
                    item_buy_logic.append(dataframe['cmf_1h'] > 0)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_24_rsi_14_max)
                    item_buy_logic.append(dataframe['rsi_14_1h'] > self.buy_24_rsi_14_1h_min)

                # Condition #25
                elif index == 25:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['rsi_20'] < dataframe['rsi_20'].shift())
                    item_buy_logic.append(dataframe['rsi_4'] < self.buy_25_rsi_4_max)
                    item_buy_logic.append(dataframe['ema_20_1h'] > dataframe['ema_26_1h'])
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_15'] * self.buy_25_ma_offset)
                    item_buy_logic.append(dataframe['cti'] < self.buy_25_cti_max)
                    item_buy_logic.append(dataframe['cci'] < self.buy_25_cci_max)

                # Condition #26
                elif index == 26:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['zema_61'] * self.buy_26_zema_low_offset))
                    item_buy_logic.append(dataframe['cti'] < self.buy_26_cti_max)
                    item_buy_logic.append(dataframe['cci'] < self.buy_26_cci_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_26_r_14_max)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_26_cti_1h_max)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_26_volume))

                # Condition #27
                elif index == 27:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['r_480'] < self.buy_27_wr_max)
                    item_buy_logic.append(dataframe['r_14'] == self.buy_27_r_14)
                    item_buy_logic.append(dataframe['r_480_1h'] < self.buy_27_wr_1h_max)
                    item_buy_logic.append(dataframe['rsi_14_1h'] + dataframe['rsi_14'] < self.buy_27_rsi_max)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_27_volume))

                # Condition #28
                elif index == 28:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['moderi_64'] == True)
                    item_buy_logic.append(dataframe['close'] < dataframe['hull_75'] * self.buy_28_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_28_ewo_min)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_28_rsi_14_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_28_cti_max)
                    item_buy_logic.append(dataframe['cti'].shift(1) < self.buy_28_cti_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_28_r_14_max)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_28_cti_1h_max)

                # Condition #29
                elif index == 29:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['moderi_64'] == True)
                    item_buy_logic.append(dataframe['close'] < dataframe['hull_75'] * self.buy_29_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] < self.buy_29_ewo_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_29_cti_max)

                # Condition #30
                elif index == 30:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['moderi_64'] == False)
                    item_buy_logic.append(dataframe['close'] < dataframe['zlema_68'] * self.buy_30_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_30_ewo_min)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_30_rsi_14_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_30_cti_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_30_r_14_max)

                # Condition #31
                elif index == 31:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['moderi_64'] == False)
                    item_buy_logic.append(dataframe['close'] < dataframe['zlema_68'] * self.buy_31_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] < self.buy_31_ewo_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_31_r_14_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_31_cti_max)

                # Condition #32 - Quick mode buy
                elif index == 32:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_20_1h'] > dataframe['ema_25_1h'])

                    # Logic
                    item_buy_logic.append(dataframe['rsi_20'] < dataframe['rsi_20'].shift(1))
                    item_buy_logic.append(dataframe['rsi_4'] < self.buy_32_rsi_4_max)
                    item_buy_logic.append(dataframe['rsi_14'] > self.buy_32_rsi_14_min)
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_15'] * self.buy_32_ma_offset)
                    item_buy_logic.append(dataframe['cti'] < self.buy_32_cti_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_32_crsi_1h_min)
                    item_buy_logic.append(dataframe['crsi_1h'] < self.buy_32_crsi_1h_max)

                # Condition #33 - Quick mode buy
                elif index == 33:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_13'] * self.buy_33_ma_offset))
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_33_ewo_min)
                    item_buy_logic.append(dataframe['cti'] < self.buy_33_cti_max)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_33_rsi_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_33_r_14_max)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_33_cti_1h_max)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_33_volume))

                # Condition #34 - Quick mode buy
                elif index == 34:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_13'] * self.buy_34_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] < self.buy_34_ewo_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_34_cti_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_34_r_14_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_34_crsi_1h_min)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * self.buy_34_volume))

                # Condition #35 - PMAX0 buy
                elif index == 35:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['pm'] <= dataframe['pmax_thresh'])
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * self.buy_35_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_35_ewo_min)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_35_rsi_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_35_cti_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_35_r_14_max)

                # Condition #36 - PMAX1 buy
                elif index == 36:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['pm'] <= dataframe['pmax_thresh'])
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * self.buy_36_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] < self.buy_36_ewo_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_36_cti_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_36_r_14_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_36_crsi_1h_min)


                # Condition #37 - Quick mode buy
                elif index == 37:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * self.buy_37_ma_offset)
                    item_buy_logic.append(((dataframe['close_1h'].shift(12) - dataframe['close_1h']) / dataframe['close_1h']) < self.buy_37_close_1h_max)
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_37_ewo_min)
                    item_buy_logic.append(dataframe['ewo_sma'] < self.buy_37_ewo_max)
                    item_buy_logic.append(dataframe['rsi_14'] > self.buy_37_rsi_14_min)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_37_rsi_14_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_37_crsi_1h_min)
                    item_buy_logic.append(dataframe['crsi_1h'] < self.buy_37_crsi_1h_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_37_cti_max)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_37_cti_1h_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_37_r_14_max)

                # Condition #38 - PMAX3 buy
                elif index == 38:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['pm'] > dataframe['pmax_thresh'])
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * self.buy_38_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] < self.buy_38_ewo_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_38_cti_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_38_r_14_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_38_crsi_1h_min)

                # Condition #39 - Ichimoku
                elif index == 39:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['tenkan_sen_1h'] > dataframe['kijun_sen_1h'])
                    item_buy_logic.append(dataframe['close'] > dataframe['cloud_top_1h'])
                    item_buy_logic.append(dataframe['leading_senkou_span_a_1h'] > dataframe['leading_senkou_span_b_1h'])
                    item_buy_logic.append(dataframe['chikou_span_greater_1h'])
                    item_buy_logic.append(dataframe['ssl_up_1h'] > dataframe['ssl_down_1h'])
                    item_buy_logic.append(dataframe['close'] < dataframe['ssl_up_1h'])
                    item_buy_logic.append(dataframe['rsi_14_1h'] > dataframe['rsi_14_1h'].shift(12))
                    item_buy_logic.append(dataframe['cti'] < self.buy_39_cti_max)
                    item_buy_logic.append(dataframe['r_480_1h'] < self.buy_39_r_1h_max)
                    item_buy_logic.append(dataframe['cti_1h'] > self.buy_39_cti_1h_min)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_39_cti_1h_max)
                    # Start of trend
                    item_buy_logic.append(
                        (dataframe['leading_senkou_span_a_1h'].shift(12) < dataframe['leading_senkou_span_b_1h'].shift(12))
                    )

                # Condition #40
                elif index == 40:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['momdiv_buy_1h'] == True)
                    item_buy_logic.append(dataframe['cci'] < self.buy_40_cci_max)
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_40_rsi_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_40_r_14_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_40_cti_max)

                # Condition #41
                elif index == 41:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_200_1h'].shift(12) > dataframe['ema_200_1h'].shift(24))
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * self.buy_41_ma_offset_high)
                    item_buy_logic.append(dataframe['cti'] < self.buy_41_cti_max)
                    item_buy_logic.append(dataframe['cci'] < self.buy_41_cci_max)
                    item_buy_logic.append(dataframe['ewo_sma_1h'] > self.buy_41_ewo_1h_min)
                    item_buy_logic.append(dataframe['r_480_1h'] < self.buy_41_r_480_1h_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_41_crsi_1h_min)

                # Condition #42
                elif index == 42:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_200_1h'].shift(12) > dataframe['ema_200_1h'].shift(24))
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_42_ema_open_mult))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * self.buy_42_bb_offset))
                    item_buy_logic.append(dataframe['ewo_sma_1h'] > self.buy_42_ewo_1h_min)
                    item_buy_logic.append(dataframe['cti_1h'] > self.buy_42_cti_1h_min)
                    item_buy_logic.append(dataframe['r_480_1h'] < self.buy_42_r_480_1h_max)

                # Condition #43
                elif index == 43:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_200_1h'].shift(12) > dataframe['ema_200_1h'].shift(24))
                    item_buy_logic.append(dataframe['bb40_2_low'].shift().gt(0))
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * self.buy_43_bb40_bbdelta_close))
                    item_buy_logic.append(dataframe['closedelta'].gt(dataframe['close'] * self.buy_43_bb40_closedelta_close))
                    item_buy_logic.append(dataframe['tail'].lt(dataframe['bb40_2_delta'] * self.buy_43_bb40_tail_bbdelta))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))
                    item_buy_logic.append(dataframe['cti'] < self.buy_43_cti_max)
                    item_buy_logic.append(dataframe['r_480'] > self.buy_43_r_480_min)
                    item_buy_logic.append(dataframe['cti_1h'] > self.buy_43_cti_1h_min)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_43_cti_1h_max)
                    item_buy_logic.append(dataframe['r_480_1h'] > self.buy_43_r_480_1h_min)

                # Condition #44
                elif index == 44:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_16'] * self.buy_44_ma_offset))
                    item_buy_logic.append(dataframe['ewo_sma'] < self.buy_44_ewo_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_44_cti_max)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_44_crsi_1h_min)

                # Condition #45 - Long mode
                elif index == 45:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_low'].shift().gt(0))
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * self.buy_45_bb40_bbdelta_close))
                    item_buy_logic.append(dataframe['closedelta'].gt(dataframe['close'] * self.buy_45_bb40_closedelta_close))
                    item_buy_logic.append(dataframe['tail'].lt(dataframe['bb40_2_delta'] * self.buy_45_bb40_tail_bbdelta))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * self.buy_45_ma_offset)
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_45_ewo_min)
                    item_buy_logic.append(dataframe['ewo_sma_1h'] > self.buy_45_ewo_1h_min)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_45_cti_1h_max)
                    item_buy_logic.append(dataframe['r_480_1h'] < self.buy_45_r_480_1h_max)

                # Condition #46 - Long mode
                elif index == 46:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * self.buy_46_ema_open_mult))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['ewo_sma_1h'] > self.buy_46_ewo_1h_min)
                    item_buy_logic.append(dataframe['cti_1h'] > self.buy_46_cti_1h_min)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_46_cti_1h_max)

                # Condition #47 - Long mode
                elif index == 47:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_47_ewo_min)
                    item_buy_logic.append(dataframe['close'] < (dataframe['sma_30'] * self.buy_47_ma_offset))
                    item_buy_logic.append(dataframe['rsi_14'] < self.buy_47_rsi_14_max)
                    item_buy_logic.append(dataframe['cti'] < self.buy_47_cti_max)
                    item_buy_logic.append(dataframe['r_14'] < self.buy_47_r_14_max)
                    item_buy_logic.append(dataframe['ewo_sma_1h'] > self.buy_47_ewo_1h_min)
                    item_buy_logic.append(dataframe['cti_1h'] > self.buy_47_cti_1h_min)
                    item_buy_logic.append(dataframe['cti_1h'] < self.buy_47_cti_1h_max)

                # Condition #48 - Uptrend mode
                elif index == 48:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_200_1h'].shift(12) > dataframe['ema_200_1h'].shift(24))
                    item_buy_logic.append(dataframe['moderi_32'])
                    item_buy_logic.append(dataframe['moderi_64'])
                    item_buy_logic.append(dataframe['moderi_96'])

                    # Logic
                    item_buy_logic.append(dataframe['ewo_sma'] > self.buy_48_ewo_min)
                    item_buy_logic.append(dataframe['ewo_sma_1h'] > self.buy_48_ewo_1h_min)
                    item_buy_logic.append(dataframe['r_480'] > self.buy_48_r_480_min)
                    item_buy_logic.append(dataframe['r_480_1h'] > self.buy_48_r_480_1h_min)
                    item_buy_logic.append(dataframe['r_480_1h'] < self.buy_48_r_480_1h_max)
                    item_buy_logic.append(dataframe['r_480_1h'] > dataframe['r_480_1h'].shift(12))
                    item_buy_logic.append(dataframe['cti_1h'] > self.buy_48_cti_1h_min)
                    item_buy_logic.append(dataframe['crsi_1h'] > self.buy_48_crsi_1h_min)
                    item_buy_logic.append(dataframe['cti'].shift(1).rolling(12).min() < -0.5)
                    item_buy_logic.append(dataframe['cti'].shift(1).rolling(12).max() < 0.0)
                    item_buy_logic.append(dataframe['cti'].shift(1) < 0.0)
                    item_buy_logic.append(dataframe['cti'] > 0.0)

                item_buy_logic.append(dataframe['volume'] > 0)
                item_buy = reduce(lambda x, y: x & y, item_buy_logic)
                dataframe.loc[item_buy, 'buy_tag'] += f"{index} "
                conditions.append(item_buy)

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
        if self._should_hold_trade(trade, rate, sell_reason):
            return False

        self._remove_profit_target(pair)
        return True

    def _set_profit_target(self, pair: str, sell_reason: str, rate: float, current_time: "datetime"):
        self.target_profit_cache.data[pair] = {
            "rate": rate,
            "sell_reason": sell_reason,
            "time_profit_reached": current_time.isoformat()
        }
        self.target_profit_cache.save()

    def _remove_profit_target(self, pair: str):
        if self.target_profit_cache is not None:
            self.target_profit_cache.data.pop(pair, None)
            self.target_profit_cache.save()

    def _should_hold_trade(self, trade: "Trade", rate: float, sell_reason: str) -> bool:
        if self.config['runmode'].value not in ('live', 'dry_run'):
            return False

        if not self.holdSupportEnabled:
            return False

        # Just to be sure our hold data is loaded, should be a no-op call after the first bot loop
        self.load_hold_trades_config()

        if not self.hold_trades_cache:
            # Cache hasn't been setup, likely because the corresponding file does not exist, sell
            return False

        if not self.hold_trades_cache.data:
            # We have no pairs we want to hold until profit, sell
            return False

        # By default, no hold should be done
        hold_trade = False

        trade_ids: dict = self.hold_trades_cache.data.get("trade_ids")
        if trade_ids and trade.id in trade_ids:
            trade_profit_ratio = trade_ids[trade.id]
            current_profit_ratio = trade.calc_profit_ratio(rate)
            if sell_reason == "force_sell":
                formatted_profit_ratio = f"{trade_profit_ratio * 100}%"
                formatted_current_profit_ratio = f"{current_profit_ratio * 100}%"
                log.warning(
                    "Force selling %s even though the current profit of %s < %s",
                    trade, formatted_current_profit_ratio, formatted_profit_ratio
                )
                return False
            elif current_profit_ratio >= trade_profit_ratio:
                # This pair is on the list to hold, and we reached minimum profit, sell
                formatted_profit_ratio = f"{trade_profit_ratio * 100}%"
                formatted_current_profit_ratio = f"{current_profit_ratio * 100}%"
                log.warning(
                    "Selling %s because the current profit of %s >= %s",
                    trade, formatted_current_profit_ratio, formatted_profit_ratio
                )
                return False

            # This pair is on the list to hold, and we haven't reached minimum profit, hold
            hold_trade = True

        trade_pairs: dict = self.hold_trades_cache.data.get("trade_pairs")
        if trade_pairs and trade.pair in trade_pairs:
            trade_profit_ratio = trade_pairs[trade.pair]
            current_profit_ratio = trade.calc_profit_ratio(rate)
            if sell_reason == "force_sell":
                formatted_profit_ratio = f"{trade_profit_ratio * 100}%"
                formatted_current_profit_ratio = f"{current_profit_ratio * 100}%"
                log.warning(
                    "Force selling %s even though the current profit of %s < %s",
                    trade, formatted_current_profit_ratio, formatted_profit_ratio
                )
                return False
            elif current_profit_ratio >= trade_profit_ratio:
                # This pair is on the list to hold, and we reached minimum profit, sell
                formatted_profit_ratio = f"{trade_profit_ratio * 100}%"
                formatted_current_profit_ratio = f"{current_profit_ratio * 100}%"
                log.warning(
                    "Selling %s because the current profit of %s >= %s",
                    trade, formatted_current_profit_ratio, formatted_profit_ratio
                )
                return False

            # This pair is on the list to hold, and we haven't reached minimum profit, hold
            hold_trade = True

        return hold_trade

# Elliot Wave Oscillator
def ewo(dataframe, sma1_length=5, sma2_length=35):
    sma1 = ta.EMA(dataframe, timeperiod=sma1_length)
    sma2 = ta.EMA(dataframe, timeperiod=sma2_length)
    smadif = (sma1 - sma2) / dataframe['close'] * 100
    return smadif


def ewo_sma(dataframe, sma1_length=5, sma2_length=35):
    sma1 = ta.SMA(dataframe, timeperiod=sma1_length)
    sma2 = ta.SMA(dataframe, timeperiod=sma2_length)
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
    return vwma


# Modified Elder Ray Index
def moderi(dataframe: DataFrame, len_slow_ma: int = 32) -> Series:
    slow_ma = Series(ta.EMA(vwma(dataframe, length=len_slow_ma), timeperiod=len_slow_ma))
    return slow_ma >= slow_ma.shift(1)  # we just need true & false for ERI trend

# Exponential moving average of a volume weighted simple moving average
def ema_vwma_osc(dataframe, len_slow_ma):
    slow_ema = Series(ta.EMA(vwma(dataframe, len_slow_ma), len_slow_ma))

    return ((slow_ema - slow_ema.shift(1)) / slow_ema.shift(1)) * 100

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

    mavalue = f'MA_{MAtype}_{length}'
    atr = f'ATR_{period}'
    pm = f'pm_{period}_{multiplier}_{length}_{MAtype}'
    pmx = f'pmX_{period}_{multiplier}_{length}_{MAtype}'

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

# SSL Channels
def SSLChannels(dataframe, length = 7):
    ATR = ta.ATR(dataframe, timeperiod=14)
    smaHigh = dataframe['high'].rolling(length).mean() + ATR
    smaLow = dataframe['low'].rolling(length).mean() - ATR
    hlv = Series(np.where(dataframe['close'] > smaHigh, 1, np.where(dataframe['close'] < smaLow, -1, np.NAN)))
    hlv = hlv.ffill()
    sslDown = np.where(hlv < 0, smaHigh, smaLow)
    sslUp = np.where(hlv < 0, smaLow, smaHigh)
    return sslDown, sslUp

def pivot_points(dataframe: DataFrame, mode = 'fibonacci') -> Series:
    hlc3_pivot = (dataframe['high'] + dataframe['low'] + dataframe['close']).shift(1) / 3
    hl_range = (dataframe['high'] - dataframe['low']).shift(1)
    if mode == 'simple':
        res1 = hlc3_pivot * 2 - dataframe['low'].shift(1)
        sup1 = hlc3_pivot * 2 - dataframe['high'].shift(1)
        res2 = hlc3_pivot + (dataframe['high'] - dataframe['low']).shift()
        sup2 = hlc3_pivot - (dataframe['high'] - dataframe['low']).shift()
        res3 = hlc3_pivot * 2 + (dataframe['high'] - 2 * dataframe['low']).shift()
        sup3 = hlc3_pivot * 2 - (2 * dataframe['high'] - dataframe['low']).shift()
    elif mode == 'fibonacci':
        res1 = hlc3_pivot + 0.382 * hl_range
        sup1 = hlc3_pivot - 0.382 * hl_range
        res2 = hlc3_pivot + 0.618 * hl_range
        sup2 = hlc3_pivot - 0.618 * hl_range
        res3 = hlc3_pivot + 1 * hl_range
        sup3 = hlc3_pivot - 1 * hl_range

    return hlc3_pivot, res1, res2, res3, sup1, sup2, sup3

def HeikinAshi(dataframe, smooth_inputs = False, smooth_outputs = False, length = 10):
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


# Mom DIV
def momdiv(dataframe: DataFrame, mom_length: int = 10, bb_length: int = 20, bb_dev: float = 2.0, lookback: int = 30) -> DataFrame:
    mom: Series = ta.MOM(dataframe, timeperiod=mom_length)
    upperband, middleband, lowerband = ta.BBANDS(mom, timeperiod=bb_length, nbdevup=bb_dev, nbdevdn=bb_dev, matype=0)
    buy = qtpylib.crossed_below(mom, lowerband)
    sell = qtpylib.crossed_above(mom, upperband)
    hh = dataframe['high'].rolling(lookback).max()
    ll = dataframe['low'].rolling(lookback).min()
    coh = dataframe['high'] >= hh
    col = dataframe['low'] <= ll
    df = DataFrame({
            "momdiv_mom": mom,
            "momdiv_upperb": upperband,
            "momdiv_lowerb": lowerband,
            "momdiv_buy": buy,
            "momdiv_sell": sell,
            "momdiv_coh": coh,
            "momdiv_col": col,
        }, index=dataframe['close'].index)
    return df


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


class HoldsCache(Cache):

    @staticmethod
    def rapidjson_load_kwargs():
        return {
            "number_mode": rapidjson.NM_NATIVE,
            "object_hook": HoldsCache._object_hook,
        }

    @staticmethod
    def rapidjson_dump_kwargs():
        return {
            "number_mode": rapidjson.NM_NATIVE,
            "mapping_mode": rapidjson.MM_COERCE_KEYS_TO_STRINGS,
        }

    def save(self):
        raise RuntimeError("The holds cache does not allow programatical save")

    def process_loaded_data(self, data):
        trade_ids = data.get("trade_ids")
        trade_pairs = data.get("trade_pairs")

        if not trade_ids and not trade_pairs:
            return data

        open_trades = {}
        for trade in Trade.get_trades_proxy(is_open=True):
            open_trades[trade.id] = open_trades[trade.pair] = trade

        r_trade_ids = {}
        if trade_ids:
            if isinstance(trade_ids, dict):
                # New syntax
                for trade_id, profit_ratio in trade_ids.items():
                    if not isinstance(trade_id, int):
                        log.error(
                            "The trade_id(%s) defined under 'trade_ids' in %s is not an integer",
                            trade_id, self.path
                        )
                        continue
                    if not isinstance(profit_ratio, float):
                        log.error(
                            "The 'profit_ratio' config value(%s) for trade_id %s in %s is not a float",
                            profit_ratio,
                            trade_id,
                            self.path
                        )
                    if trade_id in open_trades:
                        formatted_profit_ratio = f"{profit_ratio * 100}%"
                        log.warning(
                            "The trade %s is configured to HOLD until the profit ratio of %s is met",
                            open_trades[trade_id],
                            formatted_profit_ratio
                        )
                        r_trade_ids[trade_id] = profit_ratio
                    else:
                        log.warning(
                            "The trade_id(%s) is no longer open. Please remove it from 'trade_ids' in %s",
                            trade_id,
                            self.path
                        )
            else:
                # Initial Syntax
                profit_ratio = data.get("profit_ratio")
                if profit_ratio:
                    if not isinstance(profit_ratio, float):
                        log.error(
                            "The 'profit_ratio' config value(%s) in %s is not a float",
                            profit_ratio,
                            self.path
                        )
                else:
                    profit_ratio = 0.005
                formatted_profit_ratio = f"{profit_ratio * 100}%"
                for trade_id in trade_ids:
                    if not isinstance(trade_id, int):
                        log.error(
                            "The trade_id(%s) defined under 'trade_ids' in %s is not an integer",
                            trade_id, self.path
                        )
                        continue
                    if trade_id in open_trades:
                        log.warning(
                            "The trade %s is configured to HOLD until the profit ratio of %s is met",
                            open_trades[trade_id],
                            formatted_profit_ratio
                        )
                        r_trade_ids[trade_id] = profit_ratio
                    else:
                        log.warning(
                            "The trade_id(%s) is no longer open. Please remove it from 'trade_ids' in %s",
                            trade_id,
                            self.path
                        )

        r_trade_pairs = {}
        if trade_pairs:
            for trade_pair, profit_ratio in trade_pairs.items():
                if not isinstance(trade_pair, str):
                    log.error(
                        "The trade_pair(%s) defined under 'trade_pairs' in %s is not a string",
                        trade_pair, self.path
                    )
                    continue
                if "/" not in trade_pair:
                    log.error(
                        "The trade_pair(%s) defined under 'trade_pairs' in %s does not look like "
                        "a valid '<TOKEN_NAME>/<STAKE_CURRENCY>' formatted pair.",
                        trade_pair, self.path
                    )
                    continue
                if not isinstance(profit_ratio, float):
                    log.error(
                        "The 'profit_ratio' config value(%s) for trade_pair %s in %s is not a float",
                        profit_ratio,
                        trade_pair,
                        self.path
                    )
                formatted_profit_ratio = f"{profit_ratio * 100}%"
                if trade_pair in open_trades:
                    log.warning(
                        "The trade %s is configured to HOLD until the profit ratio of %s is met",
                        open_trades[trade_pair],
                        formatted_profit_ratio
                    )
                else:
                    log.warning(
                        "The trade pair %s is configured to HOLD until the profit ratio of %s is met",
                        trade_pair,
                        formatted_profit_ratio
                    )
                r_trade_pairs[trade_pair] = profit_ratio

        r_data = {}
        if r_trade_ids:
            r_data["trade_ids"] = r_trade_ids
        if r_trade_pairs:
            r_data["trade_pairs"] = r_trade_pairs
        return r_data

    @staticmethod
    def _object_hook(data):
        _data = {}
        for key, value in data.items():
            try:
                key = int(key)
            except ValueError:
                pass
            _data[key] = value
        return _data
