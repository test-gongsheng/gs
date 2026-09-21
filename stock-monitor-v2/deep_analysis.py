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
REPORTS_DIR = os.path.join(os.path.dirname(__file__), 'reports')
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
    
    # ===== 事件影响追踪（含解禁风险） =====
    try:
        from event_tracker import format_event_for_report
        event_lines = format_event_for_report(stock['code'])
        lines.append(f"## 五、事件影响追踪")
        lines.append(f"")
        for el in event_lines:
            lines.append(el)
        lines.append(f"")
    except Exception as e:
        pass  # 事件模块未运行时不阻塞报告
    
    # 持仓实战分析（豆包式综合研判层）
    try:
        from tactics import generate_position_tactics
        tactics_lines = generate_position_tactics(stock, kline)
        if tactics_lines:
            lines.append(f"## 六、持仓实战分析")
            lines.append(f"")
            for tl in tactics_lines:
                lines.append(tl)
            lines.append(f"")
    except Exception as e:
        print(f'[Tactics] 实战分析生成失败: {e}')
    
    # 风险提示
    lines.append(f"## 七、短期风险提示")
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
        lines.append(f"## 七、近期消息摘要")
        lines.append(f"")
        for i, news in enumerate(news_list[:5], 1):
            lines.append(f"{i}. **{news['title']}**（{news['source']} {news['time']}）")
            if news['content']:
                lines.append(f"   {news['content'][:100]}...")
        lines.append(f"")
    
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
