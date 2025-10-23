# Short Trading Modes

<cite>
**Referenced Files in This Document**   
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py)
</cite>

## Table of Contents
1. [Short Trading Modes Overview](#short-trading-modes-overview)
2. [Short Entry Logic and Conditions](#short-entry-logic-and-conditions)
3. [Configuration Parameters for Short Modes](#configuration-parameters-for-short-modes)
4. [Position Adjustment and Risk Management](#position-adjustment-and-risk-management)
5. [Spot vs Futures Market Behavior](#spot-vs-futures-market-behavior)
6. [Risk Management and Common Issues](#risk-management-and-common-issues)

## Short Trading Modes Overview

The NostalgiaForInfinityX6 strategy supports multiple short trading modes designed to capitalize on bearish market conditions. These modes mirror their long counterparts in structure but are specifically tailored for short positions. The supported short modes include Normal, Pump, Quick, Rebuy, Rapid, Grind, and Scalp. Each mode is identified by unique entry condition tags and operates under specific logic to detect and act on downward price momentum.

Short modes are activated when the market exhibits signs of a downtrend, such as bearish momentum, volume spikes during price declines, or overbought conditions reversing. The strategy uses a combination of technical indicators across multiple timeframes (5m, 15m, 1h, 4h, 1d) to confirm entry signals. Unlike long modes, short entries require confirmation of selling pressure and weakening bullish sentiment.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L13853-L15529)

## Short Entry Logic and Conditions

Short entry conditions are defined within the `populate_entry_trend` method of the `NostalgiaForInfinityX6` class. The logic is structured around a series of RSI, Stochastic RSI, Aroon, and EMA-based conditions that detect bearish momentum across various timeframes.

The primary short entry conditions are controlled by the `short_entry_signal_params` dictionary, which enables or disables specific conditions. For example:

```python
short_entry_signal_params = {
    "short_entry_condition_501_enable": True,
    "short_entry_condition_502_enable": True,
    "short_entry_condition_542_enable": True,
}
```

Each condition corresponds to a specific short mode:
- **Condition 501**: Normal mode (Short)
- **Condition 502**: Normal mode (Short)
- **Condition 542**: Quick mode (Short)

The entry logic for Condition 501 (Normal mode) includes protections against empty candles and global short protections, along with RSI thresholds to ensure the asset is not oversold. It also checks for EMA crossovers and Bollinger Band conditions to confirm upward price action that may precede a reversal.

```python
if short_entry_condition_index == 501:
    short_entry_logic.append(df["num_empty_288"] <= allowed_empty_candles_288)
    short_entry_logic.append(df["protections_short_global"] == True)
    short_entry_logic.append(df["global_protections_short_pump"] == True)
    short_entry_logic.append(df["global_protections_short_dump"] == True)
    short_entry_logic.append(df["RSI_3_1h"] >= 5.0)
    short_entry_logic.append(df["RSI_3_4h"] >= 20.0)
    short_entry_logic.append(df["RSI_3_1d"] >= 20.0)
    short_entry_logic.append(df["EMA_12"] > df["EMA_26"])
    short_entry_logic.append((df["EMA_12"] - df["EMA_26"]) > (df["open"] * 0.030))
    short_entry_logic.append(df["close"] > (df["BBU_20_2.0"] * 1.001))
```

Similarly, Condition 542 (Quick mode) uses Williams %R, Aroon, and Stochastic RSI to detect overbought conditions and potential reversals.

```python
if short_entry_condition_index == 542:
    short_entry_logic.append(df["WILLR_14"] > -50.0)
    short_entry_logic.append(df["AROONU_14"] > 75.0)
    short_entry_logic.append(df["AROOND_14"] < 25.0)
    short_entry_logic.append(df["STOCHRSIk_14_14_3_3"] > 80.0)
    short_entry_logic.append(df["close_min_48"] <= (df["close"] * 0.90))
```

These conditions are combined using logical AND operations, and the resulting signal is stored in the `enter_short` column of the DataFrame.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L13865-L15529)

## Configuration Parameters for Short Modes

The strategy allows extensive configuration of short trading behavior through various parameters. These parameters can be set in the strategy configuration or via the `nfi_parameters` block in the config file.

Key configuration options include:
- **short_pump_threshold**: Not explicitly defined but inferred from mode-specific thresholds
- **short_grind_exit_delay**: Controlled via `grind_1_stop_grinds_spot` and similar parameters
- **stop_threshold_spot**: Stop loss threshold for spot markets (default 0.10)
- **stop_threshold_futures**: Stop loss threshold for futures markets (default 0.10)
- **futures_mode_leverage**: Leverage used in futures mode (default 3.0)

The strategy also defines mode-specific stake multipliers:
```python
short_normal_mode_name = "short_normal"
short_pump_mode_name = "short_pump"
short_quick_mode_name = "short_quick"
short_rebuy_mode_name = "short_rebuy"
short_high_profit_mode_name = "short_hp"
short_rapid_mode_name = "short_rapid"
short_top_coins_mode_name = "short_tc"
short_scalp_mode_name = "short_scalp"
```

Grinding parameters are defined for both spot and futures markets:
```python
grind_1_stakes_spot = [0.24, 0.26, 0.28]
grind_1_stakes_futures = [0.24, 0.26, 0.28]
grind_1_profit_threshold_spot = 0.018
grind_1_profit_threshold_futures = 0.018
```

These parameters control the size and timing of additional entries in a grinding strategy, allowing the position to average down during continued downtrends.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L150-L300)

## Position Adjustment and Risk Management

The strategy includes sophisticated position adjustment features for short positions, particularly through the grinding and derisking mechanisms. These features are enabled by default and can be configured via the following parameters:

```python
position_adjustment_enable = True
grinding_enable = True
derisk_enable = True
stops_enable = True
```

The grinding mechanism allows the strategy to add to short positions at predetermined intervals when the price continues to rise, effectively averaging down the entry price. This is controlled by parameters such as `grind_1_stakes_spot` and `grind_1_sub_thresholds_spot`.

Derisking is implemented through stop thresholds that trigger partial or full exits when the market moves against the position. For example:
```python
regular_mode_derisk_1_spot = -0.24
regular_mode_derisk_1_futures = -0.60
```

The strategy also supports a v2 grinding system with more granular control:
```python
grinding_v2_grind_1_stakes_spot = [0.20, 0.21, 0.22, 0.23]
grinding_v2_grind_1_thresholds_spot = [-0.06, -0.07, -0.08, -0.09]
```

These parameters define the stake size and price thresholds for each additional entry in the grinding sequence.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L300-L500)

## Spot vs Futures Market Behavior

The strategy differentiates between spot and futures markets in several key aspects:

1. **Leverage**: Futures positions use leverage (configurable via `futures_mode_leverage`), while spot positions do not.
2. **Stop Loss Thresholds**: Different stop loss thresholds are applied based on the market type:
   ```python
   stop_threshold_spot = 0.10
   stop_threshold_futures = 0.10
   ```
3. **Grinding Parameters**: Separate parameters exist for spot and futures grinding:
   ```python
   grind_1_stakes_spot = [0.24, 0.26, 0.28]
   grind_1_stakes_futures = [0.24, 0.26, 0.28]
   ```
4. **Derisk Levels**: Futures positions have more aggressive derisk levels due to higher volatility:
   ```python
   regular_mode_derisk_1_spot = -0.24
   regular_mode_derisk_1_futures = -0.60
   ```

The strategy automatically detects the trading mode based on the exchange configuration:
```python
if ("trading_mode" in self.config) and (self.config["trading_mode"] in ["futures", "margin"]):
    self.is_futures_mode = True
    self.can_short = True
```

This allows the strategy to adapt its risk parameters and position sizing based on the market type.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L100-L150)

## Risk Management and Common Issues

Short trading carries inherent risks, particularly in volatile markets. The strategy addresses these through several mechanisms:

1. **Stop Loss Protection**: Automatic stop loss triggers prevent excessive losses:
   ```python
   stoploss = -0.99
   ```
2. **Position Sizing**: Dynamic stake multipliers prevent overexposure:
   ```python
   short_normal_mode_tags = ["501", "502"]
   ```
3. **Market Protections**: Global protections against pumps and dumps:
   ```python
   short_entry_logic.append(df["global_protections_short_pump"] == True)
   short_entry_logic.append(df["global_protections_short_dump"] == True)
   ```

Common issues in short trading include:
- **Liquidation Risks**: In futures markets, rapid price movements can trigger liquidations. The strategy mitigates this through conservative leverage settings and early derisking.
- **Delayed Fills**: In low-liquidity pairs, short entries may experience slippage. The strategy includes a `max_slippage` parameter (default 0.01) to limit entry price deviation.
- **Volatility Spikes**: The use of multiple timeframe analysis helps filter out false signals during volatile periods.

The strategy also includes a doom stop mechanism for extreme market conditions:
```python
stop_threshold_doom_spot = 0.20
stop_threshold_doom_futures = 0.20
```

This ensures that positions are closed quickly if the market moves sharply against the short position.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L50-L100)