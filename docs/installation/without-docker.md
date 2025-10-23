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

  "strategy": "NostalgiaForInfinityX6",
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
