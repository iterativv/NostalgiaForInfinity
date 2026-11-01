# X8 V4 grind funding fallthrough

## Reproduced problem

Tested upstream: `d0b321a2ffb07300c8fe3c20ecdc824d8d2c781a` (X8 v18.0.183).

At each ordinary V4 grind level 1-5, a valid add signal calculates the original stake and minimum-stake uplift. The original `buy_amount > max_stake` branch returns from the whole adjustment callback. This prevents existing later profit-exit, grind de-risk or affordable-entry checks from running, even though the add itself cannot execute.

The correction changes only those ten funding branches: execute the existing entry notification/log/return block when `buy_amount <= max_stake`; otherwise continue in the existing order. Funded adds retain priority, including exact equality. Amounts are not downsized, exits are not forced, and no thresholds or feature defaults change.

## Current-source before and after

The same committed test cases are run with the unmodified upstream strategy mounted over the candidate module, and then with the modified strategy. They use real SQLite Trade/Order models and accounting. Only the entry-signal seam and external exchange/RPC boundaries are controlled.

| Suite | Native cases | Native pass / fail | Modified pass / fail | Runtime errors / skips |
| --- | ---: | ---: | ---: | ---: |
| Public callback and ledger | 186 | 139 / 47 | 186 / 0 | 0 / 0 |
| FreqtradeBot, Wallets and reduction-order creation | 150 | 105 / 45 | 150 / 0 | 0 / 0 |
| Total | 336 | 244 / 92 | 336 / 0 | 0 / 0 |

The long/spot increment separately passed 223 callback and engine cases before the short mirror was added.

### Concrete long-futures example

- Filled ledger: 10 units bought at 100; 4 sold at 100; one grind unit bought at 100. Leverage 3, zero fixture fees, remaining 7 units.
- Current rate 86; grind de-risk threshold -10%; the narrow add signal is true. The unchanged requested add is 50 USDT of margin.
- With max_stake 0 or 49.95, Native returns None. The modified callback returns approximately -33.333333 USDT and `grind_1_derisk 3`.
- With max_stake exactly 50, both retain `(50, "grind_1_entry")`.
- With the add signal false and the same unfunded ledger, Native already returns the reduction. Funding is the differentiating cause, not a new exit policy.

The engine cases verify that max_stake is the minimum of actual Wallets availability and the exchange stake limit. When the add is unaffordable, the real bot/order path creates the existing one-unit exit-side order, reduce-only for futures, with its original grind de-risk tag. The mocked exchange returns an **open, unfilled** order: this proves routing and order construction, not a live fill or realized profit.

Other cases cover spot and both futures directions, all five levels, minimum uplift, later affordable levels, no later eligible action, open orders, post-de-risk rebuy routing, forced liquidation-proximity de-risk precedence, the newly enabled pre-de-risk entry route, and an actual profitable grind exit. Profit exits use the real exit helper and preserve the original reverse-scan order tags.

## Reproduce with the public CI image

Both source variants were also tested with the publicly pullable amd64 image used by repository CI, pinned by digest. It runs Freqtrade 2026.9, Python 3.14.7 and CCXT 4.5.84. Results were identical to the table above: Native 92 failures / 244 passes; modified 336 passes; no errors or skips.

Run from this PR checkout:

```bash
image=ghcr.io/iterativv/ci-strategy-backtesting@sha256:c356a7900503e964e0cbe7d92a499171c4090998e9bdf0efa76053b27d249107
docker pull "$image"
docker run --rm --network none \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo \
  -v "$PWD:/repo:ro" -w /repo --entrypoint python "$image" \
  -m pytest -o addopts= -o log_cli=false -p no:cacheprovider \
  tests/unit/test_NFIX8_v4_grind_funding.py \
  tests/unit/test_NFIX8_v4_grind_funding_engine.py -q
```

For the negative control, export only the original strategy into a temporary file, keeping this PR's tests:

```bash
native_source=$(mktemp)
git show d0b321a2ffb07300c8fe3c20ecdc824d8d2c781a:NostalgiaForInfinityX8.py > "$native_source"
docker run --rm --network none \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo \
  -v "$PWD:/repo:ro" \
  -v "$native_source:/repo/NostalgiaForInfinityX8.py:ro" \
  -w /repo --entrypoint python "$image" \
  -m pytest -o addopts= -o log_cli=false -p no:cacheprovider \
  tests/unit/test_NFIX8_v4_grind_funding.py \
  tests/unit/test_NFIX8_v4_grind_funding_engine.py -q
# Expected: exit 1, 92 failed and 244 passed.
rm "$native_source"
```

The earlier local test runtime was Freqtrade 2026.8, Python 3.14.7 and CCXT 4.5.76, image ID `sha256:e051757d9663ce1c2789bf0ac273ab0f332cc1a2803d1ebc5b6e22842be36786`. That local identity is not a public registry reference. Both recorded environments produced the same focused results.

## Preservation checks and scope

Reversing only the five long and five short funding-guard transformations restores the entire upstream AST exactly. This checks that eligibility predicates, ordering, sizing, logging contents, return values, rescue predicates, earlier de-risk, managed-partial handling and unrelated callbacks were not rewritten.

Legacy 120/620 behavior and the separate V4 buyback entry budget are outside this patch. This extends the funding-fallthrough principle already used by the legacy correction in PR #1470; it does not assert that all V4/legacy mechanisms are identical.

The base also contains an unrelated stale test: `test_feature_is_opt_in` expects the pre-de-risk flag to be False even though upstream commit `a32fd54a` intentionally enabled it. The same failure was reproduced on unmodified upstream; it is separate from the 92 V4 regression failures. A separate prerequisite commit renames this test to `test_feature_is_enabled_by_default` and asserts the existing True default. The distance assertion and production default remain unchanged. No test was deleted, skipped or marked xfail.

After that alignment, the full `tests/unit tests/tools` suite passed all **2,857 cases** in the pinned public CI image, with zero failures, errors or skips and 14 existing warnings (legacy imports, pandas copy arguments and an unrelated infinite-value indicator fixture). The aligned default-test file also passed all 582 cases against the otherwise unmodified Native strategy.

Host-wide type checking is not claimed clean: runtime imports and inherited large-strategy diagnostics are unresolved on the host. Pinned-runtime tests, syntax, repository lint/format and the focused scope checks are the relevant recorded validations.

## Historical account comparison: context only

This older comparison ran on v18.0.158, Native `0d2ad91498ef44cd405427e14cd0d821a2699a61`, candidate `f299d9e4156087ac625c608523d224568f5e5c93`. It is **not a new backtest on v18.0.183** and establishes no current-source profitability.

Official Freqtrade 2026.8 image `freqtradeorg/freqtrade@sha256:4d23160b501d2b34579e76f57ad75edfa274967cd0dd824ff1c1b86d8c166ab4`; matched 19-pair Binance isolated futures, 5m, six slots, 3x leverage, independent 100,000-USDT wallets, unlimited stake with 99% tradable balance, 0.05% fee per side, PA/grinding ON. Period ends are exclusive.

| Period | Native T/W/L | Modified T/W/L | Native net PnL USDT | Modified net PnL USDT | Difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024 | 139/137/2 | 139/137/2 | 385847.79232610 | 385847.79232610 | 0 |
| 2025 | 142/140/2 | 142/140/2 | 342747.41409544 | 342747.41409544 | 0 |
| 2026-01-01 to 2026-08-06 | 31/30/1 | 31/30/1 | 34490.43964978 | 34490.43964978 | 0 |

| Period | Native / modified equity DD % | Native / modified maximum dollar DD | All-slot loss minutes, both | Force exits, both |
| --- | ---: | ---: | ---: | ---: |
| 2024 | 27.10837152 / 27.10837152 | 48726.35882891 / 48726.35882891 | 375 | 0 |
| 2025 | 20.85405264 / 20.85405264 | 29012.12648785 / 29012.12648785 | 65 | 0 |
| 2026 through August 6 exclusive | 5.86038871 / 5.86038871 | 7556.89261992 / 7556.89261992 | 0 | 1 |

Trades/orders and complete equity traces matched in every period. Changed, new, omitted, truncated and winner-to-loss positions were zero, as were liquidations. Dollar DD is the largest dollar decline from any preceding peak; it need not occur at the maximum-percentage-DD peak. The machine-readable companion records both quantities and losing-trade PnL subtotals.

These exposed samples showed **no changed execution and no economic improvement**. They therefore did not pass the old economic-improvement publication gate. They also do not establish that the funding branch was never encountered. The present PR is justified by the reproduced current callback/order-routing defect, not by hypothetical saved losses or a claim of higher returns.

Old raw account artifacts remain in the local research archive; the public companion is a derived, hash-attributed summary, not the raw market dataset. Reproducing the current correctness cases above needs no market data or exchange credentials.
