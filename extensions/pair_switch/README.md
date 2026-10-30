# X8 pair switching

An opt-in X8 subclass that closes a selected trade and opens a different pair
as a **new trade**. The original trade, orders and realized PnL remain intact.
Neither Freqtrade nor the default X8 strategy is patched.

The operator selects the source trade and replacement pair. This is not an
automatic coin-selection strategy or a way to hide a losing trade.

## Execution contract

The local CLI records an intention in a separate SQLite journal. The strategy
uses Freqtrade's ordinary exit, entry, sizing and fill callbacks to execute it:

```text
requested -> closing -> ready -> admitted -> complete
                                   |
                                   +-> review
```

- Before closing, require an open, filled source without unresolved regular
  orders and an unoccupied target with fresh analyzed data in the whitelist.
- Close the entire source. A submitted order or partial fill is not closure.
- Use the same direction and leverage for the new trade. Refuse a target whose
  leverage limit is lower.
- Limit replacement margin to the requested amount, the source margin plus its
  final net PnL, and Freqtrade's proposed/available stake. Recheck the effective
  amount at final admission, after wallet minimum-order adjustments.
- Consume source-exit and target-entry authorization once using transactional
  revision checks. A stale signal or repeated callback cannot reauthorize it.
- Reserve both pairs while the request is active. Other pairs retain their
  native behavior. Freeze position adjustments for the reserved trades.
- Do not replace the target's entry order or add to its position later. Native
  reductions remain available after the switch settles.
- Reconcile open **and closed** target trades after a restart. Missing local
  evidence after admission is not proof that the exchange rejected the order.
  Keep the request in `review`; do not automatically retry it.

New signals may wait for the next 5-minute analysis cycle. Freqtrade's ordinary
pair locks, slots, wallet and minimum-order checks still apply. Closing the old
trade and entering the new one are not atomic: the result can be a closed source
with no replacement position.

Only one request is active per journal, and one request is allowed per source
Trade ID. The same token and payload can be resubmitted idempotently. A process
lease prevents two extension bots from executing the same journal.

## Linked PnL

The new trade stores the source ID, accumulated realized PnL and a profit buffer
under the `pair_switch_v1` custom-data key. Source PnL comes from
`close_profit_abs`; current target PnL comes from
`calculate_profit(rate).total_profit`, including FT's fees, funding and prior
partial exits. Repeated switches carry the previous accumulated PnL forward.

The recovery exit is **supplemental**:

```text
target total net PnL + accumulated source net PnL >= profit_buffer
```

It never vetoes a native exit. X8 may exit before this threshold, including at a
loss. Estimated exit PnL may differ from the final fill. `complete` means the
switch settled, not that the loss was recovered.

Old entry prices, stop prices, mode tags and grinding state are not copied into
the new position. The unique `ps_` entry tag takes X8's normal-mode fallback for
trades not opened by a recognized X8 signal. Native exit and confirmation rules
remain in effect, including any existing native hold/stop vetoes.

## Setup

Validated runtime: **Freqtrade 2026.9, X8 v18.0.130, Python 3.12**.
Startup refuses other FT/X8 versions pending compatibility validation.
Requires a POSIX host with local SQLite storage, or a Linux container with the
same journal mounted for the CLI and bot. Do not use a network filesystem.

Use a separate dry-run bot and trade DB first. Add these values to its existing
complete configuration; this fragment is not a standalone exchange config:

```json
{
  "strategy": "NostalgiaForInfinityX8PairSwitch",
  "dry_run": true,
  "force_entry_enable": false,
  "timeframe": "5m",
  "use_exit_signal": true,
  "exit_profit_only": false,
  "ignore_roi_if_entry_signal": true,
  "pair_switch": {
    "database": "/absolute/private/path/pair-switch.sqlite",
    "allow_live": false
  }
}
```

The extension must run in `dry_run` or `live`, not backtest/hyperopt. Live startup
requires explicit `allow_live: true`. Exchange-connected dry-run and live
execution have not been validated by the offline tests below.

From the repository root, in the Freqtrade virtual environment:

```bash
export PYTHONPATH="$PWD"
freqtrade trade --config /absolute/path/dry-run-config.json \
  --strategy-path extensions/strategies \
  --strategy NostalgiaForInfinityX8PairSwitch
```

The target must already be whitelisted, active, quoted in the configured stake
currency and have a nonzero-volume analyzed 5m candle no older than 10 minutes.
Use exchange-native symbols, e.g. `ALGO/USDT` for spot or `ALGO/USDT:USDT` for
USDT-settled futures.

## Submit and inspect

The running extension initializes the journal. Prepare a JSON request with:

| Field | Meaning |
| --- | --- |
| `token` | Unique 32-character lowercase hex token; reuse it on submission retries |
| `source_id` | Open trade ID in this bot's trade database |
| `target` | Replacement exchange symbol |
| `stake` | Maximum replacement margin in stake currency, not leveraged notional |
| `profit_buffer` | Additional combined net-profit target; defaults to zero |
| `expires_at` | Future ISO-8601 timestamp with timezone |

For example, generate a request for trade 12 with a 100 USDT cap, then inspect
the output and save it as `request.json` before submitting:

```bash
python -c 'import json, uuid; from datetime import datetime, timedelta, timezone; print(json.dumps({
  "token": uuid.uuid4().hex,
  "source_id": 12,
  "target": "ALGO/USDT",
  "stake": 100,
  "profit_buffer": 0,
  "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
}, indent=2))'

python -m extensions.pair_switch --database /absolute/private/path/pair-switch.sqlite \
  submit request.json
python -m extensions.pair_switch --database /absolute/private/path/pair-switch.sqlite status
```

`cancel TOKEN` is allowed before target entry is admitted. It cancels the future
entry, not an already-submitted source exit. An expired/rejected request will not
buy the target. An admitted request never becomes eligible for automatic retry,
even after expiry or restart.

If source exit was admitted but has no confirmed fill, wait for reconciliation;
the extension does not resubmit its exit. Native risk exits remain available.
If target entry is in `review`, inspect exchange orders/balances and FT records.
Do not delete the journal, edit states or change tokens to bypass this stop.
There is deliberately no blind rearm command.

Use one bot and journal together. Its binding includes the trade DB URL,
exchange and dry-run mode. Do not replace/reset that trade DB under an active
journal, share the trading account with another order writer, or enable
force-entry automation. Callback/journal errors disable new admissions until
restart; they do not add a veto to native exits.

## Offline validation

With the pinned Freqtrade environment active:

```bash
python -m unittest discover -s tests/unit -p 'test_pair_switch*.py' -v
ruff check --no-fix extensions tests/unit/test_pair_switch*.py
```

The suite uses real FT Trade/Order models, SQLite, wallet accounting, entry/exit
execution and fill reconciliation, with simulated exchange responses and fixed
time. It also exercises the actual CLI and `StrategyResolver`.

It is not a market-data profitability backtest or proof of live exchange
reconciliation. The normal NFI indicator pipeline and exchange-specific execution
policies still require deployment validation. No default signal or trading
configuration is changed by installing these files.
