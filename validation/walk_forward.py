"""
Walk-Forward Validation Framework
Train → freeze params → test on unseen data.
The gold standard for detecting overfitting.
"""
import sys, os, copy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BACKTEST


def walk_forward_split(dates: list[str], train_years: int = None,
                        test_years: int = None) -> list[dict]:
    """
    Generate walk-forward train/test splits.
    
    Returns list of {"train_start", "train_end", "test_start", "test_end", "fold"}.
    """
    train_y = train_years or BACKTEST["wf_train_years"]
    test_y = test_years or BACKTEST["wf_test_years"]
    
    if not dates:
        return []
    
    folds = []
    idx = 0
    fold_num = 1
    
    while idx + train_y * 12 + test_y * 12 <= len(dates):
        train_start = idx
        train_end = idx + train_y * 12
        test_start = train_end
        test_end = test_start + test_y * 12
        
        folds.append({
            "fold": fold_num,
            "train_start": dates[train_start],
            "train_end": dates[train_end - 1],
            "test_start": dates[test_start],
            "test_end": dates[test_end - 1],
            "train_idx": (train_start, train_end),
            "test_idx": (test_start, test_end),
        })
        
        idx += 12  # advance 1 year
        fold_num += 1
    
    return folds


def run_walk_forward(months_raw: list, weeks_raw: list,
                      strategy_class, executor=None,
                      train_years=None, test_years=None) -> dict:
    """
    Execute full walk-forward validation.
    
    Args:
        months_raw: Raw monthly kline data
        weeks_raw: Raw weekly kline data
        strategy_class: Strategy class (not instance)
        executor: ExecutionSimulator instance
    
    Returns dict with per-fold results and stability analysis.
    """
    from engine.backtest_engine import BacktestEngine
    from engine.execution_simulator import ExecutionSimulator
    
    exec_sim = executor or ExecutionSimulator()
    
    # Parse dates for splitting
    month_dates = [m["date"] for m in months_raw]
    folds = walk_forward_split(month_dates, train_years, test_years)
    
    results = []
    train_params = {}
    
    for f in folds:
        # Train on train period
        train_strategy = strategy_class()
        train_engine = BacktestEngine(strategy=train_strategy, executor=exec_sim)
        _run_period(train_engine, train_strategy, months_raw, weeks_raw,
                     f["train_idx"][0], f["train_idx"][1])
        train_metrics = train_engine.final_metrics()
        
        # Freeze params (capture config)
        frozen_config = {
            "trailing_activation": getattr(train_strategy, 'trailing_activation', 5.0),
            "trailing_distance": getattr(train_strategy, 'trailing_distance', 4.0),
            "confirmation_weeks": getattr(train_strategy, 'confirmation_weeks', 2),
        }
        
        # Test on test period
        test_strategy = strategy_class()
        test_engine = BacktestEngine(strategy=test_strategy, executor=exec_sim)
        _run_period(test_engine, test_strategy, months_raw, weeks_raw,
                     f["test_idx"][0], f["test_idx"][1])
        test_metrics = test_engine.final_metrics()
        
        results.append({
            "fold": f["fold"],
            "train_period": f"{f['train_start']} → {f['train_end']}",
            "test_period": f"{f['test_start']} → {f['test_end']}",
            "train_trades": train_metrics.get("trades", 0),
            "train_win_rate": train_metrics.get("win_rate", 0),
            "train_return": train_metrics.get("total_return_pct", 0),
            "test_trades": test_metrics.get("trades", 0),
            "test_win_rate": test_metrics.get("win_rate", 0),
            "test_return": test_metrics.get("total_return_pct", 0),
            "test_max_dd": test_metrics.get("max_drawdown_pct", 0),
            "frozen_config": frozen_config,
        })
        
        fold_key = f"fold_{f['fold']}"
        train_params[fold_key] = frozen_config
    
    # Stability analysis
    test_returns = [r["test_return"] for r in results]
    test_wrs = [r["test_win_rate"] for r in results]
    
    stability = {
        "folds": len(results),
        "test_return_mean": round(sum(test_returns) / len(test_returns), 2) if test_returns else 0,
        "test_return_std": round(_std(test_returns), 2),
        "test_win_rate_mean": round(sum(test_wrs) / len(test_wrs) * 100, 1) if test_wrs else 0,
        "test_win_rate_std": round(_std(test_wrs) * 100, 1),
        "positive_folds": sum(1 for r in test_returns if r > 0),
        "parameter_stability": "stable" if _param_stable(train_params) else "unstable",
    }
    
    return {"results": results, "stability": stability, "folds_used": folds}


def _run_period(engine, strategy, months, weeks, month_start_idx, month_end_idx):
    """Helper: run strategy on a slice of the data."""
    month_map = {m["date"]: m for m in months}
    last_month = None
    
    for w in weeks:
        ym = w["date"][:7]
        if last_month and ym != last_month and last_month in month_map:
            m = month_map[last_month]
            m_idx = months.index(m) if m in months else -1
            if month_start_idx <= m_idx < month_end_idx:
                strategy.feed_monthly(m)
        last_month = ym
        
        signal = strategy.feed_weekly(w)
        if signal:
            if signal["action"] == "BUY":
                engine.buy(signal["date"], signal["price"], signal["reason"])
            else:
                engine.sell(signal["date"], signal["price"], signal["reason"])


def _std(values: list) -> float:
    if len(values) < 2:
        return 0.0
    mu = sum(values) / len(values)
    return (sum((v - mu) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def _param_stable(params: dict) -> bool:
    """Check if parameters are consistent across folds."""
    if len(params) < 2:
        return True
    keys = set()
    for k, v in params.items():
        for pk in v:
            keys.add(pk)
    for key in keys:
        values = [params[f][key] for f in params if key in params[f]]
        if _std(values) > 0.5:  # more than 0.5 unit variation
            return False
    return True
