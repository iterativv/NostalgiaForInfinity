export STRATEGY_NAME=NostalgiaForInfinityX4
export STRATEGY_VERSION=`grep version $STRATEGY_NAME.py  -A 1|grep return|cut -d '"' -f 2|sed "s/\.//g"`

export TRADING_MODE=futures

export EXCHANGE=okx
./tests/backtests/backtesting-for-hunting-bad-buys.sh
./tests/backtests/backtesting-all-years-all-pairs.sh

export EXCHANGE=binance
./tests/backtests/backtesting-for-hunting-bad-buys.sh
./tests/backtests/backtesting-all-years-all-pairs.sh


export TRADING_MODE=spot

export EXCHANGE=okx
./tests/backtests/backtesting-for-hunting-bad-buys.sh
./tests/backtests/backtesting-all-years-all-pairs.sh

export EXCHANGE=binance
./tests/backtests/backtesting-for-hunting-bad-buys.sh
./tests/backtests/backtesting-all-years-all-pairs.sh

export EXCHANGE=kucoin
./tests/backtests/backtesting-for-hunting-bad-buys.sh
./tests/backtests/backtesting-all-years-all-pairs.sh
