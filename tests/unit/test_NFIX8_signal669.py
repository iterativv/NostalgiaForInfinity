"""Guards for the 669 dump-hunter short signal (per-loss protection chains)."""

import ast
from pathlib import Path

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"


def _block_source() -> str:
  src = STRATEGY.read_text()
  start = src.index("# Condition #669 - Dump hunter")
  end = src.index("# Condition #670 - Marubozu momentum", start)
  return src[start:end]


def test_signal_definition_keeps_the_factory_volume_threshold():
  block = _block_source()
  logic = block[block.index("# Logic") :]
  assert "& (vol_rel > 3.0)" in logic
  assert "& (vol_rel > 5.0)" not in logic
  assert "adx_14_4h > 25.0" not in logic
  assert "bbb_20_2_0 > 1.15" not in logic


def test_protection_chains_are_present():
  block = _block_source()
  protections = block[: block.index("# Logic")]
  chains = [
    "((vol_rel <= 8.0) | (bbb_20_2_0 <= 3.0) | (close <= (ema_200_1h * 0.96)))",
    "((bbb_20_2_0 >= 1.0) | (bbp_20_2_0 <= -0.2) | (rsi_14 >= 30.0))",
    "((bbb_20_2_0 >= 1.0) | (rsi_14 >= 30.0) | (roc_9_1d >= -15.0))",
    "((bbb_20_2_0 >= 1.0) | (willr_14 <= -75.0) | (rsi_14_1d <= 45.0))",
    "((vol_rel >= 4.0) | (willr_14 <= -80.0) | (adx_14_4h >= 18.0))",
  ]
  for chain in chains:
    assert chain in protections, chain


def test_protection_columns_are_extracted_before_use():
  src = STRATEGY.read_text()
  tree = ast.parse(src)
  populate = next(
    node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "populate_entry_trend"
  )
  assigned = {
    target.id
    for node in ast.walk(populate)
    if isinstance(node, ast.Assign)
    for target in node.targets
    if isinstance(target, ast.Name)
  }
  for name in (
    "vol_rel",
    "bbb_20_2_0",
    "bbp_20_2_0",
    "rsi_14",
    "willr_14",
    "roc_9_1d",
    "rsi_14_1d",
    "adx_14_4h",
    "ema_200_1h",
  ):
    assert name in assigned, name


def test_signal_is_disabled_by_default():
  src = STRATEGY.read_text()
  assert '"short_entry_condition_669_enable": False' in src
