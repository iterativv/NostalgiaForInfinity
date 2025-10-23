# Run Backtests
If you plan to only clone the repository to use the strategy, a regular `git clone` will do.

However, if you plan on running additional backtest and run the test suite, you need to download data.
## Fast download test data from NFI Historical Trade Data Repo

There is a repo for this :
https://github.com/iterativv/NostalgiaForInfinityData

For fast downloading data from github repo run `tools/download-necessary-exchange-market-data-for-backtests.sh`

```bash
./tools/download-necessary-exchange-market-data-for-backtests.sh
```

## Running the tests

export your exchange (binance / kucoin)
```bash
export TRADING_MODE=binance
```


export your exchange market (spot / futures)

```bash
export TRADING_MODE=futures
```

enter the date you want to test
```bash
export TIMERANGE=20240801-20240901
```

run the test which you want:
```bash
./tests/backtests/backtesting-analysis-hunting.sh
```
