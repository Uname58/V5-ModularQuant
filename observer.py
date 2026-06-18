#!/usr/bin/env python3
"""
Moon Reversal Observer — 策略观察 & 自适应层

功能:
  1. 绩效追踪 — 记录每笔模拟交易，对比回测基准
  2. 异常检测 — 胜率偏离、回撤超限、信号频率异常
  3. 自适应 — 根据实盘表现建议调整 Kelly / 暂停车交易
"""

import json, os, datetime

JOURNAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_journal.json")

B = {'wr': 0.87, 'aw': 6.4, 'al': 12.4, 'max_dd': 13.8, 'tpy': 3.75, 'tr': 60.8, 'kelly': 0.746}

def _io(mode, data=None):
    if mode == 'r':
        if os.path.exists(JOURNAL_PATH):
            with open(JOURNAL_PATH) as f: return json.load(f)
        return {'trades': [], 'observer': [], 'status': 'active'}
    with open(JOURNAL_PATH, 'w') as f: json.dump(data, f, indent=2, ensure_ascii=False)

def record_trade(j, action, price, date, pnl=None, reason=""):
    t = {'action': action, 'price': price, 'date': date, 'reason': reason,
         'recorded_at': datetime.datetime.now().isoformat()}
    if pnl is not None: t['pnl_pct'] = pnl
    j['trades'].append(t); _io('w', j)

def analyze(j) -> dict:
    sells = [t for t in j['trades'] if t['action'] == 'SELL' and 'pnl_pct' in t]
    if len(sells) < 2:
        return {'trades': len(sells), 'status': 'insufficient_data',
                'message': f'仅{len(sells)}笔交易，需≥2笔才能分析'}

    wins, losses = [t for t in sells if t['pnl_pct'] > 0], [t for t in sells if t['pnl_pct'] <= 0]
    wr = len(wins) / len(sells)
    aw = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
    al = abs(sum(t['pnl_pct'] for t in losses) / len(losses)) if losses else 0
    total, max_loss = sum(t['pnl_pct'] for t in sells), min(t['pnl_pct'] for t in sells)
    wr_dev = (wr - B['wr']) / B['wr'] * 100

    alerts = []
    if wr_dev < -30 and len(sells) >= 4:
        alerts.append({'level': '🔴 HIGH', 'msg': f'胜率{wr*100:.0f}% 远低于基准{B["wr"]*100:.0f}%（偏差{wr_dev:.0f}%），策略可能失效'})
    elif wr_dev < -15 and len(sells) >= 4:
        alerts.append({'level': '🟡 MEDIUM', 'msg': f'胜率{wr*100:.0f}% 低于基准{B["wr"]*100:.0f}%，持续观察'})
    if abs(max_loss) > B['max_dd'] * 1.5:
        alerts.append({'level': '🔴 HIGH', 'msg': f'单笔亏损{max_loss:.1f}% 远超历史最大{B["max_dd"]}%，需检查市场结构'})
    if len(sells) >= 3 and all(t['pnl_pct'] <= 0 for t in sells[-3:]):
        alerts.append({'level': '🔴 HIGH', 'msg': '连续3笔亏损！建议暂停交易，重新评估'})

    if wr >= 0.5 and al > 0:
        ak = max(0, wr - (1 - wr) / (aw / al)) / 2
    else:
        ak = 0

    if ak <= 0: ks = "❌ Kelly为负，不建议交易"
    elif ak < B['kelly'] * 0.25: ks = f"⚠️ Kelly降至{ak*100:.0f}%，建议降仓"
    elif ak > B['kelly'] * 0.65: ks = f"📈 Kelly升至{ak*100:.0f}%，可适当加仓"
    else: ks = f"✅ Kelly稳定 {ak*100:.0f}%"

    return {'trades': len(sells), 'wins': len(wins), 'losses': len(losses),
            'win_rate': wr, 'avg_win': aw, 'avg_loss': al, 'total_pnl': total,
            'max_loss': max_loss, 'wr_deviation': wr_dev, 'alerts': alerts,
            'adaptive_kelly': ak, 'kelly_suggestion': ks,
            'status': 'active' if ak > 0 else 'warning'}

def observe(j) -> str:
    a = analyze(j)
    if a['status'] == 'insufficient_data':
        return f"📊 Observer: {a['message']}\n"

    lines = [f"📊 Moon Reversal Observer",
             f"  模拟交易: {a['trades']}笔 | 胜率: {a['win_rate']*100:.0f}%",
             f"  均盈: {a['avg_win']:+.1f}% | 均亏: {a['avg_loss']:.1f}% | 累计: {a['total_pnl']:+.1f}%",
             f"  {a['kelly_suggestion']}"]

    if a['alerts']:
        lines.append("\n⚠️ 告警:")
        for alert in a['alerts']:
            lines.append(f"  {alert['level']} {alert['msg']}")
    else:
        lines.append("  ✅ 无异常，策略运行正常")

    j['observer'].append({'date': datetime.datetime.now().isoformat(), 'analysis': a})
    _io('w', j)
    return '\n'.join(lines)

if __name__ == '__main__':
    j = _io('r')
    print(observe(j))
