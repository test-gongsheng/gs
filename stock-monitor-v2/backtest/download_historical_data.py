"""
东方财富历史数据下载脚本
在你的本地电脑上运行，下载12只持仓股的日K数据
"""
import requests
import pandas as pd
from datetime import datetime
import os
import time

# 持仓股票列表
STOCKS = [
    # A股 (代码, 名称, 市场)
    ("000559", "万向钱潮", "A股", "0"),  # 0=深, 1=沪
    ("000878", "云南铜业", "A股", "0"),
    ("002050", "三花智控", "A股", "0"),
    ("002594", "比亚迪", "A股", "0"),
    ("300229", "拓尔思", "A股", "0"),
    ("300316", "晶盛机电", "A股", "0"),
    ("300442", "润泽科技", "A股", "0"),
    ("601600", "中国铝业", "A股", "1"),
    ("688795", "摩尔线程", "A股", "1"),
    # 港股 (港股通代码, 名称, 市场, 特殊标记)
    ("00700", "腾讯控股", "港股", "hk"),
    ("00285", "比亚迪电子", "港股", "hk"),
    ("09988", "阿里巴巴", "港股", "hk"),
]

def download_a_stock(code, market_code, name, output_dir="backtest_data"):
    """下载A股历史数据"""
    os.makedirs(output_dir, exist_ok=True)
    
    url = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": f"{market_code}.{code}",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",  # 日K
        "fqt": "1",    # 前复权
        "end": "20500101",
        "lmt": "1200", # 获取1200条（约5年）
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        
        if data.get("data") and data["data"].get("klines"):
            klines = data["data"]["klines"]
            rows = []
            for line in klines:
                # 日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
                parts = line.split(",")
                rows.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                })
            
            df = pd.DataFrame(rows)
            
            # 过滤时间范围
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["date"] >= "2022-01-01") & (df["date"] <= "2026-03-31")]
            df = df.sort_values("date")
            
            output_file = os.path.join(output_dir, f"{code}.csv")
            df.to_csv(output_file, index=False)
            print(f"✓ {code} {name}: {len(df)}条数据")
            return True
    except Exception as e:
        print(f"✗ {code} {name}: 失败 - {e}")
    return False

def download_hk_stock(code, name, output_dir="backtest_data"):
    """下载港股历史数据"""
    os.makedirs(output_dir, exist_ok=True)
    
    url = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": f"116.{code}",  # 116表示港股
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "end": "20500101",
        "lmt": "1200",
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        
        if data.get("data") and data["data"].get("klines"):
            klines = data["data"]["klines"]
            rows = []
            for line in klines:
                parts = line.split(",")
                rows.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": float(parts[5]),
                })
            
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["date"] >= "2022-01-01") & (df["date"] <= "2026-03-31")]
            df = df.sort_values("date")
            
            output_file = os.path.join(output_dir, f"{code}.csv")
            df.to_csv(output_file, index=False)
            print(f"✓ {code} {name}: {len(df)}条数据")
            return True
    except Exception as e:
        print(f"✗ {code} {name}: 失败 - {e}")
    return False

def main():
    print("=" * 60)
    print("中轴价格策略回测 - 历史数据下载")
    print("=" * 60)
    print()
    
    success_count = 0
    
    for code, name, market, market_code in STOCKS:
        if market == "A股":
            if download_a_stock(code, market_code, name):
                success_count += 1
        else:
            if download_hk_stock(code, name):
                success_count += 1
        time.sleep(0.5)  # 避免请求过快
    
    print()
    print("=" * 60)
    print(f"下载完成: {success_count}/{len(STOCKS)} 只股票")
    print("数据保存在: backtest_data/ 目录")
    print("=" * 60)
    
    if success_count == len(STOCKS):
        print("\n下一步:")
        print("1. 将 backtest_data/ 目录压缩")
        print("2. 上传到服务器 stock-monitor-v2/backtest/data/")
        print("3. 运行: python3 backtest/run.py")

if __name__ == "__main__":
    main()
