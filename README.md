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

## BackTest locally

Install [Docker Compose](https://docs.docker.com/compose/install/).

Run the backtesting command:

```bash
docker-compose run --rm backtesting
```

## Test locally

Install [Docker Compose](https://docs.docker.com/compose/install/).

Run the tests command:

```bash
docker-compose run --rm tests
```

## Configure run

If you want to change `--max-open-trades` or `--stake-amount` or `--timerange` change the [.env](.env) file.


## Update pairs or timeframe

### From the [NostalgiaForInfinityData](https://github.com/iterativv/NostalgiaForInfinityData) repository
```bash
git submodule update --remote --checkout
```

### Locally

If you want to update pairs [user_data/data/pairlists.json](user_data/data/pairlists.json) from `exchange:pair_whitelist` or timeframe from [docker-compose.yml](docker-compose.yml) from `download-data:timerange`, run the following after you changed.

```bash
docker-compose run --rm download-data
```

**Do note that this will update the data locally on the git submodule. But it should still work.**

### Updating Pairs or Timeframe - Long Term

To update either the pair list or the downloaded data time frames, please check
[NostalgiaForInfinityData](https://github.com/iterativv/NostalgiaForInfinityData) and proceed from there.

Once the necessary changes are done in [NostalgiaForInfinityData](https://github.com/iterativv/NostalgiaForInfinityData) run the following:

```bash
git submodule update --remote --merge
```

Now commit the changes and push.
