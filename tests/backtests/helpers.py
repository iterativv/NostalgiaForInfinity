import json
import logging
import pprint
import shutil
import subprocess
import zipfile
from types import SimpleNamespace
import attr

from tests.conftest import REPO_ROOT

log = logging.getLogger(__name__)


@attr.s(frozen=True)
class ProcessResult:
  """
  This class serves the purpose of having a common result class which will hold the
  resulting data from a subprocess command.
  :keyword int exitcode:
      The exitcode returned by the process
  :keyword str stdout:
      The ``stdout`` returned by the process
  :keyword str stderr:
      The ``stderr`` returned by the process
  :keyword list,tuple cmdline:
      The command line used to start the process
  .. admonition:: Note
      Cast :py:class:`~saltfactories.utils.processes.ProcessResult` to a string to pretty-print it.
  """

  exitcode = attr.ib()
  stdout = attr.ib()
  stderr = attr.ib()
  cmdline = attr.ib(default=None, kw_only=True)

  @exitcode.validator
  def _validate_exitcode(self, attribute, value):
    if not isinstance(value, int):
      raise ValueError(f"'exitcode' needs to be an integer, not '{type(value)}'")

  def __str__(self):
    message = self.__class__.__name__
    if self.cmdline:
      message += f"\n Command Line: {self.cmdline}"
    if self.exitcode is not None:
      message += f"\n Exitcode: {self.exitcode}"
    if self.stdout or self.stderr:
      message += "\n Process Output:"
    if self.stdout:
      message += f"\n   >>>>> STDOUT >>>>>\n{self.stdout}\n   <<<<< STDOUT <<<<<"
    if self.stderr:
      message += f"\n   >>>>> STDERR >>>>>\n{self.stderr}\n   <<<<< STDERR <<<<<"
    return message + "\n"


class Backtest:
  def __init__(self, request, exchange=None, trading_mode=None):
    self.request = request
    self.exchange = exchange
    self.trading_mode = trading_mode

  def __call__(
    self,
    start_date,
    end_date,
    pairlist=None,
    exchange=None,
    trading_mode=None,
  ):
    if exchange is None:
      exchange = self.exchange
    if exchange is None:
      raise RuntimeError(f"No 'exchange' was passed when instantiating {self.__class__.__name__} or when calling it")

    tmp_path = self.request.getfixturevalue("tmp_path")

    # ---- Setup export directory and filename (per Freqtrade docs) ----
    export_dir = tmp_path / "backtest_results"
    export_dir.mkdir(parents=True, exist_ok=True)
    json_filename = f"backtest-result-{exchange}-{trading_mode}-{start_date}-{end_date}.json"

    exchange_config = f"configs/pairlist-backtest-static-{exchange}-{trading_mode}-usdt.json"

    # ---- Build cmdline ----
    cmdline = [
      "freqtrade",
      "backtesting",
      "--strategy=NostalgiaForInfinityX7",
      f"--timerange={start_date}-{end_date}",
      "--user-data-dir=user_data",
      "--config=configs/exampleconfig.json",
      "--config=configs/exampleconfig_secret.json",
      f"--config=configs/trading_mode-{trading_mode}.json",
      f"--config=configs/blacklist-{exchange}.json",
      "--breakdown=day",
      "--export=signals",
      f"--log-file=user_data/logs/backtesting-{exchange}-{trading_mode}-{start_date}-{end_date}.log",
      f"--export-directory={str(export_dir)}",
      f"--export-filename={json_filename}",
    ]

    if pairlist is None:
      cmdline.append(f"--config={exchange_config}")
    else:
      pairlist_config_file = tmp_path / "test-pairlist.json"
      pairlist_config_file.write_text(json.dumps({"exchange": {"name": exchange, "pair_whitelist": pairlist}}))
      cmdline.append(f"--config={pairlist_config_file}")

    if exchange == "binance":
      cmdline.append("--config=configs/proxy-binance.json")

    log.info("Running cmdline '%s' on '%s'", " ".join(cmdline), REPO_ROOT)
    proc = subprocess.run(cmdline, check=False, shell=False, cwd=REPO_ROOT, text=True, capture_output=True)
    ret = ProcessResult(
      exitcode=proc.returncode,
      stdout=proc.stdout.strip(),
      stderr=proc.stderr.strip(),
      cmdline=cmdline,
    )
    if ret.exitcode != 0:
      log.info("Command Result:\n%s", ret)
      raise RuntimeError(f"Backtest failed with exit code {ret.exitcode}!\n{ret}")
    else:
      log.debug("Command Result:\n%s", ret)

    # ---- Unzip any zip results ----
    for zip_path in export_dir.glob("backtest-result*.zip"):
      with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(export_dir)

    # ---- Helper to find backtest artifacts ----
    def find_file(pattern):
      files = [f for f in export_dir.rglob(pattern) if "_config" not in str(f) and "meta" not in str(f)]
      if not files:
        raise FileNotFoundError(f"No files found for pattern '{pattern}' in {export_dir}")
      return files[0]

    # ---- Collect artifacts ----
    json_results_file = find_file("backtest-result*.json")
    signals_file = find_file("backtest-result-*signals.pkl")
    exited_file = find_file("backtest-result-*exited.pkl")
    rejected_file = find_file("backtest-result-*rejected.pkl")

    # ---- Read JSON results ----
    raw_text = json_results_file.read_text()
    if not raw_text.strip():
      raise ValueError("Backtest result JSON file is empty.")
    results_data = json.loads(raw_text)

    # ---- Save artifacts to CI if requested ----
    if self.request.config.option.artifacts_path:
      artifacts_path = self.request.config.option.artifacts_path
      shutil.copyfile(json_results_file, artifacts_path / json_results_file.name)
      shutil.copyfile(signals_file, artifacts_path / signals_file.name)
      shutil.copyfile(exited_file, artifacts_path / exited_file.name)
      shutil.copyfile(rejected_file, artifacts_path / rejected_file.name)
      txt_path = artifacts_path / f"backtest-output-{exchange}-{trading_mode}-{start_date}-{end_date}.txt"
      txt_path.write_text(ret.stdout.strip())

    # ---- Return structured BacktestResults ----
    backtest_results = BacktestResults(
      stdout=ret.stdout.strip(),
      stderr=ret.stderr.strip(),
      raw_data=results_data,
    )

    # ---- Write CI JSON summary ----
    if self.request.config.option.artifacts_path:
      ci_json_path = artifacts_path / f"ci-results-{exchange}-{trading_mode}-{start_date}-{end_date}.json"
      summary = {f"{start_date}-{end_date}": backtest_results._stats_pct}
      ci_json_path.write_text(json.dumps(summary))

    backtest_results.log_info()
    return backtest_results


@attr.s(frozen=True)
class BacktestResults:
  stdout: str = attr.ib(repr=False)
  stderr: str = attr.ib(repr=False)
  raw_data: dict = attr.ib(repr=False)
  _results: dict = attr.ib(init=False, repr=False)
  _stats: dict = attr.ib(init=False, repr=False)
  results: SimpleNamespace = attr.ib(init=False, repr=False)
  full_stats: SimpleNamespace = attr.ib(init=False, repr=False)
  _stats_pct: dict = attr.ib(init=False, repr=False)
  stats_pct: SimpleNamespace = attr.ib(init=False, repr=True)

  @_results.default
  def _set_results(self):
    strategy_data = self.raw_data.get("strategy")

    if isinstance(strategy_data, dict):
      # Expected structure: {"strategy": {"NostalgiaForInfinityX7": {...}}}
      return strategy_data.get("NostalgiaForInfinityX7")

    elif isinstance(strategy_data, str) and strategy_data == "NostalgiaForInfinityX7":
      # Fallback structure: {"strategy": "NostalgiaForInfinityX7"}
      # Then use the top-level key instead
      return self.raw_data.get("NostalgiaForInfinityX7")

    else:
      raise TypeError(f"Unsupported 'strategy' value: {strategy_data!r}. Expected a dict or strategy name.")

  @_stats.default
  def _set_stats(self):
    comparison_data = self.raw_data.get("strategy_comparison")

    if isinstance(comparison_data, list) and len(comparison_data) > 0:
      return comparison_data[0]

    elif isinstance(comparison_data, dict):
      return comparison_data

    else:
      raise TypeError(f"Unsupported 'strategy_comparison' value: {comparison_data!r}. Expected a list or dict.")

  @results.default
  def _set_results(self):
    return json.loads(json.dumps(self._results), object_hook=lambda d: SimpleNamespace(**d))

  @full_stats.default
  def _set_full_stats(self):
    return json.loads(json.dumps(self._stats), object_hook=lambda d: SimpleNamespace(**d))

  @_stats_pct.default
  def _set__stats_pct(self):
    return {
      "duration_avg": self.full_stats.duration_avg,
      "profit_mean_pct": self.full_stats.profit_mean_pct,
      "profit_total_pct": self.full_stats.profit_total_pct,
      "max_drawdown": self.results.max_drawdown_account * 100,
      "trades": self.full_stats.trades,
      "market_change": round(self.results.market_change * 100, 2),
      "winrate": round(self.full_stats.wins * 100.0 / self.full_stats.trades, 2) if self.full_stats.trades > 0 else 0,
    }

  @stats_pct.default
  def _set_stats_pct(self):
    return json.loads(json.dumps(self._stats_pct), object_hook=lambda d: SimpleNamespace(**d))

  def log_info(self):
    data = {
      "results": self._results,
      "full_stats": self._stats,
      "stats_pct": self._stats_pct,
    }
    log.debug("Backtest results:\n%s", pprint.pformat(data))
    log.info(
      "Backtests Stats PCTs(More info at the DEBUG log level): %s",
      pprint.pformat(self._stats_pct),
    )


@attr.s(frozen=True)
class Timerange:
  start_date = attr.ib()
  end_date = attr.ib()


@attr.s(frozen=True)
class Exchange:
  name = attr.ib()
  winrate = attr.ib()
  max_drawdown = attr.ib()
