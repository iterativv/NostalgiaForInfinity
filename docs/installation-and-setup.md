# Installation and Setup

<cite>
**Referenced Files in This Document**   
- [README.md](file://README.md)
- [docker-compose.yml](file://docker-compose.yml)
- [docker-compose.tests.yml](file://docker-compose.tests.yml)
- [pyproject.toml](file://pyproject.toml)
- [configs/recommended_config.json](file://configs/recommended_config.json)
- [configs/exampleconfig_secret.json](file://configs/exampleconfig_secret.json)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py)
</cite>

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Cloning the Repository](#cloning-the-repository)
3. [Setting Up Python Environment](#setting-up-python-environment)
4. [Installing TA-Lib](#installing-ta-lib)
5. [Installing Dependencies via pyproject.toml](#installing-dependencies-via-pyprojecttoml)
6. [Configuring Freqtrade](#configuring-freqtrade)
7. [Setting Up API Keys and Exchange Credentials](#setting-up-api-keys-and-exchange-credentials)
8. [Running with Docker](#running-with-docker)
9. [Validating Configuration and Strategy](#validating-configuration-and-strategy)
10. [Troubleshooting Common Issues](#troubleshooting-common-issues)
11. [Security Best Practices](#security-best-practices)

## Prerequisites

Before setting up the NostalgiaForInfinityX6 strategy, ensure the following prerequisites are met:

- **Python 3.9+**: The strategy requires Python 3.9 or higher. The `pyproject.toml` file specifies `requires-python = ">=3.12"`, so Python 3.12 or later is recommended.
- **Freqtrade Installation**: Freqtrade must be installed either locally or via Docker. The repository uses Freqtrade as the trading bot framework.
- **API Keys for Target Exchanges**: You need valid API keys from your chosen cryptocurrency exchange (e.g., Binance, OKX, Kucoin). These keys allow the bot to interact with the exchange for trading.
- **Basic Understanding of Trading Bots**: Familiarity with how trading bots operate, including concepts like dry-run mode, backtesting, and live trading, is essential for proper configuration and monitoring.

**Section sources**
- [pyproject.toml](file://pyproject.toml#L4-L7)
- [README.md](file://README.md#L1-L57)

## Cloning the Repository

To begin, clone the NostalgiaForInfinityX6 repository from GitHub:

```bash
git clone https://github.com/iterativv/NostalgiaForInfinity.git
cd NostalgiaForInfinity
```

This will download the complete project structure, including strategies, configuration files, Docker setups, and test scripts.

**Section sources**
- [README.md](file://README.md#L1-L57)

## Setting Up Python Environment

It is highly recommended to use a virtual environment to manage dependencies and avoid conflicts with other Python projects.

### Create a Virtual Environment

```bash
python -m venv venv
```

### Activate the Virtual Environment

- On Windows:
  ```bash
  venv\Scripts\activate
  ```
- On macOS/Linux:
  ```bash
  source venv/bin/activate
  ```

Once activated, all subsequent Python and pip commands will use this isolated environment.

**Section sources**
- [pyproject.toml](file://pyproject.toml#L4-L7)

## Installing TA-Lib

The NostalgiaForInfinityX6 strategy relies on TA-Lib for technical indicator calculations. Install TA-Lib using the following steps:

### For Windows:
Download the precompiled TA-Lib wheel from [Christoph Gohlke's website](https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib) and install it using pip:

```bash
pip install TA_Lib‑0.4.24‑cp312‑cp312‑win_amd64.whl
```

### For macOS:
```bash
brew install ta-lib
pip install TA-Lib
```

### For Linux (Ubuntu/Debian):
```bash
sudo apt-get install build-essential wget
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
cd ..
pip install TA-Lib
```

Verify installation by running:
```python
import talib
print(talib.__version__)
```

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L4-L5)

## Installing Dependencies via pyproject.toml

The project uses `pyproject.toml` for dependency management. With your virtual environment activated, install the required packages:

```bash
pip install -e .
```

This command installs the project in editable mode along with its dependencies, which currently include only `freqtrade`. The installation respects the Python version constraint specified in the file.

**Section sources**
- [pyproject.toml](file://pyproject.toml#L1-L10)

## Configuring Freqtrade

Proper configuration is crucial for the strategy to function correctly.

### Copy Recommended Configuration

Start by copying the recommended configuration file to your Freqtrade user data directory:

```bash
cp configs/recommended_config.json user_data/config.json
```

The `recommended_config.json` file contains essential settings, including the strategy name and a list of additional configuration files to load:

```json
{
  "strategy": "NostalgiaForInfinityX6",
  "add_config_files": [
    "../configs/trading_mode-spot.json",
    "../configs/pairlist-volume-binance-usdt.json",
    "../configs/blacklist-binance.json",
    "../configs/exampleconfig.json",
    "../configs/exampleconfig_secret.json"
  ]
}
```

These files define trading mode, pair selection, blacklists, and secret credentials.

**Section sources**
- [configs/recommended_config.json](file://configs/recommended_config.json#L1-L18)

## Setting Up API Keys and Exchange Credentials

Sensitive credentials should be stored securely.

### Copy and Edit Secret Configuration

```bash
cp configs/exampleconfig_secret.json user_data/config-private.json
```

Edit `user_data/config-private.json` to add your exchange API credentials:

```json
"exchange": {
  "name": "binance",
  "key": "YOUR_API_KEY",
  "secret": "YOUR_API_SECRET",
  "password": "YOUR_API_PASSWORD"  // if required by exchange
}
```

Ensure `dry_run` is set to `true` during initial testing.

**Section sources**
- [configs/exampleconfig_secret.json](file://configs/exampleconfig_secret.json#L1-L86)

## Running with Docker

Docker provides an isolated and reproducible environment for running the bot.

### Production Setup with docker-compose.yml

The `docker-compose.yml` file defines the production setup:

```yaml
services:
  freqtrade:
    <<: *common-settings
    container_name: ${FREQTRADE__BOT_NAME:-Example_Test_Account}_${FREQTRADE__EXCHANGE__NAME:-binance}_${FREQTRADE__TRADING_MODE:-futures}-${FREQTRADE__STRATEGY:-NostalgiaForInfinityX6}
    ports:
      - "${FREQTRADE__API_SERVER__LISTEN_PORT:-8080}:${FREQTRADE__API_SERVER__LISTEN_PORT:-8080}"
    command: >
      trade
      --db-url sqlite:////freqtrade/user_data/${FREQTRADE__BOT_NAME:-Example_Test_Account}_${FREQTRADE__EXCHANGE__NAME:-binance}_${FREQTRADE__TRADING_MODE:-futures}-tradesv3.sqlite
      --log-file user_data/logs/${FREQTRADE__BOT_NAME:-Example_Test_Account}-${FREQTRADE__EXCHANGE__NAME:-binance}-${FREQTRADE__STRATEGY:-NostalgiaForInfinityX6}-${FREQTRADE__TRADING_MODE:-futures}.log
      --strategy-path .
```

To start the bot in dry-run mode:

```bash
docker-compose up
```

Environment variables can be set in a `.env` file or passed directly.

### Testing Setup with docker-compose.tests.yml

For backtesting and analysis, use the testing configuration:

```bash
docker-compose -f docker-compose.tests.yml up backtesting
```

This runs backtesting with predefined parameters and time ranges. Other services like `backtesting-analysis`, `plot-dataframe`, and `plot-profit` are available for detailed performance evaluation.

**Section sources**
- [docker-compose.yml](file://docker-compose.yml#L1-L37)
- [docker-compose.tests.yml](file://docker-compose.tests.yml#L1-L386)

## Validating Configuration and Strategy

Before going live, validate that everything is set up correctly.

### Check Strategy Loading

Run the bot in dry-run mode to verify the strategy loads:

```bash
freqtrade trade --config user_data/config.json --strategy NostalgiaForInfinityX6 --dry-run
```

Look for log messages confirming the strategy has been loaded and indicators are being calculated.

### Validate Configuration

Use Freqtrade's built-in configuration validation:

```bash
freqtrade check --config user_data/config.json
```

This command checks for syntax errors and missing required fields.

### Backtest the Strategy

Perform a backtest to ensure the strategy behaves as expected:

```bash
freqtrade backtesting --config user_data/config.json --strategy NostalgiaForInfinityX6 --timerange 20230101-20231231
```

Review the results in the `user_data/backtest_results/` directory.

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L68-L822)
- [configs/recommended_config.json](file://configs/recommended_config.json#L1-L18)

## Troubleshooting Common Issues

### Missing Dependencies

If you encounter import errors (e.g., `ModuleNotFoundError: No module named 'talib'`), ensure TA-Lib is installed correctly and that you are using the correct Python environment.

### Authentication Failures

- Verify API keys are copied correctly without extra spaces.
- Ensure the exchange name in `config-private.json` matches Freqtrade's expected format (e.g., `"binance"`, `"okx"`).
- Check that the API key has the necessary permissions (trading enabled).

### Configuration Syntax Errors

Use a JSON validator to check `config.json` and `config-private.json` for syntax errors like missing commas or unmatched brackets.

### Strategy Not Loading

- Confirm the strategy file `NostalgiaForInfinityX6.py` is located in `user_data/strategies/`.
- Ensure the class name in the Python file matches the strategy name in the config (`NostalgiaForInfinityX6`).

**Section sources**
- [configs/exampleconfig_secret.json](file://configs/exampleconfig_secret.json#L1-L86)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L1)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L68-L822)

## Security Best Practices

- **Never Commit Secrets**: Ensure `config-private.json` and `.env` files are not committed to version control. The repository should already include these in `.gitignore`.
- **Use Limited-Permission API Keys**: Create API keys with only the permissions necessary (e.g., trade, but not withdraw).
- **Store Secrets Securely**: Keep API keys in a secure location, preferably using a secrets manager in production.
- **Regularly Rotate Keys**: Periodically regenerate API keys to minimize the impact of potential leaks.
- **Monitor Logs**: Avoid logging sensitive information. Freqtrade generally handles this well, but custom logging should be reviewed.

**Section sources**
- [configs/exampleconfig_secret.json](file://configs/exampleconfig_secret.json#L1-L86)
- [docker-compose.yml](file://docker-compose.yml#L1-L37)
