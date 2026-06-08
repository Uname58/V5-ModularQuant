#!/usr/bin/env python3
"""
V5 精选5 — 每周信号详情（FIL/AVAX/SOL/MATIC/INJ）
规则：单笔上限 ¥4,000 (50%)，同时持仓 ≤2。
优先级：风险调整收益（Return ÷ |MaxDD|）
"""
import sys, os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)

from engine.signal_engine import check_signal

SELECTED = ["FILUSDT", "AVAXUSDT", "SOLUSDT", "NEARUSDT", "INJUSDT"]
CAPITAL = 8000
MAX_PER_TRADE = 4000
MAX_POSITIONS = 2

# 回测基准：收益, 胜率, 最大回撤
BACKTEST = {
    "FILUSDT":   (122.8, 92, -30.7),
    "AVAXUSDT":  (152.9, 91, -38.8),
    "SOLUSDT":   (130.2, 86, -38.1),
    "NEARUSDT":  (112.2, 80, -43.6),
    "INJUSDT":   (110.5, 80, -37.0),
}

# 风险调整排名：Return ÷ |MaxDD|
RANK = sorted(SELECTED, key=lambda s: BACKTEST[s][0] / abs(BACKTEST[s][2]), reverse=True)
# FIL > AVAX > SOL > MATIC > INJ

TRAIL_ACT = 5.0
TRAIL_DIST = 4.0
HKD_PER_USD = 7.83


def run():
    results = []
    for sym in SELECTED:
        try:
            r = check_signal(symbol=sym)
            r["_rank"] = RANK.index(sym) + 1
            r["_ra"] = BACKTEST[sym][0] / abs(BACKTEST[sym][2])
            results.append(r)
        except Exception as e:
            print(f"  {sym}: ERROR {e}", file=sys.stderr)
            continue

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append(f"🎯 V5 精选5 — {now}")
    lines.append(f"规则: 单笔≤¥{MAX_PER_TRADE:,} | 持仓≤{MAX_POSITIONS}个 | 优先: 风险调整收益")
    lines.append("")

    holding = [r for r in results if r["in_position"]]
    active = [r for r in results if r["entry_gate_open"] and not r["current_week_red"] and r not in holding]
    waiting = [r for r in results if r["entry_gate_open"] and r["current_week_red"] and not r["in_position"]]
    inactive = [r for r in results if not r["entry_gate_open"] and not r["in_position"]]

    slots_used = len(holding)
    slots_free = MAX_POSITIONS - slots_used

    # --- 持仓 ---
    if holding:
        lines.append(f"📈 当前持仓 ({slots_used}/{MAX_POSITIONS}):")
        for r in holding:
            entry = r.get("entry_price", r["last_price"])
            pnl = (r["last_price"] - entry) / entry * 100 if entry else 0
            tstop = r.get("trail_stop_price")
            usd_size = MAX_PER_TRADE / HKD_PER_USD
            qty = usd_size / entry if entry else 0
            tinfo = f"止损 ${tstop:,.2f}" if tstop else "未激活"
            lines.append(f"  #{r['_rank']} {r['symbol']:<6} ${entry:>,.2f} → ${r['last_price']:>,.2f} ({pnl:+.1f}%) | "
                         f"仓位 ¥{MAX_PER_TRADE:,} ({qty:.2f}个) | {tinfo}")
        lines.append("")

    # --- 买入信号 ---
    if active:
        # Pick top N by rank, respecting free slots
        pick = sorted(active, key=lambda r: r["_rank"])[:slots_free] if slots_free > 0 else []
        cannot = [r for r in active if r not in pick]

        lines.append(f"🔥 买入信号 ({len(active)}个, 可用槽位{slots_free}):")
        lines.append(f"  {'优先':<4} {'币':<6} {'价格':>9} {'上月':>8} {'止损':>9} {'追踪激活':>9} {'RA得分':>7} {'操作'}")
        lines.append(f"  {'─'*4} {'─'*6} {'─'*9} {'─'*8} {'─'*9} {'─'*9} {'─'*7} {'─'*6}")
        for r in sorted(active, key=lambda r: r["_rank"]):
            price = r["last_price"]
            stop_loss = price * (1 - TRAIL_DIST / 100)
            stop_act = price * (1 + TRAIL_ACT / 100)
            usd_size = MAX_PER_TRADE / HKD_PER_USD
            qty = usd_size / price
            action = "✅ 买入" if r in pick else f"⏸️  槽满" if slots_free == 0 else f"⏸️  排第{r['_rank']}"
            lines.append(
                f"  #{r['_rank']:<3} {r['symbol']:<6} ${price:>8,.2f} {r['prev_month_return']:>+7.1f}% "
                f"${stop_loss:>8,.2f} ${stop_act:>8,.2f} {r['_ra']:>6.2f}  {action}"
            )
        lines.append("")

    # --- 等待 ---
    if waiting:
        lines.append(f"⏳ 等绿周 ({len(waiting)}):")
        for r in sorted(waiting, key=lambda r: r["_rank"]):
            lines.append(f"  #{r['_rank']} {r['symbol']:<6} ${r['last_price']:>8,.2f} | 上月{r['prev_month_return']:+.1f}% | 本周🔴红")
        lines.append("")

    # --- 无信号 ---
    if inactive:
        lines.append(f"⏸️  无信号 ({len(inactive)}):")
        for r in sorted(inactive, key=lambda r: r["_rank"]):
            lines.append(f"  #{r['_rank']} {r['symbol']:<6} ${r['last_price']:>8,.2f} | "
                         f"上月{'🔴熊' if r['prev_month_red'] else '🟢牛'} {r['prev_month_return']:+.1f}% | 门关闭")

    # --- 基准 ---
    lines.append("")
    lines.append(f"── 风险调整排名 (Return ÷ |MaxDD|) ──")
    for sym in RANK:
        bt = BACKTEST[sym]
        ra = bt[0] / abs(bt[2])
        label = sym.replace("USDT", "")
        lines.append(f"  #{RANK.index(sym)+1} {label:<6} {bt[1]}%WR | +{bt[0]}% | DD{bt[2]}% | RA={ra:.2f}")

    return "\n".join(lines)


if __name__ == "__main__":
    print(run())
