# -*- coding: utf-8 -*-
"""
中轴价格仓位控制法回测 - 报告生成模块
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
from datetime import datetime

def generate_report(summary_file: str = "backtest/results/backtest_summary.csv", 
                   output_dir: str = "backtest/results"):
    """生成回测报告"""
    
    if not os.path.exists(summary_file):
        print(f"[ERROR] 找不到汇总文件: {summary_file}")
        return None
    
    try:
        df = pd.read_csv(summary_file)
        if len(df) == 0:
            print("[ERROR] 汇总文件为空")
            return None
    except Exception as e:
        print(f"[ERROR] 读取汇总文件失败: {e}")
        return None
    
    # 设置中文字体
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei', 'Arial Unicode MS']
    plt.rcParams['axes.unicode_minus'] = False
    
    # 创建图表
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('Backtest Report: Axis Grid Strategy (2022.01 - 2026.03)', fontsize=14, fontweight='bold')
    
    # 图1: 各股票策略收益 vs 买入持有
    ax1 = axes[0, 0]
    x = range(len(df))
    width = 0.35
    ax1.bar([i - width/2 for i in x], df['strategy_return'], width, label='Strategy', color='#3498db')
    ax1.bar([i + width/2 for i in x], df['buy_hold_return'], width, label='Buy & Hold', color='#e74c3c')
    ax1.axhline(y=0, color='gray', linestyle='--', linewidth=0.8)
    ax1.set_xlabel('Stock')
    ax1.set_ylabel('Return (%)')
    ax1.set_title('Strategy vs Buy & Hold Return')
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{row['code']}" for _, row in df.iterrows()], rotation=45, ha='right')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)
    
    # 图2: 超额收益分布
    ax2 = axes[0, 1]
    colors = ['#27ae60' if x > 0 else '#e74c3c' for x in df['excess_return']]
    ax2.barh(range(len(df)), df['excess_return'], color=colors)
    ax2.axvline(x=0, color='gray', linestyle='--', linewidth=0.8)
    ax2.set_xlabel('Excess Return (%)')
    ax2.set_ylabel('Stock')
    ax2.set_title('Excess Return (Strategy - Buy\u0026Hold)')
    ax2.set_yticks(range(len(df)))
    ax2.set_yticklabels([f"{row['code']}" for _, row in df.iterrows()])
    ax2.grid(axis='x', alpha=0.3)
    
    # 图3: 交易次数分布
    ax3 = axes[1, 0]
    ax3.bar(range(len(df)), df['total_trades'], color='#9b59b6')
    ax3.set_xlabel('Stock')
    ax3.set_ylabel('Number of Trades')
    ax3.set_title('Total Trades per Stock')
    ax3.set_xticks(range(len(df)))
    ax3.set_xticklabels([f"{row['code']}" for _, row in df.iterrows()], rotation=45, ha='right')
    ax3.grid(axis='y', alpha=0.3)
    
    # 图4: 策略收益 vs 股价涨跌（散点图）
    ax4 = axes[1, 1]
    ax4.scatter(df['price_return'], df['strategy_return'], s=100, alpha=0.6, color='#3498db')
    for _, row in df.iterrows():
        ax4.annotate(row['code'], (row['price_return'], row['strategy_return']), 
                    fontsize=8, alpha=0.7)
    # 添加对角线（策略收益=股价涨跌）
    min_val = min(df['price_return'].min(), df['strategy_return'].min())
    max_val = max(df['price_return'].max(), df['strategy_return'].max())
    ax4.plot([min_val, max_val], [min_val, max_val], 'k--', alpha=0.3, label='Strategy = Price')
    ax4.set_xlabel('Price Change (%)')
    ax4.set_ylabel('Strategy Return (%)')
    ax4.set_title('Strategy Return vs Price Change')
    ax4.legend()
    ax4.grid(alpha=0.3)
    
    plt.tight_layout()
    chart_file = os.path.join(output_dir, f"backtest_charts_{datetime.now().strftime('%Y%m%d')}.png")
    plt.savefig(chart_file, dpi=150, bbox_inches='tight')
    print(f"[OK] 图表已保存: {chart_file}")
    plt.close()
    
    # 生成Markdown报告
    md_content = f"""# 中轴价格仓位控制法回测报告

**回测周期**: 2022.01 - 2026.03 (4年2个月)  
**策略规则**:
- 单股上限: A股50万 / 港股150万
- 仓位分配: 50%底仓(长期持有) + 50%浮仓(网格交易)
- 买入: 偏离中轴-8%买入浮仓20%，-16%再买20%
- 卖出: 偏离+8%卖出浮仓20%，+16%再卖20%

## 汇总结果

| 股票 | 市场 | 股价涨跌 | 策略收益 | 买入持有 | 超额收益 | 交易次数 |
|------|------|----------|----------|----------|----------|----------|
"""
    
    for _, row in df.iterrows():
        md_content += f"| {row['code']} {row['name']} | {row['market']} | {row['price_return']:.1f}% | {row['strategy_return']:.1f}% | {row['buy_hold_return']:.1f}% | {row['excess_return']:+.1f}% | {int(row['total_trades'])} |\n"
    
    md_content += f"""
## 统计指标

| 指标 | 数值 |
|------|------|
| 回测股票数 | {len(df)} |
| 平均策略收益 | {df['strategy_return'].mean():.1f}% |
| 平均买入持有 | {df['buy_hold_return'].mean():.1f}% |
| 平均超额收益 | {df['excess_return'].mean():.1f}% |
| 胜率(超额>0) | {(df['excess_return'] > 0).sum()}/{len(df)} ({(df['excess_return'] > 0).mean()*100:.0f}%) |
| 最大超额收益 | {df['excess_return'].max():.1f}% ({df.loc[df['excess_return'].idxmax(), 'code']}) |
| 最小超额收益 | {df['excess_return'].min():.1f}% ({df.loc[df['excess_return'].idxmin(), 'code']}) |
| 平均交易次数 | {df['total_trades'].mean():.1f} |

## 图表

![回测图表](backtest_charts_{datetime.now().strftime('%Y%m%d')}.png)

## 结论

"""
    
    # 自动生成结论
    avg_excess = df['excess_return'].mean()
    win_rate = (df['excess_return'] > 0).mean()
    
    if avg_excess > 5 and win_rate >= 0.5:
        md_content += f"""✅ **策略表现优秀**

- 平均超额收益 {avg_excess:.1f}%，胜率 {win_rate*100:.0f}%
- 中轴网格策略在回测期内显著跑赢买入持有
- 建议继续使用该策略

"""
    elif avg_excess > 0:
        md_content += f"""⚠️ **策略表现一般**

- 平均超额收益 {avg_excess:.1f}%，胜率 {win_rate*100:.0f}%
- 策略略优于买入持有，但优势不明显
- 建议优化参数或结合其他指标

"""
    else:
        md_content += f"""❌ **策略表现不佳**

- 平均超额收益 {avg_excess:.1f}%，胜率 {win_rate*100:.0f}%
- 策略未跑赢买入持有
- 建议重新评估策略参数或改用其他策略

"""
    
    md_content += f"""---
*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
    
    md_file = os.path.join(output_dir, f"backtest_report_{datetime.now().strftime('%Y%m%d')}.md")
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"[OK] 报告已保存: {md_file}")
    
    return md_file

if __name__ == "__main__":
    generate_report()
