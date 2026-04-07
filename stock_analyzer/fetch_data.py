import pandas as pd
import os
import baostock as bs
import yfinance as yf
from datetime import datetime

data_dir = "/root/.openclaw/workspace/stock_analyzer/data"
os.makedirs(data_dir, exist_ok=True)

# A股列表
a_stocks = [
    {"code": "000559.SZ", "name": "万向钱潮"},
    {"code": "000878.SZ", "name": "云南铜业"},
    {"code": "002050.SZ", "name": "三花智控"},
    {"code": "002594.SZ", "name": "比亚迪"},
    {"code": "300229.SZ", "name": "拓尔思"},
    {"code": "300316.SZ", "name": "晶盛机电"},
    {"code": "300442.SZ", "name": "润泽科技"},
    {"code": "601600.SH", "name": "中国铝业"},
    {"code": "688795.SH", "name": "摩尔线程"},
]

# 港股列表 (yfinance格式)
hk_stocks = [
    {"code": "0285.HK", "name": "比亚迪电子"},
    {"code": "0700.HK", "name": "腾讯控股"},
    {"code": "9988.HK", "name": "阿里巴巴"},
]

start_date = "2022-01-01"
end_date = datetime.now().strftime("%Y-%m-%d")

print(f"开始拉取数据: {start_date} 至 {end_date}")
print("=" * 60)

all_data = {}

# ========== A股: 使用 baostock ==========
print("\n【A股 - baostock】")
lg = bs.login()
print(f"登录baostock: {lg.error_msg if lg.error_code != '0' else '成功'}")

for stock in a_stocks:
    code = stock["code"]
    name = stock["name"]
    
    try:
        # baostock 格式: sh.601600 或 sz.000559
        bs_code = code.lower().replace('.sh', '.sh').replace('.sz', '.sz')
        
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,code,open,high,low,close,volume",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3"  # 前复权
        )
        
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        
        if data_list:
            df = pd.DataFrame(data_list, columns=['date', 'code', 'open', 'high', 'low', 'close', 'volume'])
            df['stock_code'] = code.split('.')[0]
            df['stock_name'] = name
            df['market'] = code.split('.')[1]
            
            # 转换数值
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 保存
            filename = f"{code.split('.')[0]}_{name}.csv"
            filepath = os.path.join(data_dir, filename)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            
            all_data[code] = df
            print(f"✅ {code} {name}: {len(df)} 条记录")
        else:
            print(f"⚠️ {code} {name}: 无数据")
            
    except Exception as e:
        print(f"❌ {code} {name}: {str(e)[:50]}")

bs.logout()

# ========== 港股: 使用 yfinance ==========
print("\n【港股 - yfinance】")

for stock in hk_stocks:
    code = stock["code"]
    name = stock["name"]
    
    try:
        ticker = yf.Ticker(code)
        df = ticker.history(start=start_date, end=end_date)
        
        if df is not None and len(df) > 0:
            # 重置索引
            df = df.reset_index()
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]
            
            # 标准化列名
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
            
            # 选择需要的列
            df = df[['date', 'stock_code', 'stock_name', 'market', 'open', 'high', 'low', 'close', 'volume']]
            
            # 保存
            filename = f"{code.replace('.HK', '')}_{name}.csv"
            filepath = os.path.join(data_dir, filename)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            
            all_data[code] = df
            print(f"✅ {code} {name}: {len(df)} 条记录")
        else:
            print(f"⚠️ {code} {name}: 无数据")
            
    except Exception as e:
        print(f"❌ {code} {name}: {str(e)[:50]}")

# ========== 合并 ==========
print("\n" + "=" * 60)
if all_data:
    combined = pd.concat(all_data.values(), ignore_index=True)
    combined_path = os.path.join(data_dir, "all_stocks_combined.csv")
    combined.to_csv(combined_path, index=False, encoding='utf-8-sig')
    
    print(f"📊 成功: {len(all_data)}/12 只股票")
    print(f"📊 总计: {len(combined)} 条记录")
    print(f"📁 单股文件: {data_dir}")
    print(f"📁 合并文件: {combined_path}")
else:
    print("❌ 没有获取到任何数据")
