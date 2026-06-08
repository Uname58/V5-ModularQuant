#!/usr/bin/env python3
"""
批量回测 + 图表生成 — 精选5 + BTC/ETH
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.signal_engine import run_backtest
from reporting.reporter import generate_report
from analytics.metrics import compute_all_metrics

COINS = [
    ("BTCUSDT", "BTC"),
    ("ETHUSDT", "ETH"),
    ("FILUSDT", "FIL"),
    ("AVAXUSDT", "AVAX"),
    ("SOLUSDT", "SOL"),
    ("NEARUSDT", "NEAR"),
    ("INJUSDT", "INJ"),
]

for sym, label in COINS:
    print(f"── {label} ──")
    try:
        engine, months, weeks = run_backtest(symbol=sym)
        metrics = engine.final_metrics()
        sells = [t for t in engine.trades if t["action"] == "SELL"]
        eq = [e[1] for e in engine.equity_curve]
        yrs = len(weeks) / 52
        full = compute_all_metrics(sells, eq, yrs)

        # Simple text summary
        print(f"  {metrics['trades']}t  {metrics['win_rate']*100:.0f}%WR  "
              f"Return: {metrics['total_return_pct']:+.1f}%  "
              f"DD: {metrics['max_drawdown_pct']:+.1f}%  "
              f"Sharpe: {full.get('sharpe_ratio','?'):.2f}")

        # Generate charts (prefixed with symbol)
        os.makedirs(f"reports/{label}", exist_ok=True)
        # Monkey-patch output dir for this run
        orig_out = os.path.join("reports", label)
        generate_report(engine, months, weeks, output_dir=orig_out)
        print(f"  ✅ 图表 → reports/{label}/")

    except Exception as e:
        print(f"  ❌ {e}")

print("\n✅ 完成")
