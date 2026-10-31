"""Replay one published account in the pinned official Freqtrade image."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

from freqtrade.main import main
from tools.residual_profit_exit import exchange_replay


def digest(path):
  with path.open("rb") as stream:
    return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
  with path.open("x") as stream:
    json.dump(value, stream, indent=2, allow_nan=False)
    stream.write("\n")


def require(condition, message):
  if not condition:
    raise ValueError(message)


def order_signature(row):
  # JSON 39 and 39.0 denote the same quantity; retain exact numeric equality.
  return row["pair"], row["trade_open"], tuple(sorted(row["order"].items()))


def run(args):
  evidence_dir = Path(__file__).resolve().parents[2] / "docs/backtesting"
  evidence = json.loads((evidence_dir / "residual-profit-exit-validation.json").read_text())
  ledgers = json.loads((evidence_dir / evidence["ledger_file"]).read_text())
  year = args.account[-4:]
  inputs = evidence["inputs"][year]
  enabled = args.account.startswith("ON")
  source = args.strategy_dir / "NostalgiaForInfinityX8.py"
  source_hash = evidence["strategy_sha256"]["candidate" if enabled else "native"]
  require(digest(source) == source_hash, "Strategy does not match the published account")
  for item in inputs["data_sha256"]:
    require(digest(args.data_dir / item["path"]) == item["sha256"], f"Data drift: {item['path']}")

  args.output.mkdir(parents=True, exist_ok=False)
  userdir = args.output / "userdir"
  userdir.mkdir()
  config = dict(inputs["config"])
  if enabled:
    config["risk_residual_first_target_exit_enable"] = True
  save(args.output / "config.json", config)
  save(userdir / f"nfix8-profit_max-{config['bot_name']}-binance-USDT-(backtest).json", {})
  snapshot = args.output / "exchange_snapshot.json"
  with snapshot.open("x") as stream:
    stream.write(inputs["exchange_snapshot_json"])
  receipt = args.output / "replay_receipt.json"
  replay = exchange_replay.install(snapshot, inputs["exchange_snapshot_sha256"], receipt)
  start, end = (
    int(datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc).timestamp())
    for value in config["timerange"].split("-")
  )
  command = [
    "backtesting",
    "--config",
    str(args.output / "config.json"),
    "--strategy",
    "NostalgiaForInfinityX8",
    "--strategy-path",
    str(args.strategy_dir),
    "--datadir",
    str(args.data_dir),
    "--userdir",
    str(userdir),
    "--timerange",
    f"{start}-{end - 1}",
    "--cache",
    "none",
    "--export",
    "trades",
  ]
  save(args.output / "COMMAND.json", command)
  try:
    main(command)
  except SystemExit as exc:
    # The pinned CLI exits even on success; continue to the outcome checks.
    require(exc.code is None or exc.code == 0, f"Freqtrade failed: {exc.code}")
  finally:
    replay.finish()
  require(json.loads(receipt.read_text())["passed"], "Exchange replay did not complete")
  require(digest(source) == source_hash, "Strategy changed during execution")
  archives = list((userdir / "backtest_results").glob("*.zip"))
  require(len(archives) == 1, "Expected one official result archive")
  with zipfile.ZipFile(archives[0]) as archive:
    names = [
      name
      for name in archive.namelist()
      if name.endswith(".json") and not name.endswith(("_config.json", ".meta.json"))
    ]
    require(len(names) == 1, "Ambiguous result archive")
    result = json.loads(archive.read(names[0]))["strategy"]["NostalgiaForInfinityX8"]
  require(
    result["backtest_start_ts"] == start * 1000 and result["backtest_end_ts"] == (end - 300) * 1000,
    "Execution window drift",
  )
  reference = ledgers[args.account]
  fields = (
    "pair",
    "is_short",
    "open_date",
    "close_date",
    "enter_tag",
    "exit_reason",
    "trade_duration",
    "profit_abs",
    "profit_ratio",
  )

  def trade_signature(trade):
    return json.dumps(
      {key: float(trade[key]) if key in ("profit_abs", "profit_ratio") else trade[key] for key in fields},
      sort_keys=True,
    )

  require(
    Counter(map(trade_signature, result["trades"])) == Counter(map(trade_signature, reference["trades"])),
    "Published trade outcomes differ",
  )
  actual = [
    {"pair": trade["pair"], "trade_open": trade["open_timestamp"], "order": order}
    for trade in result["trades"]
    for order in trade["orders"]
  ]
  expected = [
    {"pair": row["pair"], "trade_open": row["trade_open"], "order": row["minified"]}
    for row in reference["actual_orders"]
  ]
  require(
    Counter(map(order_signature, actual)) == Counter(map(order_signature, expected)),
    "Published executed orders differ",
  )
  save(
    args.output / "VERIFIED.json",
    {
      "account": args.account,
      "trades": len(result["trades"]),
      "orders": len(actual),
      "published_trade_outcomes_and_orders_equal": True,
      "archive_sha256": digest(archives[0]),
      "strategy_sha256": source_hash,
    },
  )
  print(f"REPRODUCTION_VERIFIED {args.account}", flush=True)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument(
    "--account", required=True, choices=("Native2020", "ON2020", "Native2023", "ON2023", "Native2024", "ON2024")
  )
  parser.add_argument("--strategy-dir", required=True, type=Path)
  parser.add_argument("--data-dir", required=True, type=Path)
  parser.add_argument("--output", required=True, type=Path)
  run(parser.parse_args())
