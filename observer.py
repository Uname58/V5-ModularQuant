#!/usr/bin/env python3
"""
Moon Reversal Observer — 策略观察 & 自适应层

功能:
  1. 绩效追踪 — 记录每笔模拟交易，对比回测基准
  2. 异常检测 — 胜率偏离、回撤超限、信号频率异常
  3. 自适应 — 根据实盘表现建议调整 Kelly / 暂停车交易
"""

import json, os, datetime
from typing import Optional

JOURNAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_journal.json")

# Backtest baseline (from 4-year backtest)
BASELINE = {
    'win_rate': 0.87,
    'avg_win': 6.4,      # %
    'avg_loss': 12.4,    # % (absolute)
    'max_drawdown': 13.8, # % worst single trade loss
    'trades_per_year': 3.75,
    'total_return': 60.8, # % over 4 years
    'kelly': 0.746,
}

def load_journal():
    if os.path.exists(JOURNAL_PATH):
        with open(JOURNAL_PATH) as f:
            return json.load(f)
    return {'trades': [], 'observer': [], 'status': 'active'}

def save_journal(j):
    with open(JOURNAL_PATH, 'w') as f:
        json.dump(j, f, indent=2, ensure_ascii=False)

def record_trade(journal, action, price, date, pnl=None, reason=""):
    """记录模拟交易"""
    trade = {
        'action': action,
        'price': price,
        'date': date,
        'reason': reason,
        'recorded_at': datetime.datetime.now().isoformat(),
    }
    if pnl is not None:
        trade['pnl_pct'] = pnl
    journal['trades'].append(trade)
    save_journal(journal)

def analyze(journal) -> dict:
    """分析当前绩效 vs 回测基准"""
    sells = [t for t in journal['trades'] if t['action'] == 'SELL' and 'pnl_pct' in t]
    
    if len(sells) < 2:
        return {
            'trades': len(sells),
            'status': 'insufficient_data',
            'message': f'仅{len(sells)}笔交易，需≥2笔才能分析',
        }
    
    wins = [t for t in sells if t['pnl_pct'] > 0]
    losses = [t for t in sells if t['pnl_pct'] <= 0]
    
    wr = len(wins) / len(sells)
    aw = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
    al = abs(sum(t['pnl_pct'] for t in losses) / len(losses)) if losses else 0
    total = sum(t['pnl_pct'] for t in sells)
    max_loss = min(t['pnl_pct'] for t in sells)
    
    # Deviation analysis
    wr_dev = (wr - BASELINE['win_rate']) / BASELINE['win_rate'] * 100
    total_dev = (total - BASELINE['total_return'] * len(sells)/BASELINE['trades_per_year']/4) if BASELINE['total_return'] else 0
    
    # Alerts
    alerts = []
    
    # Alert 1: Win rate dropped significantly
    if wr_dev < -30 and len(sells) >= 4:
        alerts.append({
            'level': '🔴 HIGH',
            'msg': f'胜率{wr*100:.0f}% 远低于基准{BASELINE["win_rate"]*100:.0f}%（偏差{wr_dev:.0f}%），策略可能失效',
        })
    elif wr_dev < -15 and len(sells) >= 4:
        alerts.append({
            'level': '🟡 MEDIUM',
            'msg': f'胜率{wr*100:.0f}% 低于基准{BASELINE["win_rate"]*100:.0f}%，持续观察',
        })
    
    # Alert 2: Single loss exceeds max baseline
    if abs(max_loss) > BASELINE['max_drawdown'] * 1.5:
        alerts.append({
            'level': '🔴 HIGH',
            'msg': f'单笔亏损{max_loss:.1f}% 远超历史最大{BASELINE["max_drawdown"]}%，需检查市场结构',
        })
    
    # Alert 3: Consecutive losses
    recent_3 = sells[-3:]
    if len(recent_3) == 3 and all(t['pnl_pct'] <= 0 for t in recent_3):
        alerts.append({
            'level': '🔴 HIGH',
            'msg': '连续3笔亏损！建议暂停交易，重新评估',
        })
    
    # Adaptive Kelly suggestion
    if wr >= 0.5 and al > 0:
        rr = aw / al
        adaptive_kelly = wr - (1 - wr) / rr
        adaptive_half = adaptive_kelly / 2 if adaptive_kelly > 0 else 0
    else:
        adaptive_kelly = 0
        adaptive_half = 0
    
    kelly_suggestion = ""
    if adaptive_kelly <= 0:
        kelly_suggestion = "❌ Kelly为负，不建议交易"
    elif adaptive_kelly < BASELINE['kelly'] * 0.5:
        kelly_suggestion = f"⚠️ Kelly降至{adaptive_half*100:.0f}%，建议降仓"
    elif adaptive_kelly > BASELINE['kelly'] * 1.3:
        kelly_suggestion = f"📈 Kelly升至{adaptive_half*100:.0f}%，可适当加仓"
    else:
        kelly_suggestion = f"✅ Kelly稳定 {adaptive_half*100:.0f}%"
    
    return {
        'trades': len(sells),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': wr,
        'avg_win': aw,
        'avg_loss': al,
        'total_pnl': total,
        'max_loss': max_loss,
        'wr_deviation': wr_dev,
        'alerts': alerts,
        'adaptive_kelly': adaptive_half,
        'kelly_suggestion': kelly_suggestion,
        'status': 'active' if adaptive_kelly > 0 else 'warning',
    }

def observe(journal) -> str:
    """生成观察报告（给 cron 用）"""
    analysis = analyze(journal)
    
    if analysis['status'] == 'insufficient_data':
        return f"📊 Observer: {analysis['message']}\n"
    
    lines = []
    lines.append(f"📊 Moon Reversal Observer")
    lines.append(f"  模拟交易: {analysis['trades']}笔 | 胜率: {analysis['win_rate']*100:.0f}%")
    lines.append(f"  均盈: {analysis['avg_win']:+.1f}% | 均亏: {analysis['avg_loss']:.1f}% | 累计: {analysis['total_pnl']:+.1f}%")
    lines.append(f"  {analysis['kelly_suggestion']}")
    
    if analysis['alerts']:
        lines.append(f"\n⚠️ 告警:")
        for a in analysis['alerts']:
            lines.append(f"  {a['level']} {a['msg']}")
    else:
        lines.append(f"  ✅ 无异常，策略运行正常")
    
    # Save observation
    journal['observer'].append({
        'date': datetime.datetime.now().isoformat(),
        'analysis': analysis,
    })
    save_journal(journal)
    
    return '\n'.join(lines)

if __name__ == '__main__':
    j = load_journal()
    report = observe(j)
    print(report)
