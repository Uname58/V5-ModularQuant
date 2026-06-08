"""
Signal Engine — wraps strategy + data fetching for signal generation.
Supports multi-symbol via `symbol` parameter (default BTCUSDT).
"""
import sys, os, json, datetime, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import Optional
from config import BINANCE_BASE, MONTHLY_LIMIT, WEEKLY_LIMIT


def _kline_url(symbol: str, interval: str, limit: int) -> str:
    return f"{BINANCE_BASE}?symbol={symbol}&interval={interval}&limit={limit}"


def fetch(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "V5-SignalEngine/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def parse_candle(raw: list, fmt: str = "monthly") -> dict:
    ts = raw[0] // 1000
    return {
        "date": datetime.datetime.fromtimestamp(ts).strftime(
            "%Y-%m" if fmt == "monthly" else "%Y-%m-%d"),
        "open": float(raw[1]), "high": float(raw[2]),
        "low": float(raw[3]), "close": float(raw[4]),
    }


def fetch_data(symbol: str = "BTCUSDT"):
    """Fetch monthly and weekly klines for given symbol."""
    months_raw = fetch(_kline_url(symbol, "1M", MONTHLY_LIMIT))
    weeks_raw = fetch(_kline_url(symbol, "1w", WEEKLY_LIMIT))
    months = [parse_candle(m, "monthly") for m in months_raw]
    weeks = [parse_candle(w, "weekly") for w in weeks_raw]
    return months, weeks, {m["date"]: m for m in months}


def check_signal(strategy_class=None, symbol: str = "BTCUSDT") -> dict:
    """
    Run strategy through entire history, return last signal + current status.
    """
    from strategies import MoonReversalStrategy
    Strat = strategy_class or MoonReversalStrategy

    months, weeks, month_map = fetch_data(symbol)
    strat = Strat()
    last_month = None
    last_signal = None

    for w in weeks:
        ym = w["date"][:7]
        if last_month and ym != last_month and last_month in month_map:
            strat.feed_monthly(month_map[last_month])
        last_month = ym
        signal = strat.feed_weekly(w)
        if signal:
            last_signal = signal

    completed_month = months[-2] if len(months) >= 2 else months[-1]
    current_month = months[-1]
    prev_red = completed_month["close"] < completed_month["open"]
    is_red = weeks[-1]["close"] < weeks[-1]["open"]

    return {
        "symbol": symbol,
        "last_week": weeks[-1]["date"],
        "last_price": weeks[-1]["close"],
        "prev_month": completed_month["date"],
        "prev_month_red": prev_red,
        "prev_month_return": round(
            (completed_month["close"] - completed_month["open"]) / completed_month["open"] * 100, 1
        ),
        "current_month": current_month["date"],
        "current_week_red": is_red,
        "entry_gate_open": prev_red and not strat.in_position,
        "in_position": strat.in_position,
        "entry_price": strat.entry_price if strat.in_position else None,
        "trail_active": strat.trail_active if strat.in_position else None,
        "trail_stop_price": round(strat.highest * 0.96) if strat.in_position and strat.trail_active else None,
        "last_signal": last_signal,
    }


def run_backtest(strategy_class=None, initial_capital=None, symbol: str = "BTCUSDT"):
    """Run full backtest with realistic execution."""
    from strategies import MoonReversalStrategy
    from engine.backtest_engine import BacktestEngine
    from engine.execution_simulator import ExecutionSimulator

    Strat = strategy_class or MoonReversalStrategy
    months, weeks, month_map = fetch_data(symbol)

    strat = Strat()
    engine = BacktestEngine(
        initial_capital=initial_capital,
        strategy=strat,
        executor=ExecutionSimulator(),
    )
    last_month = None

    for w in weeks:
        ym = w["date"][:7]
        if last_month and ym != last_month and last_month in month_map:
            strat.feed_monthly(month_map[last_month])
        last_month = ym
        signal = strat.feed_weekly(w)
        if signal:
            if signal["action"] == "BUY":
                engine.buy(signal["date"], signal["price"], signal["reason"])
            else:
                engine.sell(signal["date"], signal["price"], signal["reason"])

    return engine, months, weeks
