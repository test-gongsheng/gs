# -*- coding: utf-8 -*-
"""
组合综合研判模块
三层结构：
  1. 个股层：综合研判(tactics) + 事件分析(events)
  2. 组合层：驱动力拆解 / 结构矛盾 / 明日验证点
  3. 叙述层：把数字翻译成"发生了什么、为什么、怎么办"
设计原则：规则驱动、可复现，每天的文字从当天数据长出来，不是模板填空。
"""
import json
import os
import time
from typing import Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')


# ========== 个股层 ==========

def enrich_stock_tactics(stock_analysis: Dict, kline: List[Dict]) -> List[str]:
    """个股综合研判（调用 tactics 模块）"""
    try:
        from tactics import generate_position_tactics
        stock_record = {
            'code': stock_analysis.get('code', ''),
            'name': stock_analysis.get('name', ''),
            'avg_cost': stock_analysis.get('avg_cost', 0),
            'shares': stock_analysis.get('shares', 0),
            'current_price': stock_analysis.get('current_price', 0),
        }
        return generate_position_tactics(stock_record, kline)
    except Exception as e:
        print(f"[Synthesis] tactics {stock_analysis.get('code')} 失败: {e}")
        return []


def enrich_stock_events(stock_code: str) -> List[str]:
    """个股事件分析（读本地缓存，无网络请求）"""
    try:
        from event_tracker import format_event_for_report
        return format_event_for_report(stock_code)
    except Exception as e:
        print(f"[Synthesis] events {stock_code} 失败: {e}")
        return []


# ========== 组合层 ==========

def load_prev_report(today_str: str) -> Optional[Dict]:
    """加载上一个交易日的报告"""
    import glob
    files = sorted(glob.glob(os.path.join(REPORTS_DIR, 'portfolio_analysis_2*.json')))
    for f in reversed(files):
        if today_str not in os.path.basename(f):
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    return json.load(fp)
            except Exception:
                continue
    return None


def compute_day_changes(stock_analyses: List[Dict], prev_report: Optional[Dict]) -> Dict[str, Dict]:
    """计算每只股票今日涨跌（对比上一期报告价格）"""
    changes = {}
    if not prev_report:
        return changes
    prev_stocks = {s.get('code'): s for s in prev_report.get('stock_analyses', [])}
    for sa in stock_analyses:
        code = sa.get('code', '')
        prev = prev_stocks.get(code, {})
        prev_price = prev.get('current_price', 0) or 0
        cur_price = sa.get('current_price', 0) or 0
        shares = sa.get('shares', 0) or 0
        if prev_price > 0 and cur_price > 0:
            changes[code] = {
                'change_pct': round((cur_price - prev_price) / prev_price * 100, 2),
                'pnl_change': round((cur_price - prev_price) * shares, 2),
                'prev_price': prev_price,
            }
    return changes


def generate_portfolio_synthesis(stock_analyses: List[Dict], day_changes: Dict[str, Dict],
                                  summary: Dict, prev_report: Optional[Dict]) -> Dict:
    """组合层综合研判——数据驱动的叙述"""

    synthesis = {
        'market_character': '',      # 今日性质（一句话定性）
        'driver_analysis': [],       # 驱动力拆解
        'hidden_risk': '',           # 隐忧
        'structure_note': '',        # 结构判断
        'tomorrow_focus': [],        # 明日验证点
        'oversold_verification': '', # 超卖信号验证
        'data_quality_notes': [],    # 数据质量提醒
    }

    # ── 数据质量前置检查 ──
    for sa in stock_analyses:
        cost = sa.get('avg_cost', 0) or 0
        if cost < 0:
            synthesis['data_quality_notes'].append(
                f"{sa.get('name')}({sa.get('code')}) 成本为负数({cost})，盈亏计算失真，请检查持仓数据"
            )
        elif cost > 0 and sa.get('current_price', 0) > 0:
            ratio = cost / sa['current_price']
            if ratio > 8:
                synthesis['data_quality_notes'].append(
                    f"{sa.get('name')}({sa.get('code')}) 成本({cost})是现价({sa['current_price']})的{ratio:.0f}倍，疑似成本录入错误"
                )

    # ── 日变化拆解 ──
    total_day_pnl = sum(v['pnl_change'] for v in day_changes.values())
    gainers = [(c, v) for c, v in day_changes.items() if v['pnl_change'] > 0]
    losers = [(c, v) for c, v in day_changes.items() if v['pnl_change'] < 0]
    gainers.sort(key=lambda x: -x[1]['pnl_change'])
    losers.sort(key=lambda x: x[1]['pnl_change'])

    name_map = {sa['code']: sa.get('name', sa['code']) for sa in stock_analyses}
    total_mv = summary.get('total_market_value', 0) or 1

    # 今日性质
    if abs(total_day_pnl) < total_mv * 0.003:
        synthesis['market_character'] = (
            f"今日组合基本持平（{total_day_pnl/10000:+.1f}万，{total_day_pnl/total_mv*100:+.2f}%），"
            f"多空力量在内部对冲"
        )
    elif total_day_pnl > 0:
        gain_ratio = total_day_pnl / total_mv * 100
        synthesis['market_character'] = (
            f"今日组合{'小幅' if gain_ratio < 0.5 else '明显'}收涨："
            f"{total_day_pnl/10000:+.1f}万（{gain_ratio:+.2f}%）"
        )
    else:
        loss_ratio = abs(total_day_pnl) / total_mv * 100
        synthesis['market_character'] = (
            f"今日组合{'小幅' if loss_ratio < 0.5 else '明显'}收跌："
            f"{total_day_pnl/10000:+.1f}万（{total_day_pnl/total_mv*100:+.2f}%）"
        )

    # 驱动力拆解
    if gainers:
        top = gainers[0]
        contribution = top[1]['pnl_change'] / total_day_pnl * 100 if total_day_pnl > 0 else 0
        line = (
            f"🟢 {name_map.get(top[0], top[0])}（{top[1]['change_pct']:+.2f}%）"
            f"贡献{top[1]['pnl_change']/10000:+.1f}万"
        )
        if total_day_pnl > 0 and contribution > 60:
            line += f"，独占今日涨幅的{contribution:.0f}%——单边行情特征明显"
        synthesis['driver_analysis'].append(line)
        for c, v in gainers[1:3]:
            synthesis['driver_analysis'].append(
                f"🟢 {name_map.get(c, c)}（{v['change_pct']:+.2f}%）{v['pnl_change']/10000:+.1f}万"
            )
    if losers:
        for c, v in losers[:2]:
            synthesis['driver_analysis'].append(
                f"🔴 {name_map.get(c, c)}（{v['change_pct']:+.2f}%）{v['pnl_change']/10000:+.1f}万"
            )
        if total_day_pnl > 0:
            total_loss = sum(v['pnl_change'] for _, v in losers)
            synthesis['driver_analysis'].append(
                f"注：下跌股合计{total_loss/10000:+.1f}万，"
                f"若不是{ name_map.get(gainers[0][0], '') if gainers else '头部个股' }对冲，今日实际亏损"
            )

    # 结构判断：A股 vs 港股 分化
    a_stocks = [(sa, day_changes.get(sa['code'], {})) for sa in stock_analyses if sa.get('market') == 'A股']
    hk_stocks = [(sa, day_changes.get(sa['code'], {})) for sa in stock_analyses if sa.get('market') != 'A股']
    a_pnl = sum(v.get('pnl_change', 0) for _, v in a_stocks)
    hk_pnl = sum(v.get('pnl_change', 0) for _, v in hk_stocks)
    if a_pnl * hk_pnl < 0 and abs(a_pnl) > 10000 and abs(hk_pnl) > 10000:
        direction = "沪强港弱" if a_pnl > 0 else "港强沪弱"
        synthesis['structure_note'] = (
            f"**{direction}分化日**：A股持仓今日合计{a_pnl/10000:+.1f}万，"
            f"港股持仓合计{hk_pnl/10000:+.1f}万。"
            f"组合约{sum(sa['market_value'] for sa, _ in hk_stocks)/total_mv*100:.0f}%在港股，"
            f"{'港股继续调整会持续拖累组合——但A股部分的反弹也在对冲这个风险' if hk_pnl < 0 else 'A股调整被港股对冲'}"
        )

    # 超卖信号验证（用【昨日报告】的超卖名单 × 今日实际涨幅——昨天标的今天涨了没有）
    prev_oversold_codes = []
    if prev_report:
        prev_oversold_codes = [
            s.get('code') for s in prev_report.get('stock_analyses', [])
            if s.get('technical_status') == 'oversold'
        ]
    if prev_oversold_codes and day_changes:
        verified = []
        for code in prev_oversold_codes:
            chg = day_changes.get(code, {}).get('change_pct', 0)
            nm = name_map.get(code, code)
            if chg > 2:
                verified.append(f"{nm}（昨日超卖，今日{chg:+.2f}%反弹验证）")
            elif chg < -2:
                verified.append(f"{nm}（昨日超卖，今日{chg:+.2f}%继续下探——超卖≠见底，基本面可能真有问题）")
        if verified:
            synthesis['oversold_verification'] = (
                "昨日超卖信号今日验证：" + "；".join(verified) +
                "。偏离中轴深≠必然反弹，要区分'情绪错杀'与'基本面恶化'——前者修复快，后者是下跌中继。"
            )

    # 隐忧
    concerns = []
    # 港股占比
    hk_ratio = sum(sa.get('market_value', 0) for sa in stock_analyses if sa.get('market') != 'A股') / total_mv * 100
    if hk_ratio > 40:
        concerns.append(f"港股仓位{hk_ratio:.0f}%，汇率与海外流动性风险敞口大")
    # 集中度
    top3_mv = sum(sorted([sa.get('market_value', 0) for sa in stock_analyses], reverse=True)[:3]) / total_mv * 100
    if top3_mv > 50:
        concerns.append(f"前三大重仓占{top3_mv:.0f}%，单票波动对组合影响显著")
    # 解禁风险
    try:
        unlock_file = os.path.join(DATA_DIR, 'event_impact.json')
        if os.path.exists(unlock_file):
            with open(unlock_file, 'r', encoding='utf-8') as f:
                ev = json.load(f)
            for sa in stock_analyses:
                unlock = ev.get('unlock', {}).get(sa['code'])
                if unlock and unlock.get('has_warning'):
                    for w in unlock.get('future_warnings', []):
                        if w.get('risk') == 'HIGH':
                            concerns.append(
                                f"{sa['name']} {w['date'][:10]}解禁{w['ratio']:.1f}%（高风险），"
                                f"届时供给冲击不可忽视"
                            )
    except Exception:
        pass
    if concerns:
        synthesis['hidden_risk'] = "；".join(concerns)

    # 明日验证点
    # 1) 今日大涨股：延续还是回吐
    for c, v in gainers[:2]:
        if v['change_pct'] > 3:
            sa = next((x for x in stock_analyses if x['code'] == c), {})
            axis = sa.get('axis_price', 0)
            synthesis['tomorrow_focus'].append(
                f"{name_map.get(c, c)}：今日{v['change_pct']:+.2f}%放量，明日看能否守住一半涨幅"
                + (f"，上方中轴{axis:.0f}元是下一道关" if axis > 0 else "")
            )
    # 2) 今日下跌股：止跌还是延续
    for c, v in losers[:2]:
        sa = next((x for x in stock_analyses if x['code'] == c), {})
        dev = sa.get('axis_deviation', 0)
        if abs(v['change_pct']) > 1.5:
            synthesis['tomorrow_focus'].append(
                f"{name_map.get(c, c)}：今日{v['change_pct']:+.2f}%，"
                f"偏离中轴{dev:+.1f}%" + ("，接近超卖区可留意" if dev < -6 else "，还没到策略买点，耐心等")
            )
    # 3) 组合层面
    over_sold_n = len(prev_oversold_codes)
    if over_sold_n >= 5:
        synthesis['tomorrow_focus'].append(
            f"{over_sold_n}只处于超卖区——策略买点已经出现，但一次不要全接，"
            f"优先选择偏离最深且基本面无恶化的标的"
        )

    return synthesis


# ========== 叙述层（顶层入口） ==========

def build_full_synthesis(stock_analyses: List[Dict], summary: Dict,
                          report_date: str, fetch_kline_fn=None) -> Dict:
    """生成完整综合研判：个股层+组合层，一次调用"""
    prev_report = load_prev_report(report_date)
    day_changes = compute_day_changes(stock_analyses, prev_report)

    # 附加日涨跌到个股分析
    for sa in stock_analyses:
        chg = day_changes.get(sa['code'], {})
        sa['day_change_pct'] = chg.get('change_pct', 0)
        sa['day_pnl_change'] = chg.get('pnl_change', 0)

    # 组合层综合研判
    synthesis = generate_portfolio_synthesis(stock_analyses, day_changes, summary, prev_report)

    # 个股层：事件分析（全部，读缓存）+ 综合研判（今日波动≥3%的调K线）
    for sa in stock_analyses:
        code = sa.get('code', '')
        sa['event_analysis'] = enrich_stock_events(code)

        chg_pct = abs(sa.get('day_change_pct', 0))
        if chg_pct >= 3 and fetch_kline_fn:
            try:
                kline = fetch_kline_fn(code, days=40)
                if kline:
                    sa['tactics_analysis'] = enrich_stock_tactics(sa, kline)
                    time.sleep(1)  # 防接口限流
                else:
                    sa['tactics_analysis'] = []
            except Exception as e:
                print(f"[Synthesis] {code} K线获取失败: {e}")
                sa['tactics_analysis'] = []
        else:
            sa['tactics_analysis'] = []

    return synthesis


if __name__ == '__main__':
    # 测试
    report = json.load(open(os.path.join(REPORTS_DIR, 'portfolio_analysis_latest.json'), encoding='utf-8'))
    stocks_data = json.load(open(os.path.join(DATA_DIR, 'stocks.json'), encoding='utf-8'))

    from deep_analysis import get_tencent_kline
    synthesis = build_full_synthesis(
        report['stock_analyses'], report['summary'],
        report['report_date'], fetch_kline_fn=get_tencent_kline
    )
    print(json.dumps(synthesis, ensure_ascii=False, indent=2, default=str))
