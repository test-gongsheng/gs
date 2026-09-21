# -*- coding: utf-8 -*-
"""
持仓股深度日报生成器 V3
独立模块，不依赖后端服务，对标豆包/专业投研水平
"""

import os
import sys
import json
import requests
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

# ========== 配置 ==========
BASE_DIR = os.path.dirname(__file__)
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')
DATA_DIR = os.path.join(BASE_DIR, 'data')  # __main__ 里事件引擎刷新依赖此常量（此前缺失导致刷新静默失败）
os.makedirs(REPORTS_DIR, exist_ok=True)

_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

# ========== 板块映射 ==========
SECTOR_MAP = {
    '601133': '半导体设备与服务',
    '688795': '半导体-GPU',
    '301308': '半导体-存储',
    '300316': '光伏设备',
    '300442': '数据中心/IDC',
    '002050': '汽车零部件-热管理',
    '000559': '汽车零部件',
    '002594': '新能源汽车',
    '000878': '有色金属-铜',
    '601600': '有色金属-铝',
    '300229': '软件-AI/大数据',
    '00285':  '电子制造',
    '00700':  '互联网-社交/游戏',
    '09988':  '互联网-电商/云',
}

# 板块指数代码（腾讯格式）
SECTOR_INDEX = {
    '半导体设备与服务': 'sh000001',  # 临时用大盘替代，后续优化
    '半导体-存储': 'sh000001',
    '半导体-GPU': 'sh000001',
    '光伏设备': 'sh000001',
    '数据中心/IDC': 'sh000001',
    '汽车零部件-热管理': 'sh000001',
    '汽车零部件': 'sh000001',
    '新能源汽车': 'sh000001',
    '有色金属-铜': 'sh000001',
    '有色金属-铝': 'sh000001',
    '软件-AI/大数据': 'sh000001',
    '电子制造': 'sh000001',
    '互联网-社交/游戏': 'hkHSI',
    '互联网-电商/云': 'hkHSI',
}


# ========== 数据获取 ==========

def normalize_tencent_code(code: str, market: str = 'A股') -> str:
    """股票代码转腾讯格式"""
    code = code.strip()
    if code.startswith(('sh', 'sz', 'hk')):
        return code
    if '.' in code:
        code = code.split('.')[0]
    if market == '港股' or len(code) == 5:
        return f"hk{code}"
    if code.startswith(('60', '688', '900')):
        return f"sh{code}"
    return f"sz{code}"


def _safe_float(s):
    """安全转换为float"""
    try:
        return float(s) if s else 0
    except (ValueError, TypeError):
        return 0


def is_trading_time(market: str = 'A股') -> bool:
    """判断当前是否处于交易时段（周一至周五；A股 9:30-11:30/13:00-15:00，港股 9:30-12:00/13:00-16:00）"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    if market == '港股':
        return (9 * 60 + 30 <= minutes <= 12 * 60) or (13 * 60 <= minutes <= 16 * 60)
    return (9 * 60 + 30 <= minutes <= 11 * 60 + 30) or (13 * 60 <= minutes <= 15 * 60)


def _format_amount(amount_yuan: float) -> str:
    """成交额格式化：元 -> 亿/万"""
    if not amount_yuan or amount_yuan <= 0:
        return 'N/A'
    if amount_yuan >= 100000000:
        return f"{amount_yuan / 100000000:.2f}亿"
    if amount_yuan >= 10000:
        return f"{amount_yuan / 10000:.0f}万"
    return f"{amount_yuan:.0f}元"


def get_tencent_quote(code: str, market: str = 'A股') -> Optional[Dict]:
    """腾讯实时行情（支持A股和港股）"""
    try:
        tc = normalize_tencent_code(code, market)
        url = f"http://qt.gtimg.cn/q={tc}"
        r = _session.get(url, timeout=15)
        r.encoding = 'gb2312'
        m = re.search(rf'v_{tc}="([^"]*)"', r.text)
        if not m:
            return None
        parts = m.group(1).split('~')
        if len(parts) < 10:
            return None
        
        is_hk = tc.startswith('hk')

        # A股和港股的字段位置不同
        if is_hk:
            # 港股字段映射（腾讯港股API格式与A股不同）
            # 实测: parts[31]=涨跌额, parts[32]=涨跌幅%, parts[33]=最高, parts[34]=最低
            #       parts[36]=成交量, parts[37]=成交额(港元,全额)
            price = _safe_float(parts[3])
            prev_close = _safe_float(parts[4])
            open_price = _safe_float(parts[5])
            change = _safe_float(parts[31]) if len(parts) > 31 else 0
            change_pct = _safe_float(parts[32]) if len(parts) > 32 else 0
            high = _safe_float(parts[33]) if len(parts) > 33 else 0
            low = _safe_float(parts[34]) if len(parts) > 34 else 0
            volume = int(_safe_float(parts[36])) if len(parts) > 36 else 0
            turnover = _safe_float(parts[37]) if len(parts) > 37 else 0
            amount = turnover  # 港股成交额为全额（元）
            turnover_rate = None  # 腾讯港股接口无换手率
        else:
            # A股字段映射
            # 实测: parts[37]=成交额(万元), parts[38]=换手率(%)
            price = _safe_float(parts[3])
            prev_close = _safe_float(parts[4])
            open_price = _safe_float(parts[5])
            high = _safe_float(parts[33]) if len(parts) > 33 else 0
            low = _safe_float(parts[34]) if len(parts) > 34 else 0
            volume = int(_safe_float(parts[36])) if len(parts) > 36 else 0
            change = _safe_float(parts[31]) if len(parts) > 31 else 0
            change_pct = _safe_float(parts[32]) if len(parts) > 32 else 0
            turnover = _safe_float(parts[37]) if len(parts) > 37 else 0
            amount = turnover * 10000  # A股成交额单位为万元，转为元
            turnover_rate = _safe_float(parts[38]) if len(parts) > 38 else None
        
        return {
            'name': parts[1],
            'price': price,
            'prev_close': prev_close,
            'open': open_price,
            'high': high if high > 0 else price,
            'low': low if low > 0 else price,
            'volume': volume,
            'change': change,
            'change_percent': change_pct,
            'turnover': turnover,
            'amount': amount,
            'turnover_rate': turnover_rate,
            'market_cap': 0,
            'pe_ttm': 0,
            'pb': 0,
        }
    except Exception as e:
        print(f"[腾讯行情] {code} 失败: {e}")
        return None


def get_tencent_kline(code: str, market: str = 'A股', days: int = 120) -> List[Dict]:
    """腾讯K线数据"""
    try:
        tc = normalize_tencent_code(code, market)
        url = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {'param': f"{tc},day,,,{days},qfq"}
        r = _session.get(url, params=params, timeout=15)
        data = r.json()
        kline_key = tc
        if 'data' in data and kline_key in data['data']:
            kline_data = data['data'][kline_key].get('qfqday', []) or data['data'][kline_key].get('day', [])
            result = []
            for item in kline_data:
                if len(item) >= 6:
                    # 腾讯K线行格式: [date, open, close, high, low, volume]——index3=high, index4=low
                    result.append({
                        'date': item[0],
                        'open': float(item[1]),
                        'close': float(item[2]),
                        'high': float(item[3]),
                        'low': float(item[4]),
                        'volume': int(float(item[5]))
                    })
            return result
    except Exception as e:
        print(f"[腾讯K线] {code} 失败: {e}")
    return []


def get_stock_news(code: str) -> List[Dict]:
    """个股新闻（akshare）"""
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=code)
        news = []
        for _, row in df.head(10).iterrows():
            news.append({
                'title': str(row.get('新闻标题', row.get('标题', ''))),
                'content': str(row.get('新闻内容', row.get('内容', '')))[:300],
                'time': str(row.get('发布时间', '')),
                'source': str(row.get('文章来源', row.get('来源', '')))
            })
        return news
    except Exception as e:
        print(f"[新闻] {code} 失败: {e}")
        return []


# ========== 技术指标计算 ==========

def calculate_ma(prices: List[float], period: int) -> List[float]:
    """简单移动平均"""
    if len(prices) < period:
        return []
    return [sum(prices[i-period:i]) / period for i in range(period, len(prices) + 1)]


def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
    """MACD指标"""
    if len(prices) < slow + signal:
        return {}
    
    def ema(data: List[float], n: int) -> List[float]:
        multiplier = 2 / (n + 1)
        ema_values = [data[0]]
        for price in data[1:]:
            ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
        return ema_values
    
    ema_fast = ema(prices, fast)
    ema_slow = ema(prices, slow)
    dif = [f - s for f, s in zip(ema_fast, ema_slow)]
    dea = ema(dif, signal)
    macd_hist = [2 * (d - a) for d, a in zip(dif[-len(dea):], dea)]
    
    return {
        'dif': round(dif[-1], 3),
        'dea': round(dea[-1], 3),
        'hist': round(macd_hist[-1], 3),
        'prev_hist': round(macd_hist[-2], 3) if len(macd_hist) > 1 else 0,
        'status': 'bullish' if dif[-1] > dea[-1] else 'bearish',
        'signal': '多头' if dif[-1] > dea[-1] else '空头',
    }


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """RSI指标"""
    if len(prices) < period + 1:
        return 50
    deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    avg_gain = sum(gains) / period if gains else 0.001
    avg_loss = sum(losses) / period if losses else 0.001
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)


def calculate_support_resistance(kline: List[Dict], days: int = 20) -> Dict:
    """计算支撑/压力位（近期高低点密集区）"""
    recent = kline[-days:] if len(kline) >= days else kline
    if not recent:
        return {}
    
    lows = [d['low'] for d in recent]
    highs = [d['high'] for d in recent]
    closes = [d['close'] for d in recent]
    
    # 支撑位：近期低点 + 整数关
    support1 = round(min(lows[-5:]), 2)  # 近5日最低
    support2 = round(min(lows), 2)        # 近20日最低
    support3 = round(int(min(lows)), 2)   # 整数关
    
    # 压力位：近期高点
    resistance1 = round(max(highs[-5:]), 2)  # 近5日最高
    resistance2 = round(max(highs), 2)        # 近20日最高
    
    return {
        'support_near': support1,
        'support_mid': support2,
        'support_strong': support3,
        'resistance_near': resistance1,
        'resistance_far': resistance2,
        'recent_low': support2,
        'recent_high': resistance2,
        'box_bottom': round(sorted(lows)[int(len(lows)*0.2)], 2),
        'box_top': round(sorted(highs)[int(len(highs)*0.8)], 2),
    }


def calculate_volume_ratio(kline: List[Dict]) -> Dict:
    """量比分析"""
    if len(kline) < 6:
        return {}
    today_vol = kline[-1]['volume']
    avg_5d = sum(d['volume'] for d in kline[-6:-1]) / 5
    avg_20d = sum(d['volume'] for d in kline[-21:-1]) / 20 if len(kline) >= 21 else avg_5d
    
    ratio_5d = today_vol / avg_5d if avg_5d > 0 else 0
    ratio_20d = today_vol / avg_20d if avg_20d > 0 else 0
    
    status = '缩量'
    if ratio_5d > 2:
        status = '显著放量'
    elif ratio_5d > 1.5:
        status = '放量'
    elif ratio_5d > 0.8:
        status = '正常量能'
    
    return {
        'today_vol': today_vol,
        'avg_5d': int(avg_5d),
        'avg_20d': int(avg_20d),
        'ratio_5d': round(ratio_5d, 2),
        'ratio_20d': round(ratio_20d, 2),
        'status': status,
    }


def calculate_all_indicators(kline: List[Dict]) -> Dict:
    """计算全部技术指标"""
    closes = [d['close'] for d in kline]
    if len(closes) < 60:
        return {}
    
    ma5 = calculate_ma(closes, 5)
    ma10 = calculate_ma(closes, 10)
    ma20 = calculate_ma(closes, 20)
    ma60 = calculate_ma(closes, 60)
    
    macd = calculate_macd(closes)
    rsi14 = calculate_rsi(closes, 14)
    rsi6 = calculate_rsi(closes, 6)
    
    sr = calculate_support_resistance(kline)
    vol = calculate_volume_ratio(kline)
    
    # 均线排列判断
    if ma5 and ma10 and ma20 and ma60:
        current_ma5, current_ma10 = ma5[-1], ma10[-1]
        current_ma20, current_ma60 = ma20[-1], ma60[-1]
        
        if current_ma5 > current_ma10 > current_ma20 > current_ma60:
            ma_trend = '多头排列'
        elif current_ma5 < current_ma10 < current_ma20 < current_ma60:
            ma_trend = '空头排列'
        else:
            ma_trend = '震荡排列'
        
        price_vs_ma5 = (closes[-1] - current_ma5) / current_ma5 * 100
        price_vs_ma20 = (closes[-1] - current_ma20) / current_ma20 * 100
    else:
        ma_trend = '数据不足'
        price_vs_ma5 = 0
        price_vs_ma20 = 0
    
    return {
        'ma': {
            '5': round(ma5[-1], 2) if ma5 else 0,
            '10': round(ma10[-1], 2) if ma10 else 0,
            '20': round(ma20[-1], 2) if ma20 else 0,
            '60': round(ma60[-1], 2) if ma60 else 0,
        },
        'ma_trend': ma_trend,
        'price_vs_ma5': round(price_vs_ma5, 2),
        'price_vs_ma20': round(price_vs_ma20, 2),
        'macd': macd,
        'rsi': {'rsi6': rsi6, 'rsi14': rsi14},
        'support_resistance': sr,
        'volume': vol,
    }


# ========== 综合分析 ==========

def analyze_technical(indicators: Dict, current_price: float) -> Dict:
    """技术面综合分析"""
    if not indicators:
        return {'status': '数据不足', 'summary': '技术指标计算失败'}
    
    ma = indicators.get('ma', {})
    macd = indicators.get('macd', {})
    rsi = indicators.get('rsi', {})
    sr = indicators.get('support_resistance', {})
    vol = indicators.get('volume', {})
    
    signals = []
    
    # MA分析
    if ma.get('5') and current_price < ma['5']:
        signals.append('股价跌破MA5，短期趋势走弱')
    if ma.get('20') and current_price < ma['20']:
        signals.append('股价跌破MA20，中期趋势承压')
    if ma.get('60') and current_price < ma['60']:
        signals.append('股价跌破MA60，中长期趋势转空')
    
    # MACD分析
    if macd.get('hist'):
        if macd['hist'] > 0 and macd.get('prev_hist', 0) > 0:
            if macd['hist'] > macd['prev_hist']:
                signals.append('MACD红柱扩大，多头动能增强')
            else:
                signals.append('MACD红柱缩小，多头动能减弱')
        elif macd['hist'] < 0 and macd.get('prev_hist', 0) < 0:
            if macd['hist'] < macd['prev_hist']:
                signals.append('MACD绿柱扩大，空头动能增强')
            else:
                signals.append('MACD绿柱缩小，空头动能减弱')
        elif macd['hist'] > 0 and macd.get('prev_hist', 0) < 0:
            signals.append('MACD金叉，短期转多')
        elif macd['hist'] < 0 and macd.get('prev_hist', 0) > 0:
            signals.append('MACD死叉，短期转空')
    
    # RSI分析
    rsi14 = rsi.get('rsi14', 50)
    if rsi14 > 70:
        signals.append(f'RSI={rsi14}，进入超买区')
    elif rsi14 < 30:
        signals.append(f'RSI={rsi14}，进入超卖区')
    elif rsi14 < 40:
        signals.append(f'RSI={rsi14}，偏弱')
    elif rsi14 > 60:
        signals.append(f'RSI={rsi14}，偏强')
    
    # 量能分析
    if vol.get('status'):
        signals.append(f"量能状态: {vol['status']}（量比{vol.get('ratio_5d', 0):.2f}）")
    
    # 综合判断
    bullish_count = sum(1 for s in signals if any(k in s for k in ['金叉', '增强', '偏强', '超卖']))
    bearish_count = sum(1 for s in signals if any(k in s for k in ['死叉', '减弱', '偏弱', '超买', '走弱', '承压', '转空']))
    
    if bearish_count > bullish_count + 1:
        overall = '偏弱'
    elif bullish_count > bearish_count + 1:
        overall = '偏强'
    else:
        overall = '震荡'
    
    return {
        'status': overall,
        'signals': signals,
        'bullish_count': bullish_count,
        'bearish_count': bearish_count,
    }


def generate_scenarios(current_price: float, avg_cost: float, indicators: Dict) -> Dict:
    """情景推演"""
    sr = indicators.get('support_resistance', {})
    
    # 基于支撑压力位做情景分析
    support_near = sr.get('support_near', current_price * 0.95)
    support_mid = sr.get('support_mid', current_price * 0.90)
    resistance_near = sr.get('resistance_near', current_price * 1.05)
    resistance_far = sr.get('resistance_far', current_price * 1.10)
    
    # 乐观情景
    optimistic_target = round(resistance_far * 1.05, 2) if resistance_far > current_price else round(current_price * 1.10, 2)
    optimistic_pct = (optimistic_target - current_price) / current_price * 100
    
    # 悲观情景
    pessimistic_target = min(support_mid, current_price * 0.90)
    pessimistic_pct = (pessimistic_target - current_price) / current_price * 100
    
    return {
        'optimistic': {
            'target': round(optimistic_target, 2),
            'pct': round(optimistic_pct, 1),
            'condition': f'放量突破{resistance_near}，板块情绪回暖',
        },
        'neutral': {
            'range': f"{round(support_near, 2)}-{round(resistance_near, 2)}",
            'condition': '维持震荡，等待方向选择',
        },
        'pessimistic': {
            'target': round(pessimistic_target, 2),
            'pct': round(pessimistic_pct, 1),
            'condition': f"跌破{support_near}支撑，技术面恶化",
        },
    }


# ========== 研报级增强：聚合信号与一致预期（A/C/D 需求） ==========

# A/H 两地上市映射（A股代码 -> 腾讯格式H股代码）；2026-09-21 已用 utils 行情逐一核验名称与价格可取
AH_H_MAP = {
    '301308': '09976',  # 江波龙 / 江波龙(H)
    '601600': '02600',  # 中国铝业 / 中国铝业(H)
    '002594': '01211',  # 比亚迪 / 比亚迪股份(H)
}


def _parse_news_dt(s: str) -> Optional[datetime]:
    """解析新闻/事件时间字符串，失败返回 None"""
    if not s:
        return None
    s = str(s).strip()[:19]
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _load_event_impact() -> Dict:
    """读取 data/event_impact.json，失败返回空 dict"""
    try:
        path = os.path.join(DATA_DIR, 'event_impact.json')
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f'[聚合信号] event_impact.json 读取失败: {e}')
        return {}


def buyback_signal(code: str) -> Optional[str]:
    """
    回购追踪（C-1）：扫描 event_impact.json 中该股近90天新闻标题+正文，
    正则提取回购金额并累计；识别'计划/拟回购'额度后计算执行比例。
    提取不到任何回购金额时返回 None（调用方不展示该信号）。
    """
    data = _load_event_impact()
    events = (data.get('stock_events') or {}).get(code) or []
    cutoff = datetime.now() - timedelta(days=90)

    amount_re = re.compile(r'回购[^\n]{0,60}?(\d+(?:\.\d+)?)\s*(亿|万)元')
    plan_re = re.compile(r'(?:拟回购|计划回购|回购预案|回购计划)[^\n]{0,60}?(\d+(?:\.\d+)?)\s*(亿|万)元')

    def _to_yi(v: float, unit: str) -> float:
        return v if unit == '亿' else v / 10000.0

    executed = 0.0
    planned = 0.0
    hits = 0
    for e in events:
        t = _parse_news_dt(e.get('time', ''))
        if t is None or t < cutoff:
            continue
        text = f"{e.get('title', '')}\n{e.get('content', '')}"
        # 标题与正文常重复同一金额，按事件内 (数值,单位) 去重，防止双计
        seen_amt = set()
        for m in plan_re.finditer(text):
            key = (m.group(1), m.group(2))
            if key in seen_amt:
                continue
            seen_amt.add(key)
            planned = max(planned, _to_yi(float(m.group(1)), m.group(2)))
        for m in amount_re.finditer(text):
            key = (m.group(1), m.group(2))
            if key in seen_amt:
                continue
            seen_amt.add(key)
            executed += _to_yi(float(m.group(1)), m.group(2))
            hits += 1

    if hits == 0 and planned <= 0:
        return None
    if executed > 0 and planned > 0:
        return (f"回购追踪：近90日累计回购约{executed:.1f}亿元"
                f"（占{planned:.1f}亿计划额的{executed / planned * 100:.0f}%）")
    if executed > 0:
        return f"回购追踪：近90日累计回购约{executed:.1f}亿元"
    return f"回购追踪：近90日披露回购计划约{planned:.1f}亿元（尚在执行初期，暂无落地金额）"


def ah_premium_signal(code: str, a_price: float) -> Optional[str]:
    """
    A/H 比价（C-2，仅 AH_H_MAP 中的持仓）：H股价按 utils 汇率折人民币后与A股价比较。
    汇率取 utils.exchange_rate.get_cny_hkd_rate()（1 CNY = ? HKD），失败兜底 1.0836。
    返回如 "A/H价格比1.26，H股较A股折价21%"；H股贵于A股时明确标注倒挂。
    """
    h_code = AH_H_MAP.get(code)
    if not h_code or not a_price or a_price <= 0:
        return None
    h_quote = get_tencent_quote(h_code, '港股')
    if not h_quote or not h_quote.get('price'):
        return None
    rate = None
    try:
        from utils.exchange_rate import get_cny_hkd_rate
        rate = get_cny_hkd_rate()
    except Exception:
        rate = None
    if not rate or rate <= 0:
        rate = 1.0836  # 近似口径：1 CNY ≈ 1.0836 HKD（1 HKD ≈ 0.923 CNY）
    h_price_cny = h_quote['price'] / rate
    if h_price_cny <= 0:
        return None
    ratio = a_price / h_price_cny
    if ratio >= 1:
        discount = (1 - 1 / ratio) * 100
        return (f"A/H比价：A/H价格比{ratio:.2f}，H股（¥{h_price_cny:.2f}等值）"
                f"较A股折价{discount:.0f}%")
    premium = (1 / ratio - 1) * 100
    return (f"A/H比价：A/H价格比{ratio:.2f}，H股（¥{h_price_cny:.2f}等值）"
            f"较A股溢价{premium:.0f}%（A/H倒挂，H股更贵）")


def unlock_signal_90d(code: str, current_price: float) -> Optional[str]:
    """
    未来解禁（C-3）：akshare stock_restricted_release_queue_em 拉取解禁队列，
    统计未来90天解禁（日期/数量/市值）。接口不可用或无解禁时返回 None。
    """
    try:
        import akshare as ak
        df = ak.stock_restricted_release_queue_em(symbol=code)
        if df is None or df.empty:
            return None
        today = datetime.now().strftime('%Y-%m-%d')
        end = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
        future = df[(df['解禁时间'].astype(str) >= today) & (df['解禁时间'].astype(str) <= end)]
        if future.empty:
            return None
        shares_total = 0.0
        mv_total = 0.0
        first_date = None
        for _, row in future.iterrows():
            d = str(row.get('解禁时间', ''))[:10]
            first_date = d if first_date is None else min(first_date, d)
            try:
                shares_total += float(row.get('实际解禁数量') or 0)
            except (TypeError, ValueError):
                pass
            try:
                mv_total += float(row.get('实际解禁数量市值') or 0)
            except (TypeError, ValueError):
                pass
        if mv_total <= 0 and shares_total > 0 and current_price > 0:
            mv_total = shares_total * current_price
        ratio_txt = ''
        try:
            ratios = [float(r) for r in future['占总市值比例'].tolist() if str(r) not in ('nan', 'None')]
            if ratios:
                ratio_txt = f"，合计占总市值{sum(ratios) * 100:.1f}%"
        except Exception:
            pass
        return (f"未来解禁：未来90天{len(future)}笔解禁（最近{first_date}），"
                f"合计约{shares_total / 10000:.0f}万股（约{mv_total / 100000000:.1f}亿元{ratio_txt}）")
    except Exception as e:
        print(f'[聚合信号] 解禁队列获取失败 {code}: {e}')
        return None


# 未抓取标记：区分"调用方未传参"与"抓取结果本身就是None"（如港股无覆盖），避免重复请求
_NOT_FETCHED = object()


def render_consensus_section(code: str, cons=_NOT_FETCHED) -> List[str]:
    """
    投行一致预期章节（B需求，卖方研报写法，全中文）。
    数据源：utils/consensus.get_consensus（同花顺盈利预测+东财研报）。
    数据不可得时整章降级为"暂无机构一致预期数据"，绝不编造。
    传入 cons 可避免重复请求（与综合研判章节共用同一份数据）。
    """
    lines: List[str] = []
    if cons is _NOT_FETCHED:
        try:
            from utils.consensus import get_consensus
            cons = get_consensus(code)
        except Exception as e:
            print(f'[一致预期] 模块异常 {code}: {e}')
            cons = None

    if not cons:
        lines.append('**一致预期：** 暂无机构一致预期数据（该股可能无机构覆盖或为港股，相关接口无数据）。')
        lines.append('')
        return lines

    years = cons.get('years') or []
    cur = years[0] if years else {}
    yoy = cons.get('profit_yoy_pct')

    # 1) 一致预期
    if cur:
        yoy_txt = f"（同比{'+' if yoy and yoy >= 0 else ''}{yoy:.1f}%）" if yoy is not None else ''
        eps_txt = ''
        if cur.get('eps_mean') is not None:
            eps_txt = f"、EPS均值{cur['eps_mean']:.2f}元"
        lines.append(
            f"**一致预期：** {cons.get('org_count', 0)}家机构预测{cur.get('year', '')}年"
            f"净利润均值{cur.get('profit_mean', 0):.2f}亿元{yoy_txt}{eps_txt}。"
        )
        if len(years) > 1:
            nxt = years[1]
            lines.append(
                f"- 远期预测：{nxt.get('year', '')}年净利均值{nxt.get('profit_mean', 0):.2f}亿元"
                f"（{nxt.get('org_count', 0)}家），{years[2].get('year', '')}年净利均值"
                f"{years[2].get('profit_mean', 0):.2f}亿元（{years[2].get('org_count', 0)}家）。"
                if len(years) > 2 else
                f"- 远期预测：{nxt.get('year', '')}年净利均值{nxt.get('profit_mean', 0):.2f}亿元"
                f"（{nxt.get('org_count', 0)}家）。"
            )
    # 2) 分歧度
    div = cons.get('divergence')
    if div is not None and cur:
        div_txt = f"**分歧度：** 最高预测{cur.get('profit_max', 0):.2f}亿 vs 最低预测{cur.get('profit_min', 0):.2f}亿，"
        if div >= 2:
            div_txt += f"相差{div:.2f}倍——预测分歧大，中期盈利路径不确定，一致预期的置信度打折。"
        else:
            div_txt += f"相差{div:.2f}倍，预测区间相对收敛。"
        lines.append(div_txt)
        bb = cons.get('bull_bear')
        if bb and bb.get('high') and bb.get('low'):
            lines.append(
                f"- 多空代表（当年研报EPS预测）：最乐观{bb['high']['org']}"
                f"（{bb['high']['eps']:.2f}元，{bb['high']['date']}）vs "
                f"最谨慎{bb['low']['org']}（{bb['low']['eps']:.2f}元，{bb['low']['date']}）。"
            )
    # 3) 评级
    ratings = cons.get('rating_90d') or {}
    total_r = cons.get('rating_total_90d', 0)
    if total_r > 0:
        parts = '、'.join(f"{k}{v}" for k, v in sorted(ratings.items(), key=lambda x: -x[1]))
        lines.append(f"**评级（近90天）：** 共{total_r}家，{parts}。")
    else:
        lines.append('**评级（近90天）：** 暂无新研报覆盖。')
    for r in (cons.get('recent_reports') or [])[:3]:
        lines.append(f"- {r['date']} {r['org']}【{r['rating']}】{r['title']}")
    lines.append('')
    return lines


def render_verdict_section(code: str, market: str, current_price: float,
                           kline: List[Dict], indicators: Dict,
                           consensus: Optional[Dict] = None) -> List[str]:
    """
    综合研判章节（D需求）：纯规则引擎，不调用LLM。
    四象限输入：①事件面（近10日个股+概念事件利好/利空净值）②资金面（近5日主力净流入）
              ③技术面（MA20 + 中轴价格位置）④估值面（一致预期分歧度，缺失跳过）。
    判定：偏多 / 中性偏谨慎 / 偏空注意防守（禁止无条件下强多/强空）。
    传入 consensus 可避免重复请求（与投行一致预期章节共用同一份数据）。
    """
    reasons: List[str] = []
    score = 0

    # ① 事件面
    data = _load_event_impact()
    cutoff = datetime.now() - timedelta(days=10)
    pos = neg = 0
    for e in (data.get('stock_events') or {}).get(code) or []:
        t = _parse_news_dt(e.get('time', ''))
        if t is None or t < cutoff:
            continue
        if e.get('direction') == 'positive':
            pos += 1
        elif e.get('direction') == 'negative':
            neg += 1
    for ev in data.get('events') or []:
        t = _parse_news_dt(ev.get('latest_time', ''))
        if t is None or t < cutoff:
            continue
        for s in ev.get('impacted_stocks') or []:
            if s.get('code') == code:
                if s.get('expected') == 'positive':
                    pos += 1
                elif s.get('expected') == 'negative':
                    neg += 1
                break
    ev_net = pos - neg
    ev_score = 1 if ev_net >= 1 else (-1 if ev_net <= -1 else 0)
    score += ev_score
    reasons.append(
        f"事件面：近10日该股+所属概念事件净值{ev_net:+d}"
        f"（偏利好{pos}项 / 偏利空{neg}项）"
        + ("，消息面有明确催化。" if ev_score > 0 else "，消息面存在压制。" if ev_score < 0 else "，消息面平淡。")
    )

    # ② 资金面
    fund_sum = None
    fund_pos_days = 0
    fund_days = 0
    if market != '港股':
        try:
            from utils.fund_flow import get_fund_flow
            fflow = get_fund_flow(code, market, days=5)
        except Exception:
            fflow = None
        if fflow:
            recent5 = fflow[-5:]
            fund_sum = sum(item['main'] for item in recent5)
            fund_days = len(recent5)
            fund_pos_days = sum(1 for item in recent5 if item['main'] > 0)
            fund_score = 1 if fund_sum > 0 else -1
            score += fund_score
            reasons.append(
                f"资金面：近{fund_days}日主力净流入合计{fund_sum / 100000000:+.2f}亿"
                f"（{fund_pos_days}日为正）"
                + ("，资金在进场。" if fund_score > 0 else "，资金在撤离。")
            )
        else:
            reasons.append('资金面：流向数据暂不可用，该象限不计分。')

    # ③ 技术面
    ma20 = (indicators.get('ma') or {}).get('20')
    axis_price = None
    try:
        from utils.stock_quote import calculate_axis_price
        axis = calculate_axis_price(kline) if kline else {}
        axis_price = axis.get('axis_price')
    except Exception:
        axis_price = None

    tech_bits = []
    if ma20 and current_price > 0:
        dev = (current_price - ma20) / ma20 * 100
        score += 1 if current_price >= ma20 else -1
        tech_bits.append(
            f"{'站上' if current_price >= ma20 else '跌破'}MA20（{dev:+.1f}%）"
        )
    if axis_price and current_price > 0:
        dev_axis = (current_price - axis_price) / axis_price * 100
        score += 1 if current_price >= axis_price else -1
        tech_bits.append(
            f"中轴价格¥{axis_price:.2f}上方{dev_axis:+.1f}%"
            if current_price >= axis_price else
            f"跌破中轴价格¥{axis_price:.2f}（{dev_axis:+.1f}%）"
        )
    if tech_bits:
        reasons.append(f"技术面：现价¥{current_price:.2f}，" + '，'.join(tech_bits) + '。')
    else:
        reasons.append(f"技术面：现价¥{current_price:.2f}，均线/中轴数据不足，该象限弱化处理。")

    # ④ 估值面（一致预期分歧度，共用已抓取的数据避免重复请求）
    div = (consensus or {}).get('divergence')
    if div is not None:
        if div >= 2:
            score -= 1
            reasons.append(f"估值面：机构预测分歧度{div:.2f}倍（≥2倍），一致预期内部打架，按不确定处理。")
        else:
            reasons.append(f"估值面：机构预测分歧度{div:.2f}倍，盈利路径共识尚可。")
    else:
        reasons.append('估值面：无一致预期数据，该象限不计分。')

    # 判定（保守规则 + 硬条件兜底）
    deep_below_axis = bool(axis_price and current_price < axis_price * 0.92)
    fund_all_out = bool(fund_sum is not None and fund_days > 0 and fund_pos_days == 0 and fund_sum < 0)
    bull_combo = (ev_net >= 1 and fund_sum is not None and fund_sum > 0 and ma20
                  and current_price >= ma20)
    if ev_net <= -2 or fund_all_out or deep_below_axis:
        verdict = '偏空，注意防守'
    elif bull_combo:
        verdict = '偏多'
    elif score >= 2:
        verdict = '偏多'
    elif score <= -2:
        verdict = '偏空，注意防守'
    else:
        verdict = '中性偏谨慎'

    lines = [
        f"**综合研判：{verdict}。**",
        '',
        '**为什么是这个判断（四象限规则引擎，非AI拍脑袋）：**',
    ]
    for i, r in enumerate(reasons, 1):
        lines.append(f"{i}. {r}")
    lines.append('')
    return lines


# ========== 报告生成 ==========

def generate_deep_report(stock: Dict, report_date: str = None) -> str:
    """生成单只股票深度日报（Markdown）"""
    code = stock['code']
    name = stock['name']
    market = stock['market']
    avg_cost = stock.get('avg_cost', 0)
    shares = stock.get('shares', 0)
    report_date = report_date or datetime.now().strftime('%Y-%m-%d')
    
    print(f"\n[分析] {name}({code}) 深度报告生成中...")
    
    # 1. 获取实时行情
    quote = get_tencent_quote(code, market)
    if not quote:
        return f"# {name}({code}) 报告生成失败\n\n无法获取实时行情数据。"
    
    current_price = quote['price']
    prev_close = quote['prev_close']
    change = quote['change']
    change_pct = quote['change_percent']
    high = quote['high']
    low = quote['low']
    volume_shares = quote["volume"] * 100 if market != "港股" else quote["volume"]
    volume = volume_shares
    
    # 2. 获取K线数据（优先 utils 版：proxy.finance.qq.com 通道可用，且高低价字段已修正）
    try:
        from utils.stock_quote import get_stock_kline as _util_kline
        kline = _util_kline(code, market, days=120, max_retries=2)
    except Exception as _ke:
        print(f"[K线] utils通道异常，回退本地通道 {code}: {_ke}")
        kline = get_tencent_kline(code, market, days=120)
    
    # 3. 计算技术指标
    indicators = calculate_all_indicators(kline) if kline else {}
    
    # 4. 获取新闻
    news_list = get_stock_news(code)
    
    # 5. 综合分析
    tech_analysis = analyze_technical(indicators, current_price)
    scenarios = generate_scenarios(current_price, avg_cost, indicators)
    
    # 持仓计算
    market_value = current_price * shares
    pnl = market_value - avg_cost * shares if avg_cost > 0 else 0
    pnl_pct = pnl / (avg_cost * shares) * 100 if avg_cost > 0 else 0
    cost_gap = (current_price - avg_cost) / avg_cost * 100 if avg_cost > 0 else 0
    
    # 板块
    sector = SECTOR_MAP.get(code, '其他')
    
    # 构建报告
    lines = []
    
    # 标题
    lines.append(f"# 个股日报 / 深度复盘")
    lines.append(f"")
    suffix = 'HK' if market == '港股' else ('SH' if code.startswith('6') else 'SZ')
    lines.append(f"**{name} {code}.{suffix}** · {report_date} · 研究讨论，不构成投资建议")
    lines.append(f"")
    
    # ===== 持仓状态（实时联动，对标豆包盘中报告头部） =====
    if shares > 0 and avg_cost > 0:
        head_pnl_pct = (current_price - avg_cost) / avg_cost * 100
        head_pnl_wan = (current_price - avg_cost) * shares / 10000
        lines.append(f"## 持仓状态")
        lines.append(f"")
        if head_pnl_pct >= 0:
            lines.append(f"**浮盈 +{head_pnl_pct:.1f}%**（约 {head_pnl_wan:.2f} 万元）· 持仓 {shares:,} 股 / 成本 ¥{avg_cost:.2f}")
        else:
            head_back_pct = (avg_cost - current_price) / current_price * 100
            lines.append(f"**浮亏 {head_pnl_pct:.1f}%**（约 {abs(head_pnl_wan):.2f} 万元）· 回本需 **+{head_back_pct:.1f}%** · 持仓 {shares:,} 股 / 成本 ¥{avg_cost:.2f}")
        lines.append(f"")
    elif shares > 0:
        lines.append(f"## 持仓状态")
        lines.append(f"")
        lines.append(f"持仓 {shares:,} 股，成本已为负值（历史盈利覆盖），当前市值约 {current_price * shares / 10000:.2f} 万元。")
        lines.append(f"")
    
    # ===== 盘中快照（交易时段为盘中口径，非交易时段标注收盘快照） =====
    ma20_val = None
    if kline and len(kline) >= 20:
        ma20_val = sum(d['close'] for d in kline[-20:]) / 20
    in_trade = is_trading_time(market)
    snapshot_label = '盘中快照' if in_trade else '收盘快照'
    now_str = datetime.now().strftime('%H:%M')
    lines.append(f"## {snapshot_label}（{now_str}）")
    lines.append(f"")
    if not in_trade:
        lines.append(f"> 非交易时段，以下数据为最近收盘口径。")
        lines.append(f"")
    lines.append(f"| 项目 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 现价 | ¥{current_price:.2f}（{'+' if change_pct >= 0 else ''}{change_pct:.2f}%） |")
    lines.append(f"| 盘中区间 | ¥{low:.2f} — ¥{high:.2f} |")
    lines.append(f"| 成交额 | {_format_amount(quote.get('amount'))} |")
    _tr = quote.get('turnover_rate')
    lines.append(f"| 换手率 | {f'{_tr:.2f}%' if _tr is not None else 'N/A'} |")
    if ma20_val:
        _pos_pct = (current_price - ma20_val) / ma20_val * 100
        _pos_txt = f"上方 {_pos_pct:.2f}%" if _pos_pct >= 0 else f"下方 {abs(_pos_pct):.2f}%"
        lines.append(f"| MA20位置 | {_pos_txt}（MA20 ¥{ma20_val:.2f}） |")
    lines.append(f"")
    
    # 核心结论
    lines.append(f"## 核心结论")
    lines.append(f"")
    if avg_cost > 0:
        status_text = "浮盈" if pnl > 0 else "浮亏"
        lines.append(f"1. **持仓快照：** 您 {shares:,} 股、成本 ¥{avg_cost:.2f}，现价 ¥{current_price:.2f}，**{status_text}约 {abs(pnl_pct):.1f}%、约 ¥{abs(pnl):,.0f} 元**。")
    lines.append(f"2. **价格与量能：** 今日{'涨' if change >= 0 else '跌'} {abs(change_pct):.2f}%（{'+' if change >= 0 else ''}{change:.2f}元），成交额约 ¥{volume_shares * current_price / 100000000:.2f}亿。{tech_analysis.get('signals', ['暂无'])[0] if tech_analysis.get('signals') else ''}")
    
    # 技术面判断
    tech_status = tech_analysis.get('status', '震荡')
    if '偏弱' in tech_status or '空头' in str(indicators.get('ma_trend', '')):
        trend_desc = "技术偏弱，短期承压"
    elif '偏强' in tech_status or '多头' in str(indicators.get('ma_trend', '')):
        trend_desc = "技术偏强，短期动能向上"
    else:
        trend_desc = "技术震荡，方向未明"
    lines.append(f"3. **技术区间：** {trend_desc}。")
    
    if indicators.get('support_resistance'):
        sr = indicators['support_resistance']
        lines.append(f"4. **关键价位：** 下方支撑 ¥{sr.get('support_near', 'N/A')} / ¥{sr.get('support_mid', 'N/A')}，上方压力 ¥{sr.get('resistance_near', 'N/A')} / ¥{sr.get('resistance_far', 'N/A')}。")
    
    lines.append(f"")
    
    # 持仓快照表格
    lines.append(f"## 持仓快照")
    lines.append(f"")
    lines.append(f"| 项目 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 持仓成本 | ¥{avg_cost:.2f}（您提供/券商导出） |")
    lines.append(f"| 现价 | ¥{current_price:.2f} |")
    if avg_cost > 0:
        lines.append(f"| 浮亏/盈幅度 | **{'+' if pnl_pct >= 0 else ''}{pnl_pct:.1f}%** |")
        lines.append(f"| 持仓市值 | 约 ¥{market_value:,.0f} |")
        lines.append(f"| 累计浮亏/盈 | 约 ¥{pnl:,.0f} |")
    lines.append(f"| 所属板块 | {sector} |")
    lines.append(f"")
    
    # 今日行情与量能
    lines.append(f"## 一、今日行情、量能与资金流向")
    lines.append(f"")
    lines.append(f"**价格走势：** {report_date} {'盘中' if in_trade else '收盘'} ¥{current_price:.2f}，{'涨' if change >= 0 else '跌'} {abs(change_pct):.2f}%，日内区间 ¥{low:.2f}-¥{high:.2f}。")
    if indicators.get('volume'):
        vol = indicators['volume']
        lines.append(f"**量能分析：** 今日成交约 {vol['today_vol']/10000:.1f}万手（约¥{vol['today_vol']*current_price/10000:.0f}万），近5日均量约 {vol['avg_5d']/10000:.1f}万手，量比约 {vol['ratio_5d']:.2f}，属于**{vol['status']}**。")
    
    # ===== 资金流向（东财fflow接口；服务器IP可能被封，需优雅降级） =====
    lines.append(f"**资金流向：**")
    if market == '港股':
        lines.append(f"- 港股资金流暂不支持。")
    else:
        try:
            from utils.fund_flow import get_fund_flow
            fflow = get_fund_flow(code, market, days=5)
        except Exception as _fe:
            print(f'[DeepAnalysis] 资金流模块异常 {code}: {_fe}')
            fflow = None
        if fflow:
            recent_flow = fflow[-5:]
            for item in recent_flow:
                v = item['main'] / 100000000
                sign = '+' if v >= 0 else ''
                today_tag = '（今日盘中）' if item.get('is_today') else ''
                lines.append(f"- {item['date'][5:]}：主力净流入 {sign}{v:.2f} 亿{today_tag}")
            turns = []
            for i in range(1, len(recent_flow)):
                prev_d, cur_d = recent_flow[i-1], recent_flow[i]
                if prev_d['main'] < 0 <= cur_d['main']:
                    turns.append(f"{cur_d['date'][5:]} 由净流出转为净流入")
                elif prev_d['main'] >= 0 > cur_d['main']:
                    turns.append(f"{cur_d['date'][5:]} 由净流入转为净流出")
            if turns:
                lines.append(f"- 趋势转折：{'；'.join(turns)}。")
        else:
            lines.append(f"- 资金流向数据暂不可用（数据源受限）")
    lines.append(f"")
    
    # 技术面分析
    lines.append(f"## 二、技术面分析")
    lines.append(f"")
    if indicators.get('ma'):
        ma = indicators['ma']
        lines.append(f"**均线系统：**")
        lines.append(f"- MA5: ¥{ma['5']:.2f} {'↑' if current_price >= ma['5'] else '↓'}")
        lines.append(f"- MA10: ¥{ma['10']:.2f} {'↑' if current_price >= ma['10'] else '↓'}")
        lines.append(f"- MA20: ¥{ma['20']:.2f} {'↑' if current_price >= ma['20'] else '↓'}")
        lines.append(f"- MA60: ¥{ma['60']:.2f} {'↑' if current_price >= ma['60'] else '↓'}")
        lines.append(f"- 均线排列: **{indicators.get('ma_trend', '未知')}**")
        lines.append(f"")
    
    if indicators.get('macd'):
        macd = indicators['macd']
        lines.append(f"**MACD指标：** DIF={macd['dif']}, DEA={macd['dea']}, 柱状图={macd['hist']}。信号：**{macd['signal']}**。")
        lines.append(f"")
    
    if indicators.get('rsi'):
        rsi = indicators['rsi']
        lines.append(f"**RSI指标：** RSI(6)={rsi['rsi6']}, RSI(14)={rsi['rsi14']}。{'超买区' if rsi['rsi14'] > 70 else '超卖区' if rsi['rsi14'] < 30 else '中性区'}。")
        lines.append(f"")
    
    sr = indicators.get('support_resistance', {})
    if sr:
        lines.append(f"**关键价格区间：**")
        lines.append(f"- 近期支撑: ¥{sr['support_near']}（近5日低点）/ ¥{sr['support_mid']}（近20日低点）/ ¥{sr['support_strong']}（整数关）")
        lines.append(f"- 近期压力: ¥{sr['resistance_near']}（近5日高点）/ ¥{sr['resistance_far']}（近20日高点）")
        lines.append(f"- 箱体区间: ¥{sr['box_bottom']}-¥{sr['box_top']}")
        lines.append(f"")
    
    # 信号汇总
    if tech_analysis.get('signals'):
        lines.append(f"**技术信号汇总：**")
        for sig in tech_analysis['signals']:
            lines.append(f"- {sig}")
        lines.append(f"")
    
    # 综合评估与情景推演
    lines.append(f"## 三、综合评估与情景推演")
    lines.append(f"")
    lines.append(f"**当前技术状态: {tech_analysis.get('status', '震荡')}**")
    lines.append(f"")
    
    if scenarios:
        lines.append(f"**情景判断：**")
        lines.append(f"")
        lines.append(f"- **乐观情景：** 若 {scenarios['optimistic']['condition']}，目标位 ¥{scenarios['optimistic']['target']}（+{scenarios['optimistic']['pct']:.1f}%）。")
        lines.append(f"- **中性情景：** {scenarios['neutral']['condition']}，区间 {scenarios['neutral']['range']}。")
        lines.append(f"- **悲观情景：** 若 {scenarios['pessimistic']['condition']}，目标位 ¥{scenarios['pessimistic']['target']}（{scenarios['pessimistic']['pct']:.1f}%）。")
        lines.append(f"")
    
    # 针对持仓的评估
    if avg_cost > 0:
        if current_price < avg_cost * 0.85:
            lines.append(f"**持仓评估：** 当前价格距成本线仍有 {abs(cost_gap):.1f}% 差距，处于深度浮亏状态。")
            lines.append(f"- 若看好中长期逻辑，可在支撑位附近考虑补仓摊薄成本；")
            lines.append(f"- 若跌破 ¥{scenarios.get('pessimistic', {}).get('target', sr.get('support_mid', current_price*0.9))}，需重新评估持仓逻辑。")
        elif current_price < avg_cost:
            lines.append(f"**持仓评估：** 当前价格距成本线 {abs(cost_gap):.1f}%，处于小幅浮亏。")
            lines.append(f"- 关注能否放量突破 ¥{scenarios.get('optimistic', {}).get('target', sr.get('resistance_near', current_price*1.05))} 修复至成本线上方；")
            lines.append(f"- 若持续在成本下方震荡，需评估时间成本。")
        else:
            lines.append(f"**持仓评估：** 当前已盈利 {cost_gap:.1f}%。")
            lines.append(f"- 关注 ¥{scenarios.get('optimistic', {}).get('target', sr.get('resistance_near', current_price*1.05))} 附近的压力，注意止盈节奏。")
    lines.append(f"")
    
    # ===== 市场情绪对持仓的影响（第三、四层） =====
    try:
        from emotion_engine import format_sentiment_for_report
        sentiment_lines = format_sentiment_for_report(stock['code'])
        lines.append(f"## 四、市场情绪对持仓的影响——{stock.get('name', stock['code'])}")
        lines.append(f"")
        for sl in sentiment_lines:
            lines.append(sl)
        lines.append(f"")
    except Exception as e:
        import traceback
        print(f'[DeepAnalysis] 情绪章节生成失败: {e}')
        traceback.print_exc()
    
    # ===== 事件影响追踪（含解禁风险 + 聚合信号） =====
    try:
        from event_tracker import format_event_for_report
        event_lines = format_event_for_report(stock['code'])
        lines.append(f"## 五、事件影响追踪")
        lines.append(f"")
        for el in event_lines:
            lines.append(el)
        # C需求：消息面聚合信号（回购追踪 / A/H比价 / 未来解禁），全部真实数据，取不到就不显示
        agg_signals = []
        try:
            _bb = buyback_signal(code)
            if _bb:
                agg_signals.append(_bb)
        except Exception as _e:
            print(f'[聚合信号] 回购追踪异常 {code}: {_e}')
        try:
            _ah = ah_premium_signal(code, current_price)
            if _ah:
                agg_signals.append(_ah)
        except Exception as _e:
            print(f'[聚合信号] A/H比价异常 {code}: {_e}')
        try:
            _uk = unlock_signal_90d(code, current_price)
            if _uk:
                agg_signals.append(_uk)
        except Exception as _e:
            print(f'[聚合信号] 未来解禁异常 {code}: {_e}')
        if agg_signals:
            lines.append('**聚合信号（近90日维度）：**')
            for sig in agg_signals:
                lines.append(f"- {sig}")
            lines.append('')
    except Exception as e:
        pass  # 事件模块未运行时不阻塞报告

    # ===== 投行一致预期（B需求：卖方研报级机构预测/分歧度/评级） =====
    lines.append(f"## 六、投行一致预期（机构盈利预测与评级）")
    lines.append(f"")
    try:
        from utils.consensus import get_consensus as _get_consensus
        _cons = _get_consensus(code)
    except Exception as _e:
        print(f'[一致预期] 抓取失败 {code}: {_e}')
        _cons = None
    for cl in render_consensus_section(code, _cons):
        lines.append(cl)
    
    # 持仓实战分析（豆包式综合研判层）
    try:
        from tactics import generate_position_tactics
        tactics_lines = generate_position_tactics(stock, kline)
        if tactics_lines:
            lines.append(f"## 七、持仓实战分析")
            lines.append(f"")
            for tl in tactics_lines:
                lines.append(tl)
            lines.append(f"")
    except Exception as e:
        print(f'[Tactics] 实战分析生成失败: {e}')
    
    # 风险提示
    lines.append(f"## 八、短期风险提示")
    lines.append(f"")
    risks = []
    
    if indicators.get('macd') and indicators['macd'].get('hist', 0) < 0:
        risks.append("**技术风险：** MACD处于空头区域，短期动能向下。")
    if indicators.get('rsi') and indicators['rsi'].get('rsi14', 50) < 35:
        risks.append("**超卖风险：** RSI进入超卖区，虽可能反弹，但也可能延续弱势。")
    if indicators.get('volume') and indicators['volume'].get('ratio_5d', 1) < 0.6:
        risks.append("**流动性风险：** 量能萎缩，交投清淡，大单进出可能造成较大冲击。")
    if avg_cost > 0 and current_price < avg_cost * 0.85:
        risks.append("**回撤风险：** 当前浮亏较深，若继续下跌可能触发止损情绪集中释放。")
    
    if not risks:
        risks.append("**一般性风险：** 市场整体波动、板块轮动、宏观经济政策变化等。")
    
    for risk in risks:
        lines.append(f"{risk}")
    lines.append(f"")
    
    # 消息面
    if news_list:
        lines.append(f"## 九、近期消息摘要")
        lines.append(f"")
        for i, news in enumerate(news_list[:5], 1):
            lines.append(f"{i}. **{news['title']}**（{news['source']} {news['time']}）")
            if news['content']:
                lines.append(f"   {news['content'][:100]}...")
        lines.append(f"")
    
    # ===== 综合研判（D需求：四象限规则引擎，报告收尾、免责声明之前） =====
    try:
        lines.append(f"## 十、综合研判")
        lines.append(f"")
        for vl in render_verdict_section(code, market, current_price, kline, indicators, _cons):
            lines.append(vl)
    except Exception as _e:
        print(f'[综合研判] 生成失败 {code}: {_e}')
    
    # 免责声明
    lines.append(f"---")
    lines.append(f"**免责声明：** 以上内容由AI辅助生成，仅用于信息整理和投研辅助，不构成投资建议。历史数据不代表未来表现，请基于自身风险承受能力独立判断。")
    lines.append(f"")
    lines.append(f"**数据来源：** 腾讯财经（实时行情/K线）、东方财富（新闻/资金流向）。")
    
    return '\n'.join(lines)


# ========== 批量生成 ==========

def load_portfolio() -> List[Dict]:
    """加载持仓数据"""
    data_file = os.path.join(os.path.dirname(__file__), 'data', 'stocks.json')
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('stocks', [])
    except Exception as e:
        print(f"[错误] 读取持仓失败: {e}")
        return []


def generate_all_reports(target_codes: List[str] = None):
    """生成全部持仓深度报告"""
    stocks = load_portfolio()
    if target_codes:
        stocks = [s for s in stocks if s['code'] in target_codes]
    
    report_date = datetime.now().strftime('%Y-%m-%d')
    
    for stock in stocks:
        code = stock['code']
        name = stock['name']
        
        report = generate_deep_report(stock, report_date)
        
        # 保存Markdown
        md_path = os.path.join(REPORTS_DIR, f'deep_analysis_{code}_{report_date}.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"[保存] {name}({code}) -> {md_path}")
    
    print(f"\n[完成] 共生成 {len(stocks)} 份深度报告")


if __name__ == '__main__':
    import sys
    
    # 先生成事件数据（财联社电报+东财新闻+板块归因），报告第五节要用
    # 不区分指定股票/全量，事件分析本身是全局的
    try:
        import json as _json
        _df = _json.load(open(os.path.join(DATA_DIR, 'stocks.json'), encoding='utf-8'))
        from event_tracker import run_event_analysis
        print('[DeepAnalysis] 先跑事件引擎刷新事件数据...')
        run_event_analysis(_df.get('stocks', []))
    except Exception as e:
        print(f'[DeepAnalysis] 事件引擎刷新失败（用旧数据继续）: {e}')
    
    if len(sys.argv) > 1:
        # 指定股票代码
        codes = sys.argv[1:]
        generate_all_reports(codes)
    else:
        # 生成全部
        generate_all_reports()
