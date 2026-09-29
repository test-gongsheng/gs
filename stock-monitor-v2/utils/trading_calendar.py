# -*- coding: utf-8 -*-
"""
交易日历前瞻（2026-09-29 新增）
====================================
豆包分析报告里的"明天是国庆前最后交易日/长假停牌8天/12/7解禁只剩10个交易周"
这类日历感，就是本模块提供的。数据：akshare 交易日历（新浪源），失败则降级为空。

输出：
- next_trade_date / days_to_next：下一交易日与间隔
- holiday_gap_days：当前日与下一交易日之间的连续休市天数（>3 即长假窗口）
- trading_days_between(d1, d2)：两个日期之间的交易日数（解禁/财报倒计時用）
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_CACHE: Optional[List[str]] = None


def _load_trade_dates() -> List[str]:
    """全部交易日（YYYY-MM-DD），带内存缓存。失败返回空列表。"""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    dates: List[str] = []
    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        col = df.columns[0]
        dates = sorted(str(d)[:10] for d in df[col].tolist())
    except Exception as e:
        print(f"[交易日历] 获取失败（降级为空）: {e}")
    _CACHE = dates
    return dates


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def get_calendar_context(as_of: Optional[str] = None) -> Dict:
    """日历前瞻：下一交易日、休市窗口"""
    today = as_of or _today_str()
    dates = _load_trade_dates()
    ctx: Dict = {'as_of': today}
    if not dates:
        return ctx
    future = [d for d in dates if d > today]
    if future:
        nxt = future[0]
        nxt_dt = datetime.strptime(nxt, '%Y-%m-%d')
        today_dt = datetime.strptime(today, '%Y-%m-%d')
        ctx['next_trade_date'] = nxt
        ctx['days_to_next'] = (nxt_dt - today_dt).days
        # 连续休市天数 = 间隔天数 - 1（间隔本身就是自然日差）
        gap = (nxt_dt - today_dt).days - 1
        ctx['holiday_gap_days'] = max(0, gap)
        if gap >= 3:
            ctx['is_holiday_window'] = True
            ctx['holiday_note'] = (f"长假窗口：{today}收盘后连休{gap}天，"
                                   f"{nxt}开市——期间外盘/政策/地缘风险无法交易对冲")
    return ctx


def trading_days_until(target_date: str, as_of: Optional[str] = None) -> Optional[int]:
    """从今天到目标日期（YYYY-MM-DD，含目标日）还有几个交易日。日期非法返回None。"""
    try:
        target = datetime.strptime(target_date[:10], '%Y-%m-%d')
    except ValueError:
        return None
    today = as_of or _today_str()
    dates = _load_trade_dates()
    if not dates:
        return None
    return sum(1 for d in dates if today < d <= target.strftime('%Y-%m-%d'))


def render_calendar_lines(unlock_date: str = '') -> List[str]:
    """渲染成报告行（无前缀标题，由调用方放置）"""
    lines: List[str] = []
    ctx = get_calendar_context()
    if ctx.get('next_trade_date'):
        d = ctx['days_to_next']
        line = (f"- 📅 下一交易日 **{ctx['next_trade_date']}**"
                f"（{d}天后{'开市' if d > 1 else ''}）")
        if ctx.get('is_holiday_window'):
            line += f"；⚠️ {ctx['holiday_note']}"
        lines.append(line)
    if unlock_date:
        n = trading_days_until(unlock_date)
        if n is not None:
            lines.append(f"- 📅 关键日 {unlock_date} 距今 **{n} 个交易日**")
    return lines


if __name__ == '__main__':
    ctx = get_calendar_context()
    print('calendar:', ctx)
    print('距2026-12-07交易日数:', trading_days_until('2026-12-07'))
    print('距2026-10-29交易日数:', trading_days_until('2026-10-29'))
    for l in render_calendar_lines('2026-12-07'):
        print(l)
