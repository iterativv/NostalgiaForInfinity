import argparse
import json
import os
import pathlib
import pprint
import sys

import github
from github.GithubException import GithubException


def sort_report_names(value):
    if value == "Current":
        return -1
    if value == "Previous":
        return -2
    return -3


def delete_previous_comments(commit, created_comment_ids, exchanges):
    comment_starts = {f"# {exchange.capitalize()}" for exchange in exchanges}
    for comment in commit.get_comments():
        if comment.user.login != "github-actions[bot]":
            # Not a comment made by this bot
            continue
        if comment.id in created_comment_ids:
            # These are the comments we have just created
            continue
        if not comment.body.startswith(comment_starts):
            # This comment does not start with our headers
            continue
        # We have a match, delete it
        print(f"Deleting previous comment {comment}")
        comment.delete()


def comment_results(options, results_data):
    gh = github.Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(options.repo)
    print(f"Loaded Repository: {repo.full_name}", file=sys.stderr, flush=True)

    exchanges = set()
    comment_ids = set()
    commit = repo.get_commit(os.environ["GITHUB_SHA"])
    print(f"Loaded Commit: {commit}", file=sys.stderr, flush=True)

    for exchange in sorted(results_data):
        exchanges.add(exchange)
        sorted_report_names = list(
            reversed(sorted(results_data[exchange]["names"], key=sort_report_names))
        )
        for timerange in results_data[exchange]["timeranges"]:
            comment_body = f"## {exchange.capitalize()} - {timerange}\n\n"
            report_table_header_1 = f"| "
            report_table_header_2 = "| --: "
            for report_name in sorted_report_names:
                if report_name == "Current":
                    report_table_header_1 += f"| {report_name} "
                else:
                    report_table_header_1 += f"| [{report_name}](https://github.com/{options.repo}/commit/{results_data[exchange]['names'][report_name]}) "
                report_table_header_2 += "| --: "
            report_table_header_1 += "|\n"
            report_table_header_2 += "|\n"
            comment_body += report_table_header_1
            comment_body += report_table_header_2
            for key in sorted(results_data[exchange]["timeranges"][timerange]):
                row_line = "| "
                if key == "max_drawdown":
                    label = "Max Drawdown"
                    row_line += f" {label } |"
                    for report_name in sorted_report_names:
                        value = results_data[exchange]["timeranges"][timerange][key][report_name]
                        if not isinstance(value, str):
                            value = f"{round(value, 4)} %"
                        row_line += f" {value} |"
                    comment_body += f"{row_line}\n"
                elif key == "profit_mean_pct":
                    label = "Profit Mean"
                    row_line += f" {label } |"
                    for report_name in sorted_report_names:
                        value = results_data[exchange]["timeranges"][timerange][key][report_name]
                        if not isinstance(value, str):
                            value = f"{round(value, 4)} %"
                        row_line += f" {value} |"
                    comment_body += f"{row_line}\n"
                elif key == "profit_sum_pct":
                    label = "Profit Sum"
                    row_line += f" {label } |"
                    for report_name in sorted_report_names:
                        value = results_data[exchange]["timeranges"][timerange][key][report_name]
                        if not isinstance(value, str):
                            value = f"{round(value, 4)} %"
                        row_line += f" {value} |"
                    comment_body += f"{row_line}\n"
                elif key == "profit_total_pct":
                    label = "Profit Total"
                    row_line += f" {label } |"
                    for report_name in sorted_report_names:
                        value = results_data[exchange]["timeranges"][timerange][key][report_name]
                        if not isinstance(value, str):
                            value = f"{round(value, 4)} %"
                        row_line += f" {value} |"
                    comment_body += f"{row_line}\n"
                elif key == "winrate":
                    label = "Win Rate"
                    row_line += f" {label } |"
                    for report_name in sorted_report_names:
                        value = results_data[exchange]["timeranges"][timerange][key][report_name]
                        if not isinstance(value, str):
                            value = f"{round(value, 4)} %"
                        row_line += f" {value} |"
                    comment_body += f"{row_line}\n"
                else:
                    if key == "duration_avg":
                        label = "Average Duration"
                    elif key == "trades":
                        label = "Trades"
                    else:
                        label = key
                    row_line += f" {label } |"
                    for report_name in sorted_report_names:
                        value = results_data[exchange]["timeranges"][timerange][key][report_name]
                        row_line += f" {value} |"
                    comment_body += f"{row_line}\n"
            ft_output = options.path / "current" / f"backtest-output-{exchange}-{timerange}.txt"
            comment_body += "\n<details>\n"
            comment_body += f"<summary>Freqtrade Backest Output (click me)</summary>\n"
            comment_body += f"<pre>{ft_output.read_text().strip()}</pre>\n"
            comment_body += "</details>\n"
            comment_body += "\n\n"
            comment = commit.create_comment(comment_body.rstrip())
            print(f"Created Comment: {comment}", file=sys.stderr, flush=True)
            comment_ids.add(comment.id)

    delete_previous_comments(commit, comment_ids, exchanges)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="The Organization Repository")
    parser.add_argument(
        "path", metavar="PATH", type=pathlib.Path, help="Path where artifacts are extracted"
    )

    if not os.environ.get("GITHUB_TOKEN"):
        parser.exit(status=1, message="GITHUB_TOKEN environment variable not set")

    options = parser.parse_args()

    if not options.path.is_dir():
        parser.exit(
            status=1,
            message=f"The directory where artifacts should have been extracted, {options.path}, does not exist",
        )

    reports_info_path = options.path / "reports-info.json"
    if not reports_info_path.exists():
        parser.exit(status=1, message=f"The {reports_info_path}, does not exist")

    reports_info = json.loads(reports_info_path.read_text())

    reports_data = {}
    for exchange in reports_info:
        timeranges = set()
        keys = set()
        reports_data[exchange] = {}
        for name in sorted(reports_info[exchange]):
            exchange_results = {}
            reports_data[exchange][name] = {
                "results": exchange_results,
                "sha": reports_info[exchange][name]["sha"],
            }
            results_path = pathlib.Path(reports_info[exchange][name]["path"])
            for results_file in results_path.rglob(f"ci-results-{exchange}-*"):
                exchange_results.update(json.loads(results_file.read_text()))
        # Set n/a data if necessary
        names = list(reports_data[exchange])
        reports_data[exchange]["names"] = {}
        for name in names:
            reports_data[exchange]["names"][name] = reports_data[exchange][name]["sha"]
            for timerange in reports_data[exchange][name]["results"]:
                timeranges.add(timerange)
                for key in reports_data[exchange][name]["results"][timerange]:
                    keys.add(key)
                    for oname in names:
                        if oname == name:
                            continue
                        oresults = reports_data[exchange][oname]["results"]
                        if timerange not in oresults:
                            oresults[timerange] = {}
                        oresults[timerange].setdefault(key, "n/a")
        reports_data[exchange]["timeranges"] = {}
        for timerange in sorted(timeranges):
            reports_data[exchange]["timeranges"][timerange] = {}
            for key in sorted(keys):
                reports_data[exchange]["timeranges"][timerange][key] = {}
                for name in names:
                    value = reports_data[exchange][name]["results"][timerange][key]
                    reports_data[exchange]["timeranges"][timerange][key][name] = value

    pprint.pprint(reports_data)
    try:
        comment_results(options, reports_data)
        parser.exit(0)
    except GithubException as exc:
        parser.exit(1, message=str(exc))


if __name__ == "__main__":
    main()
