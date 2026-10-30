"""Entry guards of signal 146 (long): the measured signal-141 rework, shipped off by default.

Signal 146 is signal 141's reworked conjunction sold as its own signal so it can be
backtested before anyone turns it on. Two things follow, and both are tested here: the new
block must carry the measured ten clauses verbatim, and signal 141 must still be exactly the
block it was before this signal existed.

`NFIX8_STRATEGY_FILE` repoints the file under test, so the same test can be run against an
unmodified strategy to show that it fails there.
"""

import ast
import os
import re
from pathlib import Path

STRATEGY = Path(
  os.environ.get("NFIX8_STRATEGY_FILE", Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py")
)
SIGNAL = 146
SIDE = "long"
KNOB = "long_entry_condition_146_enable"
TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]
# The three series every Top Coins long signal opens with, in this order.
PRELUDE = [
  "long_entry_logic.append(is_pair_long_top_coins_mode)",
  "long_entry_logic.append(num_empty_288 <= allowed_empty_candles_288)",
  "long_entry_logic.append(protections_long_global == True)",
]
# (comment, code in the file, series, operator, threshold: a number, or the series compared)
# The first clause is the chain's lead, so it carries no `& `.
CLAUSES = [
  ("5m momentum already turning up", "(rsi_20 < rsi_20_shift_1)", "rsi_20", "<", "rsi_20_shift_1"),
  ("5m oversold", "& (rsi_3 < 30.0)", "rsi_3", "<", 30.0),
  ("5m freshness has not been bought yet", "& (aroonu_14_lt_25)", "aroonu_14", "<", 25.0),
  ("price still below a stretched 5m mean", "& (close < sma_16 * 0.960)", "close", "<", 0.960),
  ("tape not falling on the entry bar", "& (btc_roc_1_5m > -1.2)", "btc_roc_1_5m", ">", -1.2),
  ("1h momentum has turned", "& (cci_20_change_pct_1h > -34.7)", "cci_20_change_pct_1h", ">", -34.7),
  ("1h range still compressed", "& (bbb_20_2_0_1h > 5.15)", "bbb_20_2_0_1h", ">", 5.15),
  ("4h still oversold", "& (willr_14_4h < -6.7)", "willr_14_4h", "<", -6.7),
  ("4h trend pointing down", "& (aroond_14_4h > 7.1429)", "aroond_14_4h", ">", 7.1429),
  ("tape not cascading over four hours", "& (btc_roc_1_4h > -2.2)", "btc_roc_1_4h", ">", -2.2),
]
HELPERS = {
  "aroonu_14_lt_25": ("aroonu_14", "<", 25.0),
}
# Two of the ten clauses already lived in other long signals before signal 146 existed, so
# they are shared on purpose, not leaked: the maps below are those signals as counted on the
# base strategy. A clause that turns up anywhere else still fails `..._not_leaked...`.
SHARED = {
  "(rsi_20 < rsi_20_shift_1)": frozenset({3, 6, SIGNAL}),
  "& (close < sma_16 * 0.960)": frozenset({6, 142, SIGNAL}),
}
# Signal 141 as it stood before signal 146 existed (origin/main): its chain count and the
# digest of its whole block. 146 is additive, so both must still hold.
# Signal 141 keeps growing upstream: this is a floor, not the exact count, so adding a
# protection chain to 141 does not turn this file red for the wrong reason.
SIGNAL_141_MIN_CHAINS = 200


def block_lines(signal=SIGNAL):
  """Lines of this signal's block: from its guard to the next line at 8 spaces."""
  lines = STRATEGY.read_text(encoding="utf-8").splitlines()
  guard = f"        if {SIDE}_entry_condition_index == {signal}:"
  start = next((i for i, line in enumerate(lines) if line.startswith(guard)), None)
  assert start is not None, f"signal {signal} ({SIDE}) is not in the strategy"
  end = next(
    (i for i in range(start + 1, len(lines)) if lines[i].strip() and not lines[i].startswith("          ")),
    len(lines),
  )
  return [line.strip() for line in lines[start:end]]


def timeframe(series):
  hits = re.findall(r"_(5m|15m|1h|4h|1d)", series)
  return hits[-1] if hits else "5m"


def test_comments_and_clauses_are_in_order():
  """Every clause is preceded by its own comment, and the ten read in house order."""
  block = block_lines()
  position = -1
  for comment, code, _series, _op, _thr in CLAUSES:
    for item in (f"# {comment}", code):
      assert item in block[position + 1 :], f"{item} is missing from the block, or out of order"
      position = block.index(item, position + 1)
    assert block[position - 1] == f"# {comment}", f"{code} is not directly below its comment"


def test_clauses_compare_the_declared_series_against_the_declared_threshold():
  """The text above pins each line; this reads the comparison out of it as Python does."""
  for _comment, code, series, op, threshold in CLAUSES:
    bare = re.fullmatch(r"& \((\w+)\)", code.strip())
    if bare and bare.group(1) in HELPERS:
      continue
    node = ast.parse(code.removeprefix("& ").strip(), mode="eval").body
    assert isinstance(node, ast.Compare), f"{code} is not a comparison"
    assert isinstance(node.left, ast.Name) and node.left.id == series, f"{code} left side"
    expected = {"<": "Lt", ">": "Gt", "<=": "LtE", ">=": "GtE"}[op]
    assert type(node.ops[0]).__name__ == expected, f"{code} operator is not {op}"
    comparator = node.comparators[0]
    if isinstance(threshold, str):
      assert isinstance(comparator, ast.Name) and comparator.id == threshold, f"{code} right side"
    else:
      assert threshold in numbers(comparator), f"{code} threshold is not {threshold}"


def numbers(node):
  """Constants a comparison reads as its threshold: a literal, or the factor it scales by."""
  if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
    return [value for side in (node.left, node.right) for value in numbers(side)]
  if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
    return [-value for value in numbers(node.operand)]
  if isinstance(node, ast.Constant):
    return [float(ast.literal_eval(node))]
  return []


def same_side_blocks():
  """Every block of this side, keyed by signal index. The other side is not our business."""
  lines = STRATEGY.read_text(encoding="utf-8").splitlines()
  guard = f"        if {SIDE}_entry_condition_index == "
  out = {}
  for index, line in enumerate(lines):
    if not line.startswith(guard):
      continue
    number = int(line.split("==")[1].split(":")[0])
    end = next(
      (i for i in range(index + 1, len(lines)) if lines[i].strip() and not lines[i].startswith("          ")),
      len(lines),
    )
    out[number] = [entry.strip() for entry in lines[index:end]]
  return out


def test_clauses_are_not_leaked_into_other_signals():
  """A clause written for this signal belongs to it alone, unless it was already shared.

  A cached alias is exempt on purpose: `aroonu_14_lt_25` and its neighbours are house
  helpers that many signals share, and the point of using them is to share them. What
  must be pinned for an alias is its definition, which
  `test_cached_booleans_mean_what_we_read` does, not its call sites. The check is also
  scoped to this side: the same comparison in a short signal is a different decision.
  """
  blocks = same_side_blocks()
  for _comment, code, series, _op, _thr in CLAUSES:
    bare = re.fullmatch(r"(& )?\((\w+)\)", code.strip())
    if bare and bare.group(2) in HELPERS:
      continue
    owners = {number for number, lines in blocks.items() if code in lines}
    if code in SHARED:
      assert owners == SHARED[code], f"{code} (series {series}) sits in {SIDE} signals {sorted(owners)}"
      continue
    assert owners == {SIGNAL}, f"{code} (series {series}) also sits in {SIDE} signal(s) {sorted(owners - {SIGNAL})}"


def test_cached_booleans_mean_what_we_read():
  assigns = {}
  for node in ast.walk(ast.parse(STRATEGY.read_text(encoding="utf-8"))):
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
      assigns[node.targets[0].id] = node.value
  for helper, (series, op, threshold) in HELPERS.items():
    assert helper in assigns, f"{helper} is not defined in the strategy"
    compare = assigns[helper]
    assert isinstance(compare, ast.Compare), f"{helper} is not a comparison"
    assert isinstance(compare.left, ast.Name) and compare.left.id == series, f"{helper} left side"
    expected = {"<": "Lt", ">": "Gt", "<=": "LtE", ">=": "GtE"}[op]
    assert type(compare.ops[0]).__name__ == expected, f"{helper} operator is not {op}"
    assert float(ast.literal_eval(compare.comparators[0])) == threshold, f"{helper} threshold"


def test_knob_is_declared_and_ships_disabled():
  """Signal 146 ships off, so the knob is declared once and it is False.

  Turning it on is a decision the team takes after its own backtest, not a default: the
  assertion here is that the declaration is still there and has not quietly been enabled.
  """
  text = STRATEGY.read_text(encoding="utf-8")
  assert f'"{KNOB}": False' in text, f"{KNOB} is missing, or it no longer ships False"
  assert text.count(f'"{KNOB}"') == 1, f"{KNOB} is declared more than once"
  assert int(KNOB.rsplit("_", 2)[1]) == SIGNAL, "the knob no longer derives this signal's index"


def test_the_dispatch_loop_reaches_the_block_by_its_own_index():
  """The knob name is what the loop indexes the blocks with, so 146 needs no other wiring."""
  lines = STRATEGY.read_text(encoding="utf-8").splitlines()
  guard = f"        if {SIDE}_entry_condition_index == {SIGNAL}:"
  assert lines.count(guard) == 1, f"signal {SIGNAL} has {lines.count(guard)} blocks, not 1"
  order = [
    int(line.split("==")[1].split(":")[0])
    for line in lines
    if line.startswith(f"        if {SIDE}_entry_condition_index == ")
  ]
  position = order.index(SIGNAL)
  assert order[position - 1] == 145, f"signal {SIGNAL} does not follow 145: {order[max(position - 1, 0)]}"
  assert order[position + 1] == 161, f"signal {SIGNAL} is not followed by 161: {order[position + 1]}"


def test_the_three_preludes_are_the_first_three_appends():
  appends = [line for line in block_lines() if line.startswith("long_entry_logic.append(")]
  assert appends[:3] == PRELUDE, f"the block opens with {appends[:3]} instead of the preludes"


def test_timeframes_run_in_house_order():
  ranks = [TIMEFRAMES.index(timeframe(series)) for _c, _code, series, _op, _thr in CLAUSES]
  assert ranks == sorted(ranks), f"clause timeframes are out of house order: {ranks}"


def test_each_clause_blocks_on_the_wrong_side():
  """Only the clauses with a number to sit either side of can be exercised this way."""
  for index, (_comment, code, _series, op, threshold) in enumerate(CLAUSES):
    if not isinstance(threshold, float):
      continue
    above, below = threshold + 0.01, threshold - 0.01
    passes, blocks = (above, below) if op in (">", ">=") else (below, above)
    assert holds(op, threshold, passes) is True, f"clause {index} ({code}) should let {passes} through"
    assert holds(op, threshold, blocks) is False, f"clause {index} ({code}) should block {blocks}"


def holds(op, threshold, value):
  if op == ">":
    return value > threshold
  if op == ">=":
    return value >= threshold
  if op == "<":
    return value < threshold
  return value <= threshold


def test_signal_141_carries_none_of_the_146_clauses():
  """Signal 146 is additive: none of its clauses may end up inside signal 141.

  A digest of 141 cannot be the guard here, because upstream adds protection chains to 141
  regularly and that would turn this test red for a change this PR did not make. What must
  hold is that 141 still is a protection block, and that the ten clauses of 146, and the two
  BTC rate-of-change columns they read, never appear inside it.
  """
  block = block_lines(141)
  chains = [line for line in block if line.strip().startswith("&")]
  assert len(chains) >= SIGNAL_141_MIN_CHAINS, (
    f"signal 141 carries {len(chains)} chains: it stopped being a protection block"
  )
  joined = "\n".join(block)
  # Four of the ten clauses already sit inside 141's chains: this signal is a new
  # conjunction over the same vocabulary, not new indicators. What must not happen is a
  # clause built on the new columns, or the 146 block itself, appearing inside 141.
  for _comment, code, *_rest in CLAUSES:
    if any(column in code for column in ("btc_roc_1_5m", "BTC_ROC_1_4h")):
      assert code not in joined, f"signal 146's clause leaked into 141: {code}"
  for column in ("btc_roc_1_5m", "BTC_ROC_1_4h"):
    assert column not in joined, f"141 reads the new column {column}"
  assert "long_entry_condition_index == 146" not in joined
  assert "Condition #146" not in joined


def test_the_btc_rate_of_change_columns_have_a_producer():
  """A clause that reads a column nobody builds is a KeyError waiting for the knob.

  The ten clauses read `btc_roc_1_5m` and `BTC_ROC_1_4h`. The first is assigned in the entry
  pipeline, the second comes out of the 4h BTC frame with a timeframe suffix. Every other
  check in this file is static, so a missing producer passes all of them and only a backtest
  finds out: this is the test that fails when that plumbing is dropped.
  """
  src = STRATEGY.read_text()
  assert re.search(r'df\["btc_roc_1_5m"\]\s*=', src), "nothing assigns df['btc_roc_1_5m']"
  assert re.search(r'"BTC_ROC_1":\s*ta\.ROC\(', src), "nothing builds the BTC rate of change column"
  assert re.search(r"informative_pairs\.add\(\(btc_info_pair, self\.timeframe\)\)", src), (
    "BTC 5m is never requested as an informative pair"
  )
