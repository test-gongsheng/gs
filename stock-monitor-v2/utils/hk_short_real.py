"""
港股真实沽空数据获取模块
从港交所披露易获取官方每日沽空数据
"""

import requests
import pandas as pd
from datetime import datetime, timedelta
import re


def get_hkex_short_selling_report(trade_date=None):
    """
    从港交所披露易获取每日沽空报告
    
    港交所每日收盘后披露所有股票的沽空数据：
    - 沽空股数
    - 沽空金额
    - 占成交比例
    
    Args:
        trade_date: 交易日期，格式 '20250321'，默认昨天
    
    Returns:
        DataFrame: 包含所有股票的沽空数据
    """
    if trade_date is None:
        # 获取昨天的数据（港交所T+1披露）
        yesterday = datetime.now() - timedelta(days=1)
        # 如果是周一，获取上周五数据
        if yesterday.weekday() == 0:  # 周一
            yesterday = yesterday - timedelta(days=3)
        elif yesterday.weekday() == 6:  # 周日
            yesterday = yesterday - timedelta(days=2)
        trade_date = yesterday.strftime('%Y%m%d')
    
    try:
        # 港交所披露易每日沽空报告URL
        # 格式：https://www.hkexnews.hk/sdw/search/mutualmarket.aspx?t=hk
        # 沽空数据通常在披露易的每日报告中
        
        # 尝试获取披露易的每日沽空数据文件
        # 港交所提供CSV格式的每日沽空报告
        url = f'https://www.hkex.com.hk/News/Market-Consolidation-Reports/Short-Selling-Report?sc_lang=zh-HK'
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        # 由于港交所页面可能需要JavaScript，尝试直接获取CSV文件
        # 港交所沽空报告CSV链接格式
        csv_url = f'https://www.hkex.com.hk/-/media/HKEX-Market/Mutual-Market/Stock-Connect/Short-Selling/Short_Selling_{trade_date}.csv'
        
        resp = requests.get(csv_url, headers=headers, timeout=15)
        
        if resp.status_code == 200:
            # 解析CSV数据
            from io import StringIO
            df = pd.read_csv(StringIO(resp.text))
            return df
        else:
            # 如果直接获取失败，尝试从东方财富获取（东财数据来自港交所）
            return get_short_selling_from_eastmoney(trade_date)
            
    except Exception as e:
        print(f"获取港交所沽空报告失败: {e}")
        return get_short_selling_from_eastmoney(trade_date)


def get_short_selling_from_eastmoney(trade_date=None):
    """
    从东方财富获取港股沽空数据（东财数据来源于港交所披露）
    """
    try:
        if trade_date is None:
            trade_date = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
        
        # 东方财富港股沽空数据接口
        url = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
        params = {
            'sortColumns': 'SHORT_SELLING_RATIO',  # 按沽空比例排序
            'sortTypes': '-1',
            'pageSize': '500',
            'pageNumber': '1',
            'reportName': 'RPT_HK_SHORT_SELLING',  # 港股沽空报告
            'columns': 'ALL',
            'filter': f"(TRADE_DATE='{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}')"
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://data.eastmoney.com/',
        }
        
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        data = resp.json()
        
        if data.get('result') and data['result'].get('data'):
            records = data['result']['data']
            df = pd.DataFrame(records)
            return df
        
        return None
        
    except Exception as e:
        print(f"从东方财富获取沽空数据失败: {e}")
        return None


def get_hk_stock_short_selling(stock_code: str, trade_date=None) -> dict:
    """
    获取港股个股真实沽空数据（港交所官方披露）
    
    Args:
        stock_code: 港股代码，如 '00700'
        trade_date: 交易日期，默认昨天
    
    Returns:
        Dict: 包含真实沽空金额、沽空比例
    """
    # 标准化代码
    stock_code = stock_code.zfill(5)
    
    try:
        # 尝试从东方财富获取准确数据
        df = get_short_selling_from_eastmoney(trade_date)
        
        if df is not None and len(df) > 0:
            # 查找特定股票
            # 东财数据列名：SECURITY_CODE, SECURITY_NAME, SHORT_SELLING_VOLUME, 
            #               SHORT_SELLING_AMOUNT, TOTAL_VOLUME, SHORT_SELLING_RATIO
            
            stock_row = df[df['SECURITY_CODE'] == stock_code]
            
            if len(stock_row) > 0:
                row = stock_row.iloc[0]
                
                short_volume = float(row.get('SHORT_SELLING_VOLUME', 0))
                short_amount = float(row.get('SHORT_SELLING_AMOUNT', 0)) / 100000000  # 转亿港元
                short_ratio = float(row.get('SHORT_SELLING_RATIO', 0))
                total_volume = float(row.get('TOTAL_VOLUME', 0))
                stock_name = row.get('SECURITY_NAME', '')
                
                return {
                    'success': True,
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'short_volume': int(short_volume),
                    'short_amount': round(short_amount, 2),
                    'short_ratio': round(short_ratio, 2),
                    'total_volume': int(total_volume),
                    'estimated': False,
                    'source': 'HKEX_via_Eastmoney',
                    'update_date': trade_date or (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                    'note': '港交所官方披露数据'
                }
        
        # 如果没有找到数据，返回错误
        return {
            'success': False,
            'stock_code': stock_code,
            'error': '未找到该股票的沽空数据',
            'estimated': True
        }
        
    except Exception as e:
        print(f"获取{stock_code}沽空数据失败: {e}")
        return {
            'success': False,
            'stock_code': stock_code,
            'error': str(e),
            'estimated': True
        }


def get_hk_short_selling(trade_date=None) -> dict:
    """
    获取港股市场整体沽空数据
    """
    try:
        df = get_short_selling_from_eastmoney(trade_date)
        
        if df is not None and len(df) > 0:
            # 计算市场 totals
            total_short_amount = df['SHORT_SELLING_AMOUNT'].sum() / 100000000  # 亿港元
            total_volume = df['TOTAL_VOLUME'].sum()
            total_short_volume = df['SHORT_SELLING_VOLUME'].sum()
            
            # 市场平均沽空比例
            market_short_ratio = (total_short_volume / total_volume * 100) if total_volume > 0 else 0
            
            # 计算趋势（需要历史数据）
            changes = {}
            
            return {
                'success': True,
                'short_amount': round(total_short_amount, 2),
                'short_ratio': round(market_short_ratio, 2),
                'stock_count': len(df),
                'estimated': False,
                'source': 'HKEX_via_Eastmoney',
                'update_date': trade_date or (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                'changes': changes,
                'note': '基于港交所官方披露数据计算'
            }
        
        return {
            'success': False,
            'error': '无法获取市场数据',
            'estimated': True
        }
        
    except Exception as e:
        print(f"获取港股整体沽空数据失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'estimated': True
        }


# 缓存机制
_short_selling_cache = {}
_cache_time = None

def get_hk_stock_short_selling_cached(stock_code: str, trade_date=None) -> dict:
    """
    带缓存的沽空数据获取
    """
    global _short_selling_cache, _cache_time
    
    # 检查缓存是否有效（1小时内）
    now = datetime.now()
    if _cache_time and (now - _cache_time).seconds < 3600:
        if stock_code in _short_selling_cache:
            return _short_selling_cache[stock_code]
    
    # 获取新数据
    result = get_hk_stock_short_selling(stock_code, trade_date)
    
    # 更新缓存
    if result.get('success'):
        _short_selling_cache[stock_code] = result
        _cache_time = now
    
    return result


if __name__ == '__main__':
    # 测试获取腾讯沽空数据
    result = get_hk_stock_short_selling('00700')
    print(f"腾讯沽空数据: {result}")
    
    # 测试市场整体数据
    market = get_hk_short_selling()
    print(f"市场整体: {market}")
