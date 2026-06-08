#!/usr/bin/env python3
"""
Moon Reversal 多币扫描 — 扫描主流币买入信号。
独立脚本，不依赖策略引擎（纯原始数据判断）。
"""
import json, urllib.request, sys
from datetime import datetime

BINANCE = "https://api.binance.com/api/v3/klines"

WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT", "OPUSDT",
    "ARBUSDT", "APTUSDT", "NEARUSDT", "FILUSDT", "INJUSDT",
]

def fetch(symbol, interval, limit):
    url = f"{BINANCE}?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "MoonScan/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def check(symbol):
    try:
        months = fetch(symbol, "1M", 48)
        weeks = fetch(symbol, "1w", 208)
    except Exception as e:
        return None

    prev_m = months[-2]
    this_w = weeks[-1]
    m_bear = float(prev_m[4]) < float(prev_m[1])
    w_green = float(this_w[4]) > float(this_w[1])
    m_chg = (float(prev_m[4]) - float(prev_m[1])) / float(prev_m[1]) * 100
    w_chg = (float(this_w[4]) - float(this_w[1])) / float(this_w[1]) * 100

    return {
        "symbol": symbol.replace("USDT", ""),
        "price": float(this_w[4]),
        "m_bear": m_bear, "w_green": w_green,
        "m_chg": m_chg, "w_chg": w_chg,
    }

def run():
    results = []
    for sym in WATCHLIST:
        r = check(sym)
        if r:
            results.append(r)

    buy = [r for r in results if r["m_bear"] and r["w_green"]]
    wait = [r for r in results if r["m_bear"] and not r["w_green"]]
    none_ = [r for r in results if not r["m_bear"]]

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append(f"🌙 Moon Reversal 多币扫描 — {now}")
    lines.append("")

    if buy:
        lines.append(f"🔥 买入信号 ({len(buy)}个):")
        for r in buy:
            lines.append(f"  {r['symbol']:<6} ${r['price']:>8,.2f}  上月{r['m_chg']:+.1f}%  本周{r['w_chg']:+.1f}%")
        lines.append("")

    if wait:
        lines.append(f"⏳ 等绿周 ({len(wait)}个):")
        for r in wait:
            lines.append(f"  {r['symbol']:<6} ${r['price']:>8,.2f}  上月{r['m_chg']:+.1f}%  本周{r['w_chg']:+.1f}%")
        lines.append("")

    lines.append(f"⏸️  无信号: {', '.join(r['symbol'] for r in none_)}")

    return "\n".join(lines)

if __name__ == "__main__":
    print(run())
