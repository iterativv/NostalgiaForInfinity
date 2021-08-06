import argparse
import json
import os
import pathlib
import pprint
import sys

import github
from github.GithubException import GithubException

COMMENT_TEMPLATE = """\
# CI Backest Comparisson

## Binance
{binance}

## Kucoin
{kucoin}
"""


def comment_results(options, current_data, previous_data):
    gh = github.Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(options.repo)
    print(f"Loaded Repository: {repo.full_name}", file=sys.stderr, flush=True)
    commit = repo.get_commit(os.environ["GITHUB_SHA"])
    print(f"Loaded Commit: {commit}", file=sys.stderr, flush=True)

    binance_contents = ""
    for timerange in sorted(current_data["binance"]):
        binance_contents += f"| {timerange} | Current | Previous |\n"
        binance_contents += "|         --: |     --: |      --: |\n"
        for key in sorted(current_data["binance"][timerange]):
            if key == "max_drawdown":
                label = "Max Drawdown"
                current = current_data["binance"][timerange][key]
                previous = previous_data["binance"][timerange][key]
                if not isinstance(current, str):
                    current = f"{round(current, 4)} %"
                if not isinstance(previous, str):
                    previous = f"{round(previous, 4)} %"
            elif key == "profit_mean_pct":
                label = "Profit Mean"
                current = current_data["binance"][timerange][key]
                previous = previous_data["binance"][timerange][key]
                if not isinstance(current, str):
                    current = f"{round(current, 4)} %"
                if not isinstance(previous, str):
                    previous = f"{round(previous, 4)} %"
            elif key == "profit_sum_pct":
                label = "Profit Sum"
                current = current_data["binance"][timerange][key]
                previous = previous_data["binance"][timerange][key]
                if not isinstance(current, str):
                    current = f"{round(current, 4)} %"
                if not isinstance(previous, str):
                    previous = f"{round(previous, 4)} %"
            elif key == "profit_total_pct":
                label = "Profit Total"
                current = current_data["binance"][timerange][key]
                previous = previous_data["binance"][timerange][key]
                if not isinstance(current, str):
                    current = f"{round(current, 4)} %"
                if not isinstance(previous, str):
                    previous = f"{round(previous, 4)} %"
            elif key == "duration_avg":
                label = "Average Duration"
                current = current_data["binance"][timerange][key]
                previous = previous_data["binance"][timerange][key]
            elif key == "winrate":
                label = "Win Rate"
                current = current_data["binance"][timerange][key]
                previous = previous_data["binance"][timerange][key]
                if not isinstance(current, str):
                    current = f"{round(current, 4)} %"
                if not isinstance(previous, str):
                    previous = f"{round(previous, 4)} %"
            else:
                label = key
                current = current_data["binance"][timerange][key]
                previous = previous_data["binance"][timerange][key]
            binance_contents += f"| {label} | {current} | {previous} |\n"
        binance_contents += "\n\n"
    binance_contents += "\n\n"

    kucoin_contents = ""
    for timerange in sorted(current_data["kucoin"]):
        kucoin_contents += f"| {timerange} | Current | Previous |\n"
        kucoin_contents += "|         --: |     --: |      --: |\n"
        for key in sorted(current_data["kucoin"][timerange]):
            if key == "max_drawdown":
                label = "Max Drawdown"
                current = current_data["kucoin"][timerange][key]
                previous = previous_data["kucoin"][timerange][key]
                if not isinstance(current, str):
                    current = f"{round(current, 4)} %"
                if not isinstance(previous, str):
                    previous = f"{round(previous, 4)} %"
            elif key == "profit_mean_pct":
                label = "Profit Mean"
                current = current_data["kucoin"][timerange][key]
                previous = previous_data["kucoin"][timerange][key]
                if not isinstance(current, str):
                    current = f"{round(current, 4)} %"
                if not isinstance(previous, str):
                    previous = f"{round(previous, 4)} %"
            elif key == "profit_sum_pct":
                label = "Profit Sum"
                current = current_data["kucoin"][timerange][key]
                previous = previous_data["kucoin"][timerange][key]
                if not isinstance(current, str):
                    current = f"{round(current, 4)} %"
                if not isinstance(previous, str):
                    previous = f"{round(previous, 4)} %"
            elif key == "profit_total_pct":
                label = "Profit Total"
                current = current_data["kucoin"][timerange][key]
                previous = previous_data["kucoin"][timerange][key]
                if not isinstance(current, str):
                    current = f"{round(current, 4)} %"
                if not isinstance(previous, str):
                    previous = f"{round(previous, 4)} %"
            elif key == "duration_avg":
                label = "Average Duration"
                current = current_data["kucoin"][timerange][key]
                previous = previous_data["kucoin"][timerange][key]
            elif key == "winrate":
                label = "Win Rate"
                current = current_data["kucoin"][timerange][key]
                previous = previous_data["kucoin"][timerange][key]
                if not isinstance(current, str):
                    current = f"{round(current, 4)} %"
                if not isinstance(previous, str):
                    previous = f"{round(previous, 4)} %"
            else:
                label = key
                current = current_data["kucoin"][timerange][key]
                previous = previous_data["kucoin"][timerange][key]
            kucoin_contents += f"| {label} | {current} | {previous} |\n"
        kucoin_contents += "\n\n"
    kucoin_contents += "\n\n"

    comment_body = COMMENT_TEMPLATE.format(binance=binance_contents, kucoin=kucoin_contents)
    comment = commit.create_comment(comment_body)
    print(f"Created Comment: {comment}", file=sys.stderr, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="The Organization Repository")

    if not os.environ.get("GITHUB_TOKEN"):
        parser.exit(status=1, message="GITHUB_TOKEN environment variable not set")

    results_dir = pathlib.Path("results").resolve()
    if not results_dir:
        parser.exit(status=1, message=f"The results directory {results_dir} does not exist")

    current_results_dir = results_dir / "current"
    if not current_results_dir:
        parser.exit(
            status=1, message=f"The current results directory {current_results_dir} does not exist"
        )

    binance_current_results_files = list(current_results_dir.glob("ci-results-binance-*"))
    if not binance_current_results_files:
        parser.exit(
            status=1,
            message=f"There are no files matching 'ci-results-binance-*' in {current_results_dir}",
        )

    kucoin_current_results_files = list(current_results_dir.glob("ci-results-kucoin-*"))
    if not kucoin_current_results_files:
        parser.exit(
            status=1,
            message=f"There are no files matching 'ci-results-kucoin-*' in {current_results_dir}",
        )

    previous_results_dir = results_dir / "previous"
    if not previous_results_dir:
        parser.exit(
            status=1,
            message=f"The previous results directory {previous_results_dir} does not exist",
        )

    binance_previous_results_files = list(previous_results_dir.glob("ci-results-binance-*"))
    kucoin_previous_results_files = list(previous_results_dir.glob("ci-results-kucoin-*"))

    current_data = {
        "binance": {},
        "kucoin": {},
    }
    for path in binance_current_results_files:
        current_data["binance"].update(json.loads(path.read_text()))
    for path in kucoin_current_results_files:
        current_data["kucoin"].update(json.loads(path.read_text()))

    previous_data = {
        "binance": {},
        "kucoin": {},
    }
    for path in binance_previous_results_files:
        previous_data["binance"].update(json.loads(path.read_text()))
    for path in kucoin_previous_results_files:
        previous_data["kucoin"].update(json.loads(path.read_text()))

    # Set n/a data if necessary
    for timerange in current_data["binance"]:
        previous_data["binance"].setdefault(timerange, {})
        for key in current_data["binance"][timerange]:
            previous_data["binance"][timerange].setdefault(key, "n/a")

    for timerange in current_data["kucoin"]:
        previous_data["kucoin"].setdefault(timerange, {})
        for key in current_data["kucoin"][timerange]:
            previous_data["kucoin"][timerange].setdefault(key, "n/a")

    for timerange in previous_data["binance"]:
        current_data["binance"].setdefault(timerange, {})
        for key in current_data["binance"][timerange]:
            current_data["binance"][timerange].setdefault(key, "n/a")

    for timerange in previous_data["kucoin"]:
        current_data["kucoin"].setdefault(timerange, {})
        for key in current_data["kucoin"][timerange]:
            current_data["kucoin"][timerange].setdefault(key, "n/a")

    print("Current Data:\n{}".format(pprint.pformat(current_data)), file=sys.stderr, flush=True)
    print("Previous Data:\n{}".format(pprint.pformat(previous_data)), file=sys.stderr, flush=True)
    options = parser.parse_args()
    try:
        comment_results(options, current_data, previous_data)
        parser.exit(0)
    except GithubException as exc:
        parser.exit(1, message=str(exc))


if __name__ == "__main__":
    main()
