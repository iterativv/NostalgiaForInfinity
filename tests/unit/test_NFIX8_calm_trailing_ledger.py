"""Real fees, fills, funding, reductions and diagnostic ledger probes."""

import copy
import json
from datetime import timedelta

import pytest

from tests.unit import calm_trailing_fixtures as f

database = f.database


@pytest.mark.parametrize(
  "exit_price,rate,cash,admitted",
  [
    (80.0, 110.0, -140.93, False),
    (120.0, 90.0, 138.93, True),
  ],
)
@pytest.mark.parametrize("futures", [False, True])
def test_lifecycle_cash_when_real_reduction_changes_sign(
  database,
  tmp_path,
  exit_price,
  rate,
  cash,
  admitted,
  futures,
):
  # Given
  case = f.make_case(tmp_path, futures=futures)
  f.fill(case.trade, case.trade.exit_side, 8.0, exit_price, requested=9.0)
  f.fill(case.trade, case.trade.entry_side, 0.0, 70.0, requested=9.0, pending=True)
  case.emit()
  before = f.order_ledger(case)
  assert case.ledger(rate)[0] == pytest.approx(cash)
  assert (case.trade.calc_profit_ratio(rate) > 0.0) is not admitted
  # When
  result = case.call(rate=rate)
  # Then
  assert result is None
  assert case.marker()["active"] is admitted
  assert f.order_ledger(case) == before


@pytest.mark.parametrize(
  "funding,cash,admitted",
  [
    (0.0, -1.0, False),
    (1.0, 0.0, False),
    (1.01, 0.01, True),
    (-3.0, -4.0, False),
  ],
)
def test_fee_and_funding_cash_when_callback_ratio_zero(
  database,
  tmp_path,
  funding,
  cash,
  admitted,
):
  # Given
  case = f.make_case(tmp_path)
  case.trade.funding_fees = funding
  assert case.ledger(100.0)[0] == pytest.approx(cash)
  case.emit()
  # When
  case.call(rate=100.0)
  # Then
  assert case.marker()["active"] is admitted


@pytest.mark.parametrize("funding", [float("nan"), float("inf"), -float("inf")])
def test_ineligible_first_opportunity_when_real_cash_nonfinite(database, tmp_path, funding):
  # Given
  case = f.make_case(tmp_path)
  case.trade.funding_fees = funding
  case.emit()
  # When
  case.call()
  # Then
  assert case.marker()["consumed"] is True
  assert case.marker()["active"] is False


def test_order_ledger_when_repeated_intents_unfilled(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  f.fill(case.trade, case.trade.exit_side, 0.0, 88.0, requested=10.0, pending=True)
  case.emit()
  case.call()
  case.native.side_effect = None
  before = f.order_ledger(case)
  case.call(60, 88.0)
  marker = copy.deepcopy(case.marker())
  # When
  result = case.call(120, 80.0)
  # Then
  assert result == f.REASON
  assert case.marker() == marker
  assert f.order_ledger(case) == before


def test_callback_diagnostic_when_trail_closes_at_lifecycle_loss(
  database,
  tmp_path,
  record_property,
):
  # Given
  case = f.make_case(tmp_path)
  f.actual_native(case)
  case.call()
  admitted = copy.deepcopy(case.marker())
  orders_before = f.order_ledger(case)
  # When
  result = case.call(60, 88.0)
  # Then: an intent is not a fill, and may close at a lifecycle loss.
  assert result == f.REASON
  assert case.ledger(88.0)[0] < 0.0
  assert f.order_ledger(case) == orders_before
  record_property(
    "m_callback_evidence",
    json.dumps(
      {
        "trade_id": case.trade.id,
        "pair": case.trade.pair,
        "side": "short" if case.trade.is_short else "long",
        "open_timestamp": case.trade.open_date_utc.isoformat(),
        "enabled": case.strategy.risk_calm_trail_enable,
        "stress": 19.0,
        "native_candidate": admitted["reason"],
        "admitted_at": admitted["admitted_at"],
        "admitted_rate": admitted["admitted_rate"],
        "peak_before": admitted["peak"],
        "peak_after": case.marker()["peak"],
        "trail_boundary": case.marker()["peak"] * 0.80,
        "callback_rate": 88.0,
        "callback_timestamp": (f.NOW + timedelta(seconds=60)).isoformat(),
        "exit_intent": result,
        "actual_exit_fill_rate": None,
        "orders": [
          {
            "order_id": order.order_id,
            "filled": order.safe_filled,
            "side": order.ft_order_side,
            "tag": order.ft_order_tag,
          }
          for order in case.trade.orders
        ],
        "state_end_reason": case.marker()["ended"],
        "cache_episode_active": case.marker()["episode"],
        "lifecycle_cash": case.ledger(88.0)[0],
      },
      allow_nan=False,
    ),
  )


def test_no_second_admission_when_first_cash_was_ineligible(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call(rate=100.0)
  assert case.marker()["active"] is False
  case.strategy._remove_profit_target(case.trade.pair)
  case.trade.funding_fees = 1000.0
  case.emit(stamp=f.NOW + timedelta(seconds=60))
  # When
  case.call(60)
  # Then
  assert case.marker()["active"] is False
  assert case.marker()["consumed"] is True
