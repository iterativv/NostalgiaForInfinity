import json
import logging
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


def exchange_backtest(
    exchange,
    tmp_path,
    start_date,
    end_date,
    pairlist=None,
    max_open_trades=5,
    stake_amount="unlimited",
):
    exchange_config = f"user_data/{exchange}-usdt-static.json"
    json_results_file = tmp_path / "backtest-results.json"
    cmdline = [
        "freqtrade",
        "backtesting",
        f"--user-data=user_data",
        "--strategy-list=NostalgiaForInfinityNext",
        f"--timerange={start_date}-{end_date}",
        f"--max-open-trades={max_open_trades}",
        f"--stake-amount={stake_amount}",
        "--config=user_data/pairlists.json",
        f"--export-filename={json_results_file}",
    ]
    if pairlist is None:
        cmdline.append(f"--config={exchange_config}")
    else:
        pairlist_config = {"exchange": {"name": exchange, "pair_whitelist": pairlist}}
        pairlist_config_file = tmp_path / "test-pairlist.json"
        pairlist_config_file.write(json.dumps(pairlist_config))
        cmdline.append(f"--config={pairlist_config_file}")
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
    log.info("Command Result:\n%s", ret)
    assert ret.exitcode == 0
    generated_results_file = list(tmp_path.rglob("backtest-results-*.json"))[0]
    results_data = json.loads(generated_results_file.read_text())
    data = {
        "stdout": ret.stdout.strip(),
        "stderr": ret.stderr.strip(),
        "comparison": results_data["strategy_comparison"],
        "results": results_data["strategy"]["NostalgiaForInfinityNext"],
    }
    return json.loads(json.dumps(data), object_hook=lambda d: SimpleNamespace(**d))
