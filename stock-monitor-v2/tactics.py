# -*- coding: utf-8 -*-
"""
持仓实战分析模块
对标豆包/东财深度研报的操作建议层：
  1. 持仓快照（市值/浮亏/变化趋势）
  2. 关键点位溯源（每个压力/支撑位标注K线形成原因）
  3. 操作含义（基于持仓状态+点位的具体建议，非指标罗列）
  4. 验证信号（可证伪的多空条件）
数据来源：腾讯K线（本地已有）、持仓数据（stocks.json）
"""
import json
import os
from typing import Dict, List, Optional, Tuple

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
DATA_FILE = os.path.join(DATA_DIR, 'stocks.json')


def _load_stocks() -> List[Dict]:
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get('stocks', [])
    except Exception:
        return []


def analyze_key_levels(kline: List[Dict], current_price: float, days: int = 40) -> Dict:
    """从K线识别关键点位及形成原因

    返回:
        resistance: [(price_low, price_high, reason)] 上方压力区，由近到远
        support:    [(price_low, price_high, reason)] 下方支撑区，由近到远
    """
    if len(kline) < 5 or current_price <= 0:
        return {'resistance': [], 'support': []}

    recent = kline[-days:]
    resistance = []  # (low, high, reason)
    support = []

    # ── 1. 大阴线套牢区 / 大阳线获利区 ──
    for k in recent[:-1]:  # 不含今天
        o, c, h, l = k['open'], k['close'], k['high'], k['low']
        if o <= 0:
            continue
        chg = (c - o) / o * 100
        day = (k.get('date', '') or '')[5:]  # MM-DD
        if chg < -5 and h > current_price:
            # 大阴线实体区 = 套牢盘压力
            body_top = max(o, c)
            resistance.append((body_top, h, f'{day}大阴线套牢区'))
        elif chg > 5 and l > current_price * 1.01:
            # 大涨日起点 = 获利回吐压力
            resistance.append((l, min(o, c), f'{day}放量大涨启动区'))

    # ── 2. 缺口（限近15个交易日，宽度≥2%才有效，次新股日常波动不算缺口）──
    gap_window = recent[-15:]
    for i in range(1, len(gap_window)):
        prev, cur = gap_window[i - 1], gap_window[i]
        day = (cur.get('date', '') or '')[5:]
        prev_range = prev['high'] - prev['low']
        if cur['low'] > prev['high'] * 1.005:  # 向上缺口（+0.5%容差）
            width_pct = (cur['low'] - prev['high']) / current_price * 100
            if width_pct < 2:
                continue  # 太窄，属于日常波动
            mid = (prev['high'] + cur['low']) / 2
            if mid > current_price:
                resistance.append((prev['high'], cur['low'], f'{day}向上缺口'))
            else:
                support.append((prev['high'], cur['low'], f'{day}向上缺口'))
        elif cur['high'] < prev['low'] * 0.995:  # 向下缺口
            width_pct = (prev['low'] - cur['high']) / current_price * 100
            if width_pct < 2:
                continue
            mid = (cur['high'] + prev['low']) / 2
            if mid > current_price:
                resistance.append((cur['high'], prev['low'], f'{day}向下缺口'))
            else:
                support.append((cur['high'], prev['low'], f'{day}向下缺口'))

    # ── 3. 前高前低（近20日）──
    swing = recent[-20:]
    if len(swing) >= 3:
        top = max(swing[:-1], key=lambda k: k['high'])
        bot = min(swing[:-1], key=lambda k: k['low'])
        t_day = (top.get('date', '') or '')[5:]
        b_day = (bot.get('date', '') or '')[5:]
        if top['high'] > current_price * 1.01:
            resistance.append((top['close'], top['high'], f'{t_day}阶段前高'))
        if bot['low'] < current_price * 0.99:
            support.append((bot['low'], bot['close'], f'{b_day}阶段前低'))

    # ── 4. 整数关口 ──
    for level in (400, 450, 500, 350, 300):
        if current_price * 1.02 < level < current_price * 1.15:
            resistance.append((level * 0.99, level * 1.01, f'{level}元整数关口'))
        elif current_price * 0.85 < level < current_price * 0.98:
            support.append((level * 0.99, level * 1.01, f'{level}元整数关口'))

    # ── 去重：区间重叠时保留离现价近的，不做链式合并 ──
    def dedup(zones: List[Tuple], above: bool) -> List[Tuple]:
        # 按离现价的距离排序
        if above:
            zones = [z for z in zones if z[0] > current_price * 1.005]
            zones.sort(key=lambda z: z[0] - current_price)
        else:
            zones = [z for z in zones if z[1] < current_price * 0.995]
            zones.sort(key=lambda z: current_price - z[1])
        picked = []
        for lo, hi, reason in zones:
            overlap = any(lo <= p_hi * 1.03 and hi >= p_lo * 0.97 for p_lo, p_hi, _ in picked)
            if not overlap:
                picked.append((lo, hi, reason))
            if len(picked) >= 3:
                break
        return picked

    return {
        'resistance': dedup(resistance, above=True),
        'support': dedup(support, above=False),
    }


def _fmt_wan(v: float) -> str:
    if abs(v) >= 10000:
        return f"{v / 10000:.1f}万"
    return f"{v:.0f}元"


def generate_position_tactics(stock: Dict, kline: List[Dict]) -> List[str]:
    """生成持仓实战分析段落（豆包式综合研判）

    输入: stock 持仓记录, kline 日K
    输出: markdown 行列表
    """
    code = stock.get('code', '')
    name = stock.get('name', '')
    cost = stock.get('avg_cost') or stock.get('cost') or 0
    shares = stock.get('shares') or 0
    price = stock.get('current_price') or 0

    lines = []
    if not cost or not price or cost <= 0:
        return lines
    if not kline or len(kline) < 5:
        return lines

    pnl_pct = (price - cost) / cost * 100
    mkt_val = price * shares
    pnl_amt = (price - cost) * shares

    # ── 0. 读上期浮亏做对比（趋势感知）──
    prev_note = ''
    try:
        hist_file = os.path.join(DATA_DIR, 'position_tactics_hist.json')
        hist = {}
        if os.path.exists(hist_file):
            with open(hist_file, 'r', encoding='utf-8') as f:
                hist = json.load(f)
        prev = hist.get(code, {})
        if prev.get('pnl_pct') is not None:
            delta = pnl_pct - prev['pnl_pct']
            if abs(delta) >= 0.5:
                arrow = '收窄' if delta > 0 else '扩大'
                prev_note = f"，较上期（{prev['pnl_pct']:.1f}%）{arrow}约{abs(delta):.1f}个百分点"
        hist[code] = {'pnl_pct': pnl_pct, 'price': price}
        with open(hist_file, 'w', encoding='utf-8') as f:
            json.dump(hist, f, ensure_ascii=False)
    except Exception:
        pass

    # ── 1. 持仓快照 ──
    status = '浮盈' if pnl_pct > 0 else '浮亏'
    lines.append(f"- **持仓快照：** 市值约{_fmt_wan(mkt_val)}，{status}约{_fmt_wan(abs(pnl_amt))}（{pnl_pct:+.1f}%{prev_note}）")

    # ── 2. 关键点位 ──
    levels = analyze_key_levels(kline, price)
    if levels['resistance']:
        parts = [f"{lo:.0f}-{hi:.0f}元（{r}）" for lo, hi, r in levels['resistance']]
        lines.append(f"- **上方压力：** {' → '.join(parts)}")
    if levels['support']:
        parts = [f"{lo:.0f}-{hi:.0f}元（{r}）" for lo, hi, r in levels['support']]
        lines.append(f"- **下方支撑：** {' → '.join(parts)}")

    # ── 3. 操作含义（核心研判层）──
    today = kline[-1]
    today_chg = (today['close'] - today['open']) / today['open'] * 100 if today['open'] else 0
    today_range = (today['high'] - today['low']) / today['low'] * 100 if today['low'] else 0
    vol_ratio = 0
    if len(kline) >= 6:
        avg_vol = sum(k['volume'] for k in kline[-6:-1]) / 5
        vol_ratio = today['volume'] / avg_vol if avg_vol else 0

    lines.append('')
    near_res = levels['resistance'][0] if levels['resistance'] else None
    near_sup = levels['support'][0] if levels['support'] else None

    advice = []
    if pnl_pct <= -30:
        # 深度套牢
        if near_res:
            lo, hi, reason = near_res
            if price >= lo * 0.97:
                advice.append(
                    f"当前价已进入**首档压力区**（{reason}）。若原计划减仓，此价位优于前期；"
                    f"建议分批执行（1/3~1/2仓），不必一次出完——留底仓博弈突破。"
                )
            else:
                pct_to_res = (lo / price - 1) * 100
                advice.append(
                    f"距首档压力区（{reason} {lo:.0f}元）还有约{pct_to_res:.0f}%空间。"
                    f"套牢{abs(pnl_pct):.0f}%的情况下，反弹至压力区分批降仓是纪律性选择。"
                )
        advice.append(
            "**不要追高补仓。** 今天"
            + (f"放量大涨{today_chg:.1f}%" if today_chg > 4 else f"涨{today_chg:.1f}%")
            + "，属情绪修复性质，持续性需验证；补仓摊成本应等回踩支撑确认。"
        )
    elif pnl_pct < 0:
        # 浅套
        if near_res and price >= near_res[0] * 0.98:
            advice.append(f"价位贴近压力区（{near_res[2]}），减仓窗口，可落袋部分仓位。")
        elif near_sup and price <= near_sup[1] * 1.02:
            advice.append(f"价位贴近支撑区（{near_sup[2]}），持仓待变，跌破则考虑止损。")
        else:
            advice.append("处于支撑与压力之间，持仓观察，等待方向选择。")
    else:
        # 浮盈
        if near_sup:
            advice.append(f"移动止盈线可参考{near_sup[0]:.0f}元（{near_sup[2]}），不破则持。")
        advice.append("浮盈状态下以持有为主，急涨可考虑分批兑现。")

    # 事件/解禁风险叠加
    try:
        with open(os.path.join(DATA_DIR, 'event_impact.json'), 'r', encoding='utf-8') as f:
            ev = json.load(f)
        unlock = ev.get('unlock', {}).get(code)
        if unlock and unlock.get('has_warning'):
            w = unlock['future_warnings'][0]
            if w['risk'] == 'HIGH':
                advice.append(
                    f"**风险叠加：** {w['date'][:10]}解禁{w['ratio']:.1f}%股本（高风险）。"
                    f"杠杆盘与解禁压力未出清前，反弹仓位不宜超过半仓。"
                )
    except Exception:
        pass

    if advice:
        lines.append('**操作含义：**')
        for i, a in enumerate(advice, 1):
            lines.append(f"{i}. {a}")

    # ── 4. 验证信号（可证伪条件）──
    signals = []
    if near_res:
        signals.append(f"放量站稳{near_res[1]:.0f}元上方 → 反弹延续，可看高一线")
    if near_sup:
        signals.append(f"回落跌破{near_sup[1]:.0f}元" + (f"，再失守{levels['support'][1][1]:.0f}元 → 反抽结束，减仓窗口关闭" if len(levels['support']) > 1 else " → 弱势确认"))
    if vol_ratio > 1.8:
        signals.append(f"今日量比{vol_ratio:.1f}倍，属放量级变动，信号可信度高于缩量")
    if signals:
        lines.append('')
        lines.append('**验证信号：**')
        for s in signals:
            lines.append(f"- {s}")

    return lines


if __name__ == '__main__':
    from deep_analysis import get_tencent_kline
    stocks = _load_stocks()
    s = next((x for x in stocks if x['code'] == '688795'), None)
    if s:
        s['current_price'] = 395.58
        k = get_tencent_kline('688795', days=40)
        for line in generate_position_tactics(s, k):
            print(line)
