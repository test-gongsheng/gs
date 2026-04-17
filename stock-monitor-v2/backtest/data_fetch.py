# -*- coding: utf-8 -*-
"""
中轴价格仓位控制法回测 - 数据获取模块 (本地/模拟数据版本)
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# 持仓股票列表
PORTFOLIO = {
    "000559": {"name": "万向钱潮", "market": "A股", "max_position": 500000},
    "000878": {"name": "云南铜业", "market": "A股", "max_position": 500000},
    "002050": {"name": "三花智控", "market": "A股", "max_position": 500000},
    "002594": {"name": "比亚迪", "market": "A股", "max_position": 500000},
    "300229": {"name": "拓尔思", "market": "A股", "max_position": 500000},
    "300316": {"name": "晶盛机电", "market": "A股", "max_position": 500000},
    "300442": {"name": "润泽科技", "market": "A股", "max_position": 500000},
    "601600": {"name": "中国铝业", "market": "A股", "max_position": 500000},
    "688795": {"name": "摩尔线程", "market": "A股", "max_position": 500000},
    "00700": {"name": "腾讯控股", "market": "港股", "max_position": 1500000},
    "00285": {"name": "比亚迪电子", "market": "港股", "max_position": 1500000},
    "09988": {"name": "阿里巴巴", "market": "港股", "max_position": 1500000},
}

def generate_mock_data(code: str, start_date: str = "2022-01-01", end_date: str = "2026-03-31", 
                       base_price: float = 100, volatility: float = 0.02) -> pd.DataFrame:
    """
    生成模拟股价数据（带趋势和波动的随机游走）
    用于验证策略逻辑
    """
    # 生成交易日列表
    date_range = pd.date_range(start=start_date, end=end_date, freq='B')  # B = business days
    
    # 为不同股票设置不同的特征
    stock_params = {
        # A股
        "000559": {"base": 15, "vol": 0.025, "trend": 0.0001},
        "000878": {"base": 18, "vol": 0.03, "trend": 0.0002},
        "002050": {"base": 45, "vol": 0.028, "trend": 0.0003},
        "002594": {"base": 100, "vol": 0.025, "trend": 0.0005},
        "300229": {"base": 20, "vol": 0.035, "trend": 0.0001},
        "300316": {"base": 40, "vol": 0.03, "trend": 0.0002},
        "300442": {"base": 80, "vol": 0.032, "trend": 0.0004},
        "601600": {"base": 12, "vol": 0.022, "trend": 0.0001},
        "688795": {"base": 550, "vol": 0.04, "trend": 0.0003},
        # 港股
        "00700": {"base": 400, "vol": 0.025, "trend": 0.0002},
        "00285": {"base": 25, "vol": 0.03, "trend": 0.0001},
        "09988": {"base": 100, "vol": 0.028, "trend": 0.0002},
    }
    
    params = stock_params.get(code, {"base": base_price, "vol": volatility, "trend": 0})
    
    # 生成价格序列（几何布朗运动 + 趋势）
    np.random.seed(hash(code) % 2**32)  # 用code作为随机种子保证可重复
    
    returns = np.random.normal(params["trend"], params["vol"], len(date_range))
    
    # 添加一些周期性波动（模拟市场周期）
    cycle = 0.05 * np.sin(np.arange(len(date_range)) * 2 * np.pi / 252)  # 年度周期
    returns += cycle / 252
    
    # 计算价格
    prices = params["base"] * np.exp(np.cumsum(returns))
    
    # 生成OHLCV数据
    df = pd.DataFrame({
        "date": date_range,
        "close": prices,
    })
    
    # 从收盘价生成其他价格
    df["open"] = df["close"] * (1 + np.random.normal(0, 0.005, len(df)))
    df["high"] = df[["open", "close"]].max(axis=1) * (1 + np.random.uniform(0, 0.01, len(df)))
    df["low"] = df[["open", "close"]].min(axis=1) * (1 - np.random.uniform(0, 0.01, len(df)))
    df["volume"] = np.random.uniform(1000000, 10000000, len(df))
    
    return df[["date", "open", "high", "low", "close", "volume"]]

def fetch_all_data(cache_dir: str = "backtest/data"):
    """生成所有持仓股的模拟数据"""
    os.makedirs(cache_dir, exist_ok=True)
    
    for code, info in PORTFOLIO.items():
        cache_file = os.path.join(cache_dir, f"{code}.csv")
        
        # 检查缓存
        if os.path.exists(cache_file):
            df = pd.read_csv(cache_file)
            if len(df) > 100:
                print(f"[CACHE] {code} {info['name']} 数据已存在 ({len(df)}条)")
                continue
        
        print(f"[GEN] 生成 {code} {info['name']} 模拟数据...")
        
        df = generate_mock_data(code)
        df.to_csv(cache_file, index=False)
        print(f"[OK] {code} 生成 {len(df)} 条数据")
    
    print("\n[NOTE] 使用的是模拟数据，用于验证策略逻辑")
    print("       实际回测需要真实历史数据")

if __name__ == "__main__":
    fetch_all_data()
