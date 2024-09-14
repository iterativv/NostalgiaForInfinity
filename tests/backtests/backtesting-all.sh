#!/bin/bash
# This script provided by DigiTuccar
# This script written to cover all possible tests and all possible good and bad buy signals
# This script for backtesting all possible entries in all exchanges with all pairlists
# Script will run 2 times all tests in 2 different modes
# First part will run with standart configuration as your live
# Second part will run with "Bad Buy Hunting Mode"
#
# Before Running
# You should download all history from here
# https://github.com/DigiTuccar/HistoricalDataForTradeBacktest
#
# To run tests for a special timeframe (and it will make make your tests faster)
# you can run
# export TIMERANGE=20230101-20230501
#
#
# Than you can unset TIMERANGE by entering this command
# unset TIMERANGE
#
#
# After unset TIMERANGE script will run for:
#  - ALL Possible periods
#  - ALL Exchanges
#  - ALL Pairs
#
# This run will be very very long.
# It can take 4 days
# You need a powerfull Multi Core CPU and Minimum 96 GB RAM
#
# Without running this tests you should never run your strategy in live
#
# Because without enough testing your strategy can lose big money
#
# Good Luck
# If you reading this and searching for more you should see
# https://github.com/DigiTuccar


export STRATEGY_NAME=NostalgiaForInfinityX5
export STRATEGY_VERSION=`grep version $STRATEGY_NAME.py  -A 1|grep return|cut -d '"' -f 2|sed "s/\.//g"`

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######   ######                                               #######                                          "
echo "######   #     # # #    #   ##   #    #  ####  ######         #       #    # ##### #    # #####  ######  ####  "
echo "######   #     # # ##   #  #  #  ##   # #    # #              #       #    #   #   #    # #    # #      #      "
echo "######   ######  # # #  # #    # # #  # #      #####          #####   #    #   #   #    # #    # #####   ####  "
echo "######   #     # # #  # # ###### #  # # #      #              #       #    #   #   #    # #####  #           # "
echo "######   #     # # #   ## #    # #   ## #    # #              #       #    #   #   #    # #   #  #      #    # "
echo "######   ######  # #    # #    # #    #  ####  ######         #        ####    #    ####  #    # ######  ####  "
echo "######    "
echo "######    "
echo "######    "
echo "######    "

export TRADING_MODE=futures
export EXCHANGE=binance
./tests/backtests/backtesting-all-years-all-pairs.sh

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######   ######                                                #####                      "
echo "######   #     # # #    #   ##   #    #  ####  ######         #     # #####   ####  ##### "
echo "######   #     # # ##   #  #  #  ##   # #    # #              #       #    # #    #   #   "
echo "######   ######  # # #  # #    # # #  # #      #####           #####  #    # #    #   #   "
echo "######   #     # # #  # # ###### #  # # #      #                    # #####  #    #   #   "
echo "######   #     # # #   ## #    # #   ## #    # #              #     # #      #    #   #   "
echo "######   ######  # #    # #    # #    #  ####  ######          #####  #       ####    #   "
echo "######    "
echo "######    "

export TRADING_MODE=spot
export EXCHANGE=binance
./tests/backtests/backtesting-all-years-all-pairs.sh

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######   #    #                                        #####                      "
echo "######   #   #  #    #  ####   ####  # #    #         #     # #####   ####  ##### "
echo "######   #  #   #    # #    # #    # # ##   #         #       #    # #    #   #   "
echo "######   ###    #    # #      #    # # # #  #          #####  #    # #    #   #   "
echo "######   #  #   #    # #      #    # # #  # #               # #####  #    #   #   "
echo "######   #   #  #    # #    # #    # # #   ##         #     # #      #    #   #   "
echo "######   #    #  ####   ####   ####  # #    #          #####  #       ####    #   "
echo "######    "
echo "######    "

export EXCHANGE=kucoin
./tests/backtests/backtesting-all-years-all-pairs.sh

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    ####### #    # #     #         #######                                          "
echo "######    #     # #   #   #   #          #       #    # ##### #    # #####  ######  ####  "
echo "######    #     # #  #     # #           #       #    #   #   #    # #    # #      #      "
echo "######    #     # ###       #            #####   #    #   #   #    # #    # #####   ####  "
echo "######    #     # #  #     # #           #       #    #   #   #    # #####  #           # "
echo "######    #     # #   #   #   #          #       #    #   #   #    # #   #  #      #    # "
echo "######    ####### #    # #     #         #        ####    #    ####  #    # ######  ####  "
echo "######    "
echo "######    "

export TRADING_MODE=futures
export EXCHANGE=okx
./tests/backtests/backtesting-all-years-all-pairs.sh

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######   ####### #    # #     #          #####                      "
echo "######   #     # #   #   #   #          #     # #####   ####  ##### "
echo "######   #     # #  #     # #           #       #    # #    #   #   "
echo "######   #     # ###       #             #####  #    # #    #   #   "
echo "######   #     # #  #     # #                 # #####  #    #   #   "
echo "######   #     # #   #   #   #          #     # #      #    #   #   "
echo "######   ####### #    # #     #          #####  #       ####    #   "
echo "######    "
echo "######    "

export TRADING_MODE=spot
export EXCHANGE=okx
./tests/backtests/backtesting-all-years-all-pairs.sh



export TRADING_MODE=spot
export EXCHANGE=okx
./tests/backtests/backtesting-all-years-all-pairs.sh

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    #####                      ###                         #####                      "
echo "######   #     #   ##   ##### ######  #   ####                  #     # #####   ####  ##### "
echo "######   #        #  #    #   #       #  #    #                 #       #    # #    #   #   "
echo "######   #  #### #    #   #   #####   #  #    #                  #####  #    # #    #   #   "
echo "######   #     # ######   #   #       #  #    #                       # #####  #    #   #   "
echo "######   #     # #    #   #   #       #  #    #                 #     # #      #    #   #   "
echo "######    #####  #    #   #   ###### ###  ####                   #####  #       ####    #   "
echo "######    "
echo "######    "


export TRADING_MODE=spot
export EXCHANGE=gateio
./tests/backtests/backtesting-all-years-all-pairs.sh

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    #####                      ###                        #######                                          "
echo "######   #     #   ##   ##### ######  #   ####                  #       #    # ##### #    # #####  ######  ####  "
echo "######   #        #  #    #   #       #  #    #                 #       #    #   #   #    # #    # #      #      "
echo "######   #  #### #    #   #   #####   #  #    #                 #####   #    #   #   #    # #    # #####   ####  "
echo "######   #     # ######   #   #       #  #    #                 #       #    #   #   #    # #####  #           # "
echo "######   #     # #    #   #   #       #  #    #                 #       #    #   #   #    # #   #  #      #    # "
echo "######    #####  #    #   #   ###### ###  ####                  #        ####    #    ####  #    # ######  ####  "
echo "######    "
echo "######    "

export TRADING_MODE=futures
export EXCHANGE=gateio
./tests/backtests/backtesting-all-years-all-pairs.sh


echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######   ##     ## ##     ## ##    ## ######## #### ##    ##  ######   "
echo "######   ##     ## ##     ## ###   ##    ##     ##  ###   ## ##    ##  "
echo "######   ##     ## ##     ## ####  ##    ##     ##  ####  ## ##        "
echo "######   ######### ##     ## ## ## ##    ##     ##  ## ## ## ##   #### "
echo "######   ##     ## ##     ## ##  ####    ##     ##  ##  #### ##    ##  "
echo "######   ##     ## ##     ## ##   ###    ##     ##  ##   ### ##    ##  "
echo "######   ##     ##  #######  ##    ##    ##    #### ##    ##  ######   "
echo "######    "
echo "######    "
echo "######   ######                #######                                     "
echo "######   #     #   ##   #####  #       #    # ##### #####  # ######  ####  "
echo "######   #     #  #  #  #    # #       ##   #   #   #    # # #      #      "
echo "######   ######  #    # #    # #####   # #  #   #   #    # # #####   ####  "
echo "######   #     # ###### #    # #       #  # #   #   #####  # #           # "
echo "######   #     # #    # #    # #       #   ##   #   #   #  # #      #    # "
echo "######   ######  #    # #####  ####### #    #   #   #    # # ######  ####  "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    Why this is necessary ?"
echo "######    Because in 5m timeframe you can not see all possible bad entries"
echo "######    "
echo "######    Maybe you missed some bad entry signals"
echo "######    Now we will make an extensive test with 1m timeframe detail"
echo "######    "
echo "######    Now we will catch all possible bad buy signals"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######   ######                                               #######                                          "
echo "######   #     # # #    #   ##   #    #  ####  ######         #       #    # ##### #    # #####  ######  ####  "
echo "######   #     # # ##   #  #  #  ##   # #    # #              #       #    #   #   #    # #    # #      #      "
echo "######   ######  # # #  # #    # # #  # #      #####          #####   #    #   #   #    # #    # #####   ####  "
echo "######   #     # # #  # # ###### #  # # #      #              #       #    #   #   #    # #####  #           # "
echo "######   #     # # #   ## #    # #   ## #    # #              #       #    #   #   #    # #   #  #      #    # "
echo "######   ######  # #    # #    # #    #  ####  ######         #        ####    #    ####  #    # ######  ####  "
echo "######    "
echo "######    "

export TRADING_MODE=futures
export EXCHANGE=binance
./tests/backtests/backtesting-for-hunting-bad-buys.sh

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######   ######                                                #####                      "
echo "######   #     # # #    #   ##   #    #  ####  ######         #     # #####   ####  ##### "
echo "######   #     # # ##   #  #  #  ##   # #    # #              #       #    # #    #   #   "
echo "######   ######  # # #  # #    # # #  # #      #####           #####  #    # #    #   #   "
echo "######   #     # # #  # # ###### #  # # #      #                    # #####  #    #   #   "
echo "######   #     # # #   ## #    # #   ## #    # #              #     # #      #    #   #   "
echo "######   ######  # #    # #    # #    #  ####  ######          #####  #       ####    #   "
echo "######    "
echo "######    "

export TRADING_MODE=spot
export EXCHANGE=binance
./tests/backtests/backtesting-for-hunting-bad-buys.sh

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######   #    #                                        #####                      "
echo "######   #   #  #    #  ####   ####  # #    #         #     # #####   ####  ##### "
echo "######   #  #   #    # #    # #    # # ##   #         #       #    # #    #   #   "
echo "######   ###    #    # #      #    # # # #  #          #####  #    # #    #   #   "
echo "######   #  #   #    # #      #    # # #  # #               # #####  #    #   #   "
echo "######   #   #  #    # #    # #    # # #   ##         #     # #      #    #   #   "
echo "######   #    #  ####   ####   ####  # #    #          #####  #       ####    #   "
echo "######    "
echo "######    "

export EXCHANGE=kucoin
./tests/backtests/backtesting-for-hunting-bad-buys.sh


echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    ####### #    # #     #         #######                                          "
echo "######    #     # #   #   #   #          #       #    # ##### #    # #####  ######  ####  "
echo "######    #     # #  #     # #           #       #    #   #   #    # #    # #      #      "
echo "######    #     # ###       #            #####   #    #   #   #    # #    # #####   ####  "
echo "######    #     # #  #     # #           #       #    #   #   #    # #####  #           # "
echo "######    #     # #   #   #   #          #       #    #   #   #    # #   #  #      #    # "
echo "######    ####### #    # #     #         #        ####    #    ####  #    # ######  ####  "
echo "######    "
echo "######    "

export TRADING_MODE=futures
export EXCHANGE=okx
./tests/backtests/backtesting-for-hunting-bad-buys.sh

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######   ####### #    # #     #          #####                      "
echo "######   #     # #   #   #   #          #     # #####   ####  ##### "
echo "######   #     # #  #     # #           #       #    # #    #   #   "
echo "######   #     # ###       #             #####  #    # #    #   #   "
echo "######   #     # #  #     # #                 # #####  #    #   #   "
echo "######   #     # #   #   #   #          #     # #      #    #   #   "
echo "######   ####### #    # #     #          #####  #       ####    #   "
echo "######    "
echo "######    "

export TRADING_MODE=spot
export EXCHANGE=okx
./tests/backtests/backtesting-for-hunting-bad-buys.sh

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    #####                      ###                         #####                      "
echo "######   #     #   ##   ##### ######  #   ####                  #     # #####   ####  ##### "
echo "######   #        #  #    #   #       #  #    #                 #       #    # #    #   #   "
echo "######   #  #### #    #   #   #####   #  #    #                  #####  #    # #    #   #   "
echo "######   #     # ######   #   #       #  #    #                       # #####  #    #   #   "
echo "######   #     # #    #   #   #       #  #    #                 #     # #      #    #   #   "
echo "######    #####  #    #   #   ###### ###  ####                   #####  #       ####    #   "
echo "######    "
echo "######    "


export TRADING_MODE=spot
export EXCHANGE=gateio
./tests/backtests/backtesting-for-hunting-bad-buys.sh

echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "#################################################################################"
echo "#################################################################################"
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    "
echo "######    #####                      ###                        #######                                          "
echo "######   #     #   ##   ##### ######  #   ####                  #       #    # ##### #    # #####  ######  ####  "
echo "######   #        #  #    #   #       #  #    #                 #       #    #   #   #    # #    # #      #      "
echo "######   #  #### #    #   #   #####   #  #    #                 #####   #    #   #   #    # #    # #####   ####  "
echo "######   #     # ######   #   #       #  #    #                 #       #    #   #   #    # #####  #           # "
echo "######   #     # #    #   #   #       #  #    #                 #       #    #   #   #    # #   #  #      #    # "
echo "######    #####  #    #   #   ###### ###  ####                  #        ####    #    ####  #    # ######  ####  "
echo "######    "
echo "######    "

export TRADING_MODE=futures
export EXCHANGE=gateio
./tests/backtests/backtesting-for-hunting-bad-buys.sh
