"""Regression guards for the hardened 664 squeeze-release short.

Signal 664 shipped disabled. When it is switched on (`short_entry_condition_664_enable`) the raw
release alone only reached a 97.4% win rate on the live universe, and its 32 losers were slow
bleeders: the pair had already collapsed before the squeeze fired. Four guards take it to 100% on
the 2025-2026 universe at a third of the trades:

  1. the break has to be deep once volatility is removed (ATR of the base timeframe);
  2. the daily ADX must not be stretched (exhausted trends snap back);
  3. the daily EMA50 must not be in free fall over nine days (the 2024 losses);
  4. and the last nine daily candles must not have collapsed either.

The guards are the four cached comparisons the block uses, in house style: the comparisons are
defined once next to the other thresholds, so the block reads like its neighbours and the columns
it needs are listed in the extraction section. Only one indicator is new: an ADX on the daily
informative pair. The 5m ATR is published too, and the daily EMA50 and ROC9 already existed.
"""

import ast
import re
from pathlib import Path

REPO = Path(__file__).parents[2]
SOURCE = (REPO / "NostalgiaForInfinityX8.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _strategy_class():
  return next(node for node in TREE.body if isinstance(node, ast.ClassDef) and "NostalgiaForInfinity" in node.name)


def _function_source(name):
  cls = _strategy_class()
  func = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
  segment = ast.get_source_segment(SOURCE, func)
  assert segment is not None
  return segment


def _block_664():
  start = SOURCE.index("# Condition #664 -")
  end = SOURCE.index("# Condition #665 -", start)
  return SOURCE[start:end]


def test_block_664_requires_a_deep_break_measured_in_atr():
  block = _block_664()

  assert "& (ema_20_dist_atr_lt_neg_1_2)" in block
  assert "ema_20_dist_atr = (close - ema_20) / atr_14" in SOURCE
  assert "ema_20_dist_atr_lt_neg_1_2 = ema_20_dist_atr < -1.2" in SOURCE


def test_block_664_filters_the_daily_regime():
  block = _block_664()

  assert "& (adx_14_1d_lt_45)" in block
  assert "& (ema_50_1d_slope_9_gt_neg_7_5)" in block
  assert "& (roc_9_1d_gt_neg_2_6)" in block
  assert "adx_14_1d_lt_45 = adx_14_1d < 45.0" in SOURCE
  assert "roc_9_1d_gt_neg_2_6 = roc_9_1d > -2.6" in SOURCE
  # nine days of the daily EMA50, shifted over the base timeframe (2592 closed 5m candles)
  assert "ema_50_1d_slope_9 = (ema_50_1d / np_shift(ema_50_1d, 2592) - 1.0) * 100.0" in SOURCE
  assert "ema_50_1d_slope_9_gt_neg_7_5 = ema_50_1d_slope_9 > -7.5" in SOURCE


def test_block_664_columns_are_extracted_before_use():
  for local in ('atr_14 = np_view("ATR_14")', 'adx_14_1d = np_view("ADX_14_1d")', 'ema_50_1d = np_view("EMA_50_1d")'):
    assert local in SOURCE
  assert "np_view(" not in _block_664()


def test_base_timeframe_publishes_atr_14():
  source = _function_source("base_tf_5m_indicators")

  assert "atr_14 = ta.ATR(high_np, low_np, close_np, timeperiod=14)" in source
  assert 'df["ATR_14"] = atr_14' in source


def test_daily_informative_pair_publishes_adx():
  source = _function_source("informative_1d_indicators")

  assert "ta.ADX(high_np, low_np, close_np, timeperiod=14)" in source
  assert 'informative_1d["ADX_14"] = adx_14_1d' in source


def test_signal_664_stays_disabled_by_default():
  cls = _strategy_class()
  assigned = None
  for node in cls.body:
    if isinstance(node, ast.Assign) and any(
      getattr(t, "id", None) == "short_entry_signal_params" for t in node.targets
    ):
      assigned = ast.literal_eval(node.value)
  assert assigned is not None, "short_entry_signal_params is not a literal dict"
  assert assigned["short_entry_condition_664_enable"] is False
  assert re.search(r'"short_entry_condition_664_enable": False', SOURCE)
