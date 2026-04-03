"""
南向资金腾讯数据源 - 使用腾讯财经API（快速稳定）
腾讯港股通数据API示例：
https://qt.gtimg.cn/q=hk00700
"""
import requests
import json
from datetime import datetime, timedelta

def get_hk_stock_quote(stock_code: str):
    """获取港股实时行情（腾讯API）"""
    # 港股代码格式：00700 -> hk00700
    hk_code = f"hk{stock_code}"
    url = f"https://qt.gtimg.cn/q={hk_code}"
    
    try:
        resp = requests.get(url, timeout=10)
        # 腾讯返回格式: v_hk00700="...";
        text = resp.text
        if '"' in text:
            data = text.split('"')[1]
            fields = data.split('~')
            # 字段说明: https://blog.csdn.net/afgasdg/article/details/86076967
            return {
                "code": stock_code,
                "name": fields[1] if len(fields) > 1 else "",
                "price": float(fields[3]) if len(fields) > 3 else 0,
                "prev_close": float(fields[4]) if len(fields) > 4 else 0,
            }
    except Exception as e:
        print(f"[Tencent] 获取失败: {e}")
    return None


# 南向资金历史数据 - 使用新浪API
# http://finance.sina.com.cn/stock/hkstock/ggtjd/00700.shtml
# 新浪有港股通持股历史数据，可以通过其API获取

def get_sina_southbound_history(stock_code: str, days: int = 90):
    """
    新浪港股通持股历史数据
    API: http://stock.finance.sina.com.cn/stock/api/jsonp.php/list=xxx/HK_StockGgtHldls
    """
    # 新浪港股代码：00700 -> hk00700
    sina_code = f"hk{stock_code}"
    
    # 计算日期范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 30)
    
    url = "http://stock.finance.sina.com.cn/stock/api/jsonp.php/list=holder/T=stock/HK_StockGgtHldls"
    params = {
        "symbol": sina_code,
        "begin": start_date.strftime("%Y-%m-%d"),
        "end": end_date.strftime("%Y-%m-%d"),
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        # 新浪返回的是 JSONP 格式，需要解析
        text = resp.text
        if "=" in text:
            json_str = text.split("=", 1)[1].rstrip(";")
            data = json.loads(json_str)
            # 解析数据...
            return data
    except Exception as e:
        print(f"[Sina] 获取失败: {e}")
    return None


if __name__ == "__main__":
    # 测试腾讯API
    result = get_hk_stock_quote("00700")
    print("腾讯实时行情:", result)
