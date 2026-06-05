"""
Parameter Sensitivity Engine — grid-search to find stable regions, NOT optimal points.
Searches for robustness plateaus, not peak returns.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import STRATEGY


def sensitivity_grid() -> dict:
    """Define the parameter grid for sensitivity analysis."""
    return {
        "trailing_activation_pct": [3.0, 5.0, 7.0, 10.0, 15.0],
        "trailing_distance_pct": [2.0, 3.0, 4.0, 5.0, 7.0],
        "confirmation_weeks": [1, 2, 3],
    }


def run_sensitivity(months_raw: list, weeks_raw: list,
                     strategy_class, grid: dict = None) -> list[dict]:
    """
    Grid-search parameter combinations. Returns all results, not just best.
    
    Goal: identify stable regions, not maximize any single metric.
    """
    from engine.backtest_engine import BacktestEngine
    from engine.execution_simulator import ExecutionSimulator
    
    grid = grid or sensitivity_grid()
    acts = grid["trailing_activation_pct"]
    dists = grid["trailing_distance_pct"]
    confs = grid["confirmation_weeks"]
    
    month_map = {m["date"]: m for m in months_raw}
    results = []
    
    total = len(acts) * len(dists) * len(confs)
    done = 0
    
    for act in acts:
        for dist in dists:
            for conf in confs:
                done += 1
                # Create strategy with these params
                s = strategy_class(
                    trail_activation=act,
                    trail_distance=dist,
                    confirmation_weeks=conf,
                )
                engine = BacktestEngine(strategy=s, executor=ExecutionSimulator())
                
                last_month = None
                for w in weeks_raw:
                    ym = w["date"][:7]
                    if last_month and ym != last_month and last_month in month_map:
                        s.feed_monthly(month_map[last_month])
                    last_month = ym
                    
                    signal = s.feed_weekly(w)
                    if signal:
                        if signal["action"] == "BUY":
                            engine.buy(signal["date"], signal["price"], signal["reason"])
                        else:
                            engine.sell(signal["date"], signal["price"], signal["reason"])
                
                metrics = engine.final_metrics()
                results.append({
                    "trailing_activation_pct": act,
                    "trailing_distance_pct": dist,
                    "confirmation_weeks": conf,
                    "trades": metrics.get("trades", 0),
                    "win_rate_pct": round(metrics.get("win_rate", 0) * 100, 1),
                    "total_return_pct": metrics.get("total_return_pct", 0),
                    "max_drawdown_pct": metrics.get("max_drawdown_pct", 0),
                    "final_equity": metrics.get("final_equity", 0),
                })
    
    return results


def find_stable_region(results: list[dict], metric: str = "total_return_pct",
                        stability_threshold_pct: float = 20.0) -> dict:
    """
    Find parameter region where performance is stable (low variance).
    
    Groups by each parameter and measures variance. Stable = low variance
    across nearby parameter values.
    
    Returns best stable region.
    """
    if not results:
        return {"error": "no_results"}
    
    # Find top N performers
    sorted_results = sorted(results, key=lambda r: r[metric], reverse=True)
    top_n = max(5, len(results) // 5)
    top = sorted_results[:top_n]
    
    # Measure parameter clustering
    acts = [r["trailing_activation_pct"] for r in top]
    dists = [r["trailing_distance_pct"] for r in top]
    
    mean_act = sum(acts) / len(acts)
    mean_dist = sum(dists) / len(dists)
    std_act = (sum((a - mean_act) ** 2 for a in acts) / len(acts)) ** 0.5
    std_dist = (sum((d - mean_dist) ** 2 for d in dists) / len(dists)) ** 0.5
    
    return {
        "top_n": top_n,
        "stability_zone": {
            "trailing_activation": f"{mean_act - std_act:.1f} ~ {mean_act + std_act:.1f}",
            "trailing_distance": f"{mean_dist - std_dist:.1f} ~ {mean_dist + std_dist:.1f}",
        },
        "mean_return_top_n": round(sum(r[metric] for r in top) / top_n, 2),
        "std_top_n": round((sum((r[metric] - sum(rr[metric] for rr in top)/top_n)**2 for r in top)/top_n) ** 0.5, 2),
        "parameter_stable": std_act < stability_threshold_pct and std_dist < stability_threshold_pct,
        "best_result": sorted_results[0],
    }
