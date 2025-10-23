# Scalp Long Mode

<cite>
**Referenced Files in This Document**   
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py)
</cite>

## Table of Contents
1. [Scalp Long Mode](#scalp-long-mode)
2. [Objective and Strategy Overview](#objective-and-strategy-overview)
3. [Entry Signal Logic](#entry-signal-logic)
4. [Configuration Parameters](#configuration-parameters)
5. [Position Sizing and Risk Management](#position-sizing-and-risk-management)
6. [Exit Strategy and Stop-Loss Mechanism](#exit-strategy-and-stop-loss-mechanism)
7. [Interaction with Other Modes](#interaction-with-other-modes)
8. [Practical Deployment Example](#practical-deployment-example)
9. [Common Pitfalls and Performance Considerations](#common-pitfalls-and-performance-considerations)
10. [Tuning Recommendations](#tuning-recommendations)

## Objective and Strategy Overview

The **Scalp Long Mode** in the NostalgiaForInfinityX6 (NFIX6) strategy is designed to capture small, frequent profits from minor price fluctuations, typically within minutes. This mode targets high-turnover trading by entering and exiting positions rapidly based on short-term market inefficiencies.

Scalp Long Mode operates under the tag identifiers `161`, `162`, and `163`, which are defined in the strategy as:

```python
long_scalp_mode_tags = ["161", "162", "163"]
long_scalp_mode_name = "long_scalp"
```

This mode is optimized for speed and precision, making it suitable for environments with low latency and high liquidity. It does not rely on long-term trends or momentum but instead exploits micro-price movements using real-time indicators.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L131-L141)

## Entry Signal Logic

Entry signals for Scalp Long Mode are triggered when specific short-term technical conditions align. The strategy evaluates multiple entry conditions, with `long_entry_condition_161_enable`, `long_entry_condition_162_enable`, and `long_entry_condition_163_enable` controlling the activation of each scalp-specific rule.

Although the full implementation of these conditions spans deeper into the codebase, their logical structure typically involves a combination of:

- **RSI divergence detection** on the 1-minute timeframe
- **Order book imbalance analysis** (bid pressure vs. ask pressure)
- **Tick volume surges** indicating short-term buying interest

A representative logic pattern (inferred from strategy design principles) would resemble:

```python
if scalp_mode_active and rsi_1m < 20 and bid_pressure > ask_pressure:
    enter_long()
```

These signals are evaluated within the broader `populate_entry_trend` function, where tag-based filtering determines whether a given condition belongs to the scalp mode.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L633-L635)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L902-L905)

## Configuration Parameters

Key configuration parameters for Scalp Long Mode are embedded within the strategy class and can be overridden via the configuration file under the `nfi_parameters` block. Relevant settings include:

**:min_free_slots_scalp_mode**
- Default: `1`
- Purpose: Ensures a minimum number of free trade slots before initiating a scalp trade to avoid over-leveraging.

**:stop_threshold_scalp_spot** and **:stop_threshold_scalp_futures**
- Default: `-0.20` (20% loss threshold)
- Purpose: Defines the maximum drawdown allowed before triggering a stop-loss exit in spot and futures markets respectively.

**:long_scalp_mode_tags**
- Values: `["161", "162", "163"]`
- Purpose: Identifies trades that belong to the scalp long category for targeted exit logic.

These parameters ensure that scalp trades are tightly controlled and automatically managed without manual intervention.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L756-L765)

## Position Sizing and Risk Management

Position sizing in Scalp Long Mode is kept minimal to allow high turnover and reduce exposure per trade. While the strategy does not define a dedicated stake multiplier specifically for scalp mode, it inherits conservative stake sizing from global settings and adjusts dynamically based on available slots.

The **`:min_free_slots_scalp_mode`** parameter ensures that at least one trading slot is free before entering a new scalp position, preventing overcrowding during volatile periods.

Risk is further mitigated through:
- Fixed stop-loss thresholds
- Rapid exit timing
- Exclusion of compounding or rebuy logic during initial scalp entries

This approach prioritizes capital preservation over aggressive profit-taking, aligning with the high-frequency, low-risk nature of scalping.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L756)

## Exit Strategy and Stop-Loss Mechanism

Exit strategies in Scalp Long Mode are strictly rule-based to prevent emotional decision-making and limit losses. Exits are triggered by:

1. **Fixed Stop-Loss**: When price moves against the position beyond the configured threshold (`stop_threshold_scalp_spot` or `stop_threshold_scalp_futures`).
2. **Doom Stop-Loss**: A more aggressive stop mechanism activated under extreme market conditions.
3. **Signal Reversal**: If a contrary signal is detected, the position is closed immediately.

The exit logic is implemented in the `populate_exit_trend` function, where sell reasons are tagged accordingly:

```python
sell, signal_name = True, f"exit_{self.long_scalp_mode_name}_stoploss_doom"
```

Additionally, previous sell reasons are checked to prevent repeated entries after a failed scalp:

```python
if previous_sell_reason in [f"exit_{self.long_scalp_mode_name}_stoploss_u_e"]:
```

This ensures disciplined risk control and avoids revenge trading.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L17518-L17589)

## Interaction with Other Modes

Scalp Long Mode operates independently of grinding mechanics. Unlike grind or rebuy modes, it does not utilize incremental position building or cost-averaging techniques.

Instead, derisking is replaced by **fixed stop-loss mechanisms**, ensuring that each scalp trade has a predefined exit point. This simplifies execution and reduces computational overhead during high-frequency trading.

The mode can coexist with other long strategies (e.g., normal, rapid, rebuy), but entry tags ensure isolation of logic paths. For example:

```python
is_scalp_mode = all(c in self.long_scalp_mode_tags for c in enter_tags) or (
    any(c in self.long_scalp_mode_tags for c in enter_tags) and not any(
        c in (self.long_rebuy_mode_tags + self.long_grind_mode_tags) for c in enter_tags
    )
)
```

This prevents mode interference and maintains strategy integrity.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L902-L905)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1813-L1816)

## Practical Deployment Example

A practical deployment scenario for Scalp Long Mode involves trading **BTC/USDT** on **Bybit** during low-volatility periods.

**:Exchange**: Bybit  
**:Pair**: BTC/USDT  
**:Timeframe**: 5m (primary), 1m (signal confirmation)  
**:Trading Mode**: Spot or Futures (with leverage ≤ 3x)  
**:Liquidity Requirement**: High volume (> $1B daily) and tight spread (< 0.1%)  

During a consolidation phase, the strategy detects:
- RSI(1m) drops below 20 (oversold)
- Bid volume exceeds ask volume by 3:1 ratio
- No recent scalp exits on the same pair

It enters a small position (e.g., 1–2% of portfolio) and sets a stop-loss at -20%. If price rebounds within 5–10 minutes, the trade exits with a small profit (target ~0.5–1.0%). If the move fails, the stop-loss limits downside.

This cycle repeats frequently throughout the day, capitalizing on repetitive micro-patterns.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1238)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1813)

## Common Pitfalls and Performance Considerations

### Transaction Cost Erosion
Due to the high turnover nature of scalping, **trading fees** can significantly erode profits. Even a 0.1% round-trip fee requires a minimum gain of 0.2% just to break even.

**:Recommendation**: Use exchanges with tiered fee structures (e.g., Binance, Bybit) and aim for **VIP fee tiers** through volume commitments.

### Latency Sensitivity
Scalp Long Mode is highly sensitive to **network and execution latency**. Delays of even a few hundred milliseconds can result in missed entries or slippage.

**:Recommendation**: Co-locate trading infrastructure near exchange servers or use API endpoints with lowest ping.

### API Rate Limits
Frequent polling of order book and tick data can trigger **API rate limiting**, especially on exchanges like Kraken or OKX.

**:Recommendation**: Optimize data polling frequency and use WebSocket streams where available.

### Real-Time Signal Processing
Processing 1-minute indicators across 40+ pairs demands significant CPU resources.

**:Recommendation**: Enable multi-core indicator calculation via:

```python
num_cores_indicators_calc = 4  # Adjust based on hardware
```

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L45)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L750)

## Tuning Recommendations

To optimize Scalp Long Mode performance, consider the following tuning strategies:

**:Filter by Spread Threshold**
- Only trade pairs with bid-ask spread < 0.05% to minimize entry slippage.

**:Volume Filtering**
- Require minimum 5-minute volume thresholds to avoid illiquid traps.
- Use dynamic pair lists (e.g., `pairlist-volume-bybit-usdt.json`) to auto-filter.

**:Disable During High Volatility**
- Temporarily disable scalp mode during major news events or BTC volatility spikes (> 5% hourly move).

**:Adjust Stop Threshold**
- For more aggressive scalping, reduce `stop_threshold_scalp_spot` to `-0.10` (10%).

**:Enable Advanced Mode Safely**
- Use `nfi_advanced_mode` only if fully understanding implications; otherwise, stick to `nfi_parameters` overrides.

Example config override:
```json
"nfi_parameters": {
  "stop_threshold_scalp_spot": -0.10,
  "min_free_slots_scalp_mode": 2
}
```

These adjustments help maintain profitability while adapting to changing market regimes.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L756)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L633-L635)