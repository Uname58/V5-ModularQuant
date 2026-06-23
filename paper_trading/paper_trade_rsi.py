#!/usr/bin/env python3
"""
RSI Rebound Module — Phase 1 Paper Trading Journal
Monitors 14 symbols. Runs every 30 min via cron. Records signals + fills.
Tracks: signal_close, next_open, live_quote, simulated_fill → Capture Ratio
Shadow: counterfactual without cooldown, without risk budget.
"""

import json, os, time, urllib.request
from datetime import datetime, timezone

# ===== CONFIG =====
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "XRPUSDT", "DOGEUSDT", "SUIUSDT", "NEARUSDT",
    "ADAUSDT", "AVAXUSDT", "LINKUSDT",
    "ENAUSDT", "AAVEUSDT", "INJUSDT",
]
TP = 1.5
SL = -10.0
RSI_THRESHOLD = 20
MA99_DIST = -8   # % below MA99
DROP_24H = -5    # % drop in 24h
DATA_DIR = os.path.expanduser("~/.hermes/data/rsi_paper/")
JOURNAL = os.path.join(DATA_DIR, "journal.jsonl")
os.makedirs(DATA_DIR, exist_ok=True)

# ===== Fetch helpers =====
def fetch_klines(symbol, limit=300):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1h&limit={limit}"
    try:
        data = json.loads(urllib.request.urlopen(url, timeout=10).read())
        return data
    except Exception as e:
        return None

def fetch_current_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        return float(json.loads(urllib.request.urlopen(url, timeout=5).read())['price'])
    except Exception as e:
        return None

def sma(arr, idx, p):
    if idx < p-1: return None
    return sum(arr[idx-p+1:idx+1]) / p

def rsi(arr, idx, period=14):
    if idx < period: return None
    gains = losses = 0
    for i in range(idx-period, idx):
        d = arr[i+1] - arr[i]; gains += max(d, 0); losses += max(-d, 0)
    return 100 - 100/(1 + gains/losses) if losses else 100

def load_state(symbol):
    path = os.path.join(DATA_DIR, f"{symbol}_state.json")
    if os.path.exists(path):
        with open(path) as f: return json.load(f)
    return {}

def save_state(symbol, state):
    path = os.path.join(DATA_DIR, f"{symbol}_state.json")
    with open(path, 'w') as f: json.dump(state, f)

# ===== Main =====
now = datetime.now(timezone.utc)
timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
cur_hour = now.hour + now.timetuple().tm_yday * 24
cur_day = now.timetuple().tm_yday
cur_week = now.isocalendar()[1]
output_lines = []

for sym in SYMBOLS:
    kl = fetch_klines(sym, 300)
    if not kl or len(kl) < 100:
        continue
    live_price = fetch_current_price(sym)
    if not live_price:
        continue

    closes = [float(k[4]) for k in kl]
    highs  = [float(k[2]) for k in kl]
    n = len(kl)
    i = n - 1

    # Signal check
    r = rsi(closes, i, 14)
    ma99 = sma(closes, i, 99)
    signal_active = False
    signal_detail = {}

    if r is not None and ma99 is not None and ma99 > 0:
        dist = (closes[i] - ma99) / ma99 * 100
        drop_24h = (max(highs[i-24:i+1]) - closes[i]) / max(highs[i-24:i+1]) * 100 if i >= 24 else 0
        signal_active = (r <= RSI_THRESHOLD and dist <= MA99_DIST and drop_24h >= abs(DROP_24H))
        signal_detail = {
            'rsi': round(r, 1),
            'dist_ma99': round(dist, 1),
            'drop_24h': round(drop_24h, 1),
            'close': closes[i],
            'ma99': round(ma99, 2),
        }

    # State
    st = load_state(sym)
    in_trade = st.get('in_trade', False)
    entry_price = st.get('entry_price', 0)
    entry_signal_close = st.get('entry_signal_close', 0)
    entry_next_open = st.get('entry_next_open', 0)
    entry_time = st.get('entry_time', '')
    consecutive_losses = st.get('consecutive_losses', 0)
    loss_timestamps = st.get('loss_timestamps', [])
    cooldown_until = st.get('cooldown_until', 0)
    daily_pnl = st.get('daily_pnl', 0.0)
    weekly_pnl = st.get('weekly_pnl', 0.0)
    last_day = st.get('last_day', -1)
    last_week = st.get('last_week', -1)

    # Reset daily/weekly
    if cur_day != last_day and last_day != -1: daily_pnl = 0.0
    if cur_week != last_week and last_week != -1: weekly_pnl = 0.0
    last_day = cur_day; last_week = cur_week

    # ---- Exit check ----
    if in_trade:
        unrealized = (live_price - entry_price) / entry_price * 100
        exit_reason = None
        exit_price = 0

        if live_price <= entry_price * (1 + SL/100):
            exit_reason = "SL"
            exit_price = entry_price * (1 + SL/100)
        elif live_price >= entry_price * (1 + TP/100):
            exit_reason = "TP"
            exit_price = entry_price * (1 + TP/100)

        if exit_reason:
            pnl = TP if exit_reason == "TP" else SL

            entry = {
                'symbol': sym,
                'entry_time': entry_time,
                'signal_close': round(entry_signal_close, 4),
                'next_open': round(entry_next_open, 4),
                'exit_time': timestamp,
                'exit_reason': exit_reason,
                'pnl_pct': round(pnl, 2),
                'entry_price': round(entry_price, 4),
                'exit_price': round(exit_price, 4),
            }
            with open(JOURNAL, 'a') as f: f.write(json.dumps(entry) + '\n')

            output_lines.append(f"[{timestamp}] {sym} EXIT {exit_reason} | PnL={pnl:+.2f}% | entry=${entry_price:.4f} exit=${exit_price:.4f}")

            daily_pnl += pnl
            weekly_pnl += pnl

            if pnl < 0:
                consecutive_losses += 1
                loss_timestamps.append(cur_hour)
                if consecutive_losses >= 3: cooldown_until = cur_hour + 72
                elif consecutive_losses >= 2: cooldown_until = cur_hour + 24
                else: cooldown_until = cur_hour + 6
            else:
                consecutive_losses = 0

            loss_timestamps = [h for h in loss_timestamps if cur_hour - h <= 168]
            if len(loss_timestamps) >= 3:
                cooldown_until = max(cooldown_until, cur_hour + 72)

            in_trade = False
            entry_price = 0
            entry_signal_close = 0
            entry_next_open = 0

    # ---- Entry check ----
    DAILY_RISK = 0.03
    daily_ok = abs(daily_pnl) < DAILY_RISK * 100
    not_cooldown = cur_hour >= cooldown_until

    if signal_active and not in_trade:
        status = []
        if not daily_ok: status.append("BLOCKED:daily_risk")
        if not not_cooldown: status.append(f"BLOCKED:cooldown({(cooldown_until-cur_hour)}h left)")

        if daily_ok and not_cooldown:
            in_trade = True
            entry_signal_close = closes[i]
            entry_next_open = live_price
            entry_price = live_price
            entry_time = timestamp

            r_val = signal_detail['rsi']
            if r_val < 15: size_mult = 1.5
            elif r_val < 18: size_mult = 1.2
            else: size_mult = 1.0

            output_lines.append(f"[{timestamp}] {sym} ENTRY | RSI={signal_detail['rsi']} dist={signal_detail['dist_ma99']}% drop24h={signal_detail['drop_24h']}% | price=${entry_price:.4f} size=x{size_mult:.1f}")
        else:
            output_lines.append(f"[{timestamp}] {sym} SIGNAL SKIPPED | RSI={signal_detail['rsi']} {' '.join(status)}")

    # ---- Counterfactual ----
    if signal_active and not in_trade and not not_cooldown:
        output_lines.append(f"  [shadow:cooldown_off] {sym} would have entered at ${live_price:.4f}")

    # Save state
    save_state(sym, {
        'in_trade': in_trade,
        'entry_price': entry_price,
        'entry_signal_close': entry_signal_close,
        'entry_next_open': entry_next_open,
        'entry_time': entry_time,
        'consecutive_losses': consecutive_losses,
        'loss_timestamps': loss_timestamps,
        'cooldown_until': cooldown_until,
        'daily_pnl': daily_pnl,
        'weekly_pnl': weekly_pnl,
        'last_day': last_day,
        'last_week': last_week,
    })

# ===== Output (silent unless event) =====
if output_lines:
    for line in output_lines:
        print(line)
