#!/usr/bin/env python3
"""Compare two Freqtrade backtest result exports.

This is intentionally a small tooling helper. It does not import or execute any
strategy code, and it does not change trading behavior.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import zipfile


TRADE_FIELDS = (
  "pair",
  "is_short",
  "open_date",
  "close_date",
  "enter_tag",
  "exit_reason",
  "profit_ratio",
  "profit_abs",
)

SUMMARY_FIELDS = (
  "total_trades",
  "profit_total",
  "profit_total_abs",
  "profit_factor",
  "winrate",
  "max_drawdown_account",
  "max_relative_drawdown",
  "max_drawdown_abs",
  "best_pair",
  "worst_pair",
)


def result_json_name(zip_file: zipfile.ZipFile) -> str:
  candidates = [
    name
    for name in zip_file.namelist()
    if name.endswith(".json") and not name.endswith("_config.json") and not name.endswith(".meta.json")
  ]
  if len(candidates) != 1:
    raise RuntimeError(f"Expected one backtest result json in {zip_file.filename}, found {candidates}")
  return candidates[0]


def load_result_file(path: Path) -> dict:
  if path.suffix == ".zip":
    with zipfile.ZipFile(path) as zip_file:
      return json.loads(zip_file.read(result_json_name(zip_file)))

  if path.suffix == ".json":
    return json.loads(path.read_text(encoding="utf-8"))

  raise RuntimeError(f"Unsupported result file type: {path}")


def strategy_result(data: dict, path: Path, strategy: str | None) -> tuple[str, dict]:
  strategies = data.get("strategy")

  if isinstance(strategies, dict):
    if strategy is not None:
      if strategy not in strategies:
        raise RuntimeError(f"Strategy {strategy!r} not found in {path}. Available: {sorted(strategies)}")
      return strategy, strategies[strategy]

    if len(strategies) != 1:
      raise RuntimeError(f"Expected one strategy in {path}. Use --left-strategy/--right-strategy.")

    strategy_name = next(iter(strategies))
    return strategy_name, strategies[strategy_name]

  if isinstance(strategies, str):
    strategy_name = strategy or strategies
    if strategy_name not in data:
      raise RuntimeError(f"Strategy {strategy_name!r} not found in top-level result data for {path}")
    return strategy_name, data[strategy_name]

  raise RuntimeError(f"Unsupported strategy result format in {path}")


def normalize_value(value: object, float_digits: int) -> object:
  if isinstance(value, float):
    return round(value, float_digits)
  return value


def normalize_trade(trade: dict, float_digits: int) -> dict:
  return {field: normalize_value(trade.get(field), float_digits) for field in TRADE_FIELDS}


def compare_trades(left: dict, right: dict, float_digits: int) -> tuple[bool, dict | None]:
  left_trades = [normalize_trade(trade, float_digits) for trade in left.get("trades", [])]
  right_trades = [normalize_trade(trade, float_digits) for trade in right.get("trades", [])]

  for index, (left_trade, right_trade) in enumerate(zip(left_trades, right_trades, strict=False)):
    if left_trade != right_trade:
      return False, {"index": index, "left": left_trade, "right": right_trade}

  if len(left_trades) != len(right_trades):
    return False, {"left_count": len(left_trades), "right_count": len(right_trades)}

  return True, None


def build_report(
  left_path: Path,
  right_path: Path,
  left_strategy: str | None,
  right_strategy: str | None,
  float_digits: int,
) -> dict:
  left_name, left = strategy_result(load_result_file(left_path), left_path, left_strategy)
  right_name, right = strategy_result(load_result_file(right_path), right_path, right_strategy)
  equal, first_difference = compare_trades(left, right, float_digits)

  return {
    "left_strategy": left_name,
    "right_strategy": right_name,
    "trade_surface_equal": equal,
    "left_summary": {field: left.get(field) for field in SUMMARY_FIELDS},
    "right_summary": {field: right.get(field) for field in SUMMARY_FIELDS},
    "first_difference": first_difference,
  }


def print_text_report(report: dict) -> None:
  print(f"left_strategy={report['left_strategy']}")
  print(f"right_strategy={report['right_strategy']}")
  print(f"trade_surface_equal={report['trade_surface_equal']}")
  print(f"left_total_trades={report['left_summary'].get('total_trades')}")
  print(f"right_total_trades={report['right_summary'].get('total_trades')}")
  if report["first_difference"] is not None:
    print("first_difference=")
    print(json.dumps(report["first_difference"], indent=2, sort_keys=True))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Compare the exported trade surface of two Freqtrade backtest result files."
  )
  parser.add_argument("left", type=Path, help="Left backtest result .zip or .json.")
  parser.add_argument("right", type=Path, help="Right backtest result .zip or .json.")
  parser.add_argument("--left-strategy", help="Strategy name to read from the left result when multiple exist.")
  parser.add_argument("--right-strategy", help="Strategy name to read from the right result when multiple exist.")
  parser.add_argument("--float-digits", type=int, default=10, help="Decimal places used for float comparison.")
  parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output.")
  return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
  args = parse_args(argv)
  report = build_report(
    left_path=args.left,
    right_path=args.right,
    left_strategy=args.left_strategy,
    right_strategy=args.right_strategy,
    float_digits=args.float_digits,
  )

  if args.json:
    print(json.dumps(report, indent=2, sort_keys=True))
  else:
    print_text_report(report)

  return 0 if report["trade_surface_equal"] else 1


if __name__ == "__main__":
  sys.exit(main())
