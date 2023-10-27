export STRATEGY_NAME=NostalgiaForInfinityX4
export STRATEGY_VERSION=`grep version $STRATEGY_NAME.py  -A 1|grep return|cut -d '"' -f 2|sed "s/\.//g"`

export TRADING_MODE=futures


echo " "
echo " "
echo " ####### #    # #     #         #######                                          "
echo " #     # #   #   #   #          #       #    # ##### #    # #####  ######  ####  "
echo " #     # #  #     # #           #       #    #   #   #    # #    # #      #      "
echo " #     # ###       #            #####   #    #   #   #    # #    # #####   ####  "
echo " #     # #  #     # #           #       #    #   #   #    # #####  #           # "
echo " #     # #   #   #   #          #       #    #   #   #    # #   #  #      #    # "
echo " ####### #    # #     #         #        ####    #    ####  #    # ######  ####  "
echo " "
echo " "


export EXCHANGE=okx
./tests/backtests/backtesting-all-years-all-pairs.sh

echo " "
echo " "
echo "######                                               #######                                          "
echo "#     # # #    #   ##   #    #  ####  ######         #       #    # ##### #    # #####  ######  ####  "
echo "#     # # ##   #  #  #  ##   # #    # #              #       #    #   #   #    # #    # #      #      "
echo "######  # # #  # #    # # #  # #      #####          #####   #    #   #   #    # #    # #####   ####  "
echo "#     # # #  # # ###### #  # # #      #              #       #    #   #   #    # #####  #           # "
echo "#     # # #   ## #    # #   ## #    # #              #       #    #   #   #    # #   #  #      #    # "
echo "######  # #    # #    # #    #  ####  ######         #        ####    #    ####  #    # ######  ####  "
echo " "
echo " "

export EXCHANGE=binance
./tests/backtests/backtesting-all-years-all-pairs.sh


echo " "
echo " "
echo "####### #    # #     #          #####                      "
echo "#     # #   #   #   #          #     # #####   ####  ##### "
echo "#     # #  #     # #           #       #    # #    #   #   "
echo "#     # ###       #             #####  #    # #    #   #   "
echo "#     # #  #     # #                 # #####  #    #   #   "
echo "#     # #   #   #   #          #     # #      #    #   #   "
echo "####### #    # #     #          #####  #       ####    #   "
echo " "
echo " "

export TRADING_MODE=spot
export EXCHANGE=okx
./tests/backtests/backtesting-all-years-all-pairs.sh



echo " "
echo " "
echo "######                                                #####                      "
echo "#     # # #    #   ##   #    #  ####  ######         #     # #####   ####  ##### "
echo "#     # # ##   #  #  #  ##   # #    # #              #       #    # #    #   #   "
echo "######  # # #  # #    # # #  # #      #####           #####  #    # #    #   #   "
echo "#     # # #  # # ###### #  # # #      #                    # #####  #    #   #   "
echo "#     # # #   ## #    # #   ## #    # #              #     # #      #    #   #   "
echo "######  # #    # #    # #    #  ####  ######          #####  #       ####    #   "
echo " "
echo " "

export EXCHANGE=binance
./tests/backtests/backtesting-all-years-all-pairs.sh

echo " "
echo " "
echo "#    #                                        #####                      "
echo "#   #  #    #  ####   ####  # #    #         #     # #####   ####  ##### "
echo "#  #   #    # #    # #    # # ##   #         #       #    # #    #   #   "
echo "###    #    # #      #    # # # #  #          #####  #    # #    #   #   "
echo "#  #   #    # #      #    # # #  # #               # #####  #    #   #   "
echo "#   #  #    # #    # #    # # #   ##         #     # #      #    #   #   "
echo "#    #  ####   ####   ####  # #    #          #####  #       ####    #   "
echo " "
echo " "

export EXCHANGE=kucoin
./tests/backtests/backtesting-all-years-all-pairs.sh



echo " "
echo " "
echo "##     ## ##     ## ##    ## ######## #### ##    ##  ######   "
echo "##     ## ##     ## ###   ##    ##     ##  ###   ## ##    ##  "
echo "##     ## ##     ## ####  ##    ##     ##  ####  ## ##        "
echo "######### ##     ## ## ## ##    ##     ##  ## ## ## ##   #### "
echo "##     ## ##     ## ##  ####    ##     ##  ##  #### ##    ##  "
echo "##     ## ##     ## ##   ###    ##     ##  ##   ### ##    ##  "
echo "##     ##  #######  ##    ##    ##    #### ##    ##  ######   "


echo "######                #######                                     "
echo "#     #   ##   #####  #       #    # ##### #####  # ######  ####  "
echo "#     #  #  #  #    # #       ##   #   #   #    # # #      #      "
echo "######  #    # #    # #####   # #  #   #   #    # # #####   ####  "
echo "#     # ###### #    # #       #  # #   #   #####  # #           # "
echo "#     # #    # #    # #       #   ##   #   #   #  # #      #    # "
echo "######  #    # #####  ####### #    #   #   #    # # ######  ####  "
echo " "
echo " "

export TRADING_MODE=futures


echo " "
echo " "
echo " ####### #    # #     #         #######                                          "
echo " #     # #   #   #   #          #       #    # ##### #    # #####  ######  ####  "
echo " #     # #  #     # #           #       #    #   #   #    # #    # #      #      "
echo " #     # ###       #            #####   #    #   #   #    # #    # #####   ####  "
echo " #     # #  #     # #           #       #    #   #   #    # #####  #           # "
echo " #     # #   #   #   #          #       #    #   #   #    # #   #  #      #    # "
echo " ####### #    # #     #         #        ####    #    ####  #    # ######  ####  "
echo " "
echo " "

export EXCHANGE=okx
./tests/backtests/backtesting-for-hunting-bad-buys.sh

echo " "
echo " "
echo "######                                               #######                                          "
echo "#     # # #    #   ##   #    #  ####  ######         #       #    # ##### #    # #####  ######  ####  "
echo "#     # # ##   #  #  #  ##   # #    # #              #       #    #   #   #    # #    # #      #      "
echo "######  # # #  # #    # # #  # #      #####          #####   #    #   #   #    # #    # #####   ####  "
echo "#     # # #  # # ###### #  # # #      #              #       #    #   #   #    # #####  #           # "
echo "#     # # #   ## #    # #   ## #    # #              #       #    #   #   #    # #   #  #      #    # "
echo "######  # #    # #    # #    #  ####  ######         #        ####    #    ####  #    # ######  ####  "
echo " "
echo " "

export EXCHANGE=binance
./tests/backtests/backtesting-for-hunting-bad-buys.sh


export TRADING_MODE=spot

echo " "
echo " "
echo "####### #    # #     #          #####                      "
echo "#     # #   #   #   #          #     # #####   ####  ##### "
echo "#     # #  #     # #           #       #    # #    #   #   "
echo "#     # ###       #             #####  #    # #    #   #   "
echo "#     # #  #     # #                 # #####  #    #   #   "
echo "#     # #   #   #   #          #     # #      #    #   #   "
echo "####### #    # #     #          #####  #       ####    #   "
echo " "
echo " "

export EXCHANGE=okx
./tests/backtests/backtesting-for-hunting-bad-buys.sh

echo " "
echo " "
echo "######                                                #####                      "
echo "#     # # #    #   ##   #    #  ####  ######         #     # #####   ####  ##### "
echo "#     # # ##   #  #  #  ##   # #    # #              #       #    # #    #   #   "
echo "######  # # #  # #    # # #  # #      #####           #####  #    # #    #   #   "
echo "#     # # #  # # ###### #  # # #      #                    # #####  #    #   #   "
echo "#     # # #   ## #    # #   ## #    # #              #     # #      #    #   #   "
echo "######  # #    # #    # #    #  ####  ######          #####  #       ####    #   "
echo " "
echo " "


export EXCHANGE=binance
./tests/backtests/backtesting-for-hunting-bad-buys.sh


echo " "
echo " "
echo "#    #                                        #####                      "
echo "#   #  #    #  ####   ####  # #    #         #     # #####   ####  ##### "
echo "#  #   #    # #    # #    # # ##   #         #       #    # #    #   #   "
echo "###    #    # #      #    # # # #  #          #####  #    # #    #   #   "
echo "#  #   #    # #      #    # # #  # #               # #####  #    #   #   "
echo "#   #  #    # #    # #    # # #   ##         #     # #      #    #   #   "
echo "#    #  ####   ####   ####  # #    #          #####  #       ####    #   "
echo " "
echo " "

export EXCHANGE=kucoin
./tests/backtests/backtesting-for-hunting-bad-buys.sh
