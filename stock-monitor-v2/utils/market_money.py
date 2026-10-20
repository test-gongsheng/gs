# -*- coding: utf-8 -*-
"""市场情绪面板增强数据源（2026-10-20 接入，替代空占位 {} 导致的 undefined 上屏）

三个字段：
- margin:       两市融资余额（akshare stock_margin_account_info，沪深交易所官方 T+1 披露）
- capital_flow: 全市场主力/超大单/大单/中单/小单净流入
                （复用 utils/fund_flow.py 东财双通道：push2实时优先，push2his日K兜底）
- north_south:  南向资金复用 utils.southbound_capital 成熟采集链路；
                北向资金实时净买入自 2024-08-18 起交易所已停止披露，诚实标注"停止披露"，
                不接第三方估算（与港股沽空数据源决策同一原则）。

所有获取函数失败时返回 None / 兜底字典，由前端降级显示 "--"，绝不上屏 undefined。
"""
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_cache = {}
MARGIN_TTL = 4 * 3600      # 两融 T+1 官方数据，4小时缓存
FFLOW_TTL = 30 * 60        # 主力资金日内刷新，30分钟缓存
SOUTH_TTL = 30 * 60


def _cached(key, ttl, fn):
    now = time.time()
    ent = _cache.get(key)
    if ent is not None and now - ent[0] < ttl:
        return ent[1]
    v = fn()
    _cache[key] = (now, v)
    return v


# ---------- 融资余额 ----------

def _fetch_margin():
    import akshare as ak
    df = ak.stock_margin_account_info()
    last, prev = df.iloc[-1], df.iloc[-2]
    bal = float(last['融资余额'])
    prev_bal = float(prev['融资余额'])
    chg = round(bal - prev_bal, 1)
    pct = round(chg / prev_bal * 100, 2) if prev_bal else 0.0
    return {
        'total_margin_balance': round(bal, 1),
        'margin_change': chg,
        'margin_change_pct': pct,
        'sentiment': '看多' if pct > 0.1 else ('看空' if pct < -0.1 else '中性'),
        'date': str(last['日期'])[:10],
    }


def get_margin():
    """两市融资余额；失败返回 None"""
    try:
        return _cached('margin', MARGIN_TTL, _fetch_margin)
    except Exception as e:
        print(f'[market_money] 融资余额获取失败: {e}')
        return None


# ---------- 主力资金（全市场） ----------

def _fetch_capital_flow():
    """全市场主力资金（上证+深证合计）。
    优先实时通道（push2），被封时回退日K通道（push2his）——
    部分云主机IP段会被东财封禁，本地家用宽带通常正常（见fund_flow.py部署说明）。"""
    from fund_flow import _fetch_today_realtime, _fetch_daykline
    sh = _fetch_today_realtime('1.000001')
    sz = _fetch_today_realtime('0.399001')
    if sh and sz and sh.get('date') == sz.get('date'):
        d = sh['date']
    else:
        sh_h = {r['date']: r for r in (_fetch_daykline('1.000001', 5) or [])}
        sz_h = {r['date']: r for r in (_fetch_daykline('0.399001', 5) or [])}
        common = sorted(set(sh_h) & set(sz_h))
        if not common:
            raise RuntimeError('沪深两市资金流均不可用')
        d = common[-1]
        sh, sz = sh_h[d], sz_h[d]
    out = {'date': d}
    for k in ('main', 'small', 'medium', 'large', 'super_large'):
        out[k if k != 'main' else 'main_inflow'] = round((sh[k] + sz[k]) / 1e8, 1)
    return out


def get_capital_flow():
    """全市场主力资金（沪深合计）；失败返回 None"""
    try:
        return _cached('capital_flow', FFLOW_TTL, _fetch_capital_flow)
    except Exception as e:
        print(f'[market_money] 主力资金获取失败: {e}')
        return None


# ---------- 南向资金（复用成熟链路） ----------

_NORTH_STOP = {
    'north_inflow': 0,
    'north_sentiment': '停止披露',
    'north_cumulative': 0,
    'south_inflow': 0,
    'south_sentiment': '待接入',
}


def _fetch_north_south():
    from southbound_capital import get_southbound_overall_history, get_southbound_signal
    hist = get_southbound_overall_history(days=30)
    sig = get_southbound_signal()
    latest = hist[-1] if hist else None
    stale = True
    if latest and latest.get('date'):
        try:
            d0 = datetime.strptime(latest['date'], '%Y-%m-%d')
            stale = (datetime.now() - d0).days > 5
        except Exception:
            stale = True
    if not latest or stale:
        # 数据陈旧或缺失：不拿旧数据冒充今日，诚实降级
        return dict(_NORTH_STOP)
    return {
        'north_inflow': 0,
        'north_sentiment': '停止披露',
        'north_cumulative': 0,
        'south_inflow': round(float(latest['net_inflow']), 1),
        'south_sentiment': sig.get('signal', '中性'),
    }


def get_north_south():
    """南向资金；北向停止披露。任何失败都返回兜底字典，保证前端字段齐全"""
    try:
        return _cached('north_south', SOUTH_TTL, _fetch_north_south)
    except Exception as e:
        print(f'[market_money] 南向资金获取失败: {e}')
        return dict(_NORTH_STOP)


if __name__ == '__main__':
    # 自测：python utils/market_money.py
    print('margin:', get_margin())
    print('capital_flow:', get_capital_flow())
    print('north_south:', get_north_south())
