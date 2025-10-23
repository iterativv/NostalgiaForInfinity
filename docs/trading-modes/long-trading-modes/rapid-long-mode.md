# Rapid Long Mode

<cite>
**Referenced Files in This Document**   
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py)
</cite>

## Table of Contents
1. [Rapid Long Mode](#rapid-long-mode)
2. [Configuration Parameters](#configuration-parameters)
3. [Entry Signal Logic](#entry-signal-logic)
4. [Position Sizing and Risk Control](#position-sizing-and-risk-control)
5. [Exit Strategy](#exit-strategy)
6. [Interaction with Grinding and Derisking](#interaction-with-grinding-and-derisking)
7. [Practical Example: Flash Rally on OKX Futures](#practical-example-flash-rally-on-okx-futures)
8. [Common Pitfalls and Tuning Tips](#common-pitfalls-and-tuning-tips)
9. [Performance Considerations](#performance-considerations)

## Rapid Long Mode

The **Rapid Long Mode** in the NostalgiaForInfinityX6 (NFI-X6) strategy is designed for ultra-fast execution in response to strong, immediate bullish signals. It operates with higher aggression compared to standard long modes and is typically activated during sudden price surges, such as those following major protocol announcements or market-moving news. This mode bypasses multiple confirmation layers used in normal trading logic, relying instead on primary momentum indicators to trigger entries with minimal delay.

Rapid Long Mode is identified by specific **enter_tags** assigned to trades. These tags are defined in the strategy as:

```python
long_rapid_mode_tags = ["101", "102", "103", "104", "105", "106", "107", "108", "109", "110"]
```

When a trade is tagged with any of these identifiers (e.g., `"101"`), the strategy recognizes it as part of Rapid Long Mode and applies corresponding aggressive entry, position sizing, and exit logic.

This mode is particularly effective in **futures trading environments** where leverage can amplify gains during sharp upward movements. However, due to its low-latency nature, it also carries increased risk of false positives and slippage, requiring careful configuration and monitoring.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L125)

## Configuration Parameters

Several key parameters govern the behavior of Rapid Long Mode. These are configurable either directly in the strategy file or via the `nfi_parameters` block in the configuration.

### Rapid Mode Activation and Timing
- **`rapid_mode_stake_multiplier_spot`**: Stake multiplier for spot markets. Default: `[0.75]`
- **`rapid_mode_stake_multiplier_futures`**: Stake multiplier for futures markets. Default: `[0.75]`
- **`stop_threshold_rapid_spot`**: Maximum drawdown threshold before stop logic activates in spot mode. Default: `0.20` (20%)
- **`stop_threshold_rapid_futures`**: Maximum drawdown threshold for futures. Default: `0.20` (20%)

These parameters control how much capital is allocated per trade and when protective stops are triggered.

### Risk and Exposure Limits
- **`position_adjustment_enable`**: Enables dynamic position adjustments (including rebuys and grinds). Default: `True`
- **`grinding_enable`**: Enables grinding logic. Typically disabled during rapid mode to prevent overexposure. Default: `True`, but often overridden.
- **`derisk_enable`**: Enables derisking mechanisms immediately after entry. Default: `True`

The strategy uses these flags to determine whether post-entry risk management features like trailing stops or partial exits should be active.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L125-L134)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L200-L210)

## Entry Signal Logic

Rapid Long Mode entries are triggered by high-momentum indicators that detect explosive price movements. The primary conditions are defined in the `long_entry_signal_params` dictionary:

```python
"long_entry_condition_101_enable": True,
"long_entry_condition_102_enable": True,
"long_entry_condition_103_enable": True,
"long_entry_condition_104_enable": True,
```

These conditions typically evaluate indicators such as:
- **MACD histogram spike**: A sudden increase in the MACD histogram value indicates accelerating bullish momentum.
- **Volume explosion**: A significant spike in trading volume confirms the strength of the move.
- **Price breaking key resistance levels** with minimal retest.

A representative conditional block from the strategy logic (simplified) would resemble:

```python
if rapid_mode_active and macd_histogram > rapid_trigger_level:
    enter_long()
```

This bypasses slower-moving averages or consolidation filters used in normal mode, allowing the strategy to react within a single 5-minute candle.

The use of **tag-based routing** ensures that once a rapid signal is detected, the trade is classified correctly and subsequent logic (exit, derisking) follows the rapid mode path.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L624-L627)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L897)

## Position Sizing and Risk Control

Despite the aggressive entry logic, Rapid Long Mode maintains strict risk controls through dynamic position sizing:

- **Stake Multiplier**: The `rapid_mode_stake_multiplier` limits exposure to 75% of the base stake, preventing overcommitment during volatile entries.
- **Max Slippage Control**: The parameter `max_slippage = 0.01` restricts entries to within 1% of the candle’s close, avoiding poor fills during flash spikes.
- **Capital Ratio Limit**: Although not explicitly named, the stake multiplier effectively enforces a `rapid_max_capital_ratio` of 0.75.

This ensures that even with fast execution, the strategy does not over-leverage on potentially false breakouts.

Additionally, the strategy checks for available free slots before entering new rapid trades, especially when combined with other modes like rebuy or grind.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L200-L205)

## Exit Strategy

Exit logic for Rapid Long Mode is designed for quick profit capture and loss containment:

- **Aggressive Take-Profit**: Targets are set tighter than in normal mode to secure gains rapidly.
- **Dynamic Trailing Stops**: While `trailing_stop` is globally set to `False`, the strategy implements custom dynamic exits based on momentum decay.
- **Derisking on Entry**: As soon as a rapid trade is opened, `derisk_enable = True` triggers immediate risk reduction protocols, such as preparing partial exits if momentum stalls.

The exit function evaluates conditions like RSI overbought levels (>80) or price rejection at upper Bollinger Bands to close positions swiftly.

```python
if current_profit > 0.05 and rsi_14 > 80:
    exit_trade(partial=True)
```

This prevents giving back profits during sudden reversals.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1726-L1731)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L2146-L2149)

## Interaction with Grinding and Derisking

Rapid Long Mode interacts selectively with other strategy components:

- **Grinding**: Typically **disabled** during rapid mode to avoid adding to a position that may be a false breakout. The strategy avoids using `grind_mode_stake_multiplier` or `grind_mode_coins` unless explicitly configured.
- **Derisking**: **Immediately active** post-entry. The `derisk_enable` flag ensures that protective measures like partial exits or tighter stops are engaged as soon as the trade is open.
- **Position Adjustment**: Enabled by default, but logic routes to rapid-specific adjustment functions to prevent conflict with grind or rebuy routines.

This selective interaction ensures that the strategy remains aggressive on entry but conservative on risk management.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L190-L195)

## Practical Example: Flash Rally on OKX Futures

**Scenario**: A major Layer 1 blockchain announces a successful mainnet upgrade. Within minutes, its token price on OKX Futures surges 15% with 3x average volume.

**Strategy Response**:
1. **Signal Detection**: The MACD histogram spikes above 0.5, and volume exceeds the 20-period average by 250%.
2. **Tag Assignment**: The condition `long_entry_condition_101` triggers, assigning tag `"101"` to the trade.
3. **Entry**: The strategy enters a long position with 75% of the base stake, respecting `max_slippage`.
4. **Derisk Activation**: Immediately after entry, derisking logic prepares a 50% take-profit at +5% and a hard stop at -20%.
5. **Exit**: Within 30 minutes, RSI reaches 85, triggering a partial exit. The remainder is closed as momentum fades.

This sequence demonstrates how Rapid Long Mode captures short-term alpha while minimizing exposure to reversal risk.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L624-L627)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L200-L210)

## Common Pitfalls and Tuning Tips

### Common Pitfalls
- **False Positives**: Rapid mode may trigger on pump-and-dump schemes. Solution: Add volume confirmation thresholds.
- **Slippage Risk**: High volatility can lead to poor fills. Solution: Lower `max_slippage` to `0.005` (0.5%) on less liquid pairs.
- **Overlapping Modes**: Conflicts between rapid, rebuy, and grind tags can cause unexpected behavior. Solution: Use exclusive tag logic.

### Tuning Tips
- **Signal Confirmation Window**: Introduce a 1-candle confirmation delay to filter noise, even in rapid mode.
- **Exchange-Specific Rate Limits**: Adjust polling frequency based on exchange API limits (e.g., OKX allows 24 requests/min, Bybit 60/min).
- **Enable Conditions Selectively**: Disable `long_entry_condition_104` if it generates too many false signals during low-volume periods.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L624-L627)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L200-L205)

## Performance Considerations

Optimal performance of Rapid Long Mode depends on several technical factors:

- **Co-location**: Running the bot on a server physically close to the exchange’s data center reduces latency.
- **API Priority**: Use WebSocket feeds instead of REST APIs for real-time data. Ensure `ccxt_async_config` is properly configured.
- **Data Feed Quality**: Low-latency, tick-level data is essential. Delayed or aggregated candles can cause missed entries.
- **Indicator Calculation Speed**: The parameter `num_cores_indicators_calc = 0` (auto) ensures efficient use of CPU resources during rapid signal processing.

For exchanges like **OKX**, which provide fewer candles per API call, the `startup_candle_count` is reduced to 480 to ensure timely initialization.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1000-L1010)