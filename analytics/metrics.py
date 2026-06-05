"""
Metrics Engine — comprehensive strategy-level performance analytics.
All standard quant metrics. No cherry-picking.
"""
import math
from typing import Optional


def sharpe_ratio(returns: list[float], risk_free: float = 0.0, annualize: int = 52) -> float:
    """Sharpe Ratio = (mean return - rf) / std(returns) * sqrt(periods)."""
    if len(returns) < 2:
        return 0.0
    mu = sum(returns) / len(returns)
    if mu == 0:
        return 0.0
    sd = math.sqrt(sum((r - mu) ** 2 for r in returns) / (len(returns) - 1))
    if sd == 0:
        return 0.0
    return ((mu - risk_free) / sd) * math.sqrt(annualize)


def sortino_ratio(returns: list[float], risk_free: float = 0.0, annualize: int = 52) -> float:
    """Sortino Ratio — only penalizes downside deviation."""
    if len(returns) < 2:
        return 0.0
    mu = sum(returns) / len(returns)
    downside = [min(0, r - risk_free) ** 2 for r in returns]
    if sum(downside) == 0:
        return 0.0
    ds = math.sqrt(sum(downside) / (len(returns) - 1))
    if ds == 0:
        return 0.0
    return ((mu - risk_free) / ds) * math.sqrt(annualize)


def max_drawdown(equity: list[float]) -> tuple[float, float]:
    """Max drawdown (pct) and duration (periods)."""
    peak = equity[0]
    max_dd = 0.0
    dd_start = 0
    dd_duration = 0
    in_dd = False
    dd_begin_idx = 0

    for i, eq in enumerate(equity):
        if eq > peak:
            peak = eq
            if in_dd:
                duration = i - dd_begin_idx
                if duration > dd_duration:
                    dd_duration = duration
                in_dd = False
        dd = (eq - peak) / peak * 100 if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd
            if not in_dd:
                in_dd = True
                dd_begin_idx = i
        elif in_dd and dd >= 0:
            in_dd = False

    return round(max_dd, 2), dd_duration


def calmar_ratio(total_return_pct: float, max_dd_pct: float) -> float:
    """Calmar = CAGR / |MaxDD|."""
    if max_dd_pct >= 0 or max_dd_pct == 0:
        return 0.0
    return abs(total_return_pct / max_dd_pct)


def profit_factor(gross_profit: float, gross_loss: float) -> float:
    """Profit Factor = Gross Profit / Gross Loss."""
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / abs(gross_loss)


def expectancy(win_rate: float, avg_win: float, avg_loss: float) -> float:
    """Expectancy = (WR × AW) + ((1-WR) × AL)."""
    return (win_rate * avg_win) + ((1 - win_rate) * abs(avg_loss))


def volatility(returns: list[float], annualize: int = 52) -> float:
    """Annualized volatility from periodic returns."""
    if len(returns) < 2:
        return 0.0
    mu = sum(returns) / len(returns)
    sd = math.sqrt(sum((r - mu) ** 2 for r in returns) / (len(returns) - 1))
    return sd * math.sqrt(annualize)


def rolling_window(values: list[float], window: int) -> list[float]:
    """Compute rolling sum/average. Returns list of same length."""
    if window > len(values):
        return [0.0] * len(values)
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        win = values[start:i + 1]
        result.append(sum(win) / len(win))
    return result


def compute_all_metrics(sells: list[dict], equity_curve_values: list[float],
                         years: float, risk_free: float = 0.0) -> dict:
    """
    Compute all standard metrics from backtest results.
    
    Args:
        sells: List of SELL trade dicts with 'net_pnl_pct' or 'pnl_pct'
        equity_curve_values: List of equity values over time
        years: Backtest duration in years
        risk_free: Annual risk-free rate (decimal, e.g. 0.02)
    """
    if not sells:
        return {"trades": 0, "status": "no_trades"}

    # Extract P&L
    pnls = [t.get("net_pnl_pct", t.get("pnl_pct", 0)) for t in sells]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    wr = len(wins) / len(pnls)
    aw = sum(wins) / len(wins) if wins else 0.0
    al = sum(losses) / len(losses) if losses else 0.0
    gp = sum(wins)
    gl = sum(losses)

    # Equity-based
    dd, dd_dur = max_drawdown(equity_curve_values)
    total_return = (equity_curve_values[-1] - equity_curve_values[0]) / equity_curve_values[0] * 100
    cagr = ((equity_curve_values[-1] / equity_curve_values[0]) ** (1 / years) - 1) * 100 if years > 0 else 0.0

    # Weekly returns from equity
    if len(equity_curve_values) >= 2:
        weekly_returns = [
            (equity_curve_values[i] - equity_curve_values[i - 1]) / equity_curve_values[i - 1] * 100
            for i in range(1, len(equity_curve_values))
        ]
    else:
        weekly_returns = []

    return {
        "trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "years": round(years, 2),

        # Return
        "total_return_pct": round(total_return, 2),
        "cagr_pct": round(cagr, 2),

        # Win/Loss
        "win_rate_pct": round(wr * 100, 1),
        "avg_win_pct": round(aw, 2),
        "avg_loss_pct": round(abs(al), 2),
        "win_loss_ratio": round(aw / abs(al), 2) if al != 0 else None,

        # Risk-adjusted
        "sharpe_ratio": round(sharpe_ratio(weekly_returns), 2),
        "sortino_ratio": round(sortino_ratio(weekly_returns), 2),
        "max_drawdown_pct": dd,
        "max_dd_duration_periods": dd_dur,
        "calmar_ratio": round(calmar_ratio(cagr, dd), 2),

        # Trade quality
        "profit_factor": round(profit_factor(gp, gl), 2),
        "expectancy_pct": round(expectancy(wr, aw, al), 2),
        "gross_profit_pct": round(gp, 2),
        "gross_loss_pct": round(abs(gl), 2),

        # Risk
        "volatility_annualized_pct": round(volatility(weekly_returns), 1),
    }
