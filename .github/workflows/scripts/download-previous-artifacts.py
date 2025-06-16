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
  return None


def get_previous_releases(repo, latest_n_releases):
  # Get the latest N tags/releases
  releases = []
  for tag in repo.get_tags():
    if len(releases) == latest_n_releases:
      break
    releases.append(tag)
  return releases


def download_and_extract_artifact(repo, url, outdir, outfile):
  req_headers = {}
  repo._requester._Requester__authenticate(url, req_headers, None)
  response = repo._requester._Requester__connection.session.get(url, headers=req_headers, allow_redirects=True)
  if response.status_code == 200:
    with open(outfile, "wb") as wfh:
      for data in response.iter_content(chunk_size=512 * 1024):
        if data:
          wfh.write(data)
    if not outdir.is_dir():
      outdir.mkdir()
    zipfile.ZipFile(outfile).extractall(path=outdir)
    outfile.unlink()
    return True
  else:
    print(f"Failed to download artifact from {url}: {response.status_code}", file=sys.stderr, flush=True)
    return False


def find_previous_run(workflow, branch, current_run_id, artifact_name, repo):
  """
  Finds the most recent successful run on the branch before the current run,
  where the commit also has comments.
  """
  found_current = False
  print(f"Looking for previous run before run id {current_run_id} on branch {branch} with commit comments")
  for run in workflow.get_runs(branch=branch):
    if str(run.id) == current_run_id:
      found_current = True
      continue
    if not found_current:
      continue  # Only look at runs before the current one
    if run.conclusion != "success":
      continue
    # Check if commit has comments
    commit = repo.get_commit(run.head_sha)
    if commit.get_comments().totalCount == 0:
      continue
    url = get_artifact_url(run, artifact_name)
    if url:
      return run.head_sha, url
  return None, None


def download_previous_artifacts(repo, options):
  releases = get_previous_releases(repo, options.releases)
  workflow = repo.get_workflow(options.workflow)
  runs = {}
  release_names = {release.name: release for release in releases}

  current_run_id = os.environ.get("GITHUB_RUN_ID")
  current_sha = os.environ.get("GITHUB_SHA")

  # Find the current run
  current_run = None
  for run in workflow.get_runs():
    if str(run.id) == current_run_id:
      current_run = run
      break

  # Get Current artifact
  if current_run:
    url = get_artifact_url(current_run, options.name)
    runs["Current"] = (current_sha, url)

  # Get Previous artifact (most recent successful run before current on branch)
  prev_sha, prev_url = find_previous_run(workflow, options.branch, current_run_id, options.name, repo)
  if prev_sha and prev_url:
    runs["Previous"] = (prev_sha, prev_url)

  # Get artifacts for releases (tags)
  for run in workflow.get_runs():
    if not release_names:
      break
    release = release_names.pop(run.head_branch, None)
    if release:
      url = get_artifact_url(run, options.name)
      runs[release.name] = (release.commit.sha, url)

  print(f"Collected Runs:\n{pprint.pformat(runs)}", file=sys.stderr, flush=True)
  reports_info_path = options.path / "reports-info.json"
  reports_info = {}
  if reports_info_path.exists():
    reports_info = json.loads(reports_info_path.read_text())
  if options.exchange not in reports_info:
    reports_info[options.exchange] = {}
  if options.tradingmode not in reports_info[options.exchange]:
    reports_info[options.exchange][options.tradingmode] = {}

  for name, (sha, url) in runs.items():
    if not url:
      print(f"Did not find a download url for {name}", file=sys.stderr, flush=True)
      reports_info[options.exchange][options.tradingmode][name] = {
        "sha": sha,
        "path": str(options.path / "current"),
      }
      continue
    print(f"Downloading {name} {url}....", file=sys.stderr, flush=True)
    outfile = options.path / f"{name}-{options.name}.zip"
    outdir = options.path / name.lower()
    if download_and_extract_artifact(repo, url, outdir, outfile):
      print(f"Wrote and extracted to {outdir}", file=sys.stderr, flush=True)
      reports_info[options.exchange][options.tradingmode][name] = {"sha": sha, "path": str(outdir.resolve())}
  reports_info_path.write_text(json.dumps(reports_info, indent=2))


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--repo", required=True, help="The Organization Repository")
  parser.add_argument("--exchange", required=True, help="The exchange name")
  parser.add_argument("--tradingmode", required=True, help="The trading mode")
  parser.add_argument("--name", required=True, help="The artifacts name to get")
  parser.add_argument("--workflow", required=True, help="The workflow name from where to get artifacts")
  parser.add_argument("--branch", required=True, help="The branch from where to get the previous artifacts")
  parser.add_argument(
    "--releases",
    type=int,
    default=3,
    help="Besides previous artifacts, how many previous release(tags) artifacts to get",
  )
  parser.add_argument("path", metavar="PATH", type=pathlib.Path, help="Path where to extract artifacts")

  if not os.environ.get("GITHUB_TOKEN"):
    parser.exit(status=1, message="GITHUB_TOKEN environment variable not set")

  options = parser.parse_args()
  results_dir = pathlib.Path(options.path).resolve()
  if not results_dir.is_dir():
    results_dir.mkdir(parents=True, exist_ok=True)

  gh = github.Github(os.environ["GITHUB_TOKEN"])
  repo = gh.get_repo(options.repo)
  print(f"Loaded Repository: {repo.full_name}", file=sys.stderr, flush=True)

  try:
    download_previous_artifacts(repo, options)
    parser.exit(0)
  except GithubException as exc:
    parser.exit(1, message=str(exc))
  except Exception as exc:
    parser.exit(1, message=f"Unexpected error: {exc}")


if __name__ == "__main__":
  main()
