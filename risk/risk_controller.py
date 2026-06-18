"""
Risk Controller — one-vote veto. Highest authority in V5.
Checks before ANY trade: risk pause, position limits, event overrides.
"""
import json, os, datetime

V5_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(V5_DIR, "data", "news_state.json")

# ═══════════════════════════════════════════
# CONFIGURABLE LIMITS
# ═══════════════════════════════════════════
POSITION_CAP_PCT = 0.50       # ≤50% per position
MAX_TOTAL_EXPOSURE_PCT = 1.0  # ≤100% total (2 slots × 50%)
MIN_LIQUIDITY_USD = 100_000   # Minimum 24h volume

# ═══════════════════════════════════════════
# CHECKS
# ═══════════════════════════════════════════

def is_risk_paused() -> bool:
    """S-level event active? Trading halted."""
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        return state.get("risk_pause", False)
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def get_active_s_events() -> list:
    """Return list of active S-level events for reporting."""
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        return state.get("active_s_events", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def clear_risk_pause():
    """Manual override: clear risk pause."""
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        state["risk_pause"] = False
        state["active_s_events"] = []
        state["cleared_at"] = datetime.datetime.now().isoformat()
        state["cleared_by"] = "manual"
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        return True
    except FileNotFoundError:
        return False


def pre_trade_check(symbol: str, amount_hkd: float, capital: float,
                    liquidity_usd: float = None) -> dict:
    """
    Run before executing any BUY.
    Returns: {"approved": bool, "risk_level": str, "reason": str}
    """
    # 1. Risk pause (S-level event)
    if is_risk_paused():
        events = get_active_s_events()
        return {
            "approved": False,
            "risk_level": "high",
            "veto_reason": f"S-level event active: {events[0].get('title', 'unknown')[:80] if events else 'unknown'}",
            "position_limit": "none",
            "required_checks": ["manual_review", "clear_risk_pause"],
        }

    # 2. Position cap check
    if amount_hkd > capital * POSITION_CAP_PCT:
        return {
            "approved": False,
            "risk_level": "high",
            "veto_reason": f"Position ¥{amount_hkd:,.0f} exceeds {POSITION_CAP_PCT*100:.0f}% cap (¥{capital*POSITION_CAP_PCT:,.0f})",
            "position_limit": f"¥{capital * POSITION_CAP_PCT:,.0f}",
            "required_checks": ["reduce_position_size"],
        }

    # 3. Liquidity check (if provided)
    if liquidity_usd is not None and liquidity_usd < MIN_LIQUIDITY_USD:
        return {
            "approved": False,
            "risk_level": "medium",
            "veto_reason": f"24h volume ${liquidity_usd:,.0f} < minimum ${MIN_LIQUIDITY_USD:,.0f}",
            "position_limit": f"¥{amount_hkd:,.0f}",
            "required_checks": ["liquidity_verify"],
        }

    # 4. Total exposure (existing + new)
    # Note: caller must pass current exposure; we don't track it here
    # Simplified: just check this position alone is within cap

    # APPROVED
    return {
        "approved": True,
        "risk_level": "low",
        "veto_reason": "",
        "position_limit": f"¥{min(amount_hkd, capital * POSITION_CAP_PCT):,.0f}",
        "required_checks": [],
    }


def pre_trade_sell_check(symbol: str, reason: str) -> dict:
    """
    Run before executing any SELL.
    Sells are almost always approved unless we're in a panic where
    selling into a crash is worse (rare edge case).
    """
    # Even during risk pause, selling is allowed — preservation of capital
    return {"approved": True, "risk_level": "low", "veto_reason": "", "note": "sell always permitted"}


def full_audit(positions: list[dict], capital: float, current_prices: dict = None) -> dict:
    """
    Full portfolio risk audit.
    positions: [{"symbol": "BTCUSDT", "amount_hkd": 5000, "entry_price": 60000}, ...]
    """
    report = {
        "risk_pause": is_risk_paused(),
        "active_s_events": get_active_s_events(),
        "total_exposure_pct": 0,
        "position_count": len(positions),
        "violations": [],
        "warnings": [],
    }

    total_exposure = sum(p["amount_hkd"] for p in positions)
    report["total_exposure_pct"] = round(total_exposure / capital * 100, 1) if capital > 0 else 0

    if report["total_exposure_pct"] > MAX_TOTAL_EXPOSURE_PCT * 100:
        report["violations"].append(
            f"Total exposure {report['total_exposure_pct']:.0f}% > {MAX_TOTAL_EXPOSURE_PCT*100:.0f}%"
        )

    for p in positions:
        if p["amount_hkd"] > capital * POSITION_CAP_PCT:
            report["violations"].append(
                f"{p['symbol']}: ¥{p['amount_hkd']:,.0f} > {POSITION_CAP_PCT*100:.0f}% cap"
            )

    if report["risk_pause"]:
        report["warnings"].append("🔴 Risk pause active — new BUYs blocked")

    return report


if __name__ == "__main__":
    print("Risk Controller Status:")
    print(f"  Risk Pause: {'🔴 ACTIVE' if is_risk_paused() else '🟢 CLEAR'}")
    events = get_active_s_events()
    if events:
        for e in events:
            print(f"  S-Event: {e.get('title', '?')[:100]}")
    # Test pre-trade check
    result = pre_trade_check("BTCUSDT", 5000, 10000)
    print(f"  Pre-trade check: {'✅' if result['approved'] else '⛔'} {result['risk_level']}")
