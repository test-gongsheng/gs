"""
南向资金快速数据源 - 使用东方财富直接API
替代 akshare 的全量数据拉取方式
"""
import requests
import json
import time
from datetime import datetime, timedelta

def get_southbound_stock_fast(stock_code: str, days: int = 90):
    """
    使用东方财富直接API获取南向资金数据（比akshare快10倍以上）
    
    API来源：东方财富港股通持股详情页
    示例URL：http://data.eastmoney.com/hkstock/ggt/00700.html
    """
    # 东方财富港股通个股API
    # 这个API直接返回单只股票的持股数据，不需要拉取全量数据
    url = "http://datacenter-web.eastmoney.com/api/data/v1/get"
    
    params = {
        "sortColumns": "HOLD_DATE",
        "sortTypes": "-1",  # 降序，最新的在前
        "pageSize": days,
        "pageNumber": "1",
        "reportName": "RPT_HKSTOCK_HOLDERS",
        "columns": "ALL",
        "filter": f"(SECURITY_CODE={stock_code.lstrip('0')})"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    try:
        print(f"[FastAPI] 请求: {stock_code}")
        start = time.time()
        
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        elapsed = time.time() - start
        print(f"[FastAPI] 响应: {elapsed:.2f}秒")
        
        if data.get("result") and data["result"].get("data"):
            items = data["result"]["data"]
            # 转换为统一格式
            result = []
            for item in reversed(items):  # 反转，按日期升序
                result.append({
                    "date": item["HOLD_DATE"][:10],  # YYYY-MM-DD
                    "stock_code": stock_code,
                    "stock_name": item.get("SECURITY_NAME_ABBR", ""),
                    "hold_ratio": round(item.get("HOLD_SHARES_RATIO", 0), 2),
                    "hold_shares": round(item.get("HOLD_SHARES", 0) / 10000, 2),  # 万股
                    "close_price": round(item.get("CLOSE_PRICE", 0), 2),
                    # 净流入需要计算（持股变化 × 股价）
                    "net_inflow": 0  # 需要额外计算
                })
            
            # 计算净流入（持股变化 × 股价）
            for i in range(1, len(result)):
                hold_change = result[i]["hold_shares"] - result[i-1]["hold_shares"]
                result[i]["net_inflow"] = round(hold_change * result[i]["close_price"], 2)
            
            return result
        
        return []
        
    except Exception as e:
        print(f"[FastAPI] 失败: {e}")
        return None  # 返回None表示失败，可以fallback到akshare


# 测试
if __name__ == "__main__":
    result = get_southbound_stock_fast("00700", 90)
    if result:
        print(f"获取到 {len(result)} 条数据")
        print(f"最新: {result[-1]}")
    else:
        print("获取失败")
