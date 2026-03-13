"""
股票行情数据获取模块
支持腾讯财经API（更实时）
"""

import requests
import re
from typing import Dict, List, Optional, Tuple

# 腾讯财经行情API
TENCENT_API_URL = "http://qt.gtimg.cn/q={codes}"


def normalize_tencent_code(code: str, market: str = 'A股') -> str:
    """
    将股票代码转换为腾讯格式
    A股: sh600000, sz000001
    港股: hk00700
    """
    code = code.strip()
    
    # 如果已经包含市场前缀，直接返回
    if code.startswith(('sh', 'sz', 'hk')):
        return code
    
    # 移除可能的后缀（如.SZ, .HK, .SH）
    if '.' in code:
        code = code.split('.')[0]
    
    if market == '港股' or len(code) == 5:
        return f"hk{code}"
    
    # A股判断
    # 沪市：60开头、688开头、900开头（B股）
    # 深市：00开头、30开头、200开头（B股）
    if code.startswith(('60', '688', '900')):
        return f"sh{code}"
    else:
        return f"sz{code}"


def parse_tencent_response(response_text: str) -> Dict:
    """
    解析腾讯行情返回数据
    
    格式：
    v_sh600000="1~浦发银行~600000~10.50~10.48~...";
    v_hk00700="1~腾讯控股~00700~385.20~382.00~...";
    
    字段说明（以~分隔）：
    0: 未知, 1: 名称, 2: 代码, 3: 当前价, 4: 昨收, 5: 今开, 
    6: 成交量(手), 7: 外盘, 8: 内盘, 9: 买一价, 10: 买一量, 
    11-18: 买二到买五, 19: 卖一价, 20: 卖一量, 21-28: 卖二到卖五,
    29-32: 最近逐笔成交, 33: 时间, 34: 涨跌, 35: 涨跌%, 
    36: 最高价, 37: 最低价, 38: 价格/成交量(手)/成交额, 
    39: 成交量(手), 40: 成交额(万), 41: 换手率, 42: 市盈率,
    43: 未知, 44: 最高价, 45: 最低价, 46: 振幅, 47: 流通市值,
    48: 总市值, 49: 市净率, 50: 涨停价, 51: 跌停价
    """
    result = {}
    
    # 提取所有股票数据
    pattern = r'v_([\w]+)="([^"]*)"'
    matches = re.findall(pattern, response_text)
    
    for code_key, data_str in matches:
        if not data_str:
            result[code_key] = None
            continue
        
        parts = data_str.split('~')
        if len(parts) < 10:
            result[code_key] = None
            continue
        
        try:
            # 解析基本数据
            name = parts[1] if len(parts) > 1 else ''
            code = parts[2] if len(parts) > 2 else ''
            price = float(parts[3]) if len(parts) > 3 and parts[3] else 0
            prev_close = float(parts[4]) if len(parts) > 4 and parts[4] else 0
            open_price = float(parts[5]) if len(parts) > 5 and parts[5] else 0
            high = float(parts[33]) if len(parts) > 33 and parts[33] else 0
            low = float(parts[34]) if len(parts) > 34 and parts[34] else 0
            
            # 腾讯直接提供涨跌和涨跌%
            change = float(parts[31]) if len(parts) > 31 and parts[31] else (price - prev_close)
            change_percent = float(parts[32]) if len(parts) > 32 and parts[32] else 0
            
            # 成交量（手）
            volume = int(float(parts[36])) if len(parts) > 36 and parts[36] else 0
            
            # 判断市场类型
            market = '港股' if code_key.startswith('hk') else 'A股'
            
            # 港股需要使用汇率换算
            # 腾讯港股数据中没有直接提供汇率，使用默认汇率
            exchange_rate = 1.1369  # 默认汇率
            price_cny = None
            if market == '港股' and price > 0:
                price_cny = price / exchange_rate
            
            result[code_key] = {
                'name': name,
                'price': price,
                'open': open_price,
                'high': high if high > 0 else price,
                'low': low if low > 0 else price,
                'prev_close': prev_close,
                'change': change,
                'change_percent': change_percent,
                'volume': volume,
                'market': market,
                'exchange_rate': exchange_rate,
                'price_cny': price_cny
            }
        except (ValueError, IndexError) as e:
            print(f"解析 {code_key} 数据出错: {e}")
            result[code_key] = None
    
    return result


def get_stock_quotes(stocks: List[Dict]) -> Dict[str, Dict]:
    """
    获取多只股票实时行情
    
    Args:
        stocks: 股票列表，每个元素包含 code 和 market
        
    Returns:
        以腾讯格式代码为key的行情字典
    """
    if not stocks:
        return {}
    
    # 转换为腾讯代码格式
    tencent_codes = []
    for stock in stocks:
        code = stock.get('code', '')
        market = stock.get('market', 'A股')
        tencent_code = normalize_tencent_code(code, market)
        tencent_codes.append(tencent_code)
    
    codes_str = ','.join(tencent_codes)
    url = TENCENT_API_URL.format(codes=codes_str)
    
    try:
        # 设置headers模拟浏览器请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'http://qt.gtimg.cn'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gb2312'  # 腾讯返回GB2312编码
        
        return parse_tencent_response(response.text)
    except Exception as e:
        print(f"获取行情失败: {e}")
        return {}


def get_single_stock_quote(code: str, market: str = 'A股') -> Optional[Dict]:
    """获取单只股票实时行情"""
    tencent_code = normalize_tencent_code(code, market)
    result = get_stock_quotes([{'code': code, 'market': market}])
    return result.get(tencent_code)


def get_stock_kline(code: str, market: str = 'A股', days: int = 90) -> List[Dict]:
    """
    获取股票K线数据（使用腾讯财经接口）
    
    Args:
        code: 股票代码
        market: A股/港股
        days: 获取多少天的数据，默认90天（约3个月）
        
    Returns:
        K线数据列表，每个元素包含 date, open, high, low, close, volume
    """
    tencent_code = normalize_tencent_code(code, market)
    
    # 腾讯财经K线API
    # fq=0 不复权，fq=1 前复权
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        'param': f"{tencent_code},day,,,{days},qfq"  # qfq 前复权
    }
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, params=params, headers=headers, timeout=15)
        data = response.json()
        
        # 解析K线数据
        kline_key = f"{tencent_code}"
        if 'data' in data and kline_key in data['data']:
            kline_data = data['data'][kline_key].get('qfqday', []) or data['data'][kline_key].get('day', [])
            
            result = []
            for item in kline_data:
                # 格式: [日期, 开盘, 收盘, 最低, 最高, 成交量]
                if len(item) >= 6:
                    result.append({
                        'date': item[0],
                        'open': float(item[1]),
                        'close': float(item[2]),
                        'low': float(item[3]),
                        'high': float(item[4]),
                        'volume': int(float(item[5]))
                    })
            return result
        return []
    except Exception as e:
        print(f"获取K线数据失败 {code}: {e}")
        return []


def calculate_axis_price(kline_data: List[Dict]) -> Dict:
    """
    基于K线数据计算中轴价格
    
    使用中位数和加权平均的综合算法：
    - 中位数价格：反映这段时间的中间水平
    - 成交量加权均价(VWAP)：反映主要成交区域
    
    Returns:
        {
            'axis_price': 中轴价格,
            'avg_price': 简单平均价,
            'vwap': 成交量加权均价,
            'median': 中位数价格,
            'max_price': 最高价,
            'min_price': 最低价,
            'std': 标准差（波动率）
        }
    """
    if not kline_data:
        return {}
    
    closes = [d['close'] for d in kline_data]
    volumes = [d['volume'] for d in kline_data]
    highs = [d['high'] for d in kline_data]
    lows = [d['low'] for d in kline_data]
    
    n = len(closes)
    
    # 简单平均
    avg_price = sum(closes) / n
    
    # 中位数
    sorted_closes = sorted(closes)
    median = sorted_closes[n // 2] if n % 2 == 1 else (sorted_closes[n//2-1] + sorted_closes[n//2]) / 2
    
    # 成交量加权均价(VWAP)
    total_volume = sum(volumes)
    vwap = sum(c * v for c, v in zip(closes, volumes)) / total_volume if total_volume > 0 else avg_price
    
    # 标准差（波动率）
    variance = sum((c - avg_price) ** 2 for c in closes) / n
    std = variance ** 0.5
    
    # 中轴价格 = 0.4 * 中位数 + 0.4 * VWAP + 0.2 * 简单平均
    # 这样兼顾了主要成交区和价格中枢
    axis_price = 0.4 * median + 0.4 * vwap + 0.2 * avg_price
    
    return {
        'axis_price': round(axis_price, 2),
        'avg_price': round(avg_price, 2),
        'vwap': round(vwap, 2),
        'median': round(median, 2),
        'max_price': round(max(highs), 2),
        'min_price': round(min(lows), 2),
        'std': round(std, 3),
        'days': n
    }


def get_dynamic_axis_price(code: str, market: str = 'A股', days: int = 90) -> Dict:
    """
    获取股票的动态中轴价格（基于历史K线）
    
    Returns:
        包含中轴价格和触发价位的字典
    """
    kline = get_stock_kline(code, market, days)
    
    if not kline:
        return {}
    
    axis_data = calculate_axis_price(kline)
    
    if not axis_data:
        return {}
    
    axis_price = axis_data['axis_price']
    
    # 基于波动率动态调整触发阈值
    # 如果波动率大(>5%)，阈值放宽到10%；波动率小(<3%)，阈值收紧到6%
    std = axis_data['std']
    avg = axis_data['avg_price']
    volatility = (std / avg * 100) if avg > 0 else 5
    
    if volatility > 5:
        trigger_pct = 0.10  # 10%
    elif volatility < 3:
        trigger_pct = 0.06  # 6%
    else:
        trigger_pct = 0.08  # 8%
    
    return {
        **axis_data,
        'trigger_buy': round(axis_price * (1 - trigger_pct), 2),
        'trigger_sell': round(axis_price * (1 + trigger_pct), 2),
        'trigger_pct': round(trigger_pct * 100, 1),
        'volatility': round(volatility, 2)
    }


if __name__ == '__main__':
    # 测试
    test_stocks = [
        {'code': '000559', 'market': 'A股'},
        {'code': '000001', 'market': 'A股'},
        {'code': '00700', 'market': '港股'},
    ]
    
    quotes = get_stock_quotes(test_stocks)
    for code, quote in quotes.items():
        if quote:
            print(f"{code}: {quote['name']} 价格:{quote['price']} 涨跌:{quote['change_percent']:.2f}%")
        else:
            print(f"{code}: 获取失败")
