#!/usr/bin/env python3
"""
持仓股每日分析报告生成器 V2
为每只持仓股生成详细分析报告，包括数据来源、分析逻辑、结论
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import load_data

REPORTS_DIR = os.path.join(os.path.dirname(__file__), 'reports')
ANALYSIS_FILE = os.path.join(REPORTS_DIR, 'portfolio_analysis_latest.json')

# 板块映射表（可以根据持仓股的行业属性维护）
SECTOR_MAP = {
    # 科技
    '00700': '互联网科技', 'BABA': '互联网科技', 'PDD': '互联网科技',
    '002050': '智能制造', '300124': '智能制造',
    # 新能源
    '002594': '新能源汽车', '300750': '新能源汽车',
    # 周期
    '000878': '有色金属', '000559': '汽车零部件',
    # 半导体
    '688981': '半导体', '688012': '半导体',
}

def get_stock_sector(code: str) -> str:
    """获取股票所属板块"""
    return SECTOR_MAP.get(code, '其他')


def analyze_stock_detailed(stock: Dict) -> Dict:
    """生成单只股票的详细分析报告"""
    code = stock['code']
    name = stock['name']
    market = stock['market']
    avg_cost = stock.get('avg_cost', 0)
    shares = stock.get('shares', 0)
    current_price = stock.get('current_price', 0)
    
    # 基础计算
    market_value = current_price * shares
    cost_value = avg_cost * shares
    pnl = market_value - cost_value
    pnl_percent = round(pnl / cost_value * 100, 2) if cost_value > 0 else 0
    
    # 中轴偏离计算
    pivot_price = avg_cost
    if pivot_price > 0:
        pivot_deviation = round((current_price - pivot_price) / pivot_price * 100, 2)
    else:
        pivot_deviation = 0
    
    # 确定技术状态
    technical_status = 'neutral'
    status_desc = '震荡'
    if pivot_deviation > 8:
        technical_status = 'overbought'
        status_desc = '超买'
    elif pivot_deviation > 3:
        technical_status = 'strong'
        status_desc = '强势'
    elif pivot_deviation < -8:
        technical_status = 'oversold'
        status_desc = '超卖'
    elif pivot_deviation < -3:
        technical_status = 'weak'
        status_desc = '弱势'
    
    # 触发价格计算
    trigger_buy = round(pivot_price * 0.92, 2)
    trigger_sell = round(pivot_price * 1.08, 2)
    
    # 生成详细分析内容
    analysis_detail = generate_stock_analysis_detail(
        name, code, market, current_price, avg_cost, 
        pivot_deviation, pnl, pnl_percent, technical_status,
        trigger_buy, trigger_sell
    )
    
    return {
        'code': code,
        'name': name,
        'market': market,
        'sector': get_stock_sector(code),
        'current_price': current_price,
        'avg_cost': avg_cost,
        'pivot_price': pivot_price,
        'pivot_deviation': pivot_deviation,
        'shares': shares,
        'market_value': round(market_value, 2),
        'pnl': round(pnl, 2),
        'pnl_percent': pnl_percent,
        'technical_status': technical_status,
        'status_desc': status_desc,
        'status_icon': {
            'overbought': '⚠️', 'strong': '🟢', 'neutral': '⚪',
            'weak': '🔴', 'oversold': '💡'
        }.get(technical_status, '⚪'),
        'trigger_buy': trigger_buy,
        'trigger_sell': trigger_sell,
        'action_suggestion': {
            'overbought': '考虑减仓',
            'strong': '持有观察',
            'neutral': '正常持有',
            'weak': '关注支撑',
            'oversold': '关注买入'
        }.get(technical_status, '正常持有'),
        # 详细分析内容
        'analysis': analysis_detail
    }


def generate_stock_analysis_detail(name: str, code: str, market: str, 
                                   current_price: float, avg_cost: float,
                                   pivot_deviation: float, pnl: float, 
                                   pnl_percent: float, status: str,
                                   trigger_buy: float, trigger_sell: float) -> Dict:
    """生成单只股票的详细分析内容"""
    
    # 1. 数据来源
    data_sources = [
        f"**持仓成本**: ¥{avg_cost:.2f}（您的实际买入均价）",
        f"**当前价格**: ¥{current_price:.2f}（{market}实时行情）",
        f"**中轴价格**: ¥{avg_cost:.2f}（基于持仓成本）",
        f"**触发价格**: 买入≤¥{trigger_buy} / 卖出≥¥{trigger_sell}（中轴±8%）",
    ]
    
    if market == 'A股':
        data_sources.append("**行情数据**: 东方财富/akshare实时数据")
    else:
        data_sources.append("**行情数据**: 港股实时行情")
    
    # 2. 分析逻辑
    analysis_logic = []
    
    # 中轴偏离分析
    if abs(pivot_deviation) < 3:
        analysis_logic.append(
            f"**中轴偏离**: 当前价格偏离中轴{pivot_deviation:+.2f}%，处于±3%正常震荡区间，"
            f"符合预期波动范围，无需特殊操作。"
        )
    elif pivot_deviation > 0:
        analysis_logic.append(
            f"**中轴偏离**: 当前价格高于中轴{pivot_deviation:+.2f}%，处于上涨趋势，"
            f"偏离度{abs(pivot_deviation):.1f}%，"
        )
        if pivot_deviation > 8:
            analysis_logic.append(
                f"已超过+8%卖出触发线（¥{trigger_sell}），建议考虑减仓锁定利润。"
            )
        else:
            analysis_logic.append(
                f"距离+8%卖出触发线（¥{trigger_sell}）还有{((trigger_sell-current_price)/current_price*100):.1f}%空间。"
            )
    else:
        analysis_logic.append(
            f"**中轴偏离**: 当前价格低于中轴{pivot_deviation:.2f}%，处于下跌趋势，"
            f"偏离度{abs(pivot_deviation):.1f}%，"
        )
        if pivot_deviation < -8:
            analysis_logic.append(
                f"已跌破-8%买入触发线（¥{trigger_buy}），可关注加仓机会。"
            )
        else:
            analysis_logic.append(
                f"距离-8%买入触发线（¥{trigger_buy}）还有{((current_price-trigger_buy)/current_price*100):.1f}%空间。"
            )
    
    # 盈亏分析
    if pnl > 0:
        analysis_logic.append(
            f"**盈亏状况**: 当前浮盈¥{pnl:,.2f}（+{pnl_percent}%），"
            f"建议根据中轴偏离度决定是否获利了结。"
        )
    elif pnl < 0:
        analysis_logic.append(
            f"**盈亏状况**: 当前浮亏¥{abs(pnl):,.2f}（{pnl_percent}%），"
            f"建议根据中轴偏离度和基本面判断是否补仓。"
        )
    else:
        analysis_logic.append("**盈亏状况**: 当前盈亏平衡。")
    
    # 3. 结论与建议
    if status == 'overbought':
        conclusion = {
            'title': '⚠️ 超买区 - 建议减仓',
            'content': [
                f"{name}当前处于超买状态，价格偏离中轴成本+8%以上。",
                "根据中轴价格策略，这是网格策略的卖出点。",
                f"建议：考虑卖出部分仓位（如1/4或1/3），锁定利润。",
                "减仓后等待价格回落至中轴附近再考虑接回。"
            ]
        }
    elif status == 'strong':
        conclusion = {
            'title': '🟢 强势区 - 持有观察',
            'content': [
                f"{name}表现强势，价格高于中轴但尚未达到卖出触发线。",
                "可继续持有，享受上涨收益。",
                f"建议：设置卖出预警价为¥{trigger_sell}，达到后考虑减仓。",
                "同时关注是否出现放量滞涨等见顶信号。"
            ]
        }
    elif status == 'oversold':
        conclusion = {
            'title': '💡 超卖区 - 关注买入',
            'content': [
                f"{name}当前处于超卖状态，价格跌破中轴成本8%以上。",
                "根据中轴价格策略，这是网格策略的买入点。",
                f"建议：关注买入机会，可考虑分批加仓。",
                "买入后等待价格反弹至中轴附近。"
            ]
        }
    elif status == 'weak':
        conclusion = {
            'title': '🔴 弱势区 - 关注支撑',
            'content': [
                f"{name}相对弱势，价格低于中轴但尚未达到买入触发线。",
                "建议关注是否继续下跌，或出现企稳信号。",
                f"若跌破¥{trigger_buy}则进入超卖区，可考虑加仓。",
                "同时关注基本面是否有变化导致持续走弱。"
            ]
        }
    else:
        conclusion = {
            'title': '⚪ 震荡区 - 正常持有',
            'content': [
                f"{name}价格在正常震荡区间，偏离中轴±3%以内。",
                "符合预期波动范围，保持当前仓位。",
                "建议：继续监控，等待中轴偏离信号触发。",
                f"上方阻力位¥{trigger_sell}，下方支撑位¥{trigger_buy}。"
            ]
        }
    
    return {
        'data_sources': data_sources,
        'analysis_logic': analysis_logic,
        'conclusion': conclusion,
        'update_time': datetime.now().strftime('%Y-%m-%d %H:%M')
    }


def analyze_sector(stocks: List[Dict]) -> Dict:
    """分析板块情况"""
    sector_stats = {}
    
    for stock in stocks:
        sector = stock.get('sector', '其他')
        if sector not in sector_stats:
            sector_stats[sector] = {
                'stocks': [],
                'total_value': 0,
                'total_cost': 0,
                'strong': 0, 'neutral': 0, 'weak': 0,
                'oversold': 0, 'overbought': 0
            }
        
        sector_stats[sector]['stocks'].append(stock['code'])
        sector_stats[sector]['total_value'] += stock['market_value']
        sector_stats[sector]['total_cost'] += stock['avg_cost'] * stock['shares']
        sector_stats[sector][stock['technical_status']] += 1
    
    # 生成板块分析
    sector_analysis = []
    for sector, stats in sector_stats.items():
        pnl = stats['total_value'] - stats['total_cost']
        pnl_percent = round(pnl / stats['total_cost'] * 100, 2) if stats['total_cost'] > 0 else 0
        
        # 判断板块整体状态
        total = len(stats['stocks'])
        if stats['overbought'] >= total * 0.3:
            status = '⚠️ 过热'
        elif stats['oversold'] >= total * 0.3:
            status = '💡 超卖'
        elif stats['strong'] > stats['weak']:
            status = '🟢 强势'
        elif stats['weak'] > stats['strong']:
            status = '🔴 弱势'
        else:
            status = '⚪ 震荡'
        
        sector_analysis.append({
            'name': sector,
            'stock_count': total,
            'market_value': round(stats['total_value'], 2),
            'pnl': round(pnl, 2),
            'pnl_percent': pnl_percent,
            'status': status,
            'distribution': {
                'overbought': stats['overbought'],
                'strong': stats['strong'],
                'neutral': stats['neutral'],
                'weak': stats['weak'],
                'oversold': stats['oversold']
            }
        })
    
    # 按市值排序
    sector_analysis.sort(key=lambda x: x['market_value'], reverse=True)
    return sector_analysis


def generate_portfolio_analysis_v2() -> Dict:
    """生成完整的持仓分析报告V2"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始生成持仓分析报告V2...")
    
    data = load_data()
    stocks = data.get('stocks', [])
    
    report_date = datetime.now().strftime('%Y-%m-%d')
    
    # 分析每只股票
    stock_analyses = []
    total_market_value = 0
    total_cost = 0
    
    for stock in stocks:
        analysis = analyze_stock_detailed(stock)
        stock_analyses.append(analysis)
        total_market_value += analysis['market_value']
        total_cost += stock['avg_cost'] * stock['shares']
    
    # 计算总体盈亏
    total_pnl = total_market_value - total_cost
    total_pnl_percent = round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0
    
    # 状态统计
    status_counts = {'overbought': 0, 'strong': 0, 'neutral': 0, 'weak': 0, 'oversold': 0}
    alerts = []
    highlights = []
    
    for analysis in stock_analyses:
        status = analysis['technical_status']
        status_counts[status] += 1
        
        deviation = analysis['pivot_deviation']
        name = analysis['name']
        
        if status == 'overbought':
            alerts.append({
                'type': 'warning',
                'stock': name,
                'code': analysis['code'],
                'deviation': deviation,
                'message': f'偏离中轴+{deviation}%，进入超买区',
                'action': '考虑减仓'
            })
        elif status == 'oversold':
            highlights.append({
                'type': 'opportunity',
                'stock': name,
                'code': analysis['code'],
                'deviation': deviation,
                'message': f'偏离中轴{deviation}%，进入超卖区',
                'action': '关注买入'
            })
    
    # 板块分析
    sector_analysis = analyze_sector(stock_analyses)
    
    # 生成报告
    report = {
        'report_date': report_date,
        'report_type': 'portfolio_daily_analysis_v2',
        'version': '2.0',
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
            'buy_opportunities_count': status_counts.get('oversold', 0),
            'sell_signals_count': status_counts.get('overbought', 0)
        },
        'stock_analyses': stock_analyses,
        'sector_analysis': sector_analysis,
        'alerts': alerts,
        'highlights': highlights
    }
    
    return report


def calculate_health_score(status_counts: Dict) -> int:
    """计算健康度评分"""
    total = sum(status_counts.values())
    if total == 0:
        return 50
    
    score = (
        status_counts.get('strong', 0) * 20 +
        status_counts.get('overbought', 0) * 15 +
        status_counts.get('neutral', 0) * 12 +
        status_counts.get('oversold', 0) * 10 +
        status_counts.get('weak', 0) * 5
    ) / total
    
    return min(100, max(0, int(score * 5)))


def save_report(report: Dict):
    """保存报告"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    
    with open(ANALYSIS_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    backup_file = os.path.join(REPORTS_DIR, f'portfolio_analysis_{report["report_date"]}.json')
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 报告已保存: {ANALYSIS_FILE}")


def main():
    try:
        report = generate_portfolio_analysis_v2()
        save_report(report)
        
        # 打印摘要
        print("\n" + "="*60)
        print(f"📊 持仓分析报告V2 ({report['report_date']})")
        print("="*60)
        summary = report['summary']
        print(f"🟡 健康度: {summary['health_score']}/100")
        print(f"📈 盈亏: ¥{summary['total_pnl']:,.2f} ({summary['total_pnl_percent']}%)")
        print(f"💰 市值: ¥{summary['total_market_value']:,.2f}")
        print(f"\n📊 板块分布:")
        for sector in report['sector_analysis'][:3]:
            print(f"  {sector['status']} {sector['name']}: {sector['stock_count']}只")
        print(f"\n📝 已生成 {len(report['stock_analyses'])} 只股票详细分析")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"❌ 失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
