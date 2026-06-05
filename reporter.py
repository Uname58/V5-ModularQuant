#!/usr/bin/env python3
"""
Moon Reversal Reporter — GitHub-style 4-chart backtest dashboard.
Uses realistic engine (fees, slippage, compounding).
"""
import json, sys, os, datetime, argparse, urllib.request
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from strategies import MoonReversalStrategy
from engine.backtest_engine import BacktestEngine
from engine.execution_simulator import ExecutionSimulator
from engine.signal_engine import fetch_data, parse_candle

# Dark theme — matching GitHub repo style
plt.style.use('dark_background')
C = {
    'green': '#00ff88', 'red': '#ff4466', 'blue': '#44aaff',
    'yellow': '#ffcc00', 'bg': '#1a1a2e', 'grid': '#2a2a3e',
}


def run():
    months, weeks, month_map = fetch_data()

    strat = MoonReversalStrategy()
    engine = BacktestEngine(strategy=strat, executor=ExecutionSimulator())
    last_month = None

    # Collect trade markers with week data for charting
    all_trades = []
    for w in weeks:
        ym = w['date'][:7]
        if last_month and ym != last_month and last_month in month_map:
            strat.feed_monthly(month_map[last_month])
        last_month = ym
        signal = strat.feed_weekly(w)
        if signal:
            all_trades.append({**signal, 'week': w})
            if signal['action'] == 'BUY':
                engine.buy(signal['date'], signal['price'], signal['reason'])
            elif signal['action'] == 'SELL':
                engine.sell(signal['date'], signal['price'], signal['reason'])

    # Build datetime fields for charting
    for w in weeks:
        w['datetime'] = datetime.datetime.strptime(w['date'], '%Y-%m-%d')
    for m in months:
        m['datetime'] = datetime.datetime.strptime(m['date'], '%Y-%m')

    return weeks, months, all_trades, engine


def generate_charts(output_dir='.'):
    weeks, months, all_trades, engine = run()

    sells = [t for t in all_trades if t['action'] == 'SELL']
    buys = [t for t in all_trades if t['action'] == 'BUY']
    engine_sells = [t for t in engine.trades if t['action'] == 'SELL']
    eq_dates = [e[0] for e in engine.equity_curve[1:]]  # skip initial (None, capital)
    eq_vals = [e[1] for e in engine.equity_curve]

    if not sells:
        print("无交易数据")
        return

    # ---- Chart 1: BTC Price + Buy/Sell Markers ----
    fig, ax = plt.subplots(figsize=(16, 7))
    fig.patch.set_facecolor(C['bg'])
    ax.set_facecolor(C['bg'])

    dates = [w['datetime'] for w in weeks]
    closes = [w['close'] for w in weeks]
    ax.plot(dates, closes, color=C['blue'], linewidth=0.8, alpha=0.7, label='BTC Weekly Close')

    buy_dates = [b['week']['datetime'] for b in buys]
    buy_prices = [b['price'] for b in buys]
    ax.scatter(buy_dates, buy_prices, color=C['green'], marker='^', s=100,
              zorder=5, label=f'BUY ({len(buys)})', edgecolors='white', linewidths=0.5)

    for t in sells:
        color = C['green'] if t['pnl_pct'] > 0 else C['red']
        ax.scatter(t['week']['datetime'], t['price'], color=color, marker='v', s=80,
                  zorder=5, edgecolors='white', linewidths=0.5)
    ax.scatter([], [], color=C['green'], marker='v', s=80, label='SELL Win', edgecolors='white', linewidths=0.5)
    ax.scatter([], [], color=C['red'], marker='v', s=80, label='SELL Loss', edgecolors='white', linewidths=0.5)

    ax.set_title('Moon Reversal Strategy — BTC Weekly with Trade Markers', fontsize=14, fontweight='bold', pad=15)
    ax.set_ylabel('BTC/USDT', fontsize=11)
    ax.legend(loc='upper left', framealpha=0.3)
    ax.grid(True, alpha=0.15, color=C['grid'])
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    fig.savefig(f'{output_dir}/btc_trades.png', dpi=150, facecolor=C['bg'])
    plt.close()
    print(f"✅ btc_trades.png")

    # ---- Chart 2: Cumulative P&L (trade-by-trade, not weekly equity) ----
    fig, ax = plt.subplots(figsize=(16, 6))
    fig.patch.set_facecolor(C['bg'])
    ax.set_facecolor(C['bg'])

    # Use engine trade net P&L, accumulated trade by trade
    trade_pnls = [t.get('net_pnl_pct', t.get('pnl_pct', 0)) for t in engine_sells]
    trade_dates_sell = [datetime.datetime.strptime(t['date'], '%Y-%m-%d') for t in engine_sells]
    cumulative = []
    running = 0
    for p in trade_pnls:
        running += p
        cumulative.append(running)

    colors_pnl = [C['green'] if c > 0 else C['red'] for c in cumulative]
    ax.fill_between(range(len(cumulative)), 0, cumulative, alpha=0.3,
                     color=C['green' if cumulative[-1] > 0 else 'red'])
    ax.plot(range(len(cumulative)), cumulative, color=C['yellow'], linewidth=2, marker='o', markersize=6)

    for i, (d, c) in enumerate(zip(trade_dates_sell, cumulative)):
        ax.annotate(f'{c:+.1f}%', (i, c), textcoords="offset points", xytext=(0, 12),
                   ha='center', fontsize=8, color=C['green'] if c > 0 else C['red'])

    cagr = ((eq_vals[-1] / engine.initial) ** (1 / (len(weeks) / 52)) - 1) * 100
    ax.set_title(f'Cumulative P&L: {cumulative[-1]:+.1f}% | {len(trade_pnls)} trades | CAGR: {cagr:+.1f}%',
                 fontsize=14, fontweight='bold')
    ax.set_ylabel('Cumulative Return (%)', fontsize=11)
    ax.axhline(y=0, color='white', linewidth=0.5, alpha=0.3)
    ax.grid(True, alpha=0.15, color=C['grid'])
    ax.set_xticks(range(len(cumulative)))
    ax.set_xticklabels([d.strftime('%Y-%m') for d in trade_dates_sell], rotation=45, fontsize=8)
    plt.tight_layout()
    fig.savefig(f'{output_dir}/equity_curve.png', dpi=150, facecolor=C['bg'])
    plt.close()
    print(f"✅ equity_curve.png")

    # ---- Chart 3: Trade P&L Distribution ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor(C['bg'])

    # Use engine trade P&L (net, with costs)
    pnls = [t.get('net_pnl_pct', t.get('pnl_pct', 0)) for t in engine_sells]
    colors_bar = [C['green'] if p > 0 else C['red'] for p in pnls]

    ax1.set_facecolor(C['bg'])
    ax1.bar(range(len(pnls)), pnls, color=colors_bar, edgecolor='white', linewidth=0.5)
    ax1.axhline(y=0, color='white', linewidth=0.5)
    ax1.set_title('Trade-by-Trade P&L (net of fees)', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Return (%)', fontsize=10)
    ax1.grid(True, alpha=0.15, color=C['grid'])

    wins = sum(1 for p in pnls if p > 0)
    losses = len(pnls) - wins
    ax2.set_facecolor(C['bg'])
    ax2.pie([wins, losses], labels=[f'Wins ({wins})', f'Losses ({losses})'],
            colors=[C['green'], C['red']], autopct='%1.0f%%',
            explode=(0.05, 0), startangle=90, textprops={'color': 'white', 'fontsize': 11})
    ax2.set_title(f'Win Rate: {wins/len(pnls)*100:.0f}%', fontsize=12, fontweight='bold')

    plt.tight_layout()
    fig.savefig(f'{output_dir}/pnl_distribution.png', dpi=150, facecolor=C['bg'])
    plt.close()
    print(f"✅ pnl_distribution.png")

    # ---- Chart 4: Drawdown (trade-by-trade) ----
    fig, ax = plt.subplots(figsize=(16, 5))
    fig.patch.set_facecolor(C['bg'])
    ax.set_facecolor(C['bg'])

    running = 0
    peak = 0
    drawdowns = []
    for p in trade_pnls:
        running += p
        if running > peak:
            peak = running
        dd = (running - peak) if peak > 0 else 0
        drawdowns.append(dd)

    ax.fill_between(range(len(drawdowns)), 0, drawdowns, color=C['red'], alpha=0.4)
    ax.plot(range(len(drawdowns)), drawdowns, color=C['red'], linewidth=1.5)
    ax.set_title(f'Drawdown | Max: {min(drawdowns):.1f}%', fontsize=12, fontweight='bold')
    ax.set_ylabel('Drawdown (%)', fontsize=10)
    ax.grid(True, alpha=0.15, color=C['grid'])
    ax.set_xticks(range(len(drawdowns)))
    ax.set_xticklabels([d.strftime('%Y-%m') for d in trade_dates_sell], rotation=45, fontsize=8)
    plt.tight_layout()
    fig.savefig(f'{output_dir}/drawdown.png', dpi=150, facecolor=C['bg'])
    plt.close()
    print(f"✅ drawdown.png")

    # ---- Summary ----
    avg_win = sum(p for p in trade_pnls if p > 0) / wins if wins else 0
    avg_loss = sum(p for p in trade_pnls if p <= 0) / losses if losses else 0
    cagr = ((eq_vals[-1] / engine.initial) ** (1 / (len(weeks) / 52)) - 1) * 100
    dd_max = min(drawdowns) if drawdowns else 0

    # Weekly returns for Sharpe
    wr_list = [(eq_vals[i] - eq_vals[i-1]) / eq_vals[i-1] * 100 for i in range(1, len(eq_vals))]
    mu = sum(wr_list) / len(wr_list) if wr_list else 0
    sd = (sum((r - mu)**2 for r in wr_list) / (len(wr_list) - 1))**0.5 if len(wr_list) > 1 else 0
    sharpe = (mu / sd) * (52**0.5) if sd > 0 else 0

    total_return = cumulative[-1] if cumulative else 0

    print(f"\n{'='*50}")
    print(f"📊 报告已生成 → {output_dir}/")
    print(f"{'='*50}")
    print(f"btc_trades.png        BTC价格 + 买卖点标记")
    print(f"equity_curve.png      累计收益曲线")
    print(f"pnl_distribution.png  每笔盈亏 + 胜率饼图")
    print(f"drawdown.png          回撤曲线")
    print(f"\n交易: {len(sells)} | 胜率: {wins/len(sells)*100:.0f}%")
    print(f"均盈: {avg_win:+.1f}% | 均亏: {avg_loss:.1f}% | 累计: {total_return:+.1f}%")
    print(f"CAGR: {cagr:+.1f}% | MaxDD: {dd_max:.1f}% | Sharpe: {sharpe:.2f}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=SCRIPT_DIR, help='Output directory')
    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)
    generate_charts(args.output)
