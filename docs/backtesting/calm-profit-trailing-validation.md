# X8 optional calm-market profit trailing

This option lets an already profitable long position continue beyond its first
Native profit target while the measured market remains calm. It is disabled by
default. It is a different exit policy, not a correction to Native exits.

```json
{
  "risk_calm_trail_enable": true
}
```

The same key is accepted inside `nfi_parameters`. It does not require advanced
mode. Short positions use the original path.

## Fixed behavior

Admission requires the first newly committed positive Native long profit target
of the current Trade, a finite completed-daily market stress score below 20, a
positive callback price, at least two analyzed rows, and positive Native
lifecycle cash PnL. Lifecycle cash includes earlier executed reductions and fees;
the futures path also includes funding. A positive residual price return alone
is not sufficient.

The stress score is the percentage of eligible current-whitelist markets whose
daily close is more than 25% below their rolling 30-day high. Eligibility requires
50 observed nonmissing closes and a usable rolling high. The daily result is
merged only when that daily candle is complete; missing or expired observations
do not establish calm conditions.

Once admitted, the trail starts at that callback's price and follows only later
observed callback prices. It requests an exit at or below 80% of the observed
peak. This is a **20% price retracement**, not a 20% leveraged return threshold.
It does not use a historical trade high, an unobserved candle wick, or a timeout.

Only the nonprotective profit exit belonging to the admitted Native target
episode is deferred. The original target evaluator still runs once. Protective
targets, unrelated profit episodes, direct exits and other Native exits keep
priority. Losing the target cache ends that deferral, but not the independent
price trail.

An ineligible first opportunity is consumed; it is not retried when conditions
later improve. A preexisting target at first activation is not retroactively
admitted. Loss of calm conditions or an invalid observation cancels an active
trail permanently. An already-issued exit intent instead remains pending and is
retried, with Native exits still taking priority.

State is stored on the Trade and survives a database reload. Disabling the option
uses Native behavior without updating that state; re-enabling can resume the
stored trail or pending intent. A new Trade on the same pair does not inherit it.

## Trade-offs

A profitable admission does not guarantee a profitable exit. A 20% retracement
can turn a Native winner into a loss and keep a slot occupied longer. The original
Native protections remain available, but they do not make this policy risk-free.
An exit callback result is an intent, not proof that an order filled.

## Public software reproduction

The implementation was prepared from upstream commit
`57d84e44db42c2da93e6b99d4334874724b07e7c`. The candidate strategy SHA-256 is
`b172cf60233a84ce2a72d4cea956504bf6a9e2d929ad4dde7263db7613535e21`.

The public suite contains 155 feature cases covering admission, price and stress
boundaries, cancellation, pending retries, real SQLite Trade reloads, actual
partial fills, fees, funding, spot/futures lifecycle cash, Native priority and
causal daily-data merging. No private study file or downloaded market data is
needed for these tests.

From the repository root, with the pinned image available locally:

```bash
IMAGE=ghcr.io/iterativv/ci-strategy-backtesting@sha256:c356a7900503e964e0cbe7d92a499171c4090998e9bdf0efa76053b27d249107
docker run --rm --network none --cpus 2 --memory 3g --memory-swap 3g \
  --user "$(id -u):$(id -g)" \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo \
  -v "$PWD:/repo:ro" -w /repo --entrypoint python "$IMAGE" \
  -m pytest -c /repo/pytest.ini -o addopts= -o log_cli=false \
  -p no:cacheprovider tests/unit tests/tools -q
```

Observed result: **3,203 passed, zero failures, zero skips**, including the 3,039
existing cases, 155 feature cases and nine replay-comparison cases.
The 14 warnings came from existing legacy qtpylib and
indicator tests. Pre-commit also passed. The software image uses Freqtrade 2026.9;
it is not the separately pinned 2026.8 market-data backtest image.

For feature-only execution, replace `tests/unit tests/tools` with
`tests/unit/test_NFIX8_calm_trailing_*.py`. These software results establish the
specified behavior, not portfolio profitability or live execution quality.

## Current-source measured comparison

Native is the unmodified strategy at the pinned base; enabled is the same
strategy plus this option. Each year uses identical data, pair order, wallet,
slot limit and settings across arms. The 2023 universe has 30 pairs and 2024 has
39. These exposed periods deliberately include a known favorable and a known
adverse historical result. They are not an untouched holdout.

### Long positions within the shared portfolio

| Year | Native trades/wins/losses | Enabled trades/wins/losses | Native PnL | Enabled PnL | Difference, USDT |
|---|---|---|---:|---:|---:|
| 2023 | 151/145/6 | 145/137/8 | 800.61 | 1070.83 | 270.21 |
| 2024 | 224/222/2 | 217/209/8 | 1682.57 | 1460.85 | -221.72 |

### Whole portfolio and costs

| Metric / year | Native | Enabled | Difference |
|---|---:|---:|---:|
| Net PnL USDT / 2023 | 833.70 | 1103.91 | 270.21 |
| Trades / 2023 | 181 | 175 | -6 |
| Wins / 2023 | 174 | 166 | -8 |
| Losses / 2023 | 7 | 9 | 2 |
| Losing-trade PnL subtotal USDT / 2023 | -238.79 | -345.28 | -106.49 |
| Marked equity DD % / 2023 | 2.081499 | 2.615920 | 0.534421 |
| Maximum dollar DD USDT / 2023 | 215.1144 | 274.1485 | 59.0340 |
| All-slot lifecycle loss minutes / 2023 | 5 | 90 | 85 |
| Longest all-slot loss minutes / 2023 | 5 | 65 | 60 |
| Long occupied days / 2023 | 169.0833 | 210.1528 | 41.0694 |
| Long PnL per occupied day / 2023 | 4.735031 | 5.095482 | 0.360451 |
| Force exits / 2023 | 1 | 1 | 0 |
| Net PnL USDT / 2024 | 1714.84 | 1492.67 | -222.16 |
| Trades / 2024 | 265 | 257 | -8 |
| Wins / 2024 | 262 | 248 | -14 |
| Losses / 2024 | 3 | 9 | 6 |
| Losing-trade PnL subtotal USDT / 2024 | -155.57 | -497.78 | -342.21 |
| Marked equity DD % / 2024 | 1.507979 | 1.666737 | 0.158757 |
| Maximum dollar DD USDT / 2024 | 159.4668 | 170.5105 | 11.0438 |
| All-slot lifecycle loss minutes / 2024 | 265 | 285 | 20 |
| Longest all-slot loss minutes / 2024 | 90 | 90 | 0 |
| Long occupied days / 2024 | 122.5625 | 277.2014 | 154.6389 |
| Long PnL per occupied day / 2024 | 13.728251 | 5.270007 | -8.458243 |
| Force exits / 2024 | 0 | 0 | 0 |

The losing-trade subtotal is already included in net PnL. Percentage-DD changes
are percentage points. Marks use 5m closes, include prior realized reductions
and funding-corrected remaining inventory, and reconcile with portfolio equity
on every observed row. Final pre-force-exit marks are separate from final
exported PnL. Per-tag cohorts in the JSON overlap and must not be added together.

In 2023, six Native winners were omitted and two matched winners became losses.
In 2024, eight Native winners were omitted and six matched winners became losses.
There were no omitted losers, new entries, or earlier-closed matched winners or
losers in either comparison. The historical +/-24h new-loss rule also counted
two and six respectively. Full records retain these distinct definitions.
Long-only callback behavior does not imply unchanged short outcomes: longer
shared-slot occupation can change which short trades execute.

The concrete benefit is the additional 2023 long profit and higher profit per
occupied day. The costs are increased DD and loss time in both years, longer
occupation, and lower 2024 profit and efficiency. This is a default-OFF policy
choice for review, not a claim that enabling it generally improves results.

## Current-source controls

The current-source controls used official Freqtrade 2026.8, independently of the
historical evidence below:

- 2023 replay-only Native versus observed Native: all 181 exported trades and
  448 executed order records were identical.
- 2024 Native versus the candidate with the option OFF: all 265 trades and
  714 executed order records were identical. Marked-equity CSV bytes, signal
  inputs, exchange inputs and effective parameters also matched, excluding only
  the newly introduced flag.
- Full observed order fields reconciled with the official minified exports.
  The complete 2023 marked-equity series reconciled against closed trades and
  each open position's earlier realized and remaining unrealized PnL.

These controls establish observer and default-OFF parity, not an ON improvement.

## Public account evidence and reproduction

`calm-profit-trailing-validation.json` contains the full signal-cohort metrics,
changed/omitted/new trade classifications, runtime and source identities,
effective flags, original annual configs, exchange snapshots and all 483 annual
data-file hashes. `calm-profit-trailing-ledgers.json` contains every trade in the
four comparison accounts and both minified and full actual Order records.
Requested `amount` and actual `filled` remain distinct fields.

The repository's `tools/calm_profit_trailing/reproduce.py` validates every input
data hash and the selected strategy hash, restores the recorded exchange inputs,
runs the official engine, and compares all published trade outcomes and executed
order records. It fails rather than silently accepting a changed dataset,
strategy, runtime, execution window or result. Output directories must be new.

The frozen candle files are **not bundled**. Exact account reproduction requires
the files matching the published hashes, including informative, mark and funding
data. Freshly downloaded or revised exchange history may not match. The exchange
replay still invokes the original network reload; it is not an offline engine.
The reproduction command verifies trades/orders, not the marked-equity trace.

Qualification: the final public command completed the full Native2023 account
and exactly matched all **181 trades and 448 executed orders**, with frozen
inputs unchanged. `calm-profit-trailing-reproduction.json` records the command's
runtime, source/tool/evidence hashes and result. This separate qualification ran
Native2023; the other three accounts were validated by the original matched
executor, not separately rerun through this public wrapper.

For the 2023 Native control, first make the pinned Native worktree:

```bash
git worktree add --detach ../nfi-calm-native \
  57d84e44db42c2da93e6b99d4334874724b07e7c
```

Set `DATA_DIR` to the 2023 directory containing `futures/` and the 210 matching
files, and `OUTPUT_DIR` to a writable output parent. Run from this PR's root:

```bash
: "${DATA_DIR:?Set DATA_DIR to the matching annual data directory}"
: "${OUTPUT_DIR:?Set OUTPUT_DIR to a writable output parent}"
mkdir -p "$OUTPUT_DIR"
IMAGE=freqtradeorg/freqtrade@sha256:4d23160b501d2b34579e76f57ad75edfa274967cd0dd824ff1c1b86d8c166ab4
flock /tmp/nfi-calm-profit-trailing.lock \
  docker run --rm --pull never --cpus 4 --memory 30g --memory-swap 30g \
  --user "$(id -u):$(id -g)" \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/repo \
  -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 \
  -v "$PWD:/repo:ro" -v "$PWD/../nfi-calm-native:/strategy:ro" \
  -v "$DATA_DIR:/data:ro" -v "$OUTPUT_DIR:/out" --entrypoint python "$IMAGE" \
  /repo/tools/calm_profit_trailing/reproduce.py \
  --account Native2023 --strategy-dir /strategy --data-dir /data \
  --output /out/Native2023
```

For `ON2023`, mount this PR's root as `/strategy` and select a new output directory.
For 2024, select `Native2024` or `ON2024` and supply the 273 matching 2024 files.
Use the same lock as any other running backtest on the host.

## Historical seven-period evidence

These are previously completed **v18.0.159 / Freqtrade 2026.2** results, not
current-source reruns. The historical candidate source SHA-256 was
`e29fc7a57387f59bea52704f0fd5122a02d4568e47e4e95070a13ef722c5bf59`.
Each independent period started with 10,000 USDT, fixed stake 100, ten slots,
5m candles, PA/de-risk/grinding enabled, and grind-mode max slots zero.
Pair counts were 9/14/23/30/39/76/149 respectively. The 2026 window ended at
2026-10-01 exclusive; the other rows cover their full calendar year.
Every period was already exposed during research.

| Period | Native trades/wins/losses | Enabled trades/wins/losses | Native PnL, USDT | Enabled PnL, USDT | Difference |
|---|---|---|---:|---:|---:|
| 2020 | 73/72/1 | 71/69/2 | 484.05673597 | 565.98440083 | +81.92766486 |
| 2021 | 620/619/1 | 603/600/3 | 5067.35508428 | 5404.26002802 | +336.90494374 |
| 2022 | 178/178/0 | 178/178/0 | 1076.69325810 | 1144.56163461 | +67.86837651 |
| 2023 | 182/174/8 | 176/166/10 | 787.67016268 | 1052.28243133 | +264.61226865 |
| 2024 | 267/264/3 | 259/250/9 | 1706.59055753 | 1487.08185613 | -219.50870140 |
| 2025 | 486/485/1 | 485/481/4 | 3196.99998871 | 3071.86424841 | -125.13574030 |
| 2026 | 702/697/5 | 701/695/6 | 3633.94328816 | 3725.31722262 | +91.37393446 |

| Period | Marked DD %, Native / enabled | Dollar DD, Native / enabled | All-slot lifecycle loss seconds, Native / enabled | New losses |
|---|---|---|---|---:|
| 2020 | 1.703762 / 1.700593 | 171.8933 / 171.8933 | 0 / 0 | 1 |
| 2021 | 2.200127 / 2.154363 | 299.9199 / 299.9199 | 600 / 600 | 2 |
| 2022 | 1.003510 / 1.000320 | 103.4177 / 103.4177 | 0 / 0 | 0 |
| 2023 | 2.086283 / 2.622852 | 215.2780 / 274.3121 | 300 / 5400 | 2 |
| 2024 | 1.508845 / 1.668151 | 162.0291 / 170.5640 | 15900 / 17100 | 6 |
| 2025 | 1.643650 / 1.643650 | 167.5181 / 167.5181 | 2700 / 2700 | 3 |
| 2026 | 1.466923 / 1.458734 | 161.6422 / 161.6422 | 0 / 0 | 1 |

The historical analysis corrected the 2026.2 raw-cost/funding marks and used 5m
closing prices, not intrabar extremes. A "new loss" here means no losing Native
trade on the same pair opened within an inclusive +/-24h window; this definition
is existential and side-blind, not exact trade matching.

PnL increased in five of seven periods, but long occupancy increased in every
period and long PnL per occupied day improved only in 2023. In 2024, long slot-days
rose from 119.2014 to 271.5069. There were 35 omitted Native winners and 15 Native
winners that became losses, with no omitted Native losses or new entries.
Force exits were unchanged except in 2026, where they increased from one to two.
There were no liquidations in either arm.

The historical fixed adoption gates therefore **rejected** this policy. That
decision is preserved. Presenting the option for review does not turn that
rejection into adoption approval or establish a general improvement. Independent
annual wallets are not a continuous or compounded return.
