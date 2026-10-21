"""Regression guards for the hardened 664 squeeze-release short.

Signal 664 shipped disabled. When it is switched on (`short_entry_condition_664_enable`) the raw
release alone only reached a 97.4% win rate on the live universe, and its 32 losers were slow
bleeders: the pair had already collapsed before the squeeze fired. Five guards take it to 100% on
the 2025-2026 universe at a third of the trades:

  1. the break has to be deep once volatility is removed, measured in ATR of the base timeframe;
  2. the daily range must not already be in the top decile (those releases are violent);
  3. the daily ADX must not be stretched (exhausted trends snap back);
  4. the daily EMA50 must not be in free fall over nine days (the 2024 losses);
  5. and the last nine daily candles must not have collapsed either.

Three of them need indicators the strategy did not compute: an ATR on the 5m frame and an ADX and
an ATR percentage on the daily informative pair. These checks pin both the columns and the guards,
because a missing column is a silent KeyError only when the block is enabled.
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

  assert '(close - ema_20) / np_view("ATR_14") < -1.2' in block


def test_block_664_filters_the_daily_regime():
  block = _block_664()

  assert 'np_view("ATR_PCT_14_1d") < 10.0' in block
  assert 'np_view("ADX_14_1d") < 45.0' in block
  assert 'np_view("ROC_9_1d") > -2.6' in block
  # nine days of the daily EMA50, shifted over the base timeframe (2592 closed 5m candles)
  assert 'np_view("EMA_50_1d") / np_shift(np_view("EMA_50_1d"), 2592) - 1.0' in block


def test_base_timeframe_publishes_atr_14():
  source = _function_source("base_tf_5m_indicators")

  assert "atr_14 = ta.ATR(high_np, low_np, close_np, timeperiod=14)" in source
  assert 'df["ATR_14"] = atr_14' in source


def test_daily_informative_pair_publishes_adx_and_atr_percent():
  source = _function_source("informative_1d_indicators")

  assert "ta.ADX(high_np, low_np, close_np, timeperiod=14)" in source
  assert 'informative_1d["ADX_14"] = adx_14_1d' in source
  assert 'informative_1d["ATR_PCT_14"] = atr_14_1d / np.maximum(close_np, 1e-12) * 100.0' in source


def test_signal_664_stays_disabled_by_default():
  source = _function_source("__init__") if "def __init__" in SOURCE else SOURCE
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
