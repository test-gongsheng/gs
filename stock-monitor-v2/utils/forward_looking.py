# -*- coding: utf-8 -*-
"""
前瞻催化剂雷达（2026-09-29 新增）
====================================================
用户核心要求：报告要"有前瞻性，不要做事后诸葛亮"。
本模块聚合持仓股未来 N 天的已知催化剂，让每日报告从"复盘昨天"升级为"盯住明天"：

1. 解禁倒计时 —— event_tracker.analyze_unlock_risk 的未来解禁清单
2. 事件验证节点 —— event_verifier 里验证中的事件（d1/d3/d5 待到期节点）
3. 事件跟踪中 —— event_impact.json 近10天挂接的高级别事件（含方向）
4. 组合级宏观日程 —— 最新财联社电报池里"将于/明日/下周/FOMC/议息"类前瞻表述

数据源全部为本地已落盘文件，不新增外部接口；任何一项缺失即跳过，绝不编造日期。
"""
import os
import json
import glob
import re
from datetime import datetime, timedelta
from typing import Dict, List

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')

# 前瞻日程关键词：标题出现这些词且带未来时间暗示才入选
_SCHEDULE_KW = ['将于', '明日', '下周', '本周', 'FOMC', '议息', '利率决议',
                '发布会', '财报', '业绩披露', '解禁', '听证会', '听证',
                '开工', '投产', '量产', '交付', '表决', '投票', '生效', '落地']

_EVENT_STALE_DAYS = 10       # 事件跟踪的有效期
_MAX_PER_STOCK = 4           # 每只股票最多列几条催化剂
_MAX_MACRO = 6               # 组合级宏观日程最多几条


def _latest_news_pool() -> List[Dict]:
    """取日期最新的电报池文件"""
    files = sorted(glob.glob(os.path.join(DATA_DIR, 'news_pool_*.json')))
    if not files:
        return []
    try:
        with open(files[-1], encoding='utf-8') as f:
            data = json.load(f)
        return data.get('news', []) if isinstance(data, dict) else []
    except Exception:
        return []


def _scan_macro_schedule(news_list: List[Dict]) -> List[Dict]:
    """从电报池挑前瞻日程类条目（未来事件预告，非已发生复盘）"""
    out, seen = [], set()
    for n in news_list:
        title = re.sub(r'</?em>', '', n.get('title', '') or '')
        if not title or title in seen:
            continue
        if not any(k in title for k in _SCHEDULE_KW):
            continue
        # 排除纯行情播报
        if any(w in title for w in ['涨停', '跌停', '涨超', '跌超', '龙虎榜', '换手率']) and \
                not any(w in title for w in _SCHEDULE_KW[:8]):
            continue
        seen.add(title)
        out.append({'title': title[:80], 'time': n.get('time', ''),
                    'source': n.get('source', '')})
        if len(out) >= _MAX_MACRO:
            break
    return out


def _parse_time(s: str):
    if not s:
        return None
    s = str(s).strip()[:19]
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def build_stock_catalysts(code: str, name: str = '') -> List[Dict]:
    """单只持仓股的前瞻催化剂清单（按时间紧迫度排序）"""
    items: List[Dict] = []
    now = datetime.now()

    # 1) 解禁倒计时
    try:
        from event_tracker import analyze_unlock_risk
        unlock = analyze_unlock_risk(code, name) or {}
        for w in unlock.get('future_warnings', [])[:2]:
            items.append({
                'type': '解禁',
                'date': w.get('date', ''),
                'days_until': w.get('days_until'),
                'title': f"限售股解禁 {w.get('date', '')}"
                         + (f"（{w.get('shares_ratio') or w.get('ratio') or ''}）"
                            if (w.get('shares_ratio') or w.get('ratio')) else ''),
                'source': '解禁监控',
            })
    except Exception:
        pass

    # 2) 事件验证节点（验证中的 d1/d3/d5）
    try:
        from utils.event_verifier import verifications_for_code, format_verify_status
        for ev in verifications_for_code(code):
            verify = ev.get('verify') or {}
            if verify.get('conclusion'):
                continue  # 已结案，不再前瞻
            status = format_verify_status(ev)
            if '待到期' not in status:
                continue  # 全部节点已出数，无前瞻点
            items.append({
                'type': '验证节点',
                'date': '',
                'days_until': None,
                'title': f"{(ev.get('title') or '')[:40]} → {status}",
                'source': '事件验证',
            })
    except Exception:
        pass

    # 3) 事件跟踪中（近10天挂接的高级别事件，含方向供前瞻参考）
    try:
        path = os.path.join(DATA_DIR, 'event_impact.json')
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            cutoff = now - timedelta(days=_EVENT_STALE_DAYS)
            seen_t = set()
            for e in data.get('stock_events', {}).get(code, []):
                t = _parse_time(e.get('time', ''))
                if not t or t < cutoff:
                    continue
                clean = re.sub(r'^【.+?】', '', e.get('title', '') or '').strip()[:36]
                if not clean or clean in seen_t:
                    continue
                seen_t.add(clean)
                d = e.get('direction', 'neutral')
                items.append({
                    'type': '事件跟踪',
                    'date': (e.get('time', '') or '')[:10],
                    'days_until': None,
                    'title': clean,
                    'source': e.get('source', '') or '事件引擎',
                    'direction': d,
                })
    except Exception:
        pass

    # 排序：有明确日期的按天数升序在前，无日期的按类型稳定在后
    items = items[:_MAX_PER_STOCK]
    items.sort(key=lambda x: (x.get('days_until') is None, x.get('days_until') or 99))
    return items


def build_forward_outlook(stocks: List[Dict]) -> Dict:
    """组合级前瞻：每只股票催化剂 + 宏观日程"""
    per_stock = {}
    for s in stocks:
        code = s.get('code', '')
        cats = build_stock_catalysts(code, s.get('name', ''))
        if cats:
            per_stock[code] = {'name': s.get('name', code), 'catalysts': cats}

    macro = _scan_macro_schedule(_latest_news_pool())
    days_with_catalysts = sum(1 for v in per_stock.values() if v['catalysts'])
    return {
        'as_of': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'stocks': per_stock,
        'macro_schedule': macro,
        'stats': {
            'stocks_with_catalysts': days_with_catalysts,
            'total_catalysts': sum(len(v['catalysts']) for v in per_stock.values()),
            'macro_items': len(macro),
        },
    }


if __name__ == '__main__':
    # 自测：用真实持仓跑一遍
    with open(os.path.join(DATA_DIR, 'stocks.json'), encoding='utf-8') as f:
        _stocks = json.load(f).get('stocks', [])
    out = build_forward_outlook(_stocks)
    print(f"as_of={out['as_of']} stats={out['stats']}")
    for code, v in list(out['stocks'].items())[:4]:
        print(f"\n[{v['name']} {code}]")
        for c in v['catalysts'][:3]:
            print(f"  - [{c['type']}] {c['title'][:60]}")
    print("\n宏观日程:")
    for m in out['macro_schedule'][:3]:
        print(f"  - {m['time']} {m['title'][:60]}")
