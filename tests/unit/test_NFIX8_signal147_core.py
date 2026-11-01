"""Signal 147 (long): the signal-142 entry nucleus shipped on its own, without the wall.

Signal 147 is measured, not invented. It is exactly what signal 142 opens with -- the three
Top Coins long preludes plus the four-clause nucleus -- with the 520-line wall of OR chains
left behind, and it ships off by default. Two things follow, and both are tested here: the
new block must carry the measured nucleus verbatim, and signal 142 must still be the block
it was before this signal existed.

`NFIX8_STRATEGY_FILE` repoints the file under test, so the same test can be run against an
unmodified strategy to show that it fails there.
"""

import os
from pathlib import Path

STRATEGY = Path(
  os.environ.get("NFIX8_STRATEGY_FILE", Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py")
)
SIGNAL = 147
SIDE = "long"
KNOB = "long_entry_condition_147_enable"
# The three series every Top Coins long signal opens with, in this order.
PRELUDE = [
  "long_entry_logic.append(is_pair_long_top_coins_mode)",
  "long_entry_logic.append(num_empty_288 <= allowed_empty_candles_288)",
  "long_entry_logic.append(protections_long_global == True)",
]
# (comment, code in the file): the nucleus of signal 142, in the order it was measured. The
# first clause is the chain's lead, so it carries no `& `.
CLAUSES = [
  ("5m not fully sold off yet", "(rsi_3_gt_5)"),
  ("5m still weak", "& (rsi_4 < 46.0)"),
  ("5m momentum already turning up", "& (rsi_20 < rsi_20_shift_1)"),
  ("price still below a stretched 5m mean", "& (close < sma_16 * 0.960)"),
]
# Signal 147 is the nucleus alone. Three preludes, one append, four clauses: anything close
# to a wall here is a filter nobody measured.
MAX_CODE_LINES = 12
# Signal 142 keeps its wall. This is a floor, not the exact count, so an upstream edit to
# 142 does not turn this file red for the wrong reason.
SIGNAL_142_MIN_LINES = 400


def block_lines(signal):
  """Lines of this signal's block: from its guard to the next line at 8 spaces."""
  lines = STRATEGY.read_text(encoding="utf-8").splitlines()
  guard = f"        if {SIDE}_entry_condition_index == {signal}:"
  start = next((i for i, line in enumerate(lines) if line.startswith(guard)), None)
  assert start is not None, f"signal {signal} ({SIDE}) is not in the strategy"
  end = next(
    (i for i in range(start + 1, len(lines)) if lines[i].strip() and not lines[i].startswith("          ")),
    len(lines),
  )
  return lines[start:end]


def code_lines(block):
  """Body lines of a block: the guard goes, comments go, indentation goes."""
  return [line.strip() for line in block if line.strip() and not line.strip().startswith("#")][1:]


def nucleus(signal):
  """The last append of a block, comments dropped: its lead line, clauses and close."""
  block = block_lines(signal)
  openers = [i for i, line in enumerate(block) if "long_entry_logic.append(" in line]
  assert openers, f"signal {signal} has no logic append"
  start = openers[-1]
  end = next(i for i in range(start, len(block)) if block[i].strip() == ")")
  return [line.strip() for line in block[start : end + 1] if line.strip() and not line.strip().startswith("#")]


def test_signal_147_is_in_the_strategy():
  assert block_lines(SIGNAL), "signal 147 has no block"


def test_signal_147_opens_with_the_three_preludes():
  assert code_lines(block_lines(SIGNAL))[:3] == PRELUDE


def test_signal_147_carries_the_measured_nucleus_verbatim():
  block = block_lines(SIGNAL)
  found = [line.strip() for line in block if line.strip() in [code for _, code in CLAUSES]]
  assert found == [code for _, code in CLAUSES]
  text = "\n".join(block)
  for comment, _ in CLAUSES:
    assert f"# {comment}" in text


def test_signal_147_has_no_wall():
  code = code_lines(block_lines(SIGNAL))
  assert len(code) <= MAX_CODE_LINES, f"signal 147 grew a wall: {len(code)} code lines"


def test_signal_147_nucleus_is_the_signal_142_nucleus():
  assert nucleus(SIGNAL) == nucleus(142)


def test_signal_147_knob_ships_off():
  assert f'"{KNOB}": False,' in STRATEGY.read_text(encoding="utf-8")


def test_signal_142_still_has_its_wall():
  assert len(block_lines(142)) > SIGNAL_142_MIN_LINES
