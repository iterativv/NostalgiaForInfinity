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
from technical.indicators import RMI, zema, VIDYA, ichimoku
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
##                NostalgiaForInfinityX by iterativ                                                     ##
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
##   "nfi-hold-trades.json" file add something like:                                                     ##
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
##   BTC: bc1qvflsvddkmxh7eqhc4jyu5z5k6xcw3ay8jl49sk                                                     ##
##   ETH (ERC20): 0x83D3cFb8001BDC5d2211cBeBB8cB3461E5f7Ec91                                             ##
##   BEP20/BSC (USDT, ETH, BNB, ...): 0x86A0B21a20b39d16424B7c8003E4A7e12d78ABEe                         ##
##   TRC20/TRON (USDT, TRON, ...): TTAa9MX6zMLXNgWMhg7tkNormVHWCoq8Xk                                    ##
##                                                                                                       ##
##               REFERRAL LINKS                                                                          ##
##                                                                                                       ##
##  Binance: https://accounts.binance.com/en/register?ref=EAZC47FM (5% discount on trading fees)         ##
##  Kucoin: https://www.kucoin.com/r/QBSSSPYV (5% discount on trading fees)                              ##
##  Gate.io: https://www.gate.io/signup/8054544 (10% discount on trading fees)                           ##
##  OKEx: https://www.okex.com/join/11749725760 (5% discount on trading fees)                            ##
##  Huobi: https://www.huobi.com/en-us/topic/double-reward/?invite_code=ubpt2223                         ##
###########################################################################################################


class NostalgiaForInfinityX(IStrategy):
    INTERFACE_VERSION = 2

    def version(self) -> str:
        return "v10.9.72"

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
    res_timeframe = 'none'
    info_timeframe_1d = '1d'
    info_timeframe_1h = '1h'
    info_timeframe_15m = '15m'

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
        "buy_condition_35_enable": True,
        "buy_condition_36_enable": True,
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
        "buy_condition_49_enable": True,
        "buy_condition_50_enable": True,
        "buy_condition_51_enable": True,
        "buy_condition_52_enable": True,
        "buy_condition_53_enable": True,
        "buy_condition_54_enable": True,
        "buy_condition_55_enable": True,
        "buy_condition_56_enable": True,
        "buy_condition_57_enable": True,
        "buy_condition_58_enable": True,
        "buy_condition_59_enable": True,
        "buy_condition_60_enable": True,
        "buy_condition_61_enable": True,
        "buy_condition_62_enable": True,
        "buy_condition_63_enable": True,
        "buy_condition_64_enable": True,
        "buy_condition_65_enable": True,
        "buy_condition_66_enable": True,
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
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : 0.06,
            "safe_dips_threshold_12"    : 0.24,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.36,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 1.2,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 2.0,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        2: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "20",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "28",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.06,
            "safe_dips_threshold_12"    : 0.3,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.8,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        3: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "20",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "28",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.06,
            "safe_dips_threshold_12"    : 0.34,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.5,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 0.9,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "sup1", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.99,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        4: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "28",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.54,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump_6h_threshold"    : 0.6,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.7,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        5: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
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
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.3,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.68,
            "safe_pump_36h_threshold"   : 0.74,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        6: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "28",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.3,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.78,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.3,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "pivot", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.98,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        7: {
            "ema_fast"                  : True,
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
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : 0.022,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.3,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.8,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.98,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.6
        },
        8: {
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
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.3,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.74,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.98,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.6
        },
        9: {
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
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.3,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.9,
            "safe_pump_48h_threshold"   : 1.2,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        10: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "26",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : True,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.16,
            "safe_dips_threshold_144"   : 0.9,
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
        11: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "26",
            "ema_slow"                  : True,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.14,
            "safe_dips_threshold_144"   : 0.24,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.88,
            "safe_pump_48h_threshold"   : 1.1,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "sup3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.06,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        12: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "26",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.13,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : 0.5,
            "safe_pump_24h_threshold"   : 0.75,
            "safe_pump_36h_threshold"   : 1.8,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        13: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "26",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : 0.52,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.9,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        14: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "100",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "44",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "72",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
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
            "ema_fast_len"              : "100",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : True,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "48",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.48,
            "safe_dips_threshold_144"   : 0.9,
            "safe_pump_6h_threshold"    : 0.5,
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
            "ema_fast_len"              : "100",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : 0.02,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
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
        17: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "100",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.25,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.25,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        18: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "100",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : 0.03,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.14,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.35,
            "safe_pump_12h_threshold"   : 0.45,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.65,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        19: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "100",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : 0.026,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.35,
            "safe_pump_12h_threshold"   : 0.45,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        20: {
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
            "sma200_1h_rising"          : None,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : 0.35,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        21: {
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
            "sma200_1h_rising"          : None,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.6,
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
        22: {
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
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "48",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.6,
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
        23: {
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
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.2,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        24: {
            "ema_fast"                  : True,
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
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.16,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.4,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.8,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.1
        },
        25: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "36",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.8,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        26: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.16,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 1.0,
            "safe_pump_48h_threshold"   : 1.8,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        27: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : 0.5,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.8,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        28: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 1.9,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        29: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.5,
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
        30: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "50",
            "ema_slow"                  : True,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.03,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.28,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        31: {
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
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.024,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.44,
            "safe_pump_6h_threshold"    : 0.5,
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
        32: {
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
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.26,
            "safe_dips_threshold_144"   : 0.3,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.78,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        33: {
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
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.8,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.07
        },
        34: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.066,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
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
        35: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.028,
            "safe_dips_threshold_2"     : 0.066,
            "safe_dips_threshold_12"    : 0.32,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
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
        36: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "16",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.14,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.6,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.45
        },
        37: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.14,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.2
        },
        38: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "16",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.13,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.45,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 2.0,
            "safe_pump_36h_threshold"   : 2.0,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.8
        },
        39: {
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
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.16,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : 0.54,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.8,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.25
        },
        40: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "30",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : 0.3,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.55,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.67,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        41: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.08,
            "safe_dips_threshold_12"    : 0.16,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.9,
            "safe_pump_48h_threshold"   : 3.2,
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
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : 0.4,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.1,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        43: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.03,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : None,
            "safe_pump_12h_threshold"   : 0.9,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.0,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "sup3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.99,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        44: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : True,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.16,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 1.2,
            "safe_pump_48h_threshold"   : 1.4,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        45: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.03,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.4,
            "safe_dips_threshold_144"   : 0.8,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.35,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        46: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "24",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.32,
            "safe_dips_threshold_144"   : 0.34,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.6,
            "safe_pump_36h_threshold"   : 1.0,
            "safe_pump_48h_threshold"   : 1.4,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        47: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : True,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.03,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.9,
            "safe_pump_48h_threshold"   : 1.4,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        48: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : 0.26,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.8,
            "safe_pump_36h_threshold"   : 1.3,
            "safe_pump_48h_threshold"   : 1.4,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.2
        },
        49: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : True,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.03,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : None,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.6,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.4,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        50: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.03,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.56,
            "safe_pump_36h_threshold"   : 1.0,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        51: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.03,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : 0.3,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : 0.58,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.1,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
        },
        52: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.25,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.62,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 0.95,
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
         },
        53: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.16,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.1,
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
         },
        54: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.18,
            "safe_dips_threshold_144"   : 0.24,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.95,
            "safe_pump_48h_threshold"   : 1.05,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
         },
        55: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : 0.7,
            "safe_pump_48h_threshold"   : 0.7,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
         },
        56: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : 0.3,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.8,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
         },
        57: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.28,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.1,
            "btc_1h_not_downtrend"      : True,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
         },
        58: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.024,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.14,
            "safe_dips_threshold_144"   : 0.24,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.0,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
         },
        59: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.36,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.52,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.0,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "sup3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.75,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
         },
        60: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.8,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "sup2", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 0.96,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
         },
        62: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "50",
            "ema_slow"                  : False,
            "ema_slow_len"              : "50",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "42",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "50",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.18,
            "safe_dips_threshold_144"   : 0.23,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.6,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.4,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
         },
        63: {
            "ema_fast"                  : True,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "48",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.13,
            "safe_dips_threshold_144"   : 0.26,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.5,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.4,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "res3", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.2
         },
        64: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "48",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.18,
            "safe_dips_threshold_144"   : 0.26,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.75,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.4,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : 1.0,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : 1.0
         },
        65: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "48",
            "safe_dips_threshold_0"     : None,
            "safe_dips_threshold_2"     : None,
            "safe_dips_threshold_12"    : None,
            "safe_dips_threshold_144"   : None,
            "safe_pump_6h_threshold"    : None,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : None,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : None,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : None,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : None
         },
        66: {
            "ema_fast"                  : False,
            "ema_fast_len"              : "12",
            "ema_slow"                  : False,
            "ema_slow_len"              : "12",
            "close_above_ema_fast"      : False,
            "close_above_ema_fast_len"  : "200",
            "close_above_ema_slow"      : False,
            "close_above_ema_slow_len"  : "200",
            "sma200_rising"             : False,
            "sma200_rising_val"         : "24",
            "sma200_1h_rising"          : False,
            "sma200_1h_rising_val"      : "48",
            "safe_dips_threshold_0"     : 0.032,
            "safe_dips_threshold_2"     : 0.09,
            "safe_dips_threshold_12"    : 0.18,
            "safe_dips_threshold_144"   : 0.26,
            "safe_pump_6h_threshold"    : 0.5,
            "safe_pump_12h_threshold"   : None,
            "safe_pump_24h_threshold"   : 0.75,
            "safe_pump_36h_threshold"   : None,
            "safe_pump_48h_threshold"   : 1.4,
            "btc_1h_not_downtrend"      : False,
            "close_over_pivot_type"     : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_over_pivot_offset"   : None,
            "close_under_pivot_type"    : "none", # pivot, sup1, sup2, sup3, res1, res2, res3
            "close_under_pivot_offset"  : None
         }
    }

    # Sell
    sell_condition_1_enable = True

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
        conditions = []
        for row in range(len(row_data)-1):
            if row < len(row_data)/2:
                conditions.append(row_data[row] > row_data[row+1])
            else:
                conditions.append(row_data[row] < row_data[row+1])
        return reduce(lambda x, y: x & y, conditions)

    def is_resistance(self, row_data) -> bool:
        conditions = []
        for row in range(len(row_data)-1):
            if row < len(row_data)/2:
                conditions.append(row_data[row] < row_data[row+1])
            else:
                conditions.append(row_data[row] > row_data[row+1])
        return reduce(lambda x, y: x & y, conditions)

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
        if (last_candle['rsi_14'] > 79.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) and (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']) and (previous_candle_4['close'] > previous_candle_4['bb20_2_upp']) and (previous_candle_5['close'] > previous_candle_5['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_1_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_1_2_1'
                # elif (current_profit < -0.05) and (max_loss > 0.12):
                #     return True, 'sell_signal_1_2_2'

        # Sell signal 2
        elif (last_candle['rsi_14'] > 80.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) and (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_2_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_2_2_1'
                # elif (current_profit < -0.05) and (max_loss > 0.12):
                #     return True, 'sell_signal_2_2_2'

        # Sell signal 3
        elif (last_candle['rsi_14'] > 83.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_3_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_3_2_1'
                # elif (current_profit < -0.05) and (max_loss > 0.12):
                #     return True, 'sell_signal_3_2_2'

        # Sell signal 4
        elif (last_candle['rsi_14'] > 78.0) and (last_candle['rsi_14_1h'] > 78.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_4_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_4_2_1'
                # elif (current_profit < -0.05) and (max_loss > 0.12):
                #     return True, 'sell_signal_4_2_2'

        # Sell signal 6
        elif (last_candle['close'] < last_candle['ema_200']) and (last_candle['close'] > last_candle['ema_50']) and (last_candle['rsi_14'] > 79.5):
            if (current_profit > 0.01):
                return True, 'sell_signal_6_1'
            # elif (current_profit < -0.05) and (max_loss > 0.12):
            #     return True, 'sell_signal_6_2'

        # Sell signal 7
        elif (last_candle['rsi_14_1h'] > 80.0) and (last_candle['crossed_below_ema_12_26']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_7_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_7_2_1'
                # elif (current_profit < -0.05) and (max_loss > 0.12):
                #     return True, 'sell_signal_7_2_2'

        # Sell signal 8
        elif (last_candle['close'] > last_candle['bb20_2_upp_1h'] * 1.08):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, 'sell_signal_8_1_1'
            else:
                if (current_profit > 0.01):
                    return True, 'sell_signal_8_2_1'
                # elif (current_profit < -0.05) and (max_loss > 0.12):
                #     return True, 'sell_signal_8_2_2'

        return False, None

    def sell_stoploss(self, current_profit: float, max_profit: float, max_loss: float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if (
                (current_profit < -0.0)
                and (last_candle['close'] < last_candle['ema_200'])
                and (last_candle['sma_200_dec_20'])
                and (last_candle['sma_200_dec_20_15m'])
                and (last_candle['sma_200_dec_20_1h'])
                and (last_candle['ema_vwma_osc_32'] < -0.0)
                and (last_candle['ema_vwma_osc_64'] < -0.0)
                and (last_candle['ema_vwma_osc_96'] < -0.0)
                and (last_candle['cmf'] < -0.0)
                and (last_candle['cmf_15m'] < -0.0)
                and (last_candle['cmf_1h'] < -0.0)
                and (current_time - timedelta(minutes=2880) > trade.open_date_utc)
        ):
            if (-0.12 <= current_profit < -0.08):
                if (last_candle['close'] < last_candle['atr_high_thresh_1']) and (previous_candle_1['close'] > previous_candle_1['atr_high_thresh_1']):
                    return True, 'sell_stoploss_atr_1'
            elif (-0.16 <= current_profit < -0.12):
                if (last_candle['close'] < last_candle['atr_high_thresh_2']) and (previous_candle_1['close'] > previous_candle_1['atr_high_thresh_2']):
                    return True, 'sell_stoploss_atr_2'
            elif (-0.2 <= current_profit < -0.16):
                if (last_candle['close'] < last_candle['atr_high_thresh_3']) and (previous_candle_1['close'] > previous_candle_1['atr_high_thresh_3']):
                    return True, 'sell_stoploss_atr_3'
            elif (current_profit < -0.2):
                if (last_candle['close'] < last_candle['atr_high_thresh_4']) and (previous_candle_1['close'] > previous_candle_1['atr_high_thresh_4']):
                    return True, 'sell_stoploss_atr_4'

        # Under & near EMA200, local uptrend move
        if (
                (current_profit < -0.025)
                and (last_candle['close'] < last_candle['ema_200'])
                and (last_candle['cmf'] < -0.0)
                and (((last_candle['ema_200'] - last_candle['close']) / last_candle['close']) < 0.004)
                and last_candle['rsi_14'] > previous_candle_1['rsi_14']
                and (last_candle['rsi_14'] > (last_candle['rsi_14_1h'] + 20.0))
                and (last_candle['sma_200_dec_20'])
                and (last_candle['sma_200_dec_24'])
                and (current_time - timedelta(minutes=4320) > trade.open_date_utc)
                # temporary
                and (trade.open_date_utc + timedelta(minutes=8000) > current_time )
        ):
            return True, 'sell_stoploss_u_e_1'

        return False, None

    def sell_over_main(self, current_profit: float, last_candle) -> tuple:
        if last_candle['close'] > last_candle['ema_200']:
            if (last_candle['ema_vwma_osc_96']):
                if current_profit >= 0.20:
                    if (last_candle['rsi_14'] < 39.0):
                        return True, 'sell_profit_o_bull_12_1'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_12_2'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_12_3'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_12_4'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_12_5'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_12_6'
                elif 0.20 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 41.0):
                        return True, 'sell_profit_o_bull_11_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_11_2'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_11_3'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_11_4'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_11_5'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_11_6'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_o_bull_10_1'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_10_2'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_10_3'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_10_4'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_10_5'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_10_6'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_o_bull_9_1'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_9_2'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_9_3'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_9_4'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_9_5'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_9_6'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_o_bull_8_1'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_8_2'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_8_3'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_8_4'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_8_5'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_8_6'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_o_bull_7_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_7_2'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_7_3'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_7_4'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_7_5'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_7_6'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_o_bull_6_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_6_2'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_6_3'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_6_4'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_6_5'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_6_6'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 41.0):
                        return True, 'sell_profit_o_bull_5_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_5_2'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_5_3'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_5_4'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_5_5'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_5_6'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 39.0):
                        return True, 'sell_profit_o_bull_4_1'
                    elif (last_candle['rsi_14'] < 62.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_4_2'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_4_3'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_4_4'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_4_5'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_4_6'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 37.0):
                        return True, 'sell_profit_o_bull_3_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_3_2'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_3_3'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_3_4'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_3_5'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_3_6'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_o_bull_2_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_2_2'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_2_3'
                    elif (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_2_4'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_2_5'
                    elif (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_2_6'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 33.0):
                        return True, 'sell_profit_o_bull_1_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_1_2'
                    elif (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_1_3'
                    elif (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bull_1_4'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bull_1_5'
                    elif (last_candle['rsi_14'] < 34.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bull_1_6'
            else:
                if current_profit >= 0.20:
                    if (last_candle['rsi_14'] < 40.0):
                        return True, 'sell_profit_o_bear_12_1'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_12_2'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_12_3'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_12_4'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_12_5'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_12_6'
                elif 0.20 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_o_bear_11_1'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_11_2'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_11_3'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_11_4'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_11_5'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_11_6'
                elif 0.12 > current_profit >= 0.10:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_o_bear_10_1'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_10_2'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_10_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_10_4'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_10_5'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_10_6'
                elif 0.10 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_o_bear_9_1'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_9_2'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_9_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_9_4'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_9_5'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_9_6'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_o_bear_8_1'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_8_2'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_8_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_8_4'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_8_5'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_8_6'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_o_bear_7_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_7_2'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_7_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_7_4'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_7_5'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_7_6'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_o_bear_6_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_6_2'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_6_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_6_4'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_6_5'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_6_6'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_o_bear_5_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_5_2'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_5_3'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_5_4'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_5_5'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_5_6'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 40.0):
                        return True, 'sell_profit_o_bear_4_1'
                    elif (last_candle['rsi_14'] < 62.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_4_2'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_4_3'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_4_4'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_4_5'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_4_6'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 38.0):
                        return True, 'sell_profit_o_bear_3_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_3_2'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_3_3'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_3_4'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_3_5'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_3_6'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 35.0):
                        return True, 'sell_profit_o_bear_2_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_2_2'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_2_3'
                    elif (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_2_4'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_2_5'
                    elif (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_2_6'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_o_bear_1_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bear_1_2'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_1_3'
                    elif (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_o_bear_1_4'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_o_bear_1_5'
                    elif (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_o_bear_1_6'

        return False, None

    def sell_under_main(self, current_profit: float, last_candle) -> tuple:
        if last_candle['close'] < last_candle['ema_200']:
            if (last_candle['ema_vwma_osc_96'] > 0.0):
                if current_profit >= 0.20:
                    if (last_candle['rsi_14'] < 41.0):
                        return True, 'sell_profit_u_bull_12_1'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bull_12_2'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_12_3'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_12_4'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_12_5'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_12_6'
                elif 0.20 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_u_bull_11_1'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_o_bull_11_2'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_11_3'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_11_4'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_11_5'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_11_6'
                elif 0.12 > current_profit >= 0.10:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_u_bull_10_1'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bull_10_2'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_10_3'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_10_4'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_10_5'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_10_6'
                elif 0.10 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_u_bull_9_1'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bull_9_2'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_9_3'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_9_4'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_9_5'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_9_6'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 49.0):
                        return True, 'sell_profit_u_bull_8_1'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bull_8_2'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_8_3'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_8_4'
                    elif (last_candle['rsi_14'] < 53.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_8_5'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_8_6'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_u_bull_7_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bull_7_2'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_7_3'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_7_4'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_7_5'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_7_6'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_u_bull_6_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bull_6_2'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_6_3'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_6_4'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_6_5'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_6_6'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_u_bull_5_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bull_5_2'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_5_3'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_5_4'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_5_5'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_5_6'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 41.0):
                        return True, 'sell_profit_u_bull_4_1'
                    elif (last_candle['rsi_14'] < 62.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bull_4_2'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_4_3'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_4_4'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_4_5'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_3_6'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 39.0):
                        return True, 'sell_profit_u_bull_3_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bull_3_2'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_3_3'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_3_4'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_3_5'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_3_6'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 36.0):
                        return True, 'sell_profit_u_bull_2_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bull_2_2'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_2_3'
                    elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_2_4'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_2_5'
                    elif (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_2_6'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 35.0):
                        return True, 'sell_profit_u_bull_1_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bull_1_2'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_1_3'
                    elif (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bull_1_4'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bull_1_5'
                    elif (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bull_1_6'
            else:
                if current_profit >= 0.20:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_u_bear_12_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_12_2'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_12_3'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_12_4'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_12_5'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_12_6'
                elif 0.20 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_u_bear_11_1'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_11_2'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_11_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_11_4'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_11_5'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_11_6'
                elif 0.12 > current_profit >= 0.10:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_u_bear_10_1'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_10_2'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_10_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_10_4'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_10_5'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_10_6'
                elif 0.10 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_u_bear_9_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_9_2'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_9_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_9_4'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_9_5'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_9_6'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_u_bear_8_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_8_2'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_8_3'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_8_4'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_8_5'
                    elif (last_candle['rsi_14'] < 51.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_8_6'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_u_bear_7_1'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_7_2'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_7_3'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_7_4'
                    elif (last_candle['rsi_14'] < 52.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_7_5'
                    elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_7_6'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_u_bear_6_1'
                    elif (last_candle['rsi_14'] < 54.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_6_2'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_6_3'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_6_4'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_6_5'
                    elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_6_6'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_u_bear_5_1'
                    elif (last_candle['rsi_14'] < 58.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_5_2'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_5_3'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_5_4'
                    elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_5_5'
                    elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_5_6'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_u_bear_4_1'
                    elif (last_candle['rsi_14'] < 62.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_4_2'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_4_3'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_4_4'
                    elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_4_5'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_4_6'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0):
                        return True, 'sell_profit_u_bear_3_1'
                    elif (last_candle['rsi_14'] < 56.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_3_2'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_3_3'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_3_4'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_3_5'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_3_6'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 39.0):
                        return True, 'sell_profit_u_bear_2_1'
                    elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_2_2'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_2_3'
                    elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_2_4'
                    elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_2_5'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_2_6'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 38.0):
                        return True, 'sell_profit_u_bear_1_1'
                    elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.4):
                        return True, 'sell_profit_u_bear_1_2'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_1_3'
                    elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_u_bear_1_4'
                    elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                        return True, 'sell_profit_u_bear_1_5'
                    elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2):
                        return True, 'sell_profit_u_bear_1_6'

        return False, None

    def sell_r(self, current_profit: float, max_profit: float, max_loss: float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if 0.01 > current_profit > 0.001:
            if (last_candle['r_96'] < -90.0) and (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.3) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.2):
                return True, 'sell_profit_w_0_1'
            elif (last_candle['rsi_14'] < 30.0) and (last_candle['r_96'] < -90.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.3) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_0_2'
            elif (last_candle['rsi_14'] < 28.0) and (last_candle['cmf'] < -0.5) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_0_3'
            elif (last_candle['r_480'] < -80.0) and (last_candle['rsi_14'] > 80.0):
                return True, 'sell_profit_w_0_4'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -90.0):
                return True, 'sell_profit_w_0_5'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 82.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_0_6'
        elif 0.02 > current_profit >= 0.01:
            if (last_candle['r_480'] > -0.4):
                return True, 'sell_profit_w_1_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 75.0):
                return True, 'sell_profit_w_1_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 44.0):
                return True, 'sell_profit_w_1_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 74.0):
                return True, 'sell_profit_w_1_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 73.0):
                return True, 'sell_profit_w_1_5'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 360.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_1_6'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_1_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_1_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 74.0):
                return True, 'sell_profit_w_1_9'
            elif (last_candle['r_480'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 220.0):
                return True, 'sell_profit_w_1_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_1_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 260.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_1_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_1_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 70.0):
                return True, 'sell_profit_w_1_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_1_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 300.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_1_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_1_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_1_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_1_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.8) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_1_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_1_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_1_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_1_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_1_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_1_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 75.0):
                return True, 'sell_profit_w_1_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_1_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_1_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 280.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_1_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_32'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_1_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_1_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_1_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_1_37'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -10.0):
                return True, 'sell_profit_w_1_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_1_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_1_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_1_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_1_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_1_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_1_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_1_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_1_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_1_48'
            elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_1_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_1_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_1_51'
            elif (last_candle['r_14'] > -15.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_1_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_1_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_1_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_1_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_1_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_1_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_1_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_1_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_1_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 73.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_1_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_1_63'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_1_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_1_65'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_1_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_1_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_68'
            elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_1_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_1_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_1_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_1_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_1_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_1_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_1_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_1_76'
            elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_1_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_78'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_1_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_1_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_1_83'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_1_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_1_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_1_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_1_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_1_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_1_90'
        elif 0.03 > current_profit >= 0.02:
            if (last_candle['r_480'] > -0.5):
                return True, 'sell_profit_w_2_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 74.0):
                return True, 'sell_profit_w_2_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 46.0):
                return True, 'sell_profit_w_2_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 73.0):
                return True, 'sell_profit_w_2_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_2_5'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 350.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_2_6'
            elif (last_candle['rsi_14'] < 47.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_2_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_2_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_2_9'
            elif (last_candle['r_480'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 220.0):
                return True, 'sell_profit_w_2_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 300.0):
                return True, 'sell_profit_w_2_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 250.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_2_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_2_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 69.0):
                return True, 'sell_profit_w_2_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_2_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 290.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_2_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_2_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_2_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_2_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.8) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_2_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_2_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_2_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_2_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_2_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_2_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 74.0):
                return True, 'sell_profit_w_2_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_2_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_2_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_2_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_32'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_2_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_2_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_2_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_2_37'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -10.0):
                return True, 'sell_profit_w_2_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_2_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_2_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_2_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_2_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_2_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_2_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_2_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_2_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_2_48'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_2_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_2_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_2_51'
            elif (last_candle['r_14'] > -15.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_2_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_2_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_2_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_2_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_2_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_2_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_2_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_2_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_2_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 72.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_2_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_2_63'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_2_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_2_65'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_2_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_2_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_68'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_2_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_2_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_2_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_2_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_2_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_2_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_2_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_2_76'
            elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_2_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_78'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_2_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_2_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_2_83'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_2_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_2_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_2_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_2_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_2_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_2_90'
        elif 0.04 > current_profit >= 0.03:
            if (last_candle['r_480'] > -0.6):
                return True, 'sell_profit_w_3_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 73.0):
                return True, 'sell_profit_w_3_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 48.0):
                return True, 'sell_profit_w_3_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_3_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 71.0):
                return True, 'sell_profit_w_3_5'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 340.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_3_6'
            elif (last_candle['rsi_14'] < 48.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_3_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_3_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 68.0):
                return True, 'sell_profit_w_3_9'
            elif (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 220.0):
                return True, 'sell_profit_w_3_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 290.0):
                return True, 'sell_profit_w_3_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 240.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_3_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_3_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 68.0):
                return True, 'sell_profit_w_3_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_3_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 280.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_3_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_3_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_3_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_3_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.8) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_3_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_3_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_3_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_3_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_3_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_3_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 73.0):
                return True, 'sell_profit_w_3_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_3_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_3_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_3_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_32'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_3_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_3_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_3_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_3_37'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -10.0):
                return True, 'sell_profit_w_3_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_3_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 59.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_3_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_3_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_3_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_3_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_3_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_3_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_3_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_3_48'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_3_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_3_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_3_51'
            elif (last_candle['r_14'] > -15.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_3_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_3_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_3_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_3_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_3_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_3_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_3_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_3_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_3_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 71.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_3_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_3_63'
            elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_3_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_3_65'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_3_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_3_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_68'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_3_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_3_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_3_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_3_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_3_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_3_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_3_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_3_76'
            elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_3_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_78'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_3_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_3_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_3_83'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_3_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_3_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_3_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_3_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_3_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_3_90'
        elif 0.05 > current_profit >= 0.04:
            if (last_candle['r_480'] > -0.7):
                return True, 'sell_profit_w_4_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_4_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 50.0):
                return True, 'sell_profit_w_4_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 71.0):
                return True, 'sell_profit_w_4_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 70.0):
                return True, 'sell_profit_w_4_5'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 330.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_4_6'
            elif (last_candle['rsi_14'] < 49.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_4_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_4_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 66.0):
                return True, 'sell_profit_w_4_9'
            elif (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 220.0):
                return True, 'sell_profit_w_4_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 280.0):
                return True, 'sell_profit_w_4_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 230.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_4_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_4_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 67.0):
                return True, 'sell_profit_w_4_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_4_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 270.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_4_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_4_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_4_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_4_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.8) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_4_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_4_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_4_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_4_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_4_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_4_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_4_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_4_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_4_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_4_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_32'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_4_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_4_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_4_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_4_37'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -10.0):
                return True, 'sell_profit_w_4_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_4_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 58.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_4_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_4_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_4_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_4_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_4_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_4_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_4_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_4_48'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_4_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_4_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_4_51'
            elif (last_candle['r_14'] > -15.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_4_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_4_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_4_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_4_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_4_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_4_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_4_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_4_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_4_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 70.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_4_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_4_63'
            elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_4_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_4_65'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_4_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_4_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_68'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_4_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_4_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_4_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_4_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_4_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_4_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_4_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_4_76'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_4_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_78'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_4_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_4_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_4_83'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_4_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_4_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_4_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_4_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_4_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_4_90'
        elif 0.06 > current_profit >= 0.05:
            if (last_candle['r_480'] > -0.8):
                return True, 'sell_profit_w_5_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 71.0):
                return True, 'sell_profit_w_5_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 54.0):
                return True, 'sell_profit_w_5_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 70.0):
                return True, 'sell_profit_w_5_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 69.0):
                return True, 'sell_profit_w_5_5'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 320.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_5_6'
            elif (last_candle['rsi_14'] < 50.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_5_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_5_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 64.0):
                return True, 'sell_profit_w_5_9'
            elif (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 220.0):
                return True, 'sell_profit_w_5_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 270.0):
                return True, 'sell_profit_w_5_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 220.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_5_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_5_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 66.0):
                return True, 'sell_profit_w_5_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_5_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_5_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_5_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_5_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 63.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_5_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_5_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_5_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_5_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_5_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_5_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_5_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 71.0):
                return True, 'sell_profit_w_5_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_5_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_5_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 200.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_5_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_32'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_5_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_5_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_5_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_5_37'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -10.0):
                return True, 'sell_profit_w_5_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_5_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 57.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_5_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_5_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_5_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_5_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_5_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_5_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_5_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_5_48'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_5_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_5_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_5_51'
            elif (last_candle['r_14'] > -15.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_5_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_5_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_5_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_5_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_5_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_5_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_5_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_5_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_5_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 69.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_5_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_5_63'
            elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_5_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_5_65'
            elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_5_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_5_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_68'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_5_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_5_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_5_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_5_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_5_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_5_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_5_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_5_76'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_5_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_78'
            elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_5_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_5_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_5_83'
            elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_5_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_5_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_5_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_5_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_5_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_5_90'
        elif 0.07 > current_profit >= 0.06:
            if (last_candle['r_480'] > -0.9):
                return True, 'sell_profit_w_6_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_6_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 52.0):
                return True, 'sell_profit_w_6_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 71.0):
                return True, 'sell_profit_w_6_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 70.0):
                return True, 'sell_profit_w_6_5'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 310.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_6_6'
            elif (last_candle['rsi_14'] < 49.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_6_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_6_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 66.0):
                return True, 'sell_profit_w_6_9'
            elif (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 220.0):
                return True, 'sell_profit_w_6_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 260.0):
                return True, 'sell_profit_w_6_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 230.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_6_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_6_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 67.0):
                return True, 'sell_profit_w_6_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_6_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 270.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_6_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_6_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_6_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_6_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.8) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_6_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_6_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_6_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_6_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_6_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_6_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_6_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_6_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_6_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_6_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_32'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_6_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_6_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_6_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_6_37'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -10.0):
                return True, 'sell_profit_w_6_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_6_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 58.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_6_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_6_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_6_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_6_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_6_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_6_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_6_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_6_48'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_6_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_6_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_6_51'
            elif (last_candle['r_14'] > -15.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_6_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_6_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_6_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_6_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_6_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_6_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_6_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_6_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_6_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 70.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_6_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_6_63'
            elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_6_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_6_65'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_6_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_6_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_68'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_6_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_6_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_6_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_6_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_6_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_6_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_6_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_6_76'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_6_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_78'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_6_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_6_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_6_83'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_6_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_6_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_6_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_6_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_6_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_6_90'
        elif 0.08 > current_profit >= 0.07:
            if (last_candle['r_480'] > -1.0):
                return True, 'sell_profit_w_7_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 73.0):
                return True, 'sell_profit_w_7_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 50.0):
                return True, 'sell_profit_w_7_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_7_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 71.0):
                return True, 'sell_profit_w_7_5'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 300.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_7_6'
            elif (last_candle['rsi_14'] < 48.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_7_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_7_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 68.0):
                return True, 'sell_profit_w_7_9'
            elif (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 220.0):
                return True, 'sell_profit_w_7_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 270.0):
                return True, 'sell_profit_w_7_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 240.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_7_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_7_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 68.0):
                return True, 'sell_profit_w_7_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_7_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 280.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_7_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_7_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_7_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_7_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.85) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_7_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_7_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_7_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_7_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_7_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_7_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 73.0):
                return True, 'sell_profit_w_7_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_7_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_7_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_7_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_32'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_7_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_7_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_7_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_7_37'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -10.0):
                return True, 'sell_profit_w_7_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_7_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 59.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_7_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_7_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_7_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_7_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_7_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_7_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_7_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_7_48'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_7_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_7_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_7_51'
            elif (last_candle['r_14'] > -15.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_7_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_7_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_7_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_7_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_7_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_7_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_7_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_7_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_7_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 71.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_7_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_7_63'
            elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_7_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_7_65'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_7_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_7_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_68'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_7_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_7_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_7_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_7_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_7_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_7_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_7_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_7_76'
            elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_7_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_78'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_7_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_7_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_7_83'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_7_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_7_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_7_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_7_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_7_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_7_90'
        elif 0.09 > current_profit >= 0.08:
            if (last_candle['r_480'] > -1.2):
                return True, 'sell_profit_w_8_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 74.0):
                return True, 'sell_profit_w_8_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 48.0):
                return True, 'sell_profit_w_8_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 73.0):
                return True, 'sell_profit_w_8_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_8_5'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 310.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_8_6'
            elif (last_candle['rsi_14'] < 47.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_8_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_8_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 70.0):
                return True, 'sell_profit_w_8_9'
            elif (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 220.0):
                return True, 'sell_profit_w_8_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 280.0):
                return True, 'sell_profit_w_8_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 250.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_8_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_8_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 69.0):
                return True, 'sell_profit_w_8_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_8_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 290.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_8_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_8_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_8_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_8_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.85) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_8_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_8_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_8_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_8_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_8_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_8_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 74.0):
                return True, 'sell_profit_w_8_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_8_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_8_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_8_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_32'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_8_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_8_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_8_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_8_37'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -10.0):
                return True, 'sell_profit_w_8_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_8_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_8_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_8_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_8_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_8_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_8_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_8_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_8_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_8_48'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_8_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_8_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_8_51'
            elif (last_candle['r_14'] > -15.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_8_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_8_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_8_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_8_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_8_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_8_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_8_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_8_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_8_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 72.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_8_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_8_63'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_8_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_8_65'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_8_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_8_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_68'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_8_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_8_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_8_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_8_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_8_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_8_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_8_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_8_76'
            elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_8_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_78'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_8_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_8_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_8_83'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_8_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_8_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_8_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_8_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_8_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_8_90'
        elif 0.1 > current_profit >= 0.09:
            if (last_candle['r_480'] > -1.2):
                return True, 'sell_profit_w_9_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 75.0):
                return True, 'sell_profit_w_9_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 46.0):
                return True, 'sell_profit_w_9_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 74.0):
                return True, 'sell_profit_w_9_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 73.0):
                return True, 'sell_profit_w_9_5'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 320.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_9_6'
            elif (last_candle['rsi_14'] < 46.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_9_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_9_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 72.0):
                return True, 'sell_profit_w_9_9'
            elif (last_candle['r_480'] > -10.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 220.0):
                return True, 'sell_profit_w_9_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 290.0):
                return True, 'sell_profit_w_9_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 260.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_9_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_9_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 70.0):
                return True, 'sell_profit_w_9_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_9_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 300.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_9_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_9_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_9_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_9_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.85) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_9_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_9_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_9_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_9_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_9_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_9_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 75.0):
                return True, 'sell_profit_w_9_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_9_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_9_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 280.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_9_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_32'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_9_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_9_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_9_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_9_37'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -10.0):
                return True, 'sell_profit_w_9_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_9_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_9_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_9_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_9_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_9_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_9_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_9_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_9_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_9_48'
            elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_9_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_9_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_9_51'
            elif (last_candle['r_14'] > -15.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_9_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_9_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_9_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_9_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_9_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_9_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_9_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_9_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_9_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 73.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_9_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_9_63'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_9_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_9_65'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_9_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_9_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_68'
            elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_9_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_9_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_9_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_9_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_9_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_9_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_9_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_9_76'
            elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_9_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_78'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_9_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_9_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_9_83'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_9_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_9_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_9_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_9_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_9_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_9_90'
        elif 0.12 > current_profit >= 0.1:
            if (last_candle['r_480'] > -1.0):
                return True, 'sell_profit_w_10_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 76.0):
                return True, 'sell_profit_w_10_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 44.0):
                return True, 'sell_profit_w_10_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 75.0):
                return True, 'sell_profit_w_10_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 74.0):
                return True, 'sell_profit_w_10_5'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 330.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_10_6'
            elif (last_candle['rsi_14'] < 45.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_10_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_10_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 74.0):
                return True, 'sell_profit_w_10_9'
            elif (last_candle['r_480'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 240.0):
                return True, 'sell_profit_w_10_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 300.0):
                return True, 'sell_profit_w_10_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 270.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_10_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_10_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 71.0):
                return True, 'sell_profit_w_10_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_10_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 310.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_10_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_10_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_10_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_10_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.85) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_10_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_10_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_10_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_10_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_10_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_10_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 76.0):
                return True, 'sell_profit_w_10_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_10_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_10_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 300.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_10_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_32'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_10_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_10_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_10_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_10_37'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -10.0):
                return True, 'sell_profit_w_10_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_10_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_10_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_10_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_10_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_10_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_10_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_10_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_10_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_10_48'
            elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_10_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_10_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_10_51'
            elif (last_candle['r_14'] > -15.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_10_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_10_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_10_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_10_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_10_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_10_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_10_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_10_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_10_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 74.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_10_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_10_63'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_10_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_10_65'
            elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_10_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_10_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_68'
            elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_10_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_10_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_10_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_10_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_10_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_10_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_10_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_10_76'
            elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_10_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_78'
            elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_10_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_10_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_10_83'
            elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_10_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_10_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_10_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_10_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_10_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_10_90'
        elif 0.2 > current_profit >= 0.12:
            if (last_candle['r_480'] > -0.5):
                return True, 'sell_profit_w_11_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 77.0):
                return True, 'sell_profit_w_11_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 42.0):
                return True, 'sell_profit_w_11_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 76.0):
                return True, 'sell_profit_w_11_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 75.0):
                return True, 'sell_profit_w_11_5'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 340.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_11_6'
            elif (last_candle['rsi_14'] < 44.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_11_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_11_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 75.0):
                return True, 'sell_profit_w_11_9'
            elif (last_candle['r_480'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 260.0):
                return True, 'sell_profit_w_11_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 310.0):
                return True, 'sell_profit_w_11_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 280.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_11_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_11_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 71.0):
                return True, 'sell_profit_w_11_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_11_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cci'] > 320.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_11_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_11_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_11_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_11_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.85) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_11_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_11_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_11_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_11_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_11_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_11_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 77.0):
                return True, 'sell_profit_w_11_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_11_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_11_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 320.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_11_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_32'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_11_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_11_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_11_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_11_37'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_64'] > -5.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -10.0):
                return True, 'sell_profit_w_11_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_11_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_11_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_11_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_11_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_11_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_11_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_11_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_11_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_11_48'
            elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_11_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_11_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_11_51'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_11_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_11_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_11_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_11_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_11_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_11_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_11_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_11_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_11_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 75.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_11_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_11_63'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_11_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_11_65'
            elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_11_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_11_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_68'
            elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_11_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_11_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_11_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_11_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_11_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_11_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_11_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_11_76'
            elif (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_11_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_78'
            elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_11_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_11_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_11_83'
            elif (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_11_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_11_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_11_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_11_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_11_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_11_90'
        elif current_profit >= 0.2:
            if (last_candle['r_480'] > -0.4):
                return True, 'sell_profit_w_12_1'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['rsi_14'] > 78.0):
                return True, 'sell_profit_w_12_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 40.0):
                return True, 'sell_profit_w_12_3'
            elif (last_candle['r_14'] >= -2.5) and (last_candle['rsi_14'] > 77.0):
                return True, 'sell_profit_w_12_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['r_32'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 76.0):
                return True, 'sell_profit_w_12_5'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 360.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_12_6'
            elif (last_candle['rsi_14'] < 43.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_12_7'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['r_96'] >= -3.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.9):
                return True, 'sell_profit_w_12_8'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_24'] == 0.0) and (last_candle['rsi_14'] > 76.0):
                return True, 'sell_profit_w_12_9'
            elif (last_candle['r_480'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.85) and (last_candle['cci'] > 280.0):
                return True, 'sell_profit_w_12_10'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 320.0):
                return True, 'sell_profit_w_12_11'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 290.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_12_12'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_12_13'
            elif (last_candle['r_14'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 71.0):
                return True, 'sell_profit_w_12_14'
            elif (last_candle['r_14'] > -0.1)  and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_12_15'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 330.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_12_16'
            elif (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['r_480_1h'] < -75.0):
                return True, 'sell_profit_w_12_17'
            elif (last_candle['r_14'] > -18.0) and (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.96) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_12_18'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.85) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_12_19'
            elif (last_candle['r_64'] > -20.0) and (last_candle['r_96'] > -15.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.85) and (last_candle['r_64_15m'] > -15.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_12_20'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['btc_not_downtrend_1h'] == False)  and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_21'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] < -55.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_22'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_12_23'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_12_24'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['rsi_14_1h'] < 38.0):
                return True, 'sell_profit_w_12_25'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_12_26'
            elif (last_candle ['r_14'] > -3.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_12_27'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 78.0):
                return True, 'sell_profit_w_12_28'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['r_14_15m'] > -4.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_12_29'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cti'] > 0.85):
                return True, 'sell_profit_w_12_30'
            elif (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 340.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_12_31'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cci'] > 260.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_32'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_33'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] > -3.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 220.0) and (last_candle['r_14_15m'] > -3.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_12_34'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['r_480_1h'] > -15.0):
                return True, 'sell_profit_w_12_35'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -4.0) and (last_candle['r_96'] > -4.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_12_36'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.9) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20']):
                return True, 'sell_profit_w_12_37'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_64'] > -5.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9) and (last_candle['r_64_15m'] > -5.0):
                return True, 'sell_profit_w_12_38'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cti'] > 0.85) and (last_candle['cmf_1h'] < -0.25) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_12_39'
            elif (last_candle['r_14'] == 0.0) and (last_candle['r_64'] == 0.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_40'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_480_1h'] < -90.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_12_41'
            elif (last_candle['r_480'] < -75.0) and (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -85.0):
                return True, 'sell_profit_w_12_42'
            elif (last_candle['r_14'] > -5.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.25):
                return True, 'sell_profit_w_12_43'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 200.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -50.0) and (last_candle['close'] < last_candle['ema_200']):
                return True, 'sell_profit_w_12_44'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_64'] > -5.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_12_45'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_12_46'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_14_15m'] > -5.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_12_47'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_64'] > -12.0) and (last_candle['r_96'] > -12.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_12_48'
            elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] > -20.0) and (last_candle['ema_vwma_osc_96'] < -0.0):
                return True, 'sell_profit_w_12_49'
            elif (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.2) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_12_50'
            elif (last_candle['r_96'] < -75.0) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_12_51'
            elif (last_candle['r_14'] > -5.0) and (last_candle['r_64'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_12_52'
            elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['r_96'] > -5.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_12_53'
            elif (last_candle['r_96'] > -25.0) and (last_candle['rsi_14'] > 79.0) and (last_candle['cci'] > 280.0) and (last_candle['sma_200_dec_20']) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_12_54'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['r_96'] > -1.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['r_14_15m'] > -20.0):
                return True, 'sell_profit_w_12_55'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['rsi_14_1h'] > 70.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_w_12_56'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] > -20.0) and (last_candle['rsi_14_1h'] > 50.0):
                return True, 'sell_profit_w_12_57'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.8) and (last_candle['cmf_1h'] < -0.2) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_12_58'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_32'] > -1.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_12_59'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -6.0) and (last_candle['r_64'] > -6.0) and (last_candle['r_96'] > -6.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] > -30.0):
                return True, 'sell_profit_w_12_60'
            elif (last_candle['r_14'] > -3.0) and (last_candle['r_32'] > -3.0) and (last_candle['r_96'] > -3.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_61'
            elif (last_candle['r_14'] > -6.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 76.0)  and (last_candle['cci'] > 200.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_12_62'
            elif (last_candle['r_14'] > -4.0) and (last_candle['r_32'] > -4.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['r_480_1h'] > -25.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1):
                return True, 'sell_profit_w_12_63'
            elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] > 60.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_12_64'
            elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] > -25.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0):
                return True, 'sell_profit_w_12_65'
            elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_12_66'
            elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_480_1h'] < -50.0):
                return True, 'sell_profit_w_12_67'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_68'
            elif (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_480_1h'] > -25.0):
                return True, 'sell_profit_w_12_69'
            elif (last_candle['r_480'] < -50.0) and (last_candle['r_96'] < -70.0) and (last_candle['r_14'] > -75.0) and (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.3) and (last_candle['r_96_15m'] < -60.0):
                return True, 'sell_profit_w_12_70'
            elif (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_12_71'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -75.0):
                return True, 'sell_profit_w_12_72'
            elif (last_candle['r_14'] > -8.0) and (last_candle['r_32'] > -5.0) and (last_candle['rsi_14'] > 78.0) and (last_candle['cci'] > 250.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_12_73'
            elif (last_candle['r_96'] > -20.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_12_74'
            elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                return True, 'sell_profit_w_12_75'
            elif (last_candle['r_14'] > -1.0) and (last_candle['r_64'] > -1.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_12_76'
            elif (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_12_77'
            elif (last_candle['r_14'] > -6.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_1h'] < -0.2) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_78'
            elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_12_79'
            elif (last_candle['r_14'] == 0.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_80'
            elif (last_candle['r_14'] > -2.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_w_12_81'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_82'
            elif (last_candle['r_14'] > -2.0) and (last_candle['r_64'] > -2.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0):
                return True, 'sell_profit_w_12_83'
            elif (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] > -30.0):
                return True, 'sell_profit_w_12_84'
            elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_85'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['r_480'] < -75.0) and (last_candle['r_96_15m'] < -75.0) and (last_candle['rsi_14_1h'] < 40.0):
                return True, 'sell_profit_w_12_86'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_w_12_87'
            elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['cci'] > 240.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_w_12_88'
            elif (last_candle['r_14'] > -1.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                return True, 'sell_profit_w_12_89'
            elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['btc_not_downtrend_1h'] == False):
                return True, 'sell_profit_w_12_90'

        return False, None

    def sell_trail(self, current_profit: float, max_profit: float, max_loss: float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if 0.012 > current_profit >= 0.0:
            if (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14'] < 46.0):
                return True, 'sell_profit_t_0_1'
            elif (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14'] < 32.0):
                return True, 'sell_profit_t_0_2'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14'] < 48.0):
                return True, 'sell_profit_t_0_3'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14'] < 50.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_0_4'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_0_5'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14'] < 36.0) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_0_6'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['sma_200_dec_20_15m']):
                return True, 'sell_profit_t_0_7'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 49.0):
                return True, 'sell_profit_t_0_8'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 34.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_0_9'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14'] < 38.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_0_10'
        elif 0.02 > current_profit >= 0.012:
            if (max_profit > (current_profit + 0.01)) and (last_candle['rsi_14'] < 39.0):
                return True, 'sell_profit_t_1_1'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_1_2'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_1_3'
            elif (max_profit > (current_profit + 0.02)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_1_4'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 49.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_1_5'
            elif (max_profit > (current_profit + 0.015)) and (last_candle['rsi_14'] < 42.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_1_6'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_1_7'
            elif (max_profit > (current_profit + 0.015)) and (last_candle['rsi_14'] < 41.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_1_8'
            elif (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_1_9'
            elif (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_1_10'
            elif (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14'] < 42.0):
                return True, 'sell_profit_t_1_11'
            elif (max_profit > (current_profit + 0.01)) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_1_12'
            elif (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_1_13'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_1_14'
        elif 0.03 > current_profit >= 0.02:
            if (max_profit > (current_profit + 0.015)) and (last_candle['rsi_14'] < 40.0):
                return True, 'sell_profit_t_2_1'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_2_2'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_2_3'
            elif (max_profit > (current_profit + 0.02)) and (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_2_4'
            elif (max_profit > (current_profit + 0.02)) and (last_candle['rsi_14'] < 43.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_2_6'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_2_7'
            elif (max_profit > (current_profit + 0.02)) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_2_8'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_2_9'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_2_10'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14'] < 40.0):
                return True, 'sell_profit_t_2_11'
            elif (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_2_12'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_2_13'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 47.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_2_14'
        elif 0.04 > current_profit >= 0.03:
            if (max_profit > (current_profit + 0.02)) and (last_candle['rsi_14'] < 41.0):
                return True, 'sell_profit_t_3_1'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_3_2'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_3_3'
            elif (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_3_4'
            elif (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14'] < 44.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_3_6'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_3_7'
            elif (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_3_8'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_3_9'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_3_10'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14'] < 39.0):
                return True, 'sell_profit_t_3_11'
            elif (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_3_12'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_3_13'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_3_14'
        elif 0.05 > current_profit >= 0.04:
            if (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14'] < 42.0):
                return True, 'sell_profit_t_4_1'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_4_2'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_4_3'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_4_4'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14'] < 45.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_4_6'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_4_7'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_4_8'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_4_9'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_4_10'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 38.0):
                return True, 'sell_profit_t_4_11'
            elif (max_profit > (current_profit + 0.025)) and (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_4_12'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_4_13'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_4_14'
        elif 0.06 > current_profit >= 0.05:
            if (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14'] < 43.0):
                return True, 'sell_profit_t_5_1'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_5_2'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_5_3'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_5_4'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14'] < 46.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_5_6'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_5_7'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_5_8'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_5_9'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_5_10'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14'] < 37.0):
                return True, 'sell_profit_t_5_11'
            elif (max_profit > (current_profit + 0.03)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_5_12'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_5_13'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_5_14'
        elif 0.07 > current_profit >= 0.06:
            if (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14'] < 44.0):
                return True, 'sell_profit_t_6_1'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_6_2'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_6_3'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_6_4'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 45.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_6_6'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_6_7'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_6_8'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_6_9'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_6_10'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14'] < 36.0):
                return True, 'sell_profit_t_6_11'
            elif (max_profit > (current_profit + 0.035)) and (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_6_12'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_6_13'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 43.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_6_14'
        elif 0.08 > current_profit >= 0.07:
            if (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 43.0):
                return True, 'sell_profit_t_7_1'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_7_2'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_7_3'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_7_4'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14'] < 44.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_7_6'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_7_7'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_7_8'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_7_9'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_7_10'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14'] < 36.0):
                return True, 'sell_profit_t_7_11'
            elif (max_profit > (current_profit + 0.04)) and (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_7_12'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_7_13'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_7_14'
        elif 0.09 > current_profit >= 0.08:
            if (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14'] < 42.0):
                return True, 'sell_profit_t_8_1'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_8_2'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_8_3'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_8_4'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14'] < 43.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_8_6'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_8_7'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_8_8'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_8_9'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_8_10'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 36.0):
                return True, 'sell_profit_t_8_11'
            elif (max_profit > (current_profit + 0.045)) and (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_8_12'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_8_13'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_8_14'
        elif 0.1 > current_profit >= 0.09:
            if (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14'] < 41.0):
                return True, 'sell_profit_t_9_1'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_9_2'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_9_3'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_9_4'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14'] < 42.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_9_6'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_9_7'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14'] < 41.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_9_8'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_9_9'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_9_10'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14'] < 36.0):
                return True, 'sell_profit_t_9_11'
            elif (max_profit > (current_profit + 0.05)) and (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_9_12'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_9_13'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_9_14'
        elif 0.12 > current_profit >= 0.1:
            if (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14'] < 40.0):
                return True, 'sell_profit_t_10_1'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_10_2'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_10_3'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_10_4'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 41.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_10_6'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_10_7'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_10_8'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_10_9'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_10_10'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 35.0):
                return True, 'sell_profit_t_10_11'
            elif (max_profit > (current_profit + 0.055)) and (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_10_12'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_10_13'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_10_14'
        elif 0.2 > current_profit >= 0.12:
            if (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 39.0):
                return True, 'sell_profit_t_11_1'
            elif (max_profit > (current_profit + 0.085)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_11_2'
            elif (max_profit > (current_profit + 0.085)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_11_3'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_11_4'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14'] < 40.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_11_6'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_11_7'
            elif (max_profit > (current_profit + 0.065)) and (last_candle['rsi_14'] < 39.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_11_8'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_11_9'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_11_10'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14'] < 34.0):
                return True, 'sell_profit_t_11_11'
            elif (max_profit > (current_profit + 0.06)) and (last_candle['rsi_14'] < 34.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_11_12'
            elif (max_profit > (current_profit + 0.075)) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_11_13'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_11_14'
        elif current_profit >= 0.2:
            if (max_profit > (current_profit + 0.7)) and (last_candle['rsi_14'] < 38.0):
                return True, 'sell_profit_t_12_1'
            elif (max_profit > (current_profit + 0.9)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_12_2'
            elif (max_profit > (current_profit + 0.09)) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_12_3'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.0) and (last_candle['cti_1h'] > 0.8):
                return True, 'sell_profit_t_12_4'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 39.0) and (last_candle['btc_not_downtrend_1h'] == False) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_12_6'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.0):
                return True, 'sell_profit_t_12_7'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 38.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['cmf'] < -0.0) and (last_candle['sma_200_dec_20_1h']):
                return True, 'sell_profit_t_12_8'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0):
                return True, 'sell_profit_t_12_9'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < -0.0) and (last_candle['r_480_1h'] > -20.0):
                return True, 'sell_profit_t_12_10'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14'] < 33.0):
                return True, 'sell_profit_t_12_11'
            elif (max_profit > (current_profit + 0.07)) and (last_candle['rsi_14'] < 33.0) and (last_candle['cmf'] < -0.25):
                return True, 'sell_profit_t_12_12'
            elif (max_profit > (current_profit + 0.08)) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_12_13'
            elif (max_profit > (current_profit + 0.085)) and (last_candle['rsi_14_15m'] < 36.0) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                return True, 'sell_profit_t_12_14'

        return False, None

    def sell_dec_main(self, current_profit: float, last_candle) -> tuple:
        if (last_candle['close'] > last_candle['ema_200']):
            if 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['cti'] < -0.75):
                    return True, 'sell_profit_d_o_1_1'
                elif (last_candle['rsi_14'] < 36.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_1_2'
                elif (last_candle['rsi_14'] < 36.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_1_3'
                elif (last_candle['rsi_14'] > 78.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_1_4'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_1_5'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['rsi_14_15m'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_1_6'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_15m'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_1_7'
                elif (last_candle['rsi_14'] > 70.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_1_8'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_1_9'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_1_10'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_1_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_1_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_1_13'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_1_14'
                elif (last_candle['rsi_14'] > 66.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_1_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_1_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_1_17'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_1_18'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_1_19'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_1_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_1_21'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_1_22'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 30.0):
                    return True, 'sell_profit_d_o_1_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_1_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_1_25'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_1_26'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_1_27'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_1_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_1_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_1_30'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_1_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_1_32'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_1_33'
                elif (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_1_34'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_1_35'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_1_36'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_1_37'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 36.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_2_1'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_2_2'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_2_3'
                elif (last_candle['rsi_14'] > 77.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_2_4'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_2_5'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['rsi_14_15m'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_2_6'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_15m'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_2_7'
                elif (last_candle['rsi_14'] > 65.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_2_8'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_2_9'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_2_10'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_2_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_2_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_2_13'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_2_14'
                elif (last_candle['rsi_14'] > 65.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_2_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_2_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_2_17'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_2_18'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_2_19'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_2_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_2_21'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_2_22'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 30.0):
                    return True, 'sell_profit_d_o_2_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_2_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_2_25'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_2_26'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_2_27'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_2_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_2_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_2_30'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_2_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_2_32'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_2_33'
                elif (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_2_34'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_2_35'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_2_36'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_2_37'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cti'] > 0.4):
                    return True, 'sell_profit_d_o_3_1'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 42.0):
                    return True, 'sell_profit_d_u_3_2'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_3_3'
                elif (last_candle['rsi_14'] > 76.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_3_4'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_3_5'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_15m'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_3_6'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['rsi_14_15m'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_3_7'
                elif (last_candle['rsi_14'] > 64.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_3_8'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_3_9'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_3_10'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_3_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_3_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_3_13'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_3_14'
                elif (last_candle['rsi_14'] > 64.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_3_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_3_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_3_17'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_3_18'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_3_19'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_3_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_3_21'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_3_22'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 32.0):
                    return True, 'sell_profit_d_o_3_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_3_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_3_25'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_3_26'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_3_27'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_3_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_3_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_3_30'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_3_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_3_32'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_3_33'
                elif (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_3_34'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_3_35'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_3_36'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_3_37'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < 0.05) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['cti'] > 0.3):
                    return True, 'sell_profit_d_o_4_1'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 44.0):
                    return True, 'sell_profit_d_o_4_2'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_4_3'
                elif (last_candle['rsi_14'] > 75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_4_4'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_4_5'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_15m'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_4_6'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['rsi_14_15m'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_4_7'
                elif (last_candle['rsi_14'] > 63.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_4_8'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_4_9'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_4_10'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_4_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_4_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_4_13'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_4_14'
                elif (last_candle['rsi_14'] > 63.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_4_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_4_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_4_17'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_4_18'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_4_19'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_4_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_4_21'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_4_22'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 32.0):
                    return True, 'sell_profit_d_o_4_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_4_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_4_25'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_4_26'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_4_27'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_4_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_4_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_4_30'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_4_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_4_32'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_4_33'
                elif (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_4_34'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_4_35'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_4_36'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_4_37'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['cti'] > 0.4):
                    return True, 'sell_profit_d_o_5_1'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 46.0):
                    return True, 'sell_profit_d_o_5_2'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_5_3'
                elif (last_candle['rsi_14'] > 74.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_5_4'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_5_5'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_5_6'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_5_7'
                elif (last_candle['rsi_14'] > 62.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_5_8'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_5_9'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_5_10'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_5_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_5_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_5_13'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_5_14'
                elif (last_candle['rsi_14'] > 62.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_5_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_5_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_5_17'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_5_18'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_5_19'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_5_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_5_21'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_5_22'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_5_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_5_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_5_25'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_5_26'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_5_27'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_5_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_5_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_5_30'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_5_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_5_32'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_5_33'
                elif (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_5_34'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_5_35'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_5_36'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_5_37'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 48.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_6_1'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 44.0):
                    return True, 'sell_profit_d_o_6_2'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_6_3'
                elif (last_candle['rsi_14'] > 75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_6_4'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_6_5'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_15m'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_6_6'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['rsi_14_15m'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_6_7'
                elif (last_candle['rsi_14'] > 63.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_6_8'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_6_9'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_6_10'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_6_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_6_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_6_13'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_6_14'
                elif (last_candle['rsi_14'] > 63.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_6_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_6_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_6_17'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_6_18'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_6_19'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_6_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_6_21'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_6_22'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_6_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_6_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_6_25'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_6_26'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_6_27'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_6_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_6_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_6_30'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_6_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_6_32'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_6_33'
                elif (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_6_34'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_6_35'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_6_36'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_6_37'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 46.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_7_1'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 42.0):
                    return True, 'sell_profit_d_o_7_2'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_7_3'
                elif (last_candle['rsi_14'] > 76.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_7_4'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_7_5'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_15m'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_7_6'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['rsi_14_15m'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_7_7'
                elif (last_candle['rsi_14'] > 64.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_7_8'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_7_9'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_7_10'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_7_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_7_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_7_13'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_7_14'
                elif (last_candle['rsi_14'] > 64.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_7_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_7_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_7_17'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_7_18'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_7_19'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_7_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_7_21'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_7_22'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_7_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_7_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_7_25'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_7_26'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_7_27'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_7_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_7_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_7_30'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_7_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_7_32'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_7_33'
                elif (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_7_34'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_7_35'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_7_36'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_7_37'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 44.0) and (last_candle['cti_1h'] > 0.5):
                    return True, 'sell_profit_d_o_8_1'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_8_2'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_8_3'
                elif (last_candle['rsi_14'] > 77.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_8_4'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_8_5'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['rsi_14_15m'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_8_6'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_15m'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_8_7'
                elif (last_candle['rsi_14'] > 65.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_8_8'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_8_9'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_8_10'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_8_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_8_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_8_13'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_8_14'
                elif (last_candle['rsi_14'] > 65.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_8_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_8_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_8_17'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_8_18'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_8_19'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_8_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_8_21'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_8_22'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_8_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_8_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_8_25'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_8_26'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_8_27'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_8_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_8_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_8_30'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_8_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_8_32'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_8_33'
                elif (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_8_34'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_8_35'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_8_36'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_8_37'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 42.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_9_1'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_9_2'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_9_3'
                elif (last_candle['rsi_14'] > 78.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_9_4'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_9_5'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['rsi_14_15m'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_9_6'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_15m'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_9_7'
                elif (last_candle['rsi_14'] > 66.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_9_8'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_9_9'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_9_10'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_9_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_9_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_9_13'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_9_14'
                elif (last_candle['rsi_14'] > 66.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_9_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_9_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_9_17'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_9_18'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_9_19'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_9_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_9_21'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_9_22'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_9_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_9_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_9_25'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_9_26'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_9_27'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_9_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_9_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_9_30'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_9_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_9_32'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_9_33'
                elif (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_9_34'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_9_35'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_9_36'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_9_37'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 36.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_10_1'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 36.0):
                    return True, 'sell_profit_d_o_10_2'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_10_3'
                elif (last_candle['rsi_14'] > 79.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_10_4'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_10_5'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_10_6'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_10_7'
                elif (last_candle['rsi_14'] > 67.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_10_8'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_10_9'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_10_10'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_10_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_10_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_10_13'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_10_14'
                elif (last_candle['rsi_14'] > 67.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_10_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_10_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_10_17'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_10_18'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_10_19'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_10_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_10_21'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_10_22'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_10_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_10_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_10_25'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_10_26'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_10_27'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_10_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_10_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_10_30'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_10_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_10_32'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_10_33'
                elif (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_10_34'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_10_35'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_10_36'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_10_37'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_11_1'
                elif (last_candle['rsi_14'] < 36.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 34.0):
                    return True, 'sell_profit_d_o_11_2'
                elif (last_candle['rsi_14'] < 36.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 33.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_11_3'
                elif (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_11_4'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_11_5'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['rsi_14_15m'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_11_6'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['rsi_14_15m'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_11_7'
                elif (last_candle['rsi_14'] > 68.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_11_8'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_11_9'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_11_10'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_11_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_11_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_11_13'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_11_14'
                elif (last_candle['rsi_14'] > 68.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_11_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_11_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_11_17'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_11_18'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_11_19'
                elif (last_candle['rsi_14'] < 37.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_11_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_11_21'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_11_22'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_11_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_11_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_11_25'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_11_26'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_11_27'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_11_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_11_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_11_30'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_11_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_11_32'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_11_33'
                elif (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_11_34'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_11_35'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_11_36'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_11_37'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['cti'] > 0.5):
                    return True, 'sell_profit_d_o_12_1'
                elif (last_candle['rsi_14'] < 35.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 32.0):
                    return True, 'sell_profit_d_o_12_2'
                elif (last_candle['rsi_14'] < 35.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 32.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_12_3'
                elif (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_o_12_4'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_o_12_5'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['rsi_14_15m'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_12_6'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['rsi_14_15m'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_12_7'
                elif (last_candle['rsi_14'] > 69.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_o_12_8'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_o_12_9'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_o_12_10'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_o_12_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_o_12_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_o_12_13'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_12_14'
                elif (last_candle['rsi_14'] > 69.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_12_15'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_12_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_o_12_17'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_o_12_18'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_o_12_19'
                elif (last_candle['rsi_14'] < 36.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_12_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_12_21'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_12_22'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_o_12_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_12_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_o_12_25'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_12_26'
                elif (last_candle['rsi_14'] < 37.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_o_12_27'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_o_12_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_o_12_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_o_12_30'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_o_12_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_o_12_32'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_o_12_33'
                elif (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_o_12_34'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_o_12_35'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_12_36'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_o_12_37'
        else:
            if 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 35.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_1_1'
                elif (last_candle['rsi_14'] < 37.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 42.0):
                    return True, 'sell_profit_d_u_1_2'
                elif (last_candle['rsi_14'] < 37.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_1_3'
                elif (last_candle['rsi_14'] > 77.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_1_4'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_1_5'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['rsi_14_15m'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_1_6'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_15m'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_1_7'
                elif (last_candle['rsi_14'] > 68.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_1_8'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_1_9'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_1_10'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_1_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 59.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_1_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_1_13'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_1_14'
                elif (last_candle['rsi_14'] > 63.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_1_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_1_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_1_17'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_1_18'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_1_19'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_1_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_1_21'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_1_22'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 30.0):
                    return True, 'sell_profit_d_u_1_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_1_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_1_25'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_1_26'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_1_27'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_1_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_1_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_1_30'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_1_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_1_32'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_1_33'
                elif (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_1_34'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_1_35'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_1_36'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_1_37'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 37.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_2_1'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 44.0):
                    return True, 'sell_profit_d_u_2_2'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_2_3'
                elif (last_candle['rsi_14'] > 76.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_2_4'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_2_5'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_15m'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_2_6'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_15m'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_2_7'
                elif (last_candle['rsi_14'] > 62.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_2_8'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_2_9'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_2_10'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_2_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 58.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_2_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_2_13'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_2_14'
                elif (last_candle['rsi_14'] > 62.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_2_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_2_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_2_17'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_2_18'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_2_19'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_2_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_2_21'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_2_22'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 30.0):
                    return True, 'sell_profit_d_u_2_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_2_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_2_25'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_2_26'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_2_27'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_2_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_2_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_2_30'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_2_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_2_32'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_2_33'
                elif (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_2_34'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_2_35'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_2_36'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_2_37'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 39.5) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_3_1'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 46.0):
                    return True, 'sell_profit_d_u_3_2'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_3_3'
                elif (last_candle['rsi_14'] > 75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_3_4'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_3_5'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_15m'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_3_6'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_15m'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_3_7'
                elif (last_candle['rsi_14'] > 61.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_3_8'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_3_9'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_3_10'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_3_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 57.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_3_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_3_13'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_3_14'
                elif (last_candle['rsi_14'] > 61.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_3_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_3_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_3_17'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_3_18'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_3_19'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_3_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_3_21'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_3_22'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 32.0):
                    return True, 'sell_profit_d_u_3_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_3_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_3_25'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_3_26'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_3_27'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_3_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_3_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_3_30'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_3_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_3_32'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_3_33'
                elif (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_3_34'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_3_35'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_3_36'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_3_37'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 40.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_4_1'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 46.0):
                    return True, 'sell_profit_d_u_4_2'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_4_3'
                elif (last_candle['rsi_14'] > 74.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_4_4'
                elif (last_candle['rsi_14'] < 51.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_4_5'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_4_6'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_4_7'
                elif (last_candle['rsi_14'] > 60.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_4_8'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_4_9'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_4_10'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_4_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 56.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_4_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_4_13'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_4_14'
                elif (last_candle['rsi_14'] > 60.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_4_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_4_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_4_17'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_4_18'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_4_19'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_4_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_4_21'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_4_22'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 32.0):
                    return True, 'sell_profit_d_u_4_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_4_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_4_25'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_4_26'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_4_27'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_4_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_4_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_4_30'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_4_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_4_32'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_4_33'
                elif (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_4_34'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_4_35'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_4_36'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_4_37'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 39.5) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_5_1'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 50.0):
                    return True, 'sell_profit_d_u_5_2'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_5_3'
                elif (last_candle['rsi_14'] > 73.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_5_4'
                elif (last_candle['rsi_14'] < 52.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_5_5'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['rsi_14_15m'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_5_6'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['rsi_14_15m'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_5_7'
                elif (last_candle['rsi_14'] > 59.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_5_8'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_5_9'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_5_10'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_5_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 55.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_5_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_5_13'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_5_14'
                elif (last_candle['rsi_14'] > 59.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_5_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_5_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_5_17'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_5_18'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_5_19'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_5_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_5_21'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_5_22'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_5_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_5_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_5_25'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_5_26'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_5_27'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_5_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_5_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_5_30'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_5_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_5_32'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_5_33'
                elif (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_5_34'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_5_35'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_5_36'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_5_37'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 39.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_6_1'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 48.0):
                    return True, 'sell_profit_d_u_6_2'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_6_3'
                elif (last_candle['rsi_14'] > 74.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_6_4'
                elif (last_candle['rsi_14'] < 51.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_6_5'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_6_6'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['rsi_14_15m'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_6_7'
                elif (last_candle['rsi_14'] > 60.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_6_8'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_6_9'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_6_10'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_6_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 56.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_6_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_6_13'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_6_14'
                elif (last_candle['rsi_14'] > 60.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_6_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_6_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_6_17'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_6_18'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_6_19'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_6_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_6_21'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_6_22'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_6_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_6_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_6_25'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_6_26'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_6_27'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_6_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_6_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_6_30'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_6_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_6_32'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_6_33'
                elif (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_6_34'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_6_35'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_6_36'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_6_37'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 38.5) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_7_1'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 46.0):
                    return True, 'sell_profit_d_u_7_2'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_7_3'
                elif (last_candle['rsi_14'] > 75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_7_4'
                elif (last_candle['rsi_14'] < 50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_7_5'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_15m'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_7_6'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_15m'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_7_7'
                elif (last_candle['rsi_14'] > 61.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_7_8'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_7_9'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_7_10'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_7_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 57.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_7_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_7_13'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_7_14'
                elif (last_candle['rsi_14'] > 61.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_7_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_7_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_7_17'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_7_18'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_7_19'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_7_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_7_21'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_7_22'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_7_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_7_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_7_25'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_7_26'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_7_27'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_7_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_7_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_7_30'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_7_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_7_32'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_7_33'
                elif (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_7_34'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_7_35'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_7_36'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_7_37'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 38.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_8_1'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 44.0):
                    return True, 'sell_profit_d_u_8_2'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_8_3'
                elif (last_candle['rsi_14'] > 76.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_8_4'
                elif (last_candle['rsi_14'] < 49.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_8_5'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_15m'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_8_6'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_15m'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_8_7'
                elif (last_candle['rsi_14'] > 62.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_8_8'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_8_9'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_8_10'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_8_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 58.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_8_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_8_13'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_8_14'
                elif (last_candle['rsi_14'] > 62.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_8_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_8_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_8_17'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_8_18'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_8_19'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_8_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_8_21'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_8_22'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_8_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_8_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_8_25'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_8_26'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_8_27'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_8_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_8_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_8_30'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_8_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_8_32'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_8_33'
                elif (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_8_34'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_8_35'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_8_36'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_8_37'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 37.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_9_1'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 42.0):
                    return True, 'sell_profit_d_u_9_2'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_9_3'
                elif (last_candle['rsi_14'] > 77.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_9_4'
                elif (last_candle['rsi_14'] < 48.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_9_5'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['rsi_14_15m'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_9_6'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_15m'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_9_7'
                elif (last_candle['rsi_14'] > 63.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_9_8'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_9_9'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_9_10'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_9_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 59.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_9_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_9_13'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_9_14'
                elif (last_candle['rsi_14'] > 63.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_9_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_9_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_9_17'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_9_18'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_9_19'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_9_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_9_21'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_9_22'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_9_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_9_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_9_25'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_9_26'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_9_27'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_9_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_9_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_9_30'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_9_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_9_32'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_9_33'
                elif (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_9_34'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_9_35'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_9_36'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_9_37'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 37.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 36.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_10_1'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_10_2'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_10_3'
                elif (last_candle['rsi_14'] > 78.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_10_4'
                elif (last_candle['rsi_14'] < 47.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_10_5'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['rsi_14_15m'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_10_6'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['rsi_14_15m'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_10_7'
                elif (last_candle['rsi_14'] > 64.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_10_8'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_10_9'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_10_10'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_10_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_10_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_10_13'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_10_14'
                elif (last_candle['rsi_14'] > 64.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_10_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_10_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_10_17'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_10_18'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_10_19'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_10_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_10_21'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_10_22'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_10_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_10_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_10_25'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_10_26'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_10_27'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_10_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_10_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_10_30'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_10_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_10_32'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_10_33'
                elif (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_10_34'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_10_35'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_10_36'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_10_37'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 35.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 35.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_11_1'
                elif (last_candle['rsi_14'] < 37.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_11_2'
                elif (last_candle['rsi_14'] < 37.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 33.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_11_3'
                elif (last_candle['rsi_14'] > 79.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_11_4'
                elif (last_candle['rsi_14'] < 46.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_11_5'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_11_6'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_11_7'
                elif (last_candle['rsi_14'] > 65.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_11_8'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_11_9'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_11_10'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_11_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_11_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_11_13'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_11_14'
                elif (last_candle['rsi_14'] > 65.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_11_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_11_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_11_17'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_11_18'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_11_19'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_11_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_11_21'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_11_22'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_11_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_11_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_11_25'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_11_26'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_11_27'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_11_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_11_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_11_30'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_11_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_11_32'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_11_33'
                elif (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_11_34'
                elif (last_candle['rsi_14'] < 44.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_11_35'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_11_36'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_11_37'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 33.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.05) and (last_candle['rsi_14_1h'] < 34.0) and (last_candle['cti_1h'] < -0.85):
                    return True, 'sell_profit_d_u_12_1'
                elif (last_candle['rsi_14'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 36.0):
                    return True, 'sell_profit_d_u_12_2'
                elif (last_candle['rsi_14'] < 34.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['rsi_14_1h'] < 32.0) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_12_3'
                elif (last_candle['rsi_14'] > 80.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_1h']):
                    return True, 'sell_profit_d_u_12_4'
                elif (last_candle['rsi_14'] < 45.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -50.0) and (last_candle['rsi_14_1h'] < 47.0):
                    return True, 'sell_profit_d_u_12_5'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['rsi_14_15m'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.25) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_12_6'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['rsi_14_15m'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.4) and (last_candle['cmf_15m'] < -0.25) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_12_7'
                elif (last_candle['rsi_14'] > 66.0) and (last_candle['r_480'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -90.0):
                    return True, 'sell_profit_d_u_12_8'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.25) and (last_candle['cti_1h'] > 0.9):
                    return True, 'sell_profit_d_u_12_9'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96'] < -75.0):
                    return True, 'sell_profit_d_u_12_10'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1):
                    return True, 'sell_profit_d_u_12_11'
                elif (last_candle['r_14'] > -15.0) and (last_candle['r_32'] > -25.0) and (last_candle['r_480'] > -20.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 50.0) and (last_candle['rsi_14_1h'] < 55.0) and (last_candle['r_96_15m'] > -50.0) and (last_candle['r_480_1h'] > -20.0):
                    return True, 'sell_profit_d_u_12_12'
                elif (last_candle['r_14'] > -20.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_15m'] < 40.0) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_480_1h'] < -70.0):
                    return True, 'sell_profit_d_u_12_13'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['r_96'] < -75.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_12_14'
                elif (last_candle['rsi_14'] > 65.0) and (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_12_15'
                elif (last_candle['r_14'] > -30.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_12_16'
                elif (last_candle['r_14'] > -25.0) and (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -85.0) and (last_candle['r_480_1h'] > -25.0):
                    return True, 'sell_profit_d_u_12_17'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -80.0) and (last_candle['r_480_1h'] > -30.0):
                    return True, 'sell_profit_d_u_12_18'
                elif (last_candle['rsi_14'] < 37.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.1) and (last_candle['cmf_1h'] < -0.0):
                    return True, 'sell_profit_d_u_12_19'
                elif (last_candle['rsi_14'] < 37.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_12_20'
                elif (last_candle['r_14'] > -8.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] < -75.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_12_21'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_12_22'
                elif (last_candle['rsi_14'] < 41.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 35.0):
                    return True, 'sell_profit_d_u_12_23'
                elif (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cti'] > 0.85) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_12_24'
                elif (last_candle['r_14'] > -10.0) and (last_candle['r_32'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cti'] > 0.8) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 50.0) and (last_candle['r_96_15m'] < -75.0):
                    return True, 'sell_profit_d_u_12_25'
                elif (last_candle['rsi_14'] < 39.0) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['cmf_15m'] < -0.2) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_12_26'
                elif (last_candle['rsi_14'] < 38.0) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.2) and (last_candle['rsi_14_1h'] < 55.0):
                    return True, 'sell_profit_d_u_12_27'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['rsi_14_15m'] < 34.0) and (last_candle['rsi_14_1h'] < 38.0):
                    return True, 'sell_profit_d_u_12_28'
                elif (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -80.0):
                    return True, 'sell_profit_d_u_12_29'
                elif (last_candle['r_14'] > -20.0) and (last_candle['r_480'] < -50.0) and (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['rsi_14_1h'] < 41.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -75.0):
                    return True, 'sell_profit_d_u_12_30'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['cmf_15m'] < -0.15) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] < -45.0) and (last_candle['r_480_1h'] > -30.0) and (last_candle['rsi_14_15m'] < 45.0):
                    return True, 'sell_profit_d_u_12_31'
                elif (last_candle['r_480'] < -70.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 220.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -70.0) and (last_candle['cti_1h'] < -0.75):
                    return True, 'sell_profit_d_u_12_32'
                elif (last_candle['rsi_14'] < 40.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 40.0) and(last_candle['r_96_15m'] < -85.0):
                    return True, 'sell_profit_d_u_12_33'
                elif (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0) and (last_candle['rsi_14_1h'] < 45.0):
                    return True, 'sell_profit_d_u_12_34'
                elif (last_candle['rsi_14'] < 43.0) and (last_candle['sma_200_dec_20']) and (last_candle['sma_200_dec_20_15m']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 45.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                    return True, 'sell_profit_d_u_12_35'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_1h'] < -0.1) and (last_candle['r_96_15m'] < -50.0) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_12_36'
                elif (last_candle['rsi_14'] < 42.0) and (last_candle['sma_200_dec_20']) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.1) and (last_candle['rsi_14_1h'] < 40.0):
                    return True, 'sell_profit_d_u_12_37'

        return False, None

    def sell_pump_main(self, current_profit: float, last_candle) -> tuple:
        if (last_candle['hl_pct_change_48_1h'] > 0.9):
            if (last_candle['ema_vwma_osc_96'] > 0.0):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_p_bull_48_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_p_bull_48_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_p_bull_48_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_p_bull_48_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 49.0):
                        return True, 'sell_profit_p_bull_48_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_p_bull_48_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_p_bull_48_1_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_p_bull_48_1_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_p_bull_48_1_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 41.0):
                        return True, 'sell_profit_p_bull_48_1_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 37.0):
                        return True, 'sell_profit_p_bull_48_1_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 35.0):
                        return True, 'sell_profit_p_bull_48_1_1_1'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_p_bear_48_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_p_bear_48_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_p_bear_48_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 51.0):
                        return True, 'sell_profit_p_bear_48_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_p_bear_48_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 49.0):
                        return True, 'sell_profit_p_bear_48_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_p_bear_48_1_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_p_bear_48_1_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_p_bear_48_1_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_p_bear_48_1_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 39.0):
                        return True, 'sell_profit_p_bear_48_1_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 36.0):
                        return True, 'sell_profit_p_bear_48_1_1_1'

        if (last_candle['hl_pct_change_48_1h'] > 0.8):
            if (last_candle['ema_vwma_osc_96'] > 0.0):
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
                    if (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_2_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_2_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bull_48_2_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bull_48_2_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_2_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_2_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_2_1_1'
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
                    if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.1):
                        return True, 'sell_profit_p_bear_48_2_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.15):
                        return True, 'sell_profit_p_bear_48_2_1_1'

        if (last_candle['hl_pct_change_48_1h'] > 0.5):
            if (last_candle['ema_vwma_osc_96'] > 0.0):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 32.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bull_48_3_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 33.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bull_48_3_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 35.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bull_48_3_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.3):
                        return True, 'sell_profit_p_bull_48_3_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 45.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 43.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bull_48_3_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 41.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 39.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 37.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bull_48_3_1_1'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 33.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bear_48_3_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 34.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bear_48_3_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 36.0) and (last_candle['cmf'] < -0.35):
                        return True, 'sell_profit_p_bear_48_3_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.3):
                        return True, 'sell_profit_p_bear_48_3_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 48.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 44.0) and (last_candle['cmf'] < -0.2):
                        return True, 'sell_profit_p_bear_48_3_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 42.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 38.0) and (last_candle['cmf'] < -0.25):
                        return True, 'sell_profit_p_bear_48_3_1_1'

        if (last_candle['hl_pct_change_36_1h'] > 0.72):
            if (last_candle['ema_vwma_osc_96'] > 0.0):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 32.0):
                        return True, 'sell_profit_p_bull_36_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_p_bull_36_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_p_bull_36_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_p_bull_36_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 49.0):
                        return True, 'sell_profit_p_bull_36_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_p_bull_36_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_p_bull_36_1_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_p_bull_36_1_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_p_bull_36_1_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0):
                        return True, 'sell_profit_p_bull_36_1_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 36.0):
                        return True, 'sell_profit_p_bull_36_1_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 34.0):
                        return True, 'sell_profit_p_bull_36_1_1_1'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 33.0):
                        return True, 'sell_profit_p_bear_36_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 35.0):
                        return True, 'sell_profit_p_bear_36_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_p_bear_36_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 51.0):
                        return True, 'sell_profit_p_bear_36_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_p_bear_36_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 49.0):
                        return True, 'sell_profit_p_bear_36_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_p_bear_36_1_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_p_bear_36_1_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_p_bear_36_1_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 41.0):
                        return True, 'sell_profit_p_bear_36_1_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 37.0):
                        return True, 'sell_profit_p_bear_36_1_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 35.0):
                        return True, 'sell_profit_p_bear_36_1_1_1'

        if (last_candle['hl_pct_change_24_1h'] > 0.68):
            if (last_candle['ema_vwma_osc_96'] > 0.0):
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 41.0):
                        return True, 'sell_profit_p_bull_24_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_p_bull_24_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_p_bull_24_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 51.0):
                        return True, 'sell_profit_p_bull_24_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 49.0):
                        return True, 'sell_profit_p_bull_24_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 47.0):
                        return True, 'sell_profit_p_bull_24_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 45.0):
                        return True, 'sell_profit_p_bull_24_1_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 43.0):
                        return True, 'sell_profit_p_bull_24_1_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 41.0):
                        return True, 'sell_profit_p_bull_24_1_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 39.0):
                        return True, 'sell_profit_p_bull_24_1_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 37.0):
                        return True, 'sell_profit_p_bull_24_1_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 35.0):
                        return True, 'sell_profit_p_bull_24_1_1_1'
            else:
                if current_profit >= 0.2:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_p_bear_24_1_12_1'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_p_bear_24_1_11_1'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_p_bear_24_1_10_1'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['rsi_14'] < 52.0):
                        return True, 'sell_profit_p_bear_24_1_9_1'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['rsi_14'] < 50.0):
                        return True, 'sell_profit_p_bear_24_1_8_1'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['rsi_14'] < 48.0):
                        return True, 'sell_profit_p_bear_24_1_7_1'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['rsi_14'] < 46.0):
                        return True, 'sell_profit_p_bear_24_1_6_1'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['rsi_14'] < 44.0):
                        return True, 'sell_profit_p_bear_24_1_5_1'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['rsi_14'] < 42.0):
                        return True, 'sell_profit_p_bear_24_1_4_1'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['rsi_14'] < 40.0):
                        return True, 'sell_profit_p_bear_24_1_3_1'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['rsi_14'] < 38.0):
                        return True, 'sell_profit_p_bear_24_1_2_1'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['rsi_14'] < 36.0):
                        return True, 'sell_profit_p_bear_24_1_1_1'

        if (last_candle['hl_pct_change_24_1h'] > 0.5):
            if (last_candle['ema_vwma_osc_96'] > 0.0):
                if current_profit >= 0.2:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_12_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_12_2'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_11_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_11_2'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_10_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_10_2'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_9_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_9_2'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_8_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_8_2'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_7_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_7_2'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_6_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_6_2'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_5_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_5_2'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_4_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_4_2'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_3_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_3_2'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_2_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_2_2'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bull_24_2_1_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bull_24_2_1_2'
            else:
                if current_profit >= 0.2:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_12_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_12_2'
                elif 0.2 > current_profit >= 0.12:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_11_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_11_2'
                elif 0.12 > current_profit >= 0.1:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_10_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_10_2'
                elif 0.1 > current_profit >= 0.09:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_9_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_9_2'
                elif 0.09 > current_profit >= 0.08:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_8_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_8_2'
                elif 0.08 > current_profit >= 0.07:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_7_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_7_2'
                elif 0.07 > current_profit >= 0.06:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_6_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_6_2'
                elif 0.06 > current_profit >= 0.05:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_5_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 60.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_5_2'
                elif 0.05 > current_profit >= 0.04:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_4_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_4_2'
                elif 0.04 > current_profit >= 0.03:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_3_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_3_2'
                elif 0.03 > current_profit >= 0.02:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_2_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_2_2'
                elif 0.02 > current_profit >= 0.01:
                    if (last_candle['r_14'] > -4.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 240.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['cmf_1h'] < -0.0):
                        return True, 'sell_profit_p_bear_24_2_1_1'
                    elif (last_candle['r_14'] > -18.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cti'] > 0.9) and (last_candle['sma_200_dec_20_15m']) and (last_candle['sma_200_dec_20_1h']) and (last_candle['cmf'] < -0.0) and (last_candle['cmf_15m'] < -0.0) and (last_candle['r_96_15m'] < -50.0) and (last_candle['r_480_1h'] < -50.0):
                        return True, 'sell_profit_p_bear_24_2_1_2'

        return False, None

    def sell_pump_stoploss(self, current_profit: float, max_profit: float, max_loss: float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if (last_candle['hl_pct_change_48_1h'] > 0.95):
            if (
                    (-0.04 > current_profit > -0.08)
                    and (max_profit < 0.005)
                    and (max_loss < 0.08)
                    and (last_candle['close'] < last_candle['ema_200'])
                    and (last_candle['sma_200_dec_20'])
                    and (last_candle['ema_vwma_osc_32'] < 0.0)
                    and (last_candle['ema_vwma_osc_64'] < 0.0)
                    and (last_candle['ema_vwma_osc_96'] < 0.0)
                    and (last_candle['cmf'] < -0.25)
                    and (last_candle['cmf_15m'] < -0.25)
                    and (last_candle['cmf_1h'] < -0.0)
            ):
                return True, 'sell_stoploss_p_48_1_1'
            elif (
                    (-0.04 > current_profit > -0.08)
                    and (max_profit < 0.01)
                    and (max_loss < 0.08)
                    and (last_candle['close'] < last_candle['ema_200'])
                    and (last_candle['sma_200_dec_20'])
                    and (last_candle['ema_vwma_osc_32'] < 0.0)
                    and (last_candle['ema_vwma_osc_64'] < 0.0)
                    and (last_candle['ema_vwma_osc_96'] < 0.0)
                    and (last_candle['cmf'] < -0.25)
                    and (last_candle['cmf_15m'] < -0.25)
                    and (last_candle['cmf_1h'] < -0.0)
            ):
                return True, 'sell_stoploss_p_48_1_2'

        if (last_candle['hl_pct_change_36_1h'] > 0.7):
            if (
                    (-0.04 > current_profit > -0.08)
                    and (max_loss < 0.08)
                    and (max_profit > (current_profit + 0.1))
                    and (last_candle['close'] < last_candle['ema_200'])
                    and (last_candle['sma_200_dec_20'])
                    and (last_candle['sma_200_dec_20_1h'])
                    and (last_candle['ema_vwma_osc_32'] < 0.0)
                    and (last_candle['ema_vwma_osc_64'] < 0.0)
                    and (last_candle['ema_vwma_osc_96'] < 0.0)
                    and (last_candle['cmf'] < -0.25)
                    and (last_candle['cmf_15m'] < -0.25)
                    and (last_candle['cmf_1h'] < -0.0)
            ):
                return True, 'sell_stoploss_p_36_1_1'

        if (last_candle['hl_pct_change_36_1h'] > 0.5):
            if (
                    (-0.05 > current_profit > -0.08)
                    and (max_loss < 0.08)
                    and (max_profit > (current_profit + 0.1))
                    and (last_candle['close'] < last_candle['ema_200'])
                    and (last_candle['sma_200_dec_20'])
                    and (last_candle['sma_200_dec_20_1h'])
                    and (last_candle['ema_vwma_osc_32'] < 0.0)
                    and (last_candle['ema_vwma_osc_64'] < 0.0)
                    and (last_candle['ema_vwma_osc_96'] < 0.0)
                    and (last_candle['cmf'] < -0.25)
                    and (last_candle['cmf_15m'] < -0.25)
                    and (last_candle['cmf_1h'] < -0.0)
                    and (last_candle['rsi_14'] < 40.0)
            ):
                return True, 'sell_stoploss_p_36_2_1'

        if (last_candle['hl_pct_change_24_1h'] > 0.6):
            if (
                    (-0.04 > current_profit > -0.08)
                    and (max_loss < 0.08)
                    and (max_profit < 0.01)
                    and (last_candle['close'] < last_candle['ema_200'])
                    and (last_candle['sma_200_dec_20'])
                    and (last_candle['sma_200_dec_20_1h'])
                    and (last_candle['ema_vwma_osc_32'] < 0.0)
                    and (last_candle['ema_vwma_osc_64'] < 0.0)
                    and (last_candle['ema_vwma_osc_96'] < 0.0)
                    and (last_candle['cmf'] < -0.25)
                    and (last_candle['cmf_15m'] < -0.25)
                    and (last_candle['cmf_1h'] < -0.0)
            ):
                return True, 'sell_stoploss_p_24_1_1'


        return False, None

    def sell_pivot(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, trade: 'Trade', current_time: 'datetime') -> tuple:
        if (last_candle['close'] > (last_candle['res3_1d'] * 1.2)):
            if (0.02 > current_profit >= 0.01):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_1_1'
            elif (0.03 > current_profit >= 0.02):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_2_1'
            elif (0.04 > current_profit >= 0.03):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_3_1'
            elif (0.05 > current_profit >= 0.04):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_4_1'
            elif (0.06 > current_profit >= 0.05):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_5_1'
            elif (0.07 > current_profit >= 0.06):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_6_1'
            elif (0.08 > current_profit >= 0.07):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_7_1'
            elif (0.09 > current_profit >= 0.08):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 69.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_8_1'
            elif (0.1 > current_profit >= 0.09):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_9_1'
            elif (0.12 > current_profit >= 0.1):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_10_1'
            elif (0.2 > current_profit >= 0.12):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_11_1'
            elif (current_profit >= 0.2):
                if (last_candle['r_14'] > -10.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['cci'] > 260.0) and (last_candle['cmf_15m'] < -0.1):
                    return True, 'sell_profit_pv_1_12_1'

        if (last_candle['close'] > (last_candle['res3_1d'] * 1.1)):
            if (0.02 > current_profit >= 0.01):
                if (last_candle['rsi_14'] < 43.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_1_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_1_2'
            elif (0.03 > current_profit >= 0.02):
                if (last_candle['rsi_14'] < 44.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_2_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_2_2'
            elif (0.04 > current_profit >= 0.03):
                if (last_candle['rsi_14'] < 45.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_3_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_3_2'
            elif (0.05 > current_profit >= 0.04):
                if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_4_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_4_2'
            elif (0.06 > current_profit >= 0.05):
                if (last_candle['rsi_14'] < 47.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_5_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 61.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_5_2'
            elif (0.07 > current_profit >= 0.06):
                if (last_candle['rsi_14'] < 46.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_6_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 62.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_6_2'
            elif (0.08 > current_profit >= 0.07):
                if (last_candle['rsi_14'] < 45.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_7_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 63.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_7_2'
            elif (0.09 > current_profit >= 0.08):
                if (last_candle['rsi_14'] < 44.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_8_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 64.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_8_2'
            elif (0.1 > current_profit >= 0.09):
                if (last_candle['rsi_14'] < 43.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_9_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 65.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_9_2'
            elif (0.12 > current_profit >= 0.1):
                if (last_candle['rsi_14'] < 42.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_10_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 66.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_10_2'
            elif (0.2 > current_profit >= 0.12):
                if (last_candle['rsi_14'] < 41.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_11_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 67.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_11_2'
            elif (current_profit >= 0.2):
                if (last_candle['rsi_14'] < 40.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_12_1'
                elif (last_candle['r_14'] > -3.0) and (last_candle['rsi_14'] > 68.0) and (last_candle['cmf_15m'] < -0.1) and (last_candle['cmf_1h'] < -0.0) and (last_candle['r_96_15m'] > -35.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_2_12_2'

        if (last_candle['close'] > (last_candle['res1_1d'] * 1.0)):
            if (0.02 > current_profit >= 0.01):
                if (last_candle['rsi_14'] < 37.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_1_1'
            elif (0.03 > current_profit >= 0.02):
                if (last_candle['rsi_14'] < 38.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_2_1'
            elif (0.04 > current_profit >= 0.03):
                if (last_candle['rsi_14'] < 39.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_3_1'
            elif (0.05 > current_profit >= 0.04):
                if (last_candle['rsi_14'] < 40.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_4_1'
            elif (0.06 > current_profit >= 0.05):
                if (last_candle['rsi_14'] < 41.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_5_1'
            elif (0.07 > current_profit >= 0.06):
                if (last_candle['rsi_14'] < 40.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_6_1'
            elif (0.08 > current_profit >= 0.07):
                if (last_candle['rsi_14'] < 39.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_7_1'
            elif (0.09 > current_profit >= 0.08):
                if (last_candle['rsi_14'] < 38.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_8_1'
            elif (0.1 > current_profit >= 0.09):
                if (last_candle['rsi_14'] < 37.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_9_1'
            elif (0.12 > current_profit >= 0.1):
                if (last_candle['rsi_14'] < 36.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_10_1'
            elif (0.2 > current_profit >= 0.12):
                if (last_candle['rsi_14'] < 35.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_11_1'
            elif (current_profit >= 0.2):
                if (last_candle['rsi_14'] < 34.0) and (last_candle['r_480_1h'] > -50.0) and (last_candle['rsi_14_1h'] > 60.0):
                    return True, 'sell_profit_pv_3_12_1'

        if (last_candle['close'] > (last_candle['res3_1d'] * 1.8)):
            if (0.02 > current_profit >= 0.01):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_1_1'
            elif (0.03 > current_profit >= 0.02):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_2_1'
            elif (0.04 > current_profit >= 0.03):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_3_1'
            elif (0.05 > current_profit >= 0.04):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_4_1'
            elif (0.06 > current_profit >= 0.05):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 48.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_5_1'
            elif (0.07 > current_profit >= 0.06):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 47.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_6_1'
            elif (0.08 > current_profit >= 0.07):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 46.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_7_1'
            elif (0.09 > current_profit >= 0.08):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 45.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_8_1'
            elif (0.1 > current_profit >= 0.09):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 44.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_9_1'
            elif (0.12 > current_profit >= 0.1):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 43.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_10_1'
            elif (0.2 > current_profit >= 0.12):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 42.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_11_1'
            elif (current_profit >= 0.2):
                if (last_candle['r_480'] > -35.0) and (last_candle['rsi_14'] < 41.0) and (last_candle['rsi_14_1h'] > 50.0) and (last_candle['r_480_1h'] > -35.0):
                    return True, 'sell_profit_pv_4_12_1'

        return False, None

    def sell_long_mode(self, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Original sell signals
        sell, signal_name = self.sell_signals(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, buy_tag)
        if sell and (signal_name is not None):
            return True, signal_name

        # Stoplosses
        sell, signal_name = self.sell_stoploss(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
        if sell and (signal_name is not None):
            return True, signal_name

        if (0.0 < current_profit <= 0.02) and (max_profit - current_profit > 0.025) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_0'
        elif (0.02 < current_profit <= 0.04) and (max_profit - current_profit > 0.03) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_1'
        elif (0.04 < current_profit <= 0.06) and (max_profit - current_profit > 0.035) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_2'
        elif (0.06 < current_profit <= 0.08) and (max_profit - current_profit > 0.04) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_3'
        elif (0.08 < current_profit <= 0.1) and (max_profit - current_profit > 0.045) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_4'
        elif (0.1 < current_profit <= 0.12) and (max_profit - current_profit > 0.05) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_5'
        elif (0.12 < current_profit <= 0.14) and (max_profit - current_profit > 0.055) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_6'
        elif (0.14 < current_profit <= 0.16) and (max_profit - current_profit > 0.06) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_7'
        elif (0.16 < current_profit <= 0.18) and (max_profit - current_profit > 0.065) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_8'
        elif (0.18 < current_profit <= 0.2) and (max_profit - current_profit > 0.07) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_8'
        elif (0.2 < current_profit <= 0.3) and (max_profit - current_profit > 0.075) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_9'
        elif (0.3 < current_profit <= 0.4) and (max_profit - current_profit > 0.08) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_10'
        elif (0.4 < current_profit <= 0.5) and (max_profit - current_profit > 0.085) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_11'
        elif (0.5 < current_profit <= 1.0) and (max_profit - current_profit > 0.09) and (last_candle['cmf'] < 0.0):
            return True, 'sell_long_t_12'

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

        # Long mode
        if all(c in ['31', '32', '33', '34', '35', '36'] for c in buy_tags):
            sell, signal_name = self.sell_long_mode(current_profit, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, buy_tag)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {buy_tag})"
            # Skip remaining sell logic for long mode
            return None

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
        sell, signal_name = self.sell_r(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
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

        # The pair is pumped, stoploss
        sell, signal_name = self.sell_pump_stoploss(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
        if sell and (signal_name is not None):
            return f"{signal_name} ( {buy_tag})"

        # Pivot points based sells
        sell, signal_name = self.sell_pivot(current_profit, max_profit, max_loss, last_candle, previous_candle_1, trade, current_time)
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
        informative_pairs.extend([(pair, self.info_timeframe_15m) for pair in pairs])

        if self.config['stake_currency'] in ['USDT','BUSD','USDC','DAI','TUSD','PAX','USD','EUR','GBP']:
            btc_info_pair = f"BTC/{self.config['stake_currency']}"
        else:
            btc_info_pair = "BTC/USDT"

        informative_pairs.append((btc_info_pair, self.timeframe))
        informative_pairs.append((btc_info_pair, self.info_timeframe_1d))
        informative_pairs.append((btc_info_pair, self.info_timeframe_1h))
        informative_pairs.append((btc_info_pair, self.info_timeframe_15m))
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

        # S/R
        res_series = informative_1d['high'].rolling(window = 5, center=True).apply(lambda row: self.is_resistance(row), raw=True).shift(2)
        sup_series = informative_1d['low'].rolling(window = 5, center=True).apply(lambda row: self.is_support(row), raw=True).shift(2)
        informative_1d['res_level'] = Series(np.where(res_series, np.where(informative_1d['close'] > informative_1d['open'], informative_1d['close'], informative_1d['open']), float('NaN'))).ffill()
        informative_1d['res_hlevel'] = Series(np.where(res_series, informative_1d['high'], float('NaN'))).ffill()
        informative_1d['sup_level'] = Series(np.where(sup_series, np.where(informative_1d['close'] < informative_1d['open'], informative_1d['close'], informative_1d['open']), float('NaN'))).ffill()

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] informative_1d_indicators took: {tok - tik:0.4f} seconds.")

        return informative_1d

    def informative_1h_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        assert self.dp, "DataProvider is required for multiple timeframes."
        # Get the informative pair
        informative_1h = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=self.info_timeframe_1h)
        
        # Heikin Ashi
        inf_heikinashi = qtpylib.heikinashi(informative_1h)
        informative_1h['ha_close'] = inf_heikinashi['close']
        informative_1h['rocr'] = ta.ROCR(informative_1h['ha_close'], timeperiod=168)

        # RSI
        informative_1h['rsi_14'] = ta.RSI(informative_1h, timeperiod=14)
        
        informative_1h['rmi_length_17'] = RMI(dataframe, length=17, mom=4)
        informative_1h['cci_length_25'] = ta.CCI(dataframe, 25)

        # EMAs
        informative_1h['ema_12'] = ta.EMA(informative_1h, timeperiod=12)
        informative_1h['ema_20'] = ta.EMA(informative_1h, timeperiod=20)
        informative_1h['ema_25'] = ta.EMA(informative_1h, timeperiod=25)
        informative_1h['ema_35'] = ta.EMA(informative_1h, timeperiod=35)
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

        informative_1h['bb20_width'] = ((informative_1h['bb20_2_upp'] - informative_1h['bb20_2_low']) / informative_1h['bb20_2_mid'])

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

        # ROC
        informative_1h['roc_9'] = ta.ROC(informative_1h, timeperiod=9)

        # T3 Average
        informative_1h['t3_avg'] = t3_average(informative_1h)

        # S/R
        res_series = informative_1h['high'].rolling(window = 5, center=True).apply(lambda row: self.is_resistance(row), raw=True).shift(2)
        sup_series = informative_1h['low'].rolling(window = 5, center=True).apply(lambda row: self.is_support(row), raw=True).shift(2)
        informative_1h['res_level'] = Series(np.where(res_series, np.where(informative_1h['close'] > informative_1h['open'], informative_1h['close'], informative_1h['open']), float('NaN'))).ffill()
        informative_1h['res_hlevel'] = Series(np.where(res_series, informative_1h['high'], float('NaN'))).ffill()
        informative_1h['sup_level'] = Series(np.where(sup_series, np.where(informative_1h['close'] < informative_1h['open'], informative_1h['close'], informative_1h['open']), float('NaN'))).ffill()

        # Pump protections
        informative_1h['hl_pct_change_48'] = self.range_percent_change(informative_1h, 'HL', 48)
        informative_1h['hl_pct_change_36'] = self.range_percent_change(informative_1h, 'HL', 36)
        informative_1h['hl_pct_change_24'] = self.range_percent_change(informative_1h, 'HL', 24)
        informative_1h['hl_pct_change_12'] = self.range_percent_change(informative_1h, 'HL', 12)
        informative_1h['hl_pct_change_6'] = self.range_percent_change(informative_1h, 'HL', 6)

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] informative_1h_indicators took: {tok - tik:0.4f} seconds.")

        return informative_1h

    def informative_15m_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()
        assert self.dp, "DataProvider is required for multiple timeframes."
        # Get the informative pair
        informative_15m = self.dp.get_pair_dataframe(pair=metadata['pair'], timeframe=self.info_timeframe_15m)

        # RSI
        informative_15m['rsi_14'] = ta.RSI(informative_15m, timeperiod=14)

        # EMAs
        informative_15m['ema_12'] = ta.EMA(informative_15m, timeperiod=12)
        informative_15m['ema_16'] = ta.EMA(informative_15m, timeperiod=16)
        informative_15m['ema_20'] = ta.EMA(informative_15m, timeperiod=20)
        informative_15m['ema_26'] = ta.EMA(informative_15m, timeperiod=25)
        informative_15m['ema_50'] = ta.EMA(informative_15m, timeperiod=50)
        informative_15m['ema_100'] = ta.EMA(informative_15m, timeperiod=100)
        informative_15m['ema_200'] = ta.EMA(informative_15m, timeperiod=200)

        # SMA
        informative_15m['sma_15'] = ta.SMA(informative_15m, timeperiod=15)
        informative_15m['sma_30'] = ta.SMA(informative_15m, timeperiod=30)
        informative_15m['sma_200'] = ta.SMA(informative_15m, timeperiod=200)

        informative_15m['sma_200_dec_20'] = informative_15m['sma_200'] < informative_15m['sma_200'].shift(20)

        # BB
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(informative_15m), window=20, stds=2)
        informative_15m['bb20_2_low'] = bollinger['lower']
        informative_15m['bb20_2_mid'] = bollinger['mid']
        informative_15m['bb20_2_upp'] = bollinger['upper']

        # BB 40 - STD2
        bb_40_std2 = qtpylib.bollinger_bands(informative_15m['close'], window=40, stds=2)
        informative_15m['bb40_2_low'] = bb_40_std2['lower']
        informative_15m['bb40_2_mid'] = bb_40_std2['mid']
        informative_15m['bb40_2_delta'] = (bb_40_std2['mid'] - informative_15m['bb40_2_low']).abs()
        informative_15m['closedelta'] = (informative_15m['close'] - informative_15m['close'].shift()).abs()
        informative_15m['tail'] = (informative_15m['close'] - informative_15m['bb40_2_low']).abs()

        # CMF
        informative_15m['cmf'] = chaikin_money_flow(informative_15m, 20)

        # CTI
        informative_15m['cti'] = pta.cti(informative_15m["close"], length=20)

        # Williams %R
        informative_15m['r_14'] = williams_r(informative_15m, period=14)
        informative_15m['r_64'] = williams_r(informative_15m, period=64)
        informative_15m['r_96'] = williams_r(informative_15m, period=96)

        # EWO
        informative_15m['ewo'] = ewo(informative_15m, 50, 200)

        # CCI
        informative_15m['cci'] = ta.CCI(informative_15m, source='hlc3', timeperiod=20)

        # CRSI (3, 2, 100)
        crsi_closechange = informative_15m['close'] / informative_15m['close'].shift(1)
        crsi_updown = np.where(crsi_closechange.gt(1), 1.0, np.where(crsi_closechange.lt(1), -1.0, 0.0))
        informative_15m['crsi'] =  (ta.RSI(informative_15m['close'], timeperiod=3) + ta.RSI(crsi_updown, timeperiod=2) + ta.ROC(informative_15m['close'], 100)) / 3

        tok = time.perf_counter()
        log.debug(f"[{metadata['pair']}] informative_1h_indicators took: {tok - tik:0.4f} seconds.")

        return informative_15m

    def normal_tf_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        tik = time.perf_counter()

        # RSI
        dataframe['rsi_4'] = ta.RSI(dataframe, timeperiod=4)
        dataframe['rsi_14'] = ta.RSI(dataframe, timeperiod=14)
        
        dataframe['rmi_length_17'] = RMI(dataframe, length=17, mom=4)
        dataframe['cci_length_25'] = ta.CCI(dataframe, 25)
        
        # Heiken Ashi
        heikinashi = qtpylib.heikinashi(dataframe)
        dataframe['ha_open'] = heikinashi['open']
        dataframe['ha_close'] = heikinashi['close']
        dataframe['ha_high'] = heikinashi['high']
        dataframe['ha_low'] = heikinashi['low']

        dataframe['ha_closedelta'] = (dataframe['ha_close'] - dataframe['ha_close'].shift()).abs()
        dataframe['ha_tail'] = (dataframe['ha_close'] - dataframe['ha_low']).abs()
        
        dataframe['rocr'] = ta.ROCR(dataframe['ha_close'], timeperiod=28)
        
        # EMAs
        dataframe['ema_8'] = ta.EMA(dataframe, timeperiod=8)
        dataframe['ema_12'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['ema_13'] = ta.EMA(dataframe, timeperiod=13)
        dataframe['ema_16'] = ta.EMA(dataframe, timeperiod=16)
        dataframe['ema_20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema_25'] = ta.EMA(dataframe, timeperiod=25)
        dataframe['ema_26'] = ta.EMA(dataframe, timeperiod=26)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_100'] = ta.EMA(dataframe, timeperiod=100)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)

        # SMA
        dataframe['sma_15'] = ta.SMA(dataframe, timeperiod=15)
        dataframe['sma_28'] = ta.SMA(dataframe, timeperiod=28)
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

        # BB 20 - STD3
        bb_20_std3 = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=3)
        dataframe['bb20_3_low'] = bb_20_std3['lower']
        dataframe['bb20_3_mid'] = bb_20_std3['mid']
        dataframe['bb20_3_upp'] = bb_20_std3['upper']

        dataframe['bb20_width'] = ((dataframe['bb20_2_upp'] - dataframe['bb20_2_low']) / dataframe['bb20_2_mid'])
        dataframe['bb20_delta'] = ((dataframe['bb20_2_low'] - dataframe['bb20_3_low']) / dataframe['bb20_2_low'])
        
        # ClucHA
        dataframe['bb_delta_cluc'] = (dataframe['bb40_2_mid'] - dataframe['bb40_2_low']).abs()
        dataframe['ha_closedelta'] = (dataframe['ha_close'] - dataframe['ha_close'].shift()).abs()
        dataframe['tail'] = (dataframe['ha_close'] - dataframe['ha_low']).abs()
        dataframe['ema_slow'] = ta.EMA(dataframe['ha_close'], timeperiod=50)
        dataframe['rocr'] = ta.ROCR(dataframe['ha_close'], timeperiod=28)

        # CMF
        dataframe['cmf'] = chaikin_money_flow(dataframe, 20)

        # Williams %R
        dataframe['r_14'] = williams_r(dataframe, period=14)
        dataframe['r_24'] = williams_r(dataframe, period=24)
        dataframe['r_32'] = williams_r(dataframe, period=32)
        dataframe['r_64'] = williams_r(dataframe, period=64)
        dataframe['r_96'] = williams_r(dataframe, period=96)
        dataframe['r_480'] = williams_r(dataframe, period=480)

        # CTI
        dataframe['cti'] = pta.cti(dataframe["close"], length=20)

        # CRSI (3, 2, 100)
        crsi_closechange = dataframe['close'] / dataframe['close'].shift(1)
        crsi_updown = np.where(crsi_closechange.gt(1), 1.0, np.where(crsi_closechange.lt(1), -1.0, 0.0))
        dataframe['crsi'] =  (ta.RSI(dataframe['close'], timeperiod=3) + ta.RSI(crsi_updown, timeperiod=2) + ta.ROC(dataframe['close'], 100)) / 3

        # EMA of VWMA Oscillator
        dataframe['ema_vwma_osc_32'] = ema_vwma_osc(dataframe, 32)
        dataframe['ema_vwma_osc_64'] = ema_vwma_osc(dataframe, 64)
        dataframe['ema_vwma_osc_96'] = ema_vwma_osc(dataframe, 96)

        # EWO
        dataframe['ewo'] = ewo(dataframe, 50, 200)

        # CCI
        dataframe['cci'] = ta.CCI(dataframe, source='hlc3', timeperiod=20)
        dataframe['cci_25'] = ta.CCI(dataframe, source='hlc3', timeperiod=25)

        # MFI
        dataframe['mfi'] = ta.MFI(dataframe)

        # RMI
        dataframe['rmi_17'] = RMI(dataframe, length=17, mom=4)

        # Stochastic fast
        stoch_fast = ta.STOCHF(dataframe, 5, 3, 0, 3, 0)
        dataframe['fastd'] = stoch_fast['fastd']
        dataframe['fastk'] = stoch_fast['fastk']

        # ADX
        dataframe['adx'] = ta.ADX(dataframe)

        # STOCHRSI
        stoch = ta.STOCHRSI(dataframe, 15, 20, 2, 2)
        dataframe['srsi_fk'] = stoch['fastk']
        dataframe['srsi_fd'] = stoch['fastd']

        # Close delta
        dataframe['close_delta'] = (dataframe['close'] - dataframe['close'].shift(1)).abs()

        # T3 Average
        dataframe['t3_avg'] = t3_average(dataframe)

        # Heiken Ashi
        heikinashi = qtpylib.heikinashi(dataframe)
        dataframe['ha_open'] = heikinashi['open']
        dataframe['ha_close'] = heikinashi['close']
        dataframe['ha_high'] = heikinashi['high']
        dataframe['ha_low'] = heikinashi['low']

        dataframe['ha_closedelta'] = (dataframe['ha_close'] - dataframe['ha_close'].shift()).abs()
        dataframe['ha_tail'] = (dataframe['ha_close'] - dataframe['ha_low']).abs()

        # True range
        dataframe['trange'] = ta.TRANGE(dataframe)

        # KC
        dataframe['range_ma_28'] = ta.SMA(dataframe['trange'], 28)
        dataframe['kc_upperband_28_1'] = dataframe['sma_28'] + dataframe['range_ma_28']
        dataframe['kc_lowerband_28_1'] = dataframe['sma_28'] - dataframe['range_ma_28']

        # Linreg
        dataframe['hh_20'] = ta.MAX(dataframe['high'], 20)
        dataframe['ll_20'] = ta.MIN(dataframe['low'], 20)
        dataframe['avg_hh_ll_20'] = (dataframe['hh_20'] + dataframe['ll_20']) / 2.0
        dataframe['avg_close_20'] = ta.SMA(dataframe['close'], 20)
        dataframe['avg_val_20'] = (dataframe['avg_hh_ll_20'] + dataframe['avg_close_20']) / 2.0
        dataframe['linreg_val_20'] = ta.LINEARREG(dataframe['close'] - dataframe['avg_val_20'], 20, 0)

        # ATR
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        dataframe['atr_high_thresh_1'] = (dataframe['high'] - (dataframe['atr'] * 5.4))
        dataframe['atr_high_thresh_2'] = (dataframe['high'] - (dataframe['atr'] * 5.2))
        dataframe['atr_high_thresh_3'] = (dataframe['high'] - (dataframe['atr'] * 5.0))
        dataframe['atr_high_thresh_4'] = (dataframe['high'] - (dataframe['atr'] * 2.6))

        # For sell checks
        dataframe['crossed_below_ema_12_26'] = qtpylib.crossed_below(dataframe['ema_12'], dataframe['ema_26'])

        # Volume
        dataframe['vma_10'] = ta.SMA(dataframe['volume'], timeperiod=10)
        dataframe['vma_20'] = ta.SMA(dataframe['volume'], timeperiod=20)
        dataframe['vol_osc'] = (dataframe['vma_10'] - dataframe['vma_20']) / dataframe['vma_20'] * 100
        dataframe['volume_mean_4'] = dataframe['volume'].rolling(12).mean().shift(1)
        dataframe['volume_mean_12'] = dataframe['volume'].rolling(12).mean().shift(1)
        dataframe['volume_mean_24'] = dataframe['volume'].rolling(24).mean().shift(1)

        # Dip protection
        dataframe['tpct_change_0']   = self.top_percent_change(dataframe,0)
        dataframe['tpct_change_2']   = self.top_percent_change(dataframe,2)
        dataframe['tpct_change_12']  = self.top_percent_change(dataframe,12)
        dataframe['tpct_change_144'] = self.top_percent_change(dataframe,144)

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

        if self.info_timeframe_15m != 'none':
            informative_15m = self.informative_15m_indicators(dataframe, metadata)
            dataframe = merge_informative_pair(dataframe, informative_15m, self.timeframe, self.info_timeframe_15m, ffill=True)
            drop_columns = [f"{s}_{self.info_timeframe_15m}" for s in ['date']]
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
                    item_buy_logic.append(((dataframe['close'] - dataframe['open'].rolling(12).min()) / dataframe['open'].rolling(12).min()) > 0.027)
                    item_buy_logic.append(dataframe['rsi_14'] < 35.0)
                    item_buy_logic.append(dataframe['r_32'] < -80.0)
                    item_buy_logic.append(dataframe['mfi'] < 31.0)
                    item_buy_logic.append(dataframe['rsi_14_1h'] > 30.0)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 84.0)
                    item_buy_logic.append(dataframe['r_480_1h'] > -99.0)

                # Condition #2 - Semi swing. Local dip.
                elif index == 2:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['rsi_14'] < (dataframe['rsi_14_1h'] - 46.0))
                    item_buy_logic.append(dataframe['mfi'] < 46.0)
                    item_buy_logic.append(dataframe['cti'] < -0.8)
                    item_buy_logic.append(dataframe['r_14'] < -98.0)
                    item_buy_logic.append(dataframe['r_480'] > -95.0)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.83)
                    item_buy_logic.append(dataframe['volume_mean_12'] > (dataframe['volume_mean_24'] * 1.0))

                # Condition #3 - Semi swing. Local dip.
                elif index == 3:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_1h'] * 0.9))

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_low'].shift().gt(0))
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * 0.045))
                    item_buy_logic.append(dataframe['closedelta'].gt(dataframe['close'] * 0.022))
                    item_buy_logic.append(dataframe['tail'].lt(dataframe['bb40_2_delta'] * 0.24))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))
                    item_buy_logic.append(dataframe['cti_1h'] < -0.6)
                    item_buy_logic.append(dataframe['crsi_1h'] > 10.0)

                # Condition #4 - Semi swing. Local dip.
                elif index == 4:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_1h'] * 0.93))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.02))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.992))
                    item_buy_logic.append(dataframe['mfi'] > 18.0)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.82)
                    item_buy_logic.append(dataframe['crsi_1h'] > 10.0)

                # Condition #5 - Semi swing. Local dip. Uptrend.
                elif index == 5:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_200_1h'].shift(12) > dataframe['ema_200_1h'].shift(24))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * 0.932)
                    item_buy_logic.append(dataframe['ewo'] > 3.4)
                    item_buy_logic.append(dataframe['cti'] < -0.93)
                    item_buy_logic.append(dataframe['r_14'] < -97.0)

                # Condition #6 - Semi swing. Local dip.
                elif index == 6:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_1h'] * 0.93))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_15'] * 0.937)
                    item_buy_logic.append(dataframe['crsi'] < 30.0)
                    item_buy_logic.append(dataframe['rsi_14'] < dataframe['rsi_14'].shift(1))
                    item_buy_logic.append(dataframe['rsi_14'] < 28.0)
                    item_buy_logic.append(dataframe['cti'] < -0.78)
                    item_buy_logic.append(dataframe['cci'] < -200.0)
                    item_buy_logic.append(dataframe['r_480_1h'] < -12.0)

                # Condition #7 - Semi swing. Local dip.
                elif index == 7:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_50_1h'] > dataframe['ema_100_1h'])

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * 0.94)
                    item_buy_logic.append(dataframe['close'] < dataframe['bb20_2_low'] * 0.995)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['r_14'] < -95.0)

                # Condition #8 - Semi swing. Local deeper dip. Uptrend.
                elif index == 8:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * 0.927)
                    item_buy_logic.append(dataframe['ewo'] > 3.2)
                    item_buy_logic.append(dataframe['rsi_14'] < 32.0)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['r_14'] < -97.0)

                # Condition #9 - Semi swing. Local dip. Downtrend.
                elif index == 9:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_50_1h'] > dataframe['ema_100_1h'])

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * 0.99)
                    item_buy_logic.append(dataframe['cti'] < -0.92)
                    item_buy_logic.append(dataframe['ewo'] < -4.8)
                    item_buy_logic.append(dataframe['cti_1h'] < -0.88)
                    item_buy_logic.append(dataframe['crsi_1h'] > 18.0)

                # Condition #10 - Semi swing. Local dip.
                elif index == 10:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.017))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.984))
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * 0.965)
                    item_buy_logic.append(dataframe['cti'] < -0.87)

                # Condition #11 - Semi swing. Local dip.
                elif index == 11:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.027))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * 0.938)
                    item_buy_logic.append(dataframe['rsi_14'] < 25.0)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * 5.0))

                # Condition #12 - Semi swing. Local deeper dip. Uptrend.
                elif index == 12:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * 0.932)
                    item_buy_logic.append(dataframe['ewo'] > 0.1)
                    item_buy_logic.append(dataframe['rsi_14'] < 40.0)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['r_480_1h'] < -20.0)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * 2.8))

                # Condition #13 - Semi swing. Downtrend. Local dip.
                elif index == 13:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * 0.999)
                    item_buy_logic.append(dataframe['ewo'] < -5.4)
                    item_buy_logic.append(dataframe['cti'] < -0.97)
                    item_buy_logic.append(dataframe['crsi_1h'] > 12.0)

                # Condition #14 - Semi swing. Strong uptrend. Local dip.
                elif index == 14:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_100_1h'] > dataframe['ema_100_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(36))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_30'] * 0.98)
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.984))
                    item_buy_logic.append(dataframe['ewo'] > 7.8)
                    item_buy_logic.append(dataframe['rsi_14'] < 32.0)
                    item_buy_logic.append(dataframe['cti'] < -0.7)
                    item_buy_logic.append(dataframe['cti_1h'] > -0.5)

                # Condition #15 - Semi swing. Uptrend. Local dip.
                elif index == 15:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.99))
                    item_buy_logic.append(dataframe['ewo'] > 2.2)
                    item_buy_logic.append(dataframe['rsi_14'] < 28.5)
                    item_buy_logic.append(dataframe['cti'] < -0.8)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 80.0)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.4)

                # Condition #16 - Semi swing. Cross above.
                elif index == 16:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_12_1h'].shift(12) < dataframe['ema_35_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_12_1h'] > dataframe['ema_35_1h'])
                    item_buy_logic.append(dataframe['cmf_1h'].shift(12) < 0.0)
                    item_buy_logic.append(dataframe['cmf_1h'] > 0.0)
                    item_buy_logic.append(dataframe['rsi_14'] < 50.0)
                    item_buy_logic.append(dataframe['cti'] < 0.5)
                    item_buy_logic.append(dataframe['rsi_14_1h'] > 67.0)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.25)

                # Condition #17 - Semi swing. Deep buy.
                elif index == 17:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['r_480'] < -90.0)
                    item_buy_logic.append(dataframe['r_14'] < -99.0)
                    item_buy_logic.append(dataframe['r_480_1h'] < -93.0)
                    item_buy_logic.append(dataframe['rsi_14_1h'] + dataframe['rsi_14'] < 33.0)

                # Condition #18 - Semi swing. Local dip. BTC not negative.
                elif index == 18:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_200_1h'].shift(12) > dataframe['ema_200_1h'].shift(24))
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.018))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.982))

                # Condition #19 - Semi swing. Uptrend. Local dip.  BTC not downtrend.
                elif index == 19:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_200_1h'].shift(12) > dataframe['ema_200_1h'].shift(24))
                    item_buy_logic.append(dataframe['bb40_2_low'].shift().gt(0))
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * 0.045))
                    item_buy_logic.append(dataframe['closedelta'].gt(dataframe['close'] * 0.02))
                    item_buy_logic.append(dataframe['tail'].lt(dataframe['bb40_2_delta'] * 0.28))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['cti_1h'] > -0.75)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.25)

                # Condition #20 - Semi swing. Uptrend. Local dip.
                elif index == 20:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'].shift(1) < (dataframe['sma_15'].shift(1) * 0.942))
                    item_buy_logic.append(dataframe['close'] > (dataframe['open'].shift(1)))
                    item_buy_logic.append(dataframe['ewo'] > 4.8)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['r_14'].shift(1) < -97.0)

                # Condition #21 - Semi swing. Deep local dip. Mild uptrend.
                elif index == 21:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * 0.941)
                    item_buy_logic.append(dataframe['ewo'] > 2.0)
                    item_buy_logic.append(dataframe['cti'] < -0.84)
                    item_buy_logic.append(dataframe['r_14'] < -97.0)
                    item_buy_logic.append(dataframe['r_96'] < -87.0)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.8)

                # Condition #22 - Swing. Uptrend. Bounce from daily support level
                elif index == 22:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['close_1h'] > dataframe['sup_level_1d'])
                    item_buy_logic.append(dataframe['close_1h'] < dataframe['sup_level_1d'] * 1.05)
                    item_buy_logic.append(dataframe['low_1h'] < dataframe['sup_level_1d'] * 0.99)
                    item_buy_logic.append(dataframe['close_1h'] < dataframe['res_level_1h'])
                    item_buy_logic.append(dataframe['res_level_1d'] > dataframe['sup_level_1d'])
                    item_buy_logic.append(dataframe['rsi_14'] < 39.8)
                    item_buy_logic.append(dataframe['rsi_14_1h'] > 48.0)

                    # Confirm uptrend - Heikin-Ashi
                    item_buy_logic.append(dataframe['open_sha_1d'] < dataframe['close_sha_1d'])
                    item_buy_logic.append(dataframe['open_sha_1d'].shift(288) < dataframe['close_sha_1d'].shift(288))
                    item_buy_logic.append(dataframe['pivot_1d'] > dataframe['pivot_1d'].shift(288) * 0.95)

                # Condition #23 - Semi swing. Downtrend. Local dip.
                elif index == 23:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['ewo'].shift(1) < -6.4)
                    item_buy_logic.append(dataframe['cti'].shift(1).rolling(5).max() < -0.9)
                    item_buy_logic.append(dataframe['r_14'].shift(1) < -97.0)
                    item_buy_logic.append(dataframe['close'] > (dataframe['open'].shift(1)))
                    item_buy_logic.append(dataframe['crsi_1h'] > 2.0)

                # Condition #24 - Semi swing. Uptrend. 1h uptrend. Local dip.
                elif index == 24:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ewo'] > 5.4)
                    item_buy_logic.append(dataframe['r_14'] < -97.0)
                    item_buy_logic.append(dataframe['r_96'] < -90.0)
                    item_buy_logic.append(dataframe['ewo_1h'] > 2.8)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.92)

                # Condition #25 - Semi swing. CMF 1h cross.
                elif index == 25:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_12_1h'].shift(12) < dataframe['ema_35_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_12_1h'] > dataframe['ema_35_1h'])
                    item_buy_logic.append(dataframe['cmf_1h'].shift(12) < 0.0)
                    item_buy_logic.append(dataframe['cmf_1h'] > 0.0)
                    item_buy_logic.append(dataframe['rsi_14'] < 33.0)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.0)

                # Condition #26 - Semi swing. Local deep dip.
                elif index == 26:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_20_1h'] > dataframe['ema_25_1h'])

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_15'] * 0.93)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['r_14'] < -94.0)

                # Condition #27 - Semi swing. Local deep. Uptrend.
                elif index == 27:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * 0.934)
                    item_buy_logic.append(dataframe['ewo'] > 6.4)
                    item_buy_logic.append(dataframe['rsi_14'] < 32.0)
                    item_buy_logic.append(dataframe['cti'] < -0.8)
                    item_buy_logic.append(dataframe['r_14'] < -96.0)
                    item_buy_logic.append(dataframe['r_480_1h'] < -5.0)

                # Condition #28 - Semi swing. Downtrend. Local deep.
                elif index == 28:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['sma_75'] * 0.96)
                    item_buy_logic.append(dataframe['ewo'] < -8.0)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['r_14'] < -97.0)
                    item_buy_logic.append(dataframe['crsi_1h'] > 14.0)

                # Condition #29 - Semi swing. Downtrend. Local deep.
                elif index == 29:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_16'] * 0.982))
                    item_buy_logic.append(dataframe['ewo'] < -16.0)
                    item_buy_logic.append(dataframe['cti'] < -0.75)

                # Condition #30 - Semi swing. Local dip. BTC not downtrend.
                elif index == 30:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.018))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.98))

                # Condition #31 - Long mode. Local dip.
                elif index == 31:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * 0.045))
                    item_buy_logic.append(dataframe['closedelta'].gt(dataframe['close'] * 0.028))
                    item_buy_logic.append(dataframe['tail'].lt(dataframe['bb40_2_delta'] * 0.25))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['crsi_1h'] > 10.0)

                # Condition #32 - Long mode. Local dip.
                elif index == 32:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.046))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['r_480_1h'] < -5.0)

                # Condition #33 - Long mode. Local dip. Uptrend.
                elif index == 33:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_1h'] * 0.95))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_16'] * 0.934))
                    item_buy_logic.append(dataframe['ewo'] > 2.5)
                    item_buy_logic.append(dataframe['rsi_14'] < 46.0)
                    item_buy_logic.append(dataframe['r_14'] < -97.0)
                    item_buy_logic.append(dataframe['ewo_1h'] > 0.1)

                # Condition #34 - Long mode. Local dip.
                elif index == 34:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_50'])
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.972))
                    item_buy_logic.append(dataframe['cti'] < -0.8)
                    item_buy_logic.append(dataframe['rsi_14'] < 18.0)

                # Condition #35 - Long mode. Local deep dip.
                elif index == 35:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_25'] * 0.85)
                    item_buy_logic.append(dataframe['close'] > dataframe['open'])
                    item_buy_logic.append(dataframe['rsi_14'] < 46.0)
                    item_buy_logic.append(dataframe['mfi'] < 36.0)
                    item_buy_logic.append(dataframe['cti_1h'] > -0.85)

                # Condition #36 - Long mode. Uptrend. Local dip.
                elif index == 36:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_200'] > (dataframe['ema_200'].shift(36) * 1.035))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * 0.97)
                    item_buy_logic.append(dataframe['rsi_14'] < 34.0)
                    item_buy_logic.append(dataframe['r_14'] < -90.0)
                    item_buy_logic.append(dataframe['r_64'] < -80.0)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['volume_mean_12'] > (dataframe['volume_mean_24'] * 0.9))
                    item_buy_logic.append(dataframe['r_480_1h'] < -30.0)

                # Condition #37 - Semi swing. Uptrend. Local dip.
                elif index == 37:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_200'] > (dataframe['ema_200'].shift(12) * 1.01))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.99))
                    item_buy_logic.append(dataframe['r_14'] < -94.0)
                    item_buy_logic.append(dataframe['r_64'] < -75.0)
                    item_buy_logic.append(dataframe['r_480_1h'] < -20.0)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 80.0)

                # Condition #38 - Semi swing. Uptrend. Local dip.
                elif index == 38:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_200'] > (dataframe['ema_200'].shift(12) * 1.01))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.024))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['r_64'] < -66.0)
                    item_buy_logic.append(dataframe['r_96'] < -50.0)
                    item_buy_logic.append(dataframe['r_480_1h'] < -1.0)

                # Condition #39 - Semi swing. Uptrend. Local dip.
                elif index == 39:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_200'] > (dataframe['ema_200'].shift(12) * 1.0114))

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * 0.05))
                    item_buy_logic.append(dataframe['closedelta'].gt(dataframe['close'] * 0.01))
                    item_buy_logic.append(dataframe['tail'].lt(dataframe['bb40_2_delta'] * 0.5))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))
                    item_buy_logic.append(dataframe['r_480_1h'] < -5.0)
                    item_buy_logic.append(dataframe['volume_mean_12'] > (dataframe['volume_mean_24'] * 1.0))

                # Condition #40 - Semi swing. Uptrend. Local dip.
                elif index == 40:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_200'] > (dataframe['ema_200'].shift(12) * 1.01))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_20'] * 0.97)
                    item_buy_logic.append(dataframe['rsi_14'] < 32.0)
                    item_buy_logic.append(dataframe['r_14'] < -90.0)
                    item_buy_logic.append(dataframe['r_64'] < -80.0)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 80.0)

                # Condition #41 - 15m. Semi swing. Local dip. BTC not downtrend.
                elif index == 41:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_12_15m'] > dataframe['ema_200_1h'])

                    # Logic
                    item_buy_logic.append(dataframe['ema_26_15m'] > dataframe['ema_12_15m'])
                    item_buy_logic.append((dataframe['ema_26_15m'] - dataframe['ema_12_15m']) > (dataframe['open_15m'] * 0.03))
                    item_buy_logic.append((dataframe['ema_26_15m'].shift(3) - dataframe['ema_12_15m'].shift(3)) > (dataframe['open_15m'] / 100))
                    item_buy_logic.append(dataframe['close_15m'] < (dataframe['bb20_2_low_15m'] * 0.998))
                    item_buy_logic.append(dataframe['cti'] < -0.75)

                # Condition #42 - 15m. Semi swing. Local dip. 15m uptrend.
                elif index == 42:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_1h'] * 0.92))

                    # Logic
                    item_buy_logic.append(dataframe['ewo_15m'] > 7.8)
                    item_buy_logic.append(dataframe['rsi_14_15m'] < 36.0)
                    item_buy_logic.append(dataframe['cti_15m'] < -0.9)
                    item_buy_logic.append(dataframe['r_14_15m'] < -90.0)
                    item_buy_logic.append(dataframe['r_14'] < -96.0)
                    item_buy_logic.append(dataframe['mfi'] > 24.0)
                    item_buy_logic.append(dataframe['r_480_1h'] < -5.0)
                    item_buy_logic.append(dataframe['crsi_1h'] > 14.0)

                # Condition #43 - 15m. Semi swing. Local dip. 1h uptrend.
                elif index == 43:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_low_15m'].shift().gt(0))
                    item_buy_logic.append(dataframe['bb40_2_delta_15m'].gt(dataframe['close_15m'] * 0.045))
                    item_buy_logic.append(dataframe['closedelta_15m'].gt(dataframe['close_15m'] * 0.034))
                    item_buy_logic.append(dataframe['tail_15m'].lt(dataframe['bb40_2_delta_15m'] * 0.18))
                    item_buy_logic.append(dataframe['close_15m'].lt(dataframe['bb40_2_low_15m'].shift()))
                    item_buy_logic.append(dataframe['close_15m'].le(dataframe['close_15m'].shift()))
                    item_buy_logic.append(dataframe['rsi_14_15m'] < 30.0)
                    item_buy_logic.append(dataframe['cti_15m'] < -0.85)
                    item_buy_logic.append(dataframe['r_64_15m'] < -70.0)

                # Condition #44 - 15m. Semi swing. Local deeper dip. 15m uptrend.
                elif index == 44:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_200_15m'] > (dataframe['ema_200_15m'].shift(36) * 1.01))
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_1h'] * 0.95))

                    # Logic
                    item_buy_logic.append(dataframe['close_15m'] < dataframe['ema_26_15m'] * 0.99)
                    item_buy_logic.append(dataframe['rsi_14_15m'] < 26.0)
                    item_buy_logic.append(dataframe['r_14_15m'] < -90.0)
                    item_buy_logic.append(dataframe['volume_mean_12'] > (dataframe['volume_mean_24'] * 1.2))

                # Condition #45 - 15m. Semi swing. Local deeper dip. 15m uptrend.
                elif index == 45:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_50_15m'] > dataframe['ema_200_1h'])

                    # Logic
                    item_buy_logic.append(dataframe['close_15m'] < dataframe['ema_20_15m'] * 0.934)
                    item_buy_logic.append(dataframe['ewo_15m'] > 3.6)
                    item_buy_logic.append(dataframe['cci_15m'] < -190.0)
                    item_buy_logic.append(dataframe['r_14_15m'] < -97.0)
                    item_buy_logic.append((dataframe['rsi_14_1h'] + dataframe['rsi_14_15m']) < 70.0)

                # Condition #46 - 15m. Semi swing. 1h uptrend.
                elif index == 46:
                    # Non-Standard protections (add below)
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_200_1h'].shift(12) > dataframe['ema_200_1h'].shift(24))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26_15m'] > dataframe['ema_12_15m'])
                    item_buy_logic.append((dataframe['ema_26_15m'] - dataframe['ema_12_15m']) > (dataframe['open_15m'] * 0.027))
                    item_buy_logic.append((dataframe['ema_26_15m'].shift(3) - dataframe['ema_12_15m'].shift(3)) > (dataframe['open_15m'] / 100))
                    item_buy_logic.append(dataframe['close_15m'] < (dataframe['bb20_2_low_15m'] * 0.982))
                    item_buy_logic.append(dataframe['r_14'] < -75.0)
                    item_buy_logic.append(dataframe['crsi_1h'] > 14.0)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * 5.0))

                # Condition #47 - 15m. Semi swing. Local dip. 1h minor dip.
                elif index == 47:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['rsi_14_15m'] < dataframe['rsi_14_15m'].shift(3))
                    item_buy_logic.append(dataframe['ema_20_1h'] > dataframe['ema_25_1h'])
                    item_buy_logic.append(dataframe['close_15m'] < (dataframe['sma_15_15m'] * 0.95))
                    item_buy_logic.append(
                        ((dataframe['open_15m'] < dataframe['ema_20_1h']) & (dataframe['low_15m'] < dataframe['ema_20_1h'])) |
                        ((dataframe['open_15m'] > dataframe['ema_20_1h']) & (dataframe['low_15m'] > dataframe['ema_20_1h'])))
                    item_buy_logic.append(dataframe['cti_15m'] < -0.9)
                    item_buy_logic.append(dataframe['r_14_15m'] < -90.0)
                    item_buy_logic.append(dataframe['r_14'] < -97.0)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.1)
                    item_buy_logic.append(dataframe['crsi_1h'] > 8.0)

                # Condition #48 - 15m. Semi swing. Local deep. 15m uptrend.
                elif index == 48:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close_15m'].shift(3) < (dataframe['sma_15_15m'].shift(3) * 0.95))
                    item_buy_logic.append(dataframe['close_15m'] > (dataframe['open_15m'].shift(3)))
                    item_buy_logic.append(dataframe['ewo_15m'] > 5.0)
                    item_buy_logic.append(dataframe['cti_15m'] < -0.75)
                    item_buy_logic.append(dataframe['r_14_15m'].shift(3) < -94.0)
                    item_buy_logic.append(dataframe['cti'] < -0.5)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.1)
                    item_buy_logic.append(dataframe['crsi_1h'] > 18.0)

                # Condition #49 - 15m. Semi swing. Local deeper dip.
                elif index == 49:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_26_15m'] > dataframe['ema_12_15m'])
                    item_buy_logic.append((dataframe['ema_26_15m'] - dataframe['ema_12_15m']) > (dataframe['open_15m'] * 0.032))
                    item_buy_logic.append((dataframe['ema_26_15m'].shift(3) - dataframe['ema_12_15m'].shift(3)) > (dataframe['open_15m'] / 100))
                    item_buy_logic.append(dataframe['close_15m'] < dataframe['ema_20_15m'] * 0.928)
                    item_buy_logic.append(dataframe['rsi_14_15m'] < 28.0)
                    item_buy_logic.append(dataframe['crsi_15m'] > 18.0)

                # Condition #50 - 15m. Semi swing. Deep local dip. Mild 15m uptrend.
                elif index == 50:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close_15m'] < dataframe['ema_20_15m'] * 0.932)
                    item_buy_logic.append(dataframe['ewo_15m'] > 1.8)
                    item_buy_logic.append(dataframe['cti_15m'] < -0.9)
                    item_buy_logic.append(dataframe['r_14_15m'] < -96.0)
                    item_buy_logic.append(dataframe['r_96_15m'] < -75.0)
                    item_buy_logic.append(dataframe['rsi_14'] < 32.0)
                    item_buy_logic.append(dataframe['r_14_15m'] < -97.0)

                # Condition #51 - 15m. Semi swing. Downtrend. Dip.
                elif index == 51:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['close_15m'] < (dataframe['ema_16_15m'] * 0.942))
                    item_buy_logic.append(dataframe['ewo_15m'] < -1.0)
                    item_buy_logic.append(dataframe['rsi_14_15m'] > 29.0)
                    item_buy_logic.append(dataframe['cti_15m'] < -0.84)
                    item_buy_logic.append(dataframe['r_14_15m'] < -94.0)
                    item_buy_logic.append(dataframe['rsi_14'] > 30.0)
                    item_buy_logic.append(dataframe['crsi_1h'] > 1.0)

                # Condition #52 - 15m Semi swing. Local dip. BTC not downtrend.
                elif index == 52:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['ema_26_15m'] > dataframe['ema_12_15m'])
                    item_buy_logic.append((dataframe['ema_26_15m'] - dataframe['ema_12_15m']) > (dataframe['open_15m'] * 0.03))
                    item_buy_logic.append((dataframe['ema_26_15m'].shift(3) - dataframe['ema_12_15m'].shift(3)) > (dataframe['open_15m'] / 100))
                    item_buy_logic.append(dataframe['close_15m'] < (dataframe['bb20_2_low_15m'] * 0.998))
                    item_buy_logic.append(dataframe['crsi_1h'] > 10.0)

                # Condition #53 - 15m. Semi swing. BTC not negative. Local dip.
                elif index == 53:
                    # Non-Standard protections (add below)
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(12))
                    item_buy_logic.append(dataframe['ema_200_1h'].shift(12) > dataframe['ema_200_1h'].shift(24))
                    item_buy_logic.append(dataframe['ema_200_1h'].shift(24) > dataframe['ema_200_1h'].shift(36))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26_15m'] > dataframe['ema_12_15m'])
                    item_buy_logic.append((dataframe['ema_26_15m'] - dataframe['ema_12_15m']) > (dataframe['open_15m'] * 0.02))
                    item_buy_logic.append((dataframe['ema_26_15m'].shift(3) - dataframe['ema_12_15m'].shift(3)) > (dataframe['open_15m'] / 100))
                    item_buy_logic.append(dataframe['close_15m'] < (dataframe['bb20_2_low_15m'] * 0.99))
                    item_buy_logic.append(dataframe['r_14'] < -75.0)
                    item_buy_logic.append(dataframe['cti_1h'] > -0.7)

                # Condition #54 - 15m Semi swing. Uptrend. Local dip.
                elif index == 54:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['ema_12_15m'] > dataframe['ema_200_15m'])

                    # Logic
                    item_buy_logic.append(dataframe['ewo_15m'] > 7.4)
                    item_buy_logic.append(dataframe['r_14_15m'] < -96.0)
                    item_buy_logic.append(dataframe['r_96_15m'] < -94.0)
                    item_buy_logic.append(dataframe['r_14'] < -96.0)
                    item_buy_logic.append(dataframe['crsi_1h'] > 12.0)

                # Condition #55 - 15m. Semi swing. Uptrend. Local dip.
                elif index == 55:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['ewo_15m'] > 7.0)
                    item_buy_logic.append(dataframe['close_15m'] > (dataframe['close_15m'].shift(3)))
                    item_buy_logic.append(dataframe['close_15m'].shift(3) < (dataframe['bb20_2_low_15m'].shift(3) * 0.992))
                    item_buy_logic.append(dataframe['r_14_15m'].shift(3) < -95.0)
                    item_buy_logic.append(dataframe['r_96_15m'].shift(3) < -86.0)
                    item_buy_logic.append(dataframe['close'] < dataframe['open'])

                # Condition #56 - 15m. Semi swing. Downtrend. Local dip.
                elif index == 56:
                    # Non-Standard protections (add below)

                    # Logic
                    item_buy_logic.append(dataframe['ewo_15m'].shift(3) < -14.8)
                    item_buy_logic.append(dataframe['cti_15m'].shift(3).rolling(15).max() < -0.9)
                    item_buy_logic.append(dataframe['r_14_15m'].shift(3) < -90.0)
                    item_buy_logic.append(dataframe['r_14'] < -50.0)

                # Condition #57 - 15m. Semi swing. Strong uptrend. Local dip. BTC not downtrend.
                elif index == 57:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_1h'] * 0.92))

                    # Logic
                    item_buy_logic.append(dataframe['ewo_15m'].shift(3) > 6.5)
                    item_buy_logic.append(dataframe['close_15m'].shift(3) < (dataframe['sma_30_15m'].shift(3) * 0.988))
                    item_buy_logic.append(dataframe['close_15m'].shift(3) < (dataframe['bb20_2_low_15m'].shift(3) * 0.996))
                    item_buy_logic.append(dataframe['rsi_14_15m'].shift(3) < 31.2)
                    item_buy_logic.append(dataframe['r_14_15m'].shift(3) < -94.0)
                    item_buy_logic.append(dataframe['r_96_15m'].shift(3) < -80.0)
                    item_buy_logic.append(dataframe['close'] < dataframe['open'])

                # Condition #58 - Semi swing. Local dip.
                elif index == 58:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['rmi_17'] < 49.0)
                    item_buy_logic.append(dataframe['cci_25'] < -120.0)
                    item_buy_logic.append(dataframe['srsi_fk'] < 32.0)
                    item_buy_logic.append(dataframe['bb20_delta'] > 0.026)
                    item_buy_logic.append(dataframe['bb20_width'] > 0.095)
                    item_buy_logic.append(dataframe['close_delta'] > dataframe['close'] * 10.0 / 1000.0 )
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_3_low'] * 0.995))

                # Condition #59 - Semi swing. Local dip.
                elif index == 59:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ema_100'] < (dataframe['ema_200'] * 1.054))
                    item_buy_logic.append(dataframe['bb20_width'] > 0.34)
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_mid'] * 1.014))
                    item_buy_logic.append(dataframe['volume_mean_12'] > (dataframe['volume_mean_24'] * 1.78))
                    item_buy_logic.append(dataframe['cti'] < -0.115)
                    item_buy_logic.append(dataframe['r_14'] < -45.0)

                # Condition #60 - Semi swing. Local dip.
                elif index == 60:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['roc_9_1h'] < 86.0)
                    item_buy_logic.append(dataframe['bb20_width_1h'] < 0.954)
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_1h'] * 0.75))

                    # Logic
                    item_buy_logic.append(dataframe['rsi_4'] < 44.0)
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_8'] * 0.935)
                    item_buy_logic.append(dataframe['ewo'] > -5.0)
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_16'] * 0.968)
                    item_buy_logic.append(dataframe['rsi_14'] < 22.0)

                # Condition #61 - Semi swing. Local dip. Stochastic fast cross.
                elif index == 61:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['open'] < dataframe['ema_8'] * 1.147)
                    item_buy_logic.append(qtpylib.crossed_above(dataframe['fastk'], dataframe['fastd']))
                    item_buy_logic.append(dataframe['fastk'] < 39.0)
                    item_buy_logic.append(dataframe['fastd'] < 28.0)
                    item_buy_logic.append(dataframe['adx'] > 13.0)
                    item_buy_logic.append(dataframe['ewo'] > 3.4)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['cti_1h'] < 0.0)
                    item_buy_logic.append(dataframe['r_480_1h'] < -25.0)

                # Condition #62 - Semi swing. Local dip. Downtrend.
                elif index == 62:
                    # Non-Standard protections

                    # Logic
                    item_buy_logic.append(dataframe['ewo'] < -8.2)

                    item_buy_logic.append(dataframe['bb20_2_mid_1h'] >= dataframe['t3_avg_1h'])
                    item_buy_logic.append(dataframe['t3_avg'] <= dataframe['ema_8'] * 1.121)
                    item_buy_logic.append(dataframe['cti'] < -0.9)
                    item_buy_logic.append(dataframe['r_14'] < -78.0)

                # Condition #63 - Semi swing. Local dip. ClucHA.
                elif index == 63:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_1h'] * 0.9))
                    item_buy_logic.append(dataframe['close'] > (dataframe['ema_200_1h'] * 0.7))

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_delta'] > dataframe['ha_close'] * 0.054)
                    item_buy_logic.append(dataframe['ha_closedelta'] > dataframe['ha_close'] * 0.017)
                    item_buy_logic.append(dataframe['ha_tail'] < dataframe['bb40_2_delta'] * 1.14)
                    item_buy_logic.append(dataframe['ha_close'] < dataframe['bb40_2_low'].shift())
                    item_buy_logic.append(dataframe['ha_close'] < dataframe['ha_close'].shift())
                    item_buy_logic.append(dataframe['roc_9_1h'] > 0.526)
                    item_buy_logic.append(dataframe['r_480_1h'] < -12.0)
                    item_buy_logic.append(dataframe['volume'] < (dataframe['volume_mean_4'] * 1.25))

                # Condition #64 - Semi swing. Squeeze momentum.
                elif index == 64:
                    # Non-Standard protections
                    item_buy_logic.append(dataframe['close'] > (dataframe['sup_level_1h'] * 0.93))

                    # Logic
                    item_buy_logic.append(dataframe['bb20_2_low'] < dataframe['kc_lowerband_28_1'])
                    item_buy_logic.append(dataframe['bb20_2_upp'] > dataframe['kc_upperband_28_1'])
                    item_buy_logic.append(dataframe['linreg_val_20'].shift(2) > dataframe['linreg_val_20'].shift(1))
                    item_buy_logic.append(dataframe['linreg_val_20'].shift(1) < dataframe['linreg_val_20'])
                    item_buy_logic.append(dataframe['linreg_val_20'] < 0.0)
                    item_buy_logic.append(dataframe['close'] < dataframe['ema_13'] * 0.981)
                    item_buy_logic.append(dataframe['ewo'] < -4.0)
                    item_buy_logic.append(dataframe['r_14'] < -46.0)
                    item_buy_logic.append(dataframe['crsi_1h'] > 20.0)
                
                elif index == 65:
                    
                    item_buy_logic.append(dataframe['rocr_1h'] > 0.04401)
                    #item_buy_logic.append(dataframe['bb40_2_low'].shift() > 0)
                    item_buy_logic.append(dataframe['bb_delta_cluc'] > dataframe['ha_close'] * 0.061)
                    item_buy_logic.append(dataframe['ha_closedelta'] > dataframe['ha_close'] * 0.04401)
                    item_buy_logic.append(dataframe['tail'] < dataframe['bb_delta_cluc'] * 1.02515)
                    item_buy_logic.append(dataframe['ha_close'] < dataframe['bb40_2_low'].shift())
                    item_buy_logic.append(dataframe['ha_close'] < dataframe['ha_close'].shift())
                
                elif index == 66:
                    item_buy_logic.append(dataframe['rmi_length_17'] < 49)
                    item_buy_logic.append(dataframe['cci_length_25'] <= -116)
                    item_buy_logic.append(dataframe['srsi_fk'] < 32)
                    item_buy_logic.append(dataframe['bb20_delta'] > 0.025)
                    item_buy_logic.append(dataframe['bb20_width'] > 0.095)
                    item_buy_logic.append(dataframe['closedelta'] > dataframe['close'] * 17.922 / 1000 )
                    item_buy_logic.append(dataframe['close'] < dataframe['bb20_3_low'] * 0.999)

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
                return False

        return True

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
        if (sell_reason == 'stop_loss'):
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
