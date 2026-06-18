"""
7-Coin Moon Reversal Portfolio Backtest — ¥10,000 HKD principal
Rules: max 2 positions, ≤¥5,000 per position, RA rank priority.
"""
import json, datetime, urllib.request, sys, os

BINANCE_BASE = "https://api.binance.com/api/v3/klines"
SYMBOLS = ["FILUSDT", "AVAXUSDT", "SOLUSDT", "INJUSDT", "NEARUSDT", "BTCUSDT", "ETHUSDT"]
RA_RANK = {"FILUSDT": 1, "AVAXUSDT": 2, "SOLUSDT": 3, "INJUSDT": 4, "NEARUSDT": 5, "BTCUSDT": 6, "ETHUSDT": 7}
CAPITAL = 10000   # HKD
MAX_POS = 5000    # 50% per position
MAX_SLOTS = 2
FEE = 0.003       # 0.3% round trip

def fetch(symbol, interval, limit):
    url = f"{BINANCE_BASE}?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "V5-7coin/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def parse(raw, fmt="monthly"):
    ts = raw[0] // 1000
    ds = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m" if fmt == "monthly" else "%Y-%m-%d")
    return {"date": ds, "open": float(raw[1]), "high": float(raw[2]),
            "low": float(raw[3]), "close": float(raw[4])}

def run_strategy(symbol):
    """Run Moon Reversal on one symbol. Returns list of SELL trade dicts."""
    months_raw = fetch(symbol, "1M", 96)
    weeks_raw = fetch(symbol, "1w", 416)
    months = [parse(m, "monthly") for m in months_raw]
    weeks = [parse(w, "weekly") for w in weeks_raw]
    month_map = {m["date"]: m for m in months}

    trades = []
    in_pos, entry_price, highest, trail_active = False, 0, 0, False
    red_count, entry_allowed = 0, False
    last_month = None

    for w in weeks:
        ym = w["date"][:7]
        if last_month and ym != last_month and last_month in month_map:
            m = month_map[last_month]
            entry_allowed = (m["close"] < m["open"])
        last_month = ym

        if not in_pos:
            if entry_allowed and w["close"] > w["open"]:
                in_pos, entry_price, highest = True, w["close"], w["close"]
                trail_active, red_count = False, 0
                entry_allowed = False
                trades.append({"action": "BUY", "date": w["date"], "price": w["close"]})
            elif w["close"] > w["open"]:
                entry_allowed = False
        else:
            if w["high"] > highest:
                highest = w["high"]
            if not trail_active:
                if (highest - entry_price) / entry_price * 100 >= 5.0:
                    trail_active = True
            exit_reason, exit_price = None, None
            if w["close"] < w["open"]:
                red_count += 1
                if red_count >= 2:
                    exit_reason, exit_price = "2red", w["close"]
            else:
                red_count = 0
            if trail_active and exit_reason is None:
                tp = highest * 0.96
                if w["low"] <= tp:
                    exit_reason, exit_price = "trail", tp
            if exit_reason:
                pnl_gross = (exit_price - entry_price) / entry_price * 100
                pnl_net = pnl_gross - FEE * 100
                trades.append({"action": "SELL", "date": w["date"],
                               "entry": entry_price, "exit": exit_price,
                               "pnl_pct": round(pnl_net, 2), "reason": exit_reason})
                in_pos, entry_price, highest = False, 0, 0
                trail_active, red_count = False, 0
    return trades

def portfolio_backtest():
    print("Fetching data for 7 coins...")
    all_trades = {}
    for sym in SYMBOLS:
        label = sym.replace("USDT", "")
        trades = run_strategy(sym)
        all_trades[sym] = trades
        sells = [t for t in trades if t["action"] == "SELL"]
        print(f"  {label:<6} {len(sells)} sells", end="")
        if sells:
            wins = sum(1 for t in sells if t["pnl_pct"] > 0)
            total = sum(t["pnl_pct"] for t in sells)
            print(f"  WR {wins/len(sells)*100:.0f}%  return {total:+.1f}%")
        else:
            print()

    # Portfolio simulation: walk through all weeks chronologically, apply RA priority
    # Collect all weeks across all symbols
    all_weeks = set()
    symbol_weeks = {}
    for sym in SYMBOLS:
        weeks_raw = fetch(sym, "1w", 416)
        weeks = [parse(w, "weekly") for w in weeks_raw]
        symbol_weeks[sym] = {w["date"]: w for w in weeks}
        all_weeks.update(w["date"] for w in weeks)
    sorted_weeks = sorted(all_weeks)

    # Build trade lookup: symbol → {date: trade}
    trade_map = {}
    for sym in SYMBOLS:
        trade_map[sym] = {}
        for t in all_trades[sym]:
            trade_map[sym][t["date"]] = t

    # Portfolio simulation
    cash = CAPITAL
    positions = {}  # symbol → {entry_price, amount_hkd, pnl_pct}
    portfolio_trades = []  # executed SELLs

    for week_date in sorted_weeks:
        # Check exits first
        exited = []
        for sym, pos in list(positions.items()):
            t = trade_map[sym].get(week_date)
            if t and t["action"] == "SELL":
                gain = pos["amount_hkd"] * t["pnl_pct"] / 100
                cash += pos["amount_hkd"] + gain
                portfolio_trades.append({**t, "symbol": sym, "amount": pos["amount_hkd"], "gain": round(gain, 2)})
                exited.append(sym)
        for sym in exited:
            del positions[sym]

        # Check entries — only if we have open slots
        available_slots = MAX_SLOTS - len(positions)
        if available_slots <= 0:
            continue

        # Collect BUY signals this week, sorted by RA rank
        candidates = []
        for sym in SYMBOLS:
            if sym in positions:
                continue
            t = trade_map[sym].get(week_date)
            if t and t["action"] == "BUY":
                candidates.append((RA_RANK[sym], sym, t))

        candidates.sort()  # lower rank = higher priority
        for _, sym, t in candidates[:available_slots]:
            amount = min(MAX_POS, cash / available_slots)
            if amount < 100:  # min ¥100 per trade
                continue
            positions[sym] = {"entry_price": t["price"], "amount_hkd": amount, "entry_date": week_date}
            cash -= amount

    # Close any open positions at last price
    for sym, pos in positions.items():
        last_close = list(symbol_weeks[sym].values())[-1]["close"]
        pnl = (last_close - pos["entry_price"]) / pos["entry_price"] * 100 - FEE * 100
        gain = pos["amount_hkd"] * pnl / 100
        cash += pos["amount_hkd"] + gain
        portfolio_trades.append({"symbol": sym, "date": "open", "pnl_pct": round(pnl, 2),
                                 "amount": pos["amount_hkd"], "gain": round(gain, 2)})

    # ── OUTPUT ──
    print("\n" + "=" * 70)
    print(f"  7-Coin Moon Reversal Portfolio Backtest — ¥{CAPITAL:,} HKD")
    print("  Rules: ≤2 positions, ≤¥5,000/pos, RA rank priority, 0.3% fee")
    print("=" * 70)

    # Per-coin stats
    print(f"\n  {'Symbol':<8} {'Sells':>5} {'WR':>6} {'Return':>9} {'AvgPnL':>8} {'MaxDD':>8}")
    print("  " + "-" * 50)
    for sym in SYMBOLS:
        sells = [t for t in all_trades[sym] if t["action"] == "SELL"]
        if not sells:
            print(f"  {sym.replace('USDT',''):<8} {0:>5}")
            continue
        wins = sum(1 for t in sells if t["pnl_pct"] > 0)
        wr = wins / len(sells) * 100
        total = sum(t["pnl_pct"] for t in sells)
        avg = total / len(sells)
        # MaxDD on cumulative
        cum, peak, mdd = 0, 0, 0
        for t in sells:
            cum += t["pnl_pct"]
            if cum > peak: peak = cum
            dd = peak - cum
            if dd > mdd: mdd = dd
        print(f"  {sym.replace('USDT',''):<8} {len(sells):>5} {wr:>5.0f}% {total:>+8.1f}% {avg:>+7.2f}% {mdd:>7.1f}%")

    # Portfolio stats
    closed = [t for t in portfolio_trades if t["date"] != "open"]
    open_trades = [t for t in portfolio_trades if t["date"] == "open"]
    total_gain = sum(t["gain"] for t in portfolio_trades)
    final_value = cash

    print(f"\n  ── Portfolio ──")
    print(f"  Executed trades: {len(closed)}")
    print(f"  Open (forced close): {len(open_trades)}")
    if closed:
        wins = sum(1 for t in closed if t["gain"] > 0)
        wr = wins / len(closed) * 100
        avg_gain = sum(t["gain"] for t in closed) / len(closed)
        total_gain_closed = sum(t["gain"] for t in closed)
        print(f"  Closed WR: {wr:.0f}%  |  Avg gain/trade: ¥{avg_gain:+,.0f}")
        print(f"  Closed total gain: ¥{total_gain_closed:+,.0f}")
    print(f"  Final value: ¥{final_value:,.0f}  |  Return: {(final_value-CAPITAL)/CAPITAL*100:+.1f}%")

    # Print trade log
    print(f"\n  ── Trade Log ──")
    for t in portfolio_trades:
        label = t["symbol"].replace("USDT", "")
        status = "OPEN" if t["date"] == "open" else "CLOSED"
        print(f"  {t['date']} | {label:<6} | {status:<6} | ¥{t['amount']:,.0f} → {t['pnl_pct']:+.1f}% = ¥{t['gain']:+,.0f}")

if __name__ == "__main__":
    portfolio_backtest()
