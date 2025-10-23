# Configuration Guide

<cite>
**Referenced Files in This Document**   
- [recommended_config.json](file://configs/recommended_config.json)
- [trading_mode-futures.json](file://configs/trading_mode-futures.json)
- [trading_mode-spot.json](file://configs/trading_mode-spot.json)
- [pairlist-volume-binance-usdt.json](file://configs/pairlist-volume-binance-usdt.json)
- [blacklist-binance.json](file://configs/blacklist-binance.json)
- [proxy-binance.json](file://configs/proxy-binance.json)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py)
</cite>

## Table of Contents
1. [Configuration Hierarchy and Override System](#configuration-hierarchy-and-override-system)
2. [Configuration File Structure](#configuration-file-structure)
3. [Pair List Management](#pair-list-management)
4. [Blacklist Configuration](#blacklist-configuration)
5. [Proxy Configuration](#proxy-configuration)
6. [Strategy Parameters and Custom Overrides](#strategy-parameters-and-custom-overrides)
7. [Best Practices and Common Pitfalls](#best-practices-and-common-pitfalls)

## Configuration Hierarchy and Override System

The configuration system in NostalgiaForInfinityX6 follows a hierarchical override model, where base settings are progressively refined by more specific configuration files. The root of this hierarchy is **recommended_config.json**, which defines the default strategy and includes a list of additional configuration files via the **add_config_files** parameter.

Each file listed in **add_config_files** is loaded in sequence, with later files overriding earlier ones. This allows for layered configuration where:
- Base parameters are defined in **recommended_config.json**
- Trading mode-specific settings (e.g., spot vs futures) are applied through files like **trading_mode-spot.json**
- Exchange-specific pair lists and blacklists are loaded
- User-specific overrides and secrets are incorporated last

For example, the **trading_mode-futures.json** file sets **trading_mode** to "futures" and configures isolated margin mode, which overrides any previous trading mode settings. This modular approach enables users to mix and match configuration components without modifying core files.

**Section sources**
- [recommended_config.json](file://configs/recommended_config.json#L0-L17)
- [trading_mode-futures.json](file://configs/trading_mode-futures.json#L0-L6)

## Configuration File Structure

Configuration files follow the JSON format and contain specific sections that control different aspects of the trading strategy. Key structural elements include:

### Timeframe Configuration
The **timeframe** parameter defines the candlestick interval used for analysis. In NostalgiaForInfinityX6, this is hardcoded to "5m" (5 minutes) in the strategy file, making it a critical parameter that should not be overridden in configuration files.

### Trade Management Parameters
- **max_open_trades**: Controls the maximum number of concurrent trades (not explicitly set in base config, allowing system defaults)
- **stoploss**: Set to -0.99 in the strategy, representing a 99% stop loss threshold
- **use_exit_signal**: Must be true to enable exit signals from the strategy
- **exit_profit_only**: Should be false to allow exits regardless of profit status
- **ignore_roi_if_entry_signal**: Should be true to prioritize entry signals over ROI targets

### Custom Parameters Section
The **custom_params** section (referred to as **nfi_parameters** in this implementation) allows advanced users to override specific strategy parameters. These include:
- **futures_mode_leverage**: Leverage setting for futures trading
- **grinding_enable**: Enables the grinding (averaging down) feature
- **position_adjustment_enable**: Allows position size adjustments
- **derisk_enable**: Enables risk reduction mechanisms

The strategy processes these parameters during initialization, validating them against a whitelist of safe parameters (**NFI_SAFE_PARAMETERS**) to prevent accidental modification of critical settings.

**Section sources**
- [recommended_config.json](file://configs/recommended_config.json#L0-L17)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L100-L150)

## Pair List Management

The system supports multiple pair list strategies to dynamically select trading pairs based on market conditions and user preferences.

### Volume-Ranked Dynamic Pair Lists
Files like **pairlist-volume-binance-usdt.json** implement a volume-based selection strategy that automatically updates the trading universe. The configuration includes:
- **VolumePairList**: Selects top N assets by quote volume
- **FullTradesFilter**: Ensures only pairs with full trade history are selected
- **AgeFilter**: Excludes pairs listed less than 60 days
- **PriceFilter**: Filters out very low-priced assets (low_price_ratio: 0.003)
- **SpreadFilter**: Excludes pairs with excessive bid-ask spread (max_spread_ratio: 0.005)
- **RangeStabilityFilter**: Ensures price stability over a lookback period

This multi-stage filtering creates a robust, liquid trading universe that adapts to market conditions. The **refresh_period** of 1800 seconds (30 minutes) ensures the pair list updates regularly without excessive API calls.

### Static Pair Lists
Static lists like **pairlist-static-binance-spot-usdt.json** contain predefined sets of trading pairs. These are useful for:
- Backtesting specific market conditions
- Focusing on particular asset categories
- Maintaining consistency across different runs

### Backtest-Specific Lists
Files prefixed with **pairlist-backtest-static-** are designed for backtesting scenarios, often containing historical pairs that may no longer be actively traded. These ensure backtests use realistic historical universes rather than current market availability.

**Section sources**
- [pairlist-volume-binance-usdt.json](file://configs/pairlist-volume-binance-usdt.json#L0-L40)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L80-L90)

## Blacklist Configuration

Blacklists prevent the strategy from trading undesirable pairs that could introduce risk or complexity. Exchange-specific blacklist files (e.g., **blacklist-binance.json**) contain regex patterns that match problematic trading pairs.

The Binance blacklist includes filters for:
- **Leveraged tokens**: Patterns matching *BULL, *BEAR, *UP, *DOWN, etc.
- **Stablecoins**: Excludes various USD-pegged and other stablecoins
- **Fiat pairs**: Removes currency pairs involving traditional currencies
- **Specific tokens**: A comprehensive list of tokens deemed unsuitable for trading
- **Delisted assets**: Excludes assets that have been removed from the exchange

The blacklist is implemented as a list of regular expressions under **exchange.pair_blacklist**. Each pattern is evaluated against potential trading pairs, and any match results in exclusion from the trading universe.

This approach provides fine-grained control over trading pairs while maintaining compatibility with Freqtrade's configuration system.

**Section sources**
- [blacklist-binance.json](file://configs/blacklist-binance.json#L0-L21)

## Proxy Configuration

Proxy configurations like **proxy-binance.json** enable connectivity in regions with network restrictions. The configuration modifies CCXT (CryptoCurrency eXchange Trading) library settings to route traffic through appropriate channels.

Key settings include:
- **enableRateLimit**: Enables rate limiting to prevent API bans
- **rateLimit**: Sets request interval to 200ms
- **aiohttp_trust_env**: Allows the async HTTP client to trust environment proxy settings

These settings ensure reliable connectivity while respecting exchange API rate limits. The configuration is applied to both synchronous and asynchronous CCXT instances, ensuring consistent behavior across all trading operations.

**Section sources**
- [proxy-binance.json](file://configs/proxy-binance.json#L0-L14)

## Strategy Parameters and Custom Overrides

The strategy implements a sophisticated system for managing entry modes and trading behavior through configuration parameters.

### Entry Mode Control
The **config['entry_mode']** parameter (implemented through **long_entry_signal_params** and **short_entry_signal_params** dictionaries) controls which trading conditions are active. Each entry condition has an associated enable flag (e.g., **long_entry_condition_1_enable**). When set to true, the corresponding trading logic is activated.

This modular approach allows users to:
- Enable specific trading strategies (normal, pump, quick, rebuy modes)
- Disable underperforming strategies
- Test new strategies without affecting existing ones
- Create custom combinations of entry conditions

### Advanced Override Mechanisms
The system supports nested dictionary overrides through the **nfi_parameters** section. This allows users to modify complex parameters like grinding strategies, rebuy thresholds, and profit targets without code changes.

For example, the grinding system has multiple levels (grind_1 through grind_6) with separate settings for spot and futures trading:
- **stakes**: Position sizes for each grind level
- **thresholds**: Price drop percentages that trigger additional buys
- **profit_threshold**: Minimum profit required before exiting
- **stop_grinds**: Maximum loss threshold before stopping the grinding process

These parameters can be overridden individually, allowing fine-tuned control over risk management behavior.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L150-L200)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L2000-L2100)

## Best Practices and Common Pitfalls

### Configuration Best Practices
1. **Maintain Modularity**: Keep configuration files focused on specific concerns (trading mode, exchange, pair selection)
2. **Use Version Control**: Track configuration changes to understand performance differences
3. **Test Overrides**: Validate custom parameter changes in dry-run mode before live trading
4. **Document Changes**: Add comments explaining the rationale for non-default settings

### Common Configuration Pitfalls
1. **Overriding Critical Parameters**: Changing **timeframe** or **strategy** name can break the system
2. **Conflicting Settings**: Enabling both spot and futures trading modes simultaneously
3. **Excessive API Calls**: Setting very short refresh periods on pair lists
4. **Insufficient Filtering**: Using volume-based pair lists without age or spread filters
5. **Inadequate Blacklisting**: Failing to exclude leveraged tokens on exchanges that offer them

### Debugging Techniques
1. **Check Logs**: Monitor strategy initialization logs for parameter change notifications
2. **Validate Configuration**: Use Freqtrade's configuration validation tools
3. **Test Incrementally**: Apply configuration changes one at a time
4. **Monitor Pair Selection**: Verify the actual trading universe matches expectations
5. **Review Override Warnings**: Pay attention to warnings about invalid or unsafe parameters

Following these guidelines ensures a stable, predictable trading environment while leveraging the full flexibility of the hierarchical configuration system.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1000-L1100)
- [recommended_config.json](file://configs/recommended_config.json#L0-L17)