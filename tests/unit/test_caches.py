import json
import time
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from legacy.NostalgiaForInfinityNext import Cache


def test_no_file_cache_load(tmp_path):
  cache_file = tmp_path / "data.json"
  cache = Cache(cache_file)
  with pytest.raises(FileNotFoundError):
    cache.load()


def test_load_only_when_changed(tmp_path):
  cache_file = tmp_path / "data.json"
  data = {"bar": {"shots": 0}}
  cache_file.write_text(json.dumps(data))
  cache = Cache(cache_file)
  cache.load()
  assert cache.data == data
  # Without changing the cache file, it should not load from the file again
  with patch.object(cache, "_load", MagicMock()) as mocked_load:
    for _ in range(5):
      cache.load()
      mocked_load.assert_not_called()

  # However, if we change the cache file, it SHOULD load the file again
  for n in range(1, 6):
    # Sleep long enough so that mtime changes
    time.sleep(0.01)
    data = {"bar": {"shots": n}}
    with open(cache_file, "w") as wfh:
      wfh.write(json.dumps(data))
    assert cache.data != data
    cache.load()
    assert cache.data == data


def test_save_only_when_changed(tmp_path):
  cache_file = tmp_path / "data.json"
  data = {"bar": {"shots": 0}}
  cache_file.write_text(json.dumps(data))
  cache = Cache(cache_file)
  assert cache.data == data
  # Without changing the cache file, it should not save the file again
  with patch.object(cache, "_save", MagicMock()) as mocked_save:
    for _ in range(5):
      cache.save()
      mocked_save.assert_not_called()

  # However, if we change the data, it SHOULD save the file again
  for n in range(1, 6):
    cache.data["bar"]["shots"] = n
    cache.save()
    assert json.loads(cache_file.read_text()) == cache.data
