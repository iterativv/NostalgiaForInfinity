import sys
from pathlib import Path

# Make sure we can import the strategy module directly
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))


def pytest_addoption(parser):
  parser.addoption("--artifacts-path", default=None, help="Path to write generated test artifacts")


def pytest_configure(config):
  if config.option.artifacts_path:
    config.option.artifacts_path = Path(config.option.artifacts_path).resolve()
    if not config.option.artifacts_path.is_dir():
      config.option.artifacts_path.mkdir()
