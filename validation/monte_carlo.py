"""
Monte Carlo Simulation — bootstrap resampling for statistical confidence.
Path dependency analysis, ruin probability, outcome distribution.
"""
import sys, os, random, math
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BACKTEST


def bootstrap_trades(trade_pnls: list[float], n_simulations: int = None) -> list[dict]:
    """
    Bootstrap resample trade sequences to estimate outcome distribution.
    
    Returns list of {"path": [...], "final_return": float, "max_dd": float, "ruined": bool}
    """
    n = n_simulations or BACKTEST["mc_simulations"]
    if len(trade_pnls) < 3:
        return [{"error": "insufficient_trades", "min_required": 3}]
    
    results = []
    for sim in range(n):
        # Sample with replacement, same length as original
        path = [random.choice(trade_pnls) for _ in range(len(trade_pnls))]
        
        # Simulate equity path
        equity = 100.0
        peak = equity
        max_dd = 0.0
        ruined = False
        
        for pnl in path:
            equity *= (1 + pnl / 100)
            if equity > peak:
                peak = equity
            dd = (equity - peak) / peak * 100 if peak > 0 else 0.0
            if dd < max_dd:
                max_dd = dd
            if equity <= 0:
                ruined = True
                break
        
        final_return = (equity - 100.0) / 100.0 * 100 if not ruined else -100.0
        results.append({
            "final_return_pct": round(final_return, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "ruined": ruined,
        })
    
    return results


def analyze_monte_carlo(results: list[dict], confidence: float = None) -> dict:
    """
    Analyze bootstrap results.
    
    Returns:
        percentiles, ruin probability, expected drawdown range, CI.
    """
    if not results or "error" in results[0]:
        return {"error": "no_valid_results"}
    
    conf = confidence or BACKTEST["mc_confidence"]
    returns = sorted([r["final_return_pct"] for r in results])
    drawdowns = sorted([r["max_drawdown_pct"] for r in results])
    ruin_count = sum(1 for r in results if r["ruined"])
    
    n = len(returns)
    lower_idx = int(n * (1 - conf) / 2)
    upper_idx = int(n * (1 - (1 - conf) / 2))
    
    return {
        "simulations": n,
        "mean_return_pct": round(sum(returns) / n, 2),
        "median_return_pct": round(returns[n // 2], 2),
        "return_ci_low": round(returns[max(0, lower_idx)], 2),
        "return_ci_high": round(returns[min(n - 1, upper_idx)], 2),
        "std_return_pct": round(_mc_std(returns), 2),
        "max_dd_mean_pct": round(sum(drawdowns) / n, 2),
        "max_dd_worst_pct": round(min(drawdowns), 2),
        "max_dd_ci_low": round(drawdowns[max(0, lower_idx)], 2),
        "max_dd_ci_high": round(drawdowns[min(n - 1, upper_idx)], 2),
        "ruin_probability_pct": round(ruin_count / n * 100, 2),
        "sharpe_estimate": round(_estimate_sharpe(returns), 2),
    }


def monte_carlo_report(trade_pnls: list[float]) -> dict:
    """Full Monte Carlo pipeline: bootstrap → analyze."""
    results = bootstrap_trades(trade_pnls)
    return analyze_monte_carlo(results)


def _mc_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mu = sum(values) / len(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / (len(values) - 1))


def _estimate_sharpe(returns: list[float]) -> float:
    """Quick Sharpe estimator from bootstrap returns."""
    if len(returns) < 2:
        return 0.0
    mu = sum(returns) / len(returns)
    sd = _mc_std(returns)
    return mu / sd if sd > 0 else 0.0
