import json
import logging
import pprint
import shutil
import subprocess
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
    def __init__(self, request, exchange=None):
        self.request = request
        self.exchange = exchange

    def __call__(
        self,
        start_date,
        end_date,
        pairlist=None,
        max_open_trades=5,
        stake_amount="unlimited",
        exchange=None,
    ):
        if exchange is None:
            exchange = self.exchange
        if exchange is None:
            raise RuntimeError(
                f"No 'exchange' was passed when instantiating {self.__class__.__name__} or when calling it"
            )
        tmp_path = self.request.getfixturevalue("tmp_path")
        exchange_config = f"user_data/data/{exchange}-usdt-static.json"
        json_results_file = tmp_path / "backtest-results.json"
        cmdline = [
            "freqtrade",
            "backtesting",
            f"--user-data=user_data",
            "--strategy-list=NostalgiaForInfinityX",
            f"--timerange={start_date}-{end_date}",
            f"--max-open-trades={max_open_trades}",
            f"--stake-amount={stake_amount}",
            "--config=user_data/data/pairlists.json",
            "--no-cache",
        ]
        if pairlist is None:
            cmdline.append(f"--config={exchange_config}")
        else:
            pairlist_config = {"exchange": {"name": exchange, "pair_whitelist": pairlist}}
            pairlist_config_file = tmp_path / "test-pairlist.json"
            pairlist_config_file.write(json.dumps(pairlist_config))
            cmdline.append(f"--config={pairlist_config_file}")
        cmdline.append(f"--export-filename={json_results_file}")
        log.info("Running cmdline '%s' on '%s'", " ".join(cmdline), REPO_ROOT)
        proc = subprocess.run(
            cmdline, check=False, shell=False, cwd=REPO_ROOT, text=True, capture_output=True
        )
        ret = ProcessResult(
            exitcode=proc.returncode,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
            cmdline=cmdline,
        )
        if ret.exitcode != 0:
            log.info("Command Result:\n%s", ret)
        else:
            log.debug("Command Result:\n%s", ret)
        assert ret.exitcode == 0
        generated_results_file = list(
            f for f in tmp_path.rglob("backtest-results-*.json") if "meta" not in str(f)
        )[0]
        generated_json_ci_results_artifact_path = None
        if self.request.config.option.artifacts_path:
            generated_json_results_artifact_path = (
                self.request.config.option.artifacts_path / generated_results_file.name
            )
            shutil.copyfile(generated_results_file, generated_json_results_artifact_path)
            generated_json_ci_results_artifact_path = (
                self.request.config.option.artifacts_path
                / f"ci-results-{exchange}-{start_date}-{end_date}.json"
            )

            generated_txt_results_artifact_path = (
                self.request.config.option.artifacts_path
                / f"backtest-output-{exchange}-{start_date}-{end_date}.txt"
            )
            generated_txt_results_artifact_path.write_text(ret.stdout.strip())

        results_data = json.loads(generated_results_file.read_text())
        ret = BacktestResults(
            stdout=ret.stdout.strip(),
            stderr=ret.stderr.strip(),
            raw_data=results_data,
        )
        if generated_json_ci_results_artifact_path:
            generated_json_ci_results_artifact_path.write_text(
                json.dumps({f"{start_date}-{end_date}": ret._stats_pct})
            )
        ret.log_info()
        return ret


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
        return self.raw_data["strategy"]["NostalgiaForInfinityX"]

    @_stats.default
    def _set_stats(self):
        return self.raw_data["strategy_comparison"][0]

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
            "profit_sum_pct": self.full_stats.profit_sum_pct,
            "profit_mean_pct": self.full_stats.profit_mean_pct,
            "profit_total_pct": self.full_stats.profit_total_pct,
            "max_drawdown": self.results.max_drawdown * 100,
            "trades": self.full_stats.trades,
            "winrate": round(self.full_stats.wins * 100.0 / self.full_stats.trades, 2),
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
