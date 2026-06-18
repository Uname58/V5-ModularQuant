"""
Convert Executor — Execute trades via Binance Convert (no order book, no slippage).
Replaces spot market orders for instant, guaranteed execution.

API: ccxt fetch_convert_quote + fetch_convert_trade
Docs: https://www.binance.com/en/support/faq/how-to-use-binance-convert
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


def get_quote(from_asset: str, to_asset: str, from_amount: float) -> dict:
    """
    Get a convert quote (RFQ). Quote expires in ~10 seconds.
    Returns: {"quote_id": str, "to_amount": float, "ratio": float, "valid_seconds": int}
    """
    ex = _get_exchange()
    try:
        result = ex.fetch_convert_quote(from_asset, to_asset, from_amount)
        return {
            "quote_id": result.get("quoteId", ""),
            "from_amount": float(result.get("fromAmount", from_amount)),
            "to_amount": float(result.get("toAmount", 0)),
            "ratio": float(result.get("ratio", 0)),
            "valid_seconds": int(result.get("validTime", "10s").replace("s", "")),
        }
    except Exception as e:
        return {"error": str(e), "from_amount": from_amount, "to_amount": 0}


def execute_trade(from_asset: str, to_asset: str, from_amount: float) -> dict:
    """
    Execute a convert trade. Gets quote then immediately accepts it.
    Returns: {"success": bool, "quote_id": str, "order_id": str,
              "from_amount": float, "to_amount": float, "fee_asset": str, "fee_amount": float}
    """
    ex = _get_exchange()
    # Step 1: Get quote
    quote = get_quote(from_asset, to_asset, from_amount)
    if "error" in quote:
        return {"success": False, "error": quote["error"], "from_amount": from_amount}

    # Step 2: Accept quote
    try:
        result = ex.fetch_convert_trade(quote["quote_id"])
        return {
            "success": True,
            "quote_id": quote["quote_id"],
            "order_id": result.get("orderId", ""),
            "from_amount": float(result.get("fromAmount", from_amount)),
            "to_amount": float(result.get("toAmount", 0)),
            "fee_asset": result.get("feeAsset", ""),
            "fee_amount": float(result.get("fee", 0)),
            "price": quote["ratio"],
        }
    except Exception as e:
        return {"success": False, "error": str(e), "quote_id": quote["quote_id"],
                "from_amount": from_amount}


def buy(crypto: str, usdt_amount: float) -> dict:
    """
    Buy crypto with USDT via Convert.
    crypto: e.g. 'BTC', 'ETH', 'SOL'
    usdt_amount: USDT to spend
    """
    return execute_trade("USDT", crypto, usdt_amount)


def sell(crypto: str, crypto_amount: float) -> dict:
    """
    Sell crypto for USDT via Convert.
    crypto: e.g. 'BTC', 'ETH', 'SOL'
    crypto_amount: crypto to sell
    """
    return execute_trade(crypto, "USDT", crypto_amount)


def buy_all_usdt(crypto: str) -> dict:
    """Buy as much crypto as possible with all available USDT."""
    ex = _get_exchange()
    try:
        balance = ex.fetch_balance()
        usdt_free = float(balance["USDT"].get("free", 0))
    except Exception:
        return {"success": False, "error": "failed to fetch balance"}

    if usdt_free < 1.0:
        return {"success": False, "error": "USDT balance too low", "usdt_free": usdt_free}
    return buy(crypto, usdt_free)


def sell_all(crypto: str) -> dict:
    """Sell all available crypto for USDT."""
    ex = _get_exchange()
    try:
        balance = ex.fetch_balance()
        free = float(balance[crypto].get("free", 0))
    except Exception:
        return {"success": False, "error": "failed to fetch balance"}

    if free <= 0:
        return {"success": False, "error": f"no {crypto} balance", "free": free}
    return sell(crypto, free)


def get_history(start_time: Optional[int] = None, limit: int = 20) -> list:
    """Return Convert trade history."""
    ex = _get_exchange()
    params = {"limit": limit}
    if start_time:
        params["startTime"] = start_time
    try:
        return ex.fetch_convert_trade_history(symbol=None, since=start_time, params=params)
    except Exception as e:
        print(f"[Convert] history error: {e}")
        return []


def list_pairs(from_asset: Optional[str] = None, to_asset: Optional[str] = None) -> list:
    """List available convert pairs, optionally filtered."""
    ex = _get_exchange()
    try:
        result = ex.fetch_convert_currencies()
        pairs = []
        for item in result if isinstance(result, list) else result.get("data", []):
            f = item.get("fromAsset", "")
            t = item.get("toAsset", "")
            if from_asset and f != from_asset:
                continue
            if to_asset and t != to_asset:
                continue
            pairs.append({"from": f, "to": t, "min": float(item.get("min", 0))})
        return pairs
    except Exception as e:
        print(f"[Convert] pairs error: {e}")
        return []


if __name__ == "__main__":
    # Quick test: get quote only (no execution)
    q = get_quote("USDT", "BTC", 100)
    print(f"Quote: 100 USDT → {q.get('to_amount', 0)} BTC  (ratio: {q.get('ratio', 0)})")
    if "error" in q:
        print(f"Error: {q['error']}")
