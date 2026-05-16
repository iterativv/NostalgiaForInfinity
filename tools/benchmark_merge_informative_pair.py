#!/usr/bin/env python3
"""Benchmark repeated informative-pair merges with synthetic data.

This helper isolates DataFrame merge overhead. It does not import or execute
strategy code, and it does not change trading behavior.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from dataclasses import dataclass
import json
import math
from statistics import mean
from statistics import median
import sys
import time
from typing import Any


BASE_COLUMNS = ("open", "high", "low", "close", "volume")
DEFAULT_BTC_TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")
DEFAULT_INFO_TIMEFRAMES = ("15m", "1h", "4h", "1d")


@dataclass(frozen=True)
class MergeSpec:
  name: str
  source: str
  timeframe: str
  indicator_columns: int


def timeframe_to_minutes(timeframe: str) -> int:
  unit = timeframe[-1]
  value = int(timeframe[:-1])
  multipliers = {
    "m": 1,
    "h": 60,
    "d": 60 * 24,
    "w": 60 * 24 * 7,
  }
  if unit not in multipliers:
    raise ValueError(f"Unsupported timeframe: {timeframe}")
  return value * multipliers[unit]


def parse_timeframes(value: str) -> tuple[str, ...]:
  return tuple(item.strip() for item in value.split(",") if item.strip())


def build_merge_specs(
  btc_timeframes: tuple[str, ...],
  info_timeframes: tuple[str, ...],
  indicator_columns: int,
  btc_indicator_columns: int,
) -> list[MergeSpec]:
  specs = [
    MergeSpec(
      name=f"btc_{timeframe}",
      source="btc",
      timeframe=timeframe,
      indicator_columns=btc_indicator_columns,
    )
    for timeframe in btc_timeframes
  ]
  specs.extend(
    MergeSpec(
      name=f"informative_{timeframe}",
      source="pair",
      timeframe=timeframe,
      indicator_columns=indicator_columns,
    )
    for timeframe in info_timeframes
  )
  return specs


def import_runtime_dependencies() -> tuple[Any, Any]:
  try:
    import pandas as pd
    from freqtrade.strategy import merge_informative_pair
  except ModuleNotFoundError as exc:
    raise RuntimeError(
      "This benchmark needs pandas and freqtrade installed. Run it inside the Freqtrade environment "
      "or container used for backtesting/dry-run work."
    ) from exc
  return pd, merge_informative_pair


def informative_rows(base_rows: int, base_timeframe: str, informative_timeframe: str) -> int:
  base_minutes = timeframe_to_minutes(base_timeframe)
  informative_minutes = timeframe_to_minutes(informative_timeframe)
  return max(2, math.ceil((base_rows * base_minutes) / informative_minutes) + 2)


def build_synthetic_frame(
  pd: Any,
  rows: int,
  timeframe: str,
  indicator_columns: int,
  source: str,
) -> Any:
  minutes = timeframe_to_minutes(timeframe)
  data: dict[str, Any] = {
    "date": pd.date_range("2026-01-01", periods=rows, freq=f"{minutes}min"),
  }

  if source == "btc":
    for column in BASE_COLUMNS:
      data[f"btc_{column}"] = [1.0 + (index * 0.01) for index in range(rows)]
    indicator_prefix = "btc_indicator"
  else:
    for column in BASE_COLUMNS:
      data[column] = [1.0 + (index * 0.01) for index in range(rows)]
    indicator_prefix = "indicator"

  for index in range(indicator_columns):
    data[f"{indicator_prefix}_{index:02d}"] = [((row + index) % 100) / 100 for row in range(rows)]

  return pd.DataFrame(data)


def dataframe_memory_bytes(dataframe: Any) -> int:
  return int(dataframe.memory_usage(deep=True).sum())


def drop_columns_for_spec(spec: MergeSpec) -> list[str]:
  timeframe = spec.timeframe
  if spec.source == "btc":
    columns = [f"btc_{column}_{timeframe}" for column in ("date", *BASE_COLUMNS)]
  elif timeframe == "15m":
    columns = [f"{column}_{timeframe}" for column in ("date", "high", "low", "volume")]
  else:
    columns = [f"{column}_{timeframe}" for column in ("date", *BASE_COLUMNS)]

  columns.extend([f"date_{timeframe}", f"date_merge_{timeframe}"])
  return columns


def run_iteration(
  base_frame: Any,
  informative_frames: dict[str, Any],
  specs: list[MergeSpec],
  merge_informative_pair: Any,
  base_timeframe: str,
  drop_ohlcv: bool,
) -> list[dict[str, Any]]:
  dataframe = base_frame.copy(deep=True)
  results = []

  for spec in specs:
    before_columns = len(dataframe.columns)
    before_memory = dataframe_memory_bytes(dataframe)
    informative = informative_frames[spec.name].copy(deep=True)

    started_at = time.perf_counter()
    dataframe = merge_informative_pair(dataframe, informative, base_timeframe, spec.timeframe, ffill=True)
    if drop_ohlcv:
      dataframe.drop(columns=dataframe.columns.intersection(drop_columns_for_spec(spec)), inplace=True)
    elapsed = time.perf_counter() - started_at

    results.append(
      {
        "name": spec.name,
        "timeframe": spec.timeframe,
        "source": spec.source,
        "seconds": elapsed,
        "columns_before": before_columns,
        "columns_after": len(dataframe.columns),
        "memory_before_bytes": before_memory,
        "memory_after_bytes": dataframe_memory_bytes(dataframe),
      }
    )

  return results


def summarize_step(name: str, measurements: list[dict[str, Any]]) -> dict[str, Any]:
  seconds = [item["seconds"] for item in measurements]
  last = measurements[-1]
  return {
    "name": name,
    "source": last["source"],
    "timeframe": last["timeframe"],
    "mean_seconds": mean(seconds),
    "median_seconds": median(seconds),
    "min_seconds": min(seconds),
    "max_seconds": max(seconds),
    "columns_after": last["columns_after"],
    "memory_after_bytes": last["memory_after_bytes"],
  }


def summarize_runs(runs: list[list[dict[str, Any]]], specs: list[MergeSpec]) -> dict[str, Any]:
  totals = [sum(step["seconds"] for step in iteration) for iteration in runs]
  return {
    "total": {
      "mean_seconds": mean(totals),
      "median_seconds": median(totals),
      "min_seconds": min(totals),
      "max_seconds": max(totals),
    },
    "steps": [summarize_step(spec.name, [iteration[index] for iteration in runs]) for index, spec in enumerate(specs)],
  }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
  if args.rows <= 0:
    raise RuntimeError("--rows must be greater than 0.")
  if args.repeat <= 0:
    raise RuntimeError("--repeat must be greater than 0.")
  if args.indicator_columns < 0 or args.btc_indicator_columns < 0:
    raise RuntimeError("Indicator column counts must not be negative.")

  pd, merge_informative_pair = import_runtime_dependencies()
  specs = build_merge_specs(
    btc_timeframes=parse_timeframes(args.btc_timeframes),
    info_timeframes=parse_timeframes(args.informative_timeframes),
    indicator_columns=args.indicator_columns,
    btc_indicator_columns=args.btc_indicator_columns,
  )

  base_frame = build_synthetic_frame(pd, args.rows, args.base_timeframe, 0, "pair")
  informative_frames = {
    spec.name: build_synthetic_frame(
      pd,
      informative_rows(args.rows, args.base_timeframe, spec.timeframe),
      spec.timeframe,
      spec.indicator_columns,
      spec.source,
    )
    for spec in specs
  }
  runs = [
    run_iteration(
      base_frame=base_frame,
      informative_frames=informative_frames,
      specs=specs,
      merge_informative_pair=merge_informative_pair,
      base_timeframe=args.base_timeframe,
      drop_ohlcv=not args.no_drop_ohlcv,
    )
    for _ in range(args.repeat)
  ]
  summary = summarize_runs(runs, specs)

  return {
    "benchmark": "merge_informative_pair",
    "rows": args.rows,
    "repeat": args.repeat,
    "base_timeframe": args.base_timeframe,
    "drop_ohlcv": not args.no_drop_ohlcv,
    "specs": [asdict(spec) for spec in specs],
    "summary": summary,
  }


def bytes_to_mib(value: int) -> float:
  return value / 1024 / 1024


def format_text_report(report: dict[str, Any]) -> str:
  total = report["summary"]["total"]
  lines = [
    f"benchmark={report['benchmark']}",
    f"rows={report['rows']}",
    f"repeat={report['repeat']}",
    f"base_timeframe={report['base_timeframe']}",
    f"drop_ohlcv={report['drop_ohlcv']}",
    f"mean_total_seconds={total['mean_seconds']:.6f}",
    f"median_total_seconds={total['median_seconds']:.6f}",
    "",
    "step                         mean_s    median_s  columns_after  memory_after_mib",
  ]

  for step in report["summary"]["steps"]:
    lines.append(
      f"{step['name']:<28} "
      f"{step['mean_seconds']:>8.6f}  "
      f"{step['median_seconds']:>8.6f}  "
      f"{step['columns_after']:>13}  "
      f"{bytes_to_mib(step['memory_after_bytes']):>16.3f}"
    )

  return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Benchmark repeated Freqtrade merge_informative_pair calls with synthetic data."
  )
  parser.add_argument("--rows", type=int, default=1200, help="Rows in the base timeframe dataframe.")
  parser.add_argument("--repeat", type=int, default=5, help="Number of benchmark repetitions.")
  parser.add_argument("--base-timeframe", default="5m", help="Base dataframe timeframe.")
  parser.add_argument("--btc-timeframes", default=",".join(DEFAULT_BTC_TIMEFRAMES))
  parser.add_argument("--informative-timeframes", default=",".join(DEFAULT_INFO_TIMEFRAMES))
  parser.add_argument("--indicator-columns", type=int, default=24, help="Synthetic indicator columns per pair frame.")
  parser.add_argument(
    "--btc-indicator-columns", type=int, default=0, help="Synthetic indicator columns per BTC frame."
  )
  parser.add_argument("--no-drop-ohlcv", action="store_true", help="Keep merged OHLCV/date columns.")
  parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
  return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
  args = parse_args(argv)
  try:
    report = build_report(args)
  except RuntimeError as exc:
    print(str(exc), file=sys.stderr)
    return 2

  if args.json:
    print(json.dumps(report, indent=2, sort_keys=True))
  else:
    print(format_text_report(report))

  return 0


if __name__ == "__main__":
  sys.exit(main())
