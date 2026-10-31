"""Deterministic state probes; the parent executes these in its pinned runtime."""

from dataclasses import FrozenInstanceError, asdict

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from NostalgiaForInfinityX8 import RHourlyState, _r_cusum as _cusum


PAIRS = ("AAA/USDT:USDT", "BBB/USDT:USDT", "CCC/USDT:USDT")
START = pd.Timestamp("2020-01-01", tz="UTC")
HOUR = pd.Timedelta(hours=1)


def history(rows: int = 1700) -> dict[str, pd.DataFrame]:
  dates = pd.date_range(START, periods=rows, freq="1h")
  t = np.arange(rows, dtype=float)
  market = 0.001 * np.sin(t / 11.0) + 0.0003 * np.cos(t / 5.0)
  moves = (
    market + 0.0007 * np.sin(t / 3.0),
    market - 0.0005 * np.cos(t / 7.0),
    market + 0.0004 * np.sin(t / 17.0),
  )
  return {
    pair: pd.DataFrame({"date": dates, "close": 100.0 * np.cumprod(1.0 + move)})
    for pair, move in zip(PAIRS, moves, strict=True)
  }


def window(frames, start, stop):
  return {pair: frame.iloc[start:stop] for pair, frame in frames.items()}


def table(rows):
  return pd.DataFrame([asdict(row) for row in rows])


def assert_rows_equal(left, right):
  assert_frame_equal(table(left), table(right), check_exact=True)


def test_strict_crossing_alarm_reset_and_unknown_reset():
  state = 0.0
  values = [5.5, 0.5, 0.5001, 0.5, 4.5, np.nan, 1.0, -9.0, np.inf, -np.inf]
  actual = []
  for value in values:
    state, alarm = _cusum(state, value)
    actual.append((state, alarm))
  assert actual == [
    (5.0, False),
    (5.0, False),
    (0.0, True),
    (0.0, False),
    (4.0, False),
    (0.0, False),
    (0.5, False),
    (0.0, False),
    (0.0, False),
    (0.0, False),
  ]


def test_independent_prior_window_formula_and_warmup():
  frames = history()
  records = RHourlyState(PAIRS).update(frames, PAIRS, START + 1700 * HOUR)
  close = pd.DataFrame({pair: frame.set_index("date")["close"] for pair, frame in frames.items()})
  returns = close.pct_change(fill_method=None)
  market = returns.median(axis=1)
  for pair in PAIRS:
    result = table(records[pair])
    assert result["R_BETA"].first_valid_index() == 721
    assert result["R_Z"].first_valid_index() == 1441
    for position in (721, 1441, 1500, 1699):
      prior_r = returns[pair].iloc[position - 720 : position].to_numpy()
      prior_m = market.iloc[position - 720 : position].to_numpy()
      beta = np.cov(prior_r, prior_m, ddof=1)[0, 1] / np.var(prior_m, ddof=1)
      residual = returns[pair].iloc[position] - beta * market.iloc[position]
      assert result["R_BETA"].iloc[position] == pytest.approx(beta, rel=1e-12)
      assert result["R_RESIDUAL"].iloc[position] == pytest.approx(residual, abs=1e-14)
      if position >= 1441:
        scale = np.std(result["R_RESIDUAL"].iloc[position - 720 : position], ddof=1)
        assert result["R_SCALE"].iloc[position] == pytest.approx(scale, rel=1e-12)
        assert result["R_Z"].iloc[position] == pytest.approx(residual / scale, abs=1e-11)


def test_tiny_rolling_buffers_preserve_full_prefix_and_repeat_identity():
  frames = history()
  frames[PAIRS[0]].loc[1500:, "close"] *= np.power(1.01, np.arange(1, 201))
  batch = RHourlyState(PAIRS).update(frames, PAIRS, START + 1700 * HOUR)
  state = RHourlyState(PAIRS)
  collected = {pair: [] for pair in PAIRS}
  saved = []
  previous = 0
  for stop in [*range(24, 1700, 24), 1700]:
    source = window(frames, max(0, stop - 48), stop)
    output = state.update(source, PAIRS, START + stop * HOUR)
    assert len(output[PAIRS[0]]) == stop - previous
    assert state.update(source, tuple(reversed(PAIRS)), START + stop * HOUR) is output
    assert state.update(source, PAIRS, START + stop * HOUR + pd.Timedelta(minutes=5)) is output
    saved.append((output, table(output[PAIRS[0]])))
    for pair in PAIRS:
      collected[pair].extend(output[pair])
    previous = stop
  for pair in PAIRS:
    assert_rows_equal(collected[pair], batch[pair])
  for output, before in saved:
    assert_frame_equal(table(output[PAIRS[0]]), before, check_exact=True)
  assert len(state._raw) == 721
  assert state._market.shape == (720,)
  assert state._returns.shape == state._residuals.shape == (720, len(PAIRS))
  assert all(not rows for rows in state._rows.values())
  assert len(state._snapshot[PAIRS[0]]) <= 24
  assert any(row.R_CUSUM > 0 for row in batch[PAIRS[0]][1441:])
  assert any(row.R_UP_ALARM for row in batch[PAIRS[0]][1441:])


def test_nonzero_cusum_is_not_reinitialized_by_a_two_row_buffer():
  frames = history()
  batch = RHourlyState([PAIRS[0]]).update(frames, PAIRS, START + 1700 * HOUR)[PAIRS[0]]
  boundary = next(i + 1 for i in range(1441, 1699) if batch[i].R_CUSUM > 0 and batch[i + 1].R_Z > 0.5)
  state = RHourlyState([PAIRS[0]])
  first = state.update(window(frames, 0, boundary), PAIRS, START + boundary * HOUR)
  assert first[PAIRS[0]][-1].R_CUSUM > 0
  after = state.update(
    window(frames, boundary - 1, boundary + 1),
    PAIRS,
    START + (boundary + 1) * HOUR,
  )
  assert_rows_equal(after[PAIRS[0]], batch[boundary : boundary + 1])


def test_missed_callbacks_catch_up_every_supplied_closed_hour_once():
  frames = history()
  batch = RHourlyState(PAIRS).update(frames, PAIRS, START + 1700 * HOUR)
  state = RHourlyState(PAIRS, retain_history=True)
  first = state.update(window(frames, 0, 1490), PAIRS, START + 1490 * HOUR)
  first_table = table(first[PAIRS[0]])
  for stop in (1555, 1630, 1700):
    output = state.update(window(frames, stop - 100, stop), PAIRS, START + stop * HOUR)
    assert len(output[PAIRS[0]]) == stop
    assert output[PAIRS[0]][0] is first[PAIRS[0]][0]
    assert_rows_equal(output[PAIRS[0]], batch[PAIRS[0]][:stop])
  assert_frame_equal(table(first[PAIRS[0]]), first_table, check_exact=True)
  with pytest.raises(TypeError):
    first[PAIRS[0]] = ()
  with pytest.raises(FrozenInstanceError):
    first[PAIRS[0]][0].R_CUSUM = 1.0


def test_real_pair_and_all_market_gaps_match_batch_without_bridging():
  frames = history()
  frames[PAIRS[0]] = frames[PAIRS[0]].drop(index=1498)
  for pair in PAIRS:
    frames[pair] = frames[pair].drop(index=1500)
  batch = RHourlyState(PAIRS).update(frames, PAIRS, START + 1700 * HOUR)
  state = RHourlyState(PAIRS, retain_history=True)
  for stop in (1490, 1550, 1700):
    source = {
      pair: frame.loc[(frame["date"] >= START + max(0, stop - 1500) * HOUR) & (frame["date"] < START + stop * HOUR)]
      for pair, frame in frames.items()
    }
    output = state.update(source, PAIRS, START + stop * HOUR)
  for pair in PAIRS:
    assert_rows_equal(output[pair], batch[pair])
  result = batch[PAIRS[0]]
  assert np.isnan(result[1498].R_RETURN)
  assert np.isnan(result[1499].R_RETURN)
  assert result[1498].R_MARKET_COUNT == 2
  assert result[1500].R_MARKET_COUNT == result[1501].R_MARKET_COUNT == 0
  assert np.isnan(result[1500].R_MARKET_RETURN)
  assert all(row.R_CUSUM == 0 and not row.R_UP_ALARM for row in result[1498:])


def test_missing_catchup_data_is_unknown_not_an_interpolated_return():
  frames = history()
  state = RHourlyState([PAIRS[0]])
  state.update(window(frames, 0, 1500), PAIRS, START + 1500 * HOUR)
  output = state.update(window(frames, 1504, 1510), PAIRS, START + 1510 * HOUR)[PAIRS[0]]
  assert [row.date for row in output] == list(pd.date_range(START + 1500 * HOUR, periods=10, freq="1h"))
  assert all(row.R_MARKET_COUNT == 0 for row in output[:5])
  assert all(np.isnan(row.R_RETURN) for row in output[:5])
  assert output[5].R_MARKET_COUNT == 3
  assert all(np.isnan(row.R_Z) and row.R_CUSUM == 0 for row in output)
  with pytest.raises(ValueError, match="Committed close revision"):
    state.update(window(frames, 1500, 1510), PAIRS, START + 1510 * HOUR)
  assert state.update(window(frames, 1504, 1510), PAIRS, START + 1510 * HOUR)[PAIRS[0]] is output


@pytest.mark.parametrize("invalid", [np.nan, np.inf, -np.inf, 0.0, -1.0])
def test_invalid_closes_are_one_unknown_class(invalid):
  frames = history(10)
  frames[PAIRS[0]].loc[4, "close"] = invalid
  state = RHourlyState(PAIRS)
  output = state.update(frames, PAIRS, START + 10 * HOUR)
  result = output[PAIRS[0]]
  assert [row.R_MARKET_COUNT for row in result[4:6]] == [2, 2]
  assert all(np.isnan(row.R_RETURN) for row in result[4:6])
  assert all(np.isnan(row.R_Z) and row.R_CUSUM == 0 and not row.R_UP_ALARM for row in result)
  frames[PAIRS[0]].loc[4, "close"] = -np.inf
  assert state.update(frames, PAIRS, START + 10 * HOUR) is output


def test_zero_variance_zero_scale_and_absent_subject_stay_unknown():
  constant = history()
  for frame in constant.values():
    frame["close"] = 100.0
  flat = RHourlyState(PAIRS).update(constant, PAIRS, START + 1700 * HOUR)
  assert all(np.isnan(row.R_BETA) and np.isnan(row.R_Z) for row in flat[PAIRS[0]])
  frames = history()
  single = RHourlyState([PAIRS[0]]).update({PAIRS[0]: frames[PAIRS[0]]}, [PAIRS[0]], START + 1700 * HOUR)
  assert single[PAIRS[0]][721].R_BETA == 1.0
  assert all(np.isnan(row.R_Z) and not row.R_UP_ALARM for row in single[PAIRS[0]])
  missing = RHourlyState([PAIRS[0]]).update({PAIRS[1]: frames[PAIRS[1]]}, PAIRS, START + 1700 * HOUR)
  assert all(row.R_MARKET_COUNT == 1 for row in missing[PAIRS[0]][1:])
  assert all(np.isnan(row.R_RETURN) and np.isnan(row.R_Z) for row in missing[PAIRS[0]])


def test_future_perturbation_cutoff_and_nonwhitelist_isolation():
  frames = history()
  cutoff = START + 1537 * HOUR
  before = {pair: frame.copy(deep=True) for pair, frame in frames.items()}
  expected = RHourlyState(PAIRS).update(window(frames, 0, 1537), PAIRS, cutoff)
  altered = {pair: frame.copy(deep=True) for pair, frame in frames.items()}
  for frame in altered.values():
    frame.loc[1537:, "close"] = 1e99
  altered["OUTSIDE"] = pd.DataFrame({"unrelated": ["not an hourly source"]})
  actual = RHourlyState(PAIRS).update(altered, PAIRS, cutoff)
  original = RHourlyState(PAIRS).update(frames, PAIRS, cutoff)
  for pair in PAIRS:
    assert_rows_equal(actual[pair], expected[pair])
    assert_rows_equal(original[pair], expected[pair])
    assert_frame_equal(frames[pair], before[pair], check_exact=True)
  state = RHourlyState([PAIRS[0]])
  too_early = state.update(frames, PAIRS, cutoff - pd.Timedelta(nanoseconds=1))
  assert too_early[PAIRS[0]][-1].date == START + 1535 * HOUR
  on_time = state.update(frames, PAIRS, cutoff)
  assert len(on_time[PAIRS[0]]) == 1
  assert on_time[PAIRS[0]][0].date == START + 1536 * HOUR
  assert on_time[PAIRS[0]][0].R_AVAILABLE_AT == cutoff


def test_output_subset_does_not_change_whitelist_market_or_subject():
  frames = history()
  all_pairs = RHourlyState(PAIRS).update(frames, PAIRS, START + 1700 * HOUR)
  subset = RHourlyState([PAIRS[1]]).update(frames, PAIRS, START + 1700 * HOUR)
  assert tuple(subset) == (PAIRS[1],)
  assert_rows_equal(subset[PAIRS[1]], all_pairs[PAIRS[1]])


def test_revision_validation_is_atomic_and_old_revisions_never_replay():
  frames = history()
  state = RHourlyState(PAIRS, retain_history=True)
  prefix = state.update(window(frames, 0, 1500), PAIRS, START + 1500 * HOUR)
  revised = {pair: frame.copy() for pair, frame in window(frames, 1400, 1510).items()}
  revised[PAIRS[-1]].loc[1490, "close"] *= 1.1
  with pytest.raises(ValueError, match="Committed close revision"):
    state.update(revised, PAIRS, START + 1510 * HOUR)
  assert state.update(window(frames, 0, 1500), PAIRS, START + 1500 * HOUR) is prefix
  result = state.update(window(frames, 1400, 1510), PAIRS, START + 1510 * HOUR)
  expected = RHourlyState(PAIRS).update(frames, PAIRS, START + 1510 * HOUR)
  for pair in PAIRS:
    assert_rows_equal(result[pair], expected[pair])
  old_revision = {pair: frame.copy() for pair, frame in frames.items()}
  old_revision[PAIRS[0]].loc[0, "close"] *= 1.5
  assert state.update(old_revision, PAIRS, START + 1510 * HOUR) is result


def test_whitelist_and_cutoff_changes_reject_without_state_loss():
  frames = history(10)
  state = RHourlyState([PAIRS[0]])
  first = state.update(frames, PAIRS, START + 5 * HOUR)
  for whitelist in (PAIRS[:2], (*PAIRS, "NEW"), (*PAIRS, PAIRS[0])):
    with pytest.raises(ValueError):
      state.update(frames, whitelist, START + 6 * HOUR)
  with pytest.raises(ValueError, match="backward"):
    state.update(frames, PAIRS, START + 4 * HOUR)
  assert state.update(frames, PAIRS, START + 5 * HOUR) is first
  after = state.update(frames, PAIRS, START + 6 * HOUR)
  assert len(after[PAIRS[0]]) == 1
  assert after[PAIRS[0]][0].date == START + 5 * HOUR


@pytest.mark.parametrize("bad", ["duplicate", "unordered", "unaligned", "naive", "nat"])
def test_structural_date_errors_raise_before_epoch_advances(bad):
  frames = history(10)
  if bad == "duplicate":
    frames[PAIRS[0]].loc[1, "date"] = frames[PAIRS[0]].loc[0, "date"]
  elif bad == "unordered":
    frames[PAIRS[0]] = frames[PAIRS[0]].iloc[::-1]
  elif bad == "unaligned":
    frames[PAIRS[0]].loc[1, "date"] += pd.Timedelta(minutes=1)
  elif bad == "naive":
    frames[PAIRS[0]]["date"] = frames[PAIRS[0]]["date"].dt.tz_localize(None)
  else:
    frames[PAIRS[0]].loc[1, "date"] = pd.NaT
  state = RHourlyState(PAIRS)
  with pytest.raises(ValueError):
    state.update(frames, PAIRS, START + 10 * HOUR)
  clean = history(10)
  recovered = state.update(clean, PAIRS, START + 10 * HOUR)
  expected = RHourlyState(PAIRS).update(clean, PAIRS, START + 10 * HOUR)
  for pair in PAIRS:
    assert_rows_equal(recovered[pair], expected[pair])


def test_empty_epoch_no_prehistory_and_missing_closed_tail():
  state = RHourlyState([PAIRS[0]])
  empty = state.update({}, PAIRS, START + 10 * HOUR)
  assert empty[PAIRS[0]] == ()
  assert state.update({}, PAIRS, START + 10 * HOUR) is empty
  frames = window(history(30), 10, 20)
  result = state.update(frames, PAIRS, START + 25 * HOUR)[PAIRS[0]]
  assert len(result) == 15
  assert result[0].date == START + 10 * HOUR
  assert result[-1].date == START + 24 * HOUR
  assert result[0].R_MARKET_COUNT == 0
  assert all(row.R_MARKET_COUNT == 0 for row in result[-5:])
  assert all(np.isnan(row.R_Z) for row in result)


def test_new_instance_on_short_buffer_is_a_new_unknown_epoch():
  frames = history()
  uninterrupted = RHourlyState([PAIRS[0]])
  uninterrupted.update(window(frames, 0, 1600), PAIRS, START + 1600 * HOUR)
  source = window(frames, 1590, 1610)
  continued = uninterrupted.update(source, PAIRS, START + 1610 * HOUR)[PAIRS[0]]
  restarted = RHourlyState([PAIRS[0]]).update(source, PAIRS, START + 1610 * HOUR)[PAIRS[0]]
  assert all(np.isfinite(row.R_Z) for row in continued)
  assert all(np.isnan(row.R_Z) and row.R_CUSUM == 0 for row in restarted)
  replay = RHourlyState([PAIRS[0]]).update(frames, PAIRS, START + 1610 * HOUR)[PAIRS[0]]
  assert_rows_equal(continued, replay[-10:])


def test_retained_full_year_surface_is_complete_and_only_requested_pairs():
  frames = history(8784)
  state = RHourlyState([PAIRS[0]], retain_history=True)
  state.update(window(frames, 0, 4392), PAIRS, START + 4392 * HOUR)
  result = state.update(window(frames, 4382, 8784), PAIRS, START + 8784 * HOUR)
  assert tuple(result) == (PAIRS[0],)
  assert len(result[PAIRS[0]]) == 8784
  assert [row.date for row in result[PAIRS[0]]] == list(pd.date_range(START, periods=8784, freq="1h"))
  assert all(row.R_AVAILABLE_AT == row.date + HOUR for row in result[PAIRS[0]])
  assert len(state._raw) == 721
  assert state._returns.shape == state._residuals.shape == (720, 1)
