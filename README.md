# NostalgiaForInfinity
Trading strategy for the [Freqtrade](https://www.freqtrade.io) crypto bot

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
git submodule update --remote --recursive
```


## Change strategy

Add strategies to the [user_data/strategies](user_data/strategies) folder and also in the [docker-compose.yml](docker-compose.yml) file at `strategy-list` add your strategy in the list.

## General Recommendations

For optimal performance, suggested to use between 4 and 6 open trades, with unlimited stake.

A pairlist with 40 to 80 pairs. Volume pairlist works well.

Prefer stable coin (USDT, BUSD etc) pairs, instead of BTC or ETH pairs.

Highly recommended to blacklist leveraged tokens (*BULL, *BEAR, *UP, *DOWN etc).

Ensure that you don't override any variables in you config.json. Especially the timeframe (must be 5m).

* `use_sell_signal` must set to true (or not set at all).
* `sell_profit_only` must set to false (or not set at all).
* `ignore_roi_if_buy_signal` must set to true (or not set at all).

## Donations

Absolutely not required. However, will be accepted as a token of appreciation.

* BTC: `bc1qvflsvddkmxh7eqhc4jyu5z5k6xcw3ay8jl49sk`
* ETH (ERC20): `0x83D3cFb8001BDC5d2211cBeBB8cB3461E5f7Ec91`
* BEP20/BSC (ETH, BNB, ...): `0x86A0B21a20b39d16424B7c8003E4A7e12d78ABEe`

### Referral Links

If you like to help, you can also use the following links to sign up to various exchanges:

* Binance: https://accounts.binance.com/en/register?ref=37365811
* Kucoin: https://www.kucoin.com/ucenter/signup?rcode=rJTLZ9K
