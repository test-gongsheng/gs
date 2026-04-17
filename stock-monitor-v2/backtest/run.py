# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
中轴价格仓位控制法回测 - 一键运行脚本
"""
import sys
import os

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.data_fetch import fetch_all_data
from backtest.run_backtest import run_all_backtests
from backtest.report import generate_report

def main():
    print("=" * 70)
    print("  中轴价格仓位控制法回测系统")
    print("  策略: 底仓50% + 浮仓网格(-8%/-16%买入, +8%/+16%卖出)")
    print("  周期: 2022.01 - 2026.03 (4年2个月)")
    print("=" * 70)
    
    # 步骤1: 获取数据
    print("\n【步骤1】获取历史数据...")
    fetch_all_data()
    
    # 步骤2: 执行回测
    print("\n【步骤2】执行回测...")
    results = run_all_backtests()
    
    # 步骤3: 生成报告
    print("\n【步骤3】生成报告...")
    report_file = generate_report()
    
    print("\n" + "=" * 70)
    print("  回测完成!")
    print(f"  报告文件: {report_file}")
    print("=" * 70)

if __name__ == "__main__":
    main()
