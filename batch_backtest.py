#!/usr/bin/env python3
"""Batch backtest: Moon Reversal on 20 coins, same params."""
import json, urllib.request, sys, os
from datetime import datetime

sys.path.insert(0, "/home/uiao/projects/AI_trading_system_V3")
from strategies import MoonReversalStrategy
from engine.backtest_engine import BacktestEngine
from engine.execution_simulator import ExecutionSimulator

BINANCE = "https://api.binance.com/api/v3/klines"
UA = {"User-Agent": "V5-BatchBacktest/1.0"}

WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT", "OPUSDT",
    "ARBUSDT", "APTUSDT", "NEARUSDT", "FILUSDT", "INJUSDT",
]

def parse_candle(raw, fmt="monthly"):
    ts = raw[0] // 1000
    fmt_str = "%Y-%m" if fmt == "monthly" else "%Y-%m-%d"
    return {
        "date": datetime.fromtimestamp(ts).strftime(fmt_str),
        "open": float(raw[1]), "high": float(raw[2]),
        "low": float(raw[3]), "close": float(raw[4]),
    }

def run_one(symbol):
    try:
        url_m = f"{BINANCE}?symbol={symbol}&interval=1M&limit=48"
        url_w = f"{BINANCE}?symbol={symbol}&interval=1w&limit=208"
        req_m = urllib.request.Request(url_m, headers=UA)
        req_w = urllib.request.Request(url_w, headers=UA)
        with urllib.request.urlopen(req_m, timeout=15) as r:
            months_raw = json.loads(r.read())
        with urllib.request.urlopen(req_w, timeout=15) as r:
            weeks_raw = json.loads(r.read())
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}

    months = [parse_candle(m, "monthly") for m in months_raw]
    weeks = [parse_candle(w, "weekly") for w in weeks_raw]
    month_map = {m["date"]: m for m in months}

    strat = MoonReversalStrategy()
    engine = BacktestEngine(initial_capital=10000, strategy=strat, executor=ExecutionSimulator())
    last_month = None

    for w in weeks:
        ym = w["date"][:7]
        if last_month and ym != last_month and last_month in month_map:
            strat.feed_monthly(month_map[last_month])
        last_month = ym
        signal = strat.feed_weekly(w)
        if signal:
            if signal["action"] == "BUY":
                engine.buy(signal["date"], signal["price"], signal["reason"])
            else:
                engine.sell(signal["date"], signal["price"], signal["reason"])

    metrics = engine.final_metrics()

    if len(weeks) >= 2:
        bh_return = (weeks[-1]["close"] - weeks[0]["open"]) / weeks[0]["open"] * 100
    else:
        bh_return = 0

    return {
        "symbol": symbol.replace("USDT", ""),
        "trades": metrics["trades"],
        "wr": metrics["win_rate"],
        "return": metrics["total_return_pct"],
        "max_dd": metrics["max_drawdown_pct"],
        "pf": metrics.get("profit_factor", 0),
        "bh_return": bh_return,
        "alpha": metrics["total_return_pct"] - bh_return,
        "weeks": len(weeks),
    }

results = []
for i, sym in enumerate(WATCHLIST):
    label = sym.replace("USDT", "")
    print(f"[{i+1}/{len(WATCHLIST)}] {label}...", end=" ", flush=True)
    r = run_one(sym)
    if "error" in r:
        print(f"FAIL: {r['error']}")
        continue
    results.append(r)
    print(f"{r['trades']}t {r['wr']*100:.0f}%WR {r['return']:+.1f}%")

results.sort(key=lambda x: x["return"], reverse=True)

print()
print("=" * 75)
print("Moon Reversal 批量回测 — 同参数 × 20币")
print("=" * 75)
print(f"{'币':<6} {'交易':>4} {'胜率':>5} {'收益':>8} {'回撤':>7} {'买持':>8} {'Alpha':>8} {'评价'}")
print("-" * 75)

for r in results:
    wr_s = f"{r['wr']*100:.0f}%"
    v = "⭐" if r["return"] > 30 and r["wr"] > 0.6 else ("✓" if r["return"] > 0 else "✗")
    print(f"{r['symbol']:<6} {r['trades']:>4} {wr_s:>5} {r['return']:>+7.1f}% {r['max_dd']:>+6.1f}% {r['bh_return']:>+7.1f}% {r['alpha']:>+7.1f}%  {v}")

pos = [r for r in results if r["return"] > 0]
neg = [r for r in results if r["return"] <= 0]
beat = [r for r in results if r["alpha"] > 0]
print(f"\n赚钱: {len(pos)}/{len(results)} | 跑赢买持: {len(beat)}/{len(results)}")
print(f"平均收益: {sum(r['return'] for r in results)/len(results):+.1f}%")
