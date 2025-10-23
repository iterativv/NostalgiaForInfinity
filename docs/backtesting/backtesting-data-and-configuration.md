# Backtesting Data and Configuration

<cite>
**Referenced Files in This Document**   
- [configs/pairlist-backtest-static-binance-spot-usdt.json](file://configs/pairlist-backtest-static-binance-spot-usdt.json)
- [configs/pairlist-backtest-static-binance-futures-usdt.json](file://configs/pairlist-backtest-static-binance-futures-usdt.json)
- [configs/pairlist-backtest-static-gateio-spot-usdt.json](file://configs/pairlist-backtest-static-gateio-spot-usdt.json)
- [configs/pairlist-backtest-static-gateio-futures-usdt.json](file://configs/pairlist-backtest-static-gateio-futures-usdt.json)
- [configs/pairlist-backtest-static-kucoin-spot-usdt.json](file://configs/pairlist-backtest-static-kucoin-spot-usdt.json)
- [configs/pairlist-backtest-static-okx-spot-usdt.json](file://configs/pairlist-backtest-static-okx-spot-usdt.json)
- [configs/pairlist-backtest-static-okx-futures-usdt.json](file://configs/pairlist-backtest-static-okx-futures-usdt.json)
- [configs/pairlist-backtest-static-focus-group-binance-spot-usdt.json](file://configs/pairlist-backtest-static-focus-group-binance-spot-usdt.json)
- [configs/pairlist-backtest-static-focus-group-gateio-spot-usdt.json](file://configs/pairlist-backtest-static-focus-group-gateio-spot-usdt.json)
- [configs/pairlist-backtest-static-focus-group-kucoin-spot-usdt.json](file://configs/pairlist-backtest-static-focus-group-kucoin-spot-usdt.json)
- [configs/pairlist-backtest-static-focus-group-okx-spot-usdt.json](file://configs/pairlist-backtest-static-focus-group-okx-spot-usdt.json)
- [tests/backtests/pairs-available-binance-spot-usdt-2017.json](file://tests/backtests/pairs-available-binance-spot-usdt-2017.json)
- [tests/backtests/pairs-available-binance-spot-usdt-2018.json](file://tests/backtests/pairs-available-binance-spot-usdt-2018.json)
- [tests/backtests/pairs-available-binance-spot-usdt-2019.json](file://tests/backtests/pairs-available-binance-spot-usdt-2019.json)
- [tests/backtests/pairs-available-binance-spot-usdt-2020.json](file://tests/backtests/pairs-available-binance-spot-usdt-2020.json)
- [tests/backtests/pairs-available-binance-spot-usdt-2021.json](file://tests/backtests/pairs-available-binance-spot-usdt-2021.json)
- [tests/backtests/pairs-available-binance-spot-usdt-2022.json](file://tests/backtests/pairs-available-binance-spot-usdt-2022.json)
- [tests/backtests/pairs-available-binance-spot-usdt-2023.json](file://tests/backtests/pairs-available-binance-spot-usdt-2023.json)
- [tests/backtests/pairs-available-binance-futures-usdt-2019.json](file://tests/backtests/pairs-available-binance-futures-usdt-2019.json)
- [tests/backtests/pairs-available-binance-futures-usdt-2020.json](file://tests/backtests/pairs-available-binance-futures-usdt-2020.json)
- [tests/backtests/pairs-available-binance-futures-usdt-2021.json](file://tests/backtests/pairs-available-binance-futures-usdt-2021.json)
- [tests/backtests/pairs-available-binance-futures-usdt-2022.json](file://tests/backtests/pairs-available-binance-futures-usdt-2022.json)
- [tests/backtests/pairs-available-binance-futures-usdt-2023.json](file://tests/backtests/pairs-available-binance-futures-usdt-2023.json)
- [tests/backtests/helpers.py](file://tests/backtests/helpers.py)
- [tests/backtests/backtesting-focus-group.sh](file://tests/backtests/backtesting-focus-group.sh)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Static Pair Lists for Backtesting](#static-pair-lists-for-backtesting)
3. [Focus Group Testing Configuration](#focus-group-testing-configuration)
4. [Year-Specific Pair Availability Files](#year-specific-pair-availability-files)
5. [Integration with Freqtrade Backtesting Engine](#integration-with-freqtrade-backtesting-engine)
6. [Customization and Validation of Pair Lists](#customization-and-validation-of-pair-lists)
7. [Best Practices for Data Accuracy and Maintenance](#best-practices-for-data-accuracy-and-maintenance)
8. [Common Configuration Errors and Troubleshooting](#common-configuration-errors-and-troubleshooting)

## Introduction
This document provides a comprehensive overview of the backtesting data configuration and pair availability management system used in the NostalgiaForInfinity repository. It details how static pair lists are structured, how year-specific availability files ensure historical accuracy, and how these components integrate with the Freqtrade backtesting engine to prevent lookahead bias. The documentation also covers best practices for maintaining data integrity and avoiding common configuration pitfalls.

**Section sources**
- [configs/pairlist-backtest-static-binance-spot-usdt.json](file://configs/pairlist-backtest-static-binance-spot-usdt.json)
- [tests/backtests/helpers.py](file://tests/backtests/helpers.py)

## Static Pair Lists for Backtesting

### Exchange-Specific and Market-Type Variations
The repository contains static pair list configuration files for multiple exchanges and market types (spot vs. futures). These JSON files define the `pair_whitelist` parameter used during backtesting to specify which trading pairs should be included in the analysis.

Each file follows a consistent structure:
```json
{
  "exchange": {
    "name": "binance",
    "pair_whitelist": [
      "BTC/USDT",
      "ETH/USDT",
      "ADA/USDT"
    ]
  },
  "pairlists": [
    {
      "method": "StaticPairList"
    }
  ]
}
```

The naming convention for these files is standardized:
- `pairlist-backtest-static-{exchange}-{market_type}-usdt.json`
- Supported exchanges include: Binance, GateIO, KuCoin, OKX, Bybit, Kraken
- Market types: spot, futures

For example:
- `pairlist-backtest-static-binance-spot-usdt.json`
- `pairlist-backtest-static-gateio-futures-usdt.json`

These static lists ensure consistent backtesting conditions across different runs and prevent dynamic pair selection that could introduce bias.

**Section sources**
- [configs/pairlist-backtest-static-binance-spot-usdt.json](file://configs/pairlist-backtest-static-binance-spot-usdt.json)
- [configs/pairlist-backtest-static-binance-futures-usdt.json](file://configs/pairlist-backtest-static-binance-futures-usdt.json)
- [configs/pairlist-backtest-static-gateio-spot-usdt.json](file://configs/pairlist-backtest-static-gateio-spot-usdt.json)

## Focus Group Testing Configuration

### Purpose and Structure
Focus group testing uses specialized pair lists designed to evaluate strategy performance on specific subsets of trading pairs. These configurations are used to identify potential weaknesses or "bad buys" in the trading strategy.

The focus group pair lists are located in the `tests/backtests/` directory and follow the naming pattern:
- `pairlist-backtest-static-focus-group-{exchange}-{market_type}-usdt.json`

Example content from `pairlist-backtest-static-focus-group-binance-spot-usdt.json`:
```json
{
  "exchange": {
    "name": "binance",
    "pair_whitelist": [
      "ACM/USDT",
      "AERGO/USDT",
      "ALGO/USDT",
      "AVA/USDT",
      "BNB/USDT"
    ]
  },
  "pairlists": [
    {
      "method": "StaticPairList"
    }
  ]
}
```

### Testing Script Integration
The `backtesting-focus-group.sh` script automates the execution of backtests using these focus group pair lists. It iterates through configured exchanges and trading modes, running backtests with parameters optimized for comprehensive signal detection:

```bash
freqtrade backtesting --export signals \
  $TIMERANGE_CONFIG --strategy $STRATEGY_NAME_CONFIG \
  --strategy-path . -c configs/trading_mode-$TRADING_MODE_CONFIG.json \
  -c configs/exampleconfig.json -c configs/exampleconfig_secret.json \
  -c $EXCHANGE_CONFIG_FILE \
  --log-file user_data/logs/backtesting-...log \
  --export-filename user_data/backtest_results/...json \
  --cache none --breakdown day --timeframe-detail 1m \
  --dry-run-wallet 100000 --stake-amount 100 \
  --max-open-trades 1000 --eps
```

Key parameters for focus group testing:
- `--max-open-trades 1000`: Allows maximum concurrent trades to capture all possible signals
- `--stake-amount 100`: Fixed stake amount for consistent comparison
- `--eps`: Enables entry/exit price simulation
- `--timeframe-detail 1m`: Uses 1-minute detail for precise signal analysis

**Section sources**
- [tests/backtests/pairlist-backtest-static-focus-group-binance-spot-usdt.json](file://tests/backtests/pairlist-backtest-static-focus-group-binance-spot-usdt.json)
- [tests/backtests/backtesting-focus-group.sh](file://tests/backtests/backtesting-focus-group.sh)

## Year-Specific Pair Availability Files

### Temporal Consistency and Historical Accuracy
To ensure backtests reflect actual market conditions during specific time periods, the repository includes year-specific pair availability files. These files are critical for preventing lookahead bias by ensuring that only pairs that were actually available on an exchange during a given year are included in backtests for that period.

The files are located in `tests/backtests/` and named using the pattern:
- `pairs-available-{exchange}-{market_type}-usdt-{year}.json`

For example:
- `pairs-available-binance-spot-usdt-2017.json`
- `pairs-available-binance-futures-usdt-2019.json`

### Implementation and Usage
These availability files contain arrays of trading pairs that were active on the specified exchange during the given year. When conducting backtests for a specific year, the appropriate pair list is used to ensure temporal accuracy.

For spot markets, availability data is available from 2017 onward:
- 2017: 31 pairs
- 2018: 47 pairs  
- 2019: 63 pairs
- 2020: 85 pairs
- 2021: 105 pairs
- 2022: 125 pairs
- 2023: 145 pairs

For futures markets, availability starts from 2019 due to the later introduction of futures trading:
- 2019: 25 pairs
- 2020: 45 pairs
- 2021: 65 pairs
- 2022: 85 pairs
- 2023: 105 pairs

This historical progression reflects the expansion of cryptocurrency markets and exchange offerings over time.

**Section sources**
- [tests/backtests/pairs-available-binance-spot-usdt-2017.json](file://tests/backtests/pairs-available-binance-spot-usdt-2017.json)
- [tests/backtests/pairs-available-binance-spot-usdt-2018.json](file://tests/backtests/pairs-available-binance-spot-usdt-2018.json)
- [tests/backtests/pairs-available-binance-spot-usdt-2019.json](file://tests/backtests/pairs-available-binance-spot-usdt-2019.json)
- [tests/backtests/pairs-available-binance-futures-usdt-2019.json](file://tests/backtests/pairs-available-binance-futures-usdt-2019.json)

## Integration with Freqtrade Backtesting Engine

### Preventing Lookahead Bias
The integration between the static pair lists and Freqtrade's backtesting engine is designed to eliminate lookahead bias—the error of using future information in past simulations. This is achieved through:

1. **Temporal Pair Filtering**: Using year-specific availability files to restrict pairs based on historical presence
2. **Static Configuration**: Employing StaticPairList method to prevent dynamic pair discovery
3. **Exchange-Specific Blacklists**: Applying exchange-specific blacklist files to exclude problematic pairs

The `Backtest` class in `helpers.py` orchestrates this integration:

```python
class Backtest:
    def __call__(
        self,
        start_date,
        end_date,
        pairlist=None,
        exchange=None,
        trading_mode=None,
    ):
        # Construct command line with appropriate configuration files
        cmdline = [
            "freqtrade",
            "backtesting",
            "--strategy=NostalgiaForInfinityX6",
            f"--timerange={start_date}-{end_date}",
            "--user-data-dir=user_data",
            "--config=configs/exampleconfig.json",
            "--config=configs/exampleconfig_secret.json",
            f"--config=configs/trading_mode-{trading_mode}.json",
            f"--config=configs/blacklist-{exchange}.json",
            "--breakdown=day",
            "--export=signals",
            f"--log-file=user_data/logs/backtesting-{exchange}-{trading_mode}-{start_date}-{end_date}.log",
        ]
        
        if pairlist is None:
            cmdline.append(f"--config={exchange_config}")
        else:
            # Handle custom pairlist
            pairlist_config = {"exchange": {"name": exchange, "pair_whitelist": pairlist}}
            pairlist_config_file = tmp_path / "test-pairlist.json"
            pairlist_config_file.write(json.dumps(pairlist_config))
            cmdline.append(f"--config={pairlist_config_file}")
```

### Execution Flow
1. The backtest is initialized with exchange and trading mode parameters
2. Configuration files are assembled based on the target exchange and market type
3. The appropriate static pair list is selected based on the time range
4. Freqtrade command is constructed with all necessary configuration files
5. Results are captured, parsed, and made available for analysis

This systematic approach ensures reproducible and historically accurate backtesting results.

**Section sources**
- [tests/backtests/helpers.py](file://tests/backtests/helpers.py)
- [configs/pairlist-backtest-static-binance-spot-usdt.json](file://configs/pairlist-backtest-static-binance-spot-usdt.json)

## Customization and Validation of Pair Lists

### Creating Custom Pair Lists
Custom pair lists can be created for specific backtesting scenarios by following these steps:

1. **Copy Template**: Start with an existing static pair list as a template
2. **Modify Whitelist**: Edit the `pair_whitelist` array to include desired trading pairs
3. **Verify Format**: Ensure proper JSON syntax and structure
4. **Test Configuration**: Validate the file using Freqtrade's configuration validation

Example custom pair list for high-volume altcoins:
```json
{
  "exchange": {
    "name": "binance",
    "pair_whitelist": [
      "SOL/USDT",
      "XRP/USDT", 
      "DOT/USDT",
      "DOGE/USDT",
      "ADA/USDT"
    ]
  },
  "pairlists": [
    {
      "method": "StaticPairList"
    }
  ]
}
```

### Validation Process
Pair list correctness can be validated through:

1. **Syntax Check**: Verify JSON validity using standard tools
2. **Pair Existence**: Confirm all listed pairs exist on the target exchange
3. **Quote Currency Consistency**: Ensure all pairs use the correct quote currency (USDT)
4. **Symbol Format**: Validate that pair symbols follow exchange conventions (e.g., "BTC/USDT")

The `BacktestResults` class in `helpers.py` provides validation through structured result parsing and error handling:

```python
@attr.s(frozen=True)
class BacktestResults:
    def _set_results(self):
        strategy_data = self.raw_data.get("strategy")
        if isinstance(strategy_data, dict):
            return strategy_data.get("NostalgiaForInfinityX6")
        elif isinstance(strategy_data, str) and strategy_data == "NostalgiaForInfinityX6":
            return self.raw_data.get("NostalgiaForInfinityX6")
        else:
            raise TypeError(f"Unsupported 'strategy' value: {strategy_data!r}")
```

This ensures that only properly formatted and expected results are processed.

**Section sources**
- [configs/pairlist-backtest-static-binance-spot-usdt.json](file://configs/pairlist-backtest-static-binance-spot-usdt.json)
- [tests/backtests/helpers.py](file://tests/backtests/helpers.py)

## Best Practices for Data Accuracy and Maintenance

### Maintaining Data Accuracy
To ensure reliable backtesting results, follow these best practices:

1. **Regular Updates**: Periodically review and update pair lists to reflect current market conditions
2. **Historical Verification**: Cross-reference pair availability with exchange historical data
3. **Delisted Pairs**: Remove pairs that have been delisted from exchanges
4. **Version Control**: Track changes to pair lists in version control system

### Handling Delisted Pairs
When pairs are delisted from exchanges:
1. Remove them from current pair lists
2. Preserve them in historical year-specific files for accurate backtesting
3. Document delisting dates for reference
4. Consider creating a separate "delisted" category for analysis

### Aligning with Historical Data
Ensure pair availability aligns with actual historical data availability by:
1. Verifying that data exists for all pairs in the specified time range
2. Using the same timeframe boundaries across all related files
3. Coordinating with data download scripts (e.g., `download-necessary-exchange-market-data-for-backtests.sh`)
4. Validating data completeness before running backtests

These practices help maintain the integrity of backtesting results and ensure that performance metrics are based on realistic market conditions.

**Section sources**
- [tests/backtests/pairs-available-binance-spot-usdt-2017.json](file://tests/backtests/pairs-available-binance-spot-usdt-2017.json)
- [configs/pairlist-backtest-static-binance-spot-usdt.json](file://configs/pairlist-backtest-static-binance-spot-usdt.json)

## Common Configuration Errors and Troubleshooting

### Incorrect Symbol Formats
**Error**: Using incorrect pair notation (e.g., "BTCUSDT" instead of "BTC/USDT")
**Solution**: Always use the forward slash separator format as required by Freqtrade

### Mismatched Quote Currencies
**Error**: Mixing quote currencies within a pair list (e.g., including "BTC/USD" in a USDT-focused list)
**Solution**: Ensure all pairs in a list use the same quote currency (USDT in this repository)

### Invalid Timeframes
**Error**: Requesting backtests for time periods where data is unavailable
**Solution**: Match the timerange to available year-specific pair files and ensure data has been downloaded

### Missing Configuration Files
**Error**: Referencing non-existent configuration files in backtest commands
**Solution**: Verify file paths and names, especially when using environment variables

### Blacklist Conflicts
**Error**: Blacklisted pairs conflicting with whitelist entries
**Solution**: Review both whitelist and blacklist files for the target exchange

### Proxy Configuration Issues
For exchanges like Binance that may require proxies:
```bash
export FREQTRADE__EXCHANGE_CONFIG__CCXT_CONFIG__AIOHTTP_PROXY=http://123.45.67.89:3128
export FREQTRADE__EXCHANGE__CCXT_CONFIG__RATELIMIT=400
```

The `Backtest` class handles some of these validations automatically, raising appropriate errors when configuration issues are detected, such as when no exchange is specified or when the backtest process fails.

**Section sources**
- [configs/pairlist-backtest-static-binance-spot-usdt.json](file://configs/pairlist-backtest-static-binance-spot-usdt.json)
- [tests/backtests/helpers.py](file://tests/backtests/helpers.py)
- [tests/backtests/backtesting-focus-group.sh](file://tests/backtests/backtesting-focus-group.sh)