#!/usr/bin/env python3
"""
Moon Reversal Reporter — 可视化回测报告

用法:
  python3 reporter.py                   生成所有图表
  python3 reporter.py --output /tmp/    指定输出目录
"""

import json, sys, os, datetime, argparse
import urllib.request
import matplotlib
matplotlib.use('Agg')  # headless
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from strategies import MoonReversalStrategy

BINANCE_MONTHLY = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1M&limit=48"
BINANCE_WEEKLY = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1w&limit=208"

# Dark theme
plt.style.use('dark_background')
COLORS = {
    'green': '#00ff88',
    'red': '#ff4466',
    'blue': '#44aaff',
    'yellow': '#ffcc00',
    'bg': '#1a1a2e',
    'grid': '#2a2a3e',
}

def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'V5-Reporter/1.0'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def parse_candle(raw, fmt='monthly'):
    return {
        'date': datetime.datetime.fromtimestamp(raw[0] // 1000).strftime(
            '%Y-%m' if fmt == 'monthly' else '%Y-%m-%d'),
        'datetime': datetime.datetime.fromtimestamp(raw[0] // 1000),
        'open': float(raw[1]), 'high': float(raw[2]),
        'low': float(raw[3]), 'close': float(raw[4]),
    }

def run_backtest():
    months_raw = fetch(BINANCE_MONTHLY)
    weeks_raw = fetch(BINANCE_WEEKLY)
    
    months = [parse_candle(m, 'monthly') for m in months_raw]
    weeks = [parse_candle(w, 'weekly') for w in weeks_raw]
    month_map = {m['date']: m for m in months}
    
    strat = MoonReversalStrategy()
    trades = []
    last_month = None
    
    for w in weeks:
        ym = w['date'][:7]
        if last_month and ym != last_month and last_month in month_map:
            strat.feed_monthly(month_map[last_month])
        last_month = ym
        
        signal = strat.feed_weekly(w)
        if signal:
            trades.append({**signal, 'week': w})
    
    return weeks, months, trades

def generate_charts(output_dir='.'):
    weeks, months, all_trades = run_backtest()
    
    sells = [t for t in all_trades if t['action'] == 'SELL']
    buys = [t for t in all_trades if t['action'] == 'BUY']
    
    if not sells:
        print("无交易数据")
        return
    
    # ---- Chart 1: BTC Price + Buy/Sell markers ----
    fig, ax = plt.subplots(figsize=(16, 7))
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['bg'])
    
    dates = [w['datetime'] for w in weeks]
    closes = [w['close'] for w in weeks]
    ax.plot(dates, closes, color=COLORS['blue'], linewidth=0.8, alpha=0.7, label='BTC Weekly Close')
    
    # Buy markers
    buy_dates = [b['week']['datetime'] for b in buys]
    buy_prices = [b['price'] for b in buys]
    ax.scatter(buy_dates, buy_prices, color=COLORS['green'], marker='^', s=100, 
              zorder=5, label=f'BUY ({len(buys)})', edgecolors='white', linewidths=0.5)
    
    # Sell markers
    for t in sells:
        color = COLORS['green'] if t['pnl_pct'] > 0 else COLORS['red']
        ax.scatter(t['week']['datetime'], t['price'], color=color, marker='v', s=80,
                  zorder=5, edgecolors='white', linewidths=0.5)
    
    ax.scatter([], [], color=COLORS['green'], marker='v', s=80, label='SELL ✅', edgecolors='white', linewidths=0.5)
    ax.scatter([], [], color=COLORS['red'], marker='v', s=80, label='SELL ❌', edgecolors='white', linewidths=0.5)
    
    ax.set_title('Moon Reversal Strategy — BTC Weekly with Trade Markers', fontsize=14, fontweight='bold', pad=15)
    ax.set_ylabel('BTC/USDT', fontsize=11)
    ax.legend(loc='upper left', framealpha=0.3)
    ax.grid(True, alpha=0.15, color=COLORS['grid'])
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    fig.savefig(f'{output_dir}/btc_trades.png', dpi=150, facecolor=COLORS['bg'])
    plt.close()
    print(f"✅ btc_trades.png")
    
    # ---- Chart 2: Cumulative P&L (equity curve) ----
    fig, ax = plt.subplots(figsize=(16, 6))
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['bg'])
    
    cumulative = []
    running = 0
    trade_dates = []
    for t in sells:
        running += t['pnl_pct']
        cumulative.append(running)
        trade_dates.append(t['week']['datetime'])
    
    colors_pnl = [COLORS['green'] if c > 0 else COLORS['red'] for c in cumulative]
    ax.fill_between(range(len(cumulative)), 0, cumulative, alpha=0.3, color=COLORS['green' if cumulative[-1] > 0 else 'red'])
    ax.plot(range(len(cumulative)), cumulative, color=COLORS['yellow'], linewidth=2, marker='o', markersize=6)
    
    # Annotate each point
    for i, (d, c) in enumerate(zip(trade_dates, cumulative)):
        ax.annotate(f'{c:+.1f}%', (i, c), textcoords="offset points", xytext=(0, 12),
                   ha='center', fontsize=8, color=COLORS['green'] if c > 0 else COLORS['red'])
    
    ax.set_title(f'Cumulative P&L: {cumulative[-1]:+.1f}% | {len(sells)} trades', fontsize=14, fontweight='bold')
    ax.set_ylabel('Cumulative Return (%)', fontsize=11)
    ax.axhline(y=0, color='white', linewidth=0.5, alpha=0.3)
    ax.grid(True, alpha=0.15, color=COLORS['grid'])
    ax.set_xticks(range(len(cumulative)))
    ax.set_xticklabels([d.strftime('%Y-%m') for d in trade_dates], rotation=45, fontsize=8)
    plt.tight_layout()
    fig.savefig(f'{output_dir}/equity_curve.png', dpi=150, facecolor=COLORS['bg'])
    plt.close()
    print(f"✅ equity_curve.png")
    
    # ---- Chart 3: Trade P&L Distribution ----
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor(COLORS['bg'])
    
    pnls = [t['pnl_pct'] for t in sells]
    colors_bar = [COLORS['green'] if p > 0 else COLORS['red'] for p in pnls]
    
    # Bar chart
    ax1.set_facecolor(COLORS['bg'])
    bars = ax1.bar(range(len(pnls)), pnls, color=colors_bar, edgecolor='white', linewidth=0.5)
    ax1.axhline(y=0, color='white', linewidth=0.5)
    ax1.set_title('Trade-by-Trade P&L', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Return (%)', fontsize=10)
    ax1.grid(True, alpha=0.15, color=COLORS['grid'])
    
    # Pie: win/loss
    wins = sum(1 for p in pnls if p > 0)
    losses = len(pnls) - wins
    ax2.set_facecolor(COLORS['bg'])
    ax2.pie([wins, losses], labels=[f'Wins ({wins})', f'Losses ({losses})'],
            colors=[COLORS['green'], COLORS['red']], autopct='%1.0f%%',
            explode=(0.05, 0), startangle=90, textprops={'color': 'white', 'fontsize': 11})
    ax2.set_title(f'Win Rate: {wins/len(pnls)*100:.0f}%', fontsize=12, fontweight='bold')
    
    plt.tight_layout()
    fig.savefig(f'{output_dir}/pnl_distribution.png', dpi=150, facecolor=COLORS['bg'])
    plt.close()
    print(f"✅ pnl_distribution.png")
    
    # ---- Chart 4: Drawdown ----
    fig, ax = plt.subplots(figsize=(16, 5))
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['bg'])
    
    running = 0
    peak = 0
    drawdowns = []
    for p in pnls:
        running += p
        if running > peak:
            peak = running
        dd = (running - peak) if peak > 0 else 0
        drawdowns.append(dd)
    
    ax.fill_between(range(len(drawdowns)), 0, drawdowns, color=COLORS['red'], alpha=0.4)
    ax.plot(range(len(drawdowns)), drawdowns, color=COLORS['red'], linewidth=1.5)
    ax.set_title(f'Drawdown | Max: {min(drawdowns):.1f}%', fontsize=12, fontweight='bold')
    ax.set_ylabel('Drawdown (%)', fontsize=10)
    ax.grid(True, alpha=0.15, color=COLORS['grid'])
    ax.set_xticks(range(len(drawdowns)))
    ax.set_xticklabels([d.strftime('%Y-%m') for d in trade_dates], rotation=45, fontsize=8)
    plt.tight_layout()
    fig.savefig(f'{output_dir}/drawdown.png', dpi=150, facecolor=COLORS['bg'])
    plt.close()
    print(f"✅ drawdown.png")
    
    # ---- Summary ----
    avg_win = sum(p for p in pnls if p > 0) / wins if wins else 0
    avg_loss = sum(p for p in pnls if p <= 0) / losses if losses else 0
    
    print(f"\n{'='*50}")
    print(f"📊 报告已生成 → {output_dir}/")
    print(f"{'='*50}")
    print(f"btc_trades.png        BTC价格 + 买卖点标记")
    print(f"equity_curve.png      累计收益曲线")
    print(f"pnl_distribution.png  每笔盈亏 + 胜率饼图")
    print(f"drawdown.png          回撤曲线")
    print(f"\n交易: {len(sells)} | 胜率: {wins/len(sells)*100:.0f}%")
    print(f"均盈: {avg_win:+.1f}% | 均亏: {avg_loss:.1f}% | 累计: {sum(pnls):+.1f}%")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=SCRIPT_DIR, help='Output directory')
    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)
    generate_charts(args.output)
