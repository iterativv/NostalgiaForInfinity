## Hold support

### Specific Trades

In case you want to have SOME of the trades to only be sold when on profit, add a file named "nfi-hold-trades.json" in your `user_data/` directory

The contents should be similar to:

`{"trade_ids": [1, 3, 7], "profit_ratio": 0.005}`

Or, for individual profit ratios (Notice the trade ID's as strings):

`{"trade_ids": {"1": 0.001, "3": -0.005, "7": 0.05}}`

NOTE:

- `trade_ids` is a list of integers, the trade ID's, which you can get from the logs or from the output of the telegram `/status` command.
- Regardless of the defined profit ratio(s), the strategy MUST still produce a SELL signal for the HOLD support logic to run, which is to say, the trade will sell only if there's a proper sell signal AND the profit target has been reached.
- This feature can be completely disabled by changing `hold_support_enabled = True` to false in the strategy file.

### Specific Pairs

In case you want to have some pairs to always be on held until a specific profit, using the same "nfi-hold-trades.json" file add something like:

`{"trade_pairs": {"BTC/USDT": 0.001, "ETH/USDT": -0.005}}`

### Specific Trades and Pairs

It is also valid to include specific trades and pairs on the holds file, for example:

`{"trade_ids": {"1": 0.001}, "trade_pairs": {"BTC/USDT": 0.001}}`
