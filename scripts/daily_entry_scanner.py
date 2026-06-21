#!/usr/bin/env python3
"""
每日入场扫描 — 四灯 + K线形态确认 + ATR SL/TP + 仓位检查
做多形态(入场确认): 启明星/看涨吞没/刺透/锤形线
做空形态(离场预警): 黄昏星/看跌吞没/乌云盖顶/流星线
用法: python3 ~/.hermes/scripts/daily_entry_scanner.py
输出: 有候选+有空位 → 推送 | 否则 → 静默
"""
import ccxt, os, sys, time
from pathlib import Path

# ── 配置 ──
TIMEFRAME = '1h'
CANDLE_LIMIT = 300  # 1h × 300 ≈ 12.5 days (was 4h × 150 = 25d)
MA_SHORT, MA_MID, MA_LONG = 7, 25, 99
RSI_PERIOD = 14
MIN_VOLUME_USDT = 1_000_000
MAX_POSITIONS = 2

# ATR 退出参数
SL_MULT = 2.0
TP_MULT = 3.0

# 标准档
NORMAL = {'deviation': 0.15, 'vol': 1.1, 'rsi_hi': 75, 'rsi_lo': 30}

# ── K线形态检测 ──
def body(o, c):
    """实体大小 (正数)"""
    return abs(c - o)

def upper_shadow(h, o, c):
    return h - max(o, c)

def lower_shadow(o, c, l):
    return min(o, c) - l

def is_bullish(o, c):
    return c > o

def is_bearish(o, c):
    return c < o

def is_doji(o, c, h, l):
    """十字星/小实体: 实体 ≤ 整根K线的10%"""
    rng = h - l
    if rng == 0:
        return False
    return body(o, c) / rng <= 0.1

# ── 做多形态 (入场确认) ──
def detect_bullish_patterns(opens, highs, lows, closes, idx):
    """
    检测最近3根K线(含idx)是否有做多反转形态。
    返回匹配到的形态名列表。
    """
    if idx < 0: idx = len(opens) + idx
    patterns = []
    if idx < 2:
        return patterns

    o = opens; h = highs; l = lows; c = closes

    # ── 启明星 (Morning Star): [-2]阴 + [-1]小实体 + [0]阳 收盘>[-2]实体中点
    if (is_bearish(o[idx-2], c[idx-2]) and
        is_doji(o[idx-1], c[idx-1], h[idx-1], l[idx-1]) and
        is_bullish(o[idx], c[idx]) and
        c[idx] > (o[idx-2] + c[idx-2]) / 2):
        patterns.append('启明星')

    # ── 看涨吞没 (Bullish Engulfing): [-1]阴 + [0]阳, [0]实体完全吞没[-1]实体
    if (is_bearish(o[idx-1], c[idx-1]) and
        is_bullish(o[idx], c[idx]) and
        o[idx] <= c[idx-1] and c[idx] >= o[idx-1]):
        patterns.append('看涨吞没')

    # ── 刺透 (Piercing Line): [-1]阴 + [0]阳, 开盘<前低, 收盘>前阴实体中点
    if (is_bearish(o[idx-1], c[idx-1]) and
        is_bullish(o[idx], c[idx]) and
        o[idx] < l[idx-1] and
        c[idx] > (o[idx-1] + c[idx-1]) / 2):
        patterns.append('刺透')

    # ── 锤形线 (Hammer): 单根, 下影≥2×实体, 实体在底部1/3, 上影短
    rng = h[idx] - l[idx]
    if rng > 0:
        bd = body(o[idx], c[idx])
        ls = lower_shadow(o[idx], c[idx], l[idx])
        us = upper_shadow(h[idx], o[idx], c[idx])
        # 下影 ≥ 2×实体 且 实体>0 且 上影 ≤ 0.3×下影 (小上影)
        if bd > 0 and ls >= bd * 2 and us <= ls * 0.3:
            # 实体在底部1/3: close和open都在range的下1/3
            body_center = (o[idx] + c[idx]) / 2
            if body_center <= l[idx] + rng / 3:
                patterns.append('锤形线')

    return patterns


# ── 做空形态 (离场预警) ──
def detect_bearish_pattern(opens, highs, lows, closes, idx):
    """
    检测idx位置是否有做空反转形态。
    返回形态名或None。
    """
    if idx < 0: idx = len(opens) + idx
    if idx < 2:
        return None

    o = opens; h = highs; l = lows; c = closes

    # ── 黄昏星 (Evening Star): [-2]阳 + [-1]小实体 + [0]阴 收盘<[-2]实体中点
    if (is_bullish(o[idx-2], c[idx-2]) and
        is_doji(o[idx-1], c[idx-1], h[idx-1], l[idx-1]) and
        is_bearish(o[idx], c[idx]) and
        c[idx] < (o[idx-2] + c[idx-2]) / 2):
        return '黄昏星'

    # ── 看跌吞没 (Bearish Engulfing): [-1]阳 + [0]阴, [0]实体完全吞没[-1]实体
    if (is_bullish(o[idx-1], c[idx-1]) and
        is_bearish(o[idx], c[idx]) and
        o[idx] >= c[idx-1] and c[idx] <= o[idx-1]):
        return '看跌吞没'

    # ── 乌云盖顶 (Dark Cloud Cover): [-1]阳 + [0]阴, 开>前高, 收<前阳实体中点
    if (is_bullish(o[idx-1], c[idx-1]) and
        is_bearish(o[idx], c[idx]) and
        o[idx] > h[idx-1] and
        c[idx] < (o[idx-1] + c[idx-1]) / 2):
        return '乌云盖顶'

    # ── 流星线 (Shooting Star): 单根, 上影≥2×实体, 实体在顶部1/3, 下影短
    rng = h[idx] - l[idx]
    if rng > 0:
        bd = body(o[idx], c[idx])
        us = upper_shadow(h[idx], o[idx], c[idx])
        ls = lower_shadow(o[idx], c[idx], l[idx])
        if bd > 0 and us >= bd * 2 and ls <= us * 0.3:
            body_center = (o[idx] + c[idx]) / 2
            if body_center >= l[idx] + rng * 2 / 3:
                return '流星线'

    return None


# ── 指标 ──
def sma_at(data, idx, period):
    if idx < 0: idx = len(data) + idx  # normalize negative index
    if idx < period - 1: return None
    return sum(data[idx-period+1:idx+1]) / period

def rsi_at(closes, idx, period=14):
    if idx < 0: idx = len(closes) + idx
    if idx < period: return None
    gains = [max(closes[i+1]-closes[i], 0) for i in range(idx-period, idx)]
    losses = [max(closes[i]-closes[i+1], 0) for i in range(idx-period, idx)]
    avg_g = sum(gains)/period
    avg_l = sum(losses)/period
    return 100 - (100/(1+avg_g/avg_l)) if avg_l>0 else 100

def atr_at(highs, lows, closes, idx, period=14):
    if idx < 0: idx = len(closes) + idx
    if idx < period: return None
    tr = []
    for i in range(idx-period+1, idx+1):
        tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    return sum(tr)/period

def four_lights_at(closes, volumes, idx, tier):
    """Check 4 lights at bar index, returns (count, details dict or None)"""
    if idx < 0: idx = len(closes) + idx
    if idx < MA_LONG: return 0, None

    ma7 = sma_at(closes, idx, MA_SHORT)
    ma25 = sma_at(closes, idx, MA_MID)
    ma99 = sma_at(closes, idx, MA_LONG)
    rsi = rsi_at(closes, idx, RSI_PERIOD)

    if None in (ma7, ma25, ma99, rsi):
        return 0, None

    lights = 0
    # 灯1: 趋势
    if ma7 > ma25 > ma99:
        lights += 1
    # 灯2: 位置
    deviation = abs(closes[idx] - ma25) / ma25
    if deviation <= tier['deviation'] and closes[idx] > ma25:
        lights += 1
    # 灯3: 量 — 用前一根已完成K线, 避免当前未完成K线量=0的误报
    prev_vol = 0; prev_avg_vol = 0
    if idx >= 21:
        prev_vol = volumes[idx-1]
        prev_avg_vol = sum(volumes[idx-21:idx-1])/20
        if prev_avg_vol > 0 and prev_vol >= prev_avg_vol * tier['vol']:
            lights += 1
    # 灯4: RSI
    if tier['rsi_lo'] <= rsi <= tier['rsi_hi']:
        lights += 1

    return lights, {
        'price': closes[idx], 'ma7': ma7, 'ma25': ma25, 'ma99': ma99,
        'rsi': rsi, 'deviation': deviation,
        'vol_ratio': (volumes[idx-1]/prev_avg_vol if (idx>=21 and prev_avg_vol>0) else 0)
    }


# ── 主逻辑 ──
def main():
    # Init exchange
    env_file = Path.home() / 'projects/AI_trading_system_V3/.env'
    if env_file.exists():
        for line in open(env_file).read().strip().split('\n'):
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip()

    exchange = ccxt.binance({
        'apiKey': os.getenv('BINANCE_API_KEY', ''),
        'secret': os.getenv('BINANCE_SECRET_KEY', ''),
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'},
        'adjustForTimeDifference': True,
    })

    # Fix WSL clock drift — use raw HTTP to get server time BEFORE any ccxt API call
    import urllib.request, json
    for attempt in range(3):
        try:
            local_before = int(time.time() * 1000)
            req = urllib.request.urlopen('https://api.binance.com/api/v3/time', timeout=5)
            server_time = json.loads(req.read())['serverTime']
            local_after = int(time.time() * 1000)
            local_mid = (local_before + local_after) // 2
            offset = server_time - local_mid
            print(f"  [time sync] offset={offset}ms", file=sys.stderr)
            _orig_ms = exchange.milliseconds
            exchange.milliseconds = lambda: _orig_ms() + offset
            break
        except Exception as e:
            print(f"  [time sync] attempt {attempt+1} failed: {e}", file=sys.stderr)
            time.sleep(0.5)

    # ── 0. Watchlist ──
    watchlist = []
    wl_file = Path.home() / '.hermes/data/watchlist.json'
    if wl_file.exists():
        try: watchlist = json.loads(open(wl_file).read())
        except: pass

    # ── 1. Check position slots ──
    slots_used = 0
    positions = []
    held_assets = set()  # track which coins we already hold
    try:
        exchange.load_markets()
        balance = exchange.fetch_balance()
        for asset, info in balance['total'].items():
            if info > 0 and asset != 'USDT':
                try:
                    ticker = exchange.fetch_ticker(f'{asset}/USDT')
                    value = info * ticker['last']
                    if value > 5:
                        slots_used += 1
                        positions.append(f"{asset} ({info:.4f} ≈ ${value:.0f})")
                        held_assets.add(asset)  # mark as held
                except:
                    pass
    except Exception as e:
        print(f"⚠️ 仓位检查失败: {e}")
        return 1

    slots_open = MAX_POSITIONS - slots_used
    if slots_open <= 0:
        return 0

    # ── 2. Scan all coins ──
    symbols = [s for s in exchange.symbols
               if s.endswith('/USDT') and ':USDT' not in s
               and 'UP/' not in s and 'DOWN/' not in s
               and 'BULL/' not in s and 'BEAR/' not in s
               # exclude delisted/suspended pairs
               and exchange.markets[s].get('active', False)
               and exchange.markets[s].get('info', {}).get('status', '') == 'TRADING']

    candidates = []

    for sym in symbols:
        # Skip coins we already hold — don't double-dip
        base = sym.replace('/USDT', '')
        if base in held_assets:
            continue
        try:
            ohlcv = exchange.fetch_ohlcv(sym, TIMEFRAME, limit=CANDLE_LIMIT)
            if len(ohlcv) < MA_LONG + RSI_PERIOD:
                continue

            opens  = [c[1] for c in ohlcv]
            highs  = [c[2] for c in ohlcv]
            lows   = [c[3] for c in ohlcv]
            closes = [c[4] for c in ohlcv]
            volumes = [c[5] for c in ohlcv]

            # Check 24h volume
            ticker = exchange.fetch_ticker(sym)
            usdt_vol = ticker.get('quoteVolume', 0) or 0
            if usdt_vol < MIN_VOLUME_USDT:
                continue

            # ── 四灯 (当前) ──
            curr_lights, curr_detail = four_lights_at(closes, volumes, -1, NORMAL)
            if curr_lights != 4:
                continue

            # ── 15m 入场确认 (加分项, 不阻断) ──
            ohlcv_15m = exchange.fetch_ohlcv(sym, '15m', limit=50)
            o15 = [c[1] for c in ohlcv_15m]; h15 = [c[2] for c in ohlcv_15m]
            l15 = [c[3] for c in ohlcv_15m]; c15 = [c[4] for c in ohlcv_15m]
            v15 = [c[5] for c in ohlcv_15m]
            vol_15m_ratio = v15[-1] / (sum(v15[-6:-1])/5) if sum(v15[-6:-1])>0 else 0
            vol_surge = vol_15m_ratio >= 1.5

            # Check 15m bullish patterns
            bull_pats_15m = detect_bullish_patterns(o15, h15, l15, c15, -1)
            if not bull_pats_15m:
                bull_pats_15m = detect_bullish_patterns(o15, h15, l15, c15, -2)
            has_15m_pat = len(bull_pats_15m) > 0

            # Confidence tier (affects position size, not entry)
            if has_15m_pat and vol_surge:
                confidence = 'HIGH'
                pos_label = '满仓'
            elif has_15m_pat or vol_surge:
                confidence = 'STD'
                pos_label = '标准仓'
            else:
                confidence = 'LOW'
                pos_label = '半仓'

            # ── 做空形态预警 (离场信号, 收紧止损) ──
            bear_warning = detect_bearish_pattern(opens, highs, lows, closes, -1)
            if not bear_warning:
                bear_warning = detect_bearish_pattern(opens, highs, lows, closes, -2)

            # ── ATR SL/TP ──
            atr_val = atr_at(highs, lows, closes, -1, 14)
            if atr_val and atr_val > 0:
                sl_pct = SL_MULT * atr_val / curr_detail['price'] * 100
                tp_pct = TP_MULT * atr_val / curr_detail['price'] * 100
                sl_pct = max(2.0, min(20.0, sl_pct))
                tp_pct = max(4.0, min(40.0, tp_pct))
                if tp_pct <= sl_pct:
                    tp_pct = sl_pct * 1.5
                sl_price = curr_detail['price'] * (1 - sl_pct/100)
                tp_price = curr_detail['price'] * (1 + tp_pct/100)
            else:
                sl_pct, tp_pct, sl_price, tp_price = 2.0, 4.0, 0, 0

            # 如果有做空形态预警，收紧止损
            if bear_warning:
                sl_pct = max(1.5, sl_pct * 0.7)  # 止损收窄30%
                sl_price = curr_detail['price'] * (1 - sl_pct/100)

            candidates.append({
                'symbol': sym,
                'price': curr_detail['price'],
                'rsi': curr_detail['rsi'],
                'deviation': curr_detail['deviation']*100,
                'vol_ratio': curr_detail['vol_ratio'],
                'usdt_vol': usdt_vol,
                'confidence': confidence,
                'pos_label': pos_label,
                'bull_pats': bull_pats_15m,
                'vol_15m': vol_15m_ratio,
                'bear_warning': bear_warning,
                'sl_pct': sl_pct, 'tp_pct': tp_pct,
                'sl_price': sl_price, 'tp_price': tp_price,
                'atr_pct': atr_val/curr_detail['price']*100 if atr_val else 0,
                'change_24h': ticker.get('percentage', 0) or 0,
            })
        except:
            continue

    # ── 3. Fetch Fear & Greed ──
    fg_value = None
    try:
        fg_req = urllib.request.urlopen('https://api.alternative.me/fng/?limit=1', timeout=5)
        fg_data = json.loads(fg_req.read())
        fg_value = int(fg_data['data'][0]['value'])
    except Exception as e:
        print(f"  [fg] fetch failed: {e}", file=sys.stderr)

    # ── 4. Quality filter & output ──
    # Gate: skip LOW confidence + sub-$10M volume + stablecoins (ATR<0.1%)
    QUALITY_VOL = 10_000_000
    MIN_ATR = 0.1  # % — filter stablecoins / dead tokens
    good = [c for c in candidates
            if c['confidence'] != 'LOW'
            and c['usdt_vol'] >= QUALITY_VOL
            and c['atr_pct'] >= MIN_ATR]
    if not good:
        return 0

    # ── 5. F&G Gate: Extreme Fear → blue-chip only (≥$100M daily vol) ──
    FNG_THRESHOLD = 30
    BLUECHIP_VOL = 100_000_000
    if fg_value is not None and fg_value < FNG_THRESHOLD:
        before = len(good)
        good = [c for c in good if c['usdt_vol'] >= BLUECHIP_VOL]
        dropped = before - len(good)
        if dropped > 0:
            print(f"  [fg gate] F&G={fg_value}<{FNG_THRESHOLD} → filtered {dropped} sub-bluechip, {len(good)} remain", file=sys.stderr)
    if not good:
        return 0

    good.sort(key=lambda x: x['usdt_vol'], reverse=True)

    # ── 6. Auto-trade: take top candidate, enter with market order + OCO TP/SL ──
    best = good[0]
    sym = best['symbol']
    price = best['price']
    sl_price = best['sl_price']
    tp_price = best['tp_price']

    # Position sizing: confidence-based % of USDT balance, capped at $200
    balance_usdt = 0
    try:
        b = exchange.fetch_balance()
        balance_usdt = b['total'].get('USDT', 0)
    except:
        pass

    if balance_usdt < 15:
        print(f"⛔ 余额 ${balance_usdt:.2f} 不足，跳过", file=sys.stderr)
        return 0

    pct_map = {'HIGH': 0.40, 'STD': 0.25}
    alloc_pct = pct_map.get(best['confidence'], 0.20)
    order_value = min(balance_usdt * alloc_pct, 200.0)
    order_amount = order_value / price

    try:
        exchange.load_markets()
        market = exchange.market(sym)
        order_amount = exchange.amount_to_precision(sym, order_amount)
    except:
        print(f"⛔ {sym} 市场数据获取失败", file=sys.stderr)
        return 0

    # ── Market buy ──
    try:
        buy = exchange.create_market_buy_order(sym, order_amount)
        filled_price = float(buy['price'] or price)
        filled_qty = float(buy['filled'])
        print(f"✅ 已进场: {sym} × {filled_qty} @ ${filled_price:.6f}")
        print(f"   金额: ${filled_qty * filled_price:.2f} | 余额: ${balance_usdt:.2f}")
    except Exception as e:
        print(f"❌ 进场失败: {e}")
        return 1

    # ── OCO: TP limit sell + SL stop-limit sell ──
    # ⚠️ ccxt 不支持 'OCO' order type — 必须用 private_post_order_oco
    try:
        tp_price_r = exchange.price_to_precision(sym, tp_price)
        sl_price_r = exchange.price_to_precision(sym, sl_price)
        sl_trigger = exchange.price_to_precision(sym, sl_price * 0.995)
        sell_qty = exchange.amount_to_precision(sym, filled_qty)

        oco = exchange.private_post_order_oco({
            'symbol': sym.replace('/', ''),
            'side': 'SELL',
            'quantity': str(sell_qty),
            'price': str(tp_price_r),
            'stopPrice': str(sl_trigger),
            'stopLimitPrice': str(sl_price_r),
            'stopLimitTimeInForce': 'GTC',
        })
        print(f"   OCO已设: TP ${tp_price_r} | SL ${sl_price_r} | status={oco.get('listOrderStatus','?')}")
    except Exception as e:
        print(f"   ⚠️ OCO失败: {e} | TP=${tp_price:.6f} SL=${sl_price:.6f} (请手动设)")

    # Signal summary
    stars = '⭐' if best['confidence'] == 'HIGH' else ''
    print()
    print(f"📊 信号: {sym} [{best['pos_label']}]{stars}")
    if best['bull_pats']:
        print(f"   形态: {', '.join(best['bull_pats'])}")
    print(f"   24h: {best['change_24h']:+.1f}% | RSI: {best['rsi']:.0f} | 量: ${best['usdt_vol']:,.0f}")
    print(f"   TP: {best['tp_pct']:.1f}% | SL: {best['sl_pct']:.1f}% | F&G: {fg_value}")
    if best['bear_warning']:
        print(f"   ⚠️ 离场预警: {best['bear_warning']} (SL已收紧)")

    return 0

if __name__ == '__main__':
    sys.exit(main())
