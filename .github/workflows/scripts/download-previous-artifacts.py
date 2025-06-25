import argparse
import json
import os
import sys
import requests
import zipfile
import io
import pathlib
import github
from github.GithubException import GithubException


def get_artifact_url(workflow_run, artifact_name):
  for artifact in workflow_run.get_artifacts():
    if artifact.name == artifact_name:
      return artifact.archive_download_url
  return None


def get_recent_tags(repo, num_tags):
  tags = []
  for tag in repo.get_tags():
    if len(tags) == num_tags:
      break
    tags.append(tag)
  return tags


def find_workflow_by_filename(repo, workflow_filename):
  for wf in repo.get_workflows():
    if wf.path.endswith(workflow_filename):
      return wf
  return None


def get_run_for_commit(workflow, commit_sha):
  for run in workflow.get_runs():
    if run.head_sha == commit_sha:
      return run
  return None


def download_and_extract_artifact(response_content, outdir, outfile):
  with zipfile.ZipFile(io.BytesIO(response_content)) as zf:
    zf.extractall(outdir)
    print(f"Extracted {outfile.resolve()} to {outdir.resolve()}", file=sys.stderr, flush=True)


def find_previous_run(repo, workflow, branch, current_run_created_at, artifact_name):
  print(f"Looking for previous runs for workflow '{workflow.name}' on branch '{branch}'", file=sys.stderr, flush=True)

  for run in workflow.get_runs(branch=branch):
    if run.created_at >= current_run_created_at:
      continue
    print(f"Checking run {run.id} on {run.head_sha}", file=sys.stderr, flush=True)

    try:
      commit = repo.get_commit(run.head_sha)
      comments = commit.get_comments()
      if comments.totalCount == 0:
        print(f"Skipping run {run.id} — no commit comments on {run.head_sha}", file=sys.stderr, flush=True)
        continue

      artifact_url = get_artifact_url(run, artifact_name)
      if artifact_url:
        print(f"Found matching run {run.id} with artifact '{artifact_name}'", file=sys.stderr, flush=True)
        return run.head_sha, artifact_url
    except Exception as e:
      print(f"Error checking run {run.id}: {e}", file=sys.stderr, flush=True)
      continue

  print("No suitable previous run found.", file=sys.stderr, flush=True)
  return None, None


def download_previous_artifacts(repo, options):
  workflow = find_workflow_by_filename(repo, options.workflow)
  if not workflow:
    print(f"Workflow {options.workflow} not found in {repo.name}", file=sys.stderr, flush=True)
    return
  print(f"Using workflow: {workflow.name}", file=sys.stderr, flush=True)

  runs = {}
  current_run_id = os.environ.get("GITHUB_RUN_ID")
  current_sha = os.environ.get("GITHUB_SHA")
  if not current_run_id or not current_sha:
    print("GITHUB_RUN_ID or GITHUB_SHA environment variables not set", file=sys.stderr, flush=True)
    return

  # Fetch the current run directly from the repo
  try:
    current_run = repo.get_workflow_run(int(current_run_id))
    if current_run.head_sha != current_sha:
      print(f"Warning: SHA mismatch. Env: {current_sha}, Run: {current_run.head_sha}", file=sys.stderr, flush=True)
  except GithubException as e:
    print(f"Failed to fetch current run {current_run_id}: {e}", file=sys.stderr, flush=True)
    return

  print(f"Current run: {current_run.id} on {current_run.head_sha}", file=sys.stderr, flush=True)

  # Get the artifact URL for the current run
  artifact_url = get_artifact_url(current_run, options.artifact)
  if not artifact_url:
    print(f"Artifact {options.artifact} not found in current run {current_run.id}", file=sys.stderr, flush=True)
    return
  runs["Current"] = (current_sha, artifact_url)
  print(f"Current artifact URL: {artifact_url}", file=sys.stderr, flush=True)

  # Find the previous successful run with the specified artifact
  prev_sha, prev_url = find_previous_run(repo, workflow, options.branch, current_run.created_at, options.artifact)
  if prev_sha and prev_url:
    runs["Previous"] = (prev_sha, prev_url)
    print(f"Previous artifact URL: {prev_url}", file=sys.stderr, flush=True)
  else:
    print("No previous successful run found with the specified artifact", file=sys.stderr, flush=True)

  # Get the last few releases and their artifacts
  previous_tags = get_recent_tags(repo, options.releases)
  print(f"Found {len(previous_tags)} previous releases", file=sys.stderr, flush=True)
  for tag in previous_tags:
    run = get_run_for_commit(workflow, tag.commit.sha)
    if not run:
      continue
    artifact_url = get_artifact_url(run, options.artifact)
    if artifact_url:
      runs[tag.name] = (tag.commit.sha, artifact_url)

  print(f"Found {len(runs)} artifacts to download", file=sys.stderr, flush=True)

  # Download and extract artifacts
  reports_info = {}

  for name, (_sha, url) in runs.items():
    print(f"Downloading artifact {name} from {url}", file=sys.stderr, flush=True)
    try:
      response = requests.get(url, headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"}, timeout=30)
      if response.status_code != 200:
        print(
          f"Failed to download artifact {name}: {response.status_code} {response.reason}", file=sys.stderr, flush=True
        )
        continue

      outdir = options.path / name.lower()
      outdir.mkdir(exist_ok=True)
      outfile = outdir / f"{name}-{options.artifact}.zip"
      download_and_extract_artifact(response.content, outdir, outfile)

    except Exception as e:
      print(f"Error downloading artifact for {name}: {e}", file=sys.stderr, flush=True)

  reports_info_path = options.path / "reports-info.json"
  if reports_info_path.exists():
    reports_info = json.loads(reports_info_path.read_text())
    print(f"Loaded reports-info.json from {reports_info_path}", file=sys.stderr, flush=True)
  else:
    print(f"Could not find reports-info.json in {options.path}", file=sys.stderr, flush=True)

  reports_info.setdefault(options.exchange, {}).setdefault(options.tradingmode, {})

  for name, (sha, _) in runs.items():
    outdir = options.path / name.lower()
    reports_info[options.exchange][options.tradingmode][name] = {"sha": sha, "path": str(outdir.resolve())}

  reports_info_path.write_text(json.dumps(reports_info, indent=2))


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--repo", required=True, help="The Organization Repository")
  parser.add_argument("--workflow", default="backtests.yml", help="The workflow filename")
  parser.add_argument("--artifact", required=True, help="The artifact name")
  parser.add_argument("--branch", default="main", help="The branch name")
  parser.add_argument("--releases", type=int, default=3, help="How many releases to get")
  parser.add_argument("--exchange", required=True, help="The exchange name")
  parser.add_argument("--tradingmode", required=True, help="The trading mode name")
  parser.add_argument("path", metavar="PATH", type=pathlib.Path, help="Path where to extract artifacts")

  if not os.environ.get("GITHUB_TOKEN"):
    parser.exit(status=1, message="GITHUB_TOKEN environment variable not set")

  options = parser.parse_args()
  options.path.mkdir(parents=True, exist_ok=True)

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
