import pandas as pd
import requests
import json
import os
from datetime import datetime
import time

data_dir = "/root/.openclaw/workspace/stock_analyzer/data"

# 港股列表 (新浪财经格式)
hk_stocks = [
    {"code": "00285", "name": "比亚迪电子", "sina_code": "hk00285"},
    {"code": "00700", "name": "腾讯控股", "sina_code": "hk00700"},
    {"code": "09988", "name": "阿里巴巴", "sina_code": "hk09988"},
]

def fetch_hk_stock_sina(stock):
    """从新浪财经获取港股历史数据"""
    code = stock["code"]
    name = stock["name"]
    sina_code = stock["sina_code"]
    
    # 新浪财经港股K线接口
    # 获取日K线，最多1000个交易日
    url = f"https://quotes.sina.cn/cn/api/quotes.php?symbol={sina_code}&scale=240&ma=5&datalen=1000"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://finance.sina.com.cn',
            'Accept': '*/*',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        text = response.text
        
        # 新浪返回的是JS变量格式，需要解析
        if '"day"' in text or '"data"' in text:
            # 尝试找到JSON数组
            start = text.find('[')
            end = text.rfind(']') + 1
            
            if start > 0 and end > start:
                data_array = json.loads(text[start:end])
                
                # 解析数据 [date, open, high, low, close, volume]
                records = []
                for item in data_array:
                    if isinstance(item, list) and len(item) >= 6:
                        records.append({
                            'date': item[0],
                            'open': float(item[1]),
                            'high': float(item[2]),
                            'low': float(item[3]),
                            'close': float(item[4]),
                            'volume': int(float(item[5]))
                        })
                
                if records:
                    df = pd.DataFrame(records)
                    df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                    
                    # 过滤2022年后的数据
                    df = df[df['date'] >= '2022-01-01']
                    
                    df['stock_code'] = code
                    df['stock_name'] = name
                    df['market'] = 'HK'
                    
                    return df
                    
    except Exception as e:
        print(f"  新浪接口错误: {e}")
    
    return None

def fetch_hk_stock_qq(stock):
    """从腾讯财经获取港股历史数据"""
    code = stock["code"]
    name = stock["name"]
    
    # 腾讯财经港股日K线接口
    # 需要构造请求参数
    url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=hk{code},day,2022-01-01,{datetime.now().strftime('%Y-%m-%d')},1000,qfq"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://stockapp.finance.qq.com',
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()
        
        # 解析腾讯返回的数据
        key = f"hk{code}"
        if key in data.get('data', {}):
            klines = data['data'][key].get('day', [])
            
            if klines:
                records = []
                for item in klines:
                    if len(item) >= 6:
                        records.append({
                            'date': item[0],
                            'open': float(item[1]),
                            'close': float(item[2]),
                            'low': float(item[3]),
                            'high': float(item[4]),
                            'volume': int(float(item[5]))
                        })
                
                if records:
                    df = pd.DataFrame(records)
                    df['stock_code'] = code
                    df['stock_name'] = name
                    df['market'] = 'HK'
                    
                    # 调整列顺序
                    df = df[['date', 'stock_code', 'stock_name', 'market', 'open', 'high', 'low', 'close', 'volume']]
                    return df
                    
    except Exception as e:
        print(f"  腾讯接口错误: {e}")
    
    return None

print("【港股数据获取 - 多源尝试】")
print("=" * 60)

all_data = {}

for stock in hk_stocks:
    code = stock["code"]
    name = stock["name"]
    
    print(f"\n尝试获取 {code} {name}...")
    
    # 先尝试腾讯接口
    print("  → 尝试腾讯财经...")
    df = fetch_hk_stock_qq(stock)
    
    if df is not None and len(df) > 0:
        # 保存
        filepath = os.path.join(data_dir, f"{code}_{name}.csv")
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        all_data[code] = df
        print(f"  ✅ 腾讯财经成功: {len(df)} 条记录")
    else:
        # 再尝试新浪
        print("  → 尝试新浪财经...")
        time.sleep(1)
        df = fetch_hk_stock_sina(stock)
        
        if df is not None and len(df) > 0:
            filepath = os.path.join(data_dir, f"{code}_{name}.csv")
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            all_data[code] = df
            print(f"  ✅ 新浪财经成功: {len(df)} 条记录")
        else:
            print(f"  ❌ 所有接口失败")
    
    # 延迟避免限流
    time.sleep(3)

print("\n" + "=" * 60)
if all_data:
    print(f"📊 港股成功: {len(all_data)}/3")
    for code, df in all_data.items():
        print(f"   {code}: {len(df)} 条")
else:
    print("❌ 港股数据获取失败")
