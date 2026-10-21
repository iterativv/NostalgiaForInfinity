"""Regression guards for the hardened 669 dump-hunter short.

Signal 669 (`short_entry_condition_669_enable`, off by default) shorts a red candle that crosses
below the prior 48-candle low on explosive volume. On the 330-pair year it fired 919 times and
lost on 22 of them; the losses were not random, they were the ignitions that fired against a
calm or choppy tape: in a chop the same bar is a shakeout and the price comes back.

Three guards, all on columns the strategy already publishes:

  1. the ignition volume goes from 3.0x to 5.0x the 24h mean;
  2. the 4h has to be trending (ADX_14_4h > 25), so the dump is a continuation, not a mean
     reversion inside a range;
  3. the 5m Bollinger band is at least 1.15% wide, so the ignition happens in a live market and
     not on a dead pair, where the volume spike has no follow-through.

On the design window (2025-09 to 2026-09, 330 pairs) the pair takes 226 trades with no losers
and +17,119 USDT; on the 2024 out-of-sample year it takes 82 with no losers and +4,036.
"""

import ast
from pathlib import Path

REPO = Path(__file__).parents[2]
SOURCE = (REPO / "NostalgiaForInfinityX8.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _strategy_class():
  return next(node for node in TREE.body if isinstance(node, ast.ClassDef) and "NostalgiaForInfinity" in node.name)


def _block_669():
  start = SOURCE.index("# Condition #669 -")
  end = SOURCE.index("# Condition #670 -", start)
  return SOURCE[start:end]


def test_block_669_requires_an_ignition_volume():
  block = _block_669()

  assert "& (vol_rel > 5.0)" in block
  assert "& (vol_rel > 3.0)" not in block


def test_block_669_requires_a_trending_4h():
  block = _block_669()

  assert "& (adx_14_4h > 25.0)" in block
  assert 'adx_14_4h = np_view("ADX_14_4h")' in SOURCE


def test_block_669_requires_a_live_market():
  block = _block_669()

  assert "& (bbb_20_2_0 > 1.15)" in block
  assert 'bbb_20_2_0 = np_view("BBB_20_2.0")' in SOURCE


def test_block_669_keeps_its_original_core():
  block = _block_669()

  assert "(roc_288 > -10.0)" in block
  assert "& (roc_9_1d < -5.0)" in block
  assert "& (close < (open_rate * 0.997))" in block
  assert "& (close < dh_prev_min)" in block
  assert "& (np_shift(close, 1) >= dh_prev_min)" in block


def test_signal_669_still_ships_disabled():
  params = _strategy_class()
  defaults = [node for node in ast.walk(params) if isinstance(node, ast.Dict)]
  found = False
  for node in defaults:
    for key, value in zip(node.keys, node.values, strict=False):
      if isinstance(key, ast.Constant) and key.value == "short_entry_condition_669_enable":
        assert isinstance(value, ast.Constant) and value.value is False
        found = True
  assert found, "the 669 enable key is missing from the parameter defaults"
