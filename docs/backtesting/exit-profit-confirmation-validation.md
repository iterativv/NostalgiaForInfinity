# X8 profit-only confirmation after partial exits

## Problem and correction

Native is upstream `57d84e44db42c2da93e6b99d4334874724b07e7c`. Only the realized-profit branch of `confirm_trade_exit` changes in production (+1/-4).

With `exit_profit_only=True`, the old formula applied a long-direction price change to margin stake. After partial exits, it could approve a cumulatively losing exit or block a profitable one. The replacement uses `Trade.calculate_profit(rate).total_profit`, which includes the actual remaining quantity, direction, fees and funding, divided by the **same current stake amount** as before. It deliberately does not use `total_profit_ratio`, which has a different denominator.

The disabled default, zero-realized-profit branch, inclusive profit-offset boundary, hold checks and force/stop rules are preserved.

## Fresh matched results

The same committed test cases ran against the Native strategy and the modified strategy, with identical ledgers and runtime. These results are on the base above, not the earlier preparation base.

| Cases | Count | Native pass / fail | Modified pass / fail |
| --- | ---: | ---: | ---: |
| Direct callback, offset, funding and guard controls | 25 | 23 / 2 | 25 / 0 |
| Bot, wallet, confirmation and order creation | 36 | 28 / 8 | 36 / 0 |
| Total | 61 | 51 / 10 | 61 / 0 |

There were no runtime errors or skipped cases. Native's exit code 1 is the expected negative control; the modified cases pass. The first fix/direct-test increment passed 217 focused and adjacent cases. The final modified `tests/unit tests/tools` suite passed **3,100 cases**, with 14 existing warnings at unchanged legacy/X7/indicator locations.

### Hand-checkable examples

All four examples use 3x leverage, 10 units entered at 100, one unit partially closed, nine units remaining, zero fees/funding, and profit offset zero. Amounts below are projected cumulative USDT profit at the proposed exit rate, not live fills or portfolio returns.

| Direction | Partial close rate | Proposed remaining exit rate | Total profit | Native decision | Corrected decision |
| --- | ---: | ---: | ---: | --- | --- |
| Long | 110 | 98 | -8 | Allow | Reject |
| Long | 90 | 102 | +8 | Reject | Allow |
| Short | 90 | 102 | -8 | Allow | Reject |
| Short | 110 | 98 | +8 | Reject | Allow |

For the first row, +10 realized plus -18 on the remaining nine units equals -8. Native instead computes -6 from the 300-USDT remaining margin and adds +10, incorrectly obtaining +4. The independent cashflow oracle in the test checks the engine's cumulative profit before invoking the bot.

Other controls cover spot, the disabled option, no partial exit, 0.1% trading fees, both signs of remaining funding, the existing current-stake threshold basis and its exact equality, force exits, stop vetoes and a real hold configuration file. Stop controls use a zero profit threshold on a positive-profit ledger, so the profit filter cannot mask a missing stop veto; force controls retain a high threshold.

## Reproduce without market data or credentials

Run from a checkout of this PR. The public amd64 CI image is pinned to Freqtrade 2026.9 / Python 3.14.7:

```bash
image=ghcr.io/iterativv/ci-strategy-backtesting@sha256:c356a7900503e964e0cbe7d92a499171c4090998e9bdf0efa76053b27d249107
docker pull "$image"
docker run --rm --network none --cpus 2 --memory 3g --memory-swap 3g \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo \
  -v "$PWD:/repo:ro" -w /repo --entrypoint python "$image" \
  -m pytest -o addopts= -o log_cli=false -p no:cacheprovider \
  tests/unit/test_NFIX8_exit_profit_confirmation.py -q
# Expected: exit 0, 61 passed.
```

For Native, retain this PR's tests and overlay only the strategy from the pinned base:

```bash
native_dir=$(mktemp -d)
git worktree add --detach "$native_dir" 57d84e44db42c2da93e6b99d4334874724b07e7c
native_status=0
docker run --rm --network none --cpus 2 --memory 3g --memory-swap 3g \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo \
  -v "$PWD:/repo:ro" \
  -v "$native_dir/NostalgiaForInfinityX8.py:/repo/NostalgiaForInfinityX8.py:ro" \
  -w /repo --entrypoint python "$image" \
  -m pytest -o addopts= -o log_cli=false -p no:cacheprovider \
  tests/unit/test_NFIX8_exit_profit_confirmation.py -q || native_status=$?
git worktree remove "$native_dir"
test "$native_status" -eq 1
# Expected: Native pytest reports 10 failed and 51 passed.
```

For the full suite, use the first Docker command with `tests/unit tests/tools -q` in place of the single test file. The [machine-readable companion](exit-profit-confirmation-validation.json) records the source/test SHA-256 values, exact Native failure IDs and derived counts.

## Scope and evidence limits

The bot cases execute `FreqtradeBot.execute_trade_exit`, actual Wallets, real SQLite Trade/Order accounting, strategy confirmation and order persistence. Only exchange transport and RPC notifications are mocked. The returned exchange order is open and unfilled. Direct cases exercise the public callback on real ledgers. This proves decisions and order construction, not signal generation, exchange execution quality or portfolio gains.

No market-data backtest was run. The selected profit API was also inspected in the project's pinned official Freqtrade 2026.8 runtime; the tests reported here use the pinned CI runtime above. Repository pre-commit, Ruff, syntax and scope checks pass. Host-wide type checking is not claimed clean because runtime imports are unavailable. The companion is a derived summary; reproduction relies on the committed tests and immutable source/runtime identities, not inaccessible market datasets.
