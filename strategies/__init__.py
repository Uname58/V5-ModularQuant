"""
Moon Reversal Strategy — bear-month reversal with trend-following exit.
Parameterized from config.py, overridable for sensitivity testing.
"""
import json, datetime
sys_path = __import__('sys').path
sys_path.insert(0, __import__('os').path.dirname(__import__('os').path.dirname(__import__('os').path.abspath(__file__))))
from typing import Optional

try:
    from config import STRATEGY
    _CFG = STRATEGY
except ImportError:
    _CFG = {
        "trailing_activation_pct": 5.0,
        "trailing_distance_pct": 4.0,
        "exit_confirmation_weeks": 2,
        "kelly_fraction": 0.373,
    }


class MoonReversalStrategy:
    """Bear month → first green week entry. 2 red weeks OR trailing stop exit."""

    def __init__(
        self,
        kelly_fraction: float = None,
        trail_activation: float = None,
        trail_distance: float = None,
        confirmation_weeks: int = None,
    ):
        self.kelly = kelly_fraction if kelly_fraction is not None else _CFG.get("kelly_fraction", 0.373)
        self.trailing_activation = trail_activation if trail_activation is not None else _CFG.get("trailing_activation_pct", 5.0)
        self.trailing_distance = trail_distance if trail_distance is not None else _CFG.get("trailing_distance_pct", 4.0)
        self.confirmation_weeks = confirmation_weeks if confirmation_weeks is not None else _CFG.get("exit_confirmation_weeks", 2)
        self.reset()

    def reset(self):
        self.in_position = False
        self.entry_price = 0.0
        self.entry_date = ""
        self.highest = 0.0
        self.trail_active = False
        self.red_week_count = 0
        self.entry_allowed = False

    def _is_green(self, candle: dict) -> bool:
        return candle["close"] > candle["open"]

    def _is_red(self, candle: dict) -> bool:
        return candle["close"] < candle["open"]

    def feed_monthly(self, month: dict):
        if self._is_red(month):
            self.entry_allowed = True
        else:
            self.entry_allowed = False

    def feed_weekly(self, week: dict) -> Optional[dict]:
        if not self.in_position:
            # ENTRY
            if self.entry_allowed and self._is_green(week):
                self.in_position = True
                self.entry_price = week["close"]
                self.entry_date = week["date"]
                self.highest = week["close"]
                self.trail_active = False
                self.red_week_count = 0
                self.entry_allowed = False
                return {
                    "action": "BUY",
                    "price": week["close"],
                    "date": week["date"],
                    "reason": f"熊月后首绿周 | Kelly仓位{self.kelly*100:.0f}%",
                }
            if self._is_green(week):
                self.entry_allowed = False
        else:
            # EXIT CHECKS
            if week["high"] > self.highest:
                self.highest = week["high"]

            if not self.trail_active:
                profit_pct = (self.highest - self.entry_price) / self.entry_price * 100
                if profit_pct >= self.trailing_activation:
                    self.trail_active = True

            exit_reason = None
            exit_price = None

            if self._is_red(week):
                self.red_week_count += 1
                if self.red_week_count >= self.confirmation_weeks:
                    exit_reason = f"连续{self.confirmation_weeks}红周"
                    exit_price = week["close"]
            else:
                self.red_week_count = 0

            if self.trail_active and exit_reason is None:
                trail_price = self.highest * (1 - self.trailing_distance / 100)
                if week["low"] <= trail_price:
                    exit_reason = f"追踪止损({self.highest:.0f}→{trail_price:.0f})"
                    exit_price = trail_price

            if exit_reason:
                pnl = (exit_price - self.entry_price) / self.entry_price * 100
                result = {
                    "action": "SELL",
                    "price": exit_price,
                    "date": week["date"],
                    "reason": exit_reason,
                    "pnl_pct": round(pnl, 2),
                }
                self.reset()
                return result

        return None
