"""
Market Regime Classifier v2 — percentile-based, crypto-aware.
Uses rolling relative thresholds instead of absolute numbers.
Bull/Bear by momentum ranking, Sideways/Panic by volatility ranking.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import Optional
from config import REGIME


def classify_regime(momentum_6m: float, vol_rank: float) -> str:
    """
    Classify regime from relative momentum and volatility rank.
    
    Args:
        momentum_6m: 6-month cumulative return (%)
        vol_rank: Current month's absolute return as percentile (0-100)
                  in the rolling 24-month distribution.
    
    Returns: 'bull' | 'bear' | 'sideways' | 'panic'
    """
    # Direction: momentum ranking
    # Top 30% of historical 6m returns → bull
    # Bottom 30% → bear
    # Middle 40% → neutral (then decide by volatility)

    # Volatility: percentile in 24-month distribution
    # Top 20% → panic (unusually high vol)
    # Bottom 20% → sideways (compressed, no juice)
    # Middle 60% → normal

    if vol_rank > 80:
        return "panic"
    if vol_rank < 20:
        return "sideways"

    # Normal volatility — classify by direction
    if momentum_6m > 0:
        return "bull"
    return "bear"


def rolling_percentile(values: list[float], window: int = 24) -> list[float]:
    """
    For each position, compute: what percentile is values[i] within values[i-window:i+1]?
    Returns list of 0-100 values, same length as input.
    First (window-1) values use whatever history is available.
    """
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        window_vals = values[start:i + 1]
        if len(window_vals) < 3:
            result.append(50.0)  # neutral when insufficient data
        else:
            # Count how many are <= current value
            current = abs(values[i])  # use absolute for volatility ranking
            below = sum(1 for v in window_vals if abs(v) <= current)
            pct = below / len(window_vals) * 100
            result.append(round(pct, 1))
    return result


def rolling_momentum_rank(momentums: list[float], window: int = 24) -> list[float]:
    """
    For each position: what percentile is the 6-month cumulative return
    within the rolling window of past 6-month cumulatives?
    """
    result = []
    for i in range(len(momentums)):
        start = max(0, i - window + 1)
        window_vals = momentums[start:i + 1]
        if len(window_vals) < 3:
            result.append(50.0)
        else:
            current = momentums[i]
            below = sum(1 for v in window_vals if v <= current)
            pct = below / len(window_vals) * 100
            result.append(round(pct, 1))
    return result


def build_regime_labels(monthly_closes: list[float], window: int = None) -> list[str]:
    """
    Build regime labels for each month using percentile-based classification.
    
    Args:
        monthly_closes: List of monthly close prices
        window: Rolling window size (default 24 = 2 years)
    
    Returns list of regime labels (length = len(monthly_closes) - 1).
    The first month has no return, so labels start from month 2.
    """
    w = window or REGIME.get("lookback_months", 6) * 4  # convert months config to 24
    if w < 12:
        w = 12  # minimum 1 year for percentile to be meaningful

    n = len(monthly_closes)
    if n < 3:
        return ["unknown"] * max(0, n - 1)

    # Monthly returns
    monthly_returns = [
        (monthly_closes[i] - monthly_closes[i - 1]) / monthly_closes[i - 1] * 100
        for i in range(1, n)
    ]

    # 6-month cumulative momentum
    momentum_6m = []
    for i in range(len(monthly_returns)):
        start = max(0, i - 5)
        cum = sum(monthly_returns[start:i + 1])
        momentum_6m.append(round(cum, 1))

    # Percentile ranks
    vol_ranks = rolling_percentile(monthly_returns, w)
    mom_ranks = rolling_momentum_rank(momentum_6m, w)

    # Classify each month
    labels = []
    for i in range(len(monthly_returns)):
        label = classify_regime(momentum_6m[i], vol_ranks[i])
        labels.append(label)

    return labels


def regime_summary(labels: list[str]) -> dict:
    """Count and summarize regime labels."""
    counts = {}
    for r in labels:
        counts[r] = counts.get(r, 0) + 1
    total = len(labels)
    return {
        "total": total,
        "counts": counts,
        "pct": {k: round(v / total * 100, 1) for k, v in counts.items()},
    }


def segment_by_regime(trades: list[dict], trade_month_labels: list[str]) -> dict:
    """Group trade results by regime. (unchanged from v1)"""
    segments = {"bull": [], "bear": [], "sideways": [], "panic": []}
    
    for i, t in enumerate(trades):
        if t.get("action") != "SELL":
            continue
        regime = trade_month_labels[i] if i < len(trade_month_labels) else "unknown"
        if regime in segments:
            pnl = t.get("net_pnl_pct", t.get("pnl_pct", 0))
            segments[regime].append(pnl)
    
    result = {}
    for regime, pnls in segments.items():
        if not pnls:
            result[regime] = {"count": 0, "total_pnl": 0, "avg_pnl": 0, "win_rate": 0}
            continue
        wins = [p for p in pnls if p > 0]
        result[regime] = {
            "count": len(pnls),
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(sum(pnls) / len(pnls), 2),
            "win_rate": round(len(wins) / len(pnls) * 100, 1),
        }
    
    return result
