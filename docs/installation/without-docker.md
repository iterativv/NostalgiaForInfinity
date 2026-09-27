## Without Docker

After cloning the repository, there are only a few steps required to run NostalgiaForInfinity without Docker.

### Clone repo

Clone the NFI repository:

```bash
git clone https://github.com/iterativv/NostalgiaForInfinity
```

### Enter repo

Navigate into the repository:

```bash
cd NostalgiaForInfinity
```

### Copy the recommended configuration

Copy the recommended configuration to your `user_data` directory:

```bash
cp configs/recommended_config.json user_data/config.json
```

### Copy the private configuration

NFI keeps sensitive information such as your exchange API credentials in a separate configuration file.

Copy the example private configuration:

```bash
cp configs/exampleconfig_secret.json user_data/private_config.json
```

### Edit `user_data/private_config.json`

Open the private configuration file:

```bash
nano user_data/private_config.json
```

This file contains your private settings, including your exchange API credentials and API server authentication.

A basic example:

```json
{
    "bot_name": "freqtrade",
    "stake_currency": "USDT",
    "fiat_display_currency": "USD",

    "dry_run": true,

    "exchange": {
        "name": "binance",
        "key": "YOUR_EXCHANGE_API_KEY",
        "secret": "YOUR_EXCHANGE_API_SECRET",
        "ccxt_config": {},
        "ccxt_async_config": {},
        "pair_whitelist": []
    },

    "telegram": {
        "enabled": false,
        "token": "",
        "chat_id": ""
    },

    "api_server": {
        "enabled": true,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080,
        "verbosity": "error",
        "enable_openapi": false,
        "jwt_secret_key": "CHANGE_THIS_TO_A_RANDOM_SECRET",
        "CORS_origins": [],
        "username": "user",
        "password": "CHANGE_THIS_PASSWORD"
    },

    "initial_state": "running",
    "force_entry_enable": true,

    "internals": {
        "process_throttle_secs": 5
    }
}
```

For complete information about Freqtrade configuration options, see the [Freqtrade configuration documentation](https://www.freqtrade.io/en/stable/configuration/).

> **Security:** Keep `private_config.json` private. Do not commit your exchange API key, API secret, passwords, or other credentials to GitHub.

### Edit `user_data/config.json`

Next, open the main NFI configuration:

```bash
nano user_data/config.json
```

The configuration should load the NFI strategy and the required NFI configuration files:

```json
{
    "strategy": "NostalgiaForInfinityX8",

    "add_config_files": [
        "../configs/trading_mode-spot.json",
        "../configs/pairlist-volume-binance-usdt.json",
        "../configs/blacklist-binance.json",
        "../configs/exampleconfig.json",
        "private_config.json"
    ]
}
```

The `private_config.json` file is loaded separately so that sensitive information does not need to be stored in the main configuration.

If you are using futures instead of spot trading, change the trading-mode configuration accordingly and make sure your exchange supports futures trading.

See the [Freqtrade exchange documentation](https://www.freqtrade.io/en/stable/exchanges/) for supported exchanges.

### Start Freqtrade

From the NFI directory, start Freqtrade:

```bash
freqtrade trade --config user_data/config.json
```

If everything is configured correctly, Freqtrade will load the NFI strategy and start the bot.

You should see output similar to the Docker installation, including messages showing that:

* the configuration was loaded,
* `NostalgiaForInfinityX8` was loaded,
* the configured exchange was detected,
* the pairlist was loaded,
* the API server was started, if enabled,
* and the bot entered the `RUNNING` state.

### Open the Freqtrade web interface

If the API server is enabled and configured to listen on port `8080`, open:

```text
http://127.0.0.1:8080
```

The Freqtrade web interface should then be available.

### Dry run

For your first setup, keep:

```json
"dry_run": true
```

This allows you to verify that the configuration, exchange connection, strategy, and pairlist are working without placing real trades.

Only change this to:

```json
"dry_run": false
```

once you have completed your testing and are ready to enable live trading.


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

  "strategy": "NostalgiaForInfinityX8",
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