"""
股票行情数据获取模块 - AKShare版本
使用akshare作为稳定免费的主要数据源
"""

import requests
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# 尝试导入akshare
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    print("[警告] akshare未安装，将使用备用数据源")

# 备用数据源
TENCENT_API_URL = "http://qt.gtimg.cn/q={codes}"
SINA_API_URL = "https://hq.sinajs.cn/list={codes}"

# 缓存数据
_cache = {
    'a_spot': None,
    'hk_spot': None,
    'last_update': None
}


def normalize_tencent_code(code: str, market: str = 'A股') -> str:
    """
    将股票代码转换为腾讯格式
    A股: sh600000, sz000001
    港股: hk00700
    """
    code = code.strip()
    
    if code.startswith(('sh', 'sz', 'hk')):
        return code
    
    if '.' in code:
        code = code.split('.')[0]
    
    if market == '港股' or len(code) == 5:
        return f"hk{code}"
    
    if code.startswith(('60', '688', '900')):
        return f"sh{code}"
    else:
        return f"sz{code}"


normalize_stock_code = normalize_tencent_code


def get_akshare_a_spot() -> Dict[str, Dict]:
    """
    使用akshare获取A股实时行情（东方财富源）
    返回: {code: {name, price, change_percent, ...}}
    """
    if not AKSHARE_AVAILABLE:
        return {}
    
    try:
        # 获取A股实时行情
        df = ak.stock_zh_a_spot_em()
        
        result = {}
        for _, row in df.iterrows():
            code = str(row.get('代码', '')).strip()
            if not code:
                continue
            
            # 东方财富字段
            price = float(row.get('最新价', 0) or 0)
            prev_close = float(row.get('昨收', 0) or 0)
            open_price = float(row.get('今开', 0) or 0)
            high = float(row.get('最高价', 0) or 0)
            low = float(row.get('最低价', 0) or 0)
            volume = float(row.get('成交量', 0) or 0)
            change_percent = float(row.get('涨跌幅', 0) or 0)
            name = row.get('名称', '')
            
            # 计算涨跌额
            change = price - prev_close if price and prev_close else 0
            
            if code.startswith(('6', '688')):
                tencent_code = f"sh{code}"
            else:
                tencent_code = f"sz{code}"
            
            result[tencent_code] = {
                'name': name,
                'price': price,
                'open': open_price,
                'high': high,
                'low': low,
                'prev_close': prev_close,
                'change': change,
                'change_percent': change_percent,
                'volume': int(volume),
                'market': 'A股'
            }
        
        _cache['a_spot'] = result
        return result
        
    except Exception as e:
        print(f"[akshare] A股行情获取失败: {e}")
        return _cache.get('a_spot', {})


def get_akshare_hk_spot() -> Dict[str, Dict]:
    """
    使用akshare获取港股实时行情
    返回: {hkcode: {name, price, change_percent, ...}}
    """
    if not AKSHARE_AVAILABLE:
        return {}
    
    try:
        # 获取港股实时行情（港股通成分股）
        df = ak.stock_hk_ggt_components_em()
        
        result = {}
        for _, row in df.iterrows():
            code = str(row.get('代码', '')).strip().zfill(5)
            if not code:
                continue
            
            # 东方财富港股字段
            price = float(row.get('最新价', 0) or 0)
            prev_close = float(row.get('昨收', 0) or 0)
            open_price = float(row.get('今开', 0) or 0)
            high = float(row.get('最高价', 0) or 0)
            low = float(row.get('最低价', 0) or 0)
            volume = float(row.get('成交量', 0) or 0)
            change_percent = float(row.get('涨跌幅', 0) or 0)
            name = row.get('名称', '')
            
            change = price - prev_close if price and prev_close else 0
            
            tencent_code = f"hk{code}"
            
            result[tencent_code] = {
                'name': name,
                'price': price,
                'open': open_price,
                'high': high,
                'low': low,
                'prev_close': prev_close,
                'change': change,
                'change_percent': change_percent,
                'volume': int(volume),
                'market': '港股'
            }
        
        _cache['hk_spot'] = result
        return result
        
    except Exception as e:
        print(f"[akshare] 港股行情获取失败: {e}")
        return _cache.get('hk_spot', {})


def get_stock_quotes(stocks: List[Dict]) -> Dict[str, Dict]:
    """
    获取多只股票实时行情
    优先使用akshare，失败时回退到腾讯API
    
    Args:
        stocks: 股票列表，每个元素包含 code 和 market
        
    Returns:
        以腾讯格式代码为key的行情字典
    """
    if not stocks:
        return {}
    
    result = {}
    
    # 分离A股和港股
    a_stocks = [s for s in stocks if s.get('market') != '港股' and len(s.get('code', '')) != 5]
    hk_stocks = [s for s in stocks if s.get('market') == '港股' or len(s.get('code', '')) == 5]
    
    # 尝试使用akshare获取A股
    if a_stocks and AKSHARE_AVAILABLE:
        try:
            a_spot = get_akshare_a_spot()
            for stock in a_stocks:
                code = stock.get('code', '')
                tencent_code = normalize_tencent_code(code, 'A股')
                if tencent_code in a_spot:
                    result[tencent_code] = a_spot[tencent_code]
                else:
                    # 从备用源获取
                    backup = get_quote_from_tencent(code, 'A股')
                    if backup:
                        result[tencent_code] = backup
        except Exception as e:
            print(f"[akshare] A股获取异常，使用备用源: {e}")
            for stock in a_stocks:
                code = stock.get('code', '')
                tencent_code = normalize_tencent_code(code, 'A股')
                backup = get_quote_from_tencent(code, 'A股')
                if backup:
                    result[tencent_code] = backup
    elif a_stocks:
        # akshare不可用，使用腾讯API
        for stock in a_stocks:
            code = stock.get('code', '')
            tencent_code = normalize_tencent_code(code, 'A股')
            backup = get_quote_from_tencent(code, 'A股')
            if backup:
                result[tencent_code] = backup
    
    # 尝试使用akshare获取港股
    if hk_stocks and AKSHARE_AVAILABLE:
        try:
            hk_spot = get_akshare_hk_spot()
            for stock in hk_stocks:
                code = stock.get('code', '').zfill(5)
                tencent_code = normalize_tencent_code(code, '港股')
                if tencent_code in hk_spot:
                    result[tencent_code] = hk_spot[tencent_code]
                else:
                    # 从备用源获取
                    backup = get_quote_from_tencent(code, '港股')
                    if backup:
                        result[tencent_code] = backup
        except Exception as e:
            print(f"[akshare] 港股获取异常，使用备用源: {e}")
            for stock in hk_stocks:
                code = stock.get('code', '').zfill(5)
                tencent_code = normalize_tencent_code(code, '港股')
                backup = get_quote_from_tencent(code, '港股')
                if backup:
                    result[tencent_code] = backup
    elif hk_stocks:
        # akshare不可用，使用腾讯API
        for stock in hk_stocks:
            code = stock.get('code', '').zfill(5)
            tencent_code = normalize_tencent_code(code, '港股')
            backup = get_quote_from_tencent(code, '港股')
            if backup:
                result[tencent_code] = backup
    
    return result


def get_quote_from_tencent(code: str, market: str = 'A股') -> Optional[Dict]:
    """从腾讯财经获取单只股票行情（备用源）"""
    try:
        tencent_code = normalize_tencent_code(code, market)
        url = f"http://qt.gtimg.cn/q={tencent_code}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://qt.gtimg.cn'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gb2312'
        
        # 解析腾讯返回
        match = re.search(rf'v_{tencent_code}="([^"]*)"', response.text)
        if not match:
            return None
        
        parts = match.group(1).split('~')
        if len(parts) < 10:
            return None
        
        name = parts[1] if len(parts) > 1 else ''
        price = float(parts[3]) if len(parts) > 3 and parts[3] else 0
        prev_close = float(parts[4]) if len(parts) > 4 and parts[4] else 0
        open_price = float(parts[5]) if len(parts) > 5 and parts[5] else 0
        high = float(parts[33]) if len(parts) > 33 and parts[33] else 0
        low = float(parts[34]) if len(parts) > 34 and parts[34] else 0
        change = float(parts[31]) if len(parts) > 31 and parts[31] else (price - prev_close)
        change_percent = float(parts[32]) if len(parts) > 32 and parts[32] else 0
        volume = int(float(parts[36])) if len(parts) > 36 and parts[36] else 0
        
        return {
            'name': name,
            'price': price,
            'open': open_price,
            'high': high if high > 0 else price,
            'low': low if low > 0 else price,
            'prev_close': prev_close,
            'change': change,
            'change_percent': change_percent,
            'volume': volume,
            'market': market
        }
        
    except Exception as e:
        print(f"[腾讯] 获取失败 {code}: {e}")
        return None


def get_single_stock_quote(code: str, market: str = 'A股') -> Optional[Dict]:
    """获取单只股票实时行情"""
    tencent_code = normalize_tencent_code(code, market)
    result = get_stock_quotes([{'code': code, 'market': market}])
    return result.get(tencent_code)


def get_stock_kline(code: str, market: str = 'A股', days: int = 90, max_retries: int = 3) -> List[Dict]:
    """
    获取股票K线数据（使用akshare）
    
    Args:
        code: 股票代码
        market: A股/港股
        days: 获取多少天的数据，默认90天（约3个月）
        max_retries: 最大重试次数
        
    Returns:
        K线数据列表，每个元素包含 date, open, high, low, close, volume
    """
    if not AKSHARE_AVAILABLE:
        # 回退到腾讯K线
        return get_tencent_kline(code, market, days, max_retries)
    
    for attempt in range(max_retries):
        try:
            if market == '港股':
                # 港股历史数据
                df = ak.stock_hk_hist(symbol=code.zfill(5), period="daily", 
                                       start_date="20240101", adjust="qfq")
            else:
                # A股历史数据
                df = ak.stock_zh_a_hist(symbol=code, period="daily", 
                                       start_date="20240101", adjust="qfq")
            
            if df is None or df.empty:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(0.5 * (attempt + 1))
                    continue
                return []
            
            # 取最近days天
            df = df.tail(days)
            
            result = []
            for _, row in df.iterrows():
                result.append({
                    'date': str(row.get('日期', row.get('date', ''))),
                    'open': float(row.get('开盘', row.get('open', 0))),
                    'close': float(row.get('收盘', row.get('close', 0))),
                    'low': float(row.get('最低', row.get('low', 0))),
                    'high': float(row.get('最高', row.get('high', 0))),
                    'volume': int(float(row.get('成交量', row.get('volume', 0))))
                })
            
            return result
            
        except Exception as e:
            print(f"[akshare] K线获取失败 {code} (尝试{attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(0.5 * (attempt + 1))
            else:
                # 回退到腾讯K线
                return get_tencent_kline(code, market, days, max_retries)
    
    return []


def get_tencent_kline(code: str, market: str = 'A股', days: int = 90, max_retries: int = 3) -> List[Dict]:
    """从腾讯获取K线数据（备用）"""
    tencent_code = normalize_tencent_code(code, market)
    
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {'param': f"{tencent_code},day,,,{days},qfq"}
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=15)
            data = response.json()
            
            kline_key = f"{tencent_code}"
            if 'data' in data and kline_key in data['data']:
                kline_data = data['data'][kline_key].get('qfqday', []) or data['data'][kline_key].get('day', [])
                
                result = []
                for item in kline_data:
                    if len(item) >= 6:
                        result.append({
                            'date': item[0],
                            'open': float(item[1]),
                            'close': float(item[2]),
                            'low': float(item[3]),
                            'high': float(item[4]),
                            'volume': int(float(item[5]))
                        })
                
                if result:
                    return result
                elif attempt < max_retries - 1:
                    import time
                    time.sleep(0.3 * (attempt + 1))
            elif attempt < max_retries - 1:
                import time
                time.sleep(0.3 * (attempt + 1))
        except Exception as e:
            if attempt < max_retries - 1:
                import time
                time.sleep(0.5 * (attempt + 1))
    
    return []


def calculate_axis_price(kline_data: List[Dict]) -> Dict:
    """
    基于K线数据计算中轴价格
    
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


def get_dynamic_axis_price(code: str, market: str = 'A股', days: int = 90, max_retries: int = 3) -> Dict:
    """
    获取股票的动态中轴价格（基于历史K线）
    
    Returns:
        包含中轴价格和触发价位的字典
    """
    for attempt in range(max_retries):
        try:
            kline = get_stock_kline(code, market, days)
            
            if not kline:
                if attempt < max_retries - 1:
                    print(f"[get_dynamic_axis_price] {code} 第{attempt+1}次尝试无数据，重试...")
                    import time
                    time.sleep(0.5 * (attempt + 1))
                    continue
                print(f"[get_dynamic_axis_price] {code} 重试{max_retries}次后仍无数据")
                return {}
            
            axis_data = calculate_axis_price(kline)
            
            if not axis_data:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(0.5 * (attempt + 1))
                    continue
                return {}
            
            axis_price = axis_data['axis_price']
            
            # 基于波动率动态调整触发阈值
            std = axis_data['std']
            avg = axis_data['avg_price']
            volatility = (std / avg * 100) if avg > 0 else 5
            
            if volatility > 5:
                trigger_pct = 0.10
            elif volatility < 3:
                trigger_pct = 0.06
            else:
                trigger_pct = 0.08
            
            return {
                **axis_data,
                'trigger_buy': round(axis_price * (1 - trigger_pct), 2),
                'trigger_sell': round(axis_price * (1 + trigger_pct), 2),
                'trigger_pct': round(trigger_pct * 100, 1),
                'volatility': round(volatility, 2)
            }
        except Exception as e:
            print(f"[get_dynamic_axis_price] {code} 第{attempt+1}次尝试异常: {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(0.5 * (attempt + 1))
            else:
                raise
    
    return {}


if __name__ == '__main__':
    # 测试
    print("=== 测试AKShare数据源 ===")
    print(f"AKShare可用: {AKSHARE_AVAILABLE}")
    
    test_stocks = [
        {'code': '000001', 'market': 'A股'},
        {'code': '00700', 'market': '港股'},
    ]
    
    quotes = get_stock_quotes(test_stocks)
    for code, quote in quotes.items():
        if quote:
            print(f"{code}: {quote['name']} 价格:{quote['price']} 涨跌:{quote['change_percent']:.2f}%")
        else:
            print(f"{code}: 获取失败")
