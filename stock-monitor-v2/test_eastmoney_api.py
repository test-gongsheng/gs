"""
东方财富南向资金直接API - 抓包分析版本
页面: https://data.eastmoney.com/hsgt/StockHdDetail/09988.html
"""
import requests
import json
import time

def get_eastmoney_southbound(stock_code: str, days: int = 90):
    """
    东方财富港股通持股详情API
    从页面 https://data.eastmoney.com/hsgt/StockHdDetail/{code}.html 抓包获取
    """
    # 尝试多个可能的API端点
    
    # API 1: 港股通持股历史
    url1 = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params1 = {
        "sortColumns": "HOLD_DATE",
        "sortTypes": "-1",
        "pageSize": days,
        "pageNumber": "1",
        "reportName": "RPT_MUTUAL_STOCK_HOLDRATE",
        "columns": "ALL",
        "filter": f"(SECURITY_CODE=\"{stock_code}\")"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://data.eastmoney.com/hsgt/StockHdDetail/{stock_code}.html"
    }
    
    try:
        print(f"[EastMoney] 尝试API 1: {stock_code}")
        resp = requests.get(url1, params=params1, headers=headers, timeout=30)
        print(f"[EastMoney] 状态: {resp.status_code}")
        
        data = resp.json()
        print(f"[EastMoney] 响应: success={data.get('success')}, code={data.get('code')}")
        
        if data.get('success') and data.get('result', {}).get('data'):
            items = data['result']['data']
            print(f"[EastMoney] 获取到 {len(items)} 条数据")
            
            # 转换为统一格式
            result = []
            for item in items:
                result.append({
                    "date": item.get("HOLD_DATE", ""),
                    "stock_code": stock_code,
                    "stock_name": item.get("SECURITY_NAME_ABBR", ""),
                    "hold_ratio": round(item.get("HOLD_SHARES_RATIO", 0), 2),
                    "hold_shares": round(item.get("HOLD_SHARES", 0) / 10000, 2),
                    "close_price": round(item.get("CLOSE_PRICE", 0), 2),
                    "net_inflow": 0  # 需要计算
                })
            
            # 按日期排序（升序）
            result = sorted(result, key=lambda x: x["date"])
            
            # 计算净流入
            for i in range(1, len(result)):
                hold_change = result[i]["hold_shares"] - result[i-1]["hold_shares"]
                result[i]["net_inflow"] = round(hold_change * result[i]["close_price"], 2)
            
            return result
            
    except Exception as e:
        print(f"[EastMoney] API 1 失败: {e}")
    
    # API 2: 备选接口
    url2 = "https://datacenter.eastmoney.com/api/data/v1/get"
    
    try:
        print(f"[EastMoney] 尝试API 2: {stock_code}")
        resp = requests.get(url2, params=params1, headers=headers, timeout=30)
        data = resp.json()
        
        if data.get('success') and data.get('result', {}).get('data'):
            items = data['result']['data']
            print(f"[EastMoney] API 2 获取到 {len(items)} 条数据")
            # ... 同样处理
            
    except Exception as e:
        print(f"[EastMoney] API 2 失败: {e}")
    
    return None


# 测试
if __name__ == "__main__":
    start = time.time()
    result = get_eastmoney_southbound("09988", 30)
    elapsed = time.time() - start
    
    if result:
        print(f"\n成功! 耗时 {elapsed:.2f}秒, {len(result)} 条数据")
        if len(result) > 0:
            print(f"最新: {result[-1]}")
    else:
        print(f"\n失败! 耗时 {elapsed:.2f}秒")
