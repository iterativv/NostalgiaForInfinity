# Demand-driven first-grind remainder exits

## Default and behavior

Base: `bbddbd94f97f3c14336387d2958183870891b951` (X8 v18.0.183). Final implementation: `9d14ddb8ad3b1ffa6c7b46361100821cb4b3b879`.

`legacy_grind_demand_exit_enable` defaults **True**. The rule is limited to one pure long120 owner with its initial fill and first completed gm0 profit-taking order. Another pair must actually be rejected by the dedicated grind-slot limit. On the next 5m candle, the owner must have no open orders or active original grind queues, a remainder at most the existing `1.55 * correct_min_stake(...)` boundary, and positive native and funding-corrected whole-trade marks. The remainder itself need not be profitable.

Existing adjustment actions and full exits are checked first. The one-use snapshot requires unchanged price/ledger, nondecreasing time within the due candle, and unchanged original retry/age/force timing predicates. This handles the live bot's exit-before-adjust ordering and separate clock reads. Closing intent persists through restart; it blocks new adds but retains reductions and exit management. Only actual engine closure releases the slot. No replacement pair or immediate re-entry is forced.

Disable new admissions through ordinary configuration (top-level overrides are also supported):

```json
{"nfi_parameters": {"legacy_grind_demand_exit_enable": false}}
```

Disabling admissions does not abandon an already-persisted closing intent.

## Current-base matched results

Native is unmodified upstream above; ON is the proposed default-enabled policy. Official Freqtrade 2026.8 image `freqtradeorg/freqtrade@sha256:4d23160b501d2b34579e76f57ad75edfa274967cd0dd824ff1c1b86d8c166ab4`; identical ordered 19-pair Binance isolated-futures universe, 5m, 3x leverage, six slots, PA/grinding enabled, 0.05% fee per side, funding included by the engine, unlimited stake and 99% tradable balance. Each year starts with its own 100,000-USDT wallet. Period ends are exclusive.

### Pure long120 trades within the shared portfolio

| Period | Native PnL USDT | ON PnL USDT | Difference | Native W/L | ON W/L |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20240101-20250101 | 11,232.12 | 11,232.12 | 0.00 | 3/1 | 3/1 |
| 20250101-20260101 | -11,497.49 | 7,857.07 | +19,354.56 | 1/2 | 4/1 |

### Whole portfolio

| Period | Native T/W/L | ON T/W/L | Native net PnL USDT | ON net PnL USDT | Difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024 | 141/139/2 | 141/139/2 | 394,848.99 | 394,848.99 | 0.00 |
| 2025 | 138/136/2 | 140/139/1 | 339,270.68 | 372,882.25 | +33,611.57 |

The 2025 wallet-return difference is +33.611571 percentage points. Do not pool independent annual wallets or treat the tag cohort as isolated alpha.

| Risk/cost | 2024 Native / ON | 2025 Native / ON |
| --- | ---: | ---: |
| Marked-equity maximum DD % | 27.108664 / 27.108664 | 20.854053 / 20.854053 |
| Maximum dollar equity DD USDT | 49,635.93 / 49,635.93 | 29,012.13 / 29,012.13 |
| All-six-slot lifecycle loss minutes | 375 / 375 | 65 / 65 |
| Losing-trade PnL subtotal USDT | -8,405.51 / -8,405.51 | -17,242.83 / -1,058.63 |
| Period-end force exits | 0 / 0 | 0 / 1 |

The loss subtotal is already included in net PnL. Dollar DD is the largest dollar decline from any preceding peak, not necessarily the percentage-DD peak: the 2024 amount at its percentage-DD peak is 37,716.60 USDT. These are 5m marked-equity metrics, not closed-trade-only DD or intrabar extremes. The 2025 annual maximum occurs on February 3, before the first November policy action; equal annual maxima do not establish unchanged later risk. Worst open-position lifecycle PnL worsened from -25,541.81 to -27,388.46 USDT. The final ON2025 trace mark precedes terminal settlement by 0.04863567 USDT.

2024 has no policy action and exactly equal complete trades/orders and equity bytes. In 2025, one Native winner is omitted (ALGO short562, +298.72 USDT); three new winners and no new losers appear. No Native winner is shortened; one Native loser is closed earlier. The new ALGO long120 is the additional period-end force exit (+990.34 USDT). Shared-wallet sizing also changes other retained trades.

## Actual actions and attribution

2025 contains three actual rejected demands, two intents and two verified engine closes; no closing owner remains in the final open registry.

| Owner | Demand, UTC | Actual close, UTC | Filled quantity @ price | Next actual 120 entry |
| --- | --- | --- | --- | --- |
| CRV | INJ, Nov 5 01:20 | Nov 5 01:25 | 64.9 @ 0.405 | ADA, Nov 5 01:25 |
| ADA | GALA, Nov 14 23:10 | Nov 14 23:15 | 53 @ 0.4973 | ALGO, Dec 18 17:10 |

The intervening ETH demand for ADA was consumed without an intent because the remainder exceeded the unchanged minimum boundary. Requested and subsequent entry pairs differ in both successful cases. Backtest same-candle execution is not zero live latency.

CRV's matching Native trade closes at -16,184.21 USDT versus +1,459.59 with ON. The Native loss includes -8,206.18 realized before final closure and -7,978.03 in final residual settlement; it is not all attributable to the final abandon label. ON retains the same initial gm0 realization (+1,459.423552) and closes the remainder for +0.1665265, instead of following Native's later re-entry/reduction/recovery path. The companion JSON preserves the realized-event breakdown.

## Verification and reproduction

The core implementation passed a plain-observer/composed-observer Native2025 equality gate and a fresh OFF2025 complete trades/orders and byte-equity gate. After the final live timing-boundary correction, both ON years were re-executed: complete trades/orders and equity bytes exactly match the core ON runs. Fresh OFF accounts cannot create the snapshot used by that correction; OFF parity is explicitly the core-source run, not an invented final-source rerun.

Final repository unit/tools: **2,931 passed**, zero failures/errors/skips, 14 inherited warnings. The shipped focused suite has **74 cases**; one additional external timing reproduction also passes. Original Native produces two expected failed activation assertions and four passing preservation controls. Native is not expected to implement this new policy.

Runtime tests use real Trade/Order accounting, actual bot `should_exit`, DataProvider and Wallets, and actual backtest order/fill/closure methods. Exchange boundaries and the bot's final submission are mocked. Tests cover original action priority, exact minimum, next/same/expired candle, changed quote/ledger, retry-time boundary before/at/after, partial/canceled orders, restart, base fees and funding. They do not establish live exchange fill quality.

Run from the PR checkout, without market data or credentials:

```bash
image=ghcr.io/iterativv/ci-strategy-backtesting@sha256:c356a7900503e964e0cbe7d92a499171c4090998e9bdf0efa76053b27d249107
docker pull "$image"
docker run --rm --network none \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo \
  -v "$PWD:/repo:ro" -w /repo --entrypoint python "$image" \
  -m pytest -o addopts= -o log_cli=false -p no:cacheprovider \
  tests/unit/test_NFIX8_demand_remainder*.py -q
```

`demand-remainder-config.json` is the exact common economic config. The companion `demand-remainder-evidence.json` includes the ordered universe, all 133 relative data paths/hashes, source and result hashes, exact metrics, changes and actual close records. Backtests used `--cache none --export trades`; source/config/data/harness were locked before execution and a serial lease prevented overlapping backtests. Original raw data and observer traces remain in the local evidence archive, not in this PR. Reproducing marked-equity metrics requires those traces or an equivalent reconciled observer; the self-contained tests above are not a market-performance replay.

## Limits

The two active closes belong to the same exposed 2025 branch studied previously. Current-source confirmation is not an independent holdout or a general profit guarantee. 2024 preservation does not add active effectiveness evidence. Informative warmup uses the available history rather than fabricated 800-bar prefixes. Backtest exchange filters, candle fills and funding conventions do not establish live depth, latency, partial-fill outcome or future market behavior. Host-wide type checking remains unqualified because of missing runtime imports and inherited strategy diagnostics; pinned-runtime tests and repository checks are the recorded gates.
