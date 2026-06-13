# 🧪 V5 Modular Quant Lab

> *"Don't build a strategy. Build a strategy engine."*
> *「不造策略，造策略引擎。」*

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://python.org)
[![Status](https://img.shields.io/badge/status-live%20trading-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![Strategies](https://img.shields.io/badge/strategies-pluggable-purple)]()

---

## 💡 核心思想

**策略是插件，框架是本体。**

```
                    ┌──────────────────┐
                    │   V5 Quant Lab   │
                    │  (engine + data) │
                    └────────┬─────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
     ┌────▼────┐      ┌─────▼──────┐      ┌────▼────┐
     │ 四灯 4H │      │ Moon Rev.  │      │ 你的策略 │
     │ 42.9%WR │      │  月线反转   │      │  ...     │
     │ +21.2%  │      │  75% WR    │      │          │
     └─────────┘      └────────────┘      └─────────┘
```

任意策略接入同一套 pipeline：
- 数据拉取 → 信号生成 → 回测 → 参数扫描 → 纸交 → **实盘**

---

## 📊 已回测策略对比 (2024-08 → 2026-06)

| | 四灯 (4H/1H) | Moon Reversal (月/周) |
|------|:--:|:--:|
| 交易次数 | 42 | 15 |
| 胜率 | 42.9% | 53.3% |
| 累计收益 | **+21.2%** | -18.4% |
| vs 买入持有 | **+10.6%** | -26.1% |
| 平均持仓 | 31 小时 | ~2 周 |
| 敞口 | 8.3% | 15.6% |

Moon Reversal 8 年回测见 [analysis/](analysis/) — 它在更长周期上表现更强（8 年 75% WR, +67.2%），但 2024-2026 横盘市场遇冷。

---

## 🏗️ 架构

```
V5-ModularQuant/
│
├── config.py                  ⚙️  Centralized config (all strategies)
├── cli_runner.py              🖥️  Unified CLI
│
├── engine/                    ⚡ Execution layer
│   ├── signal_engine.py          Signal generation (symbol-parametric)
│   ├── backtest_engine.py        复利权益曲线 + 滑点/手续费
│   └── execution_simulator.py    Realistic cost modeling
│
├── strategies/                🧩 Pluggable strategies
│   ├── __init__.py               MoonReversalStrategy (月线反转)
│   └── (四灯即将模块化到这里)
│
├── analytics/                 📐 Analysis layer
│   ├── metrics.py                14 metrics (Sharpe/Sortino/Calmar/...)
│   ├── regime.py                 牛/熊/震荡/恐慌 分类
│   └── benchmarks.py             BTC/ETH buy & hold comparison
│
├── validation/                🛡️  Robustness
│   ├── walk_forward.py           Walk-forward analysis
│   ├── monte_carlo.py            10k bootstrap
│   └── sensitivity.py            Parameter grid search
│
├── reporting/
│   ├── reporter_v2.py         📊  交易级4图 (multi-coin)
│   └── reporter.py               连续权益曲线
│
├── paper_trading/             📋  Live tracking
│   ├── select5.py                RA-ranked position sizing
│   ├── moon_scan.py              20-coin signal scan
│   └── weekly_check.py           Weekly cron
│
├── risk/                      🚨  Risk control
│   └── risk_controller.py        一票否决 + 仓位门
│
├── monitoring/                📡  Monitoring
│   ├── observer.py               Performance tracking
│   └── news_monitor.py           S/A/B/C news filter
│
├── analysis/                  📝  Case studies & records
└── reports/                   📁  Backtest charts
```

---

## 🎯 当前实盘

| 项目 | 状态 |
|------|------|
| 账户 | $259 USDT（自有资金） |
| 主策略 | 🟢 四灯 4H/1H |
| 副策略 | ⏸️ Moon Reversal（等信号） |
| 持仓 | PARTI/USDT |
| 已平仓 | [RENDER +10.5%](analysis/render_live_trade_01.md) |
| 风控 | 单笔 ≤50%, 止损 -7%, 止盈 +8% |
| 信号 | 📡 每日 09:00 HKT 自动扫描 |

---

## 🚀 Quick Start

```bash
# 四灯全市场扫描 (617 coin pairs)
python3.12 scripts/crypto_screener.py

# Moon Reversal 信号
python3 cli_runner.py signal

# 回测 + 验证
python3 cli_runner.py backtest
python3 cli_runner.py validate

# 多币图表
python3 reporter_v2.py
```

---

## 🔔 自动化

| 时间 | 任务 | 策略 |
|------|------|------|
| 每日 09:00 | 四灯入场扫描 | 4H/1H |
| 周一 09:00 | Moon Reversal 周检 | 月/周 |
| 周一 09:00 | 精选7 信号 + 仓位 | RA 排名 |
| 每小时 | 新闻风控扫描 | S/A/B/C |
| 每分钟 | 高波动追踪 | >±2% |

---

*Built by [Uname58](https://github.com/Uname58) — 19yo, HK. Strategy is a plugin, not an identity.*
