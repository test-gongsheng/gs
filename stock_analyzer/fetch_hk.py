import pandas as pd
import os
import yfinance as yf
from datetime import datetime
import time

data_dir = "/root/.openclaw/workspace/stock_analyzer/data"

# 港股列表
hk_stocks = [
    {"code": "0285.HK", "name": "比亚迪电子"},
    {"code": "0700.HK", "name": "腾讯控股"},
    {"code": "9988.HK", "name": "阿里巴巴"},
]

start_date = "2022-01-01"
end_date = datetime.now().strftime("%Y-%m-%d")

print("【港股 - yfinance 重试】")
print("=" * 60)

all_data = {}

for stock in hk_stocks:
    code = stock["code"]
    name = stock["name"]
    
    # 延迟避免限流
    time.sleep(2)
    
    try:
        ticker = yf.Ticker(code)
        df = ticker.history(start=start_date, end=end_date)
        
        if df is not None and len(df) > 0:
            df = df.reset_index()
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]
            
            df = df.rename(columns={
                'date': 'date',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume'
            })
            
            df['date'] = df['date'].dt.strftime('%Y-%m-%d')
            df['stock_code'] = code.replace('.HK', '')
            df['stock_name'] = name
            df['market'] = 'HK'
            
            df = df[['date', 'stock_code', 'stock_name', 'market', 'open', 'high', 'low', 'close', 'volume']]
            
            filename = f"{code.replace('.HK', '')}_{name}.csv"
            filepath = os.path.join(data_dir, filename)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            
            all_data[code] = df
            print(f"✅ {code} {name}: {len(df)} 条记录")
        else:
            print(f"⚠️ {code} {name}: 无数据")
            
    except Exception as e:
        print(f"❌ {code} {name}: {str(e)[:60]}")

print("=" * 60)
if all_data:
    print(f"📊 成功: {len(all_data)}/3 只港股")
else:
    print("❌ 港股数据获取失败")
