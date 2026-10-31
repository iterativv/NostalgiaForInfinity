# X8 optional residual-alarm profit exit

This default-OFF option can take a long position's profit when Native starts a
new positive profit target during a recent, completed-hour residual up-alarm.
It is an alternative exit policy, not a correction to Native behavior.

```json
{
  "risk_residual_first_target_exit_enable": true
}
```

The key also works inside `nfi_parameters` without advanced mode.

## Exit contract

Native `custom_exit` runs once and every non-`None` Native decision keeps
priority. The option only considers long positions after Native returns no exit.
A positive generic or named long profit target must have been newly committed
at the current callback timestamp and belong to the current Trade. Stoploss,
doom and abandon targets are excluded.

"First target" means a fresh cache transition, not a separately tracked
first-ever opportunity in the Trade's lifetime. A rejected start cannot qualify
through a later peak update. If the old cache entry is removed, a later fresh
target transition can qualify.

The latest completed analyzed base row must carry an up-alarm whose availability
time is no later than the callback and less than one hour old. Missing, future or
expired readings do not arm a Trade for later use. Admission also requires
finite positive Native lifecycle cash PnL, including executed reductions, fees
and applicable funding. A positive residual-position return alone is not enough.

Only an issued exit intent is stored on the Trade. It survives database reloads
and retries while enabled, even if the alarm expires or profit changes. Native
still takes priority. Disabling resumes Native without consuming that marker;
re-enabling can resume the stored intent. An intent is not a guaranteed fill or
a guarantee that a delayed fill remains profitable.

## Detector and time alignment

The market return is the median of finite simple hourly returns across the fixed
whitelist. Each return requires adjacent positive finite closes. For each pair,
beta uses exactly the previous 720 subject and market returns, with sample
covariance divided by positive sample market variance.

The residual is the current subject return minus beta times the current market
return. Its scale is the sample standard deviation of the previous 720
residuals. The standardized reading is residual divided by scale, without
subtracting a residual mean. Missing or invalid normalizers remain unknown.

The positive cumulative detector adds the standardized reading minus 0.5,
floors at zero, and alarms strictly above 5.0. It resets after an alarm or unknown
reading. These constants are fixed, not configurable or retuned for this PR.

Only closed hourly inputs contribute. Availability is the hour's closing time,
merged against each base candle's close. Thus an hour ending at 01:00 can appear
on the 00:55 base candle only when that base candle closes at 01:00. Readings
expire strictly one hour after availability; prices and expired alarms are not
forward-filled.

## Operating constraints

This policy requires a **fixed whitelist and immutable committed hourly history**.
Adding/removing pairs, late backfilling a committed gap, or revising a retained
close raises an explicit error before the detector advances. It does not
silently reset its statistical history. A changing volume-based pairlist is not
compatible with this fixed-epoch contract.

The detector needs uninterrupted history: beta first becomes available at
zero-based row 721 and the standardized residual at row 1441. Native's startup
count remains 800. With shorter initial hourly buffers, Native continues while
the detector remains unknown until sufficient history accumulates.

State is process-local and survives rolling provider buffers, not process
restarts. A new strategy instance with a short history cannot reconstruct the
previous cumulative detector state. The Trade's already-issued exit intent is
persisted separately. No automatic restart continuity is claimed.

Offline modes retain a complete causal output surface for different pair
endpoints. Live/dry-run retains bounded raw/statistical history plus the required
rolling merge surface. All whitelist hourly frames are prepared before an
advancing update. Future rows cannot alter past readings.

## Validation scope

The candidate is based on upstream
`57d84e44db42c2da93e6b99d4334874724b07e7c`. The original fixed research source was
`953749b0c6817517fce0d90e40a823a1523bea8acb5df4afb68aa0c1b82c7d27`.
Native bodies and the embedded detector are checked independently against their
preserved source. Shared helpers are kept in Common Functions.

The earlier seven-period study used v18.0.159 / Freqtrade 2026.2 and rejected
adoption. It reported no new losses under its fixed matching rule, but lower
profit and long-slot efficiency in 2023 through 2026. Those historical results
are not current-source runs or evidence of general improvement.

Current confirmation uses the unchanged rules and exposed 2020, 2023 and 2024
periods, deliberately including known historical benefit and adverse outcomes.
Each account uses an independent 10,000 USDT wallet, fixed stake 100, ten configured
slots, 5m, and PA/de-risk/grinding enabled. The complete universes contain 9, 30
and 39 pairs respectively. The exact current-base 2023/2024 Native references
are reused only after full identity checks and are not described as fresh runs.

Public regression tests cover real Trade/Order accounting, spot and futures,
Native priority, retry persistence, cache-transition semantics, completed-hour
alignment, gaps, rolling buffers, revisions, warm-up and restart limitations.
Account results, not those software tests alone, determine the measured costs
and benefits. No default activation, untouched holdout or pooled annual return
is implied.

## Current-source measured comparison

Native is unmodified X8 at the pinned base. Enabled changes only the opt-in
exit policy. Native2020 and all enabled accounts are fresh; Native2023/2024
are the exact validated current-base references reused from the prior study.
All original inputs and every reference output were rechecked. Actual exported
opening and closing fee rates are 0.0005 in every account; funding and earlier
partial realizations remain included in whole-trade PnL.

### Long positions within the shared portfolio

| Year | Native trades/wins/losses | Enabled trades/wins/losses | Native PnL USDT | Enabled PnL USDT | Difference |
|---|---|---|---:|---:|---:|
| 2020 | 69/68/1 | 72/72/0 | 495.90 | 562.51 | 66.61 |
| 2023 | 151/145/6 | 151/145/6 | 800.61 | 785.00 | -15.61 |
| 2024 | 224/222/2 | 224/222/2 | 1682.57 | 1651.44 | -31.13 |

### Whole portfolio and costs

| Metric / year | Native | Enabled | Difference |
|---|---:|---:|---:|
| Net PnL USDT / 2020 | 500.94 | 567.55 | 66.61 |
| Trades / 2020 | 73 | 76 | 3 |
| Wins / 2020 | 72 | 76 | 4 |
| Losses / 2020 | 1 | 0 | -1 |
| Losing-trade PnL subtotal USDT / 2020 | -43.00 | 0.00 | 43.00 |
| Marked equity DD % / 2020 | 1.725575 | 1.725575 | 0.000000 |
| Maximum dollar DD USDT / 2020 | 174.0945 | 174.0945 | 0.0000 |
| All-slot lifecycle loss minutes / 2020 | 0 | 0 | 0 |
| Long occupied days / 2020 | 54.159722 | 48.583333 | -5.576389 |
| Long PnL per occupied day / 2020 | 9.156258 | 11.578346 | 2.422089 |
| Force exits / 2020 | 1 | 0 | -1 |
| Net PnL USDT / 2023 | 833.70 | 818.09 | -15.61 |
| Trades / 2023 | 181 | 181 | 0 |
| Wins / 2023 | 174 | 174 | 0 |
| Losses / 2023 | 7 | 7 | 0 |
| Losing-trade PnL subtotal USDT / 2023 | -238.79 | -238.79 | 0.00 |
| Marked equity DD % / 2023 | 2.081499 | 2.081499 | 0.000000 |
| Maximum dollar DD USDT / 2023 | 215.1144 | 215.1144 | 0.0000 |
| All-slot lifecycle loss minutes / 2023 | 5 | 5 | 0 |
| Long occupied days / 2023 | 169.083333 | 168.958333 | -0.125000 |
| Long PnL per occupied day / 2023 | 4.735031 | 4.646136 | -0.088895 |
| Force exits / 2023 | 1 | 1 | 0 |
| Net PnL USDT / 2024 | 1714.84 | 1683.70 | -31.13 |
| Trades / 2024 | 265 | 265 | 0 |
| Wins / 2024 | 262 | 262 | 0 |
| Losses / 2024 | 3 | 3 | 0 |
| Losing-trade PnL subtotal USDT / 2024 | -155.57 | -155.57 | 0.00 |
| Marked equity DD % / 2024 | 1.507979 | 1.511429 | 0.003450 |
| Maximum dollar DD USDT / 2024 | 159.4668 | 159.4668 | 0.0000 |
| All-slot lifecycle loss minutes / 2024 | 265 | 265 | 0 |
| Long occupied days / 2024 | 122.562500 | 122.479167 | -0.083333 |
| Long PnL per occupied day / 2024 | 13.728251 | 13.483396 | -0.244855 |
| Force exits / 2024 | 0 | 0 | 0 |

The losing-trade subtotal is already included in net PnL. DD uses 5m closing
marks, not intrabar extremes, and reconciles with closed trades plus each open
position's prior realized and funding-corrected remaining unrealized PnL.
Percentage-DD differences are percentage points. The maximum dollar DD did not
change; the 2024 percentage DD increased slightly because the equity peak
changed. The 2023 portfolio DD recovery was later: August 15 20:10 UTC versus
August 17 21:45 UTC. Per-tag cohorts are published in JSON and overlap.

### What generated the 2020 benefit

The result is concentrated in one XRP position and three later entries, not a
broad improvement across many independent trades. Both arms entered XRP at
2020-12-25 20:35 UTC. Native held until the calendar-window force exit and had
whole-trade PnL of -43.00023797 USDT; the enabled arm closed five minutes after
entry with +2.73626232 USDT. Three later XRP entries earned +0.48944018,
+19.46443020 and +0.92391169 USDT.

Native's observed cumulative partial realizations reached -71.55798569 USDT
before the final outcome. Its entire -43.00 USDT lifecycle result must not be
attributed to the final force-exit fill. The comparison is calendar-window
dependent and does not establish how the unclosed Native position would have
performed in 2021 or in live execution.

There were no omitted trades or matched winners becoming losses in the three
comparisons. In 2020 one eventual Native loser closed earlier and three new
winning entries occurred. In each of 2023 and 2024, four Native winners closed
earlier, with no new entries or changed win/loss counts. The inclusive
side-blind +/-24h new-loss rule counted zero in all three periods.

The concrete benefit is the 2020 profit and occupancy improvement. In 2023 and
2024, only three and two hours of long occupation were saved respectively,
while profit and profit per occupied day declined. These costs, the single-pair
concentration, fixed-whitelist requirement and restart limitations are reasons
to treat this as an optional policy for review, not general improvement or
default activation.

## Current controls and software reproduction

The full public unit/tools suite passed **3,181 tests**: 3,039 existing cases,
133 feature cases and nine replay-comparison cases. There were zero failures,
errors or skips, and 14 warnings from existing legacy/indicator tests. The
software runtime is the separately pinned Freqtrade 2026.9 CI image, not the
2026.8 account runtime. No private study module is required:

```bash
IMAGE=ghcr.io/iterativv/ci-strategy-backtesting@sha256:c356a7900503e964e0cbe7d92a499171c4090998e9bdf0efa76053b27d249107
docker run --rm --network none --cpus 2 --memory 3g --memory-swap 3g \
  --user "$(id -u):$(id -g)" \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo \
  -v "$PWD:/repo:ro" -w /repo --entrypoint python "$IMAGE" \
  -m pytest -c /repo/pytest.ini -o addopts= -o log_cli=false \
  -p no:cacheprovider tests/unit tests/tools -q
```

Native2020 plain versus observed matched all 73 trades and 261 executed orders.
The 2024 OFF account matched all 265 trades/714 orders, byte-equity, signals,
exchange inputs and effective parameters of the reused Native reference. The
new-source inverse AST restores Native exactly, and the detector matches its
frozen component. Shared input hashes and actual full Order records were
verified for every new account.

## Public account evidence and reproduction

`residual-profit-exit-validation.json` contains the account and signal-cohort
metrics, complete change classifications, source/runtime identities, original
configs, exchange snapshots and 582 annual data-file hashes.
`residual-profit-exit-ledgers.json` contains every comparison trade and both
minified and full actual Order records. It is compact machine-readable JSON;
requested amounts and actual filled quantities remain distinct.

The public `tools/residual_profit_exit/reproduce.py` checks all source/data
hashes, restores the recorded exchange inputs, runs the official engine and
compares every published trade outcome and executed order value. Output must
be fresh. The replay still performs the original exchange network reload.

Matching candle files are not bundled. Exact replay requires the files matching
the published hashes; newly downloaded/revised history may differ. This tool
verifies trades and orders, not the marked-equity trace.

Qualification: the final public command independently completed the full ON2020
account and matched all **76 trade outcomes and 233 executed orders**, with the
frozen inputs unchanged. `residual-profit-exit-reproduction.json` records the
runtime, code/evidence hashes and result. This separately qualifies the enabled
path for 2020; the other accounts were not rerun through this public wrapper.

From this PR's root, set `DATA_DIR` to the 2020 directory containing `futures/`
and its 99 matching files, and `OUTPUT_DIR` to a writable output parent:

```bash
: "${DATA_DIR:?Set DATA_DIR to the matching annual data directory}"
: "${OUTPUT_DIR:?Set OUTPUT_DIR to a writable output parent}"
mkdir -p "$OUTPUT_DIR"
IMAGE=freqtradeorg/freqtrade@sha256:4d23160b501d2b34579e76f57ad75edfa274967cd0dd824ff1c1b86d8c166ab4
flock /tmp/nfi-residual-profit-exit.lock \
  docker run --rm --pull never --cpus 4 --memory 30g --memory-swap 30g \
  --user "$(id -u):$(id -g)" \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 \
  -v "$PWD:/repo:ro" -v "$PWD:/strategy:ro" \
  -v "$DATA_DIR:/data:ro" -v "$OUTPUT_DIR:/out" --entrypoint python "$IMAGE" \
  /repo/tools/residual_profit_exit/reproduce.py \
  --account ON2020 --strategy-dir /strategy --data-dir /data \
  --output /out/ON2020
```

For Native, create a worktree at the pinned base and mount that as `/strategy`.
Select `Native2020`, `Native2023` or `Native2024`. Enabled choices are `ON2020`,
`ON2023` and `ON2024`; the latter years require their 210 or 273 matching files.
Use the same lock as any other backtest on the host.

## Historical seven-period results

These previously completed v18.0.159 / Freqtrade 2026.2 accounts are separate
from current-source confirmation. All periods were exposed. Wallets reset to
10,000 USDT each year, with fixed stake 100, ten configured slots, 5m, and
PA/de-risk/grinding enabled. Pair counts were 9/14/23/30/39/76/149; 2026 ends
at 2026-10-01 exclusive. No independent-year sum is a continuous return.

| Year | Native trades/wins/losses | Enabled trades/wins/losses | Native PnL USDT | Enabled PnL USDT | Difference |
|---|---|---|---:|---:|---:|
| 2020 | 73/72/1 | 76/76/0 | 484.05673597 | 563.13127067 | 79.07453470 |
| 2021 | 620/619/1 | 621/620/1 | 5067.35508428 | 5076.25730244 | 8.90221816 |
| 2022 | 178/178/0 | 178/178/0 | 1076.69325810 | 1076.81507012 | 0.12181202 |
| 2023 | 182/174/8 | 182/174/8 | 787.67016268 | 772.05877428 | -15.61138840 |
| 2024 | 267/264/3 | 267/264/3 | 1706.59055753 | 1675.45695292 | -31.13360461 |
| 2025 | 486/485/1 | 487/486/1 | 3196.99998871 | 3189.84076331 | -7.15922540 |
| 2026 | 702/697/5 | 702/697/5 | 3633.94328816 | 3622.01573122 | -11.92755694 |

| Year | Marked DD %, Native / enabled | Dollar DD, Native / enabled | All-slot lifecycle loss minutes, Native / enabled | Force exits, Native / enabled | New losses |
|---|---|---|---|---|---:|
| 2020 | 1.703762 / 1.703762 | 171.8933 / 171.8933 | 0 / 0 | 1 / 0 | 0 |
| 2021 | 2.200127 / 2.134823 | 299.9199 / 291.0177 | 10 / 10 | 0 / 0 | 0 |
| 2022 | 1.003510 / 1.003510 | 103.4177 / 103.4177 | 0 / 0 | 0 / 0 | 0 |
| 2023 | 2.086283 / 2.086283 | 215.2780 / 215.2780 | 5 / 5 | 1 / 1 | 0 |
| 2024 | 1.508845 / 1.512299 | 162.0291 / 162.0291 | 265 / 265 | 0 / 0 | 0 |
| 2025 | 1.643650 / 1.643650 | 167.5181 / 167.5181 | 45 / 45 | 1 / 1 | 0 |
| 2026 | 1.466923 / 1.466923 | 161.6422 / 161.6422 | 0 / 0 | 1 / 1 | 0 |

The historical fixed adoption gates rejected the rule: long profit per occupied
day improved in only three of seven years, and both quiet-period gates failed.
The 2020 quiet gate failed even though profit improved, because it constrained
absolute trade-count and profit changes. In 2023-2026, both profit and long-slot
efficiency declined. No new losses were counted by the inclusive, side-blind
same-pair +/-24h historical rule. Two Native winners were omitted in 2025; no
Native losers were omitted. The original rejection is preserved.

Historical DD used corrected 2026.2 remaining-cost/funding marks at 5m closes,
not intrabar extremes. Final exit labels are not attribution of earlier de-risk
losses or later grind recovery. The old Native fill coverage limits remain:
2021 used an exact OFF fill ledger, while other Native snapshots can omit the
terminal fill. Current evidence uses the separately identified 2026.8 observer.
