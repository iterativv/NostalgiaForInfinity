#!/bin/bash
MAIN_DATA_DIRECTORY="user_data/data"
# For manual running you can use these
# TIMEFRAME="5m"
# HELPER_TIME_FRAMES="15m 1h 4h 1d"
# TRADING_MODE="spot"
# EXCHANGE="binance"
URL="https://github.com/iterativv/NostalgiaForInfinityData.git"

rm PAIRS_FOR_DOWNLOAD.txt
# docker run -v ".:/running_config" --rm --env-file .github/workflows/scripts/ci-proxy.env \
#     freqtradeorg/freqtrade:stable test-pairlist -c /running_config/configs/trading_mode-$TRADING_MODE.json \
#     -c /running_config/configs/pairlist-backtest-static-$EXCHANGE-$TRADING_MODE-usdt.json \
#     -c /running_config/configs/exampleconfig.json -1 --exchange $EXCHANGE \
#     -c /running_config/configs/blacklist-$EXCHANGE.json|sed -e 's+/+_+g'>>PAIRS_FOR_DOWNLOAD.txt

jq -r .exchange.pair_whitelist[] configs/pairlist-backtest-static-$EXCHANGE-$TRADING_MODE-usdt.json | sed -e 's+/+_+g' -e 's+:+_+g' >PAIRS_FOR_DOWNLOAD.txt

if [[ -L $MAIN_DATA_DIRECTORY ]]; then
    echo "###############################################"
    echo "$MAIN_DATA_DIRECTORY exists on your filesystem as a link. We will delete it for Github CI Workflow"
    echo "###############################################"
    rm -rf $MAIN_DATA_DIRECTORY
else
    echo "###############################################"
    echo "$MAIN_DATA_DIRECTORY file link is not exists as a link on your filesystem. Necessary to download first"
    echo "###############################################"

fi

if [[ -d $MAIN_DATA_DIRECTORY ]]; then
    echo "###############################################"
    echo "$MAIN_DATA_DIRECTORY as a directory exists on CI WORKFLOW filesystem. We will delete it for Github CI Workflow"
    echo "###############################################"
    rm -rf $MAIN_DATA_DIRECTORY
else
    echo "###############################################"
    echo "$MAIN_DATA_DIRECTORY not exists on your filesystem. Necessary to download first"
    echo "###############################################"

fi
git clone --filter=blob:none --no-checkout --depth 1 --sparse $URL $MAIN_DATA_DIRECTORY
git -C $MAIN_DATA_DIRECTORY sparse-checkout reapply --no-cone

echo "Fetching necessary Timeframe Data"
data_necessary_timerange="${TIMERANGE[*]}"
for data_necessary_exchange in ${EXCHANGE[*]}; do
    for data_necessary_market_type in ${TRADING_MODE[*]}; do
        for data_necessary_timeframe in ${TIMEFRAME[*]}; do
            echo
            echo "--------------------------------------------------------------------------------------------------------"
            echo "# Exchange: $data_necessary_exchange      Market Type: $data_necessary_market_type      Time Frame: $data_necessary_timeframe     Timerange: $data_necessary_timerange"
            echo "--------------------------------------------------------------------------------------------------------"
            echo

            # Configure Market Data Directory
            EXCHANGE_MARKET_DIRECTORY="$data_necessary_exchange"

            if [[ $data_necessary_market_type == futures ]]; then
                EXCHANGE_MARKET_DIRECTORY="$data_necessary_exchange/futures"
            else
                EXCHANGE_MARKET_DIRECTORY="$data_necessary_exchange"
            fi

            while IFS= read -r pair; do
                echo "$pair" pair "$data_necessary_timeframe" added
                git -C $MAIN_DATA_DIRECTORY sparse-checkout add /$EXCHANGE_MARKET_DIRECTORY/$pair*-$data_necessary_timeframe*.feather

            done <PAIRS_FOR_DOWNLOAD.txt

        done
    done
done

echo "Fetching necessary Helper Timeframe Data"
for data_necessary_exchange in ${EXCHANGE[*]}; do
    for data_necessary_market_type in ${TRADING_MODE[*]}; do
        for data_necessary_timeframe in ${HELPER_TIME_FRAMES[*]}; do
            echo
            echo "--------------------------------------------------------------------------------------------------------"
            echo "# Exchange: $data_necessary_exchange      Market Type: $data_necessary_market_type      Time Frame: $data_necessary_timeframe     Timerange: $data_necessary_timerange"
            echo "--------------------------------------------------------------------------------------------------------"
            echo

            EXCHANGE_MARKET_DIRECTORY=$data_necessary_exchange

            if [[ $data_necessary_market_type == futures ]]; then
                EXCHANGE_MARKET_DIRECTORY="$data_necessary_exchange/futures"
            else
                EXCHANGE_MARKET_DIRECTORY="$data_necessary_exchange"
            fi

            while IFS= read -r pair; do
                echo "$pair" pair "$data_necessary_timeframe" added
                git -C $MAIN_DATA_DIRECTORY sparse-checkout add /$EXCHANGE_MARKET_DIRECTORY/$pair*-$data_necessary_timeframe*.feather

            done <PAIRS_FOR_DOWNLOAD.txt

        done
    done
done
git -C $MAIN_DATA_DIRECTORY checkout

echo "---------------------------------------------"
echo "All necessary data fetched"
