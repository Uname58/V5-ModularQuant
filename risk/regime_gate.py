"""Regime Gate -- adaptive exposure filter for Moon Reversal Strategy."""

import sys, os, datetime, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from analytics.regime import classify_regime, build_regime_labels
except ImportError:
    from analytics.regime import classify_regime as _cr

class RegimeGate:
    """Pre-execution regime filter. Modes: sideway_block, bear_reduce, vol_min."""

    def __init__(self, block_sideways=True, bear_reduction=0.0,
                 min_monthly_move_pct=0.0, max_red_streak=0):
        self.block_sideways = block_sideways
        self.bear_reduction = bear_reduction
        self.min_move = min_monthly_move_pct
        self.max_red_streak = max_red_streak
        self.decisions = []
        self.red_streak = 0

    def _reject(self, reasons):
        self.decisions.append({"timestamp": datetime.datetime.now().isoformat(),
                               "allowed": False, "adjusted_kelly": 0, "reasons": reasons})
        return False, 0.0, " | ".join(reasons)

    def _allow(self, kelly, reasons):
        self.decisions.append({"timestamp": datetime.datetime.now().isoformat(),
                               "allowed": True, "adjusted_kelly": round(kelly, 4), "reasons": reasons})
        return True, kelly, " | ".join(reasons)

    def should_enter(self, regime, monthly_returns=None, kelly_pct=0.373):
        reasons = []
        if self.block_sideways and regime == "sideways":
            return self._reject(["sideways regime blocked"])
        adj = kelly_pct
        if self.bear_reduction > 0 and regime == "bear":
            adj = kelly_pct * (1 - self.bear_reduction)
            reasons.append(f"bear regime: Kelly {kelly_pct*100:.0f}% → {adj*100:.0f}%")
        if self.min_move > 0 and monthly_returns:
            lr = monthly_returns[-1] if monthly_returns else 0
            if abs(lr) < self.min_move:
                return self._reject([f"low volatility ({lr:+.1f}% < {self.min_move}%)"])
        if self.max_red_streak > 0 and monthly_returns:
            self.red_streak = self.red_streak + 1 if (monthly_returns and monthly_returns[-1] < 0) else 0
            if self.red_streak >= self.max_red_streak:
                return self._reject([f"max red streak ({self.red_streak} >= {self.max_red_streak})"])
        if not reasons:
            reasons.append("gate passed")
        return self._allow(adj, reasons)

    def summary(self):
        if not self.decisions: return {"total": 0}
        blocked = sum(1 for d in self.decisions if not d["allowed"])
        allowed = len(self.decisions) - blocked
        avg_k = round(sum(d["adjusted_kelly"] for d in self.decisions if d["allowed"]) / max(1, allowed) * 100, 1) if allowed else 0
        return {"total_checks": len(self.decisions), "allowed": allowed, "blocked": blocked,
                "block_rate_pct": round(blocked / len(self.decisions) * 100, 1), "avg_kelly_when_allowed": avg_k}

class GatedStrategy:
    """Wraps strategy with regime gate — same interface, adds pre-entry filter."""

    def __init__(self, strategy, gate: RegimeGate, months):
        self.s = strategy
        self.gate = gate
        self._returns = [(months[i]["close"]-months[i-1]["close"])/months[i-1]["close"]*100
                         for i in range(1, len(months))]
        self._regimes = build_regime_labels([m["close"] for m in months])
        self._mi = 0

    def feed_monthly(self, m):
        self.s.feed_monthly(m); self._mi += 1

    def feed_weekly(self, w):
        if not self.s.in_position and self.s.entry_allowed:
            regime = self._regimes[self._mi - 1] if 0 < self._mi < len(self._regimes) else "unknown"
            rets = self._returns[:self._mi] if self._mi > 0 else []
            allowed, adj_k, reason = self.gate.should_enter(regime, rets, self.s.kelly)
            if not allowed:
                self.s.entry_allowed = False
                return {"action": "BLOCKED", "price": w["close"], "date": w["date"], "reason": f"GATE: {reason}"}
        return self.s.feed_weekly(w)

    in_position = property(lambda self: self.s.in_position)
    kelly = property(lambda self: self.s.kelly)
    entry_price = property(lambda self: self.s.entry_price)
    def reset(self): self.s.reset()
