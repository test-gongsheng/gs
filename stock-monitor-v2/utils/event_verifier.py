# -*- coding: utf-8 -*-
"""
事件有效性验证引擎（验证闭环）

背景：事件发生后必须用后续 1/3/5 个交易日行情验证影响有效性：
  - 每个事件建档时记录 event_price（事件日收盘基线）
  - d1/d3/d5 交易日到期后自动取该股真实收盘价，计算 pct = (close-event_price)/event_price*100
  - 判定：direction=positive → pct>=+2% 命中 / pct<=-2% 落空 / 其他 未兑现；negative 镜像
  - d5 回填后写总结论：命中≥2次"影响验证有效" / 命中1次"部分兑现" / 0命中"影响证伪"
    （含落空时注明"出现反向走势"）
  - 全部事件跑完后汇总 data/event_verification_stats.json：{主题/个股: 事件数/命中数/命中率}

交易日历取舍说明：
  优先用腾讯K线通道（utils.stock_quote.get_stock_kline）取真实交易日序列——
  它只含真实交易日，天然排除A股节假日与调休，比工作日历准确。
  K线通道不可用时回退简单工作日历（周一~周五），该路径只能算目标日期、
  无法取收盘价，槽位会留空等待下次运行，属可接受的优雅降级。
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

if __package__ in (None, ''):  # 直接 python utils/event_verifier.py 运行时补根路径
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.stock_quote import get_stock_kline

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
WATCHLIST_FILE = os.path.join(DATA_DIR, 'event_verification.json')
STATS_FILE = os.path.join(DATA_DIR, 'event_verification_stats.json')

# 判定阈值（%）：|pct| >= HIT_THRESHOLD 才计为方向命中/落空
HIT_THRESHOLD = 2.0

_VERDICT_CN = {
    'hit': '命中',
    'miss': '落空',
    'pending': '未兑现',
}

_DIR_CN = {'positive': '正向', 'negative': '负向', 'neutral': '中性'}


def _today_str(as_of: Optional[str] = None) -> str:
    return as_of or datetime.now().strftime('%Y-%m-%d')


def _infer_market(code: str) -> str:
    """复用 stock_quote 的口径：5位数字→港股，6开头/688→沪，其余→深"""
    code = (code or '').strip()
    if len(code) == 5:
        return '港股'
    return 'A股'


def load_stats() -> Dict:
    """读取命中率汇总（themes/stocks 桶），文件不存在或损坏返回 {}"""
    if not os.path.exists(STATS_FILE):
        return {}
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def load_watchlist() -> List[Dict]:
    """读取事件观察清单"""
    if not os.path.exists(WATCHLIST_FILE):
        return []
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('watchlist', []) if isinstance(data, dict) else []
    except Exception as e:
        print(f'[事件验证] 观察清单读取失败: {e}')
        return []


def save_watchlist(watchlist: List[Dict]):
    """写回事件观察清单"""
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = WATCHLIST_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'watchlist': watchlist}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, WATCHLIST_FILE)


def _theme_of(title: str) -> str:
    """从标题【主题】前缀提取主题名，无前缀归为 个股事件"""
    m = re.match(r'^【(.+?)】', title or '')
    return m.group(1) if m else '个股事件'


def _weekday_targets(event_date: str, n: int = 5) -> List[str]:
    """回退方案：简单工作日历（周一~周五，不含节假日）"""
    d = datetime.strptime(event_date, '%Y-%m-%d')
    out = []
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() < 5:  # 0-4 周一~周五
            out.append(d.strftime('%Y-%m-%d'))
    return out


def _kline_targets(kline: List[Dict], event_date: str, n: int = 5) -> List[str]:
    """从真实K线交易日序列取 event_date 之后第 1..n 个交易日"""
    dates = [k['date'] for k in kline if k.get('date') and k['date'] > event_date]
    return dates[:n]


def _close_on(kline: List[Dict], date: str) -> Optional[float]:
    for k in kline:
        if k.get('date') == date:
            return float(k['close'])
    return None


def _last_close_on_or_before(kline: List[Dict], date: str) -> Optional[float]:
    """event_date 当天无K线（停牌/非交易日）时，取之前最近一个收盘价"""
    prev = None
    for k in kline:
        if k.get('date') and k['date'] <= date:
            prev = float(k['close'])
        else:
            break
    return prev


def _judge(direction: str, pct: float) -> str:
    """方向判定：positive → 涨>=+2命中 / 跌<=-2落空；negative 镜像"""
    if direction == 'negative':
        if pct <= -HIT_THRESHOLD:
            return 'hit'
        if pct >= HIT_THRESHOLD:
            return 'miss'
        return 'pending'
    # positive / neutral 统一按正向阈值（neutral 事件在汇总时不计入方向命中率）
    if pct >= HIT_THRESHOLD:
        return 'hit'
    if pct <= -HIT_THRESHOLD:
        return 'miss'
    return 'pending'


def _write_conclusion(event: Dict):
    """d5 已回填后写总结论"""
    verify = event.setdefault('verify', {})
    slots = [verify.get('d1'), verify.get('d3'), verify.get('d5')]
    filled = [s for s in slots if s]
    if len(filled) < 3:
        return  # d5 未齐不写结论
    hits = sum(1 for s in filled if s.get('verdict') == 'hit')
    misses = sum(1 for s in filled if s.get('verdict') == 'miss')
    if hits >= 2:
        concl = '影响验证有效'
    elif hits == 1:
        concl = '部分兑现'
    else:
        concl = '影响证伪'
    if misses > 0:
        concl += '（出现反向走势）'
    verify['conclusion'] = concl


def run_verification(as_of: Optional[str] = None, verbose: bool = True) -> Dict:
    """
    对观察清单里所有事件跑一轮验证：
      - 到期槽位（dN 为空且 as_of >= 目标交易日）用真实K线收盘价回填
      - d5 齐后写总结论
      - 汇总 stats 到 data/event_verification_stats.json
    返回 {checked, filled, concluded, errors}
    """
    today = _today_str(as_of)
    watchlist = load_watchlist()
    if not watchlist:
        if verbose:
            print('[事件验证] 观察清单为空，跳过')
        return {'checked': 0, 'filled': 0, 'concluded': 0, 'errors': 0}

    kline_cache: Dict[str, List[Dict]] = {}
    filled = concluded = errors = 0

    for ev in watchlist:
        code = ev.get('code', '')
        event_date = (ev.get('event_date') or '')[:10]
        if not code or not event_date:
            errors += 1
            continue
        market = _infer_market(code)

        # K线只拉一次/股（120日窗口覆盖 d1/d3/d5 + 基线回填）
        if code not in kline_cache:
            try:
                kline_cache[code] = get_stock_kline(code, market, days=120, max_retries=2) or []
            except Exception as e:
                print(f'[事件验证] K线获取失败 {code}: {e}')
                kline_cache[code] = []

        kline = kline_cache[code]
        if kline:
            targets = _kline_targets(kline, event_date, n=5)
        else:
            targets = _weekday_targets(event_date, n=5)

        # 基线回填：建档时 event_price 缺失 → 取事件日（或之前最近）真实收盘
        if ev.get('event_price') in (None, 0) and kline:
            base = _last_close_on_or_before(kline, event_date)
            if base:
                ev['event_price'] = round(base, 3)
                if verbose:
                    print(f'[事件验证] {code} 基线回填 event_price={base:.2f}')

        verify = ev.setdefault('verify', {})
        base_price = ev.get('event_price')
        touched = False

        for key, idx in (('d1', 0), ('d3', 2), ('d5', 4)):
            slot = verify.get(key)
            if slot is not None:
                continue
            if idx >= len(targets):
                continue
            target_date = targets[idx]
            if today < target_date:
                continue  # 未到期
            close = _close_on(kline, target_date) if kline else None
            if close is None or not base_price:
                continue  # 数据未就绪，等下次运行
            pct = (close - base_price) / base_price * 100
            verdict = _judge(ev.get('direction', 'positive'), pct)
            verify[key] = {
                'date': target_date,
                'close': round(close, 3),
                'pct': round(pct, 2),
                'verdict': verdict,
            }
            filled += 1
            touched = True
            if verbose:
                print(f'[事件验证] {code} {key}({target_date}) 收{close:.2f} '
                      f'{pct:+.2f}% → {_VERDICT_CN[verdict]}')

        if touched or verify.get('conclusion') is None:
            _write_conclusion(ev)
            if verify.get('conclusion'):
                concluded += 1
                if verbose:
                    print(f'[事件验证] {code} 结论：{ev["title"][:24]}… → {verify["conclusion"]}')

    save_watchlist(watchlist)

    # ---- 汇总命中率（分母=已结案事件；未结案的留在清单里等d5）----
    stats = {'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'themes': {}, 'stocks': {}}
    for ev in watchlist:
        verify = ev.get('verify') or {}
        concl = verify.get('conclusion')
        if not concl:
            continue
        hit = concl.startswith('影响验证有效')
        partial = concl.startswith('部分兑现')
        buckets = (
            (_theme_of(ev.get('title', '')), stats['themes']),
            (ev.get('code', ''), stats['stocks']),
        )
        for key, bucket in buckets:
            if key not in bucket:
                bucket[key] = {'total': 0, 'hits': 0, 'partial': 0, 'falsified': 0, 'hit_rate': 0.0}
            b = bucket[key]
            b['total'] += 1
            if hit:
                b['hits'] += 1
            elif partial:
                b['partial'] += 1
            else:
                b['falsified'] += 1
            b['hit_rate'] = round(b['hits'] / b['total'], 3)

    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STATS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATS_FILE)

    if verbose:
        print(f'[事件验证] 本轮：回填{filled}槽位，结案{concluded}条，'
              f'主题{len(stats["themes"])}个/个股{len(stats["stocks"])}只有命中率')
    return {'checked': len(watchlist), 'filled': filled, 'concluded': concluded, 'errors': errors}


def file_watchlist_event(code: str, title: str, direction: str = 'positive',
                         level: str = 'medium', price: Optional[float] = None,
                         source: str = '', event_time: Optional[str] = None) -> bool:
    """
    自动建档：把 level 为 high/medium 的主题事件追加进观察清单。
    去重：同 code + 标题前20字。event_price 取当日收盘，取不到记 None（验证时回填）。
    返回是否新增加。
    """
    if level not in ('high', 'medium'):
        return False
    watchlist = load_watchlist()
    # 去重三口径：①同code+标题前20字（标题完全一致）
    # ②同code+同【主题】前缀+同事件日（同一主题当日换了标题措辞也不重复建档）
    evt_day = (event_time or '')[:10] or datetime.now().strftime('%Y-%m-%d')
    evt_theme = re.match(r'^(【.+?】)', title or '')
    evt_theme = evt_theme.group(1) if evt_theme else None
    for e in watchlist:
        if e.get('code') != code:
            continue
        if (e.get('title', '') or '')[:20] == (title or '')[:20]:
            return False
        e_theme = re.match(r'^(【.+?】)', e.get('title', ''))
        if (evt_theme and e_theme and e_theme.group(1) == evt_theme
                and (e.get('event_date') or '')[:10] == evt_day):
            return False
    now = datetime.now()
    watchlist.append({
        'code': code,
        'title': title,
        'event_date': evt_day,
        'event_time': event_time or now.strftime('%Y-%m-%d %H:%M:%S'),
        'source': source,
        'direction': direction if direction in ('positive', 'negative', 'neutral') else 'positive',
        'level': level,
        'event_price': round(price, 3) if price else None,
        'content': '',
        'verify': {'d1': None, 'd3': None, 'd5': None, 'conclusion': None},
    })
    save_watchlist(watchlist)
    print(f'[事件验证] 自动建档 {code} {title[:30]}（基线{"%.2f" % price if price else "待回填"}）')
    return True


def _strip_theme(title: str) -> str:
    return re.sub(r'^【.+?】', '', title or '').strip()


def _match_from(watchlist: List[Dict], code: str, title_hint: str) -> Optional[Dict]:
    """在已加载清单里找该股与标题最匹配的一条：去【主题】前缀后双向包含或前20字相等"""
    cands = [e for e in watchlist if e.get('code') == code]
    if not cands:
        return None
    hint = _strip_theme(title_hint)[:20]
    for e in cands:
        et = _strip_theme(e.get('title', ''))[:20]
        if hint and (hint in et or et in hint):
            return e
    return cands[0]


def query_verification(code: str, title_hint: str = '') -> Optional[Dict]:
    """供报告渲染层查询：返回该股与标题最匹配的一条验证记录（含 verify 全量），无则 None。"""
    return _match_from(load_watchlist(), code, title_hint)


def verifications_for_code(code: str) -> List[Dict]:
    """供报告渲染层一次加载该股全部验证记录（避免逐条读盘）"""
    return [e for e in load_watchlist() if e.get('code') == code]


def format_verify_status(ev: Dict) -> str:
    """把一条已匹配的事件验证记录渲染成一行中文结论（报告"验证结论"段用）：
      已结案 → "已结案：d1 +1.2%命中 / d3 -0.5%未兑现 / d5 +3.0%命中 → **影响验证有效**"
      验证中 → "验证中：d1(09-16) +1.2%命中 / d3(09-18) -0.5%未兑现 / d5待到期（基线¥36.18）"
      未开始 → "验证中（d1/d3/d5，基线¥36.18）"
    """
    verify = ev.get('verify') or {}
    base = ev.get('event_price')
    base_txt = f'基线¥{base:.2f}' if base else '基线待回填'

    parts = []
    for key, n in (('d1', 1), ('d3', 3), ('d5', 5)):
        slot = verify.get(key)
        if slot:
            parts.append(f'd{n}({slot["date"][5:]}) {slot["pct"]:+.1f}%'
                         f'{_VERDICT_CN.get(slot.get("verdict"), "?")}')
        else:
            parts.append(f'd{n}待到期')
    concl = verify.get('conclusion')
    if concl:
        return f'已结案：{" / ".join(parts)} → **{concl}**'
    return f'验证中：{" / ".join(parts)}（{base_txt}）'


def render_verification_line(code: str, title_hint: str) -> str:
    """从磁盘查询并渲染一行验证结论（无匹配记录时返回兜底文案）"""
    ev = query_verification(code, title_hint)
    if ev is None:
        return '验证中（未建档，等待下一轮扫描归档）'
    return format_verify_status(ev)


if __name__ == '__main__':
    print('=' * 60)
    print('事件验证引擎自测')
    print('=' * 60)

    # ---- 用例1（任务规格）：2026-09-15 正向事件挂301308，基线330 ----
    # 交易日历：d1=09-16 d3=09-18 d5=09-22（明日到期），
    # 故今天(09-21)应回填 d1/d3 两个槽位并给出判定，d5 留待明日。
    print('\n[用例1] event_date=2026-09-15 positive price=330（江波龙301308）')
    wl = load_watchlist()
    if not any(e.get('code') == '301308' and (e.get('title', '') or '').startswith('测试事件')
               for e in wl):
        wl.append({
            'code': '301308',
            'title': '测试事件：存储涨价（自测用，可删除）',
            'event_date': '2026-09-15',
            'event_time': '2026-09-15 10:00:00',
            'source': '自测',
            'direction': 'positive',
            'level': 'low',
            'event_price': 330.0,
            'content': '',
            'verify': {'d1': None, 'd3': None, 'd5': None, 'conclusion': None},
        })
        save_watchlist(wl)
        print('  已注入测试事件')

    # ---- 用例2（全链路证明）：2026-09-07 事件，d1/d3/d5 均已到期 ----
    # 09-08(d1) 09-10(d3) 09-14(d5) 全部早于今天，应三槽全填+写总结论。
    print('\n[用例2] event_date=2026-09-07 positive（全链路：三槽+结论）')
    wl = load_watchlist()
    if not any(e.get('code') == '301308' and (e.get('title', '') or '').startswith('全链路测试')
               for e in wl):
        wl.append({
            'code': '301308',
            'title': '全链路测试事件：AI算力扩产（自测用，可删除）',
            'event_date': '2026-09-07',
            'event_time': '2026-09-07 10:00:00',
            'source': '自测',
            'direction': 'positive',
            'level': 'low',
            'event_price': None,  # 故意留空，验证"基线回填"分支
            'content': '',
            'verify': {'d1': None, 'd3': None, 'd5': None, 'conclusion': None},
        })
        save_watchlist(wl)
        print('  已注入测试事件（event_price=None，测基线回填）')

    result = run_verification()
    print(f'\n[run_verification] {result}')

    # ---- 展示301308两条测试事件的验证结果 ----
    print('\n[301308 验证明细]')
    for e in load_watchlist():
        if e.get('code') == '301308' and '测试' in (e.get('title') or ''):
            print(f'  {e["title"]}')
            print(f'    event_date={e["event_date"]} direction={e["direction"]} '
                  f'基线={e.get("event_price")}')
            for key in ('d1', 'd3', 'd5'):
                slot = (e.get('verify') or {}).get(key)
                if slot:
                    print(f'    {key}: {slot["date"]} 收{slot["close"]:.2f} '
                          f'{slot["pct"]:+.2f}% → {_VERDICT_CN[slot["verdict"]]}')
                else:
                    print(f'    {key}: 待到期')
            print(f'    结论: {(e.get("verify") or {}).get("conclusion")}')

    # ---- 报告渲染接口抽查 ----
    print('\n[render_verification_line 抽查]')
    print('  测试事件 →', render_verification_line('301308', '测试事件：存储涨价'))
    print('  真实事件 →', render_verification_line('002050', '监管传闻收紧人形机器人IPO审核门槛'))
    print('=' * 60)
