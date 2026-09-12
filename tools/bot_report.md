# `bot_report.py` — redacted telemetry report for freqtrade bots

`tools/bot_report.py` exports the available information from a running freqtrade
instance (config, open/closed trades, performance, pair lists, locks, plot
config, system info) into a single JSON file, so strategy developers can review
how a strategy behaves in production and adjust it — similar to telemetry.

Everything is collected over the freqtrade REST API with read-only GET requests.

```sh
python tools/bot_report.py --url http://127.0.0.1:8080 \
    --username freqtrader --password ... -o report.json
# or via env: FREQTRADE_API_URL / FREQTRADE_API_USERNAME / FREQTRADE_API_PASSWORD
```

Redaction is on by default (`--redact`); `--no-redact` exports an unredacted
report for private diagnostics only — never share that file.

## Redacted fields and why

Redacted values are replaced with `"<redacted>"`, keeping the JSON structure
intact so consumers can see what was removed.

### Credentials and keys — reason: they grant access to the account or reveal its identity

- Any key containing a credential token: `key`, `secret`, `password`, `passwd`,
  `token`, `chat`, `webhook`, `credential` — e.g. `exchange.key`,
  `exchange.secret`, `api_server.username`, `api_server.password`,
  `telegram.token`, `telegram.chat_id`, `discord.webhook_url`, `ws_token`
- `ccxt_config` / `ccxt_async_config` — whole objects, since they commonly hold
  API keys
- `uid` and any key combining `order`/`account`/`user`/`client`/`telegram` with
  `id`

### Account and exchange order identifiers — reason: lookup risk

- `order_id` and any `*_order_id` (e.g. `stoploss_order_id`): exchange order ids
  could be looked up on the exchange to identify the account and its position
  sizes.
- Local counters (`trade_id`, `id`) are kept — they are internal sequence
  numbers, not account identifiers.

### Absolute currency values — reason: any one of them anchors the account size

Balances, stakes, costs, absolute PnL, fees in currency, volumes, and drawdown
high-water marks are all removed:

| group | keys |
|---|---|
| absolute PnL | `abs_profit`, `profit_abs`, `close_profit_abs`, `total_profit_abs`, `realized_profit`, `best_pair_profit_abs`, `*_abs` money fields |
| PnL in stake/fiat currency | `profit_closed_coin`, `profit_all_coin`, `profit_closed_fiat`, `profit_all_fiat`, `fiat_value`, `*_coin`, `*_fiat` |
| stakes & capital | `stake_amount`, `max_stake_amount`, `total_stake`, `starting_balance`, `available_capital`, `total_capital`, `dry_run_wallet` |
| trade amounts & costs | `amount`, `amount_requested`, `filled`, `remaining`, `cost`, `safe_cost`, `fee_open_cost`, `fee_close_cost`, `open_trade_value` |
| fees & funding | `funding_fee`, `funding_fees`, `*_fee` |
| drawdown marks | `max_drawdown_abs`, `current_drawdown_abs`, `drawdown_high`, `current_drawdown_high` (computed by freqtrade from `starting_balance + profit_abs`) |
| other | `trading_volume`, `starting_balance` in daily rows |

Percentages and ratios stay fully meaningful without these; the derived fields
below replace the lost detail.

Two exceptions are deliberate: `stop_loss_abs` / `initial_stop_loss_abs` are
market *price levels*, not money amounts.

### Personal and machine-specific values — reason: they can identify a person or machine

- `bot_name` (often contains a person's or account's name)
- `db_url`, `user_data_dir`, `strategy_path`, `exportfilename`, `logfile`,
  `log_configfile` (filesystem paths contain usernames/machine names)
- `open_order` (raw string that embeds an exchange order id)

### Deliberately kept (cannot reveal the balance)

- `stop_loss_abs` / `initial_stop_loss_abs` — market price levels
- `trade_id` / `id` — local counters
- config `stake_amount: "unlimited"` — sizing behavior, not a size
- `fee_open` / `fee_close` — fee rates
- timestamps, prices, dates — market data

## Derived relative fields

Computed from the raw API data before redaction, so the report stays useful
without absolute values. All are scale-invariant ratios normalized by the
per-day account balance that freqtrade's `/daily` endpoint reports (fetched with
a timescale covering the whole bot history).

| field | appears in | formula | purpose |
|---|---|---|---|
| `stake_amount_to_account_balance_ratio` | `open_trades[]`, `closed_trades.trades[]` | `stake_amount / account balance at the trade's open date` | position sizing relative to the account at entry time |
| `profit_to_account_balance_ratio` | `closed_trades.trades[]`, `open_trades[]` | `close_profit_abs / balance at close date` (closed) or `profit_abs / current balance` (open) | per-trade impact on the account |
| `funding_fees_to_stake_amount_ratio` | `open_trades[]`, `closed_trades.trades[]` | `funding_fees / stake_amount` | accumulated funding cost drag of a position |
| `funding_fee_to_order_cost_ratio` | `trades[].orders[]` | `funding_fee / order cost (notional at fill)` | effective funding rate paid on that single fill |
| `order_amount_share_of_trade` | `trades[].orders[]` | `order amount / total amount across all orders of the trade` | entry/exit (DCA / safety order) distribution of a trade |
| `total_stake_to_account_balance_ratio` | `trade_counts` | `total_stake / current balance` | share of the account currently deployed in open positions |
| `trading_volume_to_account_balance_ratio` | `profit_summary` | `trading_volume / current balance` | turnover intensity over the bot's lifetime |

## Why the balance cannot be derived

Every kept number is a market price, a ratio between two internal quantities, a
count, or a timestamp — the report contains **no absolute currency value** that
could serve as a scale anchor. A ratio would only become sensitive if combined
with such an anchor (then `anchor / its ratio` recovers the balance), which is
exactly what the redaction removes.

## Auditing

The generator is audited by inventorying every numeric and string key of a
generated report and classifying each as market price, ratio, count, timestamp,
or money. This process is what found the per-order `funding_fee` variant and the
`current_drawdown_high` balance high-water mark. Any new freqtrade API field
holding currency amounts must be added to `MONEY_EXACT_KEYS` /
`MONEY_KEY_SUFFIXES` in `tools/bot_report.py`.
