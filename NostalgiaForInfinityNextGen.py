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
##                NostalgiaForInfinityV9 by iterativ                                                     ##
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
##   the timeframe (must be 15m).                                                                         ##
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


class NostalgiaForInfinityNextGen(IStrategy):
    INTERFACE_VERSION = 2

    # ROI table:
    minimal_roi = {
        "0": 100.0,
    }

    stoploss = -0.50

    # Trailing stoploss (not used)
    trailing_stop = False
    trailing_only_offset_is_reached = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.03

    use_custom_stoploss = False

    # Optimal timeframe for the strategy.
    timeframe = '15m'
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
        #############
    }

    sell_params = {
        #############
        # Enable/Disable conditions
        "sell_condition_1_enable": True,
        #############
    }

    #############################################################
    buy_protection_params = {
        1: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "26",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "28",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.36,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        2: {
            "ema_fast"                  : False,
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
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.06,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.45,
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        3: {
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
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.035,
            "safe_dips_threshold_2"     : 0.08,
            "safe_dips_threshold_12"    : 0.2,
            "safe_dips_threshold_144"   : 0.28,
            "safe_pump_6h_threshold"    : 0.45,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        4: {
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
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.045,
            "safe_dips_threshold_2"     : 0.12,
            "safe_dips_threshold_12"    : 0.34,
            "safe_dips_threshold_144"   : 0.48,
            "safe_pump_6h_threshold"    : None,
            "safe_pump_12h_threshold"   : 0.42,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "sup3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.97,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        5: {
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
            "safe_dips_threshold_0"     : 0.03,
            "safe_dips_threshold_2"     : 0.14,
            "safe_dips_threshold_12"    : 0.28,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : None,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.5,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "sup3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.3
        },
        6: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : True,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "50",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.08,
            "safe_dips_threshold_2"     : 0.16,
            "safe_dips_threshold_12"    : 0.4,
            "safe_dips_threshold_144"   : 0.8,
            "safe_pump_6h_threshold"    : None,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.3,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.15
        },
        7: {
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
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.05,
            "safe_dips_threshold_2"     : 0.1,
            "safe_dips_threshold_12"    : 0.2,
            "safe_dips_threshold_144"   : 0.6,
            "safe_pump_6h_threshold"    : None,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.1
        },
        8: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.04,
            "safe_dips_threshold_2"     : 0.18,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump_6h_threshold"    : None,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 0.9,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.15
        },
        9: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.04,
            "safe_dips_threshold_2"     : 0.1,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.38,
            "safe_pump_6h_threshold"    : None,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 0.9,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        10: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.03,
            "safe_dips_threshold_2"     : 0.07,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.38,
            "safe_pump_6h_threshold"    : 0.2,
            "safe_pump_12h_threshold"   : 0.3,
            "safe_pump_24h_threshold"   : 0.5,
            "safe_pump_36h_threshold"   : 0.6,
            "safe_pump_48h_threshold"   : 0.9,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        11: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.04,
            "safe_dips_threshold_2"     : 0.08,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.38,
            "safe_pump_6h_threshold"    : 0.2,
            "safe_pump_12h_threshold"   : 0.4,
            "safe_pump_24h_threshold"   : 0.6,
            "safe_pump_36h_threshold"   : 0.8,
            "safe_pump_48h_threshold"   : 0.9,
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
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.04,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.32,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.2,
            "safe_pump_12h_threshold"   : 0.4,
            "safe_pump_24h_threshold"   : 0.6,
            "safe_pump_36h_threshold"   : 0.8,
            "safe_pump_48h_threshold"   : 0.9,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.9,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        13: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.04,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.32,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.3,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.74,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : True,
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
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.06,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.24,
            "safe_dips_threshold_144"   : 0.38,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.9,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        15: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.06,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.24,
            "safe_dips_threshold_144"   : 0.38,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.9,
            "safe_pump_48h_threshold"   : None,
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
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.06,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.24,
            "safe_dips_threshold_144"   : 0.38,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : 0.5,
            "safe_pump_24h_threshold"   : 0.7,
            "safe_pump_36h_threshold"   : 1.1,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.1
        }
    }

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

    # Sell
    sell_condition_1_enable = True

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

    sell_rsi_bb_1 = 74.0
    sell_rsi_bb_2 = 75.0

    sell_rsi_main_3 = 78.0

    sell_dual_rsi_rsi_4 = 68.4
    sell_dual_rsi_rsi_1h_4 = 74.6

    sell_ema_relative_5 = 0.024
    sell_rsi_diff_5 = 4.4

    sell_rsi_under_6 = 74.0

    sell_rsi_1h_7 = 76.7

    sell_bb_relative_8 = 1.1

    #############################################################


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

    def is_support(self, row_data) -> bool:
        if row_data[0] > row_data[1] and row_data[1] > row_data[2] and row_data[2] < row_data[3] and row_data[3] < row_data[4]:
            return True
        return False

    def is_resistance(self, row_data) -> bool:
        if row_data[0] < row_data[1] and row_data[1] < row_data[2] and row_data[2] > row_data[3] and row_data[3] > row_data[4]:
            return True
        return False

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

    def sell_signals(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Sell signal 1
        if (last_candle['rsi_14'] > 78.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) and (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']) and (previous_candle_4['close'] > previous_candle_4['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_1_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_1_2_1'
                elif (current_profit < -0.05) and (max_loss > 0.12):
                    return True, 'sell_signal_1_2_2'

        # Sell signal 2
        elif (last_candle['rsi_14'] > 79.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_2_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_2_2_1'
                elif (current_profit < -0.05) and (max_loss > 0.12):
                    return True, 'sell_signal_2_2_2'

        # Sell signal 3
        elif (last_candle['rsi_14'] > 82.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_3_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_3_2_1'
                elif (current_profit < -0.05) and (max_loss > 0.12):
                    return True, 'sell_signal_3_2_2'

        # Sell signal 4
        elif (last_candle['rsi_14'] > 78.0) and (last_candle['rsi_14_1h'] > 78.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_4_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_4_2_1'
                elif (current_profit < -0.05) and (max_loss > 0.12):
                    return True, 'sell_signal_4_2_2'

        # Sell signal 6
        elif (last_candle['close'] < last_candle['ema_200']) and (last_candle['close'] > last_candle['ema_50']) and (last_candle['rsi_14'] > 79.5):
            if (current_profit > 0.01):
                return True, 'sell_signal_6_1'
            elif (current_profit < -0.05) and (max_loss > 0.12):
                return True, 'sell_signal_6_2'

        # Sell signal 7
        elif (last_candle['rsi_14_1h'] > 80.0) and (last_candle['crossed_below_ema_12_26']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_7_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_7_2_1'
                elif (current_profit < -0.05) and (max_loss > 0.12):
                    return True, 'sell_signal_7_2_2'

        # Sell signal 8
        elif (last_candle['close'] > last_candle['bb20_2_upp_1h'] * 1.08):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_8_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_8_2_1'
                elif (current_profit < -0.05) and (max_loss > 0.12):
                    return True, 'sell_signal_8_2_2'

        return False, None

    def sell_stoploss(self, current_profit: float, max_profit: float, max_loss: float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        # Under & near EMA200, local uptrend move
        if (
                (current_profit < -0.05)
                and (last_candle['close'] < last_candle['ema_200'])
                and (last_candle['cmf'] < 0.0)
                and (((last_candle['ema_200'] - last_candle['close']) / last_candle['close']) < 0.015)
                and last_candle['rsi_14'] > previous_candle_1['rsi_14']
                and (last_candle['rsi_14'] > (last_candle['rsi_14_1h'] + 10.0))
                and (last_candle['sma_200_dec_24'])
                and (current_time - timedelta(minutes=2880) > trade.open_date_utc)
        ):
            return True, 'sell_stoploss_u_e_1'

        # Under EMA200, local strong uptrend move
        if (
                (current_profit < -0.08)
                and (last_candle['close'] < last_candle['ema_200'])
                and (last_candle['cmf'] < 0.0)
                and last_candle['rsi_14'] > previous_candle_1['rsi_14']
                and (last_candle['rsi_14'] > (last_candle['rsi_14_1h'] + 24.0))
                and (last_candle['sma_200_dec_20'])
                and (last_candle['sma_200_dec_24'])
                and (current_time - timedelta(minutes=2880) > trade.open_date_utc)
        ):
            return True, 'sell_stoploss_u_e_2'

        # Under EMA200, pair negative, low max rate
        if (
                (current_profit < -0.08)
                and (max_profit < 0.04)
                and (last_candle['close'] < last_candle['ema_200'])
                and (last_candle['ema_25'] < last_candle['ema_50'])
                and (last_candle['sma_200_dec_20'])
                and (last_candle['sma_200_dec_24'])
                and (last_candle['sma_200_dec_20_1h'])
                and (last_candle['ema_vwma_osc_32'] < 0.0)
                and (last_candle['ema_vwma_osc_64'] < 0.0)
                and (last_candle['ema_vwma_osc_96'] < 0.0)
                and (last_candle['cmf'] < -0.0)
                and (last_candle['cmf_1h'] < -0.0)
                and (last_candle['close'] < last_candle['sup_level_1h'])
                and (last_candle['btc_not_downtrend_1h'] == False)
                and (current_time - timedelta(minutes=1440) > trade.open_date_utc)
        ):
            return True, 'sell_stoploss_u_e_doom'

        # Under EMA200, pair and BTC negative, low max rate
        if (
                (-0.05 > current_profit > -0.09)
                and (last_candle['btc_not_downtrend_1h'] == False)
                and (last_candle['ema_vwma_osc_32'] < 0.0)
                and (last_candle['ema_vwma_osc_64'] < 0.0)
                and (max_profit < 0.005)
                and (max_loss < 0.09)
                and (last_candle['sma_200_dec_24'])
                and (last_candle['cmf'] < -0.0)
                and (last_candle['close'] < last_candle['ema_200'])
                and (last_candle['ema_25'] < last_candle['ema_50'])
                and (last_candle['cti'] < -0.8)
                and (last_candle['r_480'] < -50.0)
        ):
            return True, 'sell_stoploss_u_e_b_1'

        # Under EMA200, pair and BTC negative, CTI, Elder Ray Index negative, normal max rate
        elif (
                (-0.1 > current_profit > -0.2)
                and (last_candle['btc_not_downtrend_1h'] == False)
                and (last_candle['ema_vwma_osc_32'] < 0.0)
                and (last_candle['ema_vwma_osc_64'] < 0.0)
                and (last_candle['ema_vwma_osc_96'] < 0.0)
                and (max_profit < 0.05)
                and (max_loss < 0.2)
                and (last_candle['sma_200_dec_24'])
                and (last_candle['sma_200_dec_20_1h'])
                and (last_candle['cmf'] < -0.45)
                and (last_candle['close'] < last_candle['ema_200'])
                and (last_candle['ema_25'] < last_candle['ema_50'])
                and (last_candle['cti'] < -0.8)
                and (last_candle['r_480'] < -97.0)
        ):
            return True, 'signal_stoploss_u_e_b_2'

        return False, None

    def sell_over_main(self, current_profit: float, last_candle) -> tuple:
        if last_candle['close'] > last_candle['ema_200']:
            if (last_candle['moderi_96']):
                if current_profit >= 0.20:
                    if last_candle['rsi_14'] < 30.0:
                        return True, 'sell_profit_o_bull_12_1'
                    elif (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < -0.28) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_12_2'
                    elif (last_candle['rsi_14'] < 31.0) and (last_candle['rsi_14_1h'] < 36.0):
                        return True, 'sell_profit_o_bull_12_3'
                    elif (last_candle['rsi_14'] < 31.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_12_4'
                elif 0.20 > current_profit >= 0.12:
                    if last_candle['rsi_14'] < 32.0:
                        return True, 'sell_profit_o_bull_11_1'
                    elif (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < -0.24) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_11_2'
                    elif (last_candle['rsi_14'] < 33.0) and (last_candle['rsi_14_1h'] < 38.0):
                        return True, 'sell_profit_o_bull_11_3'
                    elif (last_candle['rsi_14'] < 33.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_11_4'
                elif 0.12 > current_profit >= 0.1:
                    if last_candle['rsi_14'] < 40.0:
                        return True, 'sell_profit_o_bull_10_1'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.22) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_10_2'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['rsi_14_1h'] < 40.0):
                        return True, 'sell_profit_o_bull_10_3'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_10_4'
                elif 0.1 > current_profit >= 0.09:
                    if last_candle['rsi_14'] < 50.0:
                        return True, 'sell_profit_o_bull_9_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 49.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_9_2'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['rsi_14_1h'] < 43.0):
                        return True, 'sell_profit_o_bull_9_3'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_9_4'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 49.0):
                        return True, 'sell_profit_o_bull_8_1'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 49.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_8_2'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['rsi_14_1h'] < 42.0):
                        return True, 'sell_profit_o_bull_8_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_8_4'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_o_bull_7_1'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 49.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_7_2'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['rsi_14_1h'] < 41.0):
                        return True, 'sell_profit_o_bull_7_3'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_7_4'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_o_bull_6_1'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 49.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_6_2'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['rsi_14_1h'] < 40.0):
                        return True, 'sell_profit_o_bull_6_3'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_o_bull_5_1'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.13) and (last_candle['rsi_14_1h'] < 49.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_5_2'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_1h'] < 39.0):
                        return True, 'sell_profit_o_bull_5_3'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_o_bull_4_1'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.14) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_4_2'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['rsi_14_1h'] < 38.0):
                        return True, 'sell_profit_o_bull_4_3'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 38.0):
                        return True, 'sell_profit_o_bull_3_1'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_3_2'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['rsi_14_1h'] < 37.0):
                        return True, 'sell_profit_o_bull_3_3'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_2_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_o_bull_2_1'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.16) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_2_2'
                    elif (last_candle['rsi_14'] < 35.0) and (last_candle['rsi_14_1h'] < 36.0):
                        return True, 'sell_profit_o_bull_2_3'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_2_4'
                elif 0.02 > current_profit >= 0.012:
                    if (last_candle['rsi_14'] < 32.0):
                        return True, 'sell_profit_o_bull_1_1'
                    elif (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bull_1_2'
                    elif (last_candle['rsi_14'] < 33.0) and (last_candle['rsi_14_1h'] < 35.0):
                        return True, 'sell_profit_o_bull_1_3'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bull_1_4'
            else:
                if current_profit >= 0.20:
                    if last_candle['rsi_14'] < 31.0:
                        return True, 'sell_profit_o_bear_12_1'
                    elif (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < -0.28) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_12_2'
                    elif (last_candle['rsi_14'] < 32.0) and (last_candle['rsi_14_1h'] < 36.0):
                        return True, 'sell_profit_o_bear_12_3'
                    elif (last_candle['rsi_14'] < 32.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_12_4'
                elif 0.20 > current_profit >= 0.12:
                    if last_candle['rsi_14'] < 33.0:
                        return True, 'sell_profit_o_bear_11_1'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.24) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_11_2'
                    elif (last_candle['rsi_14'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                        return True, 'sell_profit_o_bear_11_3'
                    elif (last_candle['rsi_14'] < 34.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_11_4'
                elif 0.12 > current_profit >= 0.10:
                    if last_candle['rsi_14'] < 41.0:
                        return True, 'sell_profit_o_bear_10_1'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.22) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_10_2'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['rsi_14_1h'] < 40.0):
                        return True, 'sell_profit_o_bear_10_3'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_10_4'
                elif 0.10 > current_profit >= 0.09:
                    if last_candle['rsi_14'] < 51.0:
                        return True, 'sell_profit_o_bear_9_1'
                    elif (last_candle['rsi_14'] < 57.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_9_2'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['rsi_14_1h'] < 43.0):
                        return True, 'sell_profit_o_bear_9_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_9_4'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_o_bear_8_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_8_2'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['rsi_14_1h'] < 42.0):
                        return True, 'sell_profit_o_bear_8_3'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_8_4'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 49.0):
                        return True, 'sell_profit_o_bear_7_1'
                    elif (last_candle['rsi_14'] < 55.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_7_2'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['rsi_14_1h'] < 41.0):
                        return True, 'sell_profit_o_bear_7_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_7_4'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_o_bear_6_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_6_2'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['rsi_14_1h'] < 40.0):
                        return True, 'sell_profit_o_bear_6_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_o_bear_5_1'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_5_2'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_1h'] < 39.0):
                        return True, 'sell_profit_o_bear_5_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_o_bear_4_1'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.13) and (last_candle['rsi_14_1h'] < 49.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_4_2'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_1h'] < 38.0):
                        return True, 'sell_profit_o_bear_4_3'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 39.0):
                        return True, 'sell_profit_o_bear_3_1'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.14) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_3_2'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['rsi_14_1h'] < 37.0):
                        return True, 'sell_profit_o_bear_3_3'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 35.0):
                        return True, 'sell_profit_o_bear_2_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_2_2'
                    elif (last_candle['rsi_14'] < 36.0) and (last_candle['rsi_14_1h'] < 36.0):
                        return True, 'sell_profit_o_bear_2_3'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_2_4'
                elif 0.02 > current_profit >= 0.012:
                    if (last_candle['rsi_14'] < 33.0):
                        return True, 'sell_profit_o_bear_1_1'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_1_2'
                    elif (last_candle['rsi_14'] < 34.0) and (last_candle['rsi_14_1h'] < 35.0):
                        return True, 'sell_profit_o_bear_1_3'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_o_bear_1_4'

        return False, None

    def sell_under_main(self, current_profit: float, last_candle) -> tuple:
        if last_candle['close'] < last_candle['ema_200']:
            if (last_candle['moderi_96']):
                if current_profit >= 0.20:
                    if last_candle['rsi_14'] < 31.0:
                        return True, 'signal_profit_u_bull_12_1'
                    elif (last_candle['rsi_14'] < 32.0) and (last_candle['cmf'] < -0.28) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_12_2'
                    elif (last_candle['rsi_14'] < 33.0) and (last_candle['rsi_14_1h'] < 36.0):
                        return True, 'sell_profit_u_bull_12_3'
                    elif (last_candle['rsi_14'] < 32.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_12_4'
                elif 0.20 > current_profit >= 0.12:
                    if last_candle['rsi_14'] < 33.0:
                        return True, 'sell_profit_u_bull_11_1'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.24) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_11_2'
                    elif (last_candle['rsi_14'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                        return True, 'sell_profit_u_bull_11_3'
                    elif (last_candle['rsi_14'] < 34.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_11_4'
                elif 0.12 > current_profit >= 0.10:
                    if last_candle['rsi_14'] < 41.0:
                        return True, 'sell_profit_u_bull_10_1'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.22) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_10_2'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['rsi_14_1h'] < 40.0):
                        return True, 'sell_profit_u_bull_10_3'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_10_4'
                elif 0.10 > current_profit >= 0.09:
                    if last_candle['rsi_14'] < 51.0:
                        return True, 'sell_profit_u_bull_9_1'
                    elif (last_candle['rsi_14'] < 55.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_9_2'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['rsi_14_1h'] < 43.0):
                        return True, 'sell_profit_u_bull_9_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_9_4'
                elif 0.09 > current_profit >= 0.08:
                    if last_candle['rsi_14'] < 50.0:
                        return True, 'sell_profit_u_bull_8_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_8_2'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['rsi_14_1h'] < 42.0):
                        return True, 'sell_profit_u_bull_8_3'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_8_4'
                elif 0.08 > current_profit >= 0.07:
                    if last_candle['rsi_14'] < 49.0:
                        return True, 'sell_profit_u_bull_7_1'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_7_2'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['rsi_14_1h'] < 41.0):
                        return True, 'sell_profit_u_bull_7_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_7_4'
                elif 0.07 > current_profit >= 0.06:
                    if last_candle['rsi_14'] < 47.0:
                        return True, 'sell_profit_u_bull_6_1'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_6_2'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['rsi_14_1h'] < 40.0):
                        return True, 'sell_profit_u_bull_6_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if last_candle['rsi_14'] < 45.0:
                        return True, 'sell_profit_u_bull_5_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.13) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_5_2'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_1h'] < 39.0):
                        return True, 'sell_profit_u_bull_5_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if last_candle['rsi_14'] < 43.0:
                        return True, 'sell_profit_u_bull_4_1'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.14) and (last_candle['rsi_14_1h'] < 49.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_4_2'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_1h'] < 38.0):
                        return True, 'sell_profit_u_bull_4_3'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if last_candle['rsi_14'] < 39.0:
                        return True, 'sell_profit_u_bull_3_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_3_2'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['rsi_14_1h'] < 37.0):
                        return True, 'sell_profit_u_bull_3_3'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if last_candle['rsi_14'] < 35.0:
                        return True, 'sell_profit_u_bull_2_1'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.16) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_2_2'
                    elif (last_candle['rsi_14'] < 36.0) and (last_candle['rsi_14_1h'] < 36.0):
                        return True, 'sell_profit_u_bull_2_3'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 33.0):
                        return True, 'sell_profit_u_bull_1_1'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bull_1_2'
                    elif (last_candle['rsi_14'] < 34.0) and (last_candle['rsi_14_1h'] < 35.0):
                        return True, 'sell_profit_u_bull_1_3'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bull_1_4'
            else:
                if current_profit >= 0.20:
                    if last_candle['rsi_14'] < 32.0:
                        return True, 'sell_profit_u_bear_12_1'
                    elif (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < -0.28) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bear_12_2'
                    elif (last_candle['rsi_14'] < 33.0) and (last_candle['rsi_14_1h'] < 36.0):
                        return True, 'sell_profit_u_bear_12_3'
                    elif (last_candle['rsi_14'] < 33.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_12_4'
                elif 0.20 > current_profit >= 0.12:
                    if last_candle['rsi_14'] < 34.0:
                        return True, 'sell_profit_u_bear_11_1'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.24) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bear_11_2'
                    elif (last_candle['rsi_14'] < 35.0) and (last_candle['rsi_14_1h'] < 38.0):
                        return True, 'sell_profit_u_bear_11_3'
                    elif (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_11_4'
                elif 0.12 > current_profit >= 0.10:
                    if last_candle['rsi_14'] < 42.0:
                        return True, 'sell_profit_u_bear_10_1'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.22) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bear_10_2'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['rsi_14_1h'] < 40.0):
                        return True, 'sell_profit_u_bear_10_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_10_4'
                elif 0.10 > current_profit >= 0.09:
                    if last_candle['rsi_14'] < 54.0:
                        return True, 'sell_profit_u_bear_9_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 51.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_o_bear_9_2'
                    elif (last_candle['rsi_14'] < 55.0) and (last_candle['rsi_14_1h'] < 43.0):
                        return True, 'sell_profit_u_bear_9_3'
                    elif (last_candle['rsi_14'] < 55.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_9_4'
                elif 0.09 > current_profit >= 0.08:
                    if last_candle['rsi_14'] < 52.0:
                        return True, 'sell_profit_u_bear_8_1'
                    elif (last_candle['rsi_14'] < 57.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 51.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bear_8_2'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['rsi_14_1h'] < 42.0):
                        return True, 'sell_profit_u_bear_8_3'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_8_4'
                elif 0.08 > current_profit >= 0.07:
                    if last_candle['rsi_14'] < 50.0:
                        return True, 'sell_profit_u_bear_7_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 51.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bear_7_2'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['rsi_14_1h'] < 41.0):
                        return True, 'sell_profit_u_bear_7_3'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_7_4'
                elif 0.07 > current_profit >= 0.06:
                    if last_candle['rsi_14'] < 48.0:
                        return True, 'sell_profit_u_bear_6_1'
                    elif (last_candle['rsi_14'] < 55.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 51.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bear_6_2'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['rsi_14_1h'] < 40.0):
                        return True, 'sell_profit_u_bear_6_3'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if last_candle['rsi_14'] < 46.0:
                        return True, 'sell_profit_u_bear_5_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12) and (last_candle['rsi_14_1h'] < 51.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bear_5_2'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['rsi_14_1h'] < 39.0):
                        return True, 'sell_profit_u_bear_5_3'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if last_candle['rsi_14'] < 44.0:
                        return True, 'sell_profit_u_bear_4_1'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['cmf'] < -0.13) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bear_4_2'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_1h'] < 38.0):
                        return True, 'sell_profit_u_bear_4_3'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if last_candle['rsi_14'] < 40.0:
                        return True, 'sell_profit_u_bear_3_1'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.14) and (last_candle['rsi_14_1h'] < 49.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bear_3_2'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['rsi_14_1h'] < 37.0):
                        return True, 'sell_profit_u_bear_3_3'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if last_candle['rsi_14'] < 36.0:
                        return True, 'sell_profit_u_bear_2_1'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bear_2_2'
                    elif (last_candle['rsi_14'] < 37.0) and (last_candle['rsi_14_1h'] < 36.0):
                        return True, 'sell_profit_u_bear_2_3'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_u_bear_1_1'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']):
                        return True, 'sell_profit_u_bear_1_2'
                    elif (last_candle['rsi_14'] < 35.0) and (last_candle['rsi_14_1h'] < 35.0):
                        return True, 'sell_profit_u_bear_1_3'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.15) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['ema_12'] < last_candle['ema_26']) and (last_candle['ema_25'] < last_candle['ema_50']) and (last_candle['close'] < last_candle['sup_level_1h']):
                        return True, 'sell_profit_u_bear_1_4'

        return False, None

    def sell_r(self, current_profit: float, last_candle) -> tuple:
        if 0.02 > current_profit >= 0.012:
            if last_candle['r_480'] > -0.4:
                return True, 'sell_profit_w_1_1'
            elif (last_candle['r_480'] > -4.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_1_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 44.0):
                return True, 'sell_profit_w_1_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 81.0):
                return True, 'sell_profit_w_1_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.96):
                return True, 'sell_profit_w_1_5'
            elif (last_candle['r_480'] > -4.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['r_480_1h'] > -3.0):
                return True, 'sell_profit_w_1_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_1_7'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] > 80.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_1_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.88) and (last_candle['cci'] > 190.0) and (last_candle['r_480_1h'] > -8.0):
                return True, 'sell_profit_w_1_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.95) and (last_candle['rsi_14'] > 75.0):
                return True, 'sell_profit_w_1_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.9) and (last_candle['cci'] > 150.0) and (last_candle['r_480'] < -50.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_1_11'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] < 46.0) and (last_candle['cmf_1h'] < -0.25):
                return True, 'sell_profit_w_1_12'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 400.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_1_13'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 320.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_1_14'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_480_1h'] > -12.0) and (last_candle['rsi_14'] > 79.5) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_1_15'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] < 40.0) and (last_candle['rsi_14_1h'] < 42.0):
                return True, 'sell_profit_w_1_16'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_1_17'
        elif 0.03 > current_profit >= 0.02:
            if last_candle['r_480'] > -0.5:
                return True, 'sell_profit_w_2_1'
            elif (last_candle['r_480'] > -4.5) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_2_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 46.0):
                return True, 'sell_profit_w_2_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 80.5):
                return True, 'sell_profit_w_2_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.958):
                return True, 'sell_profit_w_2_5'
            elif (last_candle['r_480'] > -5.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['r_480_1h'] > -3.5):
                return True, 'sell_profit_w_2_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_2_7'
            elif (last_candle['r_14'] > -0.2) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_2_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.86) and (last_candle['cci'] > 180.0) and (last_candle['r_480_1h'] > -10.0):
                return True, 'sell_profit_w_2_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.93) and (last_candle['rsi_14'] > 73.0):
                return True, 'sell_profit_w_2_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.88) and (last_candle['cci'] > 140.0) and (last_candle['r_480'] < -50.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_2_11'
            elif (last_candle['r_14'] > -0.5) and (last_candle['rsi_14'] < 48.0) and (last_candle['cmf_1h'] < -0.23):
                return True, 'sell_profit_w_2_12'
            elif (last_candle['r_14'] >= -3.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cci'] > 360.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_2_13'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 280.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_2_14'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_480_1h'] > -14.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 310.0):
                return True, 'sell_profit_w_2_15'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_1h'] < 44.0):
                return True, 'sell_profit_w_2_16'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] < 52.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 42.0):
                return True, 'sell_profit_w_2_17'
        elif 0.04 > current_profit >= 0.03:
            if last_candle['r_480'] > -0.6:
                return True, 'sell_profit_w_3_1'
            elif (last_candle['r_480'] > -5.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_3_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 48.0):
                return True, 'sell_profit_w_3_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 80.0):
                return True, 'sell_profit_w_3_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.956):
                return True, 'sell_profit_w_3_5'
            elif (last_candle['r_480'] > -6.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['r_480_1h'] > -4.0):
                return True, 'sell_profit_w_3_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_3_7'
            elif (last_candle['r_14'] > -0.4) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_3_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.84) and (last_candle['cci'] > 170.0) and (last_candle['r_480_1h'] > -12.0):
                return True, 'sell_profit_w_3_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.92) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_3_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.87) and (last_candle['cci'] > 130.0) and (last_candle['r_480'] < -50.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_3_11'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] < 50.0) and (last_candle['cmf_1h'] < -0.22):
                return True, 'sell_profit_w_3_12'
            elif (last_candle['r_14'] >= -6.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 320.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_3_13'
            elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_3_14'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_480_1h'] > -16.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cci'] > 300.0):
                return True, 'sell_profit_w_3_15'
            elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['rsi_14_1h'] < 46.0):
                return True, 'sell_profit_w_3_16'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] < 56.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 46.0):
                return True, 'sell_profit_w_3_17'
        elif 0.05 > current_profit >= 0.04:
            if last_candle['r_480'] > -0.7:
                return True, 'sell_profit_w_4_1'
            elif (last_candle['r_480'] > -5.5) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_4_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 50.0):
                return True, 'sell_profit_w_4_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 79.5):
                return True, 'sell_profit_w_4_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.954):
                return True, 'sell_profit_w_4_5'
            elif (last_candle['r_480'] > -7.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['r_480_1h'] > -4.5):
                return True, 'sell_profit_w_4_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 76.5) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_4_7'
            elif (last_candle['r_14'] > -0.5) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_4_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.83) and (last_candle['cci'] > 170.0) and (last_candle['r_480_1h'] > -13.0):
                return True, 'sell_profit_w_4_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.91) and (last_candle['rsi_14'] > 71.0):
                return True, 'sell_profit_w_4_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.86) and (last_candle['cci'] > 120.0) and (last_candle['r_480'] < -50.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_4_11'
            elif (last_candle['r_14'] > -1.5) and (last_candle['rsi_14'] < 54.0) and (last_candle['cmf_1h'] < -0.21):
                return True, 'sell_profit_w_4_12'
            elif (last_candle['r_14'] >= -9.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 280.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_4_13'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_4_14'
            elif (last_candle['r_14'] > -12.0) and (last_candle['r_480_1h'] > -18.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 290.0):
                return True, 'sell_profit_w_4_15'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] < 52.0) and (last_candle['rsi_14_1h'] < 48.0):
                return True, 'sell_profit_w_4_16'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] < 57.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 47.0):
                return True, 'sell_profit_w_4_17'
        elif 0.06 > current_profit >= 0.05:
            if last_candle['r_480'] > -1.0:
                return True, 'sell_profit_w_5_1'
            elif (last_candle['r_480'] > -6.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_5_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 52.0):
                return True, 'sell_profit_w_5_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_profit_w_5_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.952):
                return True, 'sell_profit_w_5_5'
            elif (last_candle['r_480'] > -8.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['r_480_1h'] > -5.0):
                return True, 'sell_profit_w_5_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_5_7'
            elif (last_candle['r_14'] > -0.6) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_5_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.82) and (last_candle['cci'] > 170.0) and (last_candle['r_480_1h'] > -14.0):
                return True, 'sell_profit_w_5_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.92) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_5_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 120.0) and (last_candle['r_480'] < -45.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_5_11'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] < 56.0) and (last_candle['cmf_1h'] < -0.2):
                return True, 'sell_profit_w_5_12'
            elif (last_candle['r_14'] >= -6.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 300.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_5_13'
            elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 240.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_5_14'
            elif (last_candle['r_14'] > -14.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 280.0):
                return True, 'sell_profit_w_5_15'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] < 56.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_16'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] < 54.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 44.0):
                return True, 'sell_profit_w_5_17'
        elif 0.07 > current_profit >= 0.06:
            if last_candle['r_480'] > -2.0:
                return True, 'sell_profit_w_6_1'
            elif (last_candle['r_480'] > -6.5) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_6_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 53.0):
                return True, 'sell_profit_w_6_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 78.5):
                return True, 'sell_profit_w_6_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.95):
                return True, 'sell_profit_w_6_5'
            elif (last_candle['r_480'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['r_480_1h'] > -6.0):
                return True, 'sell_profit_w_6_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 75.5) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_6_7'
            elif (last_candle['r_14'] > -0.7) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_6_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.83) and (last_candle['cci'] > 180.0) and (last_candle['r_480_1h'] > -12.0):
                return True, 'sell_profit_w_6_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.93) and (last_candle['rsi_14'] > 73.0):
                return True, 'sell_profit_w_6_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.84) and (last_candle['cci'] > 100.0) and (last_candle['r_480'] < -45.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_6_11'
            elif (last_candle['r_14'] > -2.5) and (last_candle['rsi_14'] < 58.0) and (last_candle['cmf_1h'] < -0.19):
                return True, 'sell_profit_w_6_12'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 320.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_6_13'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 260.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_6_14'
            elif (last_candle['r_14'] > -12.0) and (last_candle['r_480_1h'] > -18.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 290.0):
                return True, 'sell_profit_w_6_15'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] < 52.0) and (last_candle['rsi_14_1h'] < 48.0):
                return True, 'sell_profit_w_6_16'
            elif (last_candle['r_14'] > -7.0) and (last_candle['rsi_14'] < 52.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 43.0):
                return True, 'sell_profit_w_6_17'
        elif 0.08 > current_profit >= 0.07:
            if last_candle['r_480'] > -2.2:
                return True, 'sell_profit_w_7_1'
            elif (last_candle['r_480'] > -7.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_7_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 52.0):
                return True, 'sell_profit_w_7_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 78.0):
                return True, 'sell_profit_w_7_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.952):
                return True, 'sell_profit_w_7_5'
            elif (last_candle['r_480'] > -12.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['r_480_1h'] > -7.0):
                return True, 'sell_profit_w_7_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_7_7'
            elif (last_candle['r_14'] > -0.8) and (last_candle['rsi_14'] > 62.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_7_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.84) and (last_candle['cci'] > 180.0) and (last_candle['r_480_1h'] > -10.0):
                return True, 'sell_profit_w_7_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.94) and (last_candle['rsi_14'] > 74.0):
                return True, 'sell_profit_w_7_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.83) and (last_candle['cci'] > 100.0) and (last_candle['r_480'] < -45.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_7_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] < 60.0) and (last_candle['cmf_1h'] < -0.18):
                return True, 'sell_profit_w_7_12'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 340.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_7_13'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 280.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_7_14'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_480_1h'] > -16.0) and (last_candle['rsi_14'] > 77.5) and (last_candle['cci'] > 300.0):
                return True, 'sell_profit_w_7_15'
            elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['rsi_14_1h'] < 46.0):
                return True, 'sell_profit_w_7_16'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 42.0):
                return True, 'sell_profit_w_7_17'
        elif 0.09 > current_profit >= 0.08:
            if last_candle['r_480'] > -2.4:
                return True, 'sell_profit_w_8_1'
            elif (last_candle['r_480'] > -7.5) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_8_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 50.0):
                return True, 'sell_profit_w_8_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_profit_w_8_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.954):
                return True, 'sell_profit_w_8_5'
            elif (last_candle['r_480'] > -14.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['r_480_1h'] > -8.0):
                return True, 'sell_profit_w_8_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_8_7'
            elif (last_candle['r_14'] > -0.6) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_8_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 180.0) and (last_candle['r_480_1h'] > -10.0):
                return True, 'sell_profit_w_8_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.95) and (last_candle['rsi_14'] > 75.0):
                return True, 'sell_profit_w_8_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 110.0) and (last_candle['r_480'] < -45.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_8_11'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] < 62.0) and (last_candle['cmf_1h'] < -0.15):
                return True, 'sell_profit_w_8_12'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cci'] > 360.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_8_13'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 300.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_8_14'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_480_1h'] > -14.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cci'] > 310.0):
                return True, 'sell_profit_w_8_15'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_1h'] < 44.0):
                return True, 'sell_profit_w_8_16'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_8_17'
        elif 0.1 > current_profit >= 0.09:
            if last_candle['r_480'] > -2.6:
                return True, 'sell_profit_w_9_1'
            elif (last_candle['r_480'] > -6.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_9_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 46.0):
                return True, 'sell_profit_w_9_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 80.0):
                return True, 'sell_profit_w_9_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.956):
                return True, 'sell_profit_w_9_5'
            elif (last_candle['r_480'] > -16.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['r_480_1h'] > -9.0):
                return True, 'sell_profit_w_9_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_9_7'
            elif (last_candle['r_14'] > -0.4) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_9_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.88) and (last_candle['cci'] > 190.0) and (last_candle['r_480_1h'] > -10.0):
                return True, 'sell_profit_w_9_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.96) and (last_candle['rsi_14'] > 76.0):
                return True, 'sell_profit_w_9_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.87) and (last_candle['cci'] > 120.0) and (last_candle['r_480'] < -50.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_9_11'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] < 58.0) and (last_candle['cmf_1h'] < -0.19):
                return True, 'sell_profit_w_9_12'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 380.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_9_13'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 320.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_9_14'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_480_1h'] > -12.0) and (last_candle['rsi_14'] > 78.5) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_9_15'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] < 40.0) and (last_candle['rsi_14_1h'] < 42.0):
                return True, 'sell_profit_w_9_16'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_9_17'
        elif 0.12 > current_profit >= 0.1:
            if last_candle['r_480'] > -1.0:
                return True, 'sell_profit_w_10_1'
            elif (last_candle['r_480'] > -5.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_10_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 42.0):
                return True, 'sell_profit_w_10_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 80.5):
                return True, 'sell_profit_w_10_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.96):
                return True, 'sell_profit_w_10_5'
            elif (last_candle['r_480'] > -18.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['r_480_1h'] > -11.0):
                return True, 'sell_profit_w_10_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_10_7'
            elif (last_candle['r_14'] > -0.4) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_10_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.9) and (last_candle['cci'] > 200.0) and (last_candle['r_480_1h'] > -8.0):
                return True, 'sell_profit_w_10_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.96) and (last_candle['rsi_14'] > 77.0):
                return True, 'sell_profit_w_10_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.88) and (last_candle['cci'] > 130.0) and (last_candle['r_480'] < -50.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_10_11'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] < 50.0) and (last_candle['cmf_1h'] < -0.22):
                return True, 'sell_profit_w_10_12'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 400.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_10_13'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 340.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_10_14'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_480_1h'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 330.0):
                return True, 'sell_profit_w_10_15'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] < 36.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_10_16'
            elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] < 42.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 37.0):
                return True, 'sell_profit_w_10_17'
        elif 0.2 > current_profit >= 0.12:
            if last_candle['r_480'] > -0.5:
                return True, 'sell_profit_w_11_1'
            elif (last_candle['r_480'] > -4.5) and (last_candle['rsi_14'] > 80.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_11_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 36.0):
                return True, 'sell_profit_w_11_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 81.0):
                return True, 'sell_profit_w_11_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.965):
                return True, 'sell_profit_w_11_5'
            elif (last_candle['r_480'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['r_480_1h'] > -7.0):
                return True, 'sell_profit_w_11_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_11_7'
            elif (last_candle['r_14'] > -0.2) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_11_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9) and (last_candle['cci'] > 200.0) and (last_candle['r_480_1h'] > -8.0):
                return True, 'sell_profit_w_11_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.96) and (last_candle['rsi_14'] > 78.0):
                return True, 'sell_profit_w_11_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.89) and (last_candle['cci'] > 140.0) and (last_candle['r_480'] < -50.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_11_11'
            elif (last_candle['r_14'] > -0.5) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf_1h'] < -0.25):
                return True, 'sell_profit_w_11_12'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 80.0) and (last_candle['cci'] > 420.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_11_13'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] > 78.0) and (last_candle['cci'] > 360.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_11_14'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_480_1h'] > -8.0) and (last_candle['rsi_14'] > 79.5) and (last_candle['cci'] > 340.0):
                return True, 'sell_profit_w_11_15'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_11_16'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] < 40.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 36.0):
                return True, 'sell_profit_w_11_17'
        elif current_profit >= 0.2:
            if last_candle['r_480'] > -0.4:
                return True, 'sell_profit_w_12_1'
            elif (last_candle['r_480'] > -4.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_12_2'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] < 32.0):
                return True, 'sell_profit_w_12_3'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 81.5):
                return True, 'sell_profit_w_12_4'
            elif (last_candle['r_14'] > -5.0) and (last_candle['cti'] > 0.97):
                return True, 'sell_profit_w_12_5'
            elif (last_candle['r_480'] > -5.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['r_480_1h'] > -4.0):
                return True, 'sell_profit_w_12_6'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_12_7'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 220.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_w_12_8'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9) and (last_candle['cci'] > 200.0) and (last_candle['r_480_1h'] > -8.0):
                return True, 'sell_profit_w_12_9'
            elif (last_candle['r_480'] < -65.0) and (last_candle['cti'] > 0.96) and (last_candle['rsi_14'] > 79.0):
                return True, 'sell_profit_w_12_10'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9) and (last_candle['cci'] > 150.0) and (last_candle['r_480'] < -50.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_12_11'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf_1h'] < -0.28):
                return True, 'sell_profit_w_12_12'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['rsi_14'] > 80.0) and (last_candle['cci'] > 440.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_12_13'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 380.0) and (last_candle['hl_pct_change_48_1h'] > 0.5):
                return True, 'sell_profit_w_12_14'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_480_1h'] > -6.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['cci'] > 350.0):
                return True, 'sell_profit_w_12_15'
            elif (last_candle['r_14'] > -0.1) and (last_candle['rsi_14'] < 32.0) and (last_candle['rsi_14_1h'] < 36.0):
                return True, 'sell_profit_w_12_16'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] < 38.0) and (last_candle['r_480'] < -50.0) and (last_candle['close'] < last_candle['ema_200']) and (last_candle['rsi_14_1h'] < 35.0):
                return True, 'sell_profit_w_12_17'

        return False, None

    def sell_trail(self, current_profit: float, max_profit: float, max_loss: float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if 0.02 > current_profit >= 0.012:
            if (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 34.0):
                return True, 'sell_profit_t_1_1'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 38.0):
                return True, 'sell_profit_t_1_2'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 47.0):
                return True, 'sell_profit_t_1_3'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['cti_1h'] < -0.9):
                return True, 'sell_profit_t_1_4'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_1_5'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_1_6'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 42.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_t_1_7'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 52.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_1_8'
        elif 0.03 > current_profit >= 0.02:
            if (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14'] < 35.0):
                return True, 'sell_profit_t_2_1'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 40.0):
                return True, 'sell_profit_t_2_2'
            elif (max_profit > (current_profit + 0.09)) and (last_candle['rsi_14'] < 47.0):
                return True, 'sell_profit_t_2_3'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['cti_1h'] < -0.8):
                return True, 'sell_profit_t_2_4'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_2_5'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_2_6'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14'] < 40.0) and (last_candle['rsi_14_1h'] < 44.0):
                return True, 'sell_profit_t_2_7'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_2_8'
        elif 0.04 > current_profit >= 0.03:
            if (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14'] < 36.0):
                return True, 'sell_profit_t_3_1'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 46.0):
                return True, 'sell_profit_t_3_2'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 47.0):
                return True, 'sell_profit_t_3_3'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14_1h'] < 49.0) and (last_candle['cti_1h'] < -0.6):
                return True, 'sell_profit_t_3_4'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_3_5'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_3_6'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 38.0) and (last_candle['rsi_14_1h'] < 43.0):
                return True, 'sell_profit_t_3_7'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 48.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_3_8'
        elif 0.05 > current_profit >= 0.04:
            if (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14'] < 37.0):
                return True, 'sell_profit_t_4_1'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 47.0):
                return True, 'sell_profit_t_4_2'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 42.0):
                return True, 'sell_profit_t_4_3'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_t_4_4'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_4_5'
            elif (max_profit > (current_profit + 0.085)) and (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_4_6'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14'] < 36.0) and (last_candle['rsi_14_1h'] < 42.0):
                return True, 'sell_profit_t_4_7'
            elif (max_profit > (current_profit + 0.085)) and (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 46.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_4_8'
        elif 0.06 > current_profit >= 0.05:
            if (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 38.0):
                return True, 'sell_profit_t_5_1'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 48.0):
                return True, 'sell_profit_t_5_2'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 42.0):
                return True, 'sell_profit_t_5_3'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_t_5_4'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_5_5'
            elif (max_profit > (current_profit + 0.09)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_5_6'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 35.0) and (last_candle['rsi_14_1h'] < 41.0):
                return True, 'sell_profit_t_5_7'
            elif (max_profit > (current_profit + 0.09)) and (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_5_8'
        elif 0.07 > current_profit >= 0.06:
            if (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14'] < 39.0):
                return True, 'sell_profit_t_6_1'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 49.0):
                return True, 'sell_profit_t_6_2'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 42.0):
                return True, 'sell_profit_t_6_3'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_t_6_4'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_6_5'
            elif (max_profit > (current_profit + 0.095)) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_6_6'
            elif (max_profit > (current_profit + 0.085)) and (last_candle['rsi_14'] < 34.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_t_6_7'
            elif (max_profit > (current_profit + 0.095)) and (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 42.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_6_8'
        elif 0.08 > current_profit >= 0.07:
            if (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 40.0):
                return True, 'sell_profit_t_7_1'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 50.0):
                return True, 'sell_profit_t_7_2'
            elif (max_profit > (current_profit + 0.12)) and (last_candle['rsi_14'] < 41.0):
                return True, 'sell_profit_t_7_3'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_t_7_4'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_7_5'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_7_6'
            elif (max_profit > (current_profit + 0.09)) and (last_candle['rsi_14'] < 33.0) and (last_candle['rsi_14_1h'] < 39.0):
                return True, 'sell_profit_t_7_7'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_7_8'
        elif 0.09 > current_profit >= 0.08:
            if (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14'] < 41.0):
                return True, 'sell_profit_t_8_1'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 51.0):
                return True, 'sell_profit_t_8_2'
            elif (max_profit > (current_profit + 0.12)) and (last_candle['rsi_14'] < 42.0):
                return True, 'sell_profit_t_8_3'
            elif (max_profit > (current_profit + 0.085)) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_t_8_4'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_8_5'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_8_6'
            elif (max_profit > (current_profit + 0.095)) and (last_candle['rsi_14'] < 32.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_t_8_7'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 36.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 38.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_8_8'
        elif 0.1 > current_profit >= 0.09:
            if (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 42.0):
                return True, 'sell_profit_t_9_1'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 52.0):
                return True, 'sell_profit_t_9_2'
            elif (max_profit > (current_profit + 0.12)) and (last_candle['rsi_14'] < 43.0):
                return True, 'sell_profit_t_9_3'
            elif (max_profit > (current_profit + 0.09)) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_t_9_4'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_9_5'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_9_6'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 31.0) and (last_candle['rsi_14_1h'] < 37.0):
                return True, 'sell_profit_t_9_7'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 36.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_9_8'
        elif 0.12 > current_profit >= 0.1:
            if (max_profit > (current_profit + 0.09)) and (last_candle['rsi_14'] < 40.0):
                return True, 'sell_profit_t_10_1'
            elif (max_profit > (current_profit + 0.09)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 50.0):
                return True, 'sell_profit_t_10_2'
            elif (max_profit > (current_profit + 0.12)) and (last_candle['rsi_14'] < 41.0):
                return True, 'sell_profit_t_10_3'
            elif (max_profit > (current_profit + 0.095)) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_t_10_4'
            elif (max_profit > (current_profit + 0.09)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_10_5'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_10_6'
            elif (max_profit > (current_profit + 0.11)) and (last_candle['rsi_14'] < 30.0) and (last_candle['rsi_14_1h'] < 36.0):
                return True, 'sell_profit_t_10_7'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 33.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_10_8'
        elif 0.2 > current_profit >= 0.12:
            if (max_profit > (current_profit + 0.095)) and (last_candle['rsi_14'] < 36.0):
                return True, 'sell_profit_t_11_1'
            elif (max_profit > (current_profit + 0.095)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 46.0):
                return True, 'sell_profit_t_11_2'
            elif (max_profit > (current_profit + 0.14)) and (last_candle['rsi_14'] < 38.0):
                return True, 'sell_profit_t_11_3'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14_1h'] < 33.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_t_11_4'
            elif (max_profit > (current_profit + 0.095)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_11_5'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 34.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_11_6'
            elif (max_profit > (current_profit + 0.12)) and (last_candle['rsi_14'] < 29.0) and (last_candle['rsi_14_1h'] < 35.0):
                return True, 'sell_profit_t_11_7'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 32.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 34.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_11_8'
        elif current_profit >= 0.2:
            if (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 34.0):
                return True, 'sell_profit_t_12_1'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] < 44.0):
                return True, 'sell_profit_t_12_2'
            elif (max_profit > (current_profit + 0.16)) and (last_candle['rsi_14'] < 35.0):
                return True, 'sell_profit_t_12_3'
            elif (max_profit > (current_profit + 0.11)) and (last_candle['rsi_14_1h'] < 31.0) and (last_candle['cti_1h'] < -0.85):
                return True, 'sell_profit_t_12_4'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_12_5'
            elif (max_profit > (current_profit + 0.1)) and (last_candle['rsi_14'] < 34.0) and (last_candle['cmf'] < -0.1) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_t_12_6'
            elif (max_profit > (current_profit + 0.13)) and (last_candle['rsi_14'] < 28.0) and (last_candle['rsi_14_1h'] < 34.0):
                return True, 'sell_profit_t_12_7'
            elif (max_profit > (current_profit + 0.11)) and (last_candle['rsi_14'] < 32.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 34.0)and (current_time - timedelta(minutes=1440) > trade.open_date_utc):
                return True, 'sell_profit_t_12_8'

        return False, None

    def sell_dec_main(self, current_profit: float, last_candle) -> tuple:
        if (last_candle['close'] > last_candle['ema_200']):
            if 0.02 > current_profit >= 0.012:
                if (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['cti'] < -0.75):
                    return True, 'sell_profit_d_o_1_1'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_1_2'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_1_3'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_2_1'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_2_2'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_2_3'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cti'] > 0.4):
                    return True, 'sell_profit_d_o_3_1'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 42.0):
                    return True, 'sell_profit_d_u_3_2'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_3_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 52.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < 0.05) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['cti'] > 0.3):
                    return True, 'sell_profit_d_o_4_1'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 44.0):
                    return True, 'sell_profit_d_o_4_2'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_4_3'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cti'] > 0.4):
                    return True, 'sell_profit_d_o_5_1'
                elif (last_candle['rsi_14'] < 54.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 46.0):
                    return True, 'sell_profit_d_o_5_2'
                elif (last_candle['rsi_14'] < 51.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_5_3'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_6_1'
                elif (last_candle['rsi_14'] < 56.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 44.0):
                    return True, 'sell_profit_d_o_6_2'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_6_3'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_7_1'
                elif (last_candle['rsi_14'] < 52.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 42.0):
                    return True, 'sell_profit_d_o_7_2'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_7_3'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['cti_1h'] > 0.5):
                    return True, 'sell_profit_d_o_8_1'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_8_2'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_8_3'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_9_1'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_9_2'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_9_3'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_10_1'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 36.0):
                    return True, 'sell_profit_d_o_10_2'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_10_3'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 36.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_11_1'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 34.0):
                    return True, 'sell_profit_d_o_11_2'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 33.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_11_3'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_12_1'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 32.0):
                    return True, 'sell_profit_d_o_12_2'
                elif (last_candle['rsi_14'] < 35.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 32.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_12_3'
        else:
            if 0.02 > current_profit >= 0.012:
                if (last_candle['rsi_14'] < 55.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_1_1'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 42.0):
                    return True, 'sell_profit_d_u_1_2'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_1_3'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 57.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_2_1'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 44.0):
                    return True, 'sell_profit_d_u_2_2'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_2_3'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 57.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 39.5) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_3_1'
                elif (last_candle['rsi_14'] < 52.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 46.0):
                    return True, 'sell_profit_d_u_3_2'
                elif (last_candle['rsi_14'] < 51.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_3_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 58.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_4_1'
                elif (last_candle['rsi_14'] < 56.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 46.0):
                    return True, 'sell_profit_d_u_4_2'
                elif (last_candle['rsi_14'] < 52.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_4_3'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 57.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 39.5) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_5_1'
                elif (last_candle['rsi_14'] < 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                    return True, 'sell_profit_d_u_5_2'
                elif (last_candle['rsi_14'] < 53.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_5_3'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 56.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_6_1'
                elif (last_candle['rsi_14'] < 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 48.0):
                    return True, 'sell_profit_d_u_6_2'
                elif (last_candle['rsi_14'] < 52.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_6_3'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 55.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 38.5) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_7_1'
                elif (last_candle['rsi_14'] < 58.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 46.0):
                    return True, 'sell_profit_d_u_7_2'
                elif (last_candle['rsi_14'] < 51.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_7_3'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 54.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_8_1'
                elif (last_candle['rsi_14'] < 56.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 44.0):
                    return True, 'sell_profit_d_u_8_2'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_8_3'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 53.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_9_1'
                elif (last_candle['rsi_14'] < 54.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 42.0):
                    return True, 'sell_profit_d_u_9_2'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_9_3'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 52.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_10_1'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_10_2'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_10_3'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_11_1'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_11_2'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 33.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_11_3'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_12_1'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 36.0):
                    return True, 'sell_profit_d_u_12_2'
                elif (last_candle['rsi_14'] < 37.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 32.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_12_3'
        return False, None

    def sell_pump_main(self, current_profit: float, last_candle) -> tuple:
        if (last_candle['hl_pct_change_48_1h'] > 0.9):
            if (last_candle['moderi_96']):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 31.0):
                        return True, 'sell_profit_p_bull_48_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 33.0):
                        return True, 'sell_profit_p_bull_48_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 41.0):
                        return True, 'sell_profit_p_bull_48_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 51.0):
                        return True, 'sell_profit_p_bull_48_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_p_bull_48_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 49.0):
                        return True, 'sell_profit_p_bull_48_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_p_bull_48_1_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_48_1_6_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_48_1_6_4'
                    elif (last_candle['rsi_14'] > 77.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bull_48_1_6_5'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_p_bull_48_1_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_48_1_5_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_48_1_5_4'
                    elif (last_candle['rsi_14'] > 75.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bull_48_1_5_5'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_p_bull_48_1_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_48_1_4_3'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_48_1_4_4'
                    elif (last_candle['rsi_14'] > 73.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bull_48_1_4_5'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 39.0):
                        return True, 'sell_profit_p_bull_48_1_3_1'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_48_1_3_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_48_1_3_4'
                    elif (last_candle['rsi_14'] > 75.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bull_48_1_3_5'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 35.0):
                        return True, 'sell_profit_p_bull_48_1_2_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_48_1_2_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_48_1_2_4'
                    elif (last_candle['rsi_14'] > 77.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bull_48_1_2_5'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 33.0):
                        return True, 'sell_profit_p_bull_48_1_1_1'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_48_1_1_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_48_1_1_4'
                    elif (last_candle['rsi_14'] > 79.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bull_48_1_1_5'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 32.0):
                        return True, 'sell_profit_p_bear_48_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_p_bear_48_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_p_bear_48_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 52.0):
                        return True, 'sell_profit_p_bear_48_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 51.0):
                        return True, 'sell_profit_p_bear_48_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_p_bear_48_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_p_bear_48_1_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_48_1_6_3'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_48_1_6_4'
                    elif (last_candle['rsi_14'] > 76.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bear_48_1_6_5'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_p_bear_48_1_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_48_1_5_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_48_1_5_4'
                    elif (last_candle['rsi_14'] > 75.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bear_48_1_5_5'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_p_bear_48_1_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_48_1_4_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_48_1_4_4'
                    elif (last_candle['rsi_14'] > 72.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bear_48_1_4_5'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0):
                        return True, 'sell_profit_p_bear_48_1_3_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_48_1_3_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_48_1_3_4'
                    elif (last_candle['rsi_14'] > 74.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bear_48_1_3_5'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 36.0):
                        return True, 'sell_profit_p_bear_48_1_2_1'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_48_1_2_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_48_1_2_4'
                    elif (last_candle['rsi_14'] > 76.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bear_48_1_2_5'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_p_bear_48_1_1_1'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_48_1_1_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_48_1_1_4'
                    elif (last_candle['rsi_14'] > 78.0) and (last_candle['r_14'] >= -0.1):
                        return True, 'sell_profit_p_bear_48_1_1_5'

        if (last_candle['hl_pct_change_48_1h'] > 0.8):
            if (last_candle['moderi_96']):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 32.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bull_48_2_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 33.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bull_48_2_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bull_48_2_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.3):
                        return True, 'sell_profit_p_bull_48_2_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_2_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_2_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_2_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 55.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bull_48_2_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bull_48_2_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_2_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_2_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_2_2_1'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 33.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bear_48_2_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 34.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bear_48_2_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bear_48_2_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bear_48_2_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bear_48_2_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.15):
                        return True, 'sell_profit_p_bear_48_2_1_1'

        if (last_candle['hl_pct_change_48_1h'] > 0.5):
            if (last_candle['moderi_96']):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 32.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bull_48_3_12_1'
                    elif (last_candle['rsi_14'] > 80.0) and (last_candle['r_14'] > -0.1) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_12_2'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 33.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bull_48_3_11_1'
                    elif (last_candle['rsi_14'] > 79.0) and (last_candle['r_14'] > -0.1) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_11_2'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bull_48_3_10_1'
                    elif (last_candle['rsi_14'] > 78.0) and (last_candle['r_14'] > -0.1) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_10_2'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.3):
                        return True, 'sell_profit_p_bull_48_3_9_1'
                    elif (last_candle['rsi_14'] > 77.0) and (last_candle['r_14'] > -0.1) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_9_2'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_8_1'
                    elif (last_candle['rsi_14'] > 76.0) and (last_candle['r_14'] > -0.1) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_8_2'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_7_1'
                    elif (last_candle['rsi_14'] > 74.0) and (last_candle['r_14'] > -1.0) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_7_2'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_6_1'
                    elif (last_candle['rsi_14'] > 72.0) and (last_candle['r_14'] > -2.0) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_6_2'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 55.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_5_1'
                    elif (last_candle['rsi_14'] > 70.0) and (last_candle['r_14'] > -5.0) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_5_2'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_4_1'
                    elif (last_candle['rsi_14'] > 67.0) and (last_candle['r_14'] > -10.0) and (last_candle['cmf_1h'] < -0.15):
                        return True, 'sell_profit_p_bull_48_3_4_2'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_3_1'
                    elif (last_candle['rsi_14'] > 68.0) and (last_candle['r_14'] > -10.0) and (last_candle['cmf_1h'] < -0.15):
                        return True, 'sell_profit_p_bull_48_3_3_2'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_2_1'
                    elif (last_candle['rsi_14'] > 72.0) and (last_candle['r_14'] > -5.0) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_2_2'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_2_1'
                    elif (last_candle['rsi_14'] > 76.0) and (last_candle['r_14'] > -1.0) and (last_candle['cmf_1h'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_1_2'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 33.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bear_48_3_12_1'
                    elif (last_candle['rsi_14'] > 79.0) and (last_candle['r_14'] > -0.1) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_12_2'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 34.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bear_48_3_11_1'
                    elif (last_candle['rsi_14'] > 78.0) and (last_candle['r_14'] > -0.1) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_11_2'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bear_48_3_10_1'
                    elif (last_candle['rsi_14'] > 77.0) and (last_candle['r_14'] > -0.1) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_10_2'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.3):
                        return True, 'sell_profit_p_bear_48_3_9_1'
                    elif (last_candle['rsi_14'] > 76.0) and (last_candle['r_14'] > -0.1) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_9_2'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_8_1'
                    elif (last_candle['rsi_14'] > 75.0) and (last_candle['r_14'] > -0.1) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_8_2'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_7_1'
                    elif (last_candle['rsi_14'] > 73.0) and (last_candle['r_14'] > -1.0) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_7_2'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_6_1'
                    elif (last_candle['rsi_14'] > 71.0) and (last_candle['r_14'] > -2.0) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_6_2'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_5_1'
                    elif (last_candle['rsi_14'] > 69.0) and (last_candle['r_14'] > -5.0) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_5_2'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_4_1'
                    elif (last_candle['rsi_14'] > 66.0) and (last_candle['r_14'] > -10.0) and (last_candle['cmf_1h'] < -0.15):
                        return True, 'sell_profit_p_bear_48_3_4_2'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_3_1'
                    elif (last_candle['rsi_14'] > 67.0) and (last_candle['r_14'] > -10.0) and (last_candle['cmf_1h'] < -0.15):
                        return True, 'sell_profit_p_bear_48_3_3_2'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_2_1'
                    elif (last_candle['rsi_14'] > 71.0) and (last_candle['r_14'] > -5.0) and (last_candle['cmf_1h'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_2_2'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_1_1'
                    elif (last_candle['rsi_14'] > 75.0) and (last_candle['r_14'] > -1.0) and (last_candle['cmf_1h'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_1_2'

        if (last_candle['hl_pct_change_36_1h'] > 0.72):
            if (last_candle['moderi_96']):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 31.0):
                        return True, 'sell_profit_p_bull_36_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 33.0):
                        return True, 'sell_profit_p_bull_36_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 41.0):
                        return True, 'sell_profit_p_bull_36_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 51.0):
                        return True, 'sell_profit_p_bull_36_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_p_bull_36_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 49.0):
                        return True, 'sell_profit_p_bull_36_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_p_bull_36_1_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_36_1_6_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_36_1_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_p_bull_36_1_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_36_1_5_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_36_1_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_p_bull_36_1_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_36_1_4_3'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_36_1_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 39.0):
                        return True, 'sell_profit_p_bull_36_1_3_1'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_36_1_3_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_36_1_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 35.0):
                        return True, 'sell_profit_p_bull_36_1_2_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_36_1_2_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_36_1_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 33.0):
                        return True, 'sell_profit_p_bull_36_1_1_1'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_36_1_1_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_36_1_1_4'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 32.0):
                        return True, 'sell_profit_p_bear_36_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_p_bear_36_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_p_bear_36_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 52.0):
                        return True, 'sell_profit_p_bear_36_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 51.0):
                        return True, 'sell_profit_p_bear_36_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_p_bear_36_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_p_bear_36_1_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_36_1_6_3'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_36_1_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_p_bear_36_1_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_36_1_5_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_36_1_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_p_bear_36_1_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_36_1_4_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_36_1_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0):
                        return True, 'sell_profit_p_bear_36_1_3_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_36_1_3_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_36_1_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 36.0):
                        return True, 'sell_profit_p_bear_36_1_2_1'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_36_1_2_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_36_1_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_p_bear_36_1_1_1'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_36_1_1_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_36_1_1_4'

        if (last_candle['hl_pct_change_24_1h'] > 0.68):
            if (last_candle['moderi_96']):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 31.0):
                        return True, 'sell_profit_p_bull_24_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 33.0):
                        return True, 'sell_profit_p_bull_24_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 41.0):
                        return True, 'sell_profit_p_bull_24_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 51.0):
                        return True, 'sell_profit_p_bull_24_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_p_bull_24_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 49.0):
                        return True, 'sell_profit_p_bull_24_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_p_bull_24_1_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_24_1_6_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_24_1_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_p_bull_24_1_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_24_1_5_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_24_1_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_p_bull_24_1_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_24_1_4_3'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_24_1_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 39.0):
                        return True, 'sell_profit_p_bull_24_1_3_1'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_24_1_3_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_24_1_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 35.0):
                        return True, 'sell_profit_p_bull_24_1_2_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_24_1_2_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_24_1_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 33.0):
                        return True, 'sell_profit_p_bull_24_1_1_1'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bull_24_1_1_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bull_24_1_1_4'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 32.0):
                        return True, 'sell_profit_p_bear_24_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_p_bear_24_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_p_bear_24_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 52.0):
                        return True, 'sell_profit_p_bear_24_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 51.0):
                        return True, 'sell_profit_p_bear_24_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_p_bear_24_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_p_bear_24_1_6_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_24_1_6_3'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_24_1_6_4'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_p_bear_24_1_5_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_24_1_5_3'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_24_1_5_4'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_p_bear_24_1_4_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_24_1_4_3'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_24_1_4_4'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0):
                        return True, 'sell_profit_p_bear_24_1_3_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_24_1_3_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_24_1_3_4'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 36.0):
                        return True, 'sell_profit_p_bear_24_1_2_1'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_24_1_2_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_24_1_2_4'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_p_bear_24_1_1_1'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.12):
                        return True, 'sell_profit_p_bear_24_1_1_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_14'] == 0):
                        return True, 'sell_profit_p_bear_24_1_1_4'

        return False, None

    def sell_pump_dec(self, current_profit: float, max_profit: float, max_loss: float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if (0.05 > current_profit > 0.01) and (last_candle['hl_pct_change_24_1h'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['close'] < last_candle['ema_200']):
            return True, 'sell_profit_p_d_1'

        elif (0.05 > current_profit > 0.02) and (last_candle['hl_pct_change_36_1h'] > 1.2) and (last_candle['sma_200_dec_20']) and (last_candle['close'] < last_candle['ema_200']):
            return True, 'sell_profit_p_d_2'

        elif (0.06 > current_profit > 0.04) and (last_candle['hl_pct_change_48_1h'] > 1.4) and (last_candle['sma_200_dec_20']) and (last_candle['close'] < last_candle['ema_200']):
            return True, 'sell_profit_p_d_3'

        return False, None

    def sell_pump_trail(self, current_profit: float, max_profit: float, max_loss: float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if (0.03 > current_profit > 0.01) and (last_candle['hl_pct_change_6_1h'] > 0.16) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < 0.0) and (max_profit > (current_profit + 0.02)) and (last_candle['rsi_14'] < 50.0):
                return True, 'sell_profit_p_t_1'

        return False, None

    def sell_pump_stoploss(self, current_profit: float, max_profit: float, max_loss: float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if (last_candle['hl_pct_change_48_1h'] > 0.9):
            if (
                    (-0.04 > current_profit > -0.08)
                    and (max_profit < 0.005)
                    and (max_loss < 0.08)
                    and (last_candle['close'] < last_candle['ema_200'])
                    and (last_candle['ema_vwma_osc_32'] < 0.0)
                    and (last_candle['ema_vwma_osc_64'] < 0.0)
                    and (last_candle['ema_vwma_osc_96'] < 0.0)
                    and (last_candle['cmf'] < -0.0)
            ):
                return True, 'sell_stoploss_p_48_1_1'
            elif (
                    (-0.04 > current_profit > -0.08)
                    and (max_profit < 0.02)
                    and (max_loss < 0.08)
                    and (last_candle['close'] < last_candle['ema_200'])
                    and (last_candle['sma_200_dec_20'])
                    and (last_candle['ema_vwma_osc_32'] < 0.0)
                    and (last_candle['ema_vwma_osc_64'] < 0.0)
                    and (last_candle['ema_vwma_osc_96'] < 0.0)
                    and (last_candle['cmf'] < -0.0)
            ):
                return True, 'sell_stoploss_p_48_1_2'

        if (last_candle['hl_pct_change_36_1h'] > 0.7):
            if (
                    (-0.04 > current_profit > -0.08)
                    and (max_loss < 0.08)
                    and (max_profit > (current_profit + 0.1))
                    and (last_candle['close'] < last_candle['ema_200'])
                    and (last_candle['ema_vwma_osc_32'] < 0.0)
                    and (last_candle['ema_vwma_osc_64'] < 0.0)
                    and (last_candle['ema_vwma_osc_96'] < 0.0)
                    and (last_candle['cmf'] < -0.0)
            ):
                return True, 'sell_stoploss_p_36_1_1'

        if (last_candle['hl_pct_change_36_1h'] > 0.5):
            if (
                    (-0.05 > current_profit > -0.08)
                    and (max_loss < 0.08)
                    and (max_profit > (current_profit + 0.1))
                    and (last_candle['close'] < last_candle['ema_200'])
                    and (last_candle['ema_vwma_osc_32'] < 0.0)
                    and (last_candle['ema_vwma_osc_64'] < 0.0)
                    and (last_candle['ema_vwma_osc_96'] < 0.0)
                    and (last_candle['cmf'] < -0.0)
                    and (last_candle['rsi_14'] < 40.0)
            ):
                return True, 'sell_stoploss_p_36_2_1'

        if (last_candle['hl_pct_change_24_1h'] > 0.6):
            if (
                    (-0.04 > current_profit > -0.08)
                    and (max_loss < 0.08)
                    and (last_candle['close'] < last_candle['ema_200'])
                    and (last_candle['ema_vwma_osc_32'] < 0.0)
                    and (last_candle['ema_vwma_osc_64'] < 0.0)
                    and (last_candle['ema_vwma_osc_96'] < 0.0)
                    and (last_candle['cmf'] < -0.0)
            ):
                return True, 'sell_stoploss_p_24_1_1'


        return False, None

    def sell_duration(self, current_profit: float, max_profit: float, max_loss: float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if (current_time - timedelta(minutes=1440) > trade.open_date_utc):
            if current_profit >= 0.2:
                if (last_candle['rsi_14'] > 81.5):
                    return True, 'sell_profit_l_12_1'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] > 81.0):
                    return True, 'sell_profit_l_11_1'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] > 80.5):
                    return True, 'sell_profit_l_10_1'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] > 80.0):
                    return True, 'sell_profit_l_9_1'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] > 79.5):
                    return True, 'sell_profit_l_8_1'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] > 79.0):
                    return True, 'sell_profit_l_7_1'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] > 78.5):
                    return True, 'sell_profit_l_6_1'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] > 78.0):
                    return True, 'sell_profit_l_5_1'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] > 79.0):
                    return True, 'sell_profit_l_4_1'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] > 80.0):
                    return True, 'sell_profit_l_3_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] > 80.5):
                    return True, 'sell_profit_l_2_1'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] > 81.0):
                    return True, 'sell_profit_l_1_1'

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

        # Original sell signals
        sell, signal_name = self.sell_signals(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, buy_tag)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Stoplosses
        sell, signal_name = self.sell_stoploss(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
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

        # Williams %R based sells
        sell, signal_name = self.sell_r(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Trailing
        sell, signal_name = self.sell_trail(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # The pair is descending
        sell, signal_name = self.sell_dec_main(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Sell logic for pumped pairs
        sell, signal_name = self.sell_pump_main(current_profit, last_candle)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # The pair is pumped, descending
        sell, signal_name = self.sell_pump_dec(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # The pair is pumped, trailing
        sell, signal_name = self.sell_pump_trail(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # The pair is pumped, stoploss
        sell, signal_name = self.sell_pump_stoploss(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Trade duration based sell logic
        sell, signal_name = self.sell_duration(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

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
        informative_1d['open_sha'], informative_1d['close_sha'], informative_1d['low_sha'] = heikin_ashi(informative_1d, smooth_inputs=True, smooth_outputs=False, length=10)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] informative_1d_indicators took: {tok - tik:0.4f} seconds.")

        return informative_1d

    def informative_1h_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        assert self.dp, "DataProvider is required for multiple timeframes."
        # Get the informative pair
        informative_1h = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=self.info_timeframe_1h)

        # RSI
        informative_1h['rsi_14'] = ta.RSI(informative_1h, timeperiod=14)

        # EMAs
        informative_1h['ema_12'] = ta.EMA(informative_1h, timeperiod=12)
        informative_1h['ema_20'] = ta.EMA(informative_1h, timeperiod=20)
        informative_1h['ema_25'] = ta.EMA(informative_1h, timeperiod=25)
        informative_1h['ema_50'] = ta.EMA(informative_1h, timeperiod=50)
        informative_1h['ema_100'] = ta.EMA(informative_1h, timeperiod=100)
        informative_1h['ema_200'] = ta.EMA(informative_1h, timeperiod=200)

        # SMA
        informative_1h['sma_200'] = ta.SMA(informative_1h, timeperiod=200)

        informative_1h['sma_200_dec_20'] = informative_1h['sma_200'] < informative_1h['sma_200'].shift(20)
        informative_1h['sma_200_dec_24'] = informative_1h['sma_200'] < informative_1h['sma_200'].shift(24)

        # BB
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(informative_1h), window=20, stds=2)
        informative_1h['bb20_2_low'] = bollinger['lower']
        informative_1h['bb20_2_mid'] = bollinger['mid']
        informative_1h['bb20_2_upp'] = bollinger['upper']

        # CMF
        informative_1h['cmf'] = chaikin_money_flow(informative_1h, 20)

        # CTI
        informative_1h['cti'] = pta.cti(informative_1h["close"], length=20)

        # CRSI (3, 2, 100)
        crsi_closechange = informative_1h['close'] / informative_1h['close'].shift(1)
        crsi_updown = np.where(crsi_closechange.gt(1), 1.0, np.where(crsi_closechange.lt(1), -1.0, 0.0))
        informative_1h['crsi'] =  (ta.RSI(informative_1h['close'], timeperiod=3) + ta.RSI(crsi_updown, timeperiod=2) + ta.ROC(informative_1h['close'], 100)) / 3

        # Williams %R
        informative_1h['r_14'] = williams_r(informative_1h, period=14)
        informative_1h['r_480'] = williams_r(informative_1h, period=480)

        # EWO
        informative_1h['ewo'] = ewo(informative_1h, 50, 200)
        informative_1h['ewo_ema'] = ewo_ema(informative_1h, 50, 200)

        # S/R
        res_series = informative_1h['high'].rolling(window = 5, center=True).apply(lambda row: self.is_resistance(row), raw=True).shift(2)
        sup_series = informative_1h['low'].rolling(window = 5, center=True).apply(lambda row: self.is_support(row), raw=True).shift(2)
        informative_1h['res_level'] = Series(np.where(res_series, np.where(informative_1h['close'] > informative_1h['open'], informative_1h['close'], informative_1h['open']), float('NaN'))).ffill()
        informative_1h['res_hlevel'] = Series(np.where(res_series, informative_1h['high'], float('NaN'))).ffill()
        # informative_1h['res_level_high'] = Series(np.where(res_series, informative_1h['high'], float('NaN'))).ffill()
        # informative_1h['res_level_low'] = Series(np.where(res_series, informative_1h['low'], float('NaN'))).ffill()
        informative_1h['sup_level'] = Series(np.where(sup_series, np.where(informative_1h['close'] < informative_1h['open'], informative_1h['close'], informative_1h['open']), float('NaN'))).ffill()
        # informative_1h['sup_level_high'] = Series(np.where(sup_series, informative_1h['high'], float('NaN'))).ffill()
        # informative_1h['sup_level_low'] = Series(np.where(sup_series, informative_1h['low'], float('NaN'))).ffill()

        # Pump protections
        informative_1h['hl_pct_change_48'] = self.range_percent_change(informative_1h, 'HL', 48)
        informative_1h['hl_pct_change_36'] = self.range_percent_change(informative_1h, 'HL', 36)
        informative_1h['hl_pct_change_24'] = self.range_percent_change(informative_1h, 'HL', 24)
        informative_1h['hl_pct_change_12'] = self.range_percent_change(informative_1h, 'HL', 12)
        informative_1h['hl_pct_change_6'] = self.range_percent_change(informative_1h, 'HL', 6)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] informative_1h_indicators took: {tok - tik:0.4f} seconds.")

        return informative_1h

    def normal_tf_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()

        # RSI
        dataframe['rsi_14'] = ta.RSI(dataframe, timeperiod=14)

        # EMAs
        dataframe['ema_12'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['ema_16'] = ta.EMA(dataframe, timeperiod=16)
        dataframe['ema_20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema_25'] = ta.EMA(dataframe, timeperiod=25)
        dataframe['ema_26'] = ta.EMA(dataframe, timeperiod=26)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_100'] = ta.EMA(dataframe, timeperiod=100)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)

        # SMA
        dataframe['sma_15'] = ta.SMA(dataframe, timeperiod=15)
        dataframe['sma_30'] = ta.SMA(dataframe, timeperiod=30)
        dataframe['sma_75'] = ta.SMA(dataframe, timeperiod=75)
        dataframe['sma_200'] = ta.SMA(dataframe, timeperiod=200)

        dataframe['sma_200_dec_20'] = dataframe['sma_200'] < dataframe['sma_200'].shift(20)
        dataframe['sma_200_dec_24'] = dataframe['sma_200'] < dataframe['sma_200'].shift(24)

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

        # CMF
        dataframe['cmf'] = chaikin_money_flow(dataframe, 20)

        # Williams %R
        dataframe['r_14'] = williams_r(dataframe, period=14)
        dataframe['r_480'] = williams_r(dataframe, period=480)

        # CTI
        dataframe['cti'] = pta.cti(dataframe["close"], length=20)

        # CRSI (3, 2, 100)
        crsi_closechange = dataframe['close'] / dataframe['close'].shift(1)
        crsi_updown = np.where(crsi_closechange.gt(1), 1.0, np.where(crsi_closechange.lt(1), -1.0, 0.0))
        dataframe['crsi'] =  (ta.RSI(dataframe['close'], timeperiod=3) + ta.RSI(crsi_updown, timeperiod=2) + ta.ROC(dataframe['close'], 100)) / 3

        # Modified Elder Ray Index
        dataframe['moderi_32'] = moderi(dataframe, 32)
        dataframe['moderi_64'] = moderi(dataframe, 64)
        dataframe['moderi_96'] = moderi(dataframe, 96)

        # EMA of VWMA Oscillator
        dataframe['ema_vwma_osc_32'] = ema_vwma_osc(dataframe, 32)
        dataframe['ema_vwma_osc_64'] = ema_vwma_osc(dataframe, 64)
        dataframe['ema_vwma_osc_96'] = ema_vwma_osc(dataframe, 96)

        # EWO
        dataframe['ewo'] = ewo(dataframe, 50, 200)
        dataframe['ewo_ema'] = ewo_ema(dataframe, 50, 200)

        # CCI
        dataframe['cci'] = ta.CCI(dataframe, source='hlc3', timeperiod=20)

        # MFI
        dataframe['mfi'] = ta.MFI(dataframe)

        # For sell checks
        dataframe['crossed_below_ema_12_26'] = qtpylib.crossed_below(dataframe['ema_12'], dataframe['ema_26'])

        # Dip protection
        dataframe['tpct_change_0']   = self.top_percent_change(dataframe,0)
        dataframe['tpct_change_2']   = self.top_percent_change(dataframe,2)
        dataframe['tpct_change_12']  = self.top_percent_change(dataframe,3)
        dataframe['tpct_change_144'] = self.top_percent_change(dataframe,48)

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
                if global_buy_protection_params["safe_pump_6h_threshold"] is not None:
                    item_buy_protection_list.append(dataframe['hl_pct_change_6_1h'] < global_buy_protection_params["safe_pump_6h_threshold"])
                if global_buy_protection_params["safe_pump_12h_threshold"] is not None:
                    item_buy_protection_list.append(dataframe['hl_pct_change_12_1h'] < global_buy_protection_params["safe_pump_12h_threshold"])
                if global_buy_protection_params["safe_pump_24h_threshold"] is not None:
                    item_buy_protection_list.append(dataframe['hl_pct_change_24_1h'] < global_buy_protection_params["safe_pump_24h_threshold"])
                if global_buy_protection_params["safe_pump_36h_threshold"] is not None:
                    item_buy_protection_list.append(dataframe['hl_pct_change_36_1h'] < global_buy_protection_params["safe_pump_36h_threshold"])
                if global_buy_protection_params["safe_pump_48h_threshold"] is not None:
                    item_buy_protection_list.append(dataframe['hl_pct_change_48_1h'] < global_buy_protection_params["safe_pump_48h_threshold"])
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

                # Condition #1 - Semi swing mode. Increase in the last candles & relative local dip.
                if index == 1:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(((dataframe['close'] - dataframe['open'].rolling(4).min()) / dataframe['open'].rolling(4).min()) > 0.038)
                    item_buy_logic.append(dataframe['rsi_14'] < 33.0)
                    item_buy_logic.append(dataframe['rsi_14_1h'] > 30.0)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 50.0)
                    item_buy_logic.append(dataframe['r_480_1h'] > -99.0)

                # Condition #2 - Semi swing. Local dip. Uptrend.
                elif index == 2:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.025))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.999))

                # Condition #3 - Semi swing. Local dip. Strong uptrend.
                elif index == 3:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_25'] * 0.952)
                    item_buy_logic.append(dataframe['ewo_ema'] > 2.0)
                    item_buy_logic.append(dataframe['rsi_14'] < 40.0)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['r_14'] < -97.0)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.0)

                # Condition #4 - Semi swing. Local dip. Uptrend. Strict pump & dip protections.
                elif index == 4:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_low'].shift().gt(0))
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * 0.045))
                    item_buy_logic.append(dataframe['closedelta'].gt(dataframe['close'] * 0.03))
                    item_buy_logic.append(dataframe['tail'].lt(dataframe['bb40_2_delta'] * 0.24))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))
                    item_buy_logic.append(dataframe['cti'] < -0.5)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.8)
                    item_buy_logic.append(dataframe['r_480_1h'] < -35.0)

                # Condition #5 - Semi swing. Local deeper dip. Uptrend.
                elif index == 5:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_26'] * 0.966)
                    item_buy_logic.append(dataframe['ewo_ema'] > 4.0)
                    item_buy_logic.append(dataframe['rsi_14'] < 26.0)
                    item_buy_logic.append(dataframe['cti'] < -0.75)
                    item_buy_logic.append(dataframe['r_14'] < -96.0)
                    item_buy_logic.append(dataframe['mfi'] < 20.0)

                # Condition #6 - Semi swing. Local deeper dip. Uptrend.
                elif index == 6:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * 0.958)
                    item_buy_logic.append(dataframe['ewo_ema'] > 2.4)
                    item_buy_logic.append(dataframe['cci'] < -190.0)
                    item_buy_logic.append(dataframe['r_14'] < -97.0)
                    item_buy_logic.append(dataframe['ewo_ema_1h'] > 4.0)
                    item_buy_logic.append((dataframe['rsi_14_1h'] + dataframe['rsi_14']) < 74.0)

                # Condition #7 - Semi swing. 1h uptrend.
                elif index == 7:
                    # Non-Standard protections (add below)
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(4))
                    item_buy_logic.append(dataframe['ema_200_1h'].shift(4) > dataframe['ema_200_1h'].shift(8))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.026))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.999))

                # Condition #8 - Semi swing. Local dip. 1h minor dip.
                elif index == 8:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['rsi_14'] < dataframe['rsi_14'].shift(1))
                    item_buy_logic.append(dataframe['ema_20_1h'] > dataframe['ema_25_1h'])
                    item_buy_logic.append(dataframe['close'] < (dataframe['sma_15'] * 0.95))
                    item_buy_logic.append(
                        ((dataframe['open'] < dataframe['ema_20_1h']) & (dataframe['low'] < dataframe['ema_20_1h'])) |
                        ((dataframe['open'] > dataframe['ema_20_1h']) & (dataframe['low'] > dataframe['ema_20_1h'])))
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['r_14'] < -92.0)
                    item_buy_logic.append(dataframe['cti_1h'] < -0.1)

                # Condition #9 - Semi swing. Local deep. Uptrend, 1h uptrend.
                elif index == 9:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'].shift(1) < (dataframe['sma_15'].shift(1) * 0.97))
                    item_buy_logic.append(dataframe['close'] > (dataframe['open'].shift(1)))
                    item_buy_logic.append(dataframe['ewo_ema'] > 4.2)
                    item_buy_logic.append(dataframe['cti'] < -0.75)
                    item_buy_logic.append(dataframe['r_14'].shift(1) < -94.0)
                    item_buy_logic.append(dataframe['ewo_ema_1h'] > 2.0)
                    item_buy_logic.append(dataframe['cti_1h'] < -0.75)

                # Condition #10 - Semi swing. Local dip.
                elif index == 10:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.024))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * 0.942)
                    item_buy_logic.append(dataframe['rsi_14'] < 25.5)
                    item_buy_logic.append(dataframe['crsi'] > 8.0)
                    item_buy_logic.append(dataframe['r_480_1h'] > -75.0)

                # Condition #11 - Semi swing. Deep local dip. Mild uptrend.
                elif index == 11:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * 0.926)
                    item_buy_logic.append(dataframe['ewo_ema'] > 2.0)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.25)

                # Condition #12 - Semi swing. Downtrend. Dip.
                elif index == 12:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_16'] * 0.954))
                    item_buy_logic.append(dataframe['ewo_ema'] < -8.4)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['r_14'] < -94.0)
                    item_buy_logic.append(dataframe['crsi_1h'] > 3.0)

                # Condition #13 - Semi swing. 1h uptrend. BTC not downtrend.
                elif index == 13:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.025))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.999))

                # Condition #14 - Semi swing. Mild uptrend. 1h uptrend. Local dip.
                elif index == 14:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['ewo_ema'] > 2.0)
                    item_buy_logic.append(dataframe['close'].shift(1) < (dataframe['ema_20'].shift(1) * 0.992))
                    item_buy_logic.append(dataframe['close'] > (dataframe['close'].shift(1)))
                    item_buy_logic.append(dataframe['cmf'].shift(1) < -0.48)
                    item_buy_logic.append(dataframe['r_14'].shift(1) < -97.0)
                    item_buy_logic.append(dataframe['ewo_ema_1h'] > 7.5)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.0)

                # Condition #15 - Semi swing. Downtrend.Local dip.
                elif index == 15:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['close'].shift(1) < dataframe['ema_20'].shift(1) * 0.996)
                    item_buy_logic.append(dataframe['ewo_ema'].shift(1) < -10.4)
                    item_buy_logic.append(dataframe['cti'].shift(1).rolling(5).max() < -0.9)
                    item_buy_logic.append(dataframe['r_14'].shift(1) < -90.0)
                    item_buy_logic.append(dataframe['crsi_1h'] > 2.0)

                # Condition #16 - Semi swing. Strong uptrend. 1h uptrend. Local dip. BTC not downtrend.
                elif index == 16:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ewo_ema'].shift(1) > 6.6)
                    item_buy_logic.append(dataframe['close'].shift(1) < (dataframe['sma_30'].shift(1) * 0.988))
                    item_buy_logic.append(dataframe['close'].shift(1) < (dataframe['bb20_2_low'].shift(1) * 0.982))
                    item_buy_logic.append(dataframe['rsi_14'].shift(1) < 32.0)
                    item_buy_logic.append(dataframe['r_14'].shift(1) < -94.0)
                    item_buy_logic.append(dataframe['ewo_ema_1h'] > 2.0)
                    item_buy_logic.append(dataframe['r_480_1h'] < -20.0)

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
        return True

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
    sma1 = ta.SMA(dataframe, timeperiod=sma1_length)
    sma2 = ta.SMA(dataframe, timeperiod=sma2_length)
    smadif = (sma1 - sma2) / dataframe['close'] * 100
    return smadif

def ewo_ema(dataframe, sma1_length=5, sma2_length=35):
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

# Modified Elder Ray Index
def moderi(dataframe: DataFrame, len_slow_ma: int = 32) -> Series:
    slow_ma = Series(ta.EMA(vwma(dataframe, length=len_slow_ma), timeperiod=len_slow_ma))
    return slow_ma >= slow_ma.shift(1)  # we just need true & false for ERI trend

# Exponential moving average of a volume weighted simple moving average
def ema_vwma_osc(dataframe, len_slow_ma):
    slow_ema = Series(ta.EMA(vwma(dataframe, len_slow_ma), len_slow_ma))
    return ((slow_ema - slow_ema.shift(1)) / slow_ema.shift(1)) * 100

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
