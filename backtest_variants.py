"""
4-Strategy Variant Backtest — Same BTC 8yr data, same core Moon Reversal,
4 different meta-strategies compared against baseline.

Variants:
  A: Regime-gated — skip sideways, tighten bull, widen panic
  B: Dynamic params — trailing stop adjusted per regime
  C: Signal stacking — +RSI filter + volume confirmation
  D: Walk-forward — monthly best-of-N selector (24mo lookback)
"""
import sys, os, json, datetime, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import Optional
from config import BINANCE_BASE, MONTHLY_LIMIT, WEEKLY_LIMIT, DAILY_LIMIT

# ── Data Fetch ──
def fetch(url: str) -> list:
    req = urllib.request.Request(url, headers={"User-Agent": "V5-Backtest/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def parse_candle(raw: list, fmt: str = "monthly") -> dict:
    ts = raw[0] // 1000
    fmt_str = "%Y-%m" if fmt == "monthly" else ("%Y-%m-%d" if fmt in ("weekly", "daily") else "%Y-%m-%d")
    return {"date": datetime.datetime.fromtimestamp(ts).strftime(fmt_str),
            "open": float(raw[1]), "high": float(raw[2]),
            "low": float(raw[3]), "close": float(raw[4]), "volume": float(raw[5])}

def fetch_data_8yr(symbol: str = "BTCUSDT"):
    """Fetch 8 years (96 months, 416 weeks)"""
    months_raw = fetch(f"{BINANCE_BASE}?symbol={symbol}&interval=1M&limit=96")
    weeks_raw = fetch(f"{BINANCE_BASE}?symbol={symbol}&interval=1w&limit=416")
    months = [parse_candle(m, "monthly") for m in months_raw]
    weeks = [parse_candle(w, "weekly") for w in weeks_raw]
    return months, weeks, {m["date"]: m for m in months}

# ── Regime ──
def build_regime(monthly_closes: list) -> list[str]:
    """Build regime labels per month, matched to weeks."""
    n = len(monthly_closes)
    if n < 13: return ["unknown"] * n
    monthly_ret = [(monthly_closes[i] - monthly_closes[i-1]) / monthly_closes[i-1] * 100 for i in range(1, n)]
    momentum_6m = []
    for i in range(len(monthly_ret)):
        start = max(0, i - 5)
        momentum_6m.append(round(sum(monthly_ret[start:i+1]), 1))
    # Percentile (24-month rolling)
    def pct_rank(vals, idx, window=24):
        start = max(0, idx - window + 1)
        window_vals = vals[start:idx+1]
        if len(window_vals) < 6: return 50.0
        current = abs(vals[idx])
        below = sum(1 for v in window_vals if abs(v) <= current)
        return below / len(window_vals) * 100
    vol_ranks = [pct_rank(monthly_ret, i) for i in range(len(monthly_ret))]
    labels = []
    for i in range(len(monthly_ret)):
        if vol_ranks[i] > 80: labels.append("panic")
        elif vol_ranks[i] < 20: labels.append("sideways")
        elif momentum_6m[i] > 0: labels.append("bull")
        else: labels.append("bear")
    return labels

# ── RSI ──
def weekly_rsi(weeks: list, period: int = 14) -> list[float]:
    """Compute RSI for each week. Return list of RSI values aligned with weeks."""
    rsi = [50.0] * period
    gains, losses = [], []
    for i in range(1, period + 1):
        change = weeks[i]["close"] - weeks[i-1]["close"]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    rsi_val = 100 - (100 / (1 + avg_gain / max(avg_loss, 0.0001)))
    rsi.append(rsi_val)
    for i in range(period + 1, len(weeks)):
        change = weeks[i]["close"] - weeks[i-1]["close"]
        gain = max(change, 0)
        loss = max(-change, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rsi_val = 100 - (100 / (1 + avg_gain / max(avg_loss, 0.0001)))
        rsi.append(rsi_val)
    return rsi

# ── Core Moon Reversal Engine (parameterized) ──
def run_strategy(weeks, months, month_map, trail_act, trail_dist, conf_weeks=2,
                 skip_regimes=None, rsi_values=None, rsi_max=None, vol_confirm=False,
                 regime_labels=None, weekly_indices_to_month=None):
    """Generic Moon Reversal runner. Returns list of SELL trades.
    rsi_values: list of RSI values per week
    rsi_max: skip entry if RSI > this (None = no RSI filter)
    vol_confirm: skip entry if weekly volume < 4-week avg
    """
    trades = []
    in_pos, entry_price, highest, trail_active = False, 0, 0, False
    red_count, entry_allowed = 0, False
    last_month = None

    for wi, w in enumerate(weeks):
        ym = w["date"][:7]
        # Monthly feed
        if last_month and ym != last_month and last_month in month_map:
            m = month_map[last_month]
            if m["close"] < m["open"]:
                entry_allowed = True
            else:
                entry_allowed = False
        last_month = ym

        # Regime gate
        regime = "unknown"
        if regime_labels is not None and weekly_indices_to_month is not None:
            mi = weekly_indices_to_month.get(wi, -1)
            if 0 <= mi < len(regime_labels):
                regime = regime_labels[mi]
        if skip_regimes and regime in skip_regimes:
            continue

        # RSI filter (entry only)
        if not in_pos and rsi_max is not None and rsi_values is not None and wi < len(rsi_values):
            if rsi_values[wi] > rsi_max:  # overbought → skip
                continue

        # Volume filter (entry only)
        if not in_pos and vol_confirm and wi >= 4:
            avg_vol = sum(weeks[j]["volume"] for j in range(wi-4, wi)) / 4
            if weeks[wi]["volume"] < avg_vol:
                continue

        if not in_pos:
            if entry_allowed and w["close"] > w["open"]:
                in_pos = True
                entry_price = w["close"]
                highest = w["close"]
                trail_active = False
                red_count = 0
                entry_allowed = False
            elif w["close"] > w["open"]:
                entry_allowed = False
        else:
            if w["high"] > highest:
                highest = w["high"]
            if not trail_active:
                profit_pct = (highest - entry_price) / entry_price * 100
                if profit_pct >= trail_act:
                    trail_active = True
            exit_reason, exit_price = None, None
            if w["close"] < w["open"]:
                red_count += 1
                if red_count >= conf_weeks:
                    exit_reason = f"连续{conf_weeks}红周"
                    exit_price = w["close"]
            else:
                red_count = 0
            if trail_active and exit_reason is None:
                trail_price = highest * (1 - trail_dist / 100)
                if w["low"] <= trail_price:
                    exit_reason = f"追踪止损({highest:.0f}→{trail_price:.0f})"
                    exit_price = trail_price
            if exit_reason:
                pnl = (exit_price - entry_price) / entry_price * 100
                trades.append({"action": "SELL", "date": w["date"], "entry": round(entry_price, 0),
                               "exit": round(exit_price, 0), "pnl_pct": round(pnl, 2),
                               "reason": exit_reason, "regime": regime})
                in_pos, entry_price, highest, trail_active = False, 0, 0, False
                red_count, entry_allowed = 0, False
    return trades

# ── Metrics ──
def compute_metrics(trades: list) -> dict:
    if not trades: return {"trades": 0, "return_pct": 0, "win_rate": 0, "sharpe": 0, "max_dd": 0, "avg_pnl": 0}
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    wr = len(wins) / len(trades) * 100
    total_return = sum(t["pnl_pct"] for t in trades)
    avg_pnl = total_return / len(trades)
    # Sharpe (simple — assumes risk-free = 0)
    pnls = [t["pnl_pct"] for t in trades]
    mean = sum(pnls) / len(pnls)
    if len(pnls) > 1:
        var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
        std = var ** 0.5
        sharpe = mean / max(std, 0.01)
    else:
        sharpe = 0
    # Max DD on cumulative
    cum = 0
    peak = 0
    max_dd = 0
    for p in pnls:
        cum += p
        if cum > peak: peak = cum
        dd = peak - cum
        if dd > max_dd: max_dd = dd
    return {"trades": len(trades), "return_pct": round(total_return, 1), "win_rate": round(wr, 1),
            "sharpe": round(sharpe, 2), "max_dd": round(max_dd, 1), "avg_pnl": round(avg_pnl, 2)}

# ── Main ──
def main():
    print("Fetching BTC data...")
    months, weeks, month_map = fetch_data_8yr("BTCUSDT")
    monthly_closes = [m["close"] for m in months]
    regime_labels = build_regime(monthly_closes)  # length = len(months)-1
    rsi = weekly_rsi(weeks)

    # Map week index → month index for regime lookups
    weekly_to_month = {}
    for wi, w in enumerate(weeks):
        ym = w["date"][:7]
        for mi, m in enumerate(months):
            if m["date"] == ym and mi > 0:
                weekly_to_month[wi] = mi - 1  # regime label index
                break

    print(f"Data: {len(months)} months, {len(weeks)} weeks, {len(regime_labels)} regime labels")

    # Fee deduction: 0.3% per round trip (0.1% fee + 0.2% slippage)
    def deduct_fees(trades):
        for t in trades:
            t["pnl_pct"] = round(t["pnl_pct"] - 0.3, 2)
        return trades

    # ── Baseline ──
    base = run_strategy(weeks, months, month_map, trail_act=5.0, trail_dist=4.0, conf_weeks=2,
                        regime_labels=regime_labels, weekly_indices_to_month=weekly_to_month)
    base = deduct_fees(base)
    base_m = compute_metrics(base)

    # ── A: Regime-gated ──
    # Per regime trailing params: bull=tight, bear=std, panic=wide, sideways=skip
    # Run one unified pass with regime-conditional params
    def run_regime_gated():
        trades = []
        in_pos, entry_price, highest, trail_active = False, 0, 0, False
        red_count, entry_allowed = 0, False
        last_month = None
        for wi, w in enumerate(weeks):
            ym = w["date"][:7]
            if last_month and ym != last_month and last_month in month_map:
                m = month_map[last_month]
                entry_allowed = (m["close"] < m["open"])
            last_month = ym
            mi = weekly_to_month.get(wi, -1)
            regime = regime_labels[mi] if 0 <= mi < len(regime_labels) else "unknown"
            if regime == "sideways":
                continue  # no trades in sideways
            # Param selection
            if regime == "bull":
                ta, td = 3.0, 2.0
            elif regime == "panic":
                ta, td = 8.0, 6.0
            else:
                ta, td = 5.0, 4.0

            if not in_pos:
                if entry_allowed and w["close"] > w["open"]:
                    in_pos, entry_price, highest = True, w["close"], w["close"]
                    trail_active, red_count, entry_allowed = False, 0, False
                elif w["close"] > w["open"]:
                    entry_allowed = False
            else:
                if w["high"] > highest: highest = w["high"]
                if not trail_active and (highest - entry_price) / entry_price * 100 >= ta:
                    trail_active = True
                exit_reason, exit_price = None, None
                if w["close"] < w["open"]:
                    red_count += 1
                    if red_count >= 2:
                        exit_reason = "连续2红周"; exit_price = w["close"]
                else:
                    red_count = 0
                if trail_active and exit_reason is None:
                    tp = highest * (1 - td / 100)
                    if w["low"] <= tp:
                        exit_reason = f"追踪止损({highest:.0f}→{tp:.0f})"; exit_price = tp
                if exit_reason:
                    pnl = (exit_price - entry_price) / entry_price * 100
                    trades.append({"pnl_pct": round(pnl, 2), "regime": regime})
                    in_pos, entry_price, highest, trail_active = False, 0, 0, False
                    red_count, entry_allowed = 0, False
        return trades

    a_trades = run_regime_gated()
    a_trades = deduct_fees(a_trades)
    a_m = compute_metrics(a_trades)

    # ── B: Dynamic params (same mechanism as A but no regime-skip) ──
    def run_dynamic_params():
        trades = []
        in_pos, entry_price, highest, trail_active = False, 0, 0, False
        red_count, entry_allowed = 0, False
        last_month = None
        for wi, w in enumerate(weeks):
            ym = w["date"][:7]
            if last_month and ym != last_month and last_month in month_map:
                m = month_map[last_month]
                entry_allowed = (m["close"] < m["open"])
            last_month = ym
            mi = weekly_to_month.get(wi, -1)
            regime = regime_labels[mi] if 0 <= mi < len(regime_labels) else "unknown"
            if regime == "bull": ta, td = 3.0, 2.0
            elif regime == "panic": ta, td = 8.0, 6.0
            elif regime == "sideways": ta, td = 7.0, 5.0  # wider, let it run less
            else: ta, td = 5.0, 4.0

            if not in_pos:
                if entry_allowed and w["close"] > w["open"]:
                    in_pos, entry_price, highest = True, w["close"], w["close"]
                    trail_active, red_count, entry_allowed = False, 0, False
                elif w["close"] > w["open"]:
                    entry_allowed = False
            else:
                if w["high"] > highest: highest = w["high"]
                if not trail_active and (highest - entry_price) / entry_price * 100 >= ta:
                    trail_active = True
                exit_reason, exit_price = None, None
                if w["close"] < w["open"]:
                    red_count += 1
                    if red_count >= 2: exit_reason = "连续2红周"; exit_price = w["close"]
                else: red_count = 0
                if trail_active and exit_reason is None:
                    tp = highest * (1 - td / 100)
                    if w["low"] <= tp: exit_reason = f"追踪"; exit_price = tp
                if exit_reason:
                    pnl = (exit_price - entry_price) / entry_price * 100
                    trades.append({"pnl_pct": round(pnl, 2), "regime": regime})
                    in_pos, entry_price, highest, trail_active = False, 0, 0, False
                    red_count, entry_allowed = 0, False
        return trades

    b_trades = run_dynamic_params()
    b_trades = deduct_fees(b_trades)
    b_m = compute_metrics(b_trades)

    # ── C: Signal stacking (+RSI + Volume) ──
    c_trades = run_strategy(weeks, months, month_map, trail_act=5.0, trail_dist=4.0, conf_weeks=2,
                            rsi_values=rsi, rsi_max=70, vol_confirm=True,
                            regime_labels=regime_labels, weekly_indices_to_month=weekly_to_month)
    c_trades = deduct_fees(c_trades)
    c_m = compute_metrics(c_trades)

    # ── D: Walk-forward selector ──
    # For each month starting month 25, look back 24 months, pick best of A/B/C/Baseline,
    # execute that variant for the current month. Accumulate trades.
    d_trades = []
    for test_mi in range(24, len(monthly_closes) - 1):
        train_closes = monthly_closes[:test_mi]
        train_regime = build_regime(train_closes)
        # Scope weeks to training period
        train_months = months[:test_mi + 1]
        train_month_map = {m["date"]: m for m in train_months}
        train_weeks = [w for w in weeks if w["date"][:7] in train_month_map]
        train_weekly_to_month = {}
        for wi, w in enumerate(train_weeks):
            ym = w["date"][:7]
            for mi, m in enumerate(train_months):
                if m["date"] == ym and mi > 0:
                    train_weekly_to_month[wi] = mi - 1
                    break

        # Compute train_rsi
        train_rsi = weekly_rsi(train_weeks) if len(train_weeks) > 14 else [50] * len(train_weeks)
        # Score each variant on training window
        scores = {}
        # Baseline
        bt = run_strategy(train_weeks, train_months, train_month_map, 5.0, 4.0, 2,
                          regime_labels=train_regime, weekly_indices_to_month=train_weekly_to_month)
        scores["base"] = sum(t["pnl_pct"] for t in bt) if bt else 0
        # A
        at = run_strategy(train_weeks, train_months, train_month_map, 5.0, 4.0, 2,
                          skip_regimes={"sideways"}, regime_labels=train_regime,
                          weekly_indices_to_month=train_weekly_to_month)
        scores["A"] = sum(t["pnl_pct"] for t in at) if at else 0
        # C
        ct = run_strategy(train_weeks, train_months, train_month_map, 5.0, 4.0, 2,
                          rsi_values=train_rsi, rsi_max=70, vol_confirm=True, regime_labels=train_regime,
                          weekly_indices_to_month=train_weekly_to_month)
        scores["C"] = sum(t["pnl_pct"] for t in ct) if ct else 0

        best = max(scores, key=scores.get)
        # Execute best on test month only
        test_month = months[test_mi]
        test_month_map = {test_month["date"]: test_month}
        test_weeks = [w for w in weeks if w["date"][:7] == test_month["date"]]
        test_rsi = [50] * len(test_weeks)  # simplified: use neutral RSI for walk-forward

        test_regime_label = regime_labels[test_mi - 1] if test_mi - 1 < len(regime_labels) else "unknown"
        tw2m = {i: 0 for i in range(len(test_weeks))}  # all map to month index 0

        if best == "base":
            tt = run_strategy(test_weeks, test_month_map, test_month_map, 5.0, 4.0, 2,
                              regime_labels=[test_regime_label], weekly_indices_to_month=tw2m)
        elif best == "A":
            tt = run_strategy(test_weeks, test_month_map, test_month_map, 5.0, 4.0, 2,
                              skip_regimes={"sideways"}, regime_labels=[test_regime_label],
                              weekly_indices_to_month=tw2m)
        else:
            tt = run_strategy(test_weeks, test_month_map, test_month_map, 5.0, 4.0, 2,
                              rsi_values=test_rsi, rsi_max=70, vol_confirm=True,
                              regime_labels=[test_regime_label],
                              weekly_indices_to_month=tw2m)
        d_trades.extend(tt)

    d_m = compute_metrics(d_trades)

    # ── OUTPUT ──
    print("\n" + "=" * 72)
    print("  8-Year BTC Backtest — 4 Strategy Variants vs Baseline")
    print("=" * 72)
    print(f"  {'Variant':<30} {'Trades':>6} {'Return':>9} {'WR':>6} {'Sharpe':>7} {'MaxDD':>7} {'AvgPnL':>7}")
    print("-" * 72)
    for name, m, desc in [
        ("Baseline (Moon Reversal)", base_m, "trail +5%/-4%, 2 red weeks"),
        ("A: Regime-gated", a_m, "skip sideways, tighten bull, widen panic"),
        ("B: Dynamic params", b_m, "trail adjusted per regime (all trade)"),
        ("C: Signal stacking", c_m, "+RSI<70 + volume >avg4wk"),
        ("D: Walk-forward selector", d_m, "monthly best-of-variants (24mo lookback)"),
    ]:
        print(f"  {name:<30} {m['trades']:>6} {m['return_pct']:>+8.1f}% {m['win_rate']:>5.1f}% {m['sharpe']:>6.2f} {m['max_dd']:>6.1f}% {m['avg_pnl']:>+7.2f}%")
    print("-" * 72)
    print(f"  Description: {desc}")

    # Regime breakdown for best performer
    print("\n── Regime Breakdown (Baseline) ──")
    regime_pnls = {"bull": [], "bear": [], "sideways": [], "panic": []}
    for t in base:
        r = t.get("regime", "unknown")
        if r in regime_pnls: regime_pnls[r].append(t["pnl_pct"])
    for r in ["bull", "bear", "sideways", "panic"]:
        pnls = regime_pnls[r]
        if pnls:
            wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
            print(f"  {r:<10} {len(pnls):>3}t  WR {wr:.0f}%  avg {sum(pnls)/len(pnls):+.2f}%  total {sum(pnls):+.1f}%")
        else:
            print(f"  {r:<10}  0 trades")

if __name__ == "__main__":
    main()
