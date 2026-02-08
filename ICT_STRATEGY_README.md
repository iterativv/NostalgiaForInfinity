# ICT Time-Based Liquidity Strategy - 使用说明

## 策略概述

这是一个基于 ICT (Inner Circle Trader) 概念的量化交易策略，核心思想是：
- **市场只做两件事**：寻找流动性 (Seek Liquidity) 或 平衡不平衡 (Rebalance Imbalance)
- **Smart Money (机构) 在特定时间点猎取特定的流动性池**
- **交易假突破 (Fakeout)，而非真突破 (Breakout)**

## 核心交易逻辑

### 1. 流动性猎取 (Liquidity Sweep)

策略寻找以下模式：
```
价格突破关键水平 → 触发散户止损 → 机构介入 → 价格反转
```

**做多信号**：
- 价格向下突破 PDL/Asian Low/London Low/PWL
- 然后收盘价收回到该水平之上（Reclaim）
- 确认：形成 Bullish FVG (Fair Value Gap)

**做空信号**：
- 价格向上突破 PDH/Asian High/London High/PWH
- 然后收盘价收回到该水平之下（Reclaim）
- 确认：形成 Bearish FVG

### 2. 关键价格水平 (Liquidity Pools)

| 水平 | 说明 | 重要性 |
|------|------|--------|
| **PWH/PWL** | Previous Week High/Low (上周高低点) | ⭐⭐⭐⭐⭐ 最强 |
| **PDH/PDL** | Previous Day High/Low (昨日高低点) | ⭐⭐⭐⭐⭐ 最强 |
| **Asian High/Low** | 亚洲时段高低点 (20:00-00:00 NY) | ⭐⭐⭐⭐ 强 |
| **London High/Low** | 伦敦时段高低点 (02:00-05:00 NY) | ⭐⭐⭐⭐ 强 |

### 3. 交易时间窗口 (Session Times)

所有时间基于**纽约时间 (EST/EDT)**：

| 时段 | 时间范围 | 交易特点 |
|------|----------|----------|
| **Asian Session** | 20:00 - 00:00 | 建立当日区间，流动性较低 |
| **London Session** | 02:00 - 05:00 | 猎取 Asian Range，开始主要波动 |
| **NY AM Session** | 09:30 - 12:00 | 猎取 London Range，最大波动 |
| **NY PM Session** | 13:30 - 16:30 | 尾盘调整，准备收盘 |

### 4. Fair Value Gap (FVG)

**定义**：
- **Bullish FVG**: K线1的高点 < K线3的低点（中间有缺口）
- **Bearish FVG**: K线1的低点 > K线3的高点（中间有缺口）

**用途**：
- FVG 是未成交的价格区域（不平衡）
- 价格倾向于回到 FVG 区域填补（Rebalance）
- 作为入场确认信号

## 策略参数

### 入场条件

**做多 (Long Entry)**：
```python
1. 检测到 Bullish Liquidity Sweep (PDL/Asian Low/London Low/PWL)
2. 市场处于 Bullish Bias 或在 London/NY AM Session
3. 形成 Bullish FVG (当前或前2根K线)
4. RSI < 70 (未超买)
5. 高成交量确认 (Volume > 1.5x MA)
```

**做空 (Short Entry)**：
```python
1. 检测到 Bearish Liquidity Sweep (PDH/Asian High/London High/PWH)
2. 市场处于 Bearish Bias 或在 London/NY AM Session
3. 形成 Bearish FVG (当前或前2根K线)
4. RSI > 30 (未超卖)
5. 高成交量确认
```

### 出场条件

**止盈目标 (Take Profit)**：
- 做多：PDH / Asian High / London High / PWH
- 做空：PDL / Asian Low / London Low / PWL
- 或遇到反向 FVG/Sweep 信号

**止损 (Stop Loss)**：
- 动态止损：1.5x ATR
- 设置在流动性猎取点之外（Swing High/Low 之外）

### 风险管理

- **最大开仓数**：6 个
- **杠杆**：3x (保守)
- **资金使用率**：99%
- **止损**：5% 硬止损 + 动态 ATR 止损
- **追踪止盈**：启用，1% 触发，2% 偏移

## 使用方法

### 1. 安装策略

将 `ICT_TimeBasedLiquidityStrategy.py` 放置在 freqtrade 的 `user_data/strategies/` 目录下。

```bash
cp ICT_TimeBasedLiquidityStrategy.py /path/to/freqtrade/user_data/strategies/
```

### 2. 配置文件

使用提供的 `config_ict_strategy.json` 或修改您现有的配置：

```json
{
    "strategy": "ICT_TimeBasedLiquidityStrategy",
    "timeframe": "5m",
    "trading_mode": "futures",
    "margin_mode": "isolated",
    "max_open_trades": 6
}
```

### 3. 回测

```bash
freqtrade backtesting \
    --config config_ict_strategy.json \
    --strategy ICT_TimeBasedLiquidityStrategy \
    --timerange 20240101-20241231 \
    --timeframe 5m
```

### 4. 模拟交易 (Dry Run)

```bash
freqtrade trade \
    --config config_ict_strategy.json \
    --strategy ICT_TimeBasedLiquidityStrategy \
    --dry-run
```

### 5. 实盘交易 (Live Trading)

**⚠️ 警告**：实盘前务必：
1. 充分回测（至少6个月数据）
2. 模拟交易至少2周
3. 理解所有风险
4. 从小资金开始

```bash
freqtrade trade \
    --config config_ict_strategy.json \
    --strategy ICT_TimeBasedLiquidityStrategy
```

## 策略优化建议

### 1. 推荐交易对

- **主流币**：BTC, ETH, BNB, SOL
- **高流动性**：日交易量 > 1亿 USDT
- **避免**：杠杆代币 (*BULL, *BEAR, *UP, *DOWN)

### 2. 时区设置

策略所有时间基于纽约时间 (EST/EDT)，需要确保：
```python
# 在策略中已自动处理 UTC 到 NY 时间的转换
# 如果您的服务器时区不是 UTC，需要调整 identify_sessions() 函数
```

### 3. 参数调优

可以调整以下参数以适应不同市场：

```python
# 在策略类中修改
ASIAN_SESSION_START = 20      # 默认 20:00
ASIAN_SESSION_END = 0         # 默认 00:00，可延长到 03:00

LONDON_SESSION_START = 2      # 默认 02:00
LONDON_SESSION_END = 5        # 默认 05:00，可延长到 08:30

# 流动性猎取容差
tolerance = 0.0005            # 默认 0.05%，波动大的币可增加
```

### 4. 监控指标

重点关注：
- **Sweep 信号准确率**：有效突破 vs 假突破比例
- **FVG 填补率**：FVG 是否被回测并反转
- **Session 表现**：哪个时段表现最佳
- **最佳交易对**：不同币种的策略适配度

## 常见问题 (FAQ)

### Q1: 为什么策略没有产生信号？

**可能原因**：
1. 时区设置不正确
2. 没有足够的历史数据（需要至少 500 根 K 线）
3. 市场波动过小，未触发 Sweep 条件
4. 检查 `startup_candle_count` 是否足够

### Q2: 如何知道当前是什么 Session？

在 FreqUI 或 Telegram 中查看策略指标：
- `is_asian_session`
- `is_london_session`
- `is_ny_am_session`
- `is_ny_pm_session`

### Q3: 止损为什么会被频繁触发？

**解决方案**：
1. 增加 ATR 倍数：`atr * 2.0` (默认 1.5)
2. 检查杠杆是否过高
3. 避免在高波动新闻时段交易

### Q4: 如何添加新闻数据过滤？

可以在 `populate_indicators()` 中添加经济日历过滤：
```python
# 示例：避免在 NFP 发布时交易
dataframe['is_nfp_day'] = ...  # 需要外部数据源
```

### Q5: 策略支持现货交易吗？

策略主要为期货设计（支持做空），但可以修改为仅做多：
```python
# 在 populate_entry_trend() 中注释掉 enter_short 部分
```

## 性能优化

### 建议配置

**CPU 密集型**：
- 使用较少的交易对 (5-10)
- 减少 `startup_candle_count` 到 300

**内存密集型**：
- 限制 `informative_timeframes`
- 使用 `--max-open-trades 3`

## 策略监控

### Telegram 通知

确保 `telegram` 配置正确，您将收到：
- 入场信号 (Enter Long/Short)
- 出场信号 (Exit Long/Short)
- 止损触发
- Sweep 检测通知

### FreqUI 监控

访问 `http://localhost:8080`（或您的服务器 IP）：
- 实时查看开仓
- 查看策略指标
- 手动强制入场/出场

## 免责声明

⚠️ **风险警告**：
- 加密货币交易具有高风险
- 过去的表现不代表未来结果
- 本策略仅供学习和研究
- 使用本策略造成的任何损失，作者不承担责任
- 请仅使用您能承受损失的资金

## 支持与反馈

如有问题或建议，请：
1. 查阅 freqtrade 官方文档：https://www.freqtrade.io/
2. 查看 ICT 概念学习资源
3. 在 GitHub Issues 提交问题

## 版本历史

### v1.0.0 (2025-11-28)
- 初始版本发布
- 实现核心 ICT 流动性猎取逻辑
- 支持多时段分析
- FVG 检测和应用
- 动态止损和追踪止盈

---

**祝交易顺利！记住：保护本金，风险第一。**
