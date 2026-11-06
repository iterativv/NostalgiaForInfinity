from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import State
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.wallets import Wallets

from tests.unit import test_NFIX8_v4_grind_funding as funding_tests


NOW = funding_tests.NOW
v4_case = funding_tests.v4_case


@pytest.fixture(
  params=[
    (version, level, "grind")
    for version in ("system_v4", None, "system_v3", "system_v3_1", "system_v3_2")
    for level in range(1, 6)
  ]
  + [(None, 1, "buyback"), (None, 2, "buyback")]
)
def funding_case(request):
  return request.param


@pytest.fixture
def level(funding_case):
  return funding_case[1]


@pytest.fixture
def funded_grind_case(funding_case, v4_case, level):
  strategy, trade, rate = v4_case
  version, _, mode = funding_case
  trade.set_custom_data("system_version", version)
  if version != "system_v4":
    prefix = "grinding_v2" if version is None else "system_v3"
    for name in dir(strategy):
      if name.startswith(("grinding_v2_", "system_v3_", "system_v3_1_")) and name.endswith("_enable"):
        setattr(strategy, name, False)
    setattr(strategy, f"{prefix}_grind_{level}_enable", True)
    setattr(strategy, f"{prefix}_grind_{level}_use_derisk", True)
    for market in ("spot", "futures"):
      stakes = f"{prefix}_grind_{level}_stakes_{market}"
      setattr(strategy, stakes, [0.15] * len(getattr(strategy, stakes)))
      setattr(strategy, f"{prefix}_grind_{level}_derisk_{market}", -0.01)
    trade.orders[1].ft_order_tag = "derisk_level_1"
    strategy.long_buyback_entry_v2 = MagicMock(return_value=False)
    strategy.short_buyback_entry_v2 = MagicMock(return_value=False)
    strategy.long_buyback_entry_v3 = MagicMock(return_value=False)
    strategy.long_rebuy_entry_v3 = MagicMock(return_value=False)
    strategy.short_rebuy_entry_v3 = MagicMock(return_value=False)
    strategy._grind_entry_tag = "funding-case"
    frame, _ = strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
    frame = frame.assign(
      RSI_3_1h=50.0,
      AROONU_14_15m=100.0,
      AROOND_14_15m=100.0,
      protections_long_global=False,
      protections_short_global=False,
    )
    strategy.dp._set_cached_df(trade.pair, "5m", frame, strategy.config["candle_type_def"])
    if mode == "buyback":
      setattr(strategy, f"{prefix}_grind_{level}_enable", False)
      setattr(strategy, f"{prefix}_buyback_{level}_enable", True)
      setattr(strategy, f"{prefix}_buyback_{level + 1}_use_derisk", True)
      trade.orders[1].ft_order_tag = f"derisk_level_{level}"
      trade.orders[-1].ft_order_tag = f"buyback_{level + 1}_entry"
      for market in ("spot", "futures"):
        setattr(strategy, f"{prefix}_buyback_{level}_stake_{market}", 0.15)
        setattr(strategy, f"{prefix}_buyback_{level + 1}_derisk_{market}", -0.01)
  return strategy, trade, rate


@pytest.mark.parametrize(
  "funding_ratio,exchange_ratio,minimum",
  [
    (0.0, 100.0, 5.0),
    (0.999, 100.0, 5.0),
    (1.0, 100.0, 5.0),
    (1.25, 100.0, 5.0),
    (10.0, 1.0, 5.0),
    (10.0, 0.999, 5.0),
    (0.999, 100.0, 200.0),
    (1.0, 100.0, 200.0),
  ],
  ids=[
    "empty",
    "below-wallet",
    "exact-wallet",
    "funded",
    "exact-exchange",
    "below-exchange",
    "uplift-below",
    "uplift-exact",
  ],
)
@pytest.mark.parametrize("entry_signal", [False, True])
def test_engine_reaches_reduction_when_addition_cannot_execute(
  funded_grind_case, funding_case, level, mocker, funding_ratio, exchange_ratio, minimum, entry_signal
):
  strategy, trade, rate = funded_grind_case
  _, _, mode = funding_case
  strategy.long_grind_entry_v4 = MagicMock(return_value=entry_signal)
  strategy.short_grind_entry_v4 = MagicMock(return_value=entry_signal)
  strategy.long_grind_entry_v3 = MagicMock(return_value=entry_signal)
  strategy.short_grind_entry_v2 = MagicMock(return_value=entry_signal)
  strategy.short_grind_entry_v3 = MagicMock(return_value=entry_signal)
  strategy.long_buyback_entry_v2 = MagicMock(return_value=entry_signal)
  strategy.short_buyback_entry_v2 = MagicMock(return_value=entry_signal)
  entry_stake = max(150.0 / trade.leverage, minimum * 1.5)
  free_stake = entry_stake * funding_ratio
  exchange_limit = entry_stake * exchange_ratio
  grind_order_id = trade.orders[-1].id
  strategy.config.update(
    dry_run=True,
    dry_run_wallet=trade.stake_amount - trade.realized_profit + free_stake,
    tradable_balance_ratio=1.0,
    trading_mode=trade.trading_mode,
  )
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.config = strategy.config
  bot.strategy = strategy
  bot.trading_mode = trade.trading_mode
  bot.state = State.RUNNING
  bot._exit_reason_cache = {}
  # Mock exchange/RPC boundaries, keeping actual wallet and order creation logic.
  bot.exchange = MagicMock()
  bot.exchange.get_proxy_coin.return_value = "USDT"
  bot.exchange.get_pair_base_currency.return_value = "ETH"
  bot.exchange.get_rates.return_value = (rate, rate)
  bot.exchange.get_min_pair_stake_amount.return_value = minimum
  bot.exchange.get_max_pair_stake_amount.return_value = exchange_limit
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: round(amount, 8)
  bot.exchange.get_funding_fees.return_value = 0.0

  def create_order(**kwargs):
    return {
      "id": "v4-grind-reduction",
      "symbol": trade.pair,
      "type": "limit",
      "side": kwargs["side"],
      "status": "open",
      "price": kwargs["rate"],
      "amount": kwargs["amount"],
      "filled": 0.0,
      "remaining": kwargs["amount"],
      "cost": 0.0,
      "timestamp": int(NOW.timestamp() * 1000),
    }

  bot.exchange.create_order.side_effect = create_order
  bot.wallets = Wallets(bot.config, bot.exchange)
  bot._notify_exit = MagicMock()
  bot.execute_entry = MagicMock()
  mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now.return_value = NOW
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  assert bot.wallets.get_available_stake_amount() == pytest.approx(free_stake)

  bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  assert adjustment.call_args.kwargs["max_stake"] == pytest.approx(min(free_stake, exchange_limit))
  if entry_signal and min(funding_ratio, exchange_ratio) >= 1.0:
    bot.execute_entry.assert_called_once_with(
      trade.pair,
      entry_stake,
      price=rate,
      trade=trade,
      is_short=trade.is_short,
      mode="pos_adjust",
      enter_tag=f"{mode}_{level}_entry",
    )
    bot.exchange.create_order.assert_not_called()
  elif minimum == 200.0:
    bot.execute_entry.assert_not_called()
    bot.exchange.create_order.assert_not_called()
  else:
    bot.execute_entry.assert_not_called()
    bot.exchange.create_order.assert_called_once()
    order_args = bot.exchange.create_order.call_args.kwargs
    assert order_args["side"] == trade.exit_side
    assert order_args["reduceOnly"] == (trade.leverage > 1)
    assert order_args["amount"] == pytest.approx(1.0)
    exit_level = level + 1 if mode == "buyback" else level
    assert trade.orders[-1].ft_order_tag == f"{mode}_{exit_level}_derisk {grind_order_id}"
    assert trade.orders[-1].ft_is_open


@pytest.mark.parametrize("funding_case", [(None, 1, "grind"), ("system_v3_2", 1, "grind")], indirect=True)
@pytest.mark.parametrize("guard", ["open-order", "disabled-stop"])
def test_unfunded_entry_preserves_existing_exit_guards(funded_grind_case, funding_case, guard):
  strategy, trade, _ = funded_grind_case
  strategy.long_grind_entry_v3 = MagicMock(return_value=True)
  strategy.short_grind_entry_v2 = MagicMock(return_value=True)
  strategy.short_grind_entry_v3 = MagicMock(return_value=True)
  if guard == "open-order":
    funding_tests.fill(trade, trade.entry_side, 1.0, 100.0, "grind_1_entry", filled=0.0)
    trade.orders[-1].ft_is_open = True
    trade.orders[-1].status = "open"
  else:
    prefix = "grinding_v2" if funding_case[0] is None else "system_v3"
    setattr(strategy, f"{prefix}_grind_1_use_derisk", False)

  assert funding_tests.adjust(funded_grind_case, 0.0) is None
