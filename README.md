# NostalgiaForInfinity

Trading strategy for the [Freqtrade](https://www.freqtrade.io) crypto bot. For backtesting results, check out the comments in the individual [commit](https://github.com/iterativv/NostalgiaForInfinity/commits/main) page.



# Quick Start

## With Docker

### Clone repo
```bash
git clone https://github.com/iterativv/NostalgiaForInfinity
```
### enter repo directory
```bash
cd NostalgiaForInfinity
```

### copy configurations
```bash
cp configs/recommended_config.json user_data/config.json
cp live-account-example.env .env
```

### edit your .env file
```
# Change all necessary parts as needed

FREQTRADE__BOT_NAME=Example_Test_Account
FREQTRADE__MAX_OPEN_TRADES=10

FREQTRADE__TRADING_MODE=spot

FREQTRADE__EXCHANGE__NAME=binance
FREQTRADE__EXCHANGE__KEY=Put_Your_Exchange_Key_Here
FREQTRADE__EXCHANGE__SECRET=Put_Your_Exchange_Keys_Secret_Here

FREQTRADE__TELEGRAM__ENABLED=false
FREQTRADE__TELEGRAM__TOKEN=123123123:123123YourTelegramTokenConfiguration
FREQTRADE__TELEGRAM__CHAT_ID=461799865

FREQTRADE__API_SERVER__ENABLED=true
FREQTRADE__API_SERVER__LISTEN_PORT=8080
FREQTRADE__API_SERVER__USERNAME=user
FREQTRADE__API_SERVER__PASSWORD=pass
FREQTRADE__API_SERVER__JWT_SECRET_KEY=Put_Your_JWT_Secret_Key_Here
FREQTRADE__API_SERVER__WS_TOKEN=JustWriteSomethingVeryRandom

# Time Zone
TZ=Europe/Istanbul
FREQTRADE__DRY_RUN=true
FREQTRADE__STRATEGY=NostalgiaForInfinityX5
```

### Start docker container
```bash
docker compose up
```


---
you should see this screen and everything is ok :
```bash
docker compose up
[+] Running 2/0
 ✔ Container Example_Test_Account_binance_futures-NostalgiaForInfinityX5  Created                                                                                                                                                          0.0s
 ✔ Container nostalgiaforinfinity-restarter-1                             Created                                                                                                                                                          0.0s
Attaching to Example_Test_Account_binance_futures-NostalgiaForInfinityX5, restarter-1
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:25,075 - freqtrade - INFO - freqtrade 2024.10
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:25,563 - numexpr.utils - INFO - NumExpr defaulting to 12 threads.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,241 - freqtrade.worker - INFO - Starting worker 2024.10
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,241 - freqtrade.configuration.load_config - INFO - Using config: user_data/config.json ...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,243 - freqtrade.configuration.load_config - INFO - Using config: ../configs/trading_mode-spot.json ...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,244 - freqtrade.configuration.load_config - INFO - Using config: ../configs/pairlist-volume-binance-usdt.json ...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,244 - freqtrade.configuration.load_config - INFO - Using config: ../configs/blacklist-binance.json ...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,245 - freqtrade.configuration.load_config - INFO - Using config: ../configs/exampleconfig.json ...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,245 - freqtrade.configuration.load_config - INFO - Using config: ../configs/exampleconfig_secret.json ...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,247 - freqtrade.loggers - INFO - Verbosity set to 0
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,247 - freqtrade.configuration.configuration - INFO - Runmode set to dry_run.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,247 - freqtrade.configuration.configuration - INFO - Parameter --db-url detected ...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,247 - freqtrade.configuration.configuration - WARNING - `force_entry_enable` RPC message enabled.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,247 - freqtrade.configuration.configuration - INFO - Dry run is enabled
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,248 - freqtrade.configuration.configuration - INFO - Using DB: "sqlite:////freqtrade/user_data/Example_Test_Account_binance_futures-tradesv3.sqlite"
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,248 - freqtrade.configuration.configuration - INFO - Using max_open_trades: 6 ...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,273 - freqtrade.configuration.configuration - INFO - Using user-data directory: /freqtrade/user_data ...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,274 - freqtrade.configuration.configuration - INFO - Using data directory: /freqtrade/user_data/data/binance ...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,274 - freqtrade.exchange.check_exchange - INFO - Checking exchange...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,280 - freqtrade.exchange.check_exchange - INFO - Exchange "binance" is officially supported by the Freqtrade development team.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:27,280 - freqtrade.configuration.configuration - INFO - Using pairlist from configuration.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,014 - freqtrade.resolvers.iresolver - INFO - Using resolved strategy NostalgiaForInfinityX5 from '/freqtrade/NostalgiaForInfinityX5.py'...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,015 - freqtrade.strategy.hyper - INFO - Found no parameter file.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,015 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'timeframe' with value in config file: 5m.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,015 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'order_types' with value in config file: {'entry': 'limit', 'exit': 'limit', 'emergency_exit': 'limit', 'force_entry': 'limit', 'force_exit': 'limit', 'stoploss': 'limit', 'stoploss_on_exchange': False, 'stoploss_on_exchange_interval': 60, 'stoploss_on_exchange_limit_ratio': 0.99}.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,016 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'stake_currency' with value in config file: USDT.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,016 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'stake_amount' with value in config file: unlimited.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,016 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'unfilledtimeout' with value in config file: {'entry': 20, 'exit': 20, 'exit_timeout_count': 0, 'unit': 'minutes'}.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,016 - freqtrade.resolvers.strategy_resolver - INFO - Override strategy 'max_open_trades' with value in config file: 6.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,016 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using minimal_roi: {}
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,016 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using timeframe: 5m
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,016 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using stoploss: -0.99
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,017 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using trailing_stop: False
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,017 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using trailing_stop_positive: 0.01
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,017 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using trailing_stop_positive_offset: 0.03
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,017 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using trailing_only_offset_is_reached: True
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,017 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using use_custom_stoploss: False
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,017 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using process_only_new_candles: True
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,017 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using order_types: {'entry': 'limit', 'exit': 'limit', 'emergency_exit': 'limit', 'force_entry': 'limit', 'force_exit': 'limit', 'stoploss': 'limit', 'stoploss_on_exchange': False, 'stoploss_on_exchange_interval': 60, 'stoploss_on_exchange_limit_ratio': 0.99}
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,017 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using order_time_in_force: {'entry': 'GTC', 'exit': 'GTC'}
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,018 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using stake_currency: USDT
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,018 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using stake_amount: unlimited
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,018 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using startup_candle_count: 800
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,018 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using unfilledtimeout: {'entry': 20, 'exit': 20, 'exit_timeout_count': 0, 'unit': 'minutes'}
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,018 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using use_exit_signal: True
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,018 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using exit_profit_only: False
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,018 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using ignore_roi_if_entry_signal: True
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,018 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using exit_profit_offset: 0.0
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,019 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using disable_dataframe_checks: False
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,019 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using ignore_buying_expired_candle_after: 0
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,019 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using position_adjustment_enable: True
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,019 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using max_entry_position_adjustment: -1
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,019 - freqtrade.resolvers.strategy_resolver - INFO - Strategy using max_open_trades: 6
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,019 - freqtrade.configuration.config_validation - INFO - Validating configuration ...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,021 - freqtrade.exchange.exchange - INFO - Instance is running with dry_run enabled
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,021 - freqtrade.exchange.exchange - INFO - Using CCXT 4.4.24
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,021 - freqtrade.exchange.exchange - INFO - Applying additional ccxt config: {'enableRateLimit': True, 'rateLimit': 60, 'options': {'brokerId': None, 'partner': {'spot': {'id': None, 'key': None}, 'future': {'id': None, 'key': None}}}}
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,025 - freqtrade.exchange.exchange - INFO - Applying additional ccxt config: {'enableRateLimit': True, 'rateLimit': 60, 'options': {'brokerId': None, 'partner': {'spot': {'id': None, 'key': None}, 'future': {'id': None, 'key': None}}}}
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,031 - freqtrade.exchange.exchange - INFO - Applying additional ccxt config: {'enableRateLimit': True, 'rateLimit': 60, 'options': {'brokerId': None, 'partner': {'spot': {'id': None, 'key': None}, 'future': {'id': None, 'key': None}}}}
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:28,036 - freqtrade.exchange.exchange - INFO - Using Exchange "Binance"
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:30,629 - freqtrade.resolvers.exchange_resolver - INFO - Using resolved exchange 'Binance'...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:30,654 - freqtrade.wallets - INFO - Wallets synced.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:30,962 - freqtrade.rpc.rpc_manager - INFO - Enabling rpc.api_server
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,083 - freqtrade.rpc.api_server.webserver - INFO - Starting HTTP Server at 0.0.0.0:8080
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,083 - freqtrade.rpc.api_server.webserver - WARNING - SECURITY WARNING - No password for local REST Server defined. Please make sure that this is intentional!
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,084 - freqtrade.rpc.api_server.webserver - WARNING - SECURITY WARNING - `jwt_secret_key` seems to be default.Others may be able to log into your bot.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,084 - freqtrade.rpc.api_server.webserver - INFO - Starting Local Rest Server.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,093 - uvicorn.error - INFO - Started server process [1]
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,094 - uvicorn.error - INFO - Waiting for application startup.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,094 - uvicorn.error - INFO - Application startup complete.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,094 - uvicorn.error - INFO - Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,101 - freqtrade.resolvers.iresolver - INFO - Using resolved pairlist VolumePairList from '/freqtrade/freqtrade/plugins/pairlist/VolumePairList.py'...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,103 - freqtrade.resolvers.iresolver - INFO - Using resolved pairlist FullTradesFilter from '/freqtrade/freqtrade/plugins/pairlist/FullTradesFilter.py'...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,108 - freqtrade.resolvers.iresolver - INFO - Using resolved pairlist AgeFilter from '/freqtrade/freqtrade/plugins/pairlist/AgeFilter.py'...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,117 - freqtrade.resolvers.iresolver - INFO - Using resolved pairlist PriceFilter from '/freqtrade/freqtrade/plugins/pairlist/PriceFilter.py'...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,123 - freqtrade.resolvers.iresolver - INFO - Using resolved pairlist SpreadFilter from '/freqtrade/freqtrade/plugins/pairlist/SpreadFilter.py'...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,127 - freqtrade.resolvers.iresolver - INFO - Using resolved pairlist VolumePairList from '/freqtrade/freqtrade/plugins/pairlist/VolumePairList.py'...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,653 - VolumePairList - INFO - Pair BNB/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,653 - VolumePairList - INFO - Pair TUSD/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,653 - VolumePairList - INFO - Pair NULS/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,654 - VolumePairList - INFO - Pair USDC/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,654 - VolumePairList - INFO - Pair ZEC/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,654 - VolumePairList - INFO - Pair CHZ/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,654 - VolumePairList - INFO - Pair REN/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,655 - VolumePairList - INFO - Pair CTXC/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,655 - VolumePairList - INFO - Pair FTT/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,655 - VolumePairList - INFO - Pair EUR/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,656 - VolumePairList - INFO - Pair MBL/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,656 - VolumePairList - INFO - Pair BAL/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,656 - VolumePairList - INFO - Pair IRIS/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,656 - VolumePairList - INFO - Pair NMR/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,656 - VolumePairList - INFO - Pair LUNA/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,657 - VolumePairList - INFO - Pair PAXG/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,657 - VolumePairList - INFO - Pair SUN/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,657 - VolumePairList - INFO - Pair AKRO/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,657 - VolumePairList - INFO - Pair HARD/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,657 - VolumePairList - INFO - Pair JUV/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,658 - VolumePairList - INFO - Pair PSG/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,658 - VolumePairList - INFO - Pair ATM/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,658 - VolumePairList - INFO - Pair ASR/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,658 - VolumePairList - INFO - Pair FIRO/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,658 - VolumePairList - INFO - Pair ACM/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,659 - VolumePairList - INFO - Pair LINA/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,659 - VolumePairList - INFO - Pair BAR/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,659 - VolumePairList - INFO - Pair ELF/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,659 - VolumePairList - INFO - Pair USDP/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,659 - VolumePairList - INFO - Pair BETA/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,660 - VolumePairList - INFO - Pair CITY/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,660 - VolumePairList - INFO - Pair JASMY/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,660 - VolumePairList - INFO - Pair CVX/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,660 - VolumePairList - INFO - Pair ACA/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,660 - VolumePairList - INFO - Pair ALPINE/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,661 - VolumePairList - INFO - Pair AMB/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,661 - VolumePairList - INFO - Pair USTC/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,661 - VolumePairList - INFO - Pair QKC/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,661 - VolumePairList - INFO - Pair ID/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,661 - VolumePairList - INFO - Pair OAX/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,661 - VolumePairList - INFO - Pair SNT/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,662 - VolumePairList - INFO - Pair FDUSD/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,662 - VolumePairList - INFO - Pair ARK/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,662 - VolumePairList - INFO - Pair CREAM/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,662 - VolumePairList - INFO - Pair ORDI/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,662 - VolumePairList - INFO - Pair AEUR/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,663 - VolumePairList - INFO - Pair 1000SATS/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:31,663 - VolumePairList - INFO - Pair JUP/USDT in your blacklist. Removing it from whitelist...
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:34,718 - AgeFilter - INFO - Validated 100 pairs.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:34,777 - freqtrade.plugins.pairlistmanager - INFO - Whitelist with 80 pairs: ['BTC/USDT', 'ETH/USDT', 'DOGE/USDT', 'XRP/USDT', 'SOL/USDT', 'XLM/USDT', 'SAND/USDT', 'PEPE/USDT', 'PNUT/USDT', 'ADA/USDT', 'AVAX/USDT', 'WIF/USDT', 'SUI/USDT', 'WLD/USDT', 'SEI/USDT', 'ARB/USDT', 'SHIB/USDT', 'NEAR/USDT', 'TIA/USDT', 'NEIRO/USDT', 'DOT/USDT', 'BONK/USDT', 'TRX/USDT', 'LINK/USDT', 'FTM/USDT', 'FET/USDT', 'OP/USDT', 'ENS/USDT', 'ACT/USDT', 'UNI/USDT', 'MANA/USDT', 'APT/USDT', 'RUNE/USDT', 'FIL/USDT', 'GALA/USDT', 'LDO/USDT', 'POL/USDT', 'STX/USDT', 'ETC/USDT', 'TAO/USDT', 'LTC/USDT', 'HBAR/USDT', 'COS/USDT', 'FLOKI/USDT', 'ENA/USDT', 'ETHFI/USDT', 'CAKE/USDT', 'BOME/USDT', 'ICP/USDT', 'BCH/USDT', 'AAVE/USDT', 'RENDER/USDT', 'AR/USDT', 'NOT/USDT', 'DOGS/USDT', 'SCRT/USDT', 'EIGEN/USDT', 'CRV/USDT', 'TON/USDT', 'INJ/USDT', 'STRK/USDT', 'MKR/USDT', 'SSV/USDT', 'ATOM/USDT', 'GLM/USDT', 'ZRO/USDT', 'KDA/USDT', 'HOT/USDT', 'ARKM/USDT', 'AXS/USDT', 'ALGO/USDT', 'CKB/USDT', 'SAGA/USDT', 'AEVO/USDT', 'PYTH/USDT', 'PEOPLE/USDT', 'BLUR/USDT', 'GRT/USDT', 'PENDLE/USDT', 'XTZ/USDT']
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:34,777 - freqtrade.strategy.hyper - INFO - No params for buy found, using default values.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:34,778 - freqtrade.strategy.hyper - INFO - No params for sell found, using default values.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:34,778 - freqtrade.strategy.hyper - INFO - No params for protection found, using default values.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:34,779 - freqtrade.plugins.protectionmanager - INFO - No protection Handlers defined.
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:34,779 - freqtrade.rpc.rpc_manager - INFO - Sending rpc message: {'type': status, 'status': 'running'}
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:34,779 - freqtrade.worker - INFO - Changing state to: RUNNING
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:34,782 - freqtrade.rpc.rpc_manager - INFO - Sending rpc message: {'type': warning, 'status': 'Dry run is enabled. All trades are simulated.'}
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:34,783 - freqtrade.rpc.rpc_manager - INFO - Sending rpc message: {'type': startup, 'status': '*Exchange:* `binance`\n*Stake per trade:* `unlimited USDT`\n*Minimum ROI:* `{}`\n*Stoploss:* `-0.99`\n*Position adjustment:* `On`\n*Timeframe:* `5m`\n*Strategy:* `NostalgiaForInfinityX5`'}
Example_Test_Account_binance_futures-NostalgiaForInfinityX5  | 2024-11-25 23:30:34,783 - freqtrade.rpc.rpc_manager - INFO - Sending rpc message: {'type': startup, 'status': "Searching for USDT pairs to buy and sell based on [{'VolumePairList': 'VolumePairList - top 100 volume pairs.'}, {'FullTradesFilter': 'FullTradesFilter - Shrink whitelist when trade slots are full.'}, {'AgeFilter': 'AgeFilter - Filtering pairs with age less than 4 days'}, {'PriceFilter': 'PriceFilter - Filtering pairs priced below 0.3%.'}, {'SpreadFilter': 'SpreadFilter - Filtering pairs with ask/bid diff above 0.50%.'}, {'VolumePairList': 'VolumePairList - top 80 volume pairs.'}]"}
```

### Open your browser
http://0.0.0.0:8080
 system is up and running

---

## Without Docker
 after cloning repo there are only few steps:

### **clone repo**
```bash
git clone https://github.com/iterativv/NostalgiaForInfinity
```
### enter repo
```bash
cd NostalgiaForInfinity
```

### copy configs/recommended_config.json -> user_data/config.json
```bash
cp configs/recommended_config.json user_data/config.json
```
### copy configs/exampleconfig_secret.json -> user_data/private_config.json
```bash
cp configs/exampleconfig_secret.json user_data/private_config.json
```
### edit user_data/private_config.json (your private key etc)

```json
// For full documentation on Freqtrade configuration files please visit https://www.freqtrade.io/en/stable/configuration/
{
  "bot_name": "freqtrade", // name your bot
  "stake_currency": "USDT",
  "fiat_display_currency": "USD",
  "dry_run": true, // change after your tests
  "cancel_open_orders_on_exit": false,
  "entry_pricing": {
    "use_order_book": true,
    "order_book_top": 1,
    "check_depth_of_market": {
      "enabled": false,
      "bids_to_ask_delta": 1
    }
  },
  "exit_pricing": {
    "use_order_book": true,
    "order_book_top": 1
  },
  "exchange": {
    "name": "binance",
    "key": "",
    "secret": "",
    "ccxt_config": {},
    "ccxt_async_config": {},
    "pair_whitelist": []
  },
  "telegram": {
    "enabled": false,
    "token": "",
    "chat_id": "",
    "reload": true,
    "keyboard": [
      ["/daily", "/stats", "/balance", "/profit"],
      ["/status table", "/performance"],
      ["/reload_config", "/count", "/logs"]
    ],
    "notification_settings": {
      "status": "silent",
      "protection_trigger_global": "on",
      "warning": "on",
      "startup": "off",
      "entry": "silent",
      "entry_fill": "on",
      "entry_cancel": "on",
      "exit_cancel": "on",
      "exit_fill": "on",
      "exit": {
        "roi": "silent",
        "emergency_exit": "silent",
        "force_exit": "silent",
        "exit_signal": "silent",
        "trailing_stop_loss": "silent",
        "stop_loss": "silent",
        "stoploss_on_exchange": "silent",
        "custom_exit": "silent"
      },
      "strategy_msg": "silent",
    },
    "balance_dust_level": 0.01
  },
  "api_server": {
    "enabled": true,
    "listen_ip_address": "0.0.0.0",
    "listen_port": 8080,
    "verbosity": "error",
    "enable_openapi": false,
    "jwt_secret_key": "",
    "CORS_origins": [""],
    "username": "user", // << username
    "password": "pass" // << password
  },

  "initial_state": "running",
  "force_entry_enable": true,
  "internals": {
    "process_throttle_secs": 5
  }
}

```

### edit user_data/config.json (exchange, blacklist etc)
```json
   {
  // For full documentation on Freqtrade configuration files please visit https://www.freqtrade.io/en/stable/configuration/
  // Copy this file to user_data/config.json
  // make sure your secret files are really in a secret place
  // copy configs/exampleconfig_secret.json to user_data/config-private.json
  // Change     "dry_run": true, to     "dry_run": false, after testing

  "strategy": "NostalgiaForInfinityX5",
  "add_config_files": [
    "../configs/trading_mode-spot.json",
    "../configs/pairlist-volume-binance-usdt.json",
    "../configs/blacklist-binance.json",
    "../configs/exampleconfig.json",
    "private_config.json" // << Your private config file which you created
  ]
    }
```

### Run freqtrade trade and everything will work as necessary
```bash
freqtrade trade
```

You will see same output as docker


# Run Backtests with your own configuration

If you plan to only clone the repository to use the strategy, a regular `git clone` will do.

However, if you plan on running additional backtest and run the test suite, you need to download data.
## Fast download test data from DigiTuccar Historical Trade Data Repo

There is a repo for this :
https://github.com/DigiTuccar/HistoricalDataForTradeBacktest

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


## Change strategy

Add strategies to the [user_data/strategies](user_data/strategies) folder and also in the [docker-compose.yml](docker-compose.yml) file at `strategy-list` add your strategy in the list.

[Additional Information : NFINext is a older strategy on 5m tf , NFI-NG is a 15m tf strategy abandoned mid development , NFIX is the currently developed strategy (a rework of NG on 5m tf)]

## General Recommendations

For optimal performance, suggested to use between 4 and 6 open trades, with unlimited stake.

A pairlist with 40 to 80 pairs. Volume pairlist works well.

Prefer stable coin (USDT, USDC etc) pairs, instead of BTC or ETH pairs.

Highly recommended to blacklist leveraged tokens (*BULL, *BEAR, *UP, *DOWN etc).

Ensure that you don't override any variables in you config.json. Especially the timeframe (must be 5m).

- `use_exit_signal` must set to true (or not set at all).
- `exit_profit_only` must set to false (or not set at all).
- `ignore_roi_if_entry_signal` must set to true (or not set at all).

## Hold support

### Specific Trades

In case you want to have SOME of the trades to only be sold when on profit, add a file named "nfi-hold-trades.json" in your `user_data/` directory

The contents should be similar to:

`{"trade_ids": [1, 3, 7], "profit_ratio": 0.005}`

Or, for individual profit ratios (Notice the trade ID's as strings):

`{"trade_ids": {"1": 0.001, "3": -0.005, "7": 0.05}}`

NOTE:

- `trade_ids` is a list of integers, the trade ID's, which you can get from the logs or from the output of the telegram `/status` command.
- Regardless of the defined profit ratio(s), the strategy MUST still produce a SELL signal for the HOLD support logic to run, which is to say, the trade will sell only if there's a proper sell signal AND the profit target has been reached.
- This feature can be completely disabled by changing `hold_support_enabled = True` to false in the strategy file.

### Specific Pairs

In case you want to have some pairs to always be on held until a specific profit, using the same "nfi-hold-trades.json" file add something like:

`{"trade_pairs": {"BTC/USDT": 0.001, "ETH/USDT": -0.005}}`

### Specific Trades and Pairs

It is also valid to include specific trades and pairs on the holds file, for example:

`{"trade_ids": {"1": 0.001}, "trade_pairs": {"BTC/USDT": 0.001}}`

## Donations

Absolutely not required. However, will be accepted as a token of appreciation.

- BTC: `bc1qvflsvddkmxh7eqhc4jyu5z5k6xcw3ay8jl49sk`
- ETH (ERC20): `0x83D3cFb8001BDC5d2211cBeBB8cB3461E5f7Ec91`
- BEP20/BSC (USDT, ETH, BNB, ...): `0x86A0B21a20b39d16424B7c8003E4A7e12d78ABEe`
- TRC20/TRON (USDT, TRON, ...): `TTAa9MX6zMLXNgWMhg7tkNormVHWCoq8Xk`

- Patreon : https://www.patreon.com/iterativ

### Referral Links

If you like to help, you can also use the following links to sign up to various exchanges:

- Binance: https://www.binance.com/join?ref=C68K26A9 (20% discount on trading fees)
- Kucoin: https://www.kucoin.com/r/af/QBSSS5J2 (20% lifetime discount on trading fees)
- Gate.io: https://www.gate.io/share/nfinfinity (20% lifetime discount on trading fees)
- OKX: https://www.okx.com/join/11749725931 (20% discount on trading fees)
- MEXC: https://promote.mexc.com/a/luA6Xclb (10% discount on trading fees)
- ByBit: https://partner.bybit.com/b/nfi
- Bitget: https://bonus.bitget.com/fdqe83481698435803831 (lifetime 20% rebate all plus 10% discount on spot fees)
- BitMart: https://www.bitmart.com/invite/nfinfinity/en-US (20% lifetime discount on trading fees)
- HTX: https://www.htx.com/invite/en-us/1f?invite_code=ubpt2223 (Welcome Bonus worth 241 USDT upon completion of a deposit and trade)
- Bitvavo: https://bitvavo.com/invite?a=D22103A4BC (no fees for the first € 1000)

### Discord Link

This is where we chat, hangout and contribute as a community (both links is the same server)

- [Discord](https://discord.gg/DeAmv3btxQ)
- [Discord](https://discord.gg/nzVeNvZsQq)
