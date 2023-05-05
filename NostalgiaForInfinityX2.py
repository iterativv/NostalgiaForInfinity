import copy
import logging
import pathlib
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
from freqtrade.persistence import Trade, LocalTrade
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
##  MEXC: https://promote.mexc.com/a/nfi  (10% discount on trading fees)                                   ##
##  ByBit: https://partner.bybit.com/b/nfi                                                                 ##
##  Huobi: https://www.huobi.com/en-us/v/register/double-invite/?inviter_id=11345710&invite_code=ubpt2223  ##
##         (20% discount on trading fees)                                                                  ##
##  Bitvavo: https://account.bitvavo.com/create?a=D22103A4BC (no fees for the first € 1000)                ##
#############################################################################################################

class NostalgiaForInfinityX2(IStrategy):
    INTERFACE_VERSION = 3

    def version(self) -> str:
        return "v12.0.503"

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

    # Do you want to use the hold feature? (with hold-trades.json)
    hold_support_enabled = True

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the "ask_strategy" section in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = True

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 800

    # Normal mode tags
    normal_mode_tags = ['force_entry', '1', '2', '3', '4', '5', '6']
    # Pump mode tags
    pump_mode_tags = ['21', '22']
    # Quick mode tags
    quick_mode_tags = ['41', '42', '43', '44']
    # Rebuy mode tags
    rebuy_mode_tags = ['61']
    # Long mode tags
    long_mode_tags = ['81', '82']

    normal_mode_name = "normal"
    pump_mode_name = "pump"
    quick_mode_name = "quick"
    rebuy_mode_name = "rebuy"
    long_mode_name = "long"

    # Stop thesholds. 0: Doom Bull, 1: Doom Bear, 2: u_e Bull, 3: u_e Bear, 4: u_e mins Bull, 5: u_e mins Bear.
    # 6: u_e ema % Bull, 7: u_e ema % Bear, 8: u_e RSI diff Bull, 9: u_e RSI diff Bear.
    # 10: enable Doom Bull, 11: enable Doom Bear, 12: enable u_e Bull, 13: enable u_e Bear.
    stop_thresholds = [-0.2, -0.2, -0.025, -0.025, 720, 720, 0.016, 0.016, 24.0, 24.0, False, False, True, True]

    # Rebuy mode minimum number of free slots
    rebuy_mode_min_free_slots = 2

    # Position adjust feature
    position_adjustment_enable = True

    # Grinding feature
    grinding_enable = True
    # Grinding stakes
    grinding_stakes = [0.25, 0.25, 0.25, 0.25, 0.25]
    grinding_stakes_alt_1 = [0.5, 0.5]
    grinding_stakes_alt_2 = [0.75]
    # Current total profit
    grinding_thresholds = [-0.04, -0.08, -0.1, -0.12, -0.14]
    grinding_thresholds_alt_1 = [-0.06, -0.12]
    grinding_thresholds_alt_2 = [-0.06]

    stake_rebuy_mode_multiplier = 0.33
    pa_rebuy_mode_max = 2
    pa_rebuy_mode_pcts = (-0.02, -0.04, -0.04)
    pa_rebuy_mode_multi = (1.0, 1.0, 1.0)

    # Profit max thresholds
    profit_max_thresholds = [0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.05, 0.05]

    # Max allowed buy "slippage", how high to buy on the candle
    max_slippage = 0.01

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

        "buy_condition_21_enable": True,
        "buy_condition_22_enable": True,

        "buy_condition_41_enable": True,
        "buy_condition_42_enable": True,
        "buy_condition_43_enable": True,
        "buy_condition_44_enable": True,

        # "buy_condition_61_enable": False,

        # "buy_condition_81_enable": False,
        # "buy_condition_82_enable": False,
    }

    buy_protection_params = {}

    #############################################################
    # CACHES

    hold_trades_cache = None
    target_profit_cache = None
    #############################################################

    def __init__(self, config: dict) -> None:
        if 'ccxt_config' not in config['exchange']:
            config['exchange']['ccxt_config'] = {}
        if 'ccxt_async_config' not in config['exchange']:
            config['exchange']['ccxt_async_config'] = {}

        options = {
            'brokerId': None,
            'broker': {'spot': None, 'margin': None, 'future': None, 'delivery': None},
            'partner': {'spot': {'id': None, 'key': None}, 'future': {'id': None, 'key': None}, 'id': None, 'key': None}
        }

        config['exchange']['ccxt_config']['options'] = options
        config['exchange']['ccxt_async_config']['options'] = options
        super().__init__(config)
        if (('exit_profit_only' in self.config and self.config['exit_profit_only'])
                or ('sell_profit_only' in self.config and self.config['sell_profit_only'])):
            self.exit_profit_only = True
        if ('stop_thresholds_normal' in self.config):
            self.stop_thresholds_normal = self.config['stop_thresholds_normal']
        if ('stop_thresholds_pump' in self.config):
            self.stop_thresholds_pump = self.config['stop_thresholds_pump']
        if ('stop_thresholds_quick' in self.config):
            self.stop_thresholds_quick = self.config['stop_thresholds_quick']
        if ('stop_thresholds_rebuy' in self.config):
            self.stop_thresholds_rebuy = self.config['stop_thresholds_rebuy']
        if ('stop_thresholds_long' in self.config):
            self.stop_thresholds_long = self.config['stop_thresholds_long']
        if ('profit_max_thresholds' in self.config):
            self.profit_max_thresholds = self.config['profit_max_thresholds']
        if ('grinding_enable' in self.config):
            self.grinding_enable = self.config['grinding_enable']
        if ('grinding_stakes' in self.config):
            self.grinding_stakes = self.config['grinding_stakes']
        if ('grinding_thresholds' in self.config):
            self.grinding_thresholds = self.config['grinding_thresholds']
        if ('grinding_stakes_alt_1' in self.config):
            self.grinding_stakes_alt_1 = self.config['grinding_stakes_alt_1']
        if ('grinding_thresholds_alt_1' in self.config):
            self.grinding_thresholds_alt_1 = self.config['grinding_thresholds_alt_1']
        if ('grinding_stakes_alt_2' in self.config):
            self.grinding_stakes_alt_2 = self.config['grinding_stakes_alt_2']
        if ('grinding_thresholds_alt_2' in self.config):
            self.grinding_thresholds_alt_2 = self.config['grinding_thresholds_alt_2']
        if ('max_slippage' in self.config):
            self.max_slippage = self.config['max_slippage']
        if self.target_profit_cache is None:
            bot_name = ""
            if ('bot_name' in self.config):
                bot_name = self.config["bot_name"] + "-"
            self.target_profit_cache = Cache(
                self.config["user_data_dir"] / ("nfix2-profit_max-" + bot_name  + self.config["exchange"]["name"] + "-" + self.config["stake_currency"] +  ("-(backtest)" if (self.config['runmode'].value == 'backtest') else "") + ".json")
            )

        # OKX, Kraken provides a lower number of candle data per API call
        if self.config["exchange"]["name"] in ["okx", "okex"]:
            self.startup_candle_count = 480
        elif self.config["exchange"]["name"] in ["kraken"]:
            self.startup_candle_count = 710
        elif self.config["exchange"]["name"] in ["bybit"]:
            self.startup_candle_count = 199

        # If the cached data hasn't changed, it's a no-op
        self.target_profit_cache.save()

    def get_ticker_indicator(self):
        return int(self.timeframe[:-1])

    def exit_normal(self, pair: str, current_rate: float,
                    profit_stake: float, profit_ratio: float, profit_current_stake_ratio: float, profit_init_ratio: float,
                    max_profit: float, max_loss: float,
                    last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5,
                    trade: 'Trade', current_time: 'datetime', enter_tags) -> tuple:
        sell = False

        # Original sell signals
        sell, signal_name = self.exit_signals(self.normal_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Main sell signals
        if not sell:
            sell, signal_name = self.exit_main(self.normal_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Williams %R based sells
        if not sell:
            sell, signal_name = self.exit_r(self.normal_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Stoplosses
        if not sell:
            sell, signal_name = self.exit_stoploss(self.normal_mode_name, current_rate, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Profit Target Signal
        # Check if pair exist on target_profit_cache
        if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
            previous_rate = self.target_profit_cache.data[pair]['rate']
            previous_profit = self.target_profit_cache.data[pair]['profit']
            previous_sell_reason = self.target_profit_cache.data[pair]['sell_reason']
            previous_time_profit_reached = datetime.fromisoformat(self.target_profit_cache.data[pair]['time_profit_reached'])

            sell_max, signal_name_max = self.exit_profit_target(self.normal_mode_name, pair, trade, current_time, current_rate,
                                                                profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio,
                                                                last_candle, previous_candle_1,
                                                                previous_rate, previous_profit, previous_sell_reason,
                                                                previous_time_profit_reached, enter_tags)
            if sell_max and signal_name_max is not None:
                return True, f"{signal_name_max}_m"
            if (previous_sell_reason in [f"exit_{self.normal_mode_name}_stoploss_u_e"]):
                if (profit_ratio > (previous_profit + 0.005)):
                    mark_pair, mark_signal = self.mark_profit_target(self.normal_mode_name, pair, True, previous_sell_reason, trade, current_time, current_rate, profit_ratio, last_candle, previous_candle_1)
                    if mark_pair:
                        self._set_profit_target(pair, mark_signal, current_rate, profit_ratio, current_time)
            elif (profit_current_stake_ratio > (previous_profit + 0.005)) and (previous_sell_reason not in [f"exit_{self.normal_mode_name}_stoploss_doom"]):
                # Update the target, raise it.
                mark_pair, mark_signal = self.mark_profit_target(self.normal_mode_name, pair, True, previous_sell_reason, trade, current_time, current_rate, profit_current_stake_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)

        # Add the pair to the list, if a sell triggered and conditions met
        if sell and signal_name is not None:
            previous_profit = None
            if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                previous_profit = self.target_profit_cache.data[pair]['profit']
            if (signal_name in [f"exit_{self.normal_mode_name}_stoploss_doom", f"exit_{self.normal_mode_name}_stoploss_u_e"]):
                mark_pair, mark_signal = self.mark_profit_target(self.normal_mode_name, pair, sell, signal_name, trade, current_time, current_rate, profit_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_ratio, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
            elif (
                    (previous_profit is None)
                    or (previous_profit < profit_current_stake_ratio)
            ):
                mark_pair, mark_signal = self.mark_profit_target(self.normal_mode_name, pair, sell, signal_name, trade, current_time, current_rate, profit_current_stake_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
        else:
            if (
                    (profit_current_stake_ratio >= self.profit_max_thresholds[0])
            ):
                previous_profit = None
                if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                    previous_profit = self.target_profit_cache.data[pair]['profit']
                if (previous_profit is None) or (previous_profit < profit_current_stake_ratio):
                    mark_signal = f"exit_profit_{self.normal_mode_name}_max"
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)

        if (signal_name not in [f"exit_profit_{self.normal_mode_name}_max", f"exit_{self.normal_mode_name}_stoploss_doom", f"exit_{self.normal_mode_name}_stoploss_u_e"]):
            if sell and (signal_name is not None):
                return True, f"{signal_name}"

        return False, None

    def exit_pump(self, pair: str, current_rate: float,
                    profit_stake: float, profit_ratio: float, profit_current_stake_ratio: float, profit_init_ratio: float,
                    max_profit: float, max_loss: float,
                    last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5,
                    trade: 'Trade', current_time: 'datetime', enter_tags) -> tuple:
        sell = False

        # Original sell signals
        sell, signal_name = self.exit_signals(self.pump_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Main sell signals
        if not sell:
            sell, signal_name = self.exit_main(self.pump_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Williams %R based sells
        if not sell:
            sell, signal_name = self.exit_r(self.pump_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Stoplosses
        if not sell:
            sell, signal_name = self.exit_stoploss(self.pump_mode_name, current_rate, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Profit Target Signal
        # Check if pair exist on target_profit_cache
        if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
            previous_rate = self.target_profit_cache.data[pair]['rate']
            previous_profit = self.target_profit_cache.data[pair]['profit']
            previous_sell_reason = self.target_profit_cache.data[pair]['sell_reason']
            previous_time_profit_reached = datetime.fromisoformat(self.target_profit_cache.data[pair]['time_profit_reached'])

            sell_max, signal_name_max = self.exit_profit_target(self.pump_mode_name, pair, trade, current_time, current_rate,
                                                                profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio,
                                                                last_candle, previous_candle_1,
                                                                previous_rate, previous_profit, previous_sell_reason,
                                                                previous_time_profit_reached, enter_tags)
            if sell_max and signal_name_max is not None:
                return True, f"{signal_name_max}_m"
            if (previous_sell_reason in [f"exit_{self.pump_mode_name}_stoploss_u_e"]):
                if (profit_ratio > (previous_profit + 0.005)):
                    mark_pair, mark_signal = self.mark_profit_target(self.pump_mode_name, pair, True, previous_sell_reason, trade, current_time, current_rate, profit_ratio, last_candle, previous_candle_1)
                    if mark_pair:
                        self._set_profit_target(pair, mark_signal, current_rate, profit_ratio, current_time)
            elif (profit_current_stake_ratio > (previous_profit + 0.005)) and (previous_sell_reason not in [f"exit_{self.pump_mode_name}_stoploss_doom"]):
                # Update the target, raise it.
                mark_pair, mark_signal = self.mark_profit_target(self.pump_mode_name, pair, True, previous_sell_reason, trade, current_time, current_rate, profit_current_stake_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)

        # Add the pair to the list, if a sell triggered and conditions met
        if sell and signal_name is not None:
            previous_profit = None
            if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                previous_profit = self.target_profit_cache.data[pair]['profit']
            if (signal_name in [f"exit_{self.pump_mode_name}_stoploss_doom", f"exit_{self.pump_mode_name}_stoploss_u_e"]):
                mark_pair, mark_signal = self.mark_profit_target(self.pump_mode_name, pair, sell, signal_name, trade, current_time, current_rate, profit_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_ratio, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
            elif (
                    (previous_profit is None)
                    or (previous_profit < profit_current_stake_ratio)
            ):
                mark_pair, mark_signal = self.mark_profit_target(self.pump_mode_name, pair, sell, signal_name, trade, current_time, current_rate, profit_current_stake_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
        else:
            if (
                    (profit_current_stake_ratio >= self.profit_max_thresholds[2])
            ):
                previous_profit = None
                if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                    previous_profit = self.target_profit_cache.data[pair]['profit']
                if (previous_profit is None) or (previous_profit < profit_current_stake_ratio):
                    mark_signal = f"exit_profit_{self.pump_mode_name}_max"
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)

        if (signal_name not in [f"exit_profit_{self.pump_mode_name}_max", f"exit_{self.pump_mode_name}_stoploss_doom", f"exit_{self.pump_mode_name}_stoploss_u_e"]):
            if sell and (signal_name is not None):
                return True, f"{signal_name}"

        return False, None

    def exit_quick(self, pair: str, current_rate: float,
                    profit_stake: float, profit_ratio: float, profit_current_stake_ratio: float, profit_init_ratio: float,
                    max_profit: float, max_loss: float,
                    last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5,
                    trade: 'Trade', current_time: 'datetime', enter_tags) -> tuple:
        sell = False

        # Original sell signals
        sell, signal_name = self.exit_signals(self.quick_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Main sell signals
        if not sell:
            sell, signal_name = self.exit_main(self.quick_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Williams %R based sells
        if not sell:
            sell, signal_name = self.exit_r(self.quick_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Stoplosses
        if not sell:
            sell, signal_name = self.exit_stoploss(self.quick_mode_name, current_rate, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Extra sell logic
        if not sell:
            if (0.09 >= profit_current_stake_ratio > 0.02) and (last_candle['rsi_14'] > 78.0):
                sell, signal_name =  True, f'exit_{self.quick_mode_name}_q_1'

            if (0.09 >= profit_current_stake_ratio > 0.02) and (last_candle['cti_20'] > 0.95):
                sell, signal_name = True, f'exit_{self.quick_mode_name}_q_2'

            if (0.09 >= profit_current_stake_ratio > 0.02) and (last_candle['r_14'] >= -0.1):
                sell, signal_name = True, f'exit_{self.quick_mode_name}_q_3'

        # Profit Target Signal
        # Check if pair exist on target_profit_cache
        if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
            previous_rate = self.target_profit_cache.data[pair]['rate']
            previous_profit = self.target_profit_cache.data[pair]['profit']
            previous_sell_reason = self.target_profit_cache.data[pair]['sell_reason']
            previous_time_profit_reached = datetime.fromisoformat(self.target_profit_cache.data[pair]['time_profit_reached'])

            sell_max, signal_name_max = self.exit_profit_target(self.quick_mode_name, pair, trade, current_time, current_rate,
                                                                profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio,
                                                                last_candle, previous_candle_1,
                                                                previous_rate, previous_profit, previous_sell_reason,
                                                                previous_time_profit_reached, enter_tags)
            if sell_max and signal_name_max is not None:
                return True, f"{signal_name_max}_m"
            if (previous_sell_reason in [f"exit_{self.quick_mode_name}_stoploss_u_e"]):
                if (profit_ratio > (previous_profit + 0.005)):
                    mark_pair, mark_signal = self.mark_profit_target(self.quick_mode_name, pair, True, previous_sell_reason, trade, current_time, current_rate, profit_ratio, last_candle, previous_candle_1)
                    if mark_pair:
                        self._set_profit_target(pair, mark_signal, current_rate, profit_ratio, current_time)
            elif (profit_current_stake_ratio > (previous_profit + 0.005)) and (previous_sell_reason not in [f"exit_{self.quick_mode_name}_stoploss_doom"]):
                # Update the target, raise it.
                mark_pair, mark_signal = self.mark_profit_target(self.quick_mode_name, pair, True, previous_sell_reason, trade, current_time, current_rate, profit_current_stake_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)

        # Add the pair to the list, if a sell triggered and conditions met
        if sell and signal_name is not None:
            previous_profit = None
            if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                previous_profit = self.target_profit_cache.data[pair]['profit']
            if (signal_name in [f"exit_{self.quick_mode_name}_stoploss_doom", f"exit_{self.quick_mode_name}_stoploss_u_e"]):
                mark_pair, mark_signal = self.mark_profit_target(self.quick_mode_name, pair, sell, signal_name, trade, current_time, current_rate, profit_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_ratio, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
            elif (
                    (previous_profit is None)
                    or (previous_profit < profit_current_stake_ratio)
            ):
                mark_pair, mark_signal = self.mark_profit_target(self.quick_mode_name, pair, sell, signal_name, trade, current_time, current_rate, profit_current_stake_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
        else:
            if (
                    (profit_current_stake_ratio >= self.profit_max_thresholds[4])
            ):
                previous_profit = None
                if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                    previous_profit = self.target_profit_cache.data[pair]['profit']
                if (previous_profit is None) or (previous_profit < profit_current_stake_ratio):
                    mark_signal = f"exit_profit_{self.quick_mode_name}_max"
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)

        if (signal_name not in [f"exit_profit_{self.quick_mode_name}_max", f"exit_{self.quick_mode_name}_stoploss_doom", f"exit_{self.quick_mode_name}_stoploss_u_e"]):
            if sell and (signal_name is not None):
                return True, f"{signal_name}"

        return False, None

    def exit_rebuy(self, pair: str, current_rate: float,
                    profit_stake: float, profit_ratio: float, profit_current_stake_ratio: float, profit_init_ratio: float,
                    max_profit: float, max_loss: float,
                    last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5,
                    trade: 'Trade', current_time: 'datetime', enter_tags) -> tuple:
        sell = False

        # Original sell signals
        sell, signal_name = self.exit_signals(self.rebuy_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Main sell signals
        if not sell:
            sell, signal_name = self.exit_main(self.rebuy_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Williams %R based sells
        if not sell:
            sell, signal_name = self.exit_r(self.rebuy_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Stoplosses
        if not sell:
            sell, signal_name = self.exit_stoploss(self.rebuy_mode_name, current_rate, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Profit Target Signal
        # Check if pair exist on target_profit_cache
        if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
            previous_rate = self.target_profit_cache.data[pair]['rate']
            previous_profit = self.target_profit_cache.data[pair]['profit']
            previous_sell_reason = self.target_profit_cache.data[pair]['sell_reason']
            previous_time_profit_reached = datetime.fromisoformat(self.target_profit_cache.data[pair]['time_profit_reached'])

            sell_max, signal_name_max = self.exit_profit_target(self.rebuy_mode_name, pair, trade, current_time, current_rate,
                                                                profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio,
                                                                last_candle, previous_candle_1,
                                                                previous_rate, previous_profit, previous_sell_reason,
                                                                previous_time_profit_reached, enter_tags)
            if sell_max and signal_name_max is not None:
                return True, f"{signal_name_max}_m"
            if (previous_sell_reason in [f"exit_{self.rebuy_mode_name}_stoploss_u_e"]):
                if (profit_ratio > (previous_profit + 0.005)):
                    mark_pair, mark_signal = self.mark_profit_target(self.rebuy_mode_name, pair, True, previous_sell_reason, trade, current_time, current_rate, profit_ratio, last_candle, previous_candle_1)
                    if mark_pair:
                        self._set_profit_target(pair, mark_signal, current_rate, profit_ratio, current_time)
            elif (profit_current_stake_ratio > (previous_profit + 0.005)) and (previous_sell_reason not in [f"exit_{self.rebuy_mode_name}_stoploss_doom"]):
                # Update the target, raise it.
                mark_pair, mark_signal = self.mark_profit_target(self.rebuy_mode_name, pair, True, previous_sell_reason, trade, current_time, current_rate, profit_current_stake_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)

        # Add the pair to the list, if a sell triggered and conditions met
        if sell and signal_name is not None:
            previous_profit = None
            if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                previous_profit = self.target_profit_cache.data[pair]['profit']
            if (signal_name in [f"exit_{self.rebuy_mode_name}_stoploss_doom", f"exit_{self.rebuy_mode_name}_stoploss_u_e"]):
                mark_pair, mark_signal = self.mark_profit_target(self.rebuy_mode_name, pair, sell, signal_name, trade, current_time, current_rate, profit_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_ratio, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
            elif (
                    (previous_profit is None)
                    or (previous_profit < profit_current_stake_ratio)
            ):
                mark_pair, mark_signal = self.mark_profit_target(self.rebuy_mode_name, pair, sell, signal_name, trade, current_time, current_rate, profit_current_stake_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
        else:
            if (
                    (profit_current_stake_ratio >= self.profit_max_thresholds[6])
            ):
                previous_profit = None
                if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                    previous_profit = self.target_profit_cache.data[pair]['profit']
                if (previous_profit is None) or (previous_profit < profit_current_stake_ratio):
                    mark_signal = f"exit_profit_{self.rebuy_mode_name}_max"
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)

        if (signal_name not in [f"exit_profit_{self.rebuy_mode_name}_max", f"exit_{self.rebuy_mode_name}_stoploss_doom", f"exit_{self.rebuy_mode_name}_stoploss_u_e"]):
            if sell and (signal_name is not None):
                return True, f"{signal_name}"

        return False, None

    def exit_long(self, pair: str, current_rate: float,
                    profit_stake: float, profit_ratio: float, profit_current_stake_ratio: float, profit_init_ratio: float,
                    max_profit: float, max_loss: float,
                    last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5,
                    trade: 'Trade', current_time: 'datetime', enter_tags) -> tuple:
        sell = False

        # Original sell signals
        sell, signal_name = self.exit_signals(self.long_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Main sell signals
        if not sell:
            sell, signal_name = self.exit_main(self.long_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Williams %R based sells
        if not sell:
            sell, signal_name = self.exit_r(self.long_mode_name, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Stoplosses
        if not sell:
            sell, signal_name = self.exit_stoploss(self.long_mode_name, current_rate, profit_current_stake_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)

        # Profit Target Signal
        # Check if pair exist on target_profit_cache
        if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
            previous_rate = self.target_profit_cache.data[pair]['rate']
            previous_profit = self.target_profit_cache.data[pair]['profit']
            previous_sell_reason = self.target_profit_cache.data[pair]['sell_reason']
            previous_time_profit_reached = datetime.fromisoformat(self.target_profit_cache.data[pair]['time_profit_reached'])

            sell_max, signal_name_max = self.exit_profit_target(self.long_mode_name, pair, trade, current_time, current_rate,
                                                                profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio,
                                                                last_candle, previous_candle_1,
                                                                previous_rate, previous_profit, previous_sell_reason,
                                                                previous_time_profit_reached, enter_tags)
            if sell_max and signal_name_max is not None:
                return True, f"{signal_name_max}_m"
            if (previous_sell_reason in [f"exit_{self.long_mode_name}_stoploss_u_e"]):
                if (profit_ratio > (previous_profit + 0.005)):
                    mark_pair, mark_signal = self.mark_profit_target(self.long_mode_name, pair, True, previous_sell_reason, trade, current_time, current_rate, profit_ratio, last_candle, previous_candle_1)
                    if mark_pair:
                        self._set_profit_target(pair, mark_signal, current_rate, profit_ratio, current_time)
            elif (profit_current_stake_ratio > (previous_profit + 0.005)) and (previous_sell_reason not in [f"exit_{self.long_mode_name}_stoploss_doom"]):
                # Update the target, raise it.
                mark_pair, mark_signal = self.mark_profit_target(self.long_mode_name, pair, True, previous_sell_reason, trade, current_time, current_rate, profit_current_stake_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)

        # Add the pair to the list, if a sell triggered and conditions met
        if sell and signal_name is not None:
            previous_profit = None
            if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                previous_profit = self.target_profit_cache.data[pair]['profit']
            if (signal_name in [f"exit_{self.long_mode_name}_stoploss_doom", f"exit_{self.long_mode_name}_stoploss_u_e"]):
                mark_pair, mark_signal = self.mark_profit_target(self.long_mode_name, pair, sell, signal_name, trade, current_time, current_rate, profit_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_ratio, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
            elif (
                    (previous_profit is None)
                    or (previous_profit < profit_current_stake_ratio)
            ):
                mark_pair, mark_signal = self.mark_profit_target(self.long_mode_name, pair, sell, signal_name, trade, current_time, current_rate, profit_current_stake_ratio, last_candle, previous_candle_1)
                if mark_pair:
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)
                else:
                    # Just sell it, without maximize
                    return True, f"{signal_name}"
        else:
            if (
                    (profit_current_stake_ratio >= self.profit_max_thresholds[8])
            ):
                previous_profit = None
                if self.target_profit_cache is not None and pair in self.target_profit_cache.data:
                    previous_profit = self.target_profit_cache.data[pair]['profit']
                if (previous_profit is None) or (previous_profit < profit_current_stake_ratio):
                    mark_signal = f"exit_profit_{self.long_mode_name}_max"
                    self._set_profit_target(pair, mark_signal, current_rate, profit_current_stake_ratio, current_time)

        if (signal_name not in [f"exit_profit_{self.long_mode_name}_max", f"exit_{self.long_mode_name}_stoploss_doom", f"exit_{self.long_mode_name}_stoploss_u_e"]):
            if sell and (signal_name is not None):
                return True, f"{signal_name}"

        return False, None

    def mark_profit_target(self, mode_name: str, pair: str, sell: bool, signal_name: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float, last_candle, previous_candle_1) -> tuple:
        if sell and (signal_name is not None):
            return pair, signal_name

        return None, None

    def exit_profit_target(self, mode_name: str, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                           profit_stake: float, profit_ratio: float, profit_current_stake_ratio: float, profit_init_ratio: float,
                           last_candle, previous_candle_1, previous_rate, previous_profit, previous_sell_reason, previous_time_profit_reached, enter_tags) -> tuple:
        if (previous_sell_reason in [f"exit_{mode_name}_stoploss_doom"]):
            if (profit_ratio > 0.04):
                # profit is over the threshold, don't exit
                self._remove_profit_target(pair)
                return False, None
            if (profit_ratio < -0.18):
                if (profit_ratio < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (profit_ratio < -0.1):
                if (profit_ratio < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (profit_ratio < -0.04):
                if (profit_ratio < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            else:
                if (profit_ratio < (previous_profit - 0.04)):
                    return True, previous_sell_reason
        elif (previous_sell_reason in [f"exit_{mode_name}_stoploss_u_e"]):
            if (profit_current_stake_ratio > 0.04):
                # profit is over the threshold, don't exit
                self._remove_profit_target(pair)
                return False, None
            if (profit_ratio < (previous_profit - (0.20 if trade.realized_profit == 0.0 else 0.26))):
                    return True, previous_sell_reason
        elif (previous_sell_reason in [f"exit_profit_{mode_name}_max"]):
            if (profit_current_stake_ratio < -0.08):
                # profit is under the threshold, cancel it
                self._remove_profit_target(pair)
                return False, None
            if (0.001 <= profit_current_stake_ratio < 0.01):
                if (profit_current_stake_ratio < (previous_profit - 0.01)):
                    return True, previous_sell_reason
            elif (0.01 <= profit_current_stake_ratio < 0.02):
                if (profit_current_stake_ratio < (previous_profit - 0.02)):
                    return True, previous_sell_reason
            elif (0.02 <= profit_current_stake_ratio < 0.03):
                if (profit_current_stake_ratio < (previous_profit - 0.025)):
                    return True, previous_sell_reason
            elif (0.03 <= profit_current_stake_ratio < 0.05):
                if (profit_current_stake_ratio < (previous_profit - 0.03)):
                    return True, previous_sell_reason
            elif (0.05 <= profit_current_stake_ratio < 0.08):
                if (profit_current_stake_ratio < (previous_profit - 0.035)):
                    return True, previous_sell_reason
            elif (0.08 <= profit_current_stake_ratio < 0.12):
                if (profit_current_stake_ratio < (previous_profit - 0.04)):
                    return True, previous_sell_reason
            elif (0.12 <= profit_current_stake_ratio):
                if (profit_current_stake_ratio < (previous_profit - 0.045)):
                    return True, previous_sell_reason
        else:
            return False, None

        return False, None

    def exit_signals(self, mode_name: str, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        # Sell signal 1
        if (last_candle['rsi_14'] > 79.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']) and (previous_candle_3['close'] > previous_candle_3['bb20_2_upp']) and (previous_candle_4['close'] > previous_candle_4['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_1_1_1'
            else:
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_1_2_1'

        # Sell signal 2
        elif (last_candle['rsi_14'] > 80.0) and (last_candle['close'] > last_candle['bb20_2_upp']) and (previous_candle_1['close'] > previous_candle_1['bb20_2_upp']) and (previous_candle_2['close'] > previous_candle_2['bb20_2_upp']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_2_1_1'
            else:
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_2_2_1'

        # Sell signal 3
        elif (last_candle['rsi_14'] > 85.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_3_1_1'
            else:
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_3_2_1'

        # Sell signal 4
        elif (last_candle['rsi_14'] > 80.0) and (last_candle['rsi_14_1h'] > 78.0):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_4_1_1'
            else:
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_4_2_1'

        # Sell signal 6
        elif (last_candle['close'] < last_candle['ema_200']) and (last_candle['close'] > last_candle['ema_50']) and (last_candle['rsi_14'] > 79.0):
            if (current_profit > 0.01):
                return True, f'exit_{mode_name}_6_1'

        # Sell signal 7
        elif (last_candle['rsi_14_1h'] > 79.0) and (last_candle['crossed_below_ema_12_26']):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_7_1_1'
            else:
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_7_2_1'

        # Sell signal 8
        elif (last_candle['close'] > last_candle['bb20_2_upp_1h'] * 1.08):
            if (last_candle['close'] > last_candle['ema_200']):
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_8_1_1'
            else:
                if (current_profit > 0.01):
                    return True, f'exit_{mode_name}_8_2_1'

        return False, None

    def exit_main(self, mode_name: str, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if (last_candle['close'] > last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 20.0):
                    return True, f'exit_{mode_name}_o_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 28.0):
                    return True, f'exit_{mode_name}_o_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 30.0):
                    return True, f'exit_{mode_name}_o_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 32.0):
                    return True, f'exit_{mode_name}_o_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 34.0):
                    return True, f'exit_{mode_name}_o_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 36.0):
                    return True, f'exit_{mode_name}_o_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 38.0):
                    return True, f'exit_{mode_name}_o_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 40.0):
                    return True, f'exit_{mode_name}_o_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 42.0):
                    return True, f'exit_{mode_name}_o_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 44.0):
                    return True, f'exit_{mode_name}_o_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 46.0):
                    return True, f'exit_{mode_name}_o_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 44.0):
                    return True, f'exit_{mode_name}_o_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 42.0):
                    return True, f'exit_{mode_name}_o_12'
        elif (last_candle['close'] < last_candle['sma_200_1h']):
            if 0.01 > current_profit >= 0.001:
                if (last_candle['rsi_14'] < 22.0):
                    return True, f'exit_{mode_name}_u_0'
            elif 0.02 > current_profit >= 0.01:
                if (last_candle['rsi_14'] < 30.0):
                    return True, f'exit_{mode_name}_u_1'
            elif 0.03 > current_profit >= 0.02:
                if (last_candle['rsi_14'] < 32.0):
                    return True, f'exit_{mode_name}_u_2'
            elif 0.04 > current_profit >= 0.03:
                if (last_candle['rsi_14'] < 34.0):
                    return True, f'exit_{mode_name}_u_3'
            elif 0.05 > current_profit >= 0.04:
                if (last_candle['rsi_14'] < 36.0):
                    return True, f'exit_{mode_name}_u_4'
            elif 0.06 > current_profit >= 0.05:
                if (last_candle['rsi_14'] < 38.0):
                    return True, f'exit_{mode_name}_u_5'
            elif 0.07 > current_profit >= 0.06:
                if (last_candle['rsi_14'] < 40.0):
                    return True, f'exit_{mode_name}_u_6'
            elif 0.08 > current_profit >= 0.07:
                if (last_candle['rsi_14'] < 42.0):
                    return True, f'exit_{mode_name}_u_7'
            elif 0.09 > current_profit >= 0.08:
                if (last_candle['rsi_14'] < 44.0):
                    return True, f'exit_{mode_name}_u_8'
            elif 0.1 > current_profit >= 0.09:
                if (last_candle['rsi_14'] < 46.0):
                    return True, f'exit_{mode_name}_u_9'
            elif 0.12 > current_profit >= 0.1:
                if (last_candle['rsi_14'] < 48.0):
                    return True, f'exit_{mode_name}_u_10'
            elif 0.2 > current_profit >= 0.12:
                if (last_candle['rsi_14'] < 46.0):
                    return True, f'exit_{mode_name}_u_11'
            elif current_profit >= 0.2:
                if (last_candle['rsi_14'] < 44.0):
                    return True, f'exit_{mode_name}_u_12'

        return False, None

    def exit_r(self, mode_name: str, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        if 0.01 > current_profit >= 0.001:
            if (last_candle['r_480'] > -0.1):
                return True, f'exit_{mode_name}_w_0_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, f'exit_{mode_name}_w_0_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 44.0):
                return True, f'exit_{mode_name}_w_0_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_0_4'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_0_5'
        elif 0.02 > current_profit >= 0.01:
            if (last_candle['r_480'] > -0.2):
                return True, f'exit_{mode_name}_w_1_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 78.0):
                return True, f'exit_{mode_name}_w_1_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 46.0):
                return True, f'exit_{mode_name}_w_1_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_1_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_1_5'
        elif 0.03 > current_profit >= 0.02:
            if (last_candle['r_480'] > -0.3):
                return True, f'exit_{mode_name}_w_2_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 77.0):
                return True, f'exit_{mode_name}_w_2_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 48.0):
                return True, f'exit_{mode_name}_w_2_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_2_4'
            elif (last_candle['r_14'] >= -3.0) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_2_5'
        elif 0.04 > current_profit >= 0.03:
            if (last_candle['r_480'] > -0.4):
                return True, f'exit_{mode_name}_w_3_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 76.0):
                return True, f'exit_{mode_name}_w_3_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 50.0):
                return True, f'exit_{mode_name}_w_3_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_3_4'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_3_5'
        elif 0.05 > current_profit >= 0.04:
            if (last_candle['r_480'] > -0.5):
                return True, f'exit_{mode_name}_w_4_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 75.0):
                return True, f'exit_{mode_name}_w_4_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 52.0):
                return True, f'exit_{mode_name}_w_4_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_4_4'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_4_5'
        elif 0.06 > current_profit >= 0.05:
            if (last_candle['r_480'] > -0.6):
                return True, f'exit_{mode_name}_w_5_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 74.0):
                return True, f'exit_{mode_name}_w_5_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 54.0):
                return True, f'exit_{mode_name}_w_5_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 70.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_5_4'
            elif (last_candle['r_14'] >= -6.0) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_5_5'
        elif 0.07 > current_profit >= 0.06:
            if (last_candle['r_480'] > -0.7):
                return True, f'exit_{mode_name}_w_6_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 75.0):
                return True, f'exit_{mode_name}_w_6_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 52.0):
                return True, f'exit_{mode_name}_w_6_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 71.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_6_4'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_6_5'
        elif 0.08 > current_profit >= 0.07:
            if (last_candle['r_480'] > -0.8):
                return True, f'exit_{mode_name}_w_7_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 76.0):
                return True, f'exit_{mode_name}_w_7_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 50.0):
                return True, f'exit_{mode_name}_w_7_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 72.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_7_4'
            elif (last_candle['r_14'] >= -4.0) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_7_5'
        elif 0.09 > current_profit >= 0.08:
            if (last_candle['r_480'] > -0.9):
                return True, f'exit_{mode_name}_w_8_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 77.0):
                return True, f'exit_{mode_name}_w_8_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 48.0):
                return True, f'exit_{mode_name}_w_8_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 73.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_8_4'
            elif (last_candle['r_14'] >= -3.0) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_8_5'
        elif 0.1 > current_profit >= 0.09:
            if (last_candle['r_480'] > -1.0):
                return True, f'exit_{mode_name}_w_9_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 78.0):
                return True, f'exit_{mode_name}_w_9_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 46.0):
                return True, f'exit_{mode_name}_w_9_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 74.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_9_4'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_9_5'
        elif 0.12 > current_profit >= 0.1:
            if (last_candle['r_480'] > -1.1):
                return True, f'exit_{mode_name}_w_10_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 79.0):
                return True, f'exit_{mode_name}_w_10_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 44.0):
                return True, f'exit_{mode_name}_w_10_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 75.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_10_4'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_10_5'
        elif 0.2 > current_profit >= 0.12:
            if (last_candle['r_480'] > -0.4):
                return True, f'exit_{mode_name}_w_11_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 80.0):
                return True, f'exit_{mode_name}_w_11_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 42.0):
                return True, f'exit_{mode_name}_w_11_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 76.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_11_4'
            elif (last_candle['r_14'] >= -0.5) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_11_5'
        elif current_profit >= 0.2:
            if (last_candle['r_480'] > -0.2):
                return True, f'exit_{mode_name}_w_12_1'
            elif (last_candle['r_14'] >= -1.0) and (last_candle['rsi_14'] > 81.0):
                return True, f'exit_{mode_name}_w_12_2'
            elif (last_candle['r_14'] >= -2.0) and (last_candle['rsi_14'] < 40.0):
                return True, f'exit_{mode_name}_w_12_3'
            elif (last_candle['r_14'] >= -5.0) and (last_candle['rsi_14'] > 77.0) and (last_candle['r_480_1h'] > -25.0):
                return True, f'exit_{mode_name}_w_12_4'
            elif (last_candle['r_14'] >= -0.1) and (last_candle['cti_20'] > 0.95):
                return True, f'exit_{mode_name}_w_12_5'

        return False, None

    def exit_stoploss(self, mode_name: str, current_rate: float, current_profit: float, max_profit:float, max_loss:float, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade: 'Trade', current_time: 'datetime', buy_tag) -> tuple:
        is_backtest = self.dp.runmode.value == 'backtest'
        rel_profit = ((current_rate - trade.open_rate) / trade.open_rate)

        # Stoploss doom
        if (
                (self.stop_thresholds[10])
                and (rel_profit < self.stop_thresholds[0])
        ):
            return True, f'exit_{mode_name}_stoploss_doom'

        # Under & near EMA200, local uptrend move
        if (
                (self.stop_thresholds[12])
                and (rel_profit < self.stop_thresholds[2])
                and (last_candle['close'] < last_candle['ema_200'])
                and (((last_candle['ema_200'] - last_candle['close']) / last_candle['close']) < self.stop_thresholds[6])
                and (last_candle['rsi_14'] > previous_candle_1['rsi_14'])
                and (last_candle['rsi_14'] > (last_candle['rsi_14_1h'] + self.stop_thresholds[8]))
                and (current_time - timedelta(minutes=self.stop_thresholds[4]) > trade.open_date_utc)
        ):
            return True, f'exit_{mode_name}_stoploss_u_e'

        return False, None

    def calc_total_profit(self, trade: 'Trade', filled_entries: 'Orders', filled_exits: 'Orders', exit_rate: float) -> tuple:
        """
        Calculates the absolute profit for open trades.

        :param trade: trade object.
        :param filled_entries: Filled entries list.
        :param filled_exits: Filled exits list.
        :param exit_rate: The exit rate.
        :return tuple: The total profit in stake, ratio, ratio based on current stake, and ratio based on the first entry stake.
        """
        total_stake = 0.0
        total_profit = 0.0
        for entry in filled_entries:
            entry_stake = entry.filled * entry.average * (1 + trade.fee_open)
            total_stake += entry_stake
            total_profit -= entry_stake
        for exit in filled_exits:
            exit_stake = exit.filled * exit.average * (1 - trade.fee_close)
            total_profit += exit_stake
        current_stake = (trade.amount * exit_rate * (1 - trade.fee_close))
        total_profit += current_stake
        total_profit_ratio = (total_profit / total_stake)
        current_profit_ratio = (total_profit / current_stake)
        init_profit_ratio = (total_profit / filled_entries[0].cost)
        return total_profit, total_profit_ratio, current_profit_ratio, init_profit_ratio

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

        filled_entries = trade.select_filled_orders(trade.entry_side)
        filled_exits = trade.select_filled_orders(trade.exit_side)

        profit_stake = 0.0
        profit_ratio = 0.0
        profit_current_stake_ratio = 0.0
        profit_init_ratio = 0.0
        if (trade.realized_profit != 0.0):
            profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio = self.calc_total_profit(trade, filled_entries, filled_exits, current_rate)
        else:
            profit_ratio = current_profit
            profit_current_stake_ratio = current_profit
            profit_init_ratio = current_profit

        max_profit = ((trade.max_rate - trade.open_rate) / trade.open_rate)
        max_loss = ((trade.open_rate - trade.min_rate) / trade.min_rate)

        count_of_entries = len(filled_entries)
        if count_of_entries > 1:
            initial_entry = filled_entries[0]
            if (initial_entry is not None and initial_entry.average is not None):
                max_profit = ((trade.max_rate - initial_entry.average) / initial_entry.average)
                max_loss = ((initial_entry.average - trade.min_rate) / trade.min_rate)

        # Normal mode
        if any(c in self.normal_mode_tags for c in enter_tags):
            sell, signal_name = self.exit_normal(pair, current_rate, profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {enter_tag})"

        # Pump mode
        if any(c in self.pump_mode_tags for c in enter_tags):
            sell, signal_name = self.exit_pump(pair, current_rate, profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {enter_tag})"

        # Quick mode
        if any(c in self.quick_mode_tags for c in enter_tags):
            sell, signal_name = self.exit_quick(pair, current_rate, profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {enter_tag})"

        # Rebuy mode
        if all(c in self.rebuy_mode_tags for c in enter_tags):
            sell, signal_name = self.exit_rebuy(pair, current_rate, profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {enter_tag})"

        # Long mode
        if any(c in self.long_mode_tags for c in enter_tags):
            sell, signal_name = self.exit_long(pair, current_rate, profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {enter_tag})"

        # Trades not opened by X2
        if not any(c in (self.normal_mode_tags + self.pump_mode_tags + self.quick_mode_tags + self.rebuy_mode_tags + self.long_mode_tags) for c in enter_tags):
            # use normal mode for such trades
            sell, signal_name = self.exit_normal(pair, current_rate, profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio, max_profit, max_loss, last_candle, previous_candle_1, previous_candle_2, previous_candle_3, previous_candle_4, previous_candle_5, trade, current_time, enter_tags)
            if sell and (signal_name is not None):
                return f"{signal_name} ( {enter_tag})"

        return None

    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float,
                            proposed_stake: float, min_stake: Optional[float], max_stake: float,
                            leverage: float, entry_tag: Optional[str], side: str,
                            **kwargs) -> float:
        if (self.position_adjustment_enable == True):
            enter_tags = entry_tag.split()
            # Rebuy mode
            if all(c in self.rebuy_mode_tags for c in enter_tags):
                return proposed_stake * self.stake_rebuy_mode_multiplier

        return proposed_stake

    def adjust_trade_position(self, trade: Trade, current_time: datetime,
                          current_rate: float, current_profit: float,
                          min_stake: Optional[float], max_stake: float,
                          current_entry_rate: float, current_exit_rate: float,
                          current_entry_profit: float, current_exit_profit: float,
                          **kwargs) -> Optional[float]:
        if (self.position_adjustment_enable == False):
            return None

        enter_tag = 'empty'
        if hasattr(trade, 'enter_tag') and trade.enter_tag is not None:
            enter_tag = trade.enter_tag
        enter_tags = enter_tag.split()

        # Grinding
        if (any(c in (self.normal_mode_tags + self.pump_mode_tags  + self.quick_mode_tags + self.long_mode_tags) for c in enter_tags)
            or not any(c in (self.normal_mode_tags + self.pump_mode_tags + self.quick_mode_tags + self.rebuy_mode_tags + self.long_mode_tags) for c in enter_tags)):
            return self.grind_adjust_trade_position(trade, current_time,
                                                         current_rate, current_profit,
                                                         min_stake, max_stake,
                                                         current_entry_rate, current_exit_rate,
                                                         current_entry_profit, current_exit_profit
                                                         )

        # Rebuy mode
        if all(c in self.rebuy_mode_tags for c in enter_tags):
            return self.rebuy_adjust_trade_position(trade, current_time,
                                                         current_rate, current_profit,
                                                         min_stake, max_stake,
                                                         current_entry_rate, current_exit_rate,
                                                         current_entry_profit, current_exit_profit
                                                         )

        return None

    def grind_adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: Optional[float], max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> Optional[float]:
        is_backtest = self.dp.runmode.value == 'backtest'
        if (self.grinding_enable) and (trade.open_date_utc.replace(tzinfo=None) >= datetime(2022, 8, 1) or is_backtest):
            dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
            if(len(dataframe) < 2):
                return None
            last_candle = dataframe.iloc[-1].squeeze()
            previous_candle = dataframe.iloc[-2].squeeze()

            filled_orders = trade.select_filled_orders()
            filled_entries = trade.select_filled_orders(trade.entry_side)
            filled_exits = trade.select_filled_orders(trade.exit_side)
            count_of_entries = trade.nr_of_successful_entries
            count_of_exits = trade.nr_of_successful_exits

            if (count_of_entries == 0):
                return None

            exit_rate = current_rate
            if self.dp.runmode.value in ('live', 'dry_run'):
                ticker = self.dp.ticker(trade.pair)
                if ('bid' in ticker) and ('ask' in ticker):
                    if (trade.is_short):
                        if (self.config['exit_pricing']['price_side'] in ["ask", "other"]):
                            exit_rate = ticker['ask']
                    else:
                        if (self.config['exit_pricing']['price_side'] in ["bid", "other"]):
                            exit_rate = ticker['bid']

            profit_stake, profit_ratio, profit_current_stake_ratio, profit_init_ratio = self.calc_total_profit(trade, filled_entries, filled_exits, exit_rate)

            slice_amount = filled_entries[0].cost
            slice_profit = (exit_rate - filled_orders[-1].average) / filled_orders[-1].average
            slice_profit_entry = (exit_rate - filled_entries[-1].average) / filled_entries[-1].average
            slice_profit_exit = ((exit_rate - filled_exits[-1].average) / filled_exits[-1].average) if count_of_exits > 0 else 0.0

            current_stake_amount = trade.amount * current_rate

            # Buy
            stake_amount_threshold = slice_amount
            grinding_parts = len(self.grinding_stakes)
            grinding_thresholds = self.grinding_thresholds
            grinding_stakes = self.grinding_stakes
            # Low stakes, on Binance mostly
            if ((slice_amount * self.grinding_stakes[0]) < min_stake):
                if ((slice_amount * self.grinding_stakes_alt_1[0]) < min_stake):
                    grinding_parts = len(self.grinding_stakes_alt_2)
                    grinding_thresholds = self.grinding_thresholds_alt_2
                    grinding_stakes = self.grinding_stakes_alt_2
                else:
                    grinding_parts = len(self.grinding_stakes_alt_1)
                    grinding_thresholds = self.grinding_thresholds_alt_1
                    grinding_stakes = self.grinding_stakes_alt_1
            for i in range(grinding_parts):
                if (current_stake_amount < stake_amount_threshold):
                    if (
                            (profit_current_stake_ratio < grinding_thresholds[i])
                            and
                            (
                                (last_candle['close_max_12'] < (last_candle['close'] * 1.1))
                                and (last_candle['close_max_24'] < (last_candle['close'] * 1.12))
                                and (last_candle['close_max_48'] < (last_candle['close'] * 1.16))
                                and (last_candle['btc_pct_close_max_72_5m'] < 0.04)
                                and (last_candle['btc_pct_close_max_24_5m'] < 0.03)
                            )
                            and
                            (
                                (current_time - timedelta(minutes=30) > filled_entries[-1].order_filled_utc)
                                or (slice_profit_entry < -0.01)
                            )
                            and
                            (
                                (
                                    (last_candle['rsi_14'] < 36.0)
                                    and (last_candle['rsi_3'] > 5.0)
                                    and (last_candle['ema_26'] > last_candle['ema_12'])
                                    and ((last_candle['ema_26'] - last_candle['ema_12']) > (last_candle['open'] * 0.005))
                                    and ((previous_candle['ema_26'] - previous_candle['ema_12']) > (last_candle['open'] / 100.0))
                                    and (last_candle['rsi_3_1h'] > 10.0)
                                )
                                or
                                (
                                    (last_candle['rsi_14'] < 40.0)
                                    and (last_candle['rsi_3'] > 5.0)
                                    and (last_candle['close'] < (last_candle['ema_12'] * 0.99))
                                    and (last_candle['rsi_3_1h'] > 10.0)
                                    and (last_candle['not_downtrend_1h'])
                                    and (last_candle['not_downtrend_4h'])
                                )
                                or
                                (
                                    (last_candle['rsi_14'] < 36.0)
                                    and (last_candle['rsi_3'] > 5.0)
                                    and (last_candle['close'] < (last_candle['bb20_2_low'] * 0.996))
                                    and (last_candle['rsi_3_1h'] > 25.0)
                                    and (last_candle['not_downtrend_1h'])
                                    and (last_candle['not_downtrend_4h'])
                                )
                                or
                                (
                                    (last_candle['rsi_14'] < 32.0)
                                    and (last_candle['rsi_3'] > 5.0)
                                    and (last_candle['ha_close'] > last_candle['ha_open'])
                                    and (last_candle['rsi_3_1h'] > 10.0)
                                )
                            )
                    ):
                        buy_amount = slice_amount * grinding_stakes[i]
                        if (buy_amount > max_stake):
                            buy_amount = max_stake
                        if (buy_amount < min_stake):
                            return None
                        self.dp.send_msg(f"Grinding entry [{trade.pair}] | Rate: {current_rate} | Stake amount: {buy_amount} | Profit (stake): {profit_stake} | Profit: {(profit_ratio * 100.0):.2f}%")
                        return buy_amount
                stake_amount_threshold += slice_amount * grinding_stakes[i]

            # Sell

            if (count_of_entries > 1):
                count_of_full_exits = 0
                for exit_order in filled_exits:
                    if ((exit_order.remaining * exit_rate) < min_stake):
                        count_of_full_exits += 1
                num_buys = 0
                num_sells = 0
                for order in reversed(filled_orders):
                    if (order.ft_order_side == "buy"):
                        num_buys += 1
                    elif (order.ft_order_side == "sell"):
                        if ((order.remaining * exit_rate) < min_stake):
                            num_sells += 1
                    # patial fills on exits
                    if (num_buys == num_sells) and (order.ft_order_side == "sell"):
                        sell_amount = order.remaining * exit_rate
                        grind_profit = (exit_rate - order.average) / order.average
                        if (sell_amount > min_stake):
                            # Test if it's the last exit. Normal exit with partial fill
                            if ((trade.stake_amount - sell_amount) > min_stake):
                                if (
                                        (grind_profit > 0.01)
                                ):
                                    self.dp.send_msg(f"Grinding exit (remaining) [{trade.pair}] | Rate: {exit_rate} | Stake amount: {sell_amount} | Coin amount: {order.remaining} | Profit (stake): {profit_stake} | Profit: {(profit_ratio * 100.0):.2f}% | Grind profit: {(grind_profit * 100.0):.2f}%")
                                    return -sell_amount
                                else:
                                    # Current order is sell partial fill
                                    return None
                    elif (count_of_entries > (count_of_full_exits + 1)) and (num_buys > num_sells) and (order.ft_order_side == "buy"):
                        buy_order = order
                        grind_profit = (exit_rate - buy_order.average) / buy_order.average
                        if (
                                (grind_profit > 0.012)
                        ):
                            sell_amount = buy_order.filled * exit_rate
                            self.dp.send_msg(f"Grinding exit [{trade.pair}] | Rate: {exit_rate} | Stake amount: {sell_amount}| Coin amount: {buy_order.filled} | Profit (stake): {profit_stake} | Profit: {(profit_ratio * 100.0):.2f}% | Grind profit: {(grind_profit * 100.0):.2f}%")
                            return -sell_amount
                        break

        return None

    def rebuy_adjust_trade_position(self, trade: Trade, current_time: datetime,
                              current_rate: float, current_profit: float,
                              min_stake: Optional[float], max_stake: float,
                              current_entry_rate: float, current_exit_rate: float,
                              current_entry_profit: float, current_exit_profit: float,
                              **kwargs) -> Optional[float]:
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        if(len(dataframe) < 2):
            return None
        last_candle = dataframe.iloc[-1].squeeze()
        previous_candle = dataframe.iloc[-2].squeeze()

        filled_orders = trade.select_filled_orders()
        filled_entries = trade.select_filled_orders(trade.entry_side)
        filled_exits = trade.select_filled_orders(trade.exit_side)
        count_of_entries = trade.nr_of_successful_entries
        count_of_exits = trade.nr_of_successful_exits

        if (count_of_entries == 0):
            return None

        is_rebuy = False

        if (0 < count_of_entries <= self.pa_rebuy_mode_max):
            if (
                    (current_profit < self.pa_rebuy_mode_pcts[count_of_entries - 1])
                    and (
                        (last_candle['rsi_3'] > 10.0)
                        and (last_candle['rsi_14'] < 40.0)
                        and (last_candle['rsi_3_1h'] > 10.0)
                        and (last_candle['close_max_48'] < (last_candle['close'] * 1.1))
                        and (last_candle['btc_pct_close_max_72_5m'] < 0.03)
                    )
            ):
                is_rebuy = True

        if is_rebuy:
            # This returns first order stake size
            stake_amount = filled_entries[0].cost
            print('rebuying..')
            stake_amount = stake_amount * self.pa_rebuy_mode_multi[count_of_entries - 1]
            return stake_amount

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

        # EMA
        informative_1d['ema_200'] = ta.EMA(informative_1d, timeperiod=200)

        # CTI
        informative_1d['cti_20'] = pta.cti(informative_1d["close"], length=20)

        # Pivots
        informative_1d['pivot'], informative_1d['res1'], informative_1d['res2'], informative_1d['res3'], informative_1d['sup1'], informative_1d['sup2'], informative_1d['sup3'] = pivot_points(informative_1d, mode='fibonacci')

        # S/R
        res_series = informative_1d['high'].rolling(window = 5, center=True).apply(lambda row: is_resistance(row), raw=True).shift(2)
        sup_series = informative_1d['low'].rolling(window = 5, center=True).apply(lambda row: is_support(row), raw=True).shift(2)
        informative_1d['res_level'] = Series(np.where(res_series, np.where(informative_1d['close'] > informative_1d['open'], informative_1d['close'], informative_1d['open']), float('NaN'))).ffill()
        informative_1d['res_hlevel'] = Series(np.where(res_series, informative_1d['high'], float('NaN'))).ffill()
        informative_1d['sup_level'] = Series(np.where(sup_series, np.where(informative_1d['close'] < informative_1d['open'], informative_1d['close'], informative_1d['open']), float('NaN'))).ffill()

        # Downtrend checks
        informative_1d['is_downtrend_3'] = ((informative_1d['close'] < informative_1d['open']) & (informative_1d['close'].shift(1) < informative_1d['open'].shift(1)) & (informative_1d['close'].shift(2) < informative_1d['open'].shift(2)))

        informative_1d['is_downtrend_5'] = ((informative_1d['close'] < informative_1d['open']) & (informative_1d['close'].shift(1) < informative_1d['open'].shift(1)) & (informative_1d['close'].shift(2) < informative_1d['open'].shift(2)) & (informative_1d['close'].shift(3) < informative_1d['open'].shift(3)) & (informative_1d['close'].shift(4) < informative_1d['open'].shift(4)))

        # Wicks
        informative_1d['top_wick_pct'] = ((informative_1d['high'] - np.maximum(informative_1d['open'], informative_1d['close'])) / np.maximum(informative_1d['open'], informative_1d['close']))

        # Candle change
        informative_1d['change_pct'] = (informative_1d['close'] - informative_1d['open']) / informative_1d['open']

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

        informative_4h['is_downtrend_3'] = ((informative_4h['close'] < informative_4h['open']) & (informative_4h['close'].shift(1) < informative_4h['open'].shift(1)) & (informative_4h['close'].shift(2) < informative_4h['open'].shift(2)))

        # Wicks
        informative_4h['top_wick_pct'] = ((informative_4h['high'] - np.maximum(informative_4h['open'], informative_4h['close'])) / np.maximum(informative_4h['open'], informative_4h['close']))

        # Candle change
        informative_4h['change_pct'] = (informative_4h['close'] - informative_4h['open']) / informative_4h['open']

        # Max highs
        informative_4h['high_max_3'] = informative_4h['high'].rolling(3).max()
        informative_4h['high_max_12'] = informative_4h['high'].rolling(12).max()
        informative_4h['high_max_24'] = informative_4h['high'].rolling(24).max()
        informative_4h['high_max_36'] = informative_4h['high'].rolling(36).max()
        informative_4h['high_max_48'] = informative_4h['high'].rolling(48).max()

        informative_4h['pct_change_high_max_1_12'] = (informative_4h['high'] - informative_4h['high_max_12']) / informative_4h['high_max_12']
        informative_4h['pct_change_high_max_3_12'] = (informative_4h['high_max_3'] - informative_4h['high_max_12']) / informative_4h['high_max_12']
        informative_4h['pct_change_high_max_3_24'] = (informative_4h['high_max_3'] - informative_4h['high_max_24']) / informative_4h['high_max_24']
        informative_4h['pct_change_high_max_3_36'] = (informative_4h['high_max_3'] - informative_4h['high_max_36']) / informative_4h['high_max_36']
        informative_4h['pct_change_high_max_3_48'] = (informative_4h['high_max_3'] - informative_4h['high_max_48']) / informative_4h['high_max_48']

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
        informative_1h['rsi_3'] = ta.RSI(informative_1h, timeperiod=3)
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

        informative_1h['bb20_2_width'] = ((informative_1h['bb20_2_upp'] - informative_1h['bb20_2_low']) / informative_1h['bb20_2_mid'])

        # Williams %R
        informative_1h['r_14'] = williams_r(informative_1h, period=14)
        informative_1h['r_96'] = williams_r(informative_1h, period=96)
        informative_1h['r_480'] = williams_r(informative_1h, period=480)

        # CTI
        informative_1h['cti_20'] = pta.cti(informative_1h["close"], length=20)
        informative_1h['cti_40'] = pta.cti(informative_1h["close"], length=40)

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
        informative_1h['high_max_36'] = informative_1h['high'].rolling(36).max()
        informative_1h['high_max_48'] = informative_1h['high'].rolling(48).max()

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
        informative_15m['rsi_3'] = ta.RSI(informative_15m, timeperiod=3)
        informative_15m['rsi_14'] = ta.RSI(informative_15m, timeperiod=14)

        # EMA
        informative_15m['ema_12'] = ta.EMA(informative_15m, timeperiod=12)
        informative_15m['ema_26'] = ta.EMA(informative_15m, timeperiod=26)

        # SMA
        informative_15m['sma_200'] = ta.SMA(informative_15m, timeperiod=200)

        # CTI
        informative_15m['cti_20'] = pta.cti(informative_15m["close"], length=20)

        # Downtrend check
        informative_15m['not_downtrend'] = ((informative_15m['close'] > informative_15m['open']) | (informative_15m['close'].shift(1) > informative_15m['open'].shift(1)) | (informative_15m['close'].shift(2) > informative_15m['open'].shift(2)) | (informative_15m['rsi_14'] > 50.0) | (informative_15m['rsi_3'] > 25.0))

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
        dataframe['rsi_3'] = ta.RSI(dataframe, timeperiod=3)
        dataframe['rsi_14'] = ta.RSI(dataframe, timeperiod=14)

        # EMA
        dataframe['ema_12'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['ema_16'] = ta.EMA(dataframe, timeperiod=16)
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

        # CTI
        dataframe['cti_20'] = pta.cti(dataframe["close"], length=20)

        # Heiken Ashi
        heikinashi = qtpylib.heikinashi(dataframe)
        dataframe['ha_open'] = heikinashi['open']
        dataframe['ha_close'] = heikinashi['close']
        dataframe['ha_high'] = heikinashi['high']
        dataframe['ha_low'] = heikinashi['low']

        # Dip protection
        dataframe['tpct_change_0']   = top_percent_change(self, dataframe, 0)
        dataframe['tpct_change_2']   = top_percent_change(self, dataframe, 2)

        # Close max
        dataframe['close_max_12'] = dataframe['close'].rolling(12).max()
        dataframe['close_max_24'] = dataframe['close'].rolling(24).max()
        dataframe['close_max_48'] = dataframe['close'].rolling(48).max()

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

        # the number of free slots
        current_free_slots = self.config["max_open_trades"] - len(LocalTrade.get_trades_proxy(is_open=True))

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
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 85.0)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 85.0)
                    item_buy_logic.append(dataframe['cti_20_1d'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1d'] < 85.0)
                    item_buy_logic.append(dataframe['r_14_1h'] < -25.0)
                    item_buy_logic.append(dataframe['r_14_4h'] < -25.0)

                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.08)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.2)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_14_1h'] < 30.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['rsi_14_4h'] < 30.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_14_1h'] < 30.0)
                                          | (dataframe['rsi_14_4h'] < 30.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_14_1h'] < 30.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['rsi_14_4h'] < 30.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_14_1h'] < 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 30.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_14_1h'] < 40.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['rsi_14_4h'] < 40.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_14_1h'] < 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 30.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['hl_pct_change_48_1h'] < 0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_14_4h'] < 30.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.07)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.5))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.08)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.5))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.08)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append(((dataframe['not_downtrend_1h'])
                                           & (dataframe['not_downtrend_4h']))
                                          | (dataframe['high_max_24_4h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.12))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.06)
                                          | (dataframe['change_pct_4h'] > -0.06)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'].shift(48) < 80.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.18))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.1)
                                          | (dataframe['top_wick_pct_1d'] < 0.1)
                                          | (dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.1)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.1)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.02)
                                          | (dataframe['change_pct_4h'] > -0.02)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'].shift(48) < 70.0))
                    item_buy_logic.append((dataframe['top_wick_pct_1h'] < (abs(dataframe['change_pct_1h']) * 6.0))
                                          | (dataframe['cti_20_1h'] < 0.5))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.26)
                                          | (dataframe['top_wick_pct_4h'] < 0.26)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.26)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.16)
                                          | (dataframe['top_wick_pct_4h'] < 0.08)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_14_1h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.16)
                                          | (dataframe['top_wick_pct_4h'] < 0.08)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.12)))
                    item_buy_logic.append((dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.3))
                                          | (dataframe['hl_pct_change_24_1h'] < 0.75))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.06)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['high_max_6_1h'] < (dataframe['close'] * 1.25))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.02))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.999))

                # Condition #2 - Normal mode bull.
                if index == 2:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_12'] < (dataframe['close'] * 1.16))
                    item_buy_logic.append(dataframe['close_max_24'] < (dataframe['close'] * 1.24))
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))
                    item_buy_logic.append(dataframe['hl_pct_change_24_1h'] < 0.75)

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 85.0)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 85.0)
                    item_buy_logic.append(dataframe['cti_20_1d'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1d'] < 85.0)
                    item_buy_logic.append(dataframe['r_14_1h'] < -25.0)
                    item_buy_logic.append(dataframe['r_14_4h'] < -25.0)

                    item_buy_logic.append(((dataframe['not_downtrend_1h'])
                                           & (dataframe['not_downtrend_4h']))
                                          | (dataframe['high_max_24_4h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.25)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 16.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['r_480_4h'] < -30.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 16.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['r_480_4h'] < -30.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.25)
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_14_1h'] < 40.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['rsi_14_4h'] < 40.0)
                                          | (dataframe['cti_20_1d'] < -0.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1d'] < -0.75)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5))
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 6.0))
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 6.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.16)
                                          | (dataframe['top_wick_pct_4h'] < 0.08)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_14_1h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.16)
                                          | (dataframe['top_wick_pct_4h'] < 0.08)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.12)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.06)
                                          | (dataframe['top_wick_pct_4h'] < 0.06)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close_max_48'] < (dataframe['close'] * 1.12)))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.06)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['high_max_6_1h'] < (dataframe['close'] * 1.25))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * 0.06))
                    item_buy_logic.append(dataframe['close_delta'].gt(dataframe['close'] * 0.02))
                    item_buy_logic.append(dataframe['bb40_2_tail'].lt(dataframe['bb40_2_delta'] * 0.2))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))

                # Condition #3 - Normal mode bull.
                if index == 3:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.26))

                    item_buy_logic.append(dataframe['ema_12_1h'] > dataframe['ema_200_1h'])

                    item_buy_logic.append(dataframe['ema_12_4h'] > dataframe['ema_200_4h'])

                    item_buy_logic.append(dataframe['rsi_14_4h'] < 75.0)
                    item_buy_logic.append(dataframe['rsi_14_1d'] < 85.0)

                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.85)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_1h'] > 16.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 16.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['is_downtrend_3_1d'] == False)
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.07)))
                    item_buy_logic.append((dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['close_max_48'] < (dataframe['close'] * 1.16))
                                          | (dataframe['hl_pct_change_24_1h'] < 0.4)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.06)
                                          | (dataframe['change_pct_1d'].shift(288) > -0.06)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['hl_pct_change_24_1h'] < 0.5))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.06)
                                          | (dataframe['change_pct_4h'] > -0.06)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'].shift(48) < 80.0))
                    item_buy_logic.append((dataframe['change_pct_1d'].shift(288) < 0.02)
                                          | (dataframe['change_pct_1d'] > -0.06)
                                          | (dataframe['cti_20_1d'] < 0.85)
                                          | (dataframe['rsi_14_1d'].shift(288) < 70.0))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.05)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | (dataframe['rsi_14_1d'] < 65.0))
                    item_buy_logic.append((dataframe['rsi_3'] > 20.0)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.8))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))

                    # Logic
                    item_buy_logic.append(dataframe['rsi_14'] < 36.0)
                    item_buy_logic.append(dataframe['ha_close'] > dataframe['ha_open'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.018))

                # Condition #4 - Normal mode bull.
                if index == 4:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_12'] < (dataframe['close'] * 1.16))
                    item_buy_logic.append(dataframe['close_max_24'] < (dataframe['close'] * 1.24))
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))
                    item_buy_logic.append(dataframe['high_max_12_1h'] < (dataframe['close'] * 1.5))
                    item_buy_logic.append(dataframe['hl_pct_change_12_1h'] < 0.75)

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 85.0)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 85.0)
                    item_buy_logic.append(dataframe['cti_20_1d'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_1d'] < 85.0)

                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.5))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 16.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    # BNX
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04))
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05))
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 15.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04))
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['is_downtrend_3_1h'] == False)
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.5))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.5))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['r_480_4h'] < -30.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.3))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 16.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < 0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append(((dataframe['not_downtrend_1h'])
                                           & (dataframe['not_downtrend_4h']))
                                          | (dataframe['high_max_24_4h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 8.0))
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.02)
                                          | (dataframe['change_pct_4h'] > -0.02)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'].shift(48) < 70.0))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.7)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 8.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.06)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['high_max_6_1h'] < (dataframe['close'] * 1.25))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.018))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.996))

                # Condition #5 - Normal mode bull.
                if index == 5:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)

                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.32)
                                          | (dataframe['top_wick_pct_4h'] < 0.16)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.3)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < -0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['cti_20_1h'] < 0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.9)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < -0.75)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.25))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.9)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.25))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.25))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.25))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.08)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.9)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.25))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.08)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.07)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.25))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.08)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.09)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.25))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.1)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 16.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.09)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.9)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['is_downtrend_3_1h'] == False)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.07)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1d'] < -0.75)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append(((dataframe['not_downtrend_1h'])
                                           & (dataframe['not_downtrend_4h']))
                                          | (dataframe['high_max_24_4h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.2))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.09)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.9)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close_max_48'] < (dataframe['close'] * 1.2))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 5.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['r_14_4h'] < -25.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['hl_pct_change_24_1h'] < 0.5))
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 8.0))
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.06)
                                          | (dataframe['change_pct_4h'] > -0.06)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'].shift(48) < 80.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.18))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.08)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.1)
                                          | (dataframe['top_wick_pct_4h'] < 0.03)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close_max_12'] < (dataframe['close'] * 1.12)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.16)
                                          | (dataframe['top_wick_pct_4h'] < 0.08)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.12)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 8.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.1)
                                          | (dataframe['top_wick_pct_1d'] < 0.1)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 80.0))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['rsi_14'] < 36.0)

                # Condition #6 - Normal mode bull.
                if index == 6:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_12'] < (dataframe['close'] * 1.2))
                    item_buy_logic.append(dataframe['hl_pct_change_24_1h'] < 0.75)

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.5)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.75)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 85.0)

                    item_buy_logic.append(((dataframe['not_downtrend_1h'])
                                           & (dataframe['not_downtrend_4h']))
                                          | (dataframe['high_max_24_4h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.02)
                                          | (dataframe['top_wick_pct_1d'] < 0.06)
                                          | (dataframe['change_pct_1d'].shift(288) < 0.02)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.3))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.9))
                                          | (dataframe['rsi_3'] > 20.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.9)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.9)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.9)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.9)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close_max_12'] < (dataframe['close'] * 1.12))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close_max_12'] < (dataframe['close'] * 1.12))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close_max_12'] < (dataframe['close'] * 1.16))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.9)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close_max_12'] < (dataframe['close'] * 1.12))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['close_max_12'] < (dataframe['close'] * 1.12))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 5.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.89)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_14_1h'] < 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close_max_12'] < (dataframe['close'] * 1.12))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close_max_48'] < (dataframe['close'] * 1.26))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.86)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.9)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['r_480_4h'] > -95.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.9)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_1h'] < (dataframe['close'] * 1.3))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['r_480_1h'] > -90.0)
                                          | (dataframe['r_480_4h'] > -90.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close_max_12'] < (dataframe['close'] * 1.12))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 8.0))
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.1)
                                          | (dataframe['top_wick_pct_1d'] < 0.1)
                                          | (dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['rsi_3'] > 20.0)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.8))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_26'] * 0.94))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.996))

                # Condition #21 - Pump mode bull.
                if index == 21:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_12'] < (dataframe['close'] * 1.16))
                    item_buy_logic.append(dataframe['close_max_24'] < (dataframe['close'] * 1.24))
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))

                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                    item_buy_logic.append(dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))

                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.06)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    # CHZ
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_14_1h'] < 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.75)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.9)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['r_14_4h'] > -50.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.9)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.08)
                                          | (dataframe['top_wick_pct_4h'] < 0.08)
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_14_1h'] > 60.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['rsi_14_15m'] > 30.0)
                                          | (dataframe['cti_20_1h'] < -0.9)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < -0.75)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 10.0)
                                          | (dataframe['rsi_14_1h'] < 10.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.07)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 5.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['r_14_4h'] < -25.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.06)
                                          | (dataframe['change_pct_1d'].shift(288) > -0.06)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['close'] < (dataframe['ema_200_4h'] * 1.1)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['hl_pct_change_24_1h'] < 0.5))
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 8.0))
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['change_pct_1d'].shift(288) < 0.02)
                                          | (dataframe['change_pct_1d'] > -0.06)
                                          | (dataframe['cti_20_1d'] < 0.85)
                                          | (dataframe['rsi_14_1d'].shift(288) < 70.0))
                    item_buy_logic.append((dataframe['rsi_3'] > 20.0)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.8))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.016))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['rsi_14'] < 36.0)

                # Condition #22 - Pump mode bull.
                if index == 22:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_12'] < (dataframe['close'] * 1.2))
                    item_buy_logic.append(dataframe['close_max_24'] < (dataframe['close'] * 1.24))
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))
                    item_buy_logic.append(dataframe['high_max_24_1h'] < (dataframe['close'] * 1.5))

                    item_buy_logic.append(dataframe['rsi_14_1h'] < 85.0)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.9)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 85.0)

                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(96))
                    item_buy_logic.append(dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                    item_buy_logic.append(dataframe['sma_200_1h'] > dataframe['sma_200_1h'].shift(24))

                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.02)
                                          | (dataframe['top_wick_pct_1d'] < 0.06)
                                          | (dataframe['change_pct_1d'].shift(288) < 0.02)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.92)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.93)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < 0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.75)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.92)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.75)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.75)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.9)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.93)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.93)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.93)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < 0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.9)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.75)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.92)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.93)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.95)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.94)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.96)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_16'] * 0.92)))
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 8.0))
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.1)
                                          | (dataframe['top_wick_pct_4h'] < 0.03)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.05)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | (dataframe['rsi_14_1d'] < 65.0))
                    item_buy_logic.append((dataframe['rsi_3'] > 20.0)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.8))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_16'] * 0.968))
                    item_buy_logic.append(dataframe['cti_20'] < -0.9)
                    item_buy_logic.append(dataframe['rsi_14'] < 50.0)

                # Condition #41 - Quick mode bull.
                if index == 41:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_12'] < (dataframe['close'] * 1.2))
                    item_buy_logic.append(dataframe['close_max_24'] < (dataframe['close'] * 1.24))
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))
                    item_buy_logic.append(dataframe['high_max_24_1h'] < (dataframe['close'] * 1.5))
                    item_buy_logic.append(dataframe['hl_pct_change_12_1h'] < 0.5)
                    item_buy_logic.append(dataframe['hl_pct_change_24_1h'] < 0.75)
                    item_buy_logic.append(dataframe['hl_pct_change_48_1h'] < 0.9)

                    # pump and now started dumping, still high
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.05)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['hl_pct_change_48_1h'] < 0.4))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.16)
                                          | (dataframe['top_wick_pct_1d'] < 0.1)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.06)
                                          | (dataframe['top_wick_pct_4h'] < 0.06)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.02)
                                          | (dataframe['top_wick_pct_1d'] < 0.06)
                                          | (dataframe['change_pct_1d'].shift(288) < 0.12)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.06)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.06)
                                          | (dataframe['cti_20_4h'] < 0.5))
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.02)
                                          | (dataframe['cti_20_4h'] < 0.85)
                                          | (dataframe['cti_20_4h'].shift(48) < 0.85)
                                          | (dataframe['rsi_14_4h'].shift(48) < 70.0))
                    item_buy_logic.append((dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.9)
                                          | (dataframe['rsi_14_1d'] < 75.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.75)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.75)
                                          | (dataframe['cti_20_1d'] < -0.8))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.75))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < 0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.75))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['r_14_4h'] < -30.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.5))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < 0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0))
                    item_buy_logic.append((dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['hl_pct_change_48_1h'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.3)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['high_max_48_1h'] < (dataframe['close'] * 1.3)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.8))
                    item_buy_logic.append((dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.75)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < 0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < -0.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close_max_12'] < (dataframe['close'] * 1.12)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.06)
                                          | (dataframe['change_pct_1d'].shift(288) > -0.06)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['close'] < (dataframe['ema_200_4h'] * 1.1)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < -0.75)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['r_480_1h'] > -95.0)
                                          | (dataframe['r_480_4h'] > -95.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 6.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['r_480_1h'] > -90.0)
                                          | (dataframe['r_480_4h'] > -90.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * 0.036))
                    item_buy_logic.append(dataframe['close_delta'].gt(dataframe['close'] * 0.02))
                    item_buy_logic.append(dataframe['bb40_2_tail'].lt(dataframe['bb40_2_delta'] * 0.4))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))
                    item_buy_logic.append(dataframe['rsi_14'] < 36.0)

                # Condition #42 - Quick mode bull.
                if index == 42:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_12'] < (dataframe['close'] * 1.2))
                    item_buy_logic.append(dataframe['close_max_24'] < (dataframe['close'] * 1.24))
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))
                    item_buy_logic.append(dataframe['high_max_24_1h'] < (dataframe['close'] * 1.5))
                    item_buy_logic.append(dataframe['hl_pct_change_12_1h'] < 0.5)
                    item_buy_logic.append(dataframe['hl_pct_change_24_1h'] < 0.75)
                    item_buy_logic.append(dataframe['hl_pct_change_48_1h'] < 0.9)

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.8)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 80.0)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.8)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 80.0)

                    item_buy_logic.append(((dataframe['not_downtrend_1h'])
                                           & (dataframe['not_downtrend_4h']))
                                          | (dataframe['high_max_24_4h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 5.0))
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 5.0))
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.1)
                                          | (dataframe['top_wick_pct_1d'] < 0.05)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 80.0))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.1)
                                          | (dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['cti_20_4h'] < 0.5))
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 2.0))
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 80.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.05)))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.16)
                                          | (dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.75)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['rsi_3'] > 20.0)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.8))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 8.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.018))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close'] < (dataframe['bb20_2_low'] * 0.996))
                    item_buy_logic.append(dataframe['rsi_14'] < 40.0)

                # Condition #43 - Quick mode bull.
                if index == 43:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_12'] < (dataframe['close'] * 1.2))
                    item_buy_logic.append(dataframe['close_max_24'] < (dataframe['close'] * 1.24))
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))
                    item_buy_logic.append(dataframe['high_max_24_1h'] < (dataframe['close'] * 1.5))
                    item_buy_logic.append(dataframe['high_max_24_4h'] < (dataframe['close'] * 1.75))
                    item_buy_logic.append(dataframe['hl_pct_change_12_1h'] < 0.5)
                    item_buy_logic.append(dataframe['hl_pct_change_24_1h'] < 0.75)
                    item_buy_logic.append(dataframe['hl_pct_change_48_1h'] < 0.9)

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.8)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 80.0)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.8)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 80.0)

                    item_buy_logic.append(((dataframe['not_downtrend_1h'])
                                           & (dataframe['not_downtrend_4h']))
                                          | (dataframe['high_max_24_4h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 5.0))
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 5.0))
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.1)
                                          | (dataframe['top_wick_pct_4h'] < 0.05)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.16)
                                          | (dataframe['top_wick_pct_4h'] < 0.08)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.06)
                                          | (dataframe['change_pct_1d'].shift(288) < 0.1)
                                          | (dataframe['top_wick_pct_1d'].shift(288) < 0.1)
                                          | (dataframe['cti_20_1d'].shift(288) < 0.8)
                                          | (dataframe['rsi_14_1d'].shift(288) < 70.0))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.1)
                                          | (dataframe['top_wick_pct_1d'] < 0.05)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 80.0))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.1)
                                          | (dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['cti_20_4h'] < 0.5))
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 2.0))
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 80.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.12))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.9)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.9)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close_max_12'] < (dataframe['close'] * 1.1))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.89)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.16)
                                          | (dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.75)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.1)
                                          | (dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.9)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.93)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.91)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.92)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close'] < (dataframe['ema_26'] * 0.88)))
                    item_buy_logic.append((dataframe['rsi_3'] > 20.0)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.8))

                    # Logic
                    item_buy_logic.append(dataframe['close'] < (dataframe['ema_26'] * 0.938))
                    item_buy_logic.append(dataframe['cti_20'] < -0.75)
                    item_buy_logic.append(dataframe['r_14'] < -94.0)

                # Condition #44 - Quick mode bull.
                if index == 44:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_12'] < (dataframe['close'] * 1.2))
                    item_buy_logic.append(dataframe['close_max_24'] < (dataframe['close'] * 1.24))
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.3))
                    item_buy_logic.append(dataframe['high_max_24_1h'] < (dataframe['close'] * 1.5))
                    item_buy_logic.append(dataframe['high_max_24_4h'] < (dataframe['close'] * 1.75))
                    item_buy_logic.append(dataframe['hl_pct_change_12_1h'] < 0.5)
                    item_buy_logic.append(dataframe['hl_pct_change_24_1h'] < 0.75)
                    item_buy_logic.append(dataframe['hl_pct_change_48_1h'] < 0.9)

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.8)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 80.0)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.8)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 80.0)

                    item_buy_logic.append(dataframe['close_max_48'] > (dataframe['close'] * 1.1))

                    # pump and now started dumping, still high
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.05)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['hl_pct_change_48_1h'] < 0.4))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.1)
                                          | (dataframe['top_wick_pct_1d'] < 0.1)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.06)
                                          | (dataframe['top_wick_pct_4h'] < 0.06)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.02)
                                          | (dataframe['top_wick_pct_1d'] < 0.06)
                                          | (dataframe['change_pct_1d'].shift(288) < 0.12)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.06)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.06)
                                          | (dataframe['cti_20_4h'] < 0.5))
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.02)
                                          | (dataframe['cti_20_4h'] < 0.85)
                                          | (dataframe['cti_20_4h'].shift(48) < 0.85)
                                          | (dataframe['rsi_14_4h'].shift(48) < 70.0))
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 5.0))
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 5.0))
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.1)
                                          | (dataframe['top_wick_pct_1d'] < 0.05)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 80.0))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.1)
                                          | (dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['cti_20_4h'] < 0.5))
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 2.0))
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 80.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.16)
                                          | (dataframe['top_wick_pct_4h'] < 0.08)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.06)
                                          | (dataframe['change_pct_1d'].shift(288) < 0.1)
                                          | (dataframe['top_wick_pct_1d'].shift(288) < 0.1)
                                          | (dataframe['cti_20_1d'].shift(288) < 0.8)
                                          | (dataframe['rsi_14_1d'].shift(288) < 70.0))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.1)
                                          | (dataframe['change_pct_1d'].shift(288) < 0.1)
                                          | (dataframe['cti_20_1d'].shift(288) < 0.5)
                                          | (dataframe['rsi_14_1d'].shift(288) < 70.0))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.1)
                                          | (dataframe['top_wick_pct_1d'] < 0.05)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['rsi_14_1d'] < 80.0))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.2)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.06)
                                          | (dataframe['top_wick_pct_4h'] < 0.06)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.01)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'].shift(48) < 70.0))
                    item_buy_logic.append((dataframe['top_wick_pct_1h'] < (abs(dataframe['change_pct_1h']) * 3.0))
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.04)
                                          | (dataframe['top_wick_pct_4h'] < 0.06)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.06)
                                          | (dataframe['top_wick_pct_4h'] < 0.06)
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['r_480_1h'] > -90.0)
                                          | (dataframe['r_480_4h'] > -90.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.06)
                                          | (dataframe['top_wick_pct_4h'] < 0.06)
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.08)
                                          | (dataframe['change_pct_1h'].shift(12) < 0.08)
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.06)
                                          | (dataframe['top_wick_pct_4h'] < 0.06)
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.1)
                                          | (dataframe['top_wick_pct_4h'] < 0.06)
                                          | (dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.04)
                                          | (dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 4.0))
                                          | (dataframe['cti_20_4h'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.9)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.08)
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.05)
                                          | (dataframe['top_wick_pct_1d'] < 0.05)
                                          | (dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['is_downtrend_3_4h'] == False)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['close'] < (dataframe['ema_200_4h'] * 1.1)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['is_downtrend_3_1h'] == False)
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 2.0))
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.1)
                                          | (dataframe['top_wick_pct_4h'] < 0.03)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.04)
                                          | (dataframe['top_wick_pct_1d'] < 0.04)
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_14_1h'] < 50.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.8)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.03)
                                          | (dataframe['change_pct_1h'].shift(12) < 0.03)
                                          | (dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 2.0))
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['rsi_3_1h'] > 30.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.06)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < 0.5))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.04)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.04)
                                          | (dataframe['change_pct_4h'] > -0.02)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.06)
                                          | (dataframe['change_pct_1d'].shift(288) < 0.06)
                                          | (dataframe['cti_20_1d'].shift(288) < 0.8)
                                          | (dataframe['rsi_14_1d'].shift(288) < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.04)
                                          | (dataframe['top_wick_pct_4h'] < 0.04)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['rsi_14_4h'] < 50.0))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.16)
                                          | (dataframe['top_wick_pct_1d'] < 0.16)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.16)
                                          | (dataframe['top_wick_pct_1d'] < 0.16)
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.16)
                                          | (dataframe['top_wick_pct_1d'] < 0.16)
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.1)
                                          | (dataframe['top_wick_pct_4h'] < 0.1)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_4h'] < -0.9)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 4.0))
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.08)
                                          | (dataframe['top_wick_pct_4h'] < 0.04)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_4h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0))
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.02)
                                          | (dataframe['change_pct_1h'].shift(12) < 0.04)
                                          | (dataframe['top_wick_pct_1h'].shift(12) < 0.04)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['bb20_2_width_1h'] > 0.18))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_1h'] > 5.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.26)
                                          | (dataframe['top_wick_pct_1d'] < 0.06)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['is_downtrend_3_1d'] == False)
                                          | (dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['high_max_24_4h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.06)
                                          | (dataframe['change_pct_1h'].shift(12) < 0.06)
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 3.0))
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['bb20_2_width_1h'] > 0.18))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['bb20_2_width_1h'] > 0.2))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.2)
                                          | (dataframe['top_wick_pct_1d'] < 0.05)
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1d'] < -0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['bb20_2_width_1h'] > 0.17))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.25)
                                          | (dataframe['top_wick_pct_1d'] < 0.2)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.0))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['r_14'] < -96.0))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 25.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['bb20_2_width_1h'] > 0.16))
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.05)
                                          | (dataframe['top_wick_pct_4h'] < 0.05)
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['bb20_2_width_1h'] > 0.22))
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.1)
                                          | (dataframe['top_wick_pct_1d'] < 0.06)
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.8)
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['bb20_2_width_1h'] > 0.17))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['is_downtrend_3_1d'] == False)
                                          | (dataframe['rsi_3_15m'] > 16.0)
                                          | (dataframe['rsi_3_1h'] > 16.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['bb20_2_width_1h'] > 0.18))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['bb20_2_width_1h'] > 0.16))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['bb20_2_width_1h'] > 0.19))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.06)
                                          | (dataframe['change_pct_4h'] > -0.06)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['rsi_3_1h'] > 12.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['bb20_2_width_1h'] > 0.23))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_14_15m'] < 20.0)
                                          | (dataframe['r_480_1h'] > -90.0)
                                          | (dataframe['r_480_4h'] > -90.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['r_480_4h'] > -90.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_1h'] > 20.0)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['high_max_24_4h'] < (dataframe['close'] * 1.5)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_3_15m'] > 20.0)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['r_480_1h'] > -90.0)
                                          | (dataframe['r_480_4h'] > -90.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['r_480_4h'] > -90.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['bb20_2_width_1h'] > 0.22))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_4h'] < -0.5)
                                          | (dataframe['r_480_4h'] > -90.0)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | (dataframe['bb20_2_width_1h'] > 0.22))
                    item_buy_logic.append((dataframe['change_pct_4h'].shift(48) < 0.16)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.04)
                                          | (dataframe['change_pct_4h'] > -0.02)
                                          | (dataframe['top_wick_pct_4h'] < 0.04)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))

                    # Logic
                    item_buy_logic.append(dataframe['bb20_2_width_1h'] > 0.132)
                    item_buy_logic.append(dataframe['cti_20'] < -0.8)
                    item_buy_logic.append(dataframe['r_14'] < -90.0)

                # Condition #61 - Rebuy mode bull.
                if index == 61:
                    # Protections
                    item_buy_logic.append(current_free_slots >= self.rebuy_mode_min_free_slots)
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_12'] < (dataframe['close'] * 1.12))
                    item_buy_logic.append(dataframe['close_max_24'] < (dataframe['close'] * 1.16))
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.2))
                    item_buy_logic.append(dataframe['high_max_6_1h'] < (dataframe['close'] * 1.24))
                    item_buy_logic.append(dataframe['high_max_12_1h'] < (dataframe['close'] * 1.3))
                    item_buy_logic.append(dataframe['high_max_24_1h'] < (dataframe['close'] * 1.36))
                    item_buy_logic.append(dataframe['hl_pct_change_24_1h'] < 0.5)
                    item_buy_logic.append(dataframe['hl_pct_change_48_1h'] < 0.75)

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.95)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.95)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 85.0)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 85.0)
                    item_buy_logic.append(dataframe['rsi_14_1d'] < 85.0)
                    item_buy_logic.append(dataframe['r_14_1h'] < -25.0)
                    item_buy_logic.append(dataframe['r_14_4h'] < -25.0)

                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)

                    item_buy_logic.append(protections_global_1)
                    item_buy_logic.append(protections_global_2)
                    item_buy_logic.append(protections_global_3)
                    item_buy_logic.append(protections_global_4)
                    item_buy_logic.append(protections_global_5)
                    item_buy_logic.append(protections_global_6)
                    item_buy_logic.append(protections_global_7)
                    item_buy_logic.append(protections_global_8)
                    item_buy_logic.append(protections_global_9)
                    item_buy_logic.append(protections_global_10)

                    item_buy_logic.append(dataframe['not_downtrend_15m'])
                    # current 1h downtrend, downtrend 4h
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(288))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    # current 1h red, overbought 1h, downtrend 1h, downtrend 1h, drop last 2h
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.04)
                                          | (dataframe['cti_20_1h'] < 0.85)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(288))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 1d green, overbought 1d
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.16)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    # current 1d long relative top wick, overbought 1d, current 4h red, drop last 4h
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 5.0))
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['close_max_48'] < (dataframe['close'] * 1.1)))
                    # downtrend 1d, overbought 1d, drop in last 2h
                    item_buy_logic.append((dataframe['is_downtrend_3_1d'] == False)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 1d red with top wick, overbought 1d, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.02)
                                          | (dataframe['top_wick_pct_1d'] < 0.02)
                                          | (dataframe['cti_20_1d'] < 0.85)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 1d green with top wick, downtrend 4h, overbought 4h, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.06)
                                          | (dataframe['top_wick_pct_1d'] < 0.06)
                                          | (dataframe['is_downtrend_3_4h'] == False)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 1h red, overbought 1h, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_1h'] > -0.02)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 4h grered, previous 4h green, overbought 1h, downtrend 1h, downtrend 4h
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.04)
                                          | (dataframe['cti_20_1h'] < 0.85)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(288))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152)))
                    # current 4h red, downtrend 1h, downtrend 4h, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.08)))
                    # current 1d long red, overbought 1d, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.16)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 1d relative long top wick, overbought 1d, drop in last 2h
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 2.0))
                                          | (dataframe['cti_20_1d'] < 0.85)
                                          | (dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current and previous 1d red, overbought 1d
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.0)
                                          | (dataframe['change_pct_1d'].shift(288) > -0.0)
                                          | (dataframe['cti_20_1d'] < 0.85))
                    # downtrend 1d, overbought 1d
                    item_buy_logic.append((dataframe['is_downtrend_3_1d'] == False)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    # overbought 1d
                    item_buy_logic.append((dataframe['cti_20_1d'] < 0.9)
                                          | (dataframe['rsi_14_1d'] < 80.0))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152))
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['rsi_14_1d'] < 70.0))
                    # XAVA
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['rsi_3_15m'] > 25.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.02)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['rsi_14_15m'] < 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['cti_20_1d'] < -0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03)))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.016))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['close_delta'] > dataframe['close'] * 12.0 / 1000)
                    item_buy_logic.append(dataframe['rsi_14'] < 30.0)

                # Condition #81 - Long mode bull.
                if index == 81:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_12'] < (dataframe['close'] * 1.12))
                    item_buy_logic.append(dataframe['close_max_24'] < (dataframe['close'] * 1.16))
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.2))
                    item_buy_logic.append(dataframe['high_max_6_1h'] < (dataframe['close'] * 1.24))

                    item_buy_logic.append(dataframe['cti_20_1h'] < 0.95)
                    item_buy_logic.append(dataframe['cti_20_4h'] < 0.95)
                    item_buy_logic.append(dataframe['rsi_14_1h'] < 85.0)
                    item_buy_logic.append(dataframe['rsi_14_4h'] < 85.0)
                    item_buy_logic.append(dataframe['rsi_14_1d'] < 85.0)
                    item_buy_logic.append(dataframe['r_14_1h'] < -25.0)
                    item_buy_logic.append(dataframe['r_14_4h'] < -25.0)

                    item_buy_logic.append(dataframe['pct_change_high_max_6_24_1h'] > -0.3)
                    item_buy_logic.append(dataframe['pct_change_high_max_3_12_4h'] > -0.4)

                    item_buy_logic.append(protections_global_1)
                    item_buy_logic.append(protections_global_2)
                    item_buy_logic.append(protections_global_3)
                    item_buy_logic.append(protections_global_4)
                    item_buy_logic.append(protections_global_5)
                    item_buy_logic.append(protections_global_6)
                    item_buy_logic.append(protections_global_7)
                    item_buy_logic.append(protections_global_8)
                    item_buy_logic.append(protections_global_9)
                    item_buy_logic.append(protections_global_10)

                    item_buy_logic.append(dataframe['not_downtrend_15m'])

                    # current 4h relative long top wick, overbought 1h, downtrend 1h, downtrend 4h
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 2.0))
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(288))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(576)))
                    # current 4h relative long top wick, overbought 1d
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 6.0))
                                          | (dataframe['cti_20_1d'] < 0.5))
                    # current 4h relative long top wick, overbought 1h, downtrend 1h
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 2.0))
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['not_downtrend_1h']))
                    # big drop in last 48h, downtrend 1h
                    item_buy_logic.append((dataframe['high_max_48_1h'] < (dataframe['close'] * 1.5))
                                          | (dataframe['not_downtrend_1h']))
                    # downtrend 1h, downtrend 4h, drop in last 2h
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # downtrend 1h, overbought 1h
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < 0.5))
                    # downtrend 1h, overbought 4h
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_4h'] < 0.5))
                    # downtrend 1h, downtrend 4h, overbought 1d
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['not_downtrend_4h'])
                                          | (dataframe['cti_20_1d'] < 0.5))
                    # downtrend 1d, overbought 1d
                    item_buy_logic.append((dataframe['is_downtrend_3_1d'] == False)
                                          | (dataframe['cti_20_1d'] < 0.5))
                    # downtrend 1d, downtrend 1h
                    item_buy_logic.append((dataframe['is_downtrend_3_1d'] == False)
                                          | (dataframe['not_downtrend_1h']))
                    # current 4h red, previous 4h green, overbought 4h
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.06)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.06)
                                          | (dataframe['cti_20_4h'] < 0.5))
                    # current 1d long green with long top wick
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.12)
                                          | (dataframe['top_wick_pct_1d'] < 0.12))
                    # current 1d long 1d with top wick, overbought 1d, downtrend 1h
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.2)
                                          | (dataframe['top_wick_pct_1d'] < 0.04)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['not_downtrend_1h']))
                    # current 1d long red, overbought 1d, downtrend 1h
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.1)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['not_downtrend_1h']))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.5)
                                          | (dataframe['cti_20_1h'] < 0.5)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['cti_20_1d'] < 0.75)
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.0)
                                          | (dataframe['cti_20_1h'] < -0.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | (dataframe['ema_200_1h'] > dataframe['ema_200_1h'].shift(576))
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))

                    # Logic
                    item_buy_logic.append(dataframe['bb40_2_delta'].gt(dataframe['close'] * 0.052))
                    item_buy_logic.append(dataframe['close_delta'].gt(dataframe['close'] * 0.024))
                    item_buy_logic.append(dataframe['bb40_2_tail'].lt(dataframe['bb40_2_delta'] * 0.2))
                    item_buy_logic.append(dataframe['close'].lt(dataframe['bb40_2_low'].shift()))
                    item_buy_logic.append(dataframe['close'].le(dataframe['close'].shift()))
                    item_buy_logic.append(dataframe['rsi_14'] < 30.0)

                # Condition #82 - Long mode bull.
                if index == 82:
                    # Protections
                    item_buy_logic.append(dataframe['btc_pct_close_max_24_5m'] < 0.03)
                    item_buy_logic.append(dataframe['btc_pct_close_max_72_5m'] < 0.03)
                    item_buy_logic.append(dataframe['close_max_48'] < (dataframe['close'] * 1.2))
                    item_buy_logic.append(dataframe['high_max_12_1h'] < (dataframe['close'] * 1.3))

                    item_buy_logic.append(dataframe['ema_50_1h'] > dataframe['ema_200_1h'])
                    item_buy_logic.append(dataframe['sma_50_1h'] > dataframe['sma_200_1h'])

                    item_buy_logic.append(dataframe['ema_50_4h'] > dataframe['ema_200_4h'])
                    item_buy_logic.append(dataframe['sma_50_4h'] > dataframe['sma_200_4h'])

                    item_buy_logic.append(dataframe['rsi_14_4h'] < 85.0)
                    item_buy_logic.append(dataframe['rsi_14_1d'] < 85.0)
                    item_buy_logic.append(dataframe['r_480_4h'] < -10.0)

                    item_buy_logic.append(protections_global_1)
                    item_buy_logic.append(protections_global_2)
                    item_buy_logic.append(protections_global_3)
                    item_buy_logic.append(protections_global_4)
                    item_buy_logic.append(protections_global_5)
                    item_buy_logic.append(protections_global_6)
                    item_buy_logic.append(protections_global_7)
                    item_buy_logic.append(protections_global_8)
                    item_buy_logic.append(protections_global_9)
                    item_buy_logic.append(protections_global_10)

                    # current 1d long green with long top wick
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.12)
                                          | (dataframe['top_wick_pct_1d'] < 0.12))
                    # overbought 1d, overbought 4h, downtrend 1h, drop in last 2h
                    item_buy_logic.append((dataframe['rsi_14_1d'] < 70.0)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 4h red, downtrend 1h, overbought 4h, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.06)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_4h'] < 0.5)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 4h long red, downtrend 1h, overbought 1d, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.12)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1d'] < 0.8)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 1d red, overbought 1d, downtrend 1h, downtrend 4h, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.12)
                                          | (dataframe['cti_20_1d'] < 0.85)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['is_downtrend_3_4h'] == False)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 1d red, overbought 1d, downtrend 1h, current 4h red, previous 4h green with top wick
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.08)
                                          | (dataframe['cti_20_1d'] < 0.85)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['change_pct_4h'] > -0.0)
                                          | (dataframe['change_pct_4h'].shift(48) < 0.04)
                                          | (dataframe['top_wick_pct_4h'].shift(48) < 0.04))
                    # current 1d long red with long top wick, overbought 1d, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.12)
                                          | (dataframe['top_wick_pct_1d'] < 0.12)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 1d long red, overbought 1d, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.16)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 4h red with top wick, overbought 1d
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['top_wick_pct_4h'] < 0.04)
                                          | (dataframe['cti_20_1d'] < 0.85))
                    # current 4h green with top wick, overbought 4h
                    item_buy_logic.append((dataframe['change_pct_4h'] < 0.04)
                                          | (dataframe['top_wick_pct_4h'] < 0.04)
                                          | (dataframe['rsi_14_4h'] < 70.0))
                    # current 4h red, downtrend 1h, overbought 1d
                    item_buy_logic.append((dataframe['change_pct_4h'] > -0.04)
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1d'] < 0.5))
                    # current 1d long relative top wick, overbought 1d, drop in last 2h
                    item_buy_logic.append((dataframe['top_wick_pct_1d'] < (abs(dataframe['change_pct_1d']) * 4.0))
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 4h relative long top wick, overbought 1d, drop in last 2h
                    item_buy_logic.append((dataframe['top_wick_pct_4h'] < (abs(dataframe['change_pct_4h']) * 4.0))
                                          | (dataframe['cti_20_1d'] < 0.85)
                                          | (dataframe['rsi_14_1d'] < 50.0)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current and previous 1d red, overbought 1d, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_1d'] > -0.04)
                                          | (dataframe['change_pct_1d'].shift(288) > -0.04)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    # current 4h long green, overbought 4h, drop in last 2h
                    item_buy_logic.append((dataframe['change_pct_1d'] < 0.08)
                                          | (dataframe['rsi_14_4h'] < 70.0)
                                          | (dataframe['close_max_24'] < (dataframe['close'] * 1.1)))
                    item_buy_logic.append((dataframe['not_downtrend_15m'])
                                          | (dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_1h'] < -0.5)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['cti_20_1d'] < -0.0)
                                          | (dataframe['ema_200_4h'] > dataframe['ema_200_4h'].shift(1152))
                                          | (dataframe['ema_200_1d'] > dataframe['ema_200_1d'].shift(1152)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.8)
                                          | (dataframe['rsi_3_15m'] > 10.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['not_downtrend_1h'])
                                          | (dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['rsi_3_15m'] > 30.0)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['rsi_3_1h'] > 10.0)
                                          | (dataframe['cti_20_4h'] < -0.0)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))
                    item_buy_logic.append((dataframe['cti_20_15m'] < -0.9)
                                          | (dataframe['cti_20_1h'] < -0.8)
                                          | (dataframe['cti_20_4h'] < 0.75)
                                          | (dataframe['r_14_4h'] < -25.0)
                                          | (dataframe['cti_20_1d'] < 0.5)
                                          | ((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.04)))

                    # Logic
                    item_buy_logic.append(dataframe['ema_26'] > dataframe['ema_12'])
                    item_buy_logic.append((dataframe['ema_26'] - dataframe['ema_12']) > (dataframe['open'] * 0.03))
                    item_buy_logic.append((dataframe['ema_26'].shift() - dataframe['ema_12'].shift()) > (dataframe['open'] / 100))
                    item_buy_logic.append(dataframe['cti_20'] < -0.8)

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

            if slippage < self.max_slippage:
                return True
            else:
                log.warning(f"Cancelling buy for {pair} due to slippage {(slippage * 100.0):.2f}%")
                return False

        return True

    def confirm_trade_exit(self, pair: str, trade: Trade, order_type: str, amount: float,
                           rate: float, time_in_force: str, exit_reason: str,
                           current_time: datetime, **kwargs) -> bool:
        # Allow force exits
        if exit_reason != 'force_exit':
            if self._should_hold_trade(trade, rate, exit_reason):
                return False
            if (exit_reason == 'stop_loss'):
                return False
            if self.exit_profit_only:
                if self.exit_profit_only:
                    profit = 0.0
                    if (trade.realized_profit != 0.0):
                        profit = ((rate - trade.open_rate) / trade.open_rate) * trade.stake_amount * (1 - trade.fee_close)
                        profit = profit + trade.realized_profit
                        profit = profit / trade.stake_amount
                    else:
                        profit = trade.calc_profit_ratio(rate)
                    if (profit < self.exit_profit_offset):
                        return False

        self._remove_profit_target(pair)
        return True

    def bot_loop_start(self, **kwargs) -> None:
        if self.config["runmode"].value not in ("live", "dry_run"):
            return super().bot_loop_start(**kwargs)

        if self.hold_support_enabled:
            self.load_hold_trades_config()

        return super().bot_loop_start(**kwargs)

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str], side: str,
                 **kwargs) -> float:

        return 5.0

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

    def _should_hold_trade(self, trade: "Trade", rate: float, sell_reason: str) -> bool:
        if self.config['runmode'].value not in ('live', 'dry_run'):
            return False

        if not self.hold_support_enabled:
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
            profit = 0.0
            if (trade.realized_profit != 0.0):
                profit = ((rate - trade.open_rate) / trade.open_rate) * trade.stake_amount * (1 - trade.fee_close)
                profit = profit + trade.realized_profit
                profit = profit / trade.stake_amount
            else:
                profit = trade.calc_profit_ratio(rate)
            current_profit_ratio = profit
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
            profit = 0.0
            if (trade.realized_profit != 0.0):
                profit = ((rate - trade.open_rate) / trade.open_rate) * trade.stake_amount * (1 - trade.fee_close)
                profit = profit + trade.realized_profit
                profit = profit / trade.stake_amount
            else:
                profit = trade.calc_profit_ratio(rate)
            current_profit_ratio = profit
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
