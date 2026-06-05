#!/usr/bin/env python3
"""
Weekly Paper Trading Runner — run every Monday to:
1. Check Moon Reversal signal
2. Log to paper journal
3. Update benchmark
4. Run observer degradation check
5. Output status report
"""
import sys, os, datetime
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_DIR)

from engine.signal_engine import check_signal, fetch_data
from analytics.regime import build_regime_labels
from paper_trading.journal import PaperJournal, BASELINE


def run():
    print("V5 Paper Trading — Weekly Check")
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    print()

    # 1. Fetch and check signal
    signal = check_signal()
    months, weeks, _ = fetch_data()

    # 2. Classify current regime
    monthly_closes = [m["close"] for m in months]
    labels = build_regime_labels(monthly_closes)
    current_regime = labels[-1] if labels else "unknown"

    btc_price = signal["last_price"]

    # 3. Log to journal
    journal = PaperJournal()
    journal.record_signal_check(signal, current_regime, btc_price)

    # 4. Update benchmark (track from first run)
    journal.update_benchmark(btc_price, btc_price)

    # 5. Print status
    print(f"BTC: ${btc_price:,.0f} | Regime: {current_regime}")
    print(f"上月: {signal['prev_month']} {'🔴熊' if signal['prev_month_red'] else '🟢牛'} ({signal['prev_month_return']:+.1f}%)")
    print(f"本周: {'🔴红' if signal['current_week_red'] else '🟢绿'}")
    print(f"入场门: {'✅ OPEN' if signal['entry_gate_open'] else '⏸️ closed'}")

    if signal["in_position"]:
        pos = journal.data["open_position"]
        if pos:
            pnl = (btc_price - pos["entry_price"]) / pos["entry_price"] * 100
            print(f"持仓: ${pos['entry_price']:,.0f} → ${btc_price:,.0f} ({pnl:+.1f}%)")
            if pos.get("trail_active"):
                trail = pos["highest"] * (1 - pos["trail_distance"] / 100)
                print(f"追踪止损: ${trail:,.0f} (high: ${pos['highest']:,.0f})")

    if signal["last_signal"]:
        sig = signal["last_signal"]
        print(f"最近信号: {sig['action']} @ ${sig['price']:,.0f} ({sig['date']})")

    # 6. Full status
    report = journal.status_report()
    print()
    print(report)

    return report


if __name__ == "__main__":
    run()
