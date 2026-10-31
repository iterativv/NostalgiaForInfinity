"""Replay recorded Native exchange inputs inside the pinned backtest runtime."""

import copy
import hashlib
import inspect
import json
import math
from pathlib import Path

type JSON = dict[str, JSON] | list[JSON] | str | int | float | bool | None

ROOT_FIELDS = {"precision_mode", "precision_mode_price", "markets", "leverage_tiers"}
MARKET_FIELDS = {
  "symbol",
  "base",
  "quote",
  "settle",
  "type",
  "active",
  "contractSize",
  "linear",
  "inverse",
  "precision",
  "limits",
}
PRECISION_FIELDS = {"amount", "price", "cost", "base", "quote"}
LIMIT_FIELDS = {"leverage", "amount", "price", "cost", "market"}
TIER_FIELDS = {
  "minNotional",
  "maxNotional",
  "maintenanceMarginRate",
  "maxLeverage",
  "maintAmt",
}


class ReplayError(ValueError):
  """The recorded inputs cannot safely be replayed in this process."""


def _require(condition, message):
  if not condition:
    raise ReplayError(message)


def _object(pairs):
  result = {}
  for key, value in pairs:
    _require(key not in result, f"Duplicate snapshot key: {key}")
    result[key] = value
  return result


def _keys(value: JSON, expected: set[str], label: str) -> dict[str, JSON]:
  if not isinstance(value, dict) or set(value) != expected:
    raise ReplayError(f"Unexpected {label} schema")
  return value


def _number(value, label, nullable=True):
  _require(
    (nullable and value is None) or (type(value) in (int, float) and math.isfinite(value) and value >= 0),
    f"Invalid numeric field: {label}",
  )


def _validate_snapshot(snapshot):
  snapshot = _keys(snapshot, ROOT_FIELDS, "root")
  for field in ("precision_mode", "precision_mode_price"):
    _require(type(snapshot[field]) is int and snapshot[field] in (2, 3, 4), field)
  markets = snapshot["markets"]
  if not isinstance(markets, dict) or not markets:
    raise ReplayError("Empty or invalid markets")
  recorded_tiers = snapshot["leverage_tiers"]
  if not isinstance(recorded_tiers, dict):
    raise ReplayError("Invalid leverage tiers")
  _require(
    list(recorded_tiers) == list(markets),
    "Market and tier whitelist/order mismatch",
  )
  for pair, raw_market in markets.items():
    market = _keys(raw_market, MARKET_FIELDS, f"market {pair}")
    _require(market["symbol"] == pair, f"Market symbol mismatch: {pair}")
    for field in ("symbol", "base", "quote", "settle"):
      _require(type(market[field]) is str and bool(market[field]), f"Invalid {field}")
    _require(market["type"] == "swap", "Only futures swap snapshots are supported")
    for field in ("active", "linear", "inverse"):
      _require(type(market[field]) is bool, f"Invalid {field}")
    _number(market["contractSize"], "contractSize", nullable=False)
    precision = _keys(market["precision"], PRECISION_FIELDS, "precision")
    for field, value in precision.items():
      _number(value, f"precision.{field}")
    recorded_limits = _keys(market["limits"], LIMIT_FIELDS, "limits")
    for field, raw_limits in recorded_limits.items():
      limits = _keys(raw_limits, {"min", "max"}, f"limits.{field}")
      for bound, value in limits.items():
        _number(value, f"limits.{field}.{bound}")
    tiers = recorded_tiers[pair]
    if not isinstance(tiers, list) or not tiers:
      raise ReplayError(f"Missing parsed tiers: {pair}")
    for raw_tier in tiers:
      tier = _keys(raw_tier, TIER_FIELDS, f"parsed tier {pair}")
      for field, value in tier.items():
        _number(value, field, nullable=field in ("maxNotional", "maintAmt"))


def _runtime_sources(contract):
  import ccxt
  import freqtrade
  from freqtrade.exchange.binance import Binance
  from freqtrade.exchange.exchange import Exchange
  from freqtrade.optimize.backtesting import Backtesting

  _require(freqtrade.__version__ == contract["freqtrade"], "Freqtrade version mismatch")
  _require(ccxt.__version__ == contract["ccxt"], "CCXT version mismatch")
  sources = {}
  for name, target in (
    ("exchange", Exchange),
    ("backtesting", Backtesting),
    ("binance", Binance),
  ):
    path = Path(inspect.getfile(target))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _require(digest == contract["sources"][name]["sha256"], f"Runtime source mismatch: {name}")
    sources[name] = {"path": str(path), "sha256": digest}
  _require(Binance.reload_markets is Exchange.reload_markets, "Unsupported reload override")
  _require(Binance.fill_leverage_tiers is Exchange.fill_leverage_tiers, "Unsupported tier override")
  for name in ("reload_markets", "fill_leverage_tiers"):
    method = getattr(Exchange, name)
    _require(
      inspect.isfunction(method)
      and method.__qualname__ == f"Exchange.{name}"
      and inspect.getfile(method) == inspect.getfile(Exchange),
      f"Unsupported Exchange method override: {name}",
    )
  return sources


class ReplayState:
  def __init__(self, snapshot, digest, receipt_path, runtime_sources):
    self._snapshot = copy.deepcopy(snapshot)
    self.snapshot_sha256 = digest
    self.receipt_path = Path(receipt_path)
    self.runtime_sources = runtime_sources
    self.market_applications = 0
    self.tier_applications = 0
    self.market_differences = []
    self.errors = []
    self._finished = False

  def _guard(self, exchange, reload_hook, tier_hook, require_markets=False):
    from freqtrade.enums import RunMode, TradingMode
    from freqtrade.exchange.binance import Binance

    _require(type(exchange) is Binance, "Only the official Binance exchange is supported")
    _require(
      getattr(exchange.reload_markets, "__func__", None) is reload_hook
      and getattr(exchange.fill_leverage_tiers, "__func__", None) is tier_hook,
      "Unsupported exchange method override",
    )
    config = exchange._config
    _require(config.get("runmode") is RunMode.BACKTEST, "Replay requires BACKTEST mode")
    _require(config.get("dry_run") is True, "Replay requires dry_run=True")
    _require(exchange.trading_mode == TradingMode.FUTURES, "Replay requires futures mode")
    _require(config["exchange"].get("name") == "binance", "Unsupported exchange name")
    _require(
      config["exchange"].get("pair_whitelist") == list(self._snapshot["markets"]),
      "Configured whitelist/order mismatch",
    )
    _require(
      exchange.precisionMode == self._snapshot["precision_mode"]
      and exchange.precision_mode_price == self._snapshot["precision_mode_price"]
      and exchange._api_async.precisionMode == self._snapshot["precision_mode"],
      "Precision mode mismatch",
    )
    if require_markets:
      _require(
        isinstance(exchange._api_async.markets, dict)
        and all(pair in exchange._api_async.markets for pair in self._snapshot["markets"]),
        "Missing selected market in loaded async markets",
      )

  def _restore(self, current, recorded, pair, prefix=""):
    for field, value in recorded.items():
      path = f"{prefix}.{field}" if prefix else field
      present = field in current
      before = current.get(field)
      if isinstance(value, dict):
        _require(isinstance(before, dict), f"Missing recorded market structure: {pair}.{path}")
        self._restore(before, value, pair, path)
      elif not present or before != value or type(before) is not type(value):
        self.market_differences.append(
          {
            "application": self.market_applications + 1,
            "pair": pair,
            "field": path,
            "before_present": present,
            "before": copy.deepcopy(before),
            "after": copy.deepcopy(value),
          }
        )
        current[field] = copy.deepcopy(value)

  def finish(self) -> None:
    """Exclusively write the receipt once; no success without both hooks executing."""
    if self._finished:
      return
    receipt = {
      "passed": bool(self.market_applications and self.tier_applications and not self.errors),
      "snapshot_sha256": self.snapshot_sha256,
      "market_applications": self.market_applications,
      "tier_applications": self.tier_applications,
      "market_differences": self.market_differences,
      "runtime_sources": self.runtime_sources,
      "errors": self.errors,
    }
    with self.receipt_path.open("x", encoding="utf-8") as handle:
      json.dump(receipt, handle, indent=2, allow_nan=False)
      handle.write("\n")
    self._finished = True


def install(snapshot_path: Path | str, expected_sha256: str, receipt_path: Path | str) -> ReplayState:
  """Install input-only replay and return its atexit-compatible receipt state."""
  raw = Path(snapshot_path).read_bytes()
  digest = hashlib.sha256(raw).hexdigest()
  _require(digest == expected_sha256, "Snapshot SHA256 mismatch")
  snapshot = json.loads(raw, object_pairs_hook=_object)
  _validate_snapshot(snapshot)
  contract = json.loads(Path(__file__).with_name("REPLAY_RUNTIME_CONTRACT.json").read_text())
  _require(set(contract["market_fields"]) == MARKET_FIELDS, "Runtime market field contract mismatch")
  sources = _runtime_sources(contract)
  _require(not Path(receipt_path).exists(), "Replay receipt already exists")

  from freqtrade.exchange.exchange import Exchange

  original_reload = Exchange.reload_markets
  state = ReplayState(snapshot, digest, receipt_path, sources)

  def reload_markets(exchange, force=False, *, load_leverage_tiers=True):
    try:
      state._guard(exchange, reload_markets, fill_leverage_tiers)
      original_reload(exchange, force, load_leverage_tiers=load_leverage_tiers)
      state._guard(exchange, reload_markets, fill_leverage_tiers, require_markets=True)
      for pair, recorded in state._snapshot["markets"].items():
        market = exchange._api_async.markets[pair]
        state._restore(market, recorded, pair)
        id_markets = exchange._api_async.markets_by_id.get(market["id"], [])
        selected = [item for item in id_markets if item.get("symbol") == pair]
        _require(len(selected) == 1, f"Missing or ambiguous selected market ID: {pair}")
        # CCXT's symbol map is enriched separately from its raw ID map.
        # Synchronizing clients alone does not refresh the ID map's values.
        state._restore(selected[0], recorded, pair, prefix="by_id")
      exchange._api.set_markets_from_exchange(exchange._api_async)
      exchange._markets = exchange._api_async.markets
      state.market_applications += 1
    except Exception as exc:
      state.errors.append(f"{type(exc).__name__}: {exc}")
      raise

  def fill_leverage_tiers(exchange):
    try:
      state._guard(exchange, reload_markets, fill_leverage_tiers, require_markets=True)
      for pair, tiers in state._snapshot["leverage_tiers"].items():
        exchange._leverage_tiers[pair] = copy.deepcopy(tiers)
      state.tier_applications += 1
    except Exception as exc:
      state.errors.append(f"{type(exc).__name__}: {exc}")
      raise

  Exchange.reload_markets = reload_markets
  Exchange.fill_leverage_tiers = fill_leverage_tiers
  return state
