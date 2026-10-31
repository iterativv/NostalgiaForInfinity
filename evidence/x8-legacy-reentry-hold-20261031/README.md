# Legacy grind reentry hold: matched evidence

Add a default-OFF option to keep de-risked capital out of an unresolved legacy grind campaign. Native is unmodified main `bbddbd94f97f3c14336387d2958183870891b951`; ON changes only this admission policy under identical settings. The trade-off is lower 2024 drawdown and a smaller 2025 CRV loss, but slower 2024 recovery and missed winners.

**Pure long120 cohort within the shared portfolio**

| Year | Native PnL (USDT) | ON PnL (USDT) | Difference | Native W/L | ON W/L |
|---|---:|---:|---:|---:|---:|
| 2024 | 11,232.12 | 7,548.38 | -3,683.74 | 3/1 | 2/1 |
| 2025 | -11,497.49 | -7,117.63 | +4,379.86 | 1/2 | 1/2 |

**Full portfolio**

| Year | Native PnL (USDT) | ON PnL (USDT) | Difference | Native trades/W/L | ON trades/W/L |
|---|---:|---:|---:|---:|---:|
| 2024 | 394,848.99 | 380,848.63 | -14,000.36 | 141/139/2 | 139/137/2 |
| 2025 | 339,270.68 | 343,650.54 | +4,379.86 | 138/136/2 | 138/136/2 |

**Risk and retained-trade costs**

| Metric | 2024 Native | 2024 ON | 2025 Native | 2025 ON |
|---|---:|---:|---:|---:|
| Marked equity DD (%) | 27.1087 | 20.5105 | 20.8541 | 20.8541 |
| Maximum dollar DD (USDT) | 49,635.93 | 48,224.49 | 29,012.13 | 29,012.13 |
| Losing-trade PnL subtotal (USDT) | -8,405.51 | -8,357.96 | -17,242.83 | -12,862.98 |
| All-six-slots total-loss minutes | 375 | 350 | 65 | 65 |
| All-six-slots unrealized-loss minutes | 380 | 380 | 65 | 65 |
| Force exits | 0 | 0 | 0 | 0 |

2024 omits two Native winners (GALA144 +905.10, SOL120 +3,440.31 USDT); the earlier GALA120 closes 8 days 15 hours 50 minutes later. Neither year adds a new winner/loser or truncates a retained trade. In 2025 only CRV changes: its loss falls from -16,184.21 to -11,804.35 USDT. The annual 2025 DD peak precedes that December change.

## Safety

`legacy_grind_derisk_reentry_hold_enable = False`. Enable through ordinary `nfi_parameters` or the top-level setting; top-level takes precedence. After the latest filled `dd1`-`dd6`, pause further legacy long-grind buys while earlier native-active queue IDs remain. This includes `gd1` fallback and `gd5` rescue buys. Native queue barriers release the hold; this is not a new physical-lot accounting model.

Existing sells, partial-exit completion and reductions remain reachable; withholding an earlier buy can make a later exit execute sooner. Short/V4 policy, thresholds, sizing and signal conditions are unchanged.

## Backtest scope

Official Freqtrade 2026.8, same ordered 19 pairs, 5m, isolated futures 3x, six total slots and one dedicated grind slot, fee 0.0005; each year starts a separate 100,000-USDT wallet. Reused Native accounts were verified against exact source, config, data, runtime and capture provenance. Four new annual accounts cover default OFF and ON for both years. OFF matches complete Native trades/orders and byte-equity in each year.

Results include fees/funding. Dollar DD and percentage DD can peak at different times; loss subtotal is already included in net PnL. Exposed periods, shared-wallet effects and 5m equity marks are not an untouched holdout or intrabar/live guarantee. These results do not establish default activation. Files below retain configuration and verification inputs.

## Checks

59 real Trade/Order callback/configuration cases pass; Native has 30 expected feature failures and 29 controls. Full unit/tools: 2,916 passed, 14 inherited warnings. Syntax, scope, Ruff/format and pre-commit pass. Removing the option/allowlist/policy block and seven admission guards restores the complete Native AST.

The bundled `legacy_reentry_crv.json` is an earlier corrected-v18.0.157 ledger reused as a callback regression input. Its quantities are not the current-main backtest fills reported below. Entry signals are controlled in those unit fixtures; the official matched accounts use the actual strategy signals.

## Reproduction inputs

- Native commit: `bbddbd94f97f3c14336387d2958183870891b951`; strategy SHA-256 `80f824e879493babf42cb861d751aa077bcc475ccacf08ae62ebf7abd26eeb8f`.
- Implementation commit: `639b05c3030f0bbfd5903ac7febbb8334b3418c1`; strategy SHA-256 `c60938008e984119545b49d734c7b4792fdd65332cde3865fddb041d7aea4ad0`.
- Official image: `freqtradeorg/freqtrade@sha256:4d23160b501d2b34579e76f57ad75edfa274967cd0dd824ff1c1b86d8c166ab4`.
- `base.json` is the exact measured Native/default-OFF configuration. ON changes only `nfi_parameters.legacy_grind_derisk_reentry_hold_enable` to `true`. Advanced mode in the frozen benchmark is retained for parity; the new option does not require it.
- Full-year timeranges: `20240101-20250101`, `20250101-20260101`; `--cache none --export trades`.
- `data-sha256.csv` lists all 133 input files relative to the Freqtrade data root. `run-hashes.csv` binds all six original export archives and marked-equity streams.
- `cohorts.csv` contains all 59 year/exact-tag cohort comparisons. They partition each annual account; the pure120 cohort is not a separately funded strategy.
- Marked equity includes open positions and prior realized changes, with fees/funding accounted once. It is not the standard closed-trade DD. Raw full ledgers, streams and analysis are retained in the study; hashes identify them, not a promise that a trade-export-only replay reconstructs every observed fill.

## Actual changes and limits

In 2025 the first 15 CRV orders are identical. Native buys 113,258.4 CRV at 0.399 on December 28 12:00 UTC; ON does not. Both close at 0.361 on December 31 16:50 UTC. Actual final quantities are 198,331.0 versus 85,072.6. Price-loss avoidance 4,303.8192 + fee difference 43.038192 + funding difference 32.9997208 reconcile the +4,379.8571128-USDT result. Earlier realized PnL is -8,206.17626661 in both; final residual settlement is -7,978.02947090 versus -3,598.17235810. The entire trade loss must not be assigned to its final abandon label. Other 2025 trades are identical.

In 2024 GALA120 first differs at the March 21 01:00 UTC gd1 buy, after 21 identical orders. It closes April 21 21:10 rather than April 13 05:20 UTC. Its PnL changes +2,969.64645385 to +2,910.38228168. The two omitted winners total 4,345.41187403 USDT; changed matched records contribute -9,654.94876397. These reconcile the portfolio delta but are not independently causal returns. 116 matched trade records change, including shared-wallet sizing/accounting effects. There are no new trades or shortened retained trades.

2024 percentage DD falls 6.59813314 percentage points, while maximum dollar DD falls 1,411.44513527 USDT. The dollar drawdown at the percentage-DD trough is separately 37,716.59569290 versus 28,340.17400949 USDT. The longest all-slot-loss episode remains 95 minutes; 2025 remains 20 minutes. No force exits or liquidations occur in either matched period. Historical 2026 was not rerun or relabeled as current evidence.

This is a default-OFF risk/recovery choice, not a universal profit improvement. Spot has callback coverage, not a spot portfolio comparison. Annual wallets are independent. Unknown fill quantities outside the pure120 capture are not inferred from requested amounts. Host-wide typecheck is not claimed clean because runtime dependencies/inherited diagnostics are unavailable there. Differences are computed before rounding.
