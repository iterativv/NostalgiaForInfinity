# Advanced Configuration

<cite>
**Referenced Files in This Document**   
- [exampleconfig_secret.json](file://configs/exampleconfig_secret.json)
- [proxy-binance.json](file://configs/proxy-binance.json)
- [recommended_config.json](file://configs/recommended_config.json)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Secure Configuration with exampleconfig_secret.json](#secure-configuration-with-exampleconfig_secretjson)
3. [Proxy Configuration with proxy-binance.json](#proxy-configuration-with-proxy-binancejson)
4. [Advanced Strategy Parameters in recommended_config.json](#advanced-strategy-parameters-in-recommended_configjson)
5. [Custom Parameters and Position Management](#custom-parameters-and-position-management)
6. [Debugging Complex Configurations](#debugging-complex-configurations)
7. [Security and Risk Mitigation](#security-and-risk-mitigation)

## Introduction
This document provides a comprehensive guide to advanced configuration options for the NostalgiaForInfinityX6 trading strategy. It covers secure handling of sensitive data, network proxy configuration for restricted regions, and fine-grained control over trading behaviors through complex parameter structures. The documentation focuses on practical implementation details, security best practices, and real-world examples drawn directly from the codebase.

## Secure Configuration with exampleconfig_secret.json

The `exampleconfig_secret.json` file serves as a template for securely storing sensitive information required by the trading bot. This configuration file contains critical credentials and API endpoints that must be protected from unauthorized access.

```json
{
  "bot_name": "freqtrade",
  "stake_currency": "USDT",
  "fiat_display_currency": "USD",
  "strategy": "NostalgiaForInfinityX6",
  "dry_run": true,
  "exchange": {
    "name": "binance",
    "key": "",
    "password": "",
    "secret": "",
    "walletAddress": "",
    "privateKey": "",
    "ccxt_config": {},
    "ccxt_async_config": {}
  },
  "telegram": {
    "enabled": false,
    "token": "",
    "chat_id": "",
    "notification_settings": {
      "entry": "silent",
      "exit": {
        "roi": "silent"
      }
    }
  },
  "api_server": {
    "enabled": true,
    "listen_ip_address": "0.0.0.0",
    "listen_port": 8080,
    "jwt_secret_key": "",
    "username": "",
    "password": ""
  }
}
```

This configuration file demonstrates several security-critical components:
- Exchange API credentials (key, secret, password)
- Wallet addresses and private keys
- Telegram bot authentication tokens
- API server credentials and JWT secret key

Best practices for securing this file include:
1. Never commit this file to version control
2. Store it outside the project directory in a secure location
3. Set strict file permissions (600 or 400)
4. Use environment variables for sensitive values when possible
5. Regularly rotate API keys and secrets

**Section sources**
- [exampleconfig_secret.json](file://configs/exampleconfig_secret.json#L1-L86)

## Proxy Configuration with proxy-binance.json

The `proxy-binance.json` configuration enables connectivity to Binance exchange from geographically restricted regions by routing traffic through intermediary proxy servers. This configuration is essential for users in countries where direct access to cryptocurrency exchanges is blocked or throttled.

```json
{
  "exchange": {
    "name": "binance",
    "ccxt_config": {
      "enableRateLimit": true,
      "rateLimit": 200
    },
    "ccxt_async_config": {
      "aiohttp_trust_env": true,
      "enableRateLimit": true,
      "rateLimit": 200
    }
  }
}
```

The configuration works by:
- Enabling rate limiting to prevent API bans
- Setting a request rate limit of 200ms between calls
- Trusting environment variables for proxy settings (via `aiohttp_trust_env`)

To use HTTP or SOCKS5 proxies, users must set environment variables:
- HTTP_PROXY or HTTPS_PROXY for HTTP proxies
- ALL_PROXY for SOCKS5 proxies (e.g., `socks5://user:pass@host:port`)

This approach leverages the underlying CCXT library's proxy support, allowing seamless integration without modifying the trading bot's core code. The configuration ensures that all API requests to Binance are routed through the specified proxy server while maintaining proper rate limiting to avoid detection.

**Section sources**
- [proxy-binance.json](file://configs/proxy-binance.json#L1-L14)

## Advanced Strategy Parameters in recommended_config.json

The `recommended_config.json` file provides a foundation for advanced configuration by demonstrating how to combine multiple configuration files and override default settings. This approach enables modular configuration management and separation of sensitive data from operational parameters.

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

Key features of this advanced configuration:
- **Modular design**: Combines multiple configuration files for different purposes
- **Separation of concerns**: Sensitive credentials are separated from operational settings
- **Flexible trading modes**: Supports both spot and futures trading configurations
- **Dynamic pair management**: Uses volume-based pair lists for optimal selection
- **Risk management**: Includes exchange-specific blacklists to avoid problematic assets

The `add_config_files` parameter allows the bot to merge settings from multiple JSON files, creating a comprehensive configuration from specialized components. This approach enhances security by isolating secrets and improves maintainability by organizing settings by function.

**Section sources**
- [recommended_config.json](file://configs/recommended_config.json#L1-L18)

## Custom Parameters and Position Management

The NostalgiaForInfinityX6 strategy implements sophisticated position management through nested custom parameters. These parameters enable fine-grained control over grinding, derisking, and rebuy mechanisms, allowing traders to customize risk exposure and profit-taking behavior.

### Grinding and Derisking Configuration

The strategy defines multiple grinding levels with specific thresholds and stake multipliers:

```python
# Grinding v2 configuration
grinding_v2_grind_1_enable = True
grinding_v2_grind_1_stakes_spot = [0.20, 0.21, 0.22, 0.23]
grinding_v2_grind_1_thresholds_spot = [-0.06, -0.07, -0.08, -0.09]
grinding_v2_grind_1_profit_threshold_spot = 0.028
grinding_v2_grind_1_derisk_spot = -0.18
```

This configuration demonstrates:
- Progressive stake increases for each grind level
- Price thresholds for triggering additional buys
- Profit targets for exiting grind positions
- Derisk levels to protect against severe drawdowns

### Rebuy Mechanism

The rebuy functionality allows the strategy to average down on losing positions:

```python
rebuy_mode_stake_multiplier = 0.35
rebuy_mode_thresholds_spot = [-0.08, -0.10]
rebuy_mode_stakes_spot = [1.0, 1.0]
```

This configuration enables:
- Strategic entry at predetermined price drops
- Controlled risk exposure through stake multipliers
- Multiple rebuy opportunities within defined thresholds

### Position Adjustment Overrides

The strategy supports dynamic position adjustments based on market conditions:

```python
position_adjustment_enable = True
grinding_enable = True
derisk_enable = True
stops_enable = True
```

These flags control advanced features that can be overridden in configuration:
- Position size adjustments based on performance
- Active grinding of losing positions
- Dynamic risk reduction (derisking)
- Stop-loss mechanisms for capital preservation

**Section sources**
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L68-L822)

## Debugging Complex Configurations

Effective debugging of complex trading configurations requires a systematic approach using Freqtrade's built-in tools and careful log analysis.

### Dry-Run Mode

The `dry_run` parameter in `exampleconfig_secret.json` enables safe testing:
```json
"dry_run": true
```

When enabled, this setting:
- Prevents real trades from being executed
- Uses simulated balances and prices
- Allows full testing of entry/exit logic
- Enables strategy optimization without financial risk

### Log Analysis

The strategy implements comprehensive logging:
```python
log = logging.getLogger(__name__)
```

Key debugging techniques include:
1. Monitoring entry/exit signal generation
2. Tracking position adjustment triggers
3. Analyzing grinding and rebuy activations
4. Verifying proper derisking behavior

### Configuration Validation

The strategy includes runtime validation:
```python
if "nfi_advanced_mode" in self.config and self.config["nfi_advanced_mode"] == True:
    log.warning("The advanced configuration mode is enabled. I hope you know what you are doing.")
```

This warning alerts users when potentially dangerous advanced features are activated, encouraging careful review of configuration changes.

**Section sources**
- [exampleconfig_secret.json](file://configs/exampleconfig_secret.json#L5)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L68-L822)

## Security and Risk Mitigation

### Common Security Risks

1. **Credential Exposure**: Storing API keys in plaintext files
2. **Insecure File Permissions**: Allowing unauthorized read access
3. **Network Interception**: Unencrypted communication with exchanges
4. **Configuration Injection**: Malicious modification of config files

### Mitigation Strategies

**File Security**
- Set restrictive permissions: `chmod 600 config-private.json`
- Store configuration outside web root directories
- Use environment variables for secrets: `export BINANCE_KEY="yourkey"`

**Network Security**
- Always use HTTPS for API communication
- Validate SSL certificates
- Implement proxy authentication for SOCKS5 connections
- Monitor for suspicious outbound connections

**Operational Security**
- Regularly rotate API keys and secrets
- Use exchange-specific API keys with minimal required permissions
- Enable two-factor authentication on exchange accounts
- Monitor account activity for unauthorized transactions

**Configuration Security**
- Validate all configuration inputs
- Implement integrity checks for config files
- Use digital signatures for critical configuration files
- Maintain version control for configuration changes (without secrets)

The combination of secure configuration practices, proper file handling, and network security measures provides a robust defense against common threats in automated trading systems.

**Section sources**
- [exampleconfig_secret.json](file://configs/exampleconfig_secret.json#L1-L86)
- [proxy-binance.json](file://configs/proxy-binance.json#L1-L14)
- [NostalgiaForInfinityX6.py](file://NostalgiaForInfinityX6.py#L68-L822)