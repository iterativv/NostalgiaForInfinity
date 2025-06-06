import argparse
import json
import os
import pathlib
import pprint
import sys
import zipfile

import requests
import github
from github.GithubException import GithubException


def get_artifact_url(workflow_run, name):
  """Get the artifact download URL for a specific name from a workflow run."""
  artifacts = workflow_run.get_artifacts()
  for artifact in artifacts:
    if artifact.name == name:
      return artifact.archive_download_url
  return None


def download_artifact(url, output_path):
  """Download and save the artifact zip from GitHub REST API."""
  headers = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}

  response = requests.get(url, headers=headers, stream=True)
  if response.status_code == 200:
    with open(output_path, "wb") as f:
      for chunk in response.iter_content(chunk_size=512 * 1024):
        if chunk:
          f.write(chunk)
  else:
    raise Exception(f"Failed to download artifact: {response.status_code} {response.text}")


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
  reports_info = json.loads(reports_info_path.read_text()) if reports_info_path.exists() else {}

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
    outfile = options.path / f"{name}-{options.name}.zip"
    download_artifact(url, outfile)

    print(f"Wrote {outfile}", file=sys.stderr, flush=True)
    outdir = options.path / name.lower()
    outdir.mkdir(exist_ok=True)
    zipfile.ZipFile(outfile).extractall(path=outdir)
    outfile.unlink()

    reports_info[options.exchange][name] = {
      "sha": sha,
      "path": str(outdir.resolve()),
    }

  reports_info_path.write_text(json.dumps(reports_info, indent=2))


def get_previous_releases(repo, latest_n_releases):
  releases = []
  for tag in repo.get_tags():
    if len(releases) >= latest_n_releases:
      break
    releases.append(tag)
  return releases


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--repo", required=True, help="The Organization Repository")
  parser.add_argument("--exchange", required=True, help="The exchange name")
  parser.add_argument("--name", required=True, help="The artifact name to get")
  parser.add_argument("--workflow", required=True, help="The workflow name")
  parser.add_argument("--branch", required=True, help="The branch for 'Previous'")
  parser.add_argument("--releases", type=int, default=3, help="Number of recent releases to pull")
  parser.add_argument("path", metavar="PATH", type=pathlib.Path, help="Path to extract artifacts")

  if not os.environ.get("GITHUB_TOKEN"):
    parser.exit(status=1, message="GITHUB_TOKEN environment variable not set")

  options = parser.parse_args()

  results_dir = options.path.resolve()
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
