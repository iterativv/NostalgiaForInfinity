#!/usr/bin/env bash

# This script provided by DigiTuccar
# This script for finding all possible bad buys with all pairs available

# with these parameters you can see all possible buy signals together
# --dry-run-wallet 100000 --stake-amount 100 --max-open-trades 1000 --eps

# Because of limitations pairlists divided by years as they are available
# these tests are for covering all possible time periods and all possible pairs
#
# By this way we can hunt for bad buys in your strategy
# It can be divided to more detailed periods
#
# its a script for run before going to sleep (Takes too much time)
# When you wake up you i wish to good results

# If you need to set a proxy you can use this command

# export FREQTRADE__EXCHANGE_CONFIG__CCXT_CONFIG__AIOHTTP_PROXY=http://123.45.67.89:3128
# export FREQTRADE__EXCHANGE_CONFIG__CCXT_CONFIG__PROXIES__HTTP=http://123.45.67.89:3128
# export FREQTRADE__EXCHANGE_CONFIG__CCXT_CONFIG__PROXIES__HTTPS=http://123.45.67.89:3128

# if you get binance connection errors when you are testing you can run this
# export FREQTRADE__EXCHANGE__CCXT_CONFIG__RATELIMIT=400

# If you need to change settings before run you can set environment variables like this

# export EXCHANGE=binance
# export TRADING_MODE=spot
# export STRATEGY_VERSION=v13-0-442 # dont use . in version there is a bug
# export STRATEGY_NAME=NostalgiaForInfinityX5
# export TIMERANGE=20230801-

date() {
  if type -p gdate >/dev/null; then
    gdate "$@"
  else
    date "$@"
  fi
}

# Exchange Config
EXCHANGE_CONFIG=""
if [[ -z ${EXCHANGE} ]]; then
  EXCHANGE_CONFIG="binance"
else
  EXCHANGE_CONFIG=${EXCHANGE}
fi

# Trading Mode Config
TRADING_MODE_CONFIG=""
if [[ -z ${TRADING_MODE} ]]; then
  TRADING_MODE_CONFIG="spot"
else
  TRADING_MODE_CONFIG=${TRADING_MODE}
fi

# Strategy Config
STRATEGY_NAME_CONFIG=""
if [[ -z ${STRATEGY_NAME} ]]; then
  STRATEGY_NAME_CONFIG="NostalgiaForInfinityX5"
else
  STRATEGY_NAME_CONFIG=${STRATEGY_NAME}
fi

# Strategy Config
STRATEGY_VERSION_CONFIG=""
if [[ -z ${STRATEGY_VERSION} ]]; then
  STRATEGY_VERSION_CONFIG="$(date -r $STRATEGY_NAME_CONFIG.py '+%Y_%m_%d-%H_%M')"
else
  STRATEGY_VERSION_CONFIG=${STRATEGY_VERSION}
fi

for START_YEAR in {2023..2017}; do
  # Time Range Config
  TIMERANGE_CONFIG=""
  if [ -z "${TIMERANGE}" ]; then
    TIMERANGE_CONFIG="$START_YEAR""0101-"
  else
    TIMERANGE_CONFIG="${TIMERANGE}"
  fi

  EXCHANGE_CONFIG_FILE=tests/backtests/pairs-available-$EXCHANGE_CONFIG-$TRADING_MODE_CONFIG-usdt-$START_YEAR.json
  if [ -f "$EXCHANGE_CONFIG_FILE" ]; then

    echo " "
    echo " "
    echo "======================================================================================================"
    echo " "
    echo "# BACKTESTING WITH ALL PAIRS AVAILABLE SINCE $START_YEAR"
    echo " "
    echo "======================================================================================================"
    echo "---------------------------------------------"
    echo "###"
    echo "###         $START_YEAR"
    echo "###"
    echo "---------------------------------------------"
    echo " "
    echo "======================================================================================================"
    echo "##"
    echo "## Exchange : $EXCHANGE_CONFIG             Trading Mode : $TRADING_MODE_CONFIG            Timerange : $TIMERANGE_CONFIG"
    echo "##"
    echo "## Strategy Name : $STRATEGY_NAME_CONFIG                  Strategy Version : $STRATEGY_VERSION_CONFIG"
    echo "##"
    echo " "
    echo " "
    echo " "
    freqtrade backtesting --export signals \
      --timerange $TIMERANGE_CONFIG --strategy $STRATEGY_NAME_CONFIG \
      --strategy-path . -c configs/trading_mode-$TRADING_MODE_CONFIG.json \
      -c configs/exampleconfig.json -c configs/exampleconfig_secret.json \
      -c tests/backtests/pairs-available-$EXCHANGE_CONFIG-$TRADING_MODE_CONFIG-usdt-$START_YEAR.json \
      --log-file user_data/logs/backtesting-$STRATEGY_NAME_CONFIG-$STRATEGY_VERSION_CONFIG-$EXCHANGE_CONFIG-$TRADING_MODE_CONFIG-$TIMERANGE_CONFIG.log \
      --export-filename user_data/backtest_results/$STRATEGY_NAME_CONFIG-$STRATEGY_VERSION_CONFIG-$EXCHANGE_CONFIG-$TRADING_MODE_CONFIG-$TIMERANGE_CONFIG.json \
      --cache none --breakdown day \
      --dry-run-wallet 100000 --stake-amount 100 --max-open-trades 1000 --timeframe-detail 1m --eps

    echo " "
    echo " "
    echo "======================================================================================================"
    echo " "
    echo "# ANALYSIS THE RESULT OF BACKTEST WITH ALL PAIRS AVAILABLE SINCE $START_YEAR"
    echo " "
    echo "======================================================================================================"
    echo "---------------------------------------------"
    echo "###"
    echo "###         $START_YEAR"
    echo "###"
    echo "---------------------------------------------"
    echo " "
    echo "======================================================================================================"
    echo "##"
    echo "## Exchange : $EXCHANGE_CONFIG             Trading Mode : $TRADING_MODE_CONFIG            Timerange : $TIMERANGE_CONFIG"
    echo "##"
    echo "## Strategy Name : $STRATEGY_NAME_CONFIG                  Strategy Version : $STRATEGY_VERSION_CONFIG"
    echo "##"
    echo " "
    echo " "
    echo " "
    freqtrade backtesting-analysis --analysis-groups 0 1 2 3 4 5 \
      --timerange $TIMERANGE_CONFIG \
      -c configs/trading_mode-$TRADING_MODE_CONFIG.json \
      -c configs/exampleconfig.json -c configs/exampleconfig_secret.json \
      -c tests/backtests/pairs-available-$EXCHANGE_CONFIG-$TRADING_MODE_CONFIG-usdt-$START_YEAR.json
  fi
done
