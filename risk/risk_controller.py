"""
Risk Controller — one-vote veto. Highest authority in V5.
Checks before ANY trade: risk pause, position limits, event overrides.
"""
import json, os, datetime

V5_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SF = os.path.join(V5_DIR, "data", "news_state.json")

POS_CAP = 0.50; MAX_EXP = 1.0; MIN_LIQ = 100_000

def _load_state():
    try:
        with open(SF) as f: return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): return {}

def is_risk_paused() -> bool:
    return _load_state().get("risk_pause", False)

def active_s_events() -> list:
    return _load_state().get("active_s_events", [])

def clear_risk_pause():
    s = _load_state()
    if not s: return False
    s.update(risk_pause=False, active_s_events=[], cleared_at=datetime.datetime.now().isoformat(), cleared_by="manual")
    with open(SF, "w") as f: json.dump(s, f, indent=2)
    return True

def _veto(approved, level, reason, lim="", checks=None):
    return {"approved": approved, "risk_level": level, "veto_reason": reason,
            "position_limit": lim, "required_checks": checks or []}

def pre_trade_check(sym, amt_hkd, capital, liq_usd=None):
    if is_risk_paused():
        ev = active_s_events()
        return _veto(False, "high", f"S-level: {ev[0].get('title','unknown')[:80] if ev else 'unknown'}", checks=["manual_review","clear_risk_pause"])
    if amt_hkd > capital * POS_CAP:
        return _veto(False, "high", f"Position ¥{amt_hkd:,.0f} > {POS_CAP*100:.0f}% cap (¥{capital*POS_CAP:,.0f})", lim=f"¥{capital*POS_CAP:,.0f}", checks=["reduce_position_size"])
    if liq_usd is not None and liq_usd < MIN_LIQ:
        return _veto(False, "medium", f"Volume ${liq_usd:,.0f} < ${MIN_LIQ:,.0f}", lim=f"¥{amt_hkd:,.0f}", checks=["liquidity_verify"])
    return _veto(True, "low", "", lim=f"¥{min(amt_hkd, capital*POS_CAP):,.0f}")

def pre_trade_sell_check(sym, reason):
    return _veto(True, "low", "", checks=[])

def full_audit(positions, capital, prices=None):
    rpt = {"risk_pause": is_risk_paused(), "active_s_events": active_s_events(),
           "total_exposure_pct": 0, "position_count": len(positions), "violations": [], "warnings": []}
    tot = sum(p["amount_hkd"] for p in positions)
    rpt["total_exposure_pct"] = round(tot/capital*100, 1) if capital > 0 else 0
    if rpt["total_exposure_pct"] > MAX_EXP * 100:
        rpt["violations"].append(f"Total exposure {rpt['total_exposure_pct']:.0f}% > {MAX_EXP*100:.0f}%")
    for p in positions:
        if p["amount_hkd"] > capital * POS_CAP:
            rpt["violations"].append(f"{p['symbol']}: ¥{p['amount_hkd']:,.0f} > {POS_CAP*100:.0f}% cap")
    if rpt["risk_pause"]:
        rpt["warnings"].append("🔴 Risk pause active — new BUYs blocked")
    return rpt

if __name__ == "__main__":
    print("Risk Controller Status:")
    print(f"  Risk Pause: {'🔴 ACTIVE' if is_risk_paused() else '🟢 CLEAR'}")
    for e in active_s_events():
        print(f"  S-Event: {e.get('title', '?')[:100]}")
    r = pre_trade_check("BTCUSDT", 5000, 10000)
    print(f"  Pre-trade check: {'✅' if r['approved'] else '⛔'} {r['risk_level']}")
