"""
股票行情数据获取模块
支持新浪财经API
"""

import requests
import re
from typing import Dict, List, Optional, Tuple

# 新浪行情API
SINA_API_URL = "http://hq.sinajs.cn/list={codes}"

def normalize_stock_code(code: str, market: str = 'A股') -> str:
    """
    将股票代码转换为新浪格式
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

def parse_sina_response(response_text: str) -> Dict:
    """
    解析新浪行情返回数据
    
    A股格式：
    var hq_str_sh600000="浦发银行,10.50,10.48,10.55,10.60,10.45,10.54,10.55,1234567,13000000,10.54,1000,10.53,2000,...";
    
    港股格式：
    var hq_str_hk00700="腾讯控股,385.20,382.00,387.50,389.00,383.50,385.20,385.40,385.60,1000000,0.83,1.62,HKG,100,386.00,...";
    """
    result = {}
    
    # 提取所有股票数据
    pattern = r'var hq_str_(\w+)="([^"]*)"'
    matches = re.findall(pattern, response_text)
    
    for code_key, data_str in matches:
        if not data_str:
            result[code_key] = None
            continue
            
        parts = data_str.split(',')
        
        try:
            if code_key.startswith('hk'):
                # 港股格式 (新浪)
                # 0:英文名, 1:中文名, 2:最新价, 3:昨收, 4:最高价, 5:最低价, 6:开盘价...
                result[code_key] = {
                    'name': parts[1] if len(parts) > 1 else parts[0],  # 中文名
                    'price': float(parts[2]) if len(parts) > 2 and parts[2] else 0,  # 最新价
                    'open': float(parts[6]) if len(parts) > 6 and parts[6] else 0,
                    'high': float(parts[4]) if len(parts) > 4 and parts[4] else 0,
                    'low': float(parts[5]) if len(parts) > 5 and parts[5] else 0,
                    'prev_close': float(parts[3]) if len(parts) > 3 and parts[3] else 0,
                    'change': float(parts[2]) - float(parts[3]) if len(parts) > 3 and parts[2] and parts[3] else 0,
                    'change_percent': ((float(parts[2]) - float(parts[3])) / float(parts[3]) * 100) if len(parts) > 3 and parts[2] and parts[3] and float(parts[3]) > 0 else 0,
                    'volume': int(float(parts[12])) if len(parts) > 12 and parts[12] else 0,
                    'market': '港股'
                }
            else:
                # A股格式
                # 0:名称, 1:今日开盘价, 2:昨日收盘价, 3:当前价, 4:最高价, 5:最低价
                result[code_key] = {
                    'name': parts[0],
                    'price': float(parts[3]) if parts[3] else 0,
                    'open': float(parts[1]) if parts[1] else 0,
                    'high': float(parts[4]) if parts[4] else 0,
                    'low': float(parts[5]) if parts[5] else 0,
                    'prev_close': float(parts[2]) if parts[2] else 0,
                    'change': float(parts[3]) - float(parts[2]) if parts[3] and parts[2] else 0,
                    'change_percent': ((float(parts[3]) - float(parts[2])) / float(parts[2]) * 100) if parts[3] and parts[2] and float(parts[2]) > 0 else 0,
                    'volume': int(parts[8]) if len(parts) > 8 and parts[8] else 0,
                    'market': 'A股'
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
        以新浪格式代码为key的行情字典
    """
    if not stocks:
        return {}
    
    # 转换为新浪代码格式
    sina_codes = []
    for stock in stocks:
        code = stock.get('code', '')
        market = stock.get('market', 'A股')
        sina_code = normalize_stock_code(code, market)
        sina_codes.append(sina_code)
    
    codes_str = ','.join(sina_codes)
    url = SINA_API_URL.format(codes=codes_str)
    
    try:
        # 设置headers模拟浏览器请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'http://finance.sina.com.cn'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gb2312'  # 新浪返回GB2312编码
        
        return parse_sina_response(response.text)
    except Exception as e:
        print(f"获取行情失败: {e}")
        return {}

def get_single_stock_quote(code: str, market: str = 'A股') -> Optional[Dict]:
    """获取单只股票实时行情"""
    sina_code = normalize_stock_code(code, market)
    result = get_stock_quotes([{'code': code, 'market': market}])
    return result.get(sina_code)


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
    sina_code = normalize_stock_code(code, market)
    
    # 腾讯财经K线API
    # fq=0 不复权，fq=1 前复权
    if sina_code.startswith('sh'):
        tencent_code = f"sh{code}"
    elif sina_code.startswith('sz'):
        tencent_code = f"sz{code}"
    elif sina_code.startswith('hk'):
        tencent_code = f"hk{code.replace('hk', '')}"
    else:
        tencent_code = code
    
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
