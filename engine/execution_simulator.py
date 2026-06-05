"""
Execution Simulator — realistic trade execution modeling.
NO perfect fills. Always account for fees, slippage, and gap risk.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import EXECUTION


class ExecutionSimulator:
    """Models realistic order execution with costs."""

    def __init__(self, fee_pct=None, slippage_pct=None, gap_risk_pct=None):
        self.fee = fee_pct if fee_pct is not None else EXECUTION["fee_pct"]
        self.slippage = slippage_pct if slippage_pct is not None else EXECUTION["slippage_pct"]
        self.gap_risk = gap_risk_pct if gap_risk_pct is not None else EXECUTION["stop_gap_risk_pct"]

    def buy_price(self, signal_price: float) -> float:
        """Real buy price: signal + slippage (pay more)."""
        return signal_price * (1 + self.slippage / 100)

    def sell_price(self, signal_price: float) -> float:
        """Real sell price: signal - slippage (receive less)."""
        return signal_price * (1 - self.slippage / 100)

    def stop_price(self, stop_level: float) -> float:
        """Real stop fill: worse than trigger by gap risk."""
        return stop_level * (1 - self.gap_risk / 100)

    def apply_fee(self, trade_value: float) -> float:
        """Deduct taker fee from trade value."""
        return trade_value * (1 - self.fee / 100)

    def execute_buy(self, capital: float, signal_price: float) -> dict:
        """Execute buy: capital → position after costs."""
        entry = self.buy_price(signal_price)
        gross_units = capital / entry
        fee_cost = capital * (self.fee / 100)
        net_capital = capital - fee_cost
        units = net_capital / entry
        return {
            "entry_price": entry,
            "units": units,
            "capital_deployed": capital,
            "fee_paid": fee_cost,
            "net_capital": net_capital,
        }

    def execute_sell(self, units: float, signal_price: float, entry_price: float) -> dict:
        """Execute sell: position → realized return after costs."""
        exit_price = self.sell_price(signal_price)
        gross_value = units * exit_price
        fee_cost = gross_value * (self.fee / 100)
        net_value = gross_value - fee_cost
        gross_return_pct = (exit_price - entry_price) / entry_price * 100
        net_return_pct = (net_value / (units * entry_price) - 1) * 100
        return {
            "exit_price": exit_price,
            "gross_value": gross_value,
            "fee_paid": fee_cost,
            "net_value": net_value,
            "gross_return_pct": round(gross_return_pct, 2),
            "net_return_pct": round(net_return_pct, 2),
        }
