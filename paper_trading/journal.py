"""
Paper Trading Journal — forward observation infrastructure.
Records every signal check, simulates positions, tracks live performance.
This is the truth machine. No backtest optimism allowed.
"""
import json, os, datetime, sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

JOURNAL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trade_journal.json")
BASELINE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "baseline.json")

# 8-year baseline (2018-2026, 36 trades)
BASELINE = {
    "source": "8-year backtest (2018-07 → 2026-06)",
    "trades": 36,
    "win_rate_pct": 75.0,
    "total_return_pct": 67.2,
    "cagr_pct": 6.6,
    "sharpe": 1.36,
    "max_drawdown_pct": -41.5,
    "trades_per_year": 4.5,
    "avg_win_pct": 8.2,
    "avg_loss_pct": -11.3,
}


class PaperJournal:
    """Forward-only journal. No backtest data allowed."""

    def __init__(self, path: str = JOURNAL_PATH):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            with open(self.path) as f:
                data = json.load(f)
            # Migrate v1 → v2
            if "version" not in data or data.get("version", 1) < 2:
                old_trades = data.get("trades", [])
                old_obs = data.get("observations", [])
                data = {
                    "version": 2,
                    "created": data.get("created", datetime.datetime.now().isoformat()),
                    "signals": [],
                    "trades": old_trades,
                    "open_position": None,
                    "benchmark": {},
                    "observer": old_obs,
                }
            # Ensure all v2 keys exist
            for key in ["signals", "trades", "open_position", "benchmark", "observer"]:
                data.setdefault(key, [] if key != "open_position" and key != "benchmark" else (None if key == "open_position" else {}))
            return data
        return {
            "version": 2,
            "created": datetime.datetime.now().isoformat(),
            "signals": [],
            "trades": [],
            "open_position": None,
            "benchmark": {},
            "observer": [],
        }

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False, default=str)

    def record_signal_check(self, signal: dict, regime: str, btc_price: float):
        """Log every weekly signal check, regardless of whether we trade."""
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "week": signal.get("last_week", ""),
            "btc_price": btc_price,
            "regime": regime,
            "entry_gate_open": signal.get("entry_gate_open", False),
            "in_position": signal.get("in_position", False),
            "signal_action": signal.get("last_signal", {}).get("action") if signal.get("last_signal") else None,
        }
        self.data["signals"].append(entry)

        # Auto-trade simulation
        if not self.data["open_position"] and signal.get("entry_gate_open"):
            is_green = not signal.get("current_week_red", True)
            if is_green:
                self._open_position(signal, btc_price)

        elif self.data["open_position"]:
            self._check_exit(signal, btc_price)

        self.save()

    def _open_position(self, signal: dict, price: float):
        kelly = 0.373
        self.data["open_position"] = {
            "entry_date": signal.get("last_week", datetime.datetime.now().isoformat()),
            "entry_price": price,
            "highest": price,
            "trail_active": False,
            "trail_activation": 5.0,
            "trail_distance": 4.0,
            "red_week_count": 0,
            "kelly_used": kelly,
        }

    def _check_exit(self, signal: dict, price: float):
        pos = self.data["open_position"]
        if not pos:
            return

        current_red = signal.get("current_week_red", False)

        # Update high
        if price > pos["highest"]:
            pos["highest"] = price

        # Trail activation
        if not pos["trail_active"]:
            profit = (pos["highest"] - pos["entry_price"]) / pos["entry_price"] * 100
            if profit >= pos["trail_activation"]:
                pos["trail_active"] = True

        # Exit check: 2 red weeks
        exit_reason = None
        exit_price = None

        if current_red:
            pos["red_week_count"] += 1
            if pos["red_week_count"] >= 2:
                exit_reason = "连续2红周"
                exit_price = price
        else:
            pos["red_week_count"] = 0

        # Exit check: trailing stop
        if pos["trail_active"] and exit_reason is None:
            trail = pos["highest"] * (1 - pos["trail_distance"] / 100)
            if price <= trail:
                exit_reason = f"追踪止损 (high={pos['highest']:.0f} trail={trail:.0f})"
                exit_price = trail

        if exit_reason:
            pnl = (exit_price - pos["entry_price"]) / pos["entry_price"] * 100
            trade = {
                "entry_date": pos["entry_date"],
                "entry_price": pos["entry_price"],
                "exit_date": signal.get("last_week", ""),
                "exit_price": exit_price,
                "pnl_pct": round(pnl, 2),
                "reason": exit_reason,
                "kelly_used": pos["kelly_used"],
            }
            self.data["trades"].append(trade)
            self.data["open_position"] = None
            self._run_observer()

    def _run_observer(self):
        """After each trade closes, check for degradation."""
        trades = self.data["trades"]
        # Only process SELL trades (v1 or v2 format)
        sells = [t for t in trades if t.get("action") == "SELL" or ("pnl_pct" in t and t.get("action") != "BUY")]
        if len(sells) < 2:
            return

        wins = [t for t in sells if t["pnl_pct"] > 0]
        losses = [t for t in sells if t["pnl_pct"] <= 0]
        wr = len(wins) / len(sells)
        total = sum(t["pnl_pct"] for t in sells)
        max_loss = min(t["pnl_pct"] for t in sells) if losses else 0

        alerts = []

        # Degradation check: compare to 8-year baseline
        if len(sells) >= 5:
            wr_gap = (wr * 100) - BASELINE["win_rate_pct"]
            if wr_gap < -15:
                alerts.append(f"🔴 WR {wr*100:.0f}% vs baseline {BASELINE['win_rate_pct']}% (gap: {wr_gap:.0f}%)")

            expected = BASELINE["avg_win_pct"] * wr + BASELINE["avg_loss_pct"] * (1 - wr)
            actual_avg = total / len(sells)
            if actual_avg < expected * 0.5:
                alerts.append(f"🟡 Avg return {actual_avg:+.1f}% vs expected {expected:+.1f}%")

        # Consecutive losses
        if len(sells) >= 3 and all(t["pnl_pct"] <= 0 for t in sells[-3:]):
            alerts.append("🔴 连续3笔亏损 — 暂停评估")

        # Single catastrophic loss
        if abs(max_loss) > abs(BASELINE["max_drawdown_pct"]) * 1.5:
            alerts.append(f"🔴 单笔亏损 {max_loss:.1f}% 超出基线MaxDD {BASELINE['max_drawdown_pct']}%")

        obs = {
            "date": datetime.datetime.now().isoformat(),
            "total_trades": len(sells),
            "win_rate_pct": round(wr * 100, 1),
            "total_pnl_pct": round(total, 2),
            "max_loss_pct": round(max_loss, 2),
            "alerts": alerts,
            "status": "degraded" if len(alerts) >= 2 else ("warning" if len(alerts) == 1 else "healthy"),
        }
        self.data.setdefault("observer", []).append(obs)
        self.save()

    def update_benchmark(self, btc_price: float, btc_buy_price: float):
        """Track BTC buy-and-hold from journal start."""
        if "start_price" not in self.data["benchmark"]:
            self.data["benchmark"]["start_price"] = btc_buy_price
            self.data["benchmark"]["start_date"] = datetime.datetime.now().isoformat()
        self.data["benchmark"]["current_price"] = btc_price
        self.data["benchmark"]["return_pct"] = round(
            (btc_price - self.data["benchmark"]["start_price"]) / self.data["benchmark"]["start_price"] * 100, 1
        )
        self.save()

    def status_report(self) -> str:
        """Generate human-readable status report."""
        lines = []
        lines.append("=" * 50)
        lines.append("V5 Moon Reversal — Paper Trading Status")
        lines.append("=" * 50)

        # Open position
        pos = self.data["open_position"]
        if pos:
            pnl = (self.data["benchmark"].get("current_price", pos["entry_price"]) - pos["entry_price"]) / pos["entry_price"] * 100
            lines.append(f"\n📈 OPEN: {pos['entry_date']} @ ${pos['entry_price']:,.0f}")
            lines.append(f"   PnL: {pnl:+.1f}% | High: ${pos['highest']:,.0f}")
            if pos["trail_active"]:
                trail = pos["highest"] * (1 - pos["trail_distance"] / 100)
                lines.append(f"   ⚡ Trail active | Stop: ${trail:,.0f}")
            lines.append(f"   Red weeks: {pos['red_week_count']}")
        else:
            lines.append("\n💤 No open position")

        # Trade history
        trades = self.data["trades"]
        if trades:
            lines.append(f"\n--- Trade History ({len(trades)} closed) ---")
            # Handle both v1 format (action/date/price/pnl_pct) and v2 (entry_date/exit_date/...)
            sells = [t for t in trades if t.get("action") == "SELL" or "pnl_pct" in t]
            for t in sells[-5:]:
                pnl = t.get("pnl_pct", 0)
                emoji = "✅" if pnl > 0 else "❌"
                if "entry_date" in t:
                    lines.append(f"  {t['entry_date']} → {t['exit_date']}: {pnl:+.1f}% {emoji} ({t['reason']})")
                else:
                    lines.append(f"  {t.get('date','?')}: {pnl:+.1f}% {emoji} ({t.get('reason','?')})")
            wins = sum(1 for t in sells if t.get("pnl_pct", 0) > 0)
            total = sum(t.get("pnl_pct", 0) for t in sells)
            lines.append(f"  Total: {len(sells)}t | WR: {wins/len(sells)*100:.0f}% | PnL: {total:+.1f}%")

        # Benchmark
        bm = self.data["benchmark"]
        if bm:
            lines.append(f"\n--- Benchmark ---")
            lines.append(f"  BTC B&H: {bm.get('return_pct', 0):+.1f}%")
            strat_return = sum(t.get("pnl_pct", 0) for t in trades if t.get("action") == "SELL" or ("pnl_pct" in t and t.get("action") != "BUY"))
            if bm.get("return_pct"):
                lines.append(f"  Alpha: {strat_return - bm['return_pct']:+.1f}%")

        # Alerts
        obs = self.data.get("observer", [])
        if obs and obs[-1].get("alerts"):
            lines.append(f"\n⚠️  ALERTS:")
            for a in obs[-1]["alerts"]:
                lines.append(f"  {a}")

        return "\n".join(lines)
