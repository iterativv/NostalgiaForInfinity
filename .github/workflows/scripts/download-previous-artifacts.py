import argparse
import json
import os
import pathlib
import pprint
import sys
import zipfile

import github
from github.GithubException import GithubException


def get_artifact_url(workflow_run, name):
    headers, data = workflow_run._requester.requestJsonAndCheck("GET", workflow_run.artifacts_url)
    for artifact in data.get("artifacts", ()):
        if artifact["name"] == name:
            return artifact["archive_download_url"]


def download_previous_artifacts(repo, options):
    releases = get_previous_releases(repo, options.releases)
    workflow = repo.get_workflow(options.workflow)
    runs = {}
    release_names = {release.name: release for release in releases}
    for workflow_run in workflow.get_runs():
        if "Current" in runs and "Previous" in runs and not release_names:
            break
        if "Previous" not in runs and workflow_run.head_branch == options.branch:
            artifact_url = get_artifact_url(workflow_run, options.name)
            if artifact_url:
                runs["Previous"] = (workflow_run.head_sha, artifact_url)
                continue
        if "Current" not in runs and str(workflow_run.id) == os.environ.get("GITHUB_RUN_ID"):
            runs["Current"] = (
                os.environ["GITHUB_SHA"],
                get_artifact_url(workflow_run, options.name),
            )
            continue
        release = release_names.pop(workflow_run.head_branch, None)
        if release:
            runs[release.name] = (release.commit.sha, get_artifact_url(workflow_run, options.name))

    print(f"Collected Runs:\n{pprint.pformat(runs)}", file=sys.stderr, flush=True)
    reports_info_path = options.path / "reports-info.json"
    if reports_info_path.exists():
        reports_info = json.loads(reports_info_path.read_text())
    else:
        reports_info = {}
    if options.exchange not in reports_info:
        reports_info[options.exchange] = {}
    for name, (sha, url) in runs.items():
        if not url:
            print(f"Did not find a download url for {name}", file=sys.stderr, flush=True)
            reports_info[options.exchange][name] = {
                "sha": sha,
                "path": str(options.path / "current"),
            }
            continue
        print(f"Downloading {name} {url}....", file=sys.stderr, flush=True)
        # While pygithub doesn't support GH actions and their Artifacts interactions
        # We doit the hacky way
        req_headers = {}
        repo._requester._Requester__authenticate(url, req_headers, None)
        response = repo._requester._Requester__connection.session.get(
            url, headers=req_headers, allow_redirects=True
        )
        if response.status_code == 200:
            outfile = options.path / f"{name}-{options.name}.zip"
            with open(outfile, "wb") as wfh:
                for data in response.iter_content(chunk_size=512 * 1024):
                    if data:
                        wfh.write(data)
            print(f"Wrote {outfile}", file=sys.stderr, flush=True)
            outdir = options.path / name.lower()
            if not outdir.is_dir():
                outdir.mkdir()
            zipfile.ZipFile(outfile).extractall(path=outdir)
            outfile.unlink()
            reports_info[options.exchange][name] = {"sha": sha, "path": str(outdir.resolve())}
    reports_info_path.write_text(json.dumps(reports_info))


def get_previous_releases(repo, latest_n_releases):
    releases = []
    for tag in repo.get_tags():
        if len(releases) == latest_n_releases:
            break
        releases.append(tag)
    return releases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="The Organization Repository")
    parser.add_argument("--exchange", required=True, help="The exchange name")
    parser.add_argument("--name", required=True, help="The artifacts name to get")
    parser.add_argument(
        "--workflow",
        required=True,
        help="The workflow name from where to get artifacts",
    )
    parser.add_argument(
        "--branch",
        required=True,
        help="The branch from where to get the previous artifacts",
    )
    parser.add_argument(
        "--releases",
        type=int,
        default=3,
        help="Besides previous artifacts, how many previous release(tags) artifacts to get",
    )
    parser.add_argument(
        "path",
        metavar="PATH",
        type=pathlib.Path,
        help="Path where to extract artifacts",
    )

    if not os.environ.get("GITHUB_TOKEN"):
        parser.exit(status=1, message="GITHUB_TOKEN environment variable not set")

    options = parser.parse_args()

    results_dir = pathlib.Path(options.path).resolve()
    if not results_dir.is_dir():
        results_dir.mkdir()

    gh = github.Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(options.repo)
    print(f"Loaded Repository: {repo.full_name}", file=sys.stderr, flush=True)

    try:
        download_previous_artifacts(repo, options)
        parser.exit(0)
    except GithubException as exc:
        parser.exit(1, message=str(exc))


if __name__ == "__main__":
    main()
