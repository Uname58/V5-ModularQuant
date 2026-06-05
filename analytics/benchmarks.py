"""
Benchmark Engine — compare strategy against buy-and-hold and cash.
Critical for detecting whether strategy actually adds value.
"""
import sys, os, json, datetime, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BENCHMARKS, BINANCE_BASE


def fetch_klines(symbol: str, interval: str, limit: int) -> list:
    url = f"{BINANCE_BASE}?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "V5-Benchmark/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def benchmark_buy_hold(symbol: str, start_idx: int, end_idx: int,
                        weekly_candles: list[dict]) -> dict:
    """
    Simulate buy-and-hold on the same data period.
    
    Returns metrics comparable with strategy backtest.
    """
    if start_idx >= len(weekly_candles) or end_idx > len(weekly_candles):
        return {"error": "index out of range"}

    start_price = weekly_candles[start_idx]["close"]
    end_price = weekly_candles[end_idx - 1]["close"]
    total_return = (end_price - start_price) / start_price * 100

    # Max drawdown
    peak = start_price
    max_dd = 0.0
    for i in range(start_idx, end_idx):
        price = weekly_candles[i]["close"]
        if price > peak:
            peak = price
        dd = (price - peak) / peak * 100 if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    # Weekly returns for Sharpe
    weekly_returns = []
    for i in range(start_idx + 1, end_idx):
        r = (weekly_candles[i]["close"] - weekly_candles[i - 1]["close"]) / weekly_candles[i - 1]["close"] * 100
        weekly_returns.append(r)

    n_years = (end_idx - start_idx) / 52
    cagr = ((end_price / start_price) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0

    # Simple Sharpe
    if len(weekly_returns) >= 2:
        mu = sum(weekly_returns) / len(weekly_returns)
        sd = (sum((r - mu) ** 2 for r in weekly_returns) / (len(weekly_returns) - 1)) ** 0.5
        sharpe = (mu / sd) * (52 ** 0.5) if sd > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        "symbol": symbol,
        "total_return_pct": round(total_return, 2),
        "cagr_pct": round(cagr, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "start_price": start_price,
        "end_price": end_price,
        "years": round(n_years, 2),
    }


def compare_to_benchmarks(strategy_metrics: dict, benchmarks: dict) -> dict:
    """Generate comparison table: strategy vs each benchmark."""
    comparisons = []
    for name, bm in benchmarks.items():
        if "error" in bm:
            continue
        alpha = strategy_metrics.get("total_return_pct", 0) - bm.get("total_return_pct", 0)
        dd_improvement = strategy_metrics.get("max_drawdown_pct", 0) - bm.get("max_drawdown_pct", 0)
        comparisons.append({
            "benchmark": name,
            "strategy_return": strategy_metrics.get("total_return_pct", 0),
            "benchmark_return": bm.get("total_return_pct", 0),
            "alpha_pct": round(alpha, 2),
            "strategy_dd": strategy_metrics.get("max_drawdown_pct", 0),
            "benchmark_dd": bm.get("max_drawdown_pct", 0),
            "dd_improvement_pct": round(dd_improvement, 2),
            "verdict": "outperforms" if alpha > 0 else "underperforms",
        })
    return {"comparisons": comparisons}
