# 🧪 V5 Modular Quant Lab

> *"Strategy is a plugin. The framework is the edge."*
> *「策略是插件。风控层才是本体。」*

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://python.org)
[![Status](https://img.shields.io/badge/status-paper%20trading-yellow)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

---

## 💡 核心哲学

```
信号层告诉你何时入场。
风控层决定你能不能留下来等到它兑现。
```

Alpha 会衰减，参数会过拟合，但风险塑造是永恒的。

---

## 🎯 当前主力：RSI 流动性反弹模块

| 指标 | 值 |
|------|-----|
| 入场条件 | RSI(14) < 20 + 价格低于 MA99 8%+ + 24h 跌 5%+ |
| TP / SL | +1.5% / -10% |
| 胜率 | **93%** (2022-2026, 269 信号) |
| 年化 | 年年正收益 (2022 +55%, 2023 +20%, 2024 +28%, 2025 +13%, 2026 +3%) |
| MaxDD (风控后) | 16.5% |
| Sharpe | 1.24 |
| 中位持仓 | 2 小时 |

### 风控层

- **冷却系统**：亏损后 6h→24h→72h 递进冷却（砍掉 46% 信号 = MaxDD 从 43% → 16.5%）
- **非线性 sizing**：RSI < 15 → 1.5x, RSI < 18 → 1.2x, ATR > 5% → 0.7x
- **风险预算**：日风控 3%, 周风控 7%

### 当前阶段：Phase 1 纸交

- **14 币**：BTC ETH SOL BNB XRP DOGE SUI NEAR ADA AVAX LINK ENA AAVE INJ
- **每 30 分钟扫描**，静默运行，有信号才推送
- **追踪指标**：Capture Ratio, 执行滑点, 信号密度, 冷却触发率
- **目标**：证明回测 ≈ 实盘（30 天观察）

---

## 🏗️ 架构

```
V5-ModularQuant/
│
├── config.py                  ⚙️  集中配置
├── cli_runner.py              🖥️  统一 CLI
│
├── engine/                    ⚡ 执行层
│   ├── backtest_engine.py        复利权益曲线 + 滑点/手续费
│   └── execution_simulator.py   真实成本建模
│
├── strategies/                🧩 策略插件
│   └── (RSI 反弹 / 四灯 / Moon Reversal)
│
├── analytics/                 📐 分析层
│   ├── metrics.py                14 指标
│   ├── regime.py                 市场状态分类
│   └── benchmarks.py             基准对比
│
├── validation/                🛡️ 验证
│   └── sensitivity.py            参数网格搜索
│
├── paper_trading/             📋 纸交
│   └── paper_trade_rsi.py        RSI Phase 1 (14 币, cron)
│
├── risk/                      🚨 风控
│   └── risk_controller.py        冷却 + 风险预算
│
├── monitoring/                📡 监控
│   ├── observer.py               绩效追踪
│   └── news_monitor.py           新闻过滤
│
└── analysis/                  📝 研究记录
```

---

## 📊 策略墓地

被验证、被否决、被搁置——它们不是失败，是通往答案的路。

| 策略 | 结果 | 原因 |
|------|------|------|
| 四灯 4H/1H | ❌ | 恐慌市场 WR 25%, 熊市不适用 |
| Moon Reversal 月线 | ⏸️ | 长周期择时, 暂时搁置 |
| Bar Confirm 变体 | ❌ | 延迟入场使结果更差 |
| Regime Switching | ❌ | 120 次切换过拟合, OOS 全负 |

---

## 📈 审计结论 (2026-06-23)

| 检查项 | 结果 |
|------|:--:|
| 未来函数 | ✅ 无 (RSI 仅用已收盘数据) |
| 冷却真实性 | ✅ (砍 46% 信号) |
| 费率抗性 | ✅ (0.25% 费率下 Sharpe > 1.0) |
| 延迟抗性 | ⚠️ 敏感 (需实盘测量) |
| 最坏情况 | ✅ 仍正收益 (+27.9%) |

---

## 🚀 Quick Start

```bash
# 纸交扫描
python3 paper_trading/paper_trade_rsi.py

# 回测
python3 cli_runner.py backtest
```

---

*Built by [Uname58](https://github.com/Uname58) — 19yo, HK. The strategy changes. The framework stays.*
