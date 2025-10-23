# Trading Modes

<cite>
**Referenced Files in This Document**   
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py)
</cite>

## Table of Contents
1. [Trading Modes Overview](#trading-modes-overview)
2. [Mode Selection and Configuration](#mode-selection-and-configuration)
3. [Normal Mode](#normal-mode)
4. [Pump Mode](#pump-mode)
5. [Quick Mode](#quick-mode)
6. [Rebuy Mode](#rebuy-mode)
7. [Rapid Mode](#rapid-mode)
8. [Grind Mode](#grind-mode)
9. [Scalp Mode](#scalp-mode)
10. [Position Management and Mode Interaction](#position-management-and-mode-interaction)
11. [Mode-Specific Parameters](#mode-specific-parameters)
12. [Common Issues and Best Practices](#common-issues-and-best-practices)

## Trading Modes Overview

The NostalgiaForInfinityX6 strategy implements a comprehensive multi-mode trading system designed to adapt to different market conditions and risk profiles. Each trading mode represents a distinct approach to market entry, position management, and exit strategy. The modes are implemented through a tagging system that assigns specific numerical identifiers to trades, allowing the strategy to apply mode-specific logic for entry conditions, stop-loss behavior, take-profit targets, and position adjustments.

The strategy supports both long and short positions across all modes, with separate parameter sets and logic paths for each direction. This modular design enables traders to fine-tune their approach based on market regime, volatility levels, and risk tolerance. The modes are designed to work independently or in combination, though certain modes are mutually exclusive due to conflicting position management philosophies.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L150-L225)

## Mode Selection and Configuration

Trading modes in NostalgiaForInfinityX6 are selected through configuration parameters that determine which entry conditions are enabled and how position adjustments are handled. The primary mechanism for mode selection is through the `entry_mode` configuration parameter, which maps to specific sets of entry condition tags.

Each mode is associated with a unique set of numerical tags that are assigned to trades when specific entry conditions are met. These tags then determine which exit functions and position adjustment functions are called during the trade lifecycle. The mode selection process occurs in the `populate_entry_trend` method, where different entry conditions are evaluated based on the configured mode.

```python
# Mode tag definitions in NostalgiaForInfinityX6.py
long_normal_mode_tags = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]
long_pump_mode_tags = ["21", "22", "23", "24", "25", "26"]
long_quick_mode_tags = ["41", "42", "43", "44", "45", "46", "47", "48", "49", "50", "51", "52", "53"]
long_rebuy_mode_tags = ["61", "62"]
long_rapid_mode_tags = ["101", "102", "103", "104", "105", "106", "107", "108", "109", "110"]
long_grind_mode_tags = ["120"]
long_scalp_mode_tags = ["161", "162", "163"]
```

The configuration system allows for both simple mode selection and advanced parameter tuning. Traders can enable or disable specific entry conditions through the `long_entry_signal_params` and `short_entry_signal_params` dictionaries in the configuration. This provides granular control over which market signals trigger entries for each mode.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L150-L225)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1150-L1200)

## Normal Mode

Normal mode serves as the baseline trend-following strategy in NostalgiaForInfinityX6. It is designed for standard market conditions where price movements follow established trends with moderate volatility. This mode implements a conservative approach to entries and exits, focusing on capturing sustained price movements while minimizing false signals.

The Normal mode uses entry tags 1-13 and is activated when the corresponding entry conditions are enabled in the configuration. It relies on a combination of technical indicators including moving averages, RSI, and Bollinger Bands to identify trend direction and momentum. The entry logic typically requires confirmation across multiple timeframes to reduce the risk of entering during market noise or consolidation periods.

For long positions, Normal mode looks for bullish trend confirmation with increasing volume and positive momentum indicators. For short positions, it seeks bearish trend confirmation with decreasing volume and negative momentum indicators. The stop-loss and take-profit levels are set at moderate distances from the entry price, balancing risk-reward ratio with the probability of being stopped out by normal market fluctuations.

Normal mode is suitable for traders with moderate risk tolerance who prefer a balanced approach to position sizing and trade duration. It performs best in trending markets and may experience drawdowns during sideways or choppy market conditions.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L150-L160)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1150-L1200)

## Pump Mode

Pump mode is specifically designed for high-volatility momentum trading, targeting rapid price increases often seen during market pumps or strong breakout events. This aggressive mode uses entry tags 21-26 and is optimized for capturing short-term momentum spikes in both directions.

The Pump mode logic focuses on identifying extreme momentum conditions through indicators such as RSI divergence, volume spikes, and price acceleration. For long entries, it looks for assets showing strong upward momentum with increasing volume and bullish divergence on lower timeframes. For short entries, it targets assets showing signs of exhaustion after rapid price increases, with bearish divergence and decreasing volume.

Position sizing in Pump mode is typically smaller than in Normal mode to account for the higher risk associated with momentum trading. Stop-loss levels are set closer to the entry price to protect against sudden reversals, while take-profit targets are set at levels that capture the expected momentum extension.

This mode is most effective during periods of high market volatility and should be used cautiously during stable market conditions, as it may generate frequent false signals. Traders using Pump mode should have a higher risk tolerance and be prepared for potentially larger drawdowns in exchange for the possibility of higher returns during strong trending markets.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L153-L155)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1150-L1200)

## Quick Mode

Quick mode implements a fast-entry and fast-exit strategy designed for traders who prefer shorter holding periods and quicker turnover of positions. Using entry tags 41-53, this mode focuses on capturing short-term price movements with rapid execution and tight risk management.

The Quick mode logic emphasizes speed of execution and responsiveness to changing market conditions. It uses shorter-term indicators and more sensitive parameters to identify entry opportunities that may be missed by slower strategies. For long positions, it looks for quick bullish reversals or breakouts with immediate follow-through. For short positions, it targets quick bearish reversals or breakdowns with strong momentum.

Position sizing in Quick mode is typically moderate, with stop-loss levels set very close to the entry price to minimize potential losses on individual trades. Take-profit targets are also set at relatively close levels, aiming for a high win rate with smaller profits per trade. This approach is designed to generate consistent returns through frequent, small gains while minimizing the impact of losing trades.

Quick mode is suitable for traders with a higher risk tolerance who can actively monitor their positions and are comfortable with a higher frequency of trades. It performs best in markets with consistent volatility and clear short-term trends, but may struggle during periods of low volatility or choppy price action.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L156-L158)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1150-L1200)

## Rebuy Mode

Rebuy mode implements a cost-averaging strategy that allows for additional entries at lower prices to reduce the average entry cost of a position. This mode uses entry tags 61-62 and is designed to improve risk-reward ratios by building positions incrementally during price corrections.

The Rebuy mode logic is triggered when a position moves against the trader by a predetermined threshold, typically around 8-10%. When this occurs, the strategy places additional buy orders (for long positions) or sell orders (for short positions) to average down the entry price. This approach can significantly improve profitability when the market eventually moves in the expected direction.

For long positions, Rebuy mode looks for oversold conditions or support levels where price is likely to reverse upward. For short positions, it targets overbought conditions or resistance levels where price is likely to reverse downward. The additional entries are sized according to the `rebuy_mode_stakes` parameter, which determines the stake multiplier for each rebuy.

Rebuy mode includes specific risk management features to prevent excessive exposure. The `rebuy_mode_min_free_slots` parameter limits the number of concurrent rebuy trades, while the `rebuy_mode_derisk` parameter defines the profit threshold at which the position should be exited to lock in gains. This mode is most effective in ranging or mildly trending markets where price frequently retraces before continuing in the primary direction.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L159-L161)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L2213-L2412)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L39323-L39500)

## Rapid Mode

Rapid mode is an aggressive scalping strategy designed for ultra-short-term trading with very quick entry and exit cycles. Using entry tags 101-110, this mode targets small price movements with high frequency, aiming to accumulate profits through numerous small wins.

The Rapid mode logic focuses on identifying immediate price imbalances and order flow anomalies that can be exploited for quick profits. It uses highly sensitive indicators and very short lookback periods to detect entry opportunities that may last only a few candles. For long positions, it looks for rapid bullish momentum with strong volume support. For short positions, it targets rapid bearish momentum with increasing selling pressure.

Position sizing in Rapid mode is typically small to moderate, with extremely tight stop-loss levels placed just beyond recent swing points. Take-profit targets are set at very close levels, often just enough to cover trading fees and provide a small profit. This approach prioritizes capital preservation and high win rate over large individual gains.

Rapid mode is suitable for traders with a high risk tolerance and the ability to monitor markets closely. It performs best in highly liquid markets with consistent volatility, but can generate excessive transaction costs and slippage in less liquid markets. The mode includes specific parameters like `rapid_mode_stake_multiplier` to control position sizing and `stop_threshold_rapid` to manage risk exposure.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L163-L165)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1150-L1200)

## Grind Mode

Grind mode implements a mean-reversion strategy specifically designed for ranging markets where prices oscillate between support and resistance levels. This mode uses entry tag 120 and focuses on profiting from price reversals at technical levels rather than following trends.

The Grind mode logic identifies potential reversal points through a combination of technical indicators including RSI, Stochastic, and price action patterns. For long positions, it looks for oversold conditions near established support levels. For short positions, it targets overbought conditions near established resistance levels. The strategy then places entries with the expectation that price will revert to the mean or midpoint of the range.

Grind mode includes sophisticated position management features through the `long_grind_adjust_trade_position` and `short_grind_adjust_trade_position` functions. These functions implement a multi-tiered approach to position adjustment, with different stake sizes and profit thresholds for each "grind" level. The `grind_mode_coins` parameter allows traders to specify which assets are eligible for this mode, typically focusing on those with established trading ranges.

Risk management in Grind mode is critical due to the inherent risk of trading against the trend. The strategy includes multiple stop-loss levels and profit targets to protect against breakout moves that invalidate the range hypothesis. The `grind_mode_max_slots` parameter limits the number of concurrent grind trades to prevent overexposure to range-bound assets.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L166-L170)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L2213-L2412)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L35655-L36000)

## Scalp Mode

Scalp mode is an ultra-short-term trading strategy designed for capturing very small price movements with minimal holding time. Using entry tags 161-163, this mode targets intrabar price fluctuations and order book imbalances to generate frequent, small profits.

The Scalp mode logic focuses on identifying immediate supply and demand imbalances through order book analysis and very short-term price action. For long positions, it looks for rapid price increases with strong buying pressure and low resistance above. For short positions, it targets rapid price decreases with strong selling pressure and low support below. The strategy enters and exits positions within minutes or even seconds, depending on market conditions.

Position sizing in Scalp mode is typically small to minimize risk on each trade, with extremely tight stop-loss levels placed just beyond recent price extremes. Take-profit targets are set at minimal levels, often just enough to cover transaction costs and provide a small profit. This approach aims for a very high win rate to generate consistent returns over time.

Scalp mode includes specific parameters to manage its unique risk profile. The `min_free_slots_scalp_mode` parameter ensures sufficient capital is available for scalp opportunities, while the `stop_threshold_scalp` parameter defines the maximum allowable loss before exiting a position. This mode is most effective in highly liquid markets with tight bid-ask spreads and consistent volatility.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L171-L173)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1150-L1200)

## Position Management and Mode Interaction

The NostalgiaForInfinityX6 strategy implements sophisticated position management features that interact with trading modes to optimize risk and return. The `adjust_trade_position` method serves as the central hub for position adjustments, routing trades to mode-specific adjustment functions based on their entry tags.

```python
def adjust_trade_position(
    self,
    trade: Trade,
    current_time: datetime,
    current_rate: float,
    current_profit: float,
    min_stake: Optional[float],
    max_stake: float,
    current_entry_rate: float,
    current_exit_rate: float,
    current_entry_profit: float,
    current_exit_profit: float,
    **kwargs,
):
    if self.position_adjustment_enable == False:
        return None

    enter_tag = "empty"
    if hasattr(trade, "enter_tag") and trade.enter_tag is not None:
        enter_tag = trade.enter_tag
    enter_tags = enter_tag.split()

    is_backtest = self.is_backtest_mode()
    is_long_grind_mode = all(c in self.long_grind_mode_tags for c in enter_tags)
    is_short_grind_mode = all(c in self.short_grind_mode_tags for c in enter_tags)
    is_v2_date = trade.open_date_utc.replace(tzinfo=None) >= datetime(2025, 2, 13) or is_backtest

    # Rebuy mode
    if not trade.is_short and (
        all(c in self.long_rebuy_mode_tags for c in enter_tags)
        or (
            any(c in self.long_rebuy_mode_tags for c in enter_tags)
            and all(c in (self.long_rebuy_mode_tags + self.long_grind_mode_tags) for c in enter_tags)
        )
    ):
        return self.long_rebuy_adjust_trade_position(
            trade,
            enter_tags,
            current_time,
            current_rate,
            current_profit,
            min_stake,
            max_stake,
            current_entry_rate,
            current_exit_rate,
            current_entry_profit,
            current_exit_profit,
        )
```

The position management system includes several key features that interact with trading modes:

- **Grinding**: A cost-averaging technique that adds to positions at predetermined price levels below (for longs) or above (for shorts) the initial entry. This is implemented through mode-specific grinding functions that calculate optimal stake sizes and entry prices.

- **Derisking**: A risk reduction mechanism that partially exits positions when they reach certain profit thresholds or when market conditions change. This helps lock in gains and reduce exposure to adverse price movements.

- **Stops**: Various stop-loss mechanisms including regular stops, doom stops, and U/E stops that automatically exit positions when predefined loss thresholds are reached.

Certain modes have exclusive interactions that prevent them from being combined. For example, Rebuy mode and Grind mode are mutually exclusive because they implement different approaches to position averaging. The strategy enforces these exclusivities through conditional logic in the `adjust_trade_position` method.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L2213-L2412)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L35655-L36000)

## Mode-Specific Parameters

Each trading mode in NostalgiaForInfinityX6 has a dedicated set of parameters that control its behavior, risk profile, and performance characteristics. These parameters are defined as class attributes and can be overridden through the strategy configuration.

The parameter structure follows a consistent naming convention that includes the mode name, parameter type, and market type (spot or futures). For example, `grind_1_stakes_spot` defines the stake sizes for the first grind level in spot markets, while `grind_1_stakes_futures` defines the same parameter for futures markets.

Key parameter categories include:

- **Stake multipliers**: Control position sizing relative to the initial entry, such as `rebuy_mode_stake_multiplier` and `rapid_mode_stake_multiplier`.

- **Profit thresholds**: Define minimum profit levels for exiting positions or triggering partial sells, such as `grind_1_profit_threshold_spot`.

- **Stop thresholds**: Set maximum loss levels before exiting positions, such as `stop_threshold_spot` and `stop_threshold_futures`.

- **Sub-thresholds**: Define intermediate price levels for position adjustments, such as `grind_1_sub_thresholds_spot`.

- **Stake distributions**: Specify how capital is allocated across multiple entries, such as `grind_1_stakes_spot` and `grind_1_stakes_futures`.

These parameters are tuned based on extensive backtesting to optimize risk-reward ratios for each mode. Traders can adjust them through the configuration system to align with their risk tolerance and market expectations. The parameters are also differentiated between spot and futures trading to account for differences in leverage, fees, and market dynamics.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L226-L500)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L35655-L36000)

## Common Issues and Best Practices

Several common issues can arise when using the multi-mode trading system in NostalgiaForInfinityX6, particularly related to mode switching, parameter conflicts, and performance degradation in unsuitable market conditions.

**Mode switching during active trades**: One potential issue is changing the active trading mode while positions are open. This can lead to inconsistent behavior as the strategy may apply logic from the previous mode while new entries follow the new mode. Best practice is to avoid changing modes until all positions are closed, or to use separate strategy instances for different modes.

**Performance degradation in unsuitable markets**: Each mode is optimized for specific market conditions, and using a mode in an unsuitable market can lead to poor performance. For example, Trend mode may generate frequent losses in ranging markets, while Grind mode can suffer significant drawdowns in strongly trending markets. Regular market regime analysis is recommended to select the most appropriate mode.

**Parameter conflicts**: When combining modes or adjusting parameters, conflicts can arise that degrade performance. For example, setting stop-loss levels too tight for a volatile mode like Pump can result in premature exits. Best practice is to test parameter changes thoroughly in backtesting before deploying in live trading.

**Best practices for mode selection**:
- Use Normal mode for moderate volatility and trending markets
- Use Pump mode for high-volatility breakout situations
- Use Quick mode for active trading with shorter holding periods
- Use Rebuy mode for cost averaging in volatile but range-bound assets
- Use Rapid mode for aggressive scalping in highly liquid markets
- Use Grind mode for mean-reversion trading in established ranges
- Use Scalp mode for ultra-short-term trading with high frequency

Traders should align their mode selection with their risk tolerance, time horizon, and market outlook. Regular performance review and parameter optimization are essential for maintaining optimal results across changing market conditions.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L150-L225)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L2213-L2412)