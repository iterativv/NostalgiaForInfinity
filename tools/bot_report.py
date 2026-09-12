#!/usr/bin/env python3
"""Generate a redacted JSON report from a running freqtrade instance.

The report exports the available information from a freqtrade instance (config,
open/closed trades, performance, pair lists, locks, plot config, system info)
into a single JSON file, so strategy developers can review how a strategy is
behaving in production and adjust it, similar to telemetry.

Everything is collected over the freqtrade REST API with read-only GET requests.
Confidential information is redacted by default (every redacted field is replaced
by "<redacted>"; the full field reference is tools/bot_report.md):

- credentials and keys (exchange keys/secrets, API passwords, tokens, chat ids,
  ccxt configs)
- anything that can reveal the account balance: absolute PnL, stake amounts,
  trade amounts/costs, wallet/capital values, funding fees, drawdown high/low
  water marks, stoploss distances that encode money on some freqtrade versions,
  the /balance endpoint itself
- account and exchange order identifiers
- information that can identify a specific person (bot names, local paths)

Redaction of numbers is fail-closed: a number is kept only when its key is
recognized as safe (prices, ratios/percentages, counts, durations, timestamps,
precision values, or values under the config/system_info/plot_config sections).
Any numeric field freqtrade adds in the future is redacted until allow-listed.

Redacted absolute values are complemented by derived, scale-invariant relative
fields (formulas in tools/bot_report.md):

- stake_amount_to_account_balance_ratio      position size vs the account at entry
- profit_to_account_balance_ratio            per-trade impact on the account
- funding_fees_to_stake_amount_ratio         funding cost drag per position
- funding_fee_to_order_cost_ratio            effective funding rate paid on an order fill
- order_filled_share_of_trade_side           entry/exit (DCA / safety order) distribution
- total_stake_to_account_balance_ratio       share of the account currently deployed
- trading_volume_to_account_balance_ratio    turnover intensity over the bot's lifetime

Why the balance still cannot be derived: every kept number is a market price, a
ratio between two internal quantities, a count, or a timestamp - the report
contains no absolute currency value that could serve as a scale anchor. A ratio
would only become sensitive if combined with such an anchor, which is exactly
what the redaction removes (the generator is audited by inventorying every
numeric field of the output and by testing known derivation chains, e.g.
stoploss_entry_dist / stoploss_entry_dist_ratio).

Kept as-is on purpose: stop_loss_abs / initial_stop_loss_abs are market price
levels (not money), trade_id is a local counter, the config value
stake_amount="unlimited" is behavior and not a size, fee_open/fee_close are
rates, and timestamps/prices are market data.

Closed trades are exported in full by paginating /trades; --trades-limit only
acts as a safety cap. Use --no-redact to export an unredacted report for private
diagnostics; never share that file.

Examples:
  python tools/bot_report.py --url http://127.0.0.1:8080 \\
      --username freqtrader --password secret -o report.json
  FREQTRADE_API_URL=http://bot:8080 python tools/bot_report.py
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API_PREFIX = "/api/v1"
TRADES_PAGE_SIZE = 500
TOOL_VERSION = "1.3.0"
REDACTED = "<redacted>"

# Keys that are always redacted regardless of their value.
WHOLE_KEY_REDACT = {
  "bot_name",
  "ccxt_async_config",
  "ccxt_config",
  "db_url",
  "exportfilename",
  "log_configfile",
  "logfile",
  "open_order",
  "open_orders",
  "strategy_path",
  "uid",
  "user_data_dir",
}

# Key tokens (key split on non-alphanumerics) that mark credentials / personal data.
SECRET_TOKENS = {
  "chat",
  "credential",
  "key",
  "passwd",
  "password",
  "secret",
  "token",
  "webhook",
}

# A key is treated as an identifier when it has an "id" token plus one of these.
# Local counters (trade_id, id) stay, exchange/account identifiers do not.
ID_CONTEXT_TOKENS = {
  "account",
  "client",
  "order",
  "telegram",
  "user",
}

# Keys whose values can reveal the account balance / absolute PnL.
MONEY_EXACT_KEYS = {
  "abs_profit",
  "amount",
  "amount_requested",
  "available_capital",
  "cost",
  "current_drawdown_high",
  "current_drawdown_low",
  "drawdown_high",
  "drawdown_low",
  "dry_run_wallet",
  "expectancy",
  "fiat_value",
  "filled",
  "funding_fee",
  "funding_fees",
  "ft_fee_base",
  "max_stake_amount",
  "open_trade_value",
  "profit_all_coin",
  "profit_all_fiat",
  "profit_closed_coin",
  "profit_closed_fiat",
  "realized_profit",
  "remaining",
  "safe_cost",
  "stake_amount",
  "starting_balance",
  "total_capital",
  "total_stake",
  "trading_volume",
}

MONEY_KEY_SUFFIXES = (
  "_abs",
  "_balance",
  "_coin",
  "_cost",
  "_dist",
  "_fee",
  "_fiat",
  "_stake_amount",
  "_wallet",
)
# Absolute price levels, not money: stop_loss_abs describes the market, not the account.
MONEY_SUFFIX_EXCEPTIONS = {"initial_stop_loss_abs", "stop_loss_abs"}
# Money-like keys where a string value is behavior (e.g. "unlimited"), not an amount.
MONEY_ONLY_NUMERIC_KEYS = {"dry_run_wallet", "max_stake_amount", "stake_amount"}

# Fail-closed numeric redaction: report sections whose numbers are safe as a whole
# (strategy parameters, hardware stats, indicator plot definitions), checked after
# the deny rules above.
NUMBER_SAFE_SECTIONS = {"config", "system_info", "plot_config"}

# Key tokens that mark numbers safe to keep (ratios, market prices, counts,
# durations, timestamps, precisions). The deny rules always take precedence.
ALLOWED_NUMBER_TOKENS = {
  "average",
  "count",
  "current",
  "decimals",
  "duration",
  "interval",
  "length",
  "max",
  "offset",
  "pct",
  "percent",
  "precision",
  "price",
  "rate",
  "ratio",
  "share",
  "timestamp",
  "total",
  "ts",
  "version",
}

# Individual numeric keys that are safe but carry none of the tokens above.
ALLOWED_NUMBER_KEYS = {
  "close_profit",
  "contract_size",
  "cagr",
  "calmar",
  "fee_close",
  "fee_open",
  "initial_stop_loss_abs",
  "leverage",
  "losing_trades",
  "max_drawdown",
  "current_drawdown",
  "nr_of_successful_entries",
  "nr_of_successful_exits",
  "profit",
  "profit_factor",
  "rel_profit",
  "sharpe",
  "sortino",
  "sqn",
  "stop_loss_abs",
  "timeframe",
  "winrate",
  "winning_trades",
}

# History windows for daily/weekly/monthly, sized from the first trade date.
MAX_DAILY_DAYS = 3650
MAX_WEEKLY_WEEKS = 520
MAX_MONTHLY_MONTHS = 240


class ApiError(Exception):
  """A freqtrade API endpoint answered with an unexpected HTTP status."""

  def __init__(self, endpoint: str, status: int) -> None:
    super().__init__(f"{endpoint} failed with HTTP {status}")
    self.endpoint = endpoint
    self.status = status


def key_tokens(key: str) -> list[str]:
  return [part for part in re.split(r"[^a-z0-9]+", key.lower()) if part]


def is_sensitive(key: str, value) -> bool:
  lowered = key.lower()
  parts = key_tokens(key)
  if not parts or lowered in MONEY_SUFFIX_EXCEPTIONS:
    return False
  if lowered in WHOLE_KEY_REDACT:
    return True
  if SECRET_TOKENS.intersection(parts):
    return True
  if "id" in parts and ID_CONTEXT_TOKENS.intersection(parts):
    return True
  # Ratios/percentages are never account balance, even when they mention money words.
  if "ratio" in parts or parts[-1] in {"pct", "percent"}:
    return False
  if lowered in MONEY_EXACT_KEYS or lowered.endswith(MONEY_KEY_SUFFIXES):
    if lowered in MONEY_ONLY_NUMERIC_KEYS:
      return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True
  return False


def is_allowed_number(path: str, key: str) -> bool:
  """Whether a numeric value may be kept (fail-closed: unknown keys are redacted)."""
  if path.split(".", 1)[0] in NUMBER_SAFE_SECTIONS:
    return True
  if ALLOWED_NUMBER_TOKENS.intersection(key_tokens(key)):
    return True
  if key in ALLOWED_NUMBER_KEYS or key.endswith("_id") or key == "id":
    return True
  return False


class Redactor:
  """Recursively redacts sensitive fields while keeping the JSON structure intact."""

  def __init__(self, enabled: bool = True) -> None:
    self.enabled = enabled
    self.redacted_fields = 0

  def walk(self, obj, key: str = "", path: str = ""):
    if not self.enabled:
      return obj
    full_path = f"{path}.{key}" if path and key else (key or path)
    if key and is_sensitive(key, obj):
      self.redacted_fields += 1
      return REDACTED
    if isinstance(obj, bool):
      return obj
    if isinstance(obj, (int, float)) and key and not is_allowed_number(full_path, key):
      self.redacted_fields += 1
      return REDACTED
    if isinstance(obj, dict):
      return {name: self.walk(value, str(name), full_path) for name, value in obj.items()}
    if isinstance(obj, list):
      return [self.walk(item, key, full_path) for item in obj]
    return obj


class FreqtradeApi:
  """Minimal read-only client for the freqtrade REST API (stdlib only)."""

  def __init__(
    self, base_url: str, username: str | None, password: str | None, timeout: float, verify_tls: bool
  ) -> None:
    self.base_url = base_url.rstrip("/")
    self.timeout = timeout
    self.auth = None
    if username is not None or password is not None:
      raw = f"{username or ''}:{password or ''}".encode()
      self.auth = "Basic " + base64.b64encode(raw).decode()
    self.ssl_context = None
    if base_url.startswith("https") and not verify_tls:
      self.ssl_context = ssl.create_default_context()
      self.ssl_context.check_hostname = False
      self.ssl_context.verify_mode = ssl.CERT_NONE

  def get(self, endpoint: str, params: dict | None = None):
    url = f"{self.base_url}{API_PREFIX}/{endpoint}"
    if params:
      url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    if self.auth:
      request.add_header("Authorization", self.auth)
    try:
      with urllib.request.urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
        return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
      if err.code == 401:
        raise SystemExit(f"Authentication failed for {self.base_url}: check --username/--password.") from err
      raise ApiError(endpoint, err.code) from err
    except urllib.error.URLError as err:
      raise SystemExit(f"Cannot reach freqtrade API at {self.base_url}: {err.reason}") from err


def _safe_div(numerator, denominator):
  if numerator is None or denominator is None or denominator == 0:
    return None
  try:
    return round(numerator / denominator, 6)
  except TypeError:
    return None


def _balance_lookup(daily_rows):
  """Build a day -> starting-balance lookup from /daily rows (None if unavailable)."""
  mapping = {}
  for row in daily_rows or []:
    day, balance = row.get("date"), row.get("starting_balance")
    if day and isinstance(balance, (int, float)):
      mapping[str(day)[:10]] = balance
  if not mapping:
    return None
  days = sorted(mapping)

  def lookup(date_str):
    day = str(date_str)[:10]
    if day in mapping:
      return mapping[day]
    if day < days[0]:
      return mapping[days[0]]
    for known in reversed(days):
      if known < day:
        return mapping[known]
    return mapping[days[0]]

  return lookup


def _is_entry_order(order: dict, is_short: bool) -> bool:
  if "ft_is_entry" in order:
    return bool(order.get("ft_is_entry"))
  return (order.get("ft_order_side") == "buy") != bool(is_short)


def add_derived_fields(raw: dict) -> None:
  """Add scale-invariant relative values next to fields that will be redacted.

  Formulas are documented in tools/bot_report.md; this runs before the redactor,
  so derived keys must never match the redaction rules (all of them carry a
  "ratio" or "share" token).
  """
  lookup = _balance_lookup((raw.get("daily_performance") or {}).get("data"))
  balance_now = lookup(datetime.now(timezone.utc)) if lookup else None

  trade_counts = raw.get("trade_counts")
  if isinstance(trade_counts, dict):
    trade_counts["total_stake_to_account_balance_ratio"] = _safe_div(trade_counts.get("total_stake"), balance_now)

  profit_summary = raw.get("profit_summary")
  if isinstance(profit_summary, dict):
    profit_summary["trading_volume_to_account_balance_ratio"] = _safe_div(
      profit_summary.get("trading_volume"), balance_now
    )

  trades = list(raw.get("open_trades") or [])
  trades += list((raw.get("closed_trades") or {}).get("trades") or [])
  for trade in trades:
    if not isinstance(trade, dict):
      continue
    stake = trade.get("stake_amount")
    balance_at_open = lookup(trade.get("open_date")) if lookup else None
    trade["stake_amount_to_account_balance_ratio"] = _safe_div(stake, balance_at_open)
    if trade.get("close_date"):
      abs_profit, balance_at_close = trade.get("close_profit_abs"), lookup(trade["close_date"])
    else:
      abs_profit, balance_at_close = trade.get("profit_abs"), balance_now
    trade["profit_to_account_balance_ratio"] = _safe_div(abs_profit, balance_at_close)
    trade["funding_fees_to_stake_amount_ratio"] = _safe_div(trade.get("funding_fees"), stake)

    is_short = bool(trade.get("is_short"))
    orders = [order for order in (trade.get("orders") or []) if isinstance(order, dict)]
    filled_by_side = {True: 0.0, False: 0.0}
    for order in orders:
      filled = order.get("filled")
      if isinstance(filled, (int, float)) and filled > 0:
        filled_by_side[_is_entry_order(order, is_short)] += filled
    for order in orders:
      order["funding_fee_to_order_cost_ratio"] = _safe_div(order.get("funding_fee"), order.get("cost"))
      side_filled = filled_by_side[_is_entry_order(order, is_short)]
      order["order_filled_share_of_trade_side"] = _safe_div(order.get("filled"), side_filled or None)


def _history_days(first_trade_date) -> int:
  """Days since the first trade, for full-history daily/weekly/monthly windows."""
  try:
    start = datetime.strptime(str(first_trade_date)[:10], "%Y-%m-%d").date()
    return min(max((datetime.now(timezone.utc).date() - start).days + 2, 8), MAX_DAILY_DAYS)
  except ValueError:
    return 8


def fetch_trade_history(api: FreqtradeApi, cap: int | None, failed: list[dict]) -> dict:
  """Fetch the full closed-trade history by paginating /trades with offset."""
  trades: list = []
  seen: set = set()
  offset, total = 0, None
  while cap is None or len(trades) < cap:
    try:
      page = api.get("trades", {"limit": TRADES_PAGE_SIZE, "offset": offset})
    except ApiError as err:
      failed.append({"endpoint": "trades", "http_status": err.status})
      print(f"warning: trades failed with HTTP {err.status}", file=sys.stderr)
      break
    batch = page.get("trades") or []
    fresh = [trade for trade in batch if isinstance(trade, dict) and trade.get("trade_id") not in seen]
    seen.update(trade.get("trade_id") for trade in fresh)
    trades.extend(fresh)
    total = page.get("total_trades", total)
    offset += len(batch)
    if not batch or (total is not None and offset >= total):
      break
  if cap is not None:
    trades = trades[:cap]
  trades.sort(key=lambda trade: trade.get("trade_id") or 0)
  return {"trades": trades, "trades_count": len(trades), "total_trades": total or len(trades)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Export a redacted JSON report from a freqtrade REST API instance.",
  )
  parser.add_argument(
    "--url",
    default=os.environ.get("FREQTRADE_API_URL"),
    help="Base URL of the freqtrade REST API (default: %(default)s, env: FREQTRADE_API_URL).",
  )
  parser.add_argument(
    "--username",
    default=os.environ.get("FREQTRADE_API_USERNAME"),
    help="API username (env: FREQTRADE_API_USERNAME or FREQTRADE__API_SERVER__USERNAME).",
  )
  parser.add_argument(
    "--password",
    default=os.environ.get("FREQTRADE_API_PASSWORD"),
    help="API password (env: FREQTRADE_API_PASSWORD or FREQTRADE__API_SERVER__PASSWORD).",
  )
  parser.add_argument(
    "-o",
    "--output",
    default=None,
    help="Output JSON file (default: bot-report-<timestamp>.json).",
  )
  parser.add_argument(
    "--trades-limit",
    type=int,
    default=None,
    help="Safety cap on exported closed trades (default: full history, paginated).",
  )
  parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds.")
  parser.add_argument(
    "--redact",
    action=argparse.BooleanOptionalAction,
    default=True,
    help="Redact confidential information (default: enabled). Use --no-redact to include "
    "balances/absolute values for private diagnostics; never share that output.",
  )
  parser.add_argument("--no-verify-tls", action="store_true", help="Skip TLS certificate verification.")
  args = parser.parse_args(argv)
  args.url = args.url or "http://127.0.0.1:8080"
  args.username = args.username or os.environ.get("FREQTRADE__API_SERVER__USERNAME")
  args.password = args.password or os.environ.get("FREQTRADE__API_SERVER__PASSWORD")
  return args


def collect_report(api: FreqtradeApi, redactor: Redactor, trades_limit: int | None) -> dict:
  raw: dict = {}
  failed: list[dict] = []

  def fetch(section: str, endpoint: str, params: dict | None = None):
    try:
      data = api.get(endpoint, params)
    except ApiError as err:
      failed.append({"endpoint": endpoint, "http_status": err.status})
      print(f"warning: {endpoint} failed with HTTP {err.status}", file=sys.stderr)
      return None
    raw[section] = data
    return data

  api.get("ping")
  version = fetch("freqtrade_version", "version")
  fetch("config", "show_config")
  fetch("health", "health")
  fetch("system_info", "sysinfo")
  fetch("open_trades", "status")
  fetch("trade_counts", "count")
  fetch("profit_summary", "profit")
  fetch("performance_per_pair", "performance")
  days = _history_days((raw.get("profit_summary") or {}).get("first_trade_date"))
  fetch("daily_performance", "daily", {"timescale": days})
  fetch("weekly_performance", "weekly", {"timescale": min(days // 7 + 2, MAX_WEEKLY_WEEKS)})
  fetch("monthly_performance", "monthly", {"timescale": min(days // 30 + 2, MAX_MONTHLY_MONTHS)})
  raw["closed_trades"] = fetch_trade_history(api, trades_limit, failed)
  fetch("whitelist", "whitelist")
  fetch("blacklist", "blacklist")
  fetch("pair_locks", "locks")
  fetch("plot_config", "plot_config")
  if not redactor.enabled:
    fetch("balance", "balance")

  add_derived_fields(raw)
  report = {section: redactor.walk(data) for section, data in raw.items()}

  metadata = {
    "tool": "tools/bot_report.py",
    "tool_version": TOOL_VERSION,
    "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "freqtrade_version": (version or {}).get("version"),
    "redacted": redactor.enabled,
    "redacted_field_count": redactor.redacted_fields,
    "skipped_endpoints": ["balance", "logs"] if redactor.enabled else [],
    "failed_endpoints": failed,
  }
  return {"report_metadata": metadata, **report}


def main(argv: list[str] | None = None) -> int:
  args = parse_args(argv)
  redactor = Redactor(enabled=args.redact)
  if not args.redact:
    print("warning: redaction disabled - the report will contain confidential data, do not share it.", file=sys.stderr)

  api = FreqtradeApi(args.url, args.username, args.password, args.timeout, not args.no_verify_tls)
  report = collect_report(api, redactor, args.trades_limit)

  output = args.output or "bot-report-{}.json".format(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
  with open(output, "w", encoding="utf-8") as file:
    json.dump(report, file, indent=2, ensure_ascii=False)
    file.write("\n")

  failed = len(report["report_metadata"]["failed_endpoints"])
  print(
    f"Report written to {output} ({redactor.redacted_fields} fields redacted, "
    f"{report['closed_trades']['trades_count']} closed trades, {failed} endpoints failed)"
  )
  return 0


if __name__ == "__main__":
  sys.exit(main())
