"""
ICT Time-Based Liquidity Strategy
Based on ICT (Inner Circle Trader) concepts and TIME BASED LIQUIDITY / HIGH PROBABILITY DOLS trading notes

Core Philosophy:
- Market moves to Seek Liquidity or Rebalance Imbalance
- Smart Money operates at specific time windows
- Trade the reversal after liquidity sweep (not the breakout)

Author: Claude Code (based on trading notes)
Version: 1.0.0
"""

import logging
import numpy as np
import pandas as pd
from pandas import DataFrame
from datetime import datetime, timedelta
from typing import Optional
import talib.abstract as ta
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.persistence import Trade

log = logging.getLogger(__name__)


class ICT_TimeBasedLiquidityStrategy(IStrategy):
    """
    ICT Time-Based Liquidity Strategy for Freqtrade

    This strategy implements:
    1. Time-based session windows (Asian, London, NY AM, NY PM)
    2. Liquidity pool identification (PWH/PWL, PDH/PDL, Session Highs/Lows)
    3. Liquidity sweep and reclaim logic
    4. Fair Value Gap (FVG) detection
    5. Smart Money reversal patterns
    """

    INTERFACE_VERSION = 3

    # Strategy version
    def version(self) -> str:
        return "v1.0.0"

    # ROI table - conservative targets based on liquidity pools
    minimal_roi = {
        "0": 0.10,    # 10% - take profit at opposing liquidity
        "60": 0.05,   # 5% after 1 hour
        "120": 0.03,  # 3% after 2 hours
        "240": 0.01   # 1% after 4 hours
    }

    # Stoploss - will be managed dynamically based on swing points
    stoploss = -0.05  # 5% hard stop

    # Trailing stoploss
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    # Use custom stoploss
    use_custom_stoploss = True

    # Optimal timeframe for the strategy
    timeframe = "5m"

    # Additional timeframes for context
    informative_timeframes = ["15m", "1h", "1d"]

    # Startup candle count - need enough history for weekly/daily levels
    startup_candle_count: int = 500

    # Buy/Sell hyper parameters
    buy_params = {}
    sell_params = {}

    # Strategy-specific variables
    # All times in New York Time (EST/EDT)
    ASIAN_SESSION_START = 20  # 20:00 NY time
    ASIAN_SESSION_END = 0     # 00:00 NY time (can extend to 03:00)

    LONDON_SESSION_START = 2  # 02:00 NY time
    LONDON_SESSION_END = 5    # 05:00 NY time (can extend to 08:30)

    NY_AM_SESSION_START = 9.5   # 09:30 NY time
    NY_AM_SESSION_END = 12      # 12:00 NY time

    NY_PM_SESSION_START = 13.5  # 13:30 NY time
    NY_PM_SESSION_END = 16.5    # 16:30 NY time

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate indicators needed for the strategy
        """

        # ============================================================================
        # SECTION 1: Time-based session identification
        # ============================================================================
        dataframe = self.identify_sessions(dataframe)

        # ============================================================================
        # SECTION 2: Calculate key liquidity levels
        # ============================================================================
        dataframe = self.calculate_liquidity_levels(dataframe)

        # ============================================================================
        # SECTION 3: Fair Value Gap (FVG) detection
        # ============================================================================
        dataframe = self.detect_fvg(dataframe)

        # ============================================================================
        # SECTION 4: Liquidity sweep and reclaim detection
        # ============================================================================
        dataframe = self.detect_liquidity_sweep(dataframe)

        # ============================================================================
        # SECTION 5: Market bias and directional analysis
        # ============================================================================
        dataframe = self.determine_bias(dataframe)

        # ============================================================================
        # SECTION 6: Additional technical indicators for confirmation
        # ============================================================================
        dataframe = self.add_technical_indicators(dataframe)

        return dataframe

    def identify_sessions(self, dataframe: DataFrame) -> DataFrame:
        """
        Identify trading sessions based on New York time
        All times are in UTC, need to convert to NY time
        """
        # Convert UTC to NY time (approximately UTC-5 for EST, UTC-4 for EDT)
        # For simplicity, using UTC-5 (can be adjusted for DST)
        dataframe['hour_ny'] = (dataframe['date'].dt.hour - 5) % 24
        dataframe['minute'] = dataframe['date'].dt.minute
        dataframe['hour_decimal'] = dataframe['hour_ny'] + dataframe['minute'] / 60.0

        # Mark sessions
        dataframe['is_asian_session'] = (
            ((dataframe['hour_ny'] >= self.ASIAN_SESSION_START) |
             (dataframe['hour_ny'] < self.ASIAN_SESSION_END))
        ).astype(int)

        dataframe['is_london_session'] = (
            (dataframe['hour_ny'] >= self.LONDON_SESSION_START) &
            (dataframe['hour_ny'] < self.LONDON_SESSION_END)
        ).astype(int)

        dataframe['is_ny_am_session'] = (
            (dataframe['hour_decimal'] >= self.NY_AM_SESSION_START) &
            (dataframe['hour_decimal'] < self.NY_AM_SESSION_END)
        ).astype(int)

        dataframe['is_ny_pm_session'] = (
            (dataframe['hour_decimal'] >= self.NY_PM_SESSION_START) &
            (dataframe['hour_decimal'] < self.NY_PM_SESSION_END)
        ).astype(int)

        return dataframe

    def calculate_liquidity_levels(self, dataframe: DataFrame) -> DataFrame:
        """
        Calculate key liquidity pools:
        - PDH/PDL (Previous Day High/Low)
        - PWH/PWL (Previous Week High/Low)
        - Asian Session High/Low
        - London Session High/Low
        """

        # Previous Day High/Low (PDH/PDL)
        # Using rolling window to find previous day's high/low
        dataframe['pdh'] = dataframe['high'].shift(288).rolling(window=288).max()  # 288 = 24h in 5m candles
        dataframe['pdl'] = dataframe['low'].shift(288).rolling(window=288).min()

        # Previous Week High/Low (PWH/PWL)
        dataframe['pwh'] = dataframe['high'].shift(2016).rolling(window=2016).max()  # 2016 = 7d in 5m candles
        dataframe['pwl'] = dataframe['low'].shift(2016).rolling(window=2016).min()

        # Asian Session High/Low
        # Calculate high/low during Asian session, then forward fill for use in other sessions
        dataframe['asian_high'] = np.nan
        dataframe['asian_low'] = np.nan

        asian_mask = dataframe['is_asian_session'] == 1
        dataframe.loc[asian_mask, 'asian_high'] = dataframe.loc[asian_mask, 'high']
        dataframe.loc[asian_mask, 'asian_low'] = dataframe.loc[asian_mask, 'low']

        # Get the max/min from the last asian session
        dataframe['asian_high'] = dataframe['asian_high'].rolling(window=48, min_periods=1).max()  # 4h window
        dataframe['asian_low'] = dataframe['asian_low'].rolling(window=48, min_periods=1).min()

        # London Session High/Low
        dataframe['london_high'] = np.nan
        dataframe['london_low'] = np.nan

        london_mask = dataframe['is_london_session'] == 1
        dataframe.loc[london_mask, 'london_high'] = dataframe.loc[london_mask, 'high']
        dataframe.loc[london_mask, 'london_low'] = dataframe.loc[london_mask, 'low']

        dataframe['london_high'] = dataframe['london_high'].rolling(window=36, min_periods=1).max()  # 3h window
        dataframe['london_low'] = dataframe['london_low'].rolling(window=36, min_periods=1).min()

        # Forward fill session levels for use after session ends
        dataframe['asian_high'] = dataframe['asian_high'].ffill()
        dataframe['asian_low'] = dataframe['asian_low'].ffill()
        dataframe['london_high'] = dataframe['london_high'].ffill()
        dataframe['london_low'] = dataframe['london_low'].ffill()

        return dataframe

    def detect_fvg(self, dataframe: DataFrame) -> DataFrame:
        """
        Detect Fair Value Gaps (FVG)

        Bullish FVG: Candle 1 high < Candle 3 low (gap between them = imbalance)
        Bearish FVG: Candle 1 low > Candle 3 high (gap between them = imbalance)
        """

        # Bullish FVG (buying opportunity when price returns to gap)
        dataframe['bullish_fvg'] = (
            (dataframe['high'].shift(2) < dataframe['low']) &  # Gap exists
            (dataframe['close'].shift(1) > dataframe['open'].shift(1))  # Middle candle is bullish
        ).astype(int)

        # Bearish FVG (selling opportunity when price returns to gap)
        dataframe['bearish_fvg'] = (
            (dataframe['low'].shift(2) > dataframe['high']) &  # Gap exists
            (dataframe['close'].shift(1) < dataframe['open'].shift(1))  # Middle candle is bearish
        ).astype(int)

        # Store FVG levels for potential entry points
        dataframe['bullish_fvg_high'] = np.where(
            dataframe['bullish_fvg'] == 1,
            dataframe['low'],
            np.nan
        )
        dataframe['bullish_fvg_low'] = np.where(
            dataframe['bullish_fvg'] == 1,
            dataframe['high'].shift(2),
            np.nan
        )

        dataframe['bearish_fvg_high'] = np.where(
            dataframe['bearish_fvg'] == 1,
            dataframe['low'].shift(2),
            np.nan
        )
        dataframe['bearish_fvg_low'] = np.where(
            dataframe['bearish_fvg'] == 1,
            dataframe['high'],
            np.nan
        )

        # Forward fill FVG levels until they're used
        dataframe['bullish_fvg_high'] = dataframe['bullish_fvg_high'].ffill()
        dataframe['bullish_fvg_low'] = dataframe['bullish_fvg_low'].ffill()
        dataframe['bearish_fvg_high'] = dataframe['bearish_fvg_high'].ffill()
        dataframe['bearish_fvg_low'] = dataframe['bearish_fvg_low'].ffill()

        return dataframe

    def detect_liquidity_sweep(self, dataframe: DataFrame) -> DataFrame:
        """
        Detect liquidity sweep and reclaim patterns

        Sweep: Price breaks a key level (PDL, Asian Low, etc.)
        Reclaim: Price closes back above that level (for lows) or below (for highs)

        This is the core ICT concept: fake breakout + reversal
        """

        # Tolerance for sweep detection (price must break level by small amount)
        tolerance = 0.0005  # 0.05%

        # ===== BULLISH SETUPS (Sweep low, reclaim high) =====

        # PDL Sweep and Reclaim (strongest signal)
        dataframe['pdl_sweep'] = (
            (dataframe['low'] < dataframe['pdl'] * (1 - tolerance)) &  # Swept below PDL
            (dataframe['close'] > dataframe['pdl'])  # Closed back above PDL
        ).astype(int)

        # Asian Low Sweep and Reclaim
        dataframe['asian_low_sweep'] = (
            (dataframe['low'] < dataframe['asian_low'] * (1 - tolerance)) &
            (dataframe['close'] > dataframe['asian_low']) &
            (dataframe['is_london_session'] == 1)  # Typically happens during London session
        ).astype(int)

        # London Low Sweep and Reclaim
        dataframe['london_low_sweep'] = (
            (dataframe['low'] < dataframe['london_low'] * (1 - tolerance)) &
            (dataframe['close'] > dataframe['london_low']) &
            (dataframe['is_ny_am_session'] == 1)  # Typically happens during NY AM session
        ).astype(int)

        # PWL Sweep and Reclaim (weekly level - very strong)
        dataframe['pwl_sweep'] = (
            (dataframe['low'] < dataframe['pwl'] * (1 - tolerance)) &
            (dataframe['close'] > dataframe['pwl'])
        ).astype(int)

        # ===== BEARISH SETUPS (Sweep high, reclaim low) =====

        # PDH Sweep and Reclaim
        dataframe['pdh_sweep'] = (
            (dataframe['high'] > dataframe['pdh'] * (1 + tolerance)) &  # Swept above PDH
            (dataframe['close'] < dataframe['pdh'])  # Closed back below PDH
        ).astype(int)

        # Asian High Sweep and Reclaim
        dataframe['asian_high_sweep'] = (
            (dataframe['high'] > dataframe['asian_high'] * (1 + tolerance)) &
            (dataframe['close'] < dataframe['asian_high']) &
            (dataframe['is_london_session'] == 1)
        ).astype(int)

        # London High Sweep and Reclaim
        dataframe['london_high_sweep'] = (
            (dataframe['high'] > dataframe['london_high'] * (1 + tolerance)) &
            (dataframe['close'] < dataframe['london_high']) &
            (dataframe['is_ny_am_session'] == 1)
        ).astype(int)

        # PWH Sweep and Reclaim
        dataframe['pwh_sweep'] = (
            (dataframe['high'] > dataframe['pwh'] * (1 + tolerance)) &
            (dataframe['close'] < dataframe['pwh'])
        ).astype(int)

        # Combined sweep signals
        dataframe['bullish_sweep'] = (
            (dataframe['pdl_sweep'] == 1) |
            (dataframe['asian_low_sweep'] == 1) |
            (dataframe['london_low_sweep'] == 1) |
            (dataframe['pwl_sweep'] == 1)
        ).astype(int)

        dataframe['bearish_sweep'] = (
            (dataframe['pdh_sweep'] == 1) |
            (dataframe['asian_high_sweep'] == 1) |
            (dataframe['london_high_sweep'] == 1) |
            (dataframe['pwh_sweep'] == 1)
        ).astype(int)

        return dataframe

    def determine_bias(self, dataframe: DataFrame) -> DataFrame:
        """
        Determine market bias based on higher timeframe structure

        Bullish bias: Price above key MAs, targeting PWH
        Bearish bias: Price below key MAs, targeting PWL
        """

        # Simple trend determination using EMAs
        dataframe['ema_20'] = ta.EMA(dataframe, timeperiod=20)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)

        # Bullish bias
        dataframe['bullish_bias'] = (
            (dataframe['close'] > dataframe['ema_20']) &
            (dataframe['ema_20'] > dataframe['ema_50']) &
            (dataframe['close'] > dataframe['ema_200'])
        ).astype(int)

        # Bearish bias
        dataframe['bearish_bias'] = (
            (dataframe['close'] < dataframe['ema_20']) &
            (dataframe['ema_20'] < dataframe['ema_50']) &
            (dataframe['close'] < dataframe['ema_200'])
        ).astype(int)

        return dataframe

    def add_technical_indicators(self, dataframe: DataFrame) -> DataFrame:
        """
        Add additional technical indicators for confirmation
        """

        # RSI for overbought/oversold confirmation
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)

        # ATR for volatility-based stop loss
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)

        # Volume confirmation
        dataframe['volume_ma'] = dataframe['volume'].rolling(window=20).mean()
        dataframe['high_volume'] = (dataframe['volume'] > dataframe['volume_ma'] * 1.5).astype(int)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Define entry conditions based on ICT liquidity sweep concepts
        """

        # ===== LONG ENTRY CONDITIONS =====
        # Entry long when:
        # 1. Bullish sweep detected (liquidity taken below key level)
        # 2. Bullish bias OR in proper session timing
        # 3. Optional: Bullish FVG formed as confirmation
        # 4. Not overbought

        dataframe.loc[
            (
                # Core condition: Bullish liquidity sweep
                (dataframe['bullish_sweep'] == 1) &

                # Bias filter: Either bullish bias or in favorable session
                (
                    (dataframe['bullish_bias'] == 1) |
                    (dataframe['is_london_session'] == 1) |
                    (dataframe['is_ny_am_session'] == 1)
                ) &

                # Optional FVG confirmation (or previous FVG exists nearby)
                (
                    (dataframe['bullish_fvg'] == 1) |
                    (dataframe['bullish_fvg'].shift(1) == 1) |
                    (dataframe['bullish_fvg'].shift(2) == 1)
                ) &

                # Not overbought
                (dataframe['rsi'] < 70) &

                # Volume confirmation
                (dataframe['high_volume'] == 1) &

                # Ensure we have valid data
                (dataframe['volume'] > 0)
            ),
            ['enter_long', 'enter_tag']
        ] = (1, 'ict_liquidity_sweep_long')

        # ===== SHORT ENTRY CONDITIONS =====
        # Entry short when:
        # 1. Bearish sweep detected (liquidity taken above key level)
        # 2. Bearish bias OR in proper session timing
        # 3. Optional: Bearish FVG formed as confirmation
        # 4. Not oversold

        dataframe.loc[
            (
                # Core condition: Bearish liquidity sweep
                (dataframe['bearish_sweep'] == 1) &

                # Bias filter
                (
                    (dataframe['bearish_bias'] == 1) |
                    (dataframe['is_london_session'] == 1) |
                    (dataframe['is_ny_am_session'] == 1)
                ) &

                # Optional FVG confirmation
                (
                    (dataframe['bearish_fvg'] == 1) |
                    (dataframe['bearish_fvg'].shift(1) == 1) |
                    (dataframe['bearish_fvg'].shift(2) == 1)
                ) &

                # Not oversold
                (dataframe['rsi'] > 30) &

                # Volume confirmation
                (dataframe['high_volume'] == 1) &

                # Ensure we have valid data
                (dataframe['volume'] > 0)
            ),
            ['enter_short', 'enter_tag']
        ] = (1, 'ict_liquidity_sweep_short')

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Define exit conditions based on opposing liquidity pools

        Exit when price reaches the opposing liquidity level (target)
        """

        # ===== EXIT LONG CONDITIONS =====
        # Exit long when price reaches:
        # 1. PDH (Previous Day High)
        # 2. Asian High
        # 3. London High
        # 4. PWH (Previous Week High)
        # 5. Or bearish FVG formed (reversal signal)

        dataframe.loc[
            (
                (
                    # Price near/at resistance levels
                    (dataframe['close'] >= dataframe['pdh'] * 0.998) |
                    (dataframe['close'] >= dataframe['asian_high'] * 0.998) |
                    (dataframe['close'] >= dataframe['london_high'] * 0.998) |
                    (dataframe['close'] >= dataframe['pwh'] * 0.998) |

                    # Bearish reversal signal
                    (dataframe['bearish_fvg'] == 1) |
                    (dataframe['bearish_sweep'] == 1)
                ) &

                # Ensure we have valid data
                (dataframe['volume'] > 0)
            ),
            ['exit_long', 'exit_tag']
        ] = (1, 'ict_target_reached_long')

        # ===== EXIT SHORT CONDITIONS =====
        # Exit short when price reaches:
        # 1. PDL (Previous Day Low)
        # 2. Asian Low
        # 3. London Low
        # 4. PWL (Previous Week Low)
        # 5. Or bullish FVG formed (reversal signal)

        dataframe.loc[
            (
                (
                    # Price near/at support levels
                    (dataframe['close'] <= dataframe['pdl'] * 1.002) |
                    (dataframe['close'] <= dataframe['asian_low'] * 1.002) |
                    (dataframe['close'] <= dataframe['london_low'] * 1.002) |
                    (dataframe['close'] <= dataframe['pwl'] * 1.002) |

                    # Bullish reversal signal
                    (dataframe['bullish_fvg'] == 1) |
                    (dataframe['bullish_sweep'] == 1)
                ) &

                # Ensure we have valid data
                (dataframe['volume'] > 0)
            ),
            ['exit_short', 'exit_tag']
        ] = (1, 'ict_target_reached_short')

        return dataframe

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        """
        Custom stoploss logic based on swing points and ATR

        Stop loss should be placed beyond the swing point where liquidity was swept
        """

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        # Get ATR for dynamic stop
        atr = last_candle['atr']

        if trade.is_short:
            # For short trades, stop above recent swing high
            # Use 1.5x ATR above entry as stop
            stop_distance = (atr * 1.5) / current_rate
            return stop_distance
        else:
            # For long trades, stop below recent swing low
            # Use 1.5x ATR below entry as stop
            stop_distance = (atr * 1.5) / trade.open_rate
            return -stop_distance

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime,
                    current_rate: float, current_profit: float, **kwargs) -> Optional[str]:
        """
        Custom exit logic for special conditions
        """

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        # Exit if opposite sweep occurs (strong reversal signal)
        if trade.is_short and last_candle['bullish_sweep'] == 1:
            return 'opposite_sweep_detected'

        if not trade.is_short and last_candle['bearish_sweep'] == 1:
            return 'opposite_sweep_detected'

        return None

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: Optional[str],
                 side: str, **kwargs) -> float:
        """
        Customize leverage - conservative approach for ICT strategy
        """
        # Use moderate leverage for liquidity sweep strategies
        return 3.0
