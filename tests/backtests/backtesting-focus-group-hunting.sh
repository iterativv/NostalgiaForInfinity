#!/bin/bash
# This script provided by DigiTuccar
# This script for finding all possible bad buys with all pairs available

# with these parameters you can see all possible buy signals together
# --disable-max-market-positions --dry-run-wallet 100000 --stake-amount 1000 --max-open-trades 100

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
# export STRATEGY_VERSION=v15-0-442 # dont use . in version there is a bug
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
  EXCHANGE_CONFIG="binance gateio okx"
else
  EXCHANGE_CONFIG=${EXCHANGE}
fi

# Time Range Config
TIMERANGE_CONFIG=""
if [ -z "${TIMERANGE}" ]; then
  unset TIMERANGE_CONFIG
else
  TIMERANGE_CONFIG="--timerange ${TIMERANGE}"
fi

# Trading Mode Config
TRADING_MODE_CONFIG=""
if [[ -z ${TRADING_MODE} ]]; then
  TRADING_MODE_CONFIG="futures spot"
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

export STRATEGY_VERSION=$(grep version $STRATEGY_NAME_CONFIG.py -A 1 | grep return | cut -d '"' -f 2)

# Strategy Config
STRATEGY_VERSION_CONFIG=""
if [[ -z ${STRATEGY_VERSION} ]]; then
  STRATEGY_VERSION_CONFIG="$(date -r $STRATEGY_NAME_CONFIG.py '+%Y_%m_%d-%H_%M')"
else
  grep version $STRATEGY_NAME_CONFIG.py -A 1 | grep return | cut -d '"' -f 2
  STRATEGY_VERSION_CONFIG=$(grep version $STRATEGY_NAME_CONFIG.py -A 1 | grep return | cut -d '"' -f 2 | sed "s/\./-/g")
fi

echo "# Running Backtests on Focus Group(s)"
for TRADING_MODE_RUN in ${TRADING_MODE_CONFIG[*]}; do

  for EXCHANGE_RUN in ${EXCHANGE_CONFIG[*]}; do

    TRADING_MODE_CONFIG=$TRADING_MODE_RUN

    EXCHANGE_CONFIG=$EXCHANGE_RUN

    EXCHANGE_CONFIG_FILE=tests/backtests/pairlist-backtest-static-focus-group-$EXCHANGE_CONFIG-$TRADING_MODE_CONFIG-usdt.json
    if [[ -f "$EXCHANGE_CONFIG_FILE" ]]; then

      echo -e "\n---\n"

      # echo "======================================================================================================"
      echo -e "## Strategy Name : $STRATEGY_NAME_CONFIG"
      echo -e "\n"
      echo -e "### Strategy Version: $STRATEGY_VERSION"
      echo -e "\n### ${EXCHANGE_CONFIG} FOCUS GROUP" | tr '[a-z]' '[A-Z]'
      echo -e "\n#### Trading Mode: $TRADING_MODE_CONFIG"

      echo -e "\n#### Running Command:\n\n\`\`\`sh\n"
      echo freqtrade backtesting --export signals --dmmp --eps \
        $TIMERANGE_CONFIG --strategy $STRATEGY_NAME_CONFIG \
        --strategy-path . -c configs/trading_mode-$TRADING_MODE_CONFIG.json \
        -c configs/exampleconfig.json -c configs/exampleconfig_secret.json \
        -c $EXCHANGE_CONFIG_FILE \
        --log-file user_data/logs/backtesting-$STRATEGY_NAME_CONFIG-$STRATEGY_VERSION_CONFIG-$EXCHANGE_CONFIG-$TRADING_MODE_CONFIG-focus-group-$TIMERANGE.log \
        --export-filename user_data/backtest_results/$STRATEGY_NAME_CONFIG-$STRATEGY_VERSION_CONFIG-$EXCHANGE_CONFIG-$TRADING_MODE_CONFIG-focus-group-$TIMERANGE.json \
        --cache none --breakdown day --timeframe-detail 1m --dry-run-wallet 100000 --stake-amount 1000 --max-open-trades 100
      echo -e "\n\`\`\`\n\n---\n\n"

      freqtrade backtesting --export signals --dmmp --eps \
        $TIMERANGE_CONFIG --strategy $STRATEGY_NAME_CONFIG \
        --strategy-path . -c configs/trading_mode-$TRADING_MODE_CONFIG.json \
        -c configs/exampleconfig.json -c configs/exampleconfig_secret.json \
        -c $EXCHANGE_CONFIG_FILE \
        --log-file user_data/logs/backtesting-$STRATEGY_NAME_CONFIG-$STRATEGY_VERSION_CONFIG-$EXCHANGE_CONFIG-$TRADING_MODE_CONFIG-focus-group-$TIMERANGE.log \
        --export-filename user_data/backtest_results/$STRATEGY_NAME_CONFIG-$STRATEGY_VERSION_CONFIG-$EXCHANGE_CONFIG-$TRADING_MODE_CONFIG-focus-group-$TIMERANGE.json \
        --cache none --breakdown day --timeframe-detail 1m --dry-run-wallet 100000 --stake-amount 1000 --max-open-trades 100

      echo -e "\n### ${EXCHANGE_CONFIG} FOCUS GROUP ANALYSIS HUNTING BAD ENTRIES" | tr '[a-z]' '[A-Z]'
      echo -e "\n${STRATEGY_NAME_CONFIG} ${STRATEGY_VERSION} ${TIMERANGE}" with --eps --dmmp
      echo -e "\n"
      echo -e "#### Running Command:\n\n\`\`\`sh\n"
      echo freqtrade backtesting-analysis --analysis-groups 0 1 2 3 4 5 \
        $TIMERANGE_CONFIG \
        -c configs/trading_mode-$TRADING_MODE_CONFIG.json \
        -c configs/exampleconfig.json -c configs/exampleconfig_secret.json \
        -c $EXCHANGE_CONFIG_FILE
      echo -e "\n\`\`\`\n"

      freqtrade backtesting-analysis --analysis-groups 0 1 2 3 4 5 \
        $TIMERANGE_CONFIG \
        -c configs/trading_mode-$TRADING_MODE_CONFIG.json \
        -c configs/exampleconfig.json -c configs/exampleconfig_secret.json \
        -c $EXCHANGE_CONFIG_FILE

      echo -e "\n### ${EXCHANGE_CONFIG} FOCUS GROUP PLOT PROFIT" | tr '[a-z]' '[A-Z]'
      echo -e "\n#### Trading Mode: $TRADING_MODE_CONFIG"
      echo -e "\n${STRATEGY_NAME_CONFIG} ${STRATEGY_VERSION} ${EXCHANGE_CONFIG} ${TIMERANGE}"
      echo -e "\n"
      echo -e "#### Running Command:\n\n\`\`\`sh\n"
      echo freqtrade plot-profit $TIMERANGE_CONFIG --strategy $STRATEGY_NAME_CONFIG \
        -c configs/trading_mode-$TRADING_MODE_CONFIG.json \
        -c configs/exampleconfig.json -c configs/exampleconfig_secret.json \
        -c $EXCHANGE_CONFIG_FILE
      echo -e "\n\`\`\`\n"

      freqtrade plot-profit $TIMERANGE_CONFIG --strategy $STRATEGY_NAME_CONFIG \
        -c configs/trading_mode-$TRADING_MODE_CONFIG.json \
        -c configs/exampleconfig.json -c configs/exampleconfig_secret.json \
        -c $EXCHANGE_CONFIG_FILE

      echo -e "\n### ${EXCHANGE_CONFIG} FOCUS GROUP PLOT DATAFRAME" | tr '[a-z]' '[A-Z]'
      echo -e "\n${STRATEGY_NAME_CONFIG} ${STRATEGY_VERSION} ${TIMERANGE} with --eps --dmmp"
      echo -e "\n"
      echo -e "#### Running Command:\n\n\`\`\`sh\n"
      echo freqtrade plot-dataframe $TIMERANGE_CONFIG --strategy $STRATEGY_NAME_CONFIG \
        -c configs/trading_mode-$TRADING_MODE_CONFIG.json \
        -c configs/exampleconfig.json -c configs/exampleconfig_secret.json \
        -c $EXCHANGE_CONFIG_FILE \
        --indicators1 EMA_200 \
        --indicators2 RSI_3_1d RSI_14_1d RSI_3_4h RSI_14_4h RSI_14_1h RSI_3_1h RSI_14_15m RSI_3_15m CCI_20_15m CCI_20_1h CCI_20_4h short_entry_signal_2 short_entry_signal_1 long_entry_signal_2 long_entry_signal_1
      echo -e "\n\`\`\`\n"

      freqtrade plot-dataframe $TIMERANGE_CONFIG --strategy $STRATEGY_NAME_CONFIG \
        -c configs/trading_mode-$TRADING_MODE_CONFIG.json \
        -c configs/exampleconfig.json -c configs/exampleconfig_secret.json \
        -c $EXCHANGE_CONFIG_FILE

      echo -e "\n${EXCHANGE_CONFIG} FOCUS GROUP ANALYSIS WITH PLOT FINISHED (with --eps )" | tr '[a-z]' '[A-Z]'
      echo -e "\n${STRATEGY_NAME_CONFIG} ${STRATEGY_VERSION} ${TIMERANGE} with --eps --dmmp"
      echo -e "\n"
    fi
    unset TRADING_MODE_CONFIG
  done

done
