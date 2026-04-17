# -*- coding: utf-8 -*-
"""
中轴价格仓位控制法回测 - 执行模块
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import json
from typing import Dict, List
from backtest.data_fetch import PORTFOLIO
from backtest.strategy import AxisGridStrategy, Trade

def load_stock_data(code: str, data_dir: str = "backtest/data") -> pd.DataFrame:
    """加载股票历史数据"""
    file_path = os.path.join(data_dir, f"{code}.csv")
    if not os.path.exists(file_path):
        return None
    
    df = pd.read_csv(file_path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df

def run_backtest(code: str, info: Dict, data_dir: str = "backtest/data") -> Dict:
    """对单只股票执行回测"""
    print(f"\n[BACKTEST] {code} {info['name']}...")
    
    # 加载数据
    df = load_stock_data(code, data_dir)
    if df is None or len(df) < 100:
        print(f"[SKIP] {code} 数据不足")
        return None
    
    # 初始化策略
    strategy = AxisGridStrategy(
        code=code,
        name=info['name'],
        market=info['market'],
        max_position=info['max_position']
    )
    
    # 获取回测起始日期（确保有足够历史数据计算中轴）
    start_idx = 90  # 前90天用于计算初始中轴
    
    trades = []
    daily_records = []
    
    # 遍历每个交易日
    for i in range(start_idx, len(df)):
        row = df.iloc[i]
        date = row['date']
        price = row['close']
        
        # 执行策略
        trade = strategy.execute(date, price, df)
        if trade:
            trades.append(trade)
            print(f"  {date.strftime('%Y-%m-%d')} {trade.action.upper()} {trade.shares}股 @ {trade.price:.2f} ({trade.reason})")
        
        # 记录每日状态
        axis_price = strategy.calculate_axis_price(df, date)
        deviation = strategy.get_deviation(price, axis_price) if axis_price else 0
        
        daily_records.append({
            'date': date,
            'price': price,
            'axis_price': axis_price,
            'deviation': deviation,
            'shares': strategy.position.total_shares,
            'market_value': strategy.position.total_shares * price,
            'cash_used': strategy.cash_used,
            'cash_released': strategy.cash_released,
        })
    
    # 获取最终结果
    final_price = df.iloc[-1]['close']
    summary = strategy.get_summary(final_price)
    
    # 计算买入持有对比
    first_price = df.iloc[start_idx]['close']
    buy_hold_shares = int(info['max_position'] * 0.5 / first_price)  # 只用50%资金对比（底仓）
    buy_hold_value = buy_hold_shares * final_price
    buy_hold_cost = buy_hold_shares * first_price
    
    summary['buy_hold_pnl'] = buy_hold_value - buy_hold_cost
    summary['buy_hold_return'] = (buy_hold_value - buy_hold_cost) / buy_hold_cost * 100 if buy_hold_cost > 0 else 0
    summary['strategy_return'] = summary['unrealized_pnl'] / summary['total_invested'] * 100 if summary['total_invested'] > 0 else 0
    summary['excess_return'] = summary['strategy_return'] - summary['buy_hold_return']
    summary['first_price'] = first_price
    summary['final_price'] = final_price
    summary['price_return'] = (final_price - first_price) / first_price * 100
    summary['trades'] = trades
    summary['daily_records'] = daily_records
    
    print(f"  回测完成: 交易{len(trades)}次, 策略收益{summary['strategy_return']:.1f}%, 买入持有{summary['buy_hold_return']:.1f}%")
    
    return summary

def run_all_backtests(data_dir: str = "backtest/data", output_dir: str = "backtest/results"):
    """执行所有持仓股的回测"""
    os.makedirs(output_dir, exist_ok=True)
    
    results = []
    
    for code, info in PORTFOLIO.items():
        result = run_backtest(code, info, data_dir)
        if result:
            results.append(result)
    
    # 保存结果
    summary_list = []
    for r in results:
        summary_list.append({
            'code': r['code'],
            'name': r['name'],
            'market': r['market'],
            'max_position': r['max_position'],
            'first_price': r['first_price'],
            'final_price': r['final_price'],
            'price_return': r['price_return'],
            'total_trades': r['total_trades'],
            'total_invested': r['total_invested'],
            'final_value': r['final_value'],
            'unrealized_pnl': r['unrealized_pnl'],
            'strategy_return': r['strategy_return'],
            'buy_hold_return': r['buy_hold_return'],
            'excess_return': r['excess_return'],
        })
    
    # 保存汇总表
    summary_df = pd.DataFrame(summary_list)
    summary_file = os.path.join(output_dir, "backtest_summary.csv")
    summary_df.to_csv(summary_file, index=False)
    print(f"\n[OK] 汇总结果已保存: {summary_file}")
    
    # 保存详细结果
    detail_file = os.path.join(output_dir, "backtest_detail.json")
    # 移除不可序列化的对象
    for r in results:
        r.pop('trades', None)
        r.pop('daily_records', None)
    with open(detail_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"[OK] 详细结果已保存: {detail_file}")
    
    return summary_df

if __name__ == "__main__":
    print("=" * 60)
    print("中轴价格仓位控制法回测")
    print("=" * 60)
    
    # 先获取数据
    from data_fetch import fetch_all_data
    fetch_all_data()
    
    # 执行回测
    results = run_all_backtests()
    
    # 打印汇总
    print("\n" + "=" * 60)
    print("回测结果汇总")
    print("=" * 60)
    print(results.to_string(index=False))
    
    # 统计
    print(f"\n总体统计:")
    print(f"  平均策略收益: {results['strategy_return'].mean():.1f}%")
    print(f"  平均买入持有: {results['buy_hold_return'].mean():.1f}%")
    print(f"  平均超额收益: {results['excess_return'].mean():.1f}%")
    print(f"  胜率(超额>0): {(results['excess_return'] > 0).sum()}/{len(results)} = {(results['excess_return'] > 0).mean()*100:.0f}%")
