"""
Regime Gate — adaptive exposure filter for Moon Reversal Strategy.
Blocks entries during statistically weak environments.
Configurable, logged, fully backtestable.
"""
import sys, os, datetime, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import Optional
from config import REGIME

try:
    from analytics.regime import classify_regime, build_regime_labels
except ImportError:
    from analytics.regime import classify_regime as _cr


class RegimeGate:
    """
    Pre-execution regime filter.
    
    Modes:
      - sideway_block: Block entries in sideways regime (default)
      - bear_reduce: Reduce position size in bear (optional)
      - vol_min: Block if volatility below threshold (optional)
    """

    def __init__(
        self,
        block_sideways: bool = True,
        bear_size_reduction: float = 0.0,     # e.g. 0.5 = half Kelly in bear
        min_monthly_move_pct: float = 0.0,     # Min abs monthly return to allow entry
        max_red_months_streak: int = 0,         # Max consecutive red months before pause
    ):
        self.block_sideways = block_sideways
        self.bear_reduction = bear_size_reduction
        self.min_move = min_monthly_move_pct
        self.max_red_streak = max_red_months_streak

        self.decisions: list[dict] = []
        self.red_streak = 0

    def should_enter(self, regime: str, monthly_returns: list[float] = None,
                      kelly_pct: float = 0.373) -> tuple[bool, float, str]:
        """
        Decide whether to allow entry and at what size.
        
        Returns: (allow_entry, adjusted_kelly_pct, reason)
        """
        reasons = []

        # Rule 1: Sideways block
        if self.block_sideways and regime == "sideways":
            reasons.append("sideways regime blocked")
            self._log(False, 0.0, reasons)
            return False, 0.0, " | ".join(reasons)

        adjusted_kelly = kelly_pct

        # Rule 2: Bear size reduction
        if self.bear_reduction > 0 and regime == "bear":
            adjusted_kelly = kelly_pct * (1 - self.bear_reduction)
            reasons.append(f"bear regime: Kelly {kelly_pct*100:.0f}% → {adjusted_kelly*100:.0f}%")

        # Rule 3: Min monthly move
        if self.min_move > 0 and monthly_returns:
            last_ret = monthly_returns[-1] if monthly_returns else 0
            if abs(last_ret) < self.min_move:
                reasons.append(f"low volatility ({last_ret:+.1f}% < {self.min_move}%)")
                self._log(False, 0.0, reasons)
                return False, 0.0, " | ".join(reasons)

        # Rule 4: Consecutive red month streak
        if self.max_red_streak > 0 and monthly_returns:
            if monthly_returns and monthly_returns[-1] < 0:
                self.red_streak += 1
            else:
                self.red_streak = 0
            if self.red_streak >= self.max_red_streak:
                reasons.append(f"max red streak ({self.red_streak} >= {self.max_red_streak})")
                self._log(False, 0.0, reasons)
                return False, 0.0, " | ".join(reasons)

        if not reasons:
            reasons.append("gate passed")

        self._log(True, adjusted_kelly, reasons)
        return True, adjusted_kelly, " | ".join(reasons)

    def _log(self, allowed: bool, kelly: float, reasons: list[str]):
        self.decisions.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "allowed": allowed,
            "adjusted_kelly": round(kelly, 4),
            "reasons": reasons,
        })

    def summary(self) -> dict:
        if not self.decisions:
            return {"total": 0}
        blocked = sum(1 for d in self.decisions if not d["allowed"])
        return {
            "total_checks": len(self.decisions),
            "allowed": len(self.decisions) - blocked,
            "blocked": blocked,
            "block_rate_pct": round(blocked / len(self.decisions) * 100, 1),
            "avg_kelly_when_allowed": round(
                sum(d["adjusted_kelly"] for d in self.decisions if d["allowed"]) /
                max(1, len(self.decisions) - blocked) * 100, 1
            ),
        }


class GatedStrategy:
    """
    Wraps MoonReversalStrategy with regime gate.
    Transparent — same interface, just adds pre-entry filter.
    """

    def __init__(self, strategy, regime_gate: RegimeGate, months_raw: list):
        self.strategy = strategy
        self.gate = regime_gate
        self.months = months_raw
        self._monthly_returns = self._build_monthly_returns()
        self._regime_labels = build_regime_labels([m["close"] for m in months_raw])
        self._month_idx = 0
        self._last_trade_month = -1

    def _build_monthly_returns(self) -> list[float]:
        closes = [m["close"] for m in self.months]
        return [(closes[i] - closes[i-1]) / closes[i-1] * 100 for i in range(1, len(closes))]

    def _current_regime(self, month_idx: int) -> str:
        if month_idx < len(self._regime_labels) and month_idx > 0:
            return self._regime_labels[month_idx - 1]
        return "unknown"

    def feed_monthly(self, month: dict):
        self.strategy.feed_monthly(month)
        self._month_idx += 1

    def feed_weekly(self, week: dict) -> Optional[dict]:
        # Only gate new entries, never block exits
        if not self.strategy.in_position and self.strategy.entry_allowed:
            regime = self._current_regime(self._month_idx)
            rets = self._monthly_returns[:self._month_idx] if self._month_idx > 0 else []
            allowed, adj_kelly, reason = self.gate.should_enter(regime, rets, self.strategy.kelly)

            if not allowed:
                # Consume the entry signal but don't enter
                self.strategy.entry_allowed = False
                return {
                    "action": "BLOCKED",
                    "price": week["close"],
                    "date": week["date"],
                    "reason": f"GATE: {reason}",
                }

        return self.strategy.feed_weekly(week)

    @property
    def in_position(self):
        return self.strategy.in_position

    @property
    def kelly(self):
        return self.strategy.kelly

    @property
    def entry_price(self):
        return self.strategy.entry_price

    def reset(self):
        self.strategy.reset()
