#!/bin/bash
# This script downloads necessary data from DigiTuccar Historical Data For Backtesting
# The repo is huge and this script download only necessary info
# The repo HistoricalDataForTradeBacktest from DigiTuccar is regularly and automatically updating
# You can run this script regularly to update your data for new backteswting periods
MAIN_DATA_DIRECTORY="user_data/data"
# For manual running you can use these
TIMEFRAME="5m"
HELPER_TIME_FRAMES="1d 4h 1h 15m 1m"
# EXAMPLE
# TRADING_MODE="spot futures"
TRADING_MODE="spot"
# EXAMPLE
# EXCHANGE="binance kucoin okx"
EXCHANGE="binance kucoin"
URL="https://github.com/DigiTuccar/HistoricalDataForTradeBacktest.git"

if [ -d $MAIN_DATA_DIRECTORY ]
    then
        echo "###############################################"
        echo $MAIN_DATA_DIRECTORY exists on your filesystem. We will delete it for Github CI Workflow
        echo "###############################################"
        echo Please delete $MAIN_DATA_DIRECTORY with rm -rf $MAIN_DATA_DIRECTORY
    else
    echo "###############################################"
    echo $MAIN_DATA_DIRECTORY not exists on your filesystem. Necessary to download first
    echo "###############################################"

fi
    git clone --filter=blob:none --no-checkout --depth 1 --sparse $URL $MAIN_DATA_DIRECTORY
    git -C $MAIN_DATA_DIRECTORY sparse-checkout reapply --no-cone

echo "Fetching necessary Timeframe Data"

for data_necessary_exchange in ${EXCHANGE[*]}
do
for data_necessary_market_type in ${TRADING_MODE[*]}
do
for data_necessary_timeframe in ${TIMEFRAME[*]}
do
echo
echo "--------------------------------------------------------------------------------------------------------"
echo "# Exchange: $data_necessary_exchange      Market Type: $data_necessary_market_type      Time Frame: $data_necessary_timeframe"
echo "--------------------------------------------------------------------------------------------------------"
echo

# Configure Market Data Directory
EXCHANGE_MARKET_DIRECTORY=$data_necessary_exchange

if [[ $data_necessary_market_type == futures ]]
    then
    EXCHANGE_MARKET_DIRECTORY=$data_necessary_exchange/futures
    else
    EXCHANGE_MARKET_DIRECTORY=$data_necessary_exchange
fi
git -C $MAIN_DATA_DIRECTORY sparse-checkout add /$EXCHANGE_MARKET_DIRECTORY/*-$data_necessary_timeframe*.feather
done
done
done

echo "Fetching necessary Helper Timeframe Data"
for data_necessary_exchange in ${EXCHANGE[*]}
do
for data_necessary_market_type in ${TRADING_MODE[*]}
do
for data_necessary_timeframe in ${HELPER_TIME_FRAMES[*]}
do
echo
echo "--------------------------------------------------------------------------------------------------------"
echo "# Exchange: $data_necessary_exchange      Market Type: $data_necessary_market_type      Time Frame: $data_necessary_timeframe"
echo "--------------------------------------------------------------------------------------------------------"
echo

EXCHANGE_MARKET_DIRECTORY=$data_necessary_exchange

if [[ $data_necessary_market_type == futures ]]
    then
    EXCHANGE_MARKET_DIRECTORY=$data_necessary_exchange/futures
    else
    EXCHANGE_MARKET_DIRECTORY=$data_necessary_exchange
fi
git -C $MAIN_DATA_DIRECTORY sparse-checkout add /$EXCHANGE_MARKET_DIRECTORY/*-$data_necessary_timeframe*.feather
done
done
done
git -C $MAIN_DATA_DIRECTORY checkout

echo "---------------------------------------------"
echo "All necessary data fetched"
du -sh $MAIN_DATA_DIRECTORY
