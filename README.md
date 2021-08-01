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

### Hyperopt values to raw values

The strategy uses hyperopt values; this has some compute overhead and thus impact runtime performance with the number of parameters available in the strategy. There is a script available to transform all hyperopt values into raw values. E.g. The following line of code:

```buy_dip_threshold_10_1 = DecimalParameter(0.001, 0.05, default=0.015, space='buy', decimals=3, optimize=False, load=True)```

Would be transformed to:

```buy_dip_threshold_10_1 = 0.015```

### Command reference
```
usage: ho_to_raw_codemod.py [-h] [--input INPUT_PATH] [--output OUTPUT_PATH]

optional arguments:
  -h, --help            show this help message and exit
  --input INPUT_PATH, -i INPUT_PATH
                        Strategy path
  --output OUTPUT_PATH, -o OUTPUT_PATH
                        Output of transformed file
```

The script has a simple CLI, where it accepts two arguments, the input, which would be the strategy path and the output,  which is the path of the transformed file. E.g.

`python codemods/ho_to_raw_codemod.py -i NostalgiaForInfinityNext.py -o NostalgiaForInfinityNext_Raw.py`

