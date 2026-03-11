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
    
    # 移除可能的后缀（如.SZ, .HK）
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
                # 港股格式
                result[code_key] = {
                    'name': parts[0],
                    'price': float(parts[1]) if parts[1] else 0,  # 最新价
                    'open': float(parts[2]) if parts[2] else 0,
                    'high': float(parts[3]) if parts[3] else 0,
                    'low': float(parts[4]) if parts[4] else 0,
                    'prev_close': float(parts[5]) if parts[5] else 0,
                    'change': float(parts[1]) - float(parts[5]) if parts[1] and parts[5] else 0,
                    'change_percent': ((float(parts[1]) - float(parts[5])) / float(parts[5]) * 100) if parts[1] and parts[5] and float(parts[5]) > 0 else 0,
                    'volume': int(parts[8]) if len(parts) > 8 and parts[8] else 0,
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
