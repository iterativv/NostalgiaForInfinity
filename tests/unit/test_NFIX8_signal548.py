"""Guards for the 548 market-order-bubble short signal (per-loss protection chains)."""

import ast
from pathlib import Path

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"


def _block_source() -> str:
  src = STRATEGY.read_text()
  start = src.index("# Condition #548 - Market-order bubble")
  end = src.index("# Condition #561 - Downtrend Pullback", start)
  return src[start:end]


def test_protection_chains_are_present():
  block = _block_source()
  protections = block[: block.index("# Logic")]
  chains = [
    "((bbb_20_2_0 >= 0.8) | (mfi_14 >= 25.0) | (rsi_14_1d >= 30.0))",
    "((vol_rel <= 5.0) | (willr_14 <= -60.0) | (close <= (ema_200_1d * 0.90)))",
    "((mfi_14 >= 25.0) | (willr_14 <= -85.0) | (rsi_14_1d >= 30.0))",
    "((willr_14 >= -85.0) | (adx_14_4h >= 15.0) | (rsi_14_1d >= 45.0))",
    "((vol_rel <= 8.0) | (bbb_20_2_0 >= 0.8) | (adx_14_4h >= 15.0))",
    "((vol_rel <= 3.0) | (willr_14 >= -85.0) | (rsi_14_1d >= 35.0))",
    "((vol_rel >= 3.0) | (rsi_14_1d >= 30.0) | (close <= (ema_200_1h * 0.94)))",
  ]
  for chain in chains:
    assert chain in protections, chain


def test_signal_logic_is_untouched():
  block = _block_source()
  logic = block[block.index("# Logic") :]
  for clause in (
    "(stochrsi_k_1d < 50.0)",
    "(stochrsi_k_1h < 80.0)",
    "(aroonu_14_4h < 50.0)",
    "(aroonu_14_1d < 50.0)",
    "(ema_50_15m < ema_200_15m)",
    "(close >= (ema_50_15m * 0.998))",
    "(close < ema_200_15m)",
    "(volume > large_bubble_thr)",
    "(cvd_sell_vol > cvd_buy_vol)",
  ):
    assert clause in logic, clause
  assert "rsi_14_1d" not in logic
  assert "adx_14_4h" not in logic


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
    "mfi_14",
    "willr_14",
    "rsi_14_1d",
    "adx_14_4h",
    "ema_200_1h",
    "ema_200_1d",
  ):
    assert name in assigned, name


def test_signal_is_disabled_by_default():
  src = STRATEGY.read_text()
  assert '"short_entry_condition_548_enable": False' in src
