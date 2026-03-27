#!/usr/bin/env python3
"""
持仓股每日分析报告生成器 (MVP版本 - 简化版)
结合中轴价格策略生成每日持仓健康度分析
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import load_data

# 报告输出路径
REPORTS_DIR = os.path.join(os.path.dirname(__file__), 'reports')
ANALYSIS_FILE = os.path.join(REPORTS_DIR, 'portfolio_analysis_latest.json')


def analyze_stock(stock: Dict) -> Dict:
    """分析单只股票的中轴价格偏离情况"""
    code = stock['code']
    name = stock['name']
    market = stock['market']
    avg_cost = stock.get('avg_cost', 0)
    shares = stock.get('shares', 0)
    current_price = stock.get('current_price', 0)
    
    # 使用持仓成本作为中轴价格
    pivot_price = avg_cost
    
    # 计算与中轴的偏离度
    if pivot_price > 0:
        pivot_deviation = round((current_price - pivot_price) / pivot_price * 100, 2)
    else:
        pivot_deviation = 0
    
    # 计算浮动盈亏
    market_value = current_price * shares
    cost_value = avg_cost * shares
    pnl = market_value - cost_value
    pnl_percent = round(pnl / cost_value * 100, 2) if cost_value > 0 else 0
    
    # 根据中轴偏离判断技术状态
    # -8% ~ +8% 为正常区间
    technical_status = 'neutral'
    if pivot_deviation > 8:
        technical_status = 'overbought'  # 超买，考虑减仓
    elif pivot_deviation > 3:
        technical_status = 'strong'  # 强势
    elif pivot_deviation < -8:
        technical_status = 'oversold'  # 超卖，考虑加仓
    elif pivot_deviation < -3:
        technical_status = 'weak'  # 弱势
    
    # 计算距离触发买入/卖出的距离
    trigger_buy = round(pivot_price * 0.92, 2)  # -8% 买入触发
    trigger_sell = round(pivot_price * 1.08, 2)  # +8% 卖出触发
    distance_to_buy = round((current_price - trigger_buy) / trigger_buy * 100, 2) if trigger_buy > 0 else 0
    distance_to_sell = round((current_price - trigger_sell) / trigger_sell * 100, 2) if trigger_sell > 0 else 0
    
    return {
        'code': code,
        'name': name,
        'market': market,
        'current_price': current_price,
        'avg_cost': avg_cost,
        'pivot_price': pivot_price,
        'pivot_deviation': pivot_deviation,
        'trigger_buy': trigger_buy,
        'trigger_sell': trigger_sell,
        'distance_to_buy': distance_to_buy,
        'distance_to_sell': distance_to_sell,
        'shares': shares,
        'market_value': round(market_value, 2),
        'pnl': round(pnl, 2),
        'pnl_percent': pnl_percent,
        'technical_status': technical_status,
        'status_text': {
            'overbought': '⚠️ 超买区',
            'strong': '🟢 强势',
            'neutral': '⚪ 震荡',
            'weak': '🔴 弱势',
            'oversold': '💡 超卖区'
        }.get(technical_status, '⚪ 震荡'),
        'action_suggestion': {
            'overbought': '考虑减仓',
            'strong': '持有观察',
            'neutral': '正常持有',
            'weak': '关注支撑',
            'oversold': '关注买入'
        }.get(technical_status, '正常持有')
    }


def generate_portfolio_analysis() -> Dict:
    """生成持仓组合分析报告"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始生成持仓分析报告...")
    
    # 加载持仓数据
    data = load_data()
    stocks = data.get('stocks', [])
    portfolio = data.get('portfolio', {})
    
    report_date = datetime.now().strftime('%Y-%m-%d')
    
    # 分析每只股票
    stock_analyses = []
    total_market_value = 0
    total_cost = 0
    
    for stock in stocks:
        analysis = analyze_stock(stock)
        stock_analyses.append(analysis)
        
        total_market_value += analysis['market_value']
        total_cost += stock['avg_cost'] * stock['shares']
    
    # 计算组合整体盈亏
    total_pnl = total_market_value - total_cost
    total_pnl_percent = round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0
    
    # 按技术状态分类统计
    status_counts = {'overbought': 0, 'strong': 0, 'neutral': 0, 'weak': 0, 'oversold': 0}
    
    alerts = []
    highlights = []
    buy_opportunities = []
    sell_signals = []
    
    for analysis in stock_analyses:
        status = analysis['technical_status']
        status_counts[status] = status_counts.get(status, 0) + 1
        
        deviation = analysis['pivot_deviation']
        name = analysis['name']
        code = analysis['code']
        
        # 生成各类信号
        if status == 'overbought':
            sell_signals.append({
                'stock': name,
                'code': code,
                'deviation': deviation,
                'current_price': analysis['current_price'],
                'trigger_sell': analysis['trigger_sell'],
                'message': f'偏离中轴+{deviation}%，建议考虑减仓',
                'priority': 'high'
            })
            alerts.append({
                'type': 'warning',
                'stock': name,
                'code': code,
                'message': f'偏离中轴+{deviation}%，进入超买区',
                'action': '考虑减仓'
            })
        elif status == 'oversold':
            buy_opportunities.append({
                'stock': name,
                'code': code,
                'deviation': deviation,
                'current_price': analysis['current_price'],
                'trigger_buy': analysis['trigger_buy'],
                'message': f'偏离中轴{deviation}%，关注买入机会',
                'priority': 'medium'
            })
            highlights.append({
                'type': 'opportunity',
                'stock': name,
                'code': code,
                'message': f'偏离中轴{deviation}%，进入超卖区，关注买入',
                'action': '关注买入'
            })
        elif status == 'strong':
            highlights.append({
                'type': 'positive',
                'stock': name,
                'code': code,
                'message': f'偏离中轴+{deviation}%，表现强势',
                'action': '持有'
            })
        elif status == 'weak':
            alerts.append({
                'type': 'attention',
                'stock': name,
                'code': code,
                'message': f'偏离中轴{deviation}%，相对弱势',
                'action': '关注支撑'
            })
    
    # 生成报告
    report = {
        'report_date': report_date,
        'report_type': 'portfolio_daily_analysis',
        'version': '1.0',
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'strategy_note': '基于中轴价格±8%区间策略',
        'summary': {
            'total_stocks': len(stocks),
            'total_market_value': round(total_market_value, 2),
            'total_cost': round(total_cost, 2),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_percent': total_pnl_percent,
            'status_distribution': status_counts,
            'health_score': calculate_health_score(status_counts),
            'buy_opportunities_count': len(buy_opportunities),
            'sell_signals_count': len(sell_signals)
        },
        'stock_analyses': stock_analyses,
        'buy_opportunities': buy_opportunities,
        'sell_signals': sell_signals,
        'alerts': alerts,
        'highlights': highlights,
        'recommendations': generate_recommendations(stock_analyses, status_counts, buy_opportunities, sell_signals)
    }
    
    return report


def calculate_health_score(status_counts: Dict) -> int:
    """计算组合健康度评分 (0-100)"""
    total = sum(status_counts.values())
    if total == 0:
        return 50
    
    # 加权计算
    # 强势和超买（有利润）给高分，超卖（有机会）给中等分，弱势给低分
    score = (
        status_counts.get('strong', 0) * 20 +      # 强势：20分
        status_counts.get('overbought', 0) * 15 +  # 超买（有盈利）：15分
        status_counts.get('neutral', 0) * 12 +     # 震荡：12分
        status_counts.get('oversold', 0) * 10 +    # 超卖（有机会）：10分
        status_counts.get('weak', 0) * 5           # 弱势：5分
    ) / total
    
    return min(100, max(0, int(score * 5)))  # 映射到0-100


def generate_recommendations(analyses: List[Dict], status_counts: Dict, buy_ops: List, sell_sigs: List) -> List[Dict]:
    """生成操作建议"""
    recommendations = []
    
    # 买入机会建议
    if buy_ops:
        stocks_str = '、'.join([s['stock'] for s in buy_ops[:3]])
        recommendations.append({
            'type': 'buy',
            'priority': 'medium',
            'title': '💡 买入机会',
            'content': f'{stocks_str}等跌破中轴8%以上，可关注加仓机会（网格策略买入点）',
            'count': len(buy_ops)
        })
    
    # 卖出信号建议
    if sell_sigs:
        stocks_str = '、'.join([s['stock'] for s in sell_sigs[:3]])
        recommendations.append({
            'type': 'sell',
            'priority': 'high',
            'title': '⚠️ 减仓提示',
            'content': f'{stocks_str}等涨超中轴8%以上，建议考虑减仓锁定利润（网格策略卖出点）',
            'count': len(sell_sigs)
        })
    
    # 整体仓位建议
    if status_counts.get('overbought', 0) >= 3:
        recommendations.append({
            'type': 'position',
            'priority': 'high',
            'title': '📊 仓位管理',
            'content': '多只股票进入超买区，建议整体仓位控制在70%以下，预留资金应对回调'
        })
    elif status_counts.get('oversold', 0) >= 3:
        recommendations.append({
            'type': 'position',
            'priority': 'medium',
            'title': '📊 仓位管理',
            'content': '多只股票进入超卖区，市场可能存在机会，可适当提高仓位进行左侧布局'
        })
    
    # 平衡建议
    if not buy_ops and not sell_sigs:
        recommendations.append({
            'type': 'hold',
            'priority': 'low',
            'title': '⏸️ 持仓观察',
            'content': '当前持仓大部分处于正常区间，建议按兵不动，等待中轴偏离信号触发'
        })
    
    return recommendations


def save_report(report: Dict):
    """保存报告到文件"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    # 保存最新报告
    with open(ANALYSIS_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    # 保存历史备份
    backup_file = os.path.join(REPORTS_DIR, f'portfolio_analysis_{report["report_date"]}.json')
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 报告已保存: {ANALYSIS_FILE}")
    print(f"💾 备份已保存: {backup_file}")


def main():
    """主函数"""
    try:
        report = generate_portfolio_analysis()
        save_report(report)
        
        # 打印摘要
        print("\n" + "="*60)
        print(f"📊 持仓分析报告 ({report['report_date']})")
        print("="*60)
        summary = report['summary']
        
        # 健康度颜色
        health = summary['health_score']
        health_icon = '🟢' if health >= 70 else '🟡' if health >= 50 else '🔴'
        print(f"{health_icon} 健康度评分: {health}/100")
        
        # 盈亏
        pnl = summary['total_pnl']
        pnl_icon = '📈' if pnl >= 0 else '📉'
        print(f"{pnl_icon} 总盈亏: ¥{pnl:,.2f} ({summary['total_pnl_percent']}%)")
        print(f"💰 总市值: ¥{summary['total_market_value']:,.2f}")
        
        # 技术分布
        print(f"\n📈 技术状态分布:")
        print(f"  🟢 强势(+3~8%):   {summary['status_distribution'].get('strong', 0)}只")
        print(f"  ⚪ 震荡(±3%):     {summary['status_distribution'].get('neutral', 0)}只")
        print(f"  🔴 弱势(-3~-8%):  {summary['status_distribution'].get('weak', 0)}只")
        print(f"  💡 超卖(<-8%):    {summary['status_distribution'].get('oversold', 0)}只 → 买入机会")
        print(f"  ⚠️ 超买(>+8%):    {summary['status_distribution'].get('overbought', 0)}只 → 减仓信号")
        
        # 信号提示
        if summary['buy_opportunities_count'] > 0:
            print(f"\n💡 买入机会: {summary['buy_opportunities_count']}只股票跌破中轴8%")
        if summary['sell_signals_count'] > 0:
            print(f"\n⚠️ 减仓信号: {summary['sell_signals_count']}只股票涨超中轴8%")
        
        # 操作建议
        if report['recommendations']:
            print(f"\n📋 操作建议:")
            for i, rec in enumerate(report['recommendations'][:3], 1):
                print(f"  {i}. [{rec['title']}] {rec['content'][:50]}...")
        
        # 需要关注的股票
        if report['alerts']:
            print(f"\n⚠️ 需关注 ({len(report['alerts'])}只):")
            for alert in report['alerts'][:3]:
                print(f"  • {alert['stock']}: {alert['message']}")
        
        print("="*60)
        return True
        
    except Exception as e:
        print(f"❌ 生成报告失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
