from copy import deepcopy

import pytest

from tools.calm_profit_trailing.reproduce import order_signature


def record():
  return {
    "pair": "ETH/USDT:USDT",
    "trade_open": 1673275200000,
    "order": {
      "amount": 39.0,
      "safe_price": 100.0,
      "ft_order_side": "buy",
      "order_filled_timestamp": 1673275200000,
      "ft_is_entry": True,
      "ft_order_tag": "161",
      "cost": 3900.0,
    },
  }


def test_json_integer_and_float_quantities_are_equal():
  actual = record()
  published = deepcopy(actual)
  for key in ("amount", "safe_price", "cost"):
    published["order"][key] = int(published["order"][key])
  assert order_signature(actual) == order_signature(published)


@pytest.mark.parametrize(
  "key,value",
  [
    ("amount", 39.00000001),
    ("safe_price", 100.00000001),
    ("cost", 3900.00000001),
    ("ft_order_side", "sell"),
    ("ft_order_tag", "different"),
    ("order_filled_timestamp", 1673275200001),
  ],
)
def test_different_executed_order_does_not_match(key, value):
  actual = record()
  changed = deepcopy(actual)
  changed["order"][key] = value
  assert order_signature(actual) != order_signature(changed)


@pytest.mark.parametrize("key,value", [("pair", "BTC/USDT:USDT"), ("trade_open", 1673275200001)])
def test_different_position_does_not_match(key, value):
  actual = record()
  changed = deepcopy(actual)
  changed[key] = value
  assert order_signature(actual) != order_signature(changed)
