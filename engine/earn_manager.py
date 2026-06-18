"""
Earn Manager — Binance Simple Earn (Flexible Savings) for idle USDT.
Subscribe idle balance to Flexible Earn when not in positions.
Auto-redeem before trading.

API: ccxt implicit methods on Binance Simple Earn endpoints.
Docs: https://www.binance.com/en/support/faq/binance-simple-earn-flexible
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import Optional


def _get_exchange():
    import ccxt
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    return ccxt.binance({
        "apiKey": os.getenv("BINANCE_API_KEY"),
        "secret": os.getenv("BINANCE_SECRET_KEY"),
        "options": {"defaultType": "spot"},
        "adjustForTimeDifference": True,
    })


def get_flexible_position(asset: str = "USDT") -> Optional[dict]:
    """Return Flexible Earn position for given asset, or None."""
    ex = _get_exchange()
    try:
        result = ex.sapi_get_simple_earn_flexible_position({"asset": asset})
        rows = result.get("rows", [])
        for r in rows:
            if r["asset"] == asset:
                return {
                    "asset": r["asset"],
                    "total_amount": float(r["totalAmount"]),
                    "tier_apr": float(r.get("tierAnnualPercentageRate", 0)),
                    "can_redeem": float(r.get("canRedeem", 0)),
                }
        return None
    except Exception as e:
        print(f"[Earn] get_position error: {e}")
        return None


def get_available_apr(asset: str = "USDT") -> float:
    """Return current Flexible APR for asset (%), or 0."""
    ex = _get_exchange()
    try:
        result = ex.sapi_get_simple_earn_flexible_list({"asset": asset})
        rows = result.get("rows", [])
        for r in rows:
            if r["asset"] == asset:
                apr_val = float(r.get("latestAnnualPercentageRate", 0)) * 100
                return apr_val
        return 0
    except Exception as e:
        print(f"[Earn] APR error: {e}")
        return 0


def subscribe(amount: float, asset: str = "USDT") -> dict:
    """
    Subscribe amount to Flexible Earn.
    Returns: {"success": bool, "txn_id": str, "amount": float}
    """
    ex = _get_exchange()
    try:
        result = ex.sapi_post_simple_earn_flexible_subscribe({
            "asset": asset,
            "amount": str(amount),
        })
        return {
            "success": result.get("success", False),
            "txn_id": result.get("txnId", ""),
            "amount": amount,
        }
    except Exception as e:
        print(f"[Earn] subscribe error: {e}")
        return {"success": False, "error": str(e), "amount": amount}


def redeem(amount: float, asset: str = "USDT") -> dict:
    """
    Redeem amount from Flexible Earn back to spot wallet.
    Returns: {"success": bool, "txn_id": str, "amount": float}
    """
    ex = _get_exchange()
    try:
        result = ex.sapi_post_simple_earn_flexible_redeem({
            "asset": asset,
            "amount": str(amount),
        })
        return {
            "success": result.get("success", False),
            "txn_id": result.get("txnId", ""),
            "amount": amount,
        }
    except Exception as e:
        print(f"[Earn] redeem error: {e}")
        return {"success": False, "error": str(e), "amount": amount}


def redeem_all(asset: str = "USDT") -> dict:
    """Redeem entire Flexible Earn position back to spot."""
    pos = get_flexible_position(asset)
    if not pos or pos["can_redeem"] <= 0:
        return {"success": True, "amount": 0, "note": "no position to redeem"}
    return redeem(pos["can_redeem"], asset)


def auto_manage(asset: str = "USDT", reserve: float = 10.0) -> dict:
    """
    Subscribe all idle spot balance above reserve to Flexible Earn.
    Returns status dict with actions taken.
    """
    ex = _get_exchange()
    try:
        balance = ex.fetch_balance()
        free = float(balance[asset].get("free", 0))
    except Exception as e:
        return {"error": str(e), "spot_free": 0, "subscribed": 0, "total_earn": 0}

    pos = get_flexible_position(asset)
    total_earn = pos["total_amount"] if pos else 0
    apr = get_available_apr(asset)

    # Idle = spot free - reserve
    idle = max(0, free - reserve)
    result = {
        "spot_free": free,
        "earn_balance": total_earn,
        "apr_pct": apr,
        "subscribed": 0,
        "reserve": reserve,
    }

    if idle > 1.0:  # Min 1 USDT to trigger
        sub = subscribe(idle, asset)
        result["subscribed"] = idle if sub["success"] else 0
        if sub["success"]:
            pos = get_flexible_position(asset)
            result["earn_balance"] = pos["total_amount"] if pos else total_earn

    return result


def status(asset: str = "USDT") -> dict:
    """Return full Earn + spot status for asset."""
    ex = _get_exchange()
    try:
        balance = ex.fetch_balance()
        free = float(balance[asset].get("free", 0))
    except Exception:
        free = 0

    pos = get_flexible_position(asset)
    apr = get_available_apr(asset)
    return {
        "asset": asset,
        "spot_free": free,
        "earn_balance": pos["total_amount"] if pos else 0,
        "apr_pct": apr,
        "can_redeem": pos["can_redeem"] if pos else 0,
    }


if __name__ == "__main__":
    s = status("USDT")
    print(f"Spot: ${s['spot_free']:.2f}  |  Earn: ${s['earn_balance']:.2f}  |  APR: {s['apr_pct']:.1f}%")
    if s["earn_balance"] > 0:
        print(f"Redeemable: ${s['can_redeem']:.2f}")
