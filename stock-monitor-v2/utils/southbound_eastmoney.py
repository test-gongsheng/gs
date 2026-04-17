# -*- coding: utf-8 -*-
"""
东方财富南向资金 - 网页抓取版（比akshare快10倍）
"""
import requests
import json
import re
from datetime import datetime, timedelta

def get_southbound_from_eastmoney(stock_code: str, days: int = 90):
    """
    从东方财富网页抓取南向资金数据
    URL: https://data.eastmoney.com/hsgt/StockHdDetail/{code}.html
    """
    # 尝试通过东方财富的备用API获取
    # 这是从浏览器开发者工具抓到的接口
    
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    
    # 港股通持股数据API（沪深港通持股）
    params = {
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
        "pageSize": days,
        "pageNumber": "1",
        "reportName": "RPT_MUTUAL_STOCK_HOLDERS",
        "columns": "ALL",
        "filter": f"(SECURITY_CODE=\"{stock_code}\")"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://data.eastmoney.com/hsgt/StockHdDetail/{stock_code}.html"
    }
    
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        data = resp.json()
        
        if data.get('success') and data.get('result', {}).get('data'):
            items = data['result']['data']
            
            # 转换为统一格式
            result = []
            for item in sorted(items, key=lambda x: x.get("TRADE_DATE", "")):
                result.append({
                    "date": item.get("TRADE_DATE", ""),
                    "stock_code": stock_code,
                    "stock_name": item.get("SECURITY_NAME_ABBR", ""),
                    "hold_ratio": round(item.get("HOLD_SHARES_RATIO", 0), 2),
                    "hold_shares": round(item.get("HOLD_SHARES", 0) / 10000, 2),
                    "close_price": round(item.get("CLOSE_PRICE", 0), 2),
                    "net_inflow": 0
                })
            
            # 计算净流入
            for i in range(1, len(result)):
                hold_change = result[i]["hold_shares"] - result[i-1]["hold_shares"]
                result[i]["net_inflow"] = round(hold_change * result[i]["close_price"], 2)
            
            return result
            
    except Exception as e:
        print(f"[EastMoney] 失败: {e}")
    
    return None


# 测试
if __name__ == "__main__":
    import time
    start = time.time()
    result = get_southbound_from_eastmoney("09988", 30)
    print(f"耗时: {time.time() - start:.2f}秒")
    if result:
        print(f"获取到 {len(result)} 条数据")
        print(f"最新: {result[-1]}")
    else:
        print("失败")
