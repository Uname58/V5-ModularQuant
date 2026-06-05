"""
V5 CLI Runner — unified entry point for all operations.
Replaces overloaded paper_trader.py with modular commands.
"""
import sys, os, argparse, json, datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from engine.signal_engine import check_signal, run_backtest, fetch_data
from reporting.reporter import generate_report
from analytics.metrics import compute_all_metrics
from analytics.regime import build_regime_labels, segment_by_regime
from analytics.benchmarks import benchmark_buy_hold, compare_to_benchmarks
from validation.monte_carlo import monte_carlo_report
from validation.sensitivity import run_sensitivity, find_stable_region
from validation.walk_forward import run_walk_forward
from strategies import MoonReversalStrategy
from config import BENCHMARKS


def cmd_signal():
    """Check current signal and market status."""
    result = check_signal()
    print(f"\n{'='*55}")
    print("V5 Moon Reversal — 当前状态")
    print(f"{'='*55}")
    print(f"最新周线: {result['last_week']} | 价格: ${result['last_price']:,.0f}")
    print(f"上月: {result['prev_month']} {'🔴熊月' if result['prev_month_red'] else '🟢牛月'} ({result['prev_month_return']:+.1f}%)")
    print(f"本周: {'🔴红周' if result['current_week_red'] else '🟢绿周'}")

    if result["in_position"]:
        print(f"\n📈 模拟持仓中 | 入场价: ${result['entry_price']:,.0f}")
        if result["trail_active"]:
            print(f"⚡ 追踪止损已激活 | 止损: ${result['trail_stop_price']:,.0f}")
    elif result["entry_gate_open"]:
        print(f"\n✅ 入场门开！")
        if not result["current_week_red"]:
            print(f"🔥 本周绿周 → 模拟买入信号")
        else:
            print(f"⏳ 等待本月首根绿周")
    else:
        print(f"\n⏸️ 无入场信号")

    print(f"\n{'='*55}")
    if result["last_signal"]:
        sig = result["last_signal"]
        print(f"最近信号: {sig['action']} @ ${sig['price']:,.0f} ({sig['date']}) — {sig['reason']}")


def cmd_backtest(args):
    """Run full backtest with realistic execution."""
    print("Running backtest with execution costs...")
    engine, months, weeks = run_backtest()
    metrics = engine.final_metrics()

    print(f"\n{'='*55}")
    print("Backtest Results (with fees + slippage)")
    print(f"{'='*55}")
    print(f"交易: {metrics['trades']}笔 | 胜率: {metrics['win_rate']*100:.0f}%")
    print(f"总收益: {metrics['total_return_pct']:+.2f}% | 最大回撤: {metrics['max_drawdown_pct']:+.2f}%")
    print(f"最终权益: ${metrics['final_equity']:,.0f} | 峰值: ${metrics['peak_equity']:,.0f}")

    # Full metrics
    sells = [t for t in engine.trades if t["action"] == "SELL"]
    eq_values = [e[1] for e in engine.equity_curve]
    years = len(weeks) / 52
    full = compute_all_metrics(sells, eq_values, years)
    print(f"\nSharpe: {full['sharpe_ratio']} | Sortino: {full['sortino_ratio']} | Calmar: {full['calmar_ratio']}")
    print(f"Profit Factor: {full['profit_factor']} | Expectancy: {full['expectancy_pct']:+.2f}%")
    print(f"Volatility (ann.): {full['volatility_annualized_pct']}%")

    # Benchmarks
    start_idx = 0
    end_idx = min(len(weeks), 208)
    bm_btc = benchmark_buy_hold("BTCUSDT", start_idx, end_idx, weeks)
    comparisons = compare_to_benchmarks(metrics, {"BTC Buy&Hold": bm_btc})
    print(f"\n--- Benchmark Comparison ---")
    for c in comparisons.get("comparisons", []):
        print(f"{c['benchmark']}: Strategy {c['strategy_return']:+.1f}% vs BM {c['benchmark_return']:+.1f}% → Alpha: {c['alpha_pct']:+.1f}% ({c['verdict']})")

    # Generate charts
    if not args.no_charts:
        generate_report(engine, months, weeks)

    # Monte Carlo
    trade_pnls = [t.get("net_pnl_pct", t.get("pnl_pct", 0)) for t in sells]
    mc = monte_carlo_report(trade_pnls)
    print(f"\n--- Monte Carlo (10k sims) ---")
    print(f"Mean return: {mc.get('mean_return_pct', 'N/A'):+.1f}% | Median: {mc.get('median_return_pct', 'N/A'):+.1f}%")
    print(f"95% CI: [{mc.get('return_ci_low', 'N/A'):+.1f}%, {mc.get('return_ci_high', 'N/A'):+.1f}%]")
    print(f"Ruin prob: {mc.get('ruin_probability_pct', 'N/A')}% | Worst DD: {mc.get('max_dd_worst_pct', 'N/A'):+.1f}%")


def cmd_validate(args):
    """Run robustness validation suite."""
    from engine.signal_engine import fetch as bf
    import json, urllib.request

    BINANCE_M = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1M&limit=48"
    BINANCE_W = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1w&limit=208"
    from engine.signal_engine import parse_candle

    months_raw = [parse_candle(m, "monthly") for m in bf(BINANCE_M)]
    weeks_raw = [parse_candle(w, "weekly") for w in bf(BINANCE_W)]

    print("\n=== Walk-Forward Validation ===")
    wf = run_walk_forward(months_raw, weeks_raw, MoonReversalStrategy, train_years=2, test_years=1)
    for r in wf["results"]:
        print(f"Fold {r['fold']}: Train {r['train_trades']}t/{r['train_win_rate']*100:.0f}%WR | "
              f"Test {r['test_trades']}t/{r['test_win_rate']*100:.0f}%WR | Return: {r['test_return']:+.1f}%")
    stab = wf["stability"]
    print(f"\nStability: {stab['test_return_mean']:+.1f}% ± {stab['test_return_std']}% | "
          f"Positive folds: {stab['positive_folds']}/{stab['folds']} | Params: {stab['parameter_stability']}")

    print("\n=== Parameter Sensitivity ===")
    sens_results = run_sensitivity(months_raw, weeks_raw, MoonReversalStrategy)
    stable = find_stable_region(sens_results)
    print(f"Best: {stable['best_result']}")
    print(f"Stable zone: Activation {stable['stability_zone']['trailing_activation']} | "
          f"Distance {stable['stability_zone']['trailing_distance']}")
    print(f"Params stable: {stable['parameter_stable']}")


def main():
    parser = argparse.ArgumentParser(description="V5 MoonReversal — Quant Research CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("signal", help="Check current signal")
    bt = sub.add_parser("backtest", help="Run full backtest")
    bt.add_argument("--no-charts", action="store_true")
    sub.add_parser("validate", help="Run validation suite (walk-forward + sensitivity)")

    args = parser.parse_args()

    if args.command == "signal":
        cmd_signal()
    elif args.command == "backtest":
        cmd_backtest(args)
    elif args.command == "validate":
        cmd_validate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
