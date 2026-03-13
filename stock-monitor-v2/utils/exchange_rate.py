"""
汇率获取模块
支持人民币兑港币汇率
"""

import requests
from typing import Optional
from datetime import datetime, timedelta

# 缓存汇率数据
_exchange_cache = {
    'rate': None,
    'timestamp': None,
    'ttl': 3600  # 1小时缓存
}

# 昨日收盘汇率缓存
_yesterday_rate_cache = {
    'rate': None,
    'date': None
}


def get_cny_hkd_rate() -> Optional[float]:
    """
    获取人民币兑港币汇率 (1 CNY = ? HKD)
    数据来源：新浪财经
    """
    global _exchange_cache
    
    # 检查缓存
    if _exchange_cache['rate'] and _exchange_cache['timestamp']:
        if datetime.now() - _exchange_cache['timestamp'] < timedelta(seconds=_exchange_cache['ttl']):
            return _exchange_cache['rate']
    
    try:
        # 新浪财经汇率API
        url = "https://hq.sinajs.cn/list=fx_susdcnh,fx_shkdcnh"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://finance.sina.com.cn'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gb2312'
        
        # 解析USD/CNY和HKD/CNY
        # var hq_str_fx_susdcnh="美元人民币,7.2350,7.2380,...";
        # var hq_str_fx_shkdcnh="港币人民币,0.9275,0.9280,...";
        
        text = response.text
        
        # 提取港币人民币汇率 (1 HKD = ? CNY)
        hkd_cny_match = text.find('fx_shkdcnh')
        if hkd_cny_match > 0:
            start = text.find('"', hkd_cny_match) + 1
            end = text.find('"', start)
            data_str = text[start:end]
            parts = data_str.split(',')
            if len(parts) >= 2:
                hkd_to_cny = float(parts[1])  # 1港币 = ?人民币
                # 转换为 1人民币 = ?港币
                cny_to_hkd = 1 / hkd_to_cny if hkd_to_cny > 0 else 1.09
                
                _exchange_cache['rate'] = round(cny_to_hkd, 4)
                _exchange_cache['timestamp'] = datetime.now()
                return _exchange_cache['rate']
        
        # 备用：使用固定汇率
        return 1.09
    except Exception as e:
        print(f"获取汇率失败: {e}")
        return 1.09  # 默认汇率


def get_yesterday_cny_hkd_rate() -> Optional[float]:
    """
    获取昨日收盘汇率 (1 CNY = ? HKD)
    用于持仓市值计算，保持与交易软件一致
    """
    global _yesterday_rate_cache
    
    # 检查是否已有今日缓存
    today = datetime.now().strftime('%Y-%m-%d')
    if _yesterday_rate_cache['date'] == today and _yesterday_rate_cache['rate']:
        return _yesterday_rate_cache['rate']
    
    try:
        # 使用新浪汇率数据中的昨日收盘价
        url = "https://hq.sinajs.cn/list=fx_shkdcnh"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://finance.sina.com.cn'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gb2312'
        
        text = response.text
        # 格式：var hq_str_fx_shkdcnh="港币人民币,0.9275,0.9280,0.9270,0.9285,昨收,开盘...";
        # 第6个字段通常是昨日收盘价
        
        start = text.find('"') + 1
        end = text.find('"', start)
        data_str = text[start:end]
        parts = data_str.split(',')
        
        # 尝试获取昨日收盘价（字段索引可能不同）
        yesterday_hkd_to_cny = None
        
        # 优先使用昨收字段（通常在第6位）
        if len(parts) >= 6:
            try:
                yesterday_hkd_to_cny = float(parts[5])  # 昨收
            except:
                pass
        
        # 如果获取不到昨收，使用当前价格作为备选
        if not yesterday_hkd_to_cny and len(parts) >= 2:
            yesterday_hkd_to_cny = float(parts[1])  # 当前价
        
        if yesterday_hkd_to_cny and yesterday_hkd_to_cny > 0:
            # 转换为 1人民币 = ?港币
            cny_to_hkd = 1 / yesterday_hkd_to_cny
            rate = round(cny_to_hkd, 4)
            
            # 缓存
            _yesterday_rate_cache['rate'] = rate
            _yesterday_rate_cache['date'] = today
            
            print(f"昨日收盘汇率: 1 CNY = {rate} HKD")
            return rate
        
        # 备用
        return 1.1339  # 默认昨日收盘汇率
    except Exception as e:
        print(f"获取昨日汇率失败: {e}")
        return 1.1339  # 默认昨日收盘汇率


def convert_hkd_to_cny(hkd_amount: float, rate: float = None) -> float:
    """港币转人民币"""
    if not rate:
        rate = get_cny_hkd_rate()
    return hkd_amount / rate if rate else hkd_amount


def convert_cny_to_hkd(cny_amount: float, rate: float = None) -> float:
    """人民币转港币"""
    if not rate:
        rate = get_cny_hkd_rate()
    return cny_amount * rate if rate else cny_amount


if __name__ == '__main__':
    rate = get_cny_hkd_rate()
    yesterday_rate = get_yesterday_cny_hkd_rate()
    print(f"当前汇率: 1 CNY = {rate} HKD")
    print(f"昨日收盘汇率: 1 CNY = {yesterday_rate} HKD")
    print(f"1000 HKD = {convert_hkd_to_cny(1000):.2f} CNY")
    print(f"1000 CNY = {convert_cny_to_hkd(1000):.2f} HKD")
