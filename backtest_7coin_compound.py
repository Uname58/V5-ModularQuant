"""
7-Coin Moon Reversal Portfolio Backtest — ¥10,000 HKD, COMPOUNDING
Rules: max 2 positions, ≤50% capital per position, RA rank priority, 0.3% fee.
Position size scales with equity (compounding).
"""
import json, datetime, urllib.request

BINANCE_BASE = "https://api.binance.com/api/v3/klines"
SYMBOLS = ["FILUSDT", "AVAXUSDT", "SOLUSDT", "INJUSDT", "NEARUSDT", "BTCUSDT", "ETHUSDT"]
RA_RANK = {"FILUSDT": 1, "AVAXUSDT": 2, "SOLUSDT": 3, "INJUSDT": 4, "NEARUSDT": 5, "BTCUSDT": 6, "ETHUSDT": 7}
START_CAPITAL = 10000
MAX_SLOTS = 2
FEE = 0.003

def fetch(symbol, interval, limit):
    url = f"{BINANCE_BASE}?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "V5-7c/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def parse(raw, fmt="monthly"):
    ts = raw[0] // 1000
    ds = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m" if fmt == "monthly" else "%Y-%m-%d")
    return {"date": ds, "open": float(raw[1]), "high": float(raw[2]),
            "low": float(raw[3]), "close": float(raw[4])}

def run_strategy(symbol):
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
            if w["high"] > highest: highest = w["high"]
            if not trail_active and (highest - entry_price) / entry_price * 100 >= 5.0:
                trail_active = True
            exit_reason, exit_price = None, None
            if w["close"] < w["open"]:
                red_count += 1
                if red_count >= 2: exit_reason, exit_price = "2red", w["close"]
            else: red_count = 0
            if trail_active and exit_reason is None:
                tp = highest * 0.96
                if w["low"] <= tp: exit_reason, exit_price = "trail", tp
            if exit_reason:
                pnl_gross = (exit_price - entry_price) / entry_price * 100
                pnl_net = pnl_gross - FEE * 100
                trades.append({"action": "SELL", "date": w["date"],
                               "entry": entry_price, "exit": exit_price,
                               "pnl_pct": round(pnl_net, 2), "reason": exit_reason})
                in_pos, entry_price, highest = False, 0, 0
                trail_active, red_count = False, 0
    return trades

def main():
    print("Fetching data...")
    all_trades = {}
    symbol_weeks = {}
    all_weeks = set()
    for sym in SYMBOLS:
        label = sym.replace("USDT", "")
        trades = run_strategy(sym)
        all_trades[sym] = trades
        sells = [t for t in trades if t["action"] == "SELL"]
        print(f"  {label:<6} {len(sells)} sells  WR {sum(1 for t in sells if t['pnl_pct']>0)/max(len(sells),1)*100:.0f}%", flush=True)
        weeks_raw = fetch(sym, "1w", 416)
        weeks = [parse(w, "weekly") for w in weeks_raw]
        symbol_weeks[sym] = {w["date"]: w for w in weeks}
        all_weeks.update(w["date"] for w in weeks)
    sorted_weeks = sorted(all_weeks)

    trade_map = {}
    for sym in SYMBOLS:
        trade_map[sym] = {}
        for t in all_trades[sym]:
            trade_map[sym][t["date"]] = t

    # Compounding simulation
    equity = START_CAPITAL
    cash = START_CAPITAL
    positions = {}  # sym -> {amount, entry_price}
    portfolio_trades = []
    equity_history = []

    for week_date in sorted_weeks:
        # Exit
        exited = []
        for sym, pos in list(positions.items()):
            t = trade_map[sym].get(week_date)
            if t and t["action"] == "SELL":
                gain = pos["amount"] * t["pnl_pct"] / 100
                cash += pos["amount"] + gain
                portfolio_trades.append({**t, "symbol": sym, "amount": pos["amount"], "gain": round(gain, 2)})
                exited.append(sym)
        for sym in exited:
            del positions[sym]

        # Update equity
        unrealized = 0
        for sym, pos in positions.items():
            w = symbol_weeks[sym].get(week_date)
            if w:
                pnl = (w["close"] - pos["entry_price"]) / pos["entry_price"] * 100
                unrealized += pos["amount"] * pnl / 100
        equity = cash + sum(p["amount"] for p in positions.values()) + unrealized
        equity_history.append((week_date, equity))

        # Entry
        available_slots = MAX_SLOTS - len(positions)
        if available_slots <= 0 or cash <= 0:
            continue

        candidates = []
        for sym in SYMBOLS:
            if sym in positions: continue
            t = trade_map[sym].get(week_date)
            if t and t["action"] == "BUY":
                candidates.append((RA_RANK[sym], sym, t))
        candidates.sort()

        per_position = equity * 0.5
        for _, sym, t in candidates[:available_slots]:
            amount = min(per_position, cash)
            if amount < 100: continue
            positions[sym] = {"entry_price": t["price"], "amount": amount}
            cash -= amount

    # Close open
    for sym, pos in positions.items():
        last_close = list(symbol_weeks[sym].values())[-1]["close"]
        pnl = (last_close - pos["entry_price"]) / pos["entry_price"] * 100 - FEE * 100
        gain = pos["amount"] * pnl / 100
        cash += pos["amount"] + gain
        portfolio_trades.append({"symbol": sym, "date": "open", "pnl_pct": round(pnl, 2),
                                 "amount": pos["amount"], "gain": round(gain, 2)})
    final_equity = cash

    # BH comparison
    bh_value = 0
    for sym in SYMBOLS:
        price_first = list(symbol_weeks[sym].values())[0]["close"]
        price_last = list(symbol_weeks[sym].values())[-1]["close"]
        alloc = START_CAPITAL / len(SYMBOLS)
        bh_value += alloc / price_first * price_last

    # OUTPUT
    print(f"\n{'='*65}")
    print(f"  7-Coin Moon Reversal — ¥{START_CAPITAL:,} HKD, COMPOUNDING")
    print(f"  50% capital/pos, ≤2 slots, RA priority, 0.3% fee")
    print(f"{'='*65}")

    closed = [t for t in portfolio_trades if t["date"] != "open"]
    open_t = [t for t in portfolio_trades if t["date"] == "open"]
    print(f"\n  Executed: {len(closed)} closed + {len(open_t)} forced-close = {len(portfolio_trades)} total")
    if closed:
        wins = sum(1 for t in closed if t["gain"] > 0)
        avg_win = sum(t["gain"] for t in closed if t["gain"] > 0) / max(sum(1 for t in closed if t["gain"] > 0), 1)
        avg_loss = sum(t["gain"] for t in closed if t["gain"] < 0) / max(sum(1 for t in closed if t["gain"] < 0), 1)
        print(f"  Win rate: {wins}/{len(closed)} ({wins/len(closed)*100:.0f}%)")
        print(f"  Avg win: ¥{avg_win:+,.0f}  |  Avg loss: ¥{avg_loss:+,.0f}")
    print(f"\n  Starting:  ¥{START_CAPITAL:,}")
    print(f"  Final:     ¥{final_equity:,.0f}")
    print(f"  Return:    {(final_equity-START_CAPITAL)/START_CAPITAL*100:+.1f}%")
    print(f"  B&H equal: ¥{bh_value:,.0f} ({(bh_value-START_CAPITAL)/START_CAPITAL*100:+.1f}%)")

    # Year by year
    print(f"\n  ── Annual ──")
    years = {}
    for d, e in equity_history:
        y = d[:4]
        if y not in years: years[y] = (e, e)
        years[y] = (years[y][0], e)
    for y in sorted(years):
        start_e = years[y][0]
        end_e = years[y][1]
        ret = (end_e - start_e) / start_e * 100
        print(f"  {y}: ¥{start_e:,.0f} → ¥{end_e:,.0f} ({ret:+.1f}%)")

    # Top and worst trades
    print(f"\n  ── Best/Worst ──")
    closed_sorted = sorted(closed, key=lambda t: t["gain"], reverse=True)
    for t in closed_sorted[:3]:
        print(f"  🟢 {t['date']} {t['symbol'].replace('USDT',''):<6} ¥{t['amount']:,.0f} → {t['pnl_pct']:+.1f}% = ¥{t['gain']:+,.0f}")
    print(f"  ...")
    for t in closed_sorted[-3:]:
        print(f"  🔴 {t['date']} {t['symbol'].replace('USDT',''):<6} ¥{t['amount']:,.0f} → {t['pnl_pct']:+.1f}% = ¥{t['gain']:+,.0f}")

    # Worst drawdown (forward-only: peak must precede trough)
    dates = [d for d, _ in equity_history]
    eqs = [e for _, e in equity_history]
    peak, mdd, mdd_start, mdd_end = eqs[0], 0, dates[0], dates[0]
    peak_date = dates[0]
    for i in range(1, len(eqs)):
        if eqs[i] > peak:
            peak, peak_date = eqs[i], dates[i]
        dd = (peak - eqs[i]) / peak * 100
        if dd > mdd:
            mdd, mdd_start, mdd_end = dd, peak_date, dates[i]
    print(f"\n  Max DD: {mdd:.1f}%  (peak {mdd_start} → trough {mdd_end})")

if __name__ == "__main__":
    main()
