# Production Config Adjustments

Changes from the [NFI default example config](https://github.com/iterativv/NostalgiaForInfinity/blob/main/configs/exampleconfig.json) to `config.production.json`.

## Budget Constraints

| Setting | Default | Production | Reason |
|---|---|---|---|
| `dry_run_wallet` | 10000 | 250 | Running with a $250 starting wallet |
| `max_open_trades` | 6 | 6 | Matches NFI minimum recommendation. At 3x leverage, each trade gets ~$123 position |

## Futures Mode

The default config is written for spot. We're trading Binance USDT-M futures:

| Setting | Production Value |
|---|---|
| `trading_mode` | `futures` |
| `margin_mode` | `isolated` |
| `exchange.name` | `binance` |

The strategy auto-detects futures mode via `trading_mode` and enables shorting with `can_short = True` and `futures_mode_leverage = 3.0`.

## Pair Selection

The default config leaves pairlist and blacklist empty. We use:

- **VolumePairList** with 40 assets, filtered through AgeFilter (60 days), PriceFilter, SpreadFilter, and RangeStabilityFilter
- **Blacklist** covering leveraged tokens (BULL/BEAR/UP/DOWN), fiat pairs, stablecoins, and fan tokens — as recommended by NFI
- **MKR/OMNI** blacklisted due to high per-unit price causing minimum notional issues on small accounts

## Notifications

| Setting | Default | Production |
|---|---|---|
| `telegram.enabled` | not set | `false` |
| `webhook.enabled` | not set | `true` |

Telegram is disabled in favor of a custom webhook notifier at `https://freqtrade-notifier.lamualfa.dev/webhook/freqtrade`. All webhook templates (`webhookentry`, `webhookentryfill`, `webhookentrycancel`, `webhookexit`, `webhookexitfill`, `webhookexitcancel`, `webhookstatus`) are configured with freqtrade RPC placeholders.

## API Server

Enabled for remote access and monitoring:

- `listen_ip_address`: `0.0.0.0`
- `listen_port`: `8080`
- `enable_openapi`: `false`
- Credentials set via environment variables

## Data Format

| Setting | Production Value |
|---|---|
| `dataformat_ohlcv` | `feather` |
| `dataformat_trades` | `feather` |

Faster reads/writes compared to the default `jsongz`.

## Secrets

All sensitive values are empty strings in the config file and injected at runtime via environment variables:

- `exchange.key` / `exchange.secret`
- `api_server.jwt_secret_key`
- `api_server.username` / `api_server.password`
- `telegram.token` / `telegram.chat_id`

## Unchanged from Default

These remain identical to the NFI example config:

- `timeframe`: `5m` (must not be overridden)
- `stake_amount`: `unlimited`
- `tradable_balance_ratio`: `0.99`
- `unfilledtimeout`: entry 3m, exit 2m
- `order_types`: all `limit`, `stoploss_on_exchange: false`
- `entry_pricing` / `exit_pricing`: `use_order_book: true` (NFI default is `false`, but Binance futures requires order book pricing — ticker endpoint is unavailable)
- `rateLimit`: `60`
- `process_throttle_secs`: `5`
- `stoploss_on_exchange_interval`: `60`
- `stoploss_on_exchange_limit_ratio`: `0.99`
