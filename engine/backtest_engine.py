"""
Backtest Engine — equity curve simulation with compounding and costs.
Replaces the arithmetic sum model with true portfolio tracking.
"""
import sys, os, datetime, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import Optional
from config import BACKTEST, STRATEGY
from engine.execution_simulator import ExecutionSimulator


class BacktestEngine:
    """Strategy-agnostic backtest engine with realistic execution."""

    def __init__(self, initial_capital=None, strategy=None, executor=None):
        self.initial = initial_capital or BACKTEST["initial_capital"]
        self.strategy = strategy
        self.executor = executor or ExecutionSimulator()
        self.reset()

    def reset(self):
        self.cash = self.initial
        self.position_units = 0.0
        self.entry_price = 0.0
        self.equity_curve = [(None, self.initial)]  # (date, equity)
        self.trades = []
        self._peak = self.initial

    def _equity(self, current_price: float) -> float:
        return self.cash + self.position_units * current_price

    def _record_equity(self, date: str, price: float):
        eq = self._equity(price)
        if eq > self._peak:
            self._peak = eq
        self.equity_curve.append((date, eq))

    def buy(self, date: str, signal_price: float, reason: str = ""):
        """Enter position with Kelly sizing."""
        kelly_pct = getattr(self.strategy, 'kelly', STRATEGY["kelly_fraction"])
        kelly_pct = min(kelly_pct, STRATEGY["kelly_cap"])
        deploy = self.cash * kelly_pct

        result = self.executor.execute_buy(deploy, signal_price)
        self.position_units = result["units"]
        self.entry_price = result["entry_price"]
        self.cash -= result["capital_deployed"]

        trade = {
            "action": "BUY",
            "date": date,
            "price": signal_price,
            "executed_price": result["entry_price"],
            "units": result["units"],
            "fee": result["fee_paid"],
            "capital_deployed": result["capital_deployed"],
            "reason": reason,
        }
        self.trades.append(trade)
        self._record_equity(date, signal_price)

    def sell(self, date: str, signal_price: float, reason: str = ""):
        """Exit position."""
        result = self.executor.execute_sell(self.position_units, signal_price, self.entry_price)
        self.cash += result["net_value"]

        trade = {
            "action": "SELL",
            "date": date,
            "price": signal_price,
            "executed_price": result["exit_price"],
            "fee": result["fee_paid"],
            "gross_pnl_pct": result["gross_return_pct"],
            "net_pnl_pct": result["net_return_pct"],
            "reason": reason,
        }
        self.trades.append(trade)
        self._record_equity(date, signal_price)

        self.position_units = 0.0
        self.entry_price = 0.0

    @property
    def in_position(self) -> bool:
        return self.position_units > 0

    def current_drawdown(self, current_price: float) -> float:
        """Current drawdown from peak equity (%)."""
        eq = self._equity(current_price)
        if self._peak <= 0:
            return 0.0
        return (eq - self._peak) / self._peak * 100

    def final_metrics(self) -> dict:
        """Compute end-of-backtest summary metrics."""
        sells = [t for t in self.trades if t["action"] == "SELL"]
        if not sells:
            return {"trades": 0, "status": "no_trades"}

        wins = [t for t in sells if t["net_pnl_pct"] > 0]
        losses = [t for t in sells if t["net_pnl_pct"] <= 0]
        total_return = (self.equity_curve[-1][1] - self.initial) / self.initial * 100

        # Max drawdown from equity curve
        peak = self.initial
        max_dd = 0.0
        for _, eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (eq - peak) / peak * 100 if peak > 0 else 0.0
            if dd < max_dd:
                max_dd = dd

        return {
            "trades": len(sells),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(sells) if sells else 0,
            "avg_win_pct": sum(t["net_pnl_pct"] for t in wins) / len(wins) if wins else 0,
            "avg_loss_pct": sum(t["net_pnl_pct"] for t in losses) / len(losses) if losses else 0,
            "total_return_pct": round(total_return, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "final_equity": round(self.equity_curve[-1][1], 2),
            "peak_equity": round(self._peak, 2),
        }
