#!/usr/bin/env python3
"""
Moon Reversal Weekly Runner
被 cron 每周调用 → 检查信号 + 观察绩效 → 输出报告
"""

import sys, os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import urllib.request, json, datetime

# ---- Helpers ----
def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'V5-Weekly/1.0'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def parse_candle(raw, fmt='monthly'):
    return {
        'date': datetime.datetime.fromtimestamp(raw[0] // 1000).strftime(
            '%Y-%m' if fmt == 'monthly' else '%Y-%m-%d'),
        'open': float(raw[1]), 'high': float(raw[2]),
        'low': float(raw[3]), 'close': float(raw[4]),
    }

# ---- Main ----
BINANCE_MONTHLY = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1M&limit=48"
BINANCE_WEEKLY = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1w&limit=208"

months_raw = fetch(BINANCE_MONTHLY)
weeks_raw = fetch(BINANCE_WEEKLY)

months = [parse_candle(m, 'monthly') for m in months_raw]
weeks = [parse_candle(w, 'weekly') for w in weeks_raw]
month_map = {m['date']: m for m in months}

from strategies import MoonReversalStrategy
from observer import _io, record_trade, observe

strat = MoonReversalStrategy()
journal = _io('r')

last_month = None
new_signals = []

for w in weeks:
    ym = w['date'][:7]
    if last_month and ym != last_month and last_month in month_map:
        strat.feed_monthly(month_map[last_month])
    last_month = ym
    
    signal = strat.feed_weekly(w)
    if signal:
        # Only record if it's newer than last recorded trade
        last_trade_date = journal['trades'][-1]['date'] if journal['trades'] else '2000-01-01'
        if signal['date'] > last_trade_date:
            record_trade(journal, signal['action'], signal['price'],
                         signal['date'], signal.get('pnl_pct'), signal.get('reason', ''))
            new_signals.append(signal)

# ---- Compose Report ----
lines = []
lines.append(f"🌙 Moon Reversal 周报 — {datetime.date.today().isoformat()}")
lines.append("")

# Signal section
completed = months[-2]
current = months[-1]
latest_week = weeks[-1]

prev_red = completed['close'] < completed['open']
prev_ret = (completed['close'] - completed['open']) / completed['open'] * 100
week_green = latest_week['close'] > latest_week['open']
week_ret = (latest_week['close'] - latest_week['open']) / latest_week['open'] * 100

lines.append(f"📅 上月: {completed['date']} {'🔴熊' if prev_red else '🟢牛'} {prev_ret:+.1f}%")
lines.append(f"📅 本周: {latest_week['date']} {'🟢绿' if week_green else '🔴红'} {week_ret:+.1f}%")
lines.append(f"💰 BTC: ${latest_week['close']:,.0f}")

if new_signals:
    lines.append("")
    lines.append("⚡ 新信号:")
    for s in new_signals:
        if s['action'] == 'BUY':
            lines.append(f"  🟢 BUY @ ${s['price']:,.0f} | {s['reason']}")
        else:
            emoji = "✅" if s.get('pnl_pct', 0) > 0 else "❌"
            lines.append(f"  🔴 SELL @ ${s['price']:,.0f} {s.get('pnl_pct', 0):+.1f}% {emoji} | {s['reason']}")
else:
    lines.append("")
    if prev_red:
        if week_green:
            lines.append(f"🔥 入场门开 + 本周绿周 → 应该买入！")
            lines.append(f"   入场价 ${latest_week['close']:,.0f} | Kelly仓位 37.3%")
        else:
            lines.append(f"⏳ 入场门开，等绿周")
    else:
        lines.append(f"⏸️ 入场门关，继续等待")

# Observer section
lines.append("")
obs_report = observe(journal)
lines.append(obs_report)

print('\n'.join(lines))
