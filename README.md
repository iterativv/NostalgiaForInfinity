# NostalgiaForInfinity
Trading strategy for the [Freqtrade](https://www.freqtrade.io) crypto bot. For backtesting results, check out the comments in the individual [commit](https://github.com/iterativv/NostalgiaForInfinity/commits/main) page.

## Clone The Repository
If you plan to only clone the repository to use the strategy, a regular ``git clone`` will do.

However, if you plan on running additional strategies or run the test suite, you need to clone
the repository and it's submodules.

### Newer versions of Git

```bash
git clone --recurse-submodules https://github.com/iterativv/NostalgiaForInfinity.git checkout-path
```

### Older versions of Git

```bash
git clone --recursive https://github.com/iterativv/NostalgiaForInfinity.git checkout-path
```

### Existing Checkouts
```
git submodule update --remote --checkout
```


## Change strategy

Add strategies to the [user_data/strategies](user_data/strategies) folder and also in the [docker-compose.yml](docker-compose.yml) file at `strategy-list` add your strategy in the list.

[Additional Information : NFINext is a older strategy on 5m tf , NFI-NG is a 15m tf stategy abandoned mid development , NFIX is the currently developed strategy (a rework of NG on 5m tf)]

## General Recommendations

For optimal performance, suggested to use between 4 and 6 open trades, with unlimited stake.

A pairlist with 40 to 80 pairs. Volume pairlist works well.

Prefer stable coin (USDT, BUSD etc) pairs, instead of BTC or ETH pairs.

Highly recommended to blacklist leveraged tokens (*BULL, *BEAR, *UP, *DOWN etc).

Ensure that you don't override any variables in you config.json. Especially the timeframe (must be 5m).

* `use_exit_signal` must set to true (or not set at all).
* `exit_profit_only` must set to false (or not set at all).
* `ignore_roi_if_entry_signal` must set to true (or not set at all).

## Hold support

### Specific Trades

  In case you want to have SOME of the trades to only be sold when on profit, add a file named "nfi-hold-trades.json" in your `user_data/` directory

  The contents should be similar to:

  `{"trade_ids": [1, 3, 7], "profit_ratio": 0.005}`

  Or, for individual profit ratios (Notice the trade ID's as strings):

  `{"trade_ids": {"1": 0.001, "3": -0.005, "7": 0.05}}`

  NOTE:
   * `trade_ids` is a list of integers, the trade ID's, which you can get from the logs or from the output of the telegram `/status` command.
   * Regardless of the defined profit ratio(s), the strategy MUST still produce a SELL signal for the HOLD support logic to run, which is to say, the trade will sell only if there's a proper sell signal AND the profit target has been reached.
   * This feature can be completely disabled by changing `hold_support_enabled = True` to false in the strategy file.

### Specific Pairs

  In case you want to have some pairs to always be on held until a specific profit, using the same "nfi-hold-trades.json" file add something like:

  `{"trade_pairs": {"BTC/USDT": 0.001, "ETH/USDT": -0.005}}`

### Specific Trades and Pairs

  It is also valid to include specific trades and pairs on the holds file, for example:

  `{"trade_ids": {"1": 0.001}, "trade_pairs": {"BTC/USDT": 0.001}}`

## Donations

Absolutely not required. However, will be accepted as a token of appreciation.

* BTC: `bc1qvflsvddkmxh7eqhc4jyu5z5k6xcw3ay8jl49sk`
* ETH (ERC20): `0x83D3cFb8001BDC5d2211cBeBB8cB3461E5f7Ec91`
* BEP20/BSC (USDT, ETH, BNB, ...): `0x86A0B21a20b39d16424B7c8003E4A7e12d78ABEe`
* TRC20/TRON (USDT, TRON, ...): `TTAa9MX6zMLXNgWMhg7tkNormVHWCoq8Xk`

* Patreon : https://www.patreon.com/iterativ

### Referral Links

If you like to help, you can also use the following links to sign up to various exchanges:

* Binance: https://accounts.binance.com/en/register?ref=C68K26A9 (20% discount on trading fees)
* Kucoin: https://www.kucoin.com/r/af/QBSSS5J2 (20% lifetime discount on trading fees)
* Gate.io: https://www.gate.io/signup/8054544 (20% discount on trading fees)
* OKX: https://www.okx.com/join/11749725931 (20% discount on trading fees)
* MEXC: https://promote.mexc.com/a/nfi  (10% discount on trading fees)
* ByBit: https://partner.bybit.com/b/nfi
* Huobi: https://www.huobi.com/en-us/v/register/double-invite/?inviter_id=11345710&invite_code=ubpt2223 (20% discount on trading fees)
* Bitvavo: https://account.bitvavo.com/create?a=D22103A4BC (no fees for the first € 1000)

### Discord Link

This is where we chat, hangout and contribute as a community

* [Discord](https://discord.gg/DeAmv3btxQ)
