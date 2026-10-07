# -*- coding: utf-8 -*-
"""
holiday_catchup.py
非交易日窗口（周末/长假）新闻事件黑洞修复。

根因：事件引擎 event_tracker.run_event_analysis 只在交易日被每日任务调用，
按天落盘 data/news_pool_YYYY-MM-DD.json；deep_analysis 只扫"近N天存在的池文件"。
长假窗口（如 2026-10-01~10-07）不产生池文件，窗口期新闻（宏观/地缘/产业大事）
永远不会进入任何深度报告。

本模块：
1. detect_gap()      —— 检测最新池文件日期与今天的缺口
2. run_catchup()     —— 抓窗口期新闻，按新闻自身真实时间归入对应日期池文件；
                        并对持仓股跑事件识别，合并进 events_history.json / event_impact.json
3. 数据源全部复用现有通道（禁止重复造轮子）：
   - 财联社电报/要闻   event_tracker.fetch_cls_telegraph（akshare 只有"最新"电报，
                       能捞多少捞多少，按 time 归期）
   - 财联社头条通道   utils.headline_feed（同样只有最新）
   - 东财个股搜索     event_tracker.fetch_stock_news（结果含 date 字段，
                       窗口历史主要靠它，按 date 过滤到窗口内）
   - 主题补漏         event_tracker._load_topup_keywords + _eastmoney_search
4. 全程 try/except 保护：单源失败打印警告继续，绝不崩溃中断。
   抓不到新闻的日期直接跳过，不造数据；每篇新闻的 time 必须真实。

CLI:
    python3 holiday_catchup.py --dry-run     # 只打印缺口与计划补录明细，不写盘
    python3 holiday_catchup.py               # 自动检测缺口并回补
    python3 holiday_catchup.py --days 14     # 手动指定回补天数（截至今天）
"""
import argparse
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 复用事件引擎既有通道（见模块 docstring，禁止重复造轮子）
from event_tracker import (  # noqa: E402
    fetch_cls_telegraph,
    fetch_stock_news,
    _eastmoney_search,
    _load_topup_keywords,
    extract_stock_events,
    extract_concept_events,
    identify_events,
    _attach_macro_theme_events,
    STOCK_CONCEPT_TAGS,
    _load_events,
    _save_events,
    STOCK_EVENT_TTL_DAYS,
)

POOL_DATE_RE = re.compile(r'^news_pool_(\d{4}-\d{2}-\d{2})\.json$')
LAST_RUN_FILE = os.path.join(DATA_DIR, 'holiday_catchup_last.json')


# ========== 缺口检测 ==========

def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def detect_gap(today: Optional[str] = None) -> Dict:
    """检测最新 news_pool_*.json 日期与今天的缺口。

    返回 {'latest': 'YYYY-MM-DD'|None, 'gap_days': int|None, 'missing_dates': [...]}。
    missing_dates = (latest, today] 之间每一天（含今天，若当天池文件尚不存在）。
    gap_days = today - latest 的天数；无池文件时 gap_days=None。
    """
    today = today or _today_str()
    latest: Optional[str] = None
    for fp in glob.glob(os.path.join(DATA_DIR, 'news_pool_*.json')):
        m = POOL_DATE_RE.match(os.path.basename(fp))
        if m and (latest is None or m.group(1) > latest):
            latest = m.group(1)
    if latest is None:
        return {'latest': None, 'gap_days': None, 'missing_dates': []}
    d_latest = datetime.strptime(latest, '%Y-%m-%d')
    d_today = datetime.strptime(today, '%Y-%m-%d')
    gap_days = (d_today - d_latest).days
    missing: List[str] = []
    if gap_days >= 1:
        d = d_latest + timedelta(days=1)
        while d <= d_today:
            missing.append(d.strftime('%Y-%m-%d'))
            d += timedelta(days=1)
    return {'latest': latest, 'gap_days': gap_days, 'missing_dates': missing}


# ========== 窗口新闻采集（全部复用现有通道） ==========

def _norm_title(t: str) -> str:
    return re.sub(r'</?em>', '', str(t or '')).strip()


def _norm_time(t: str) -> Optional[str]:
    """规整 time 为 'YYYY-MM-DD HH:MM:SS'；无法解析出日期则返回 None（不收）。"""
    s = str(t or '').strip()
    if not s:
        return None
    m = re.match(r'(\d{4}-\d{2}-\d{2})([ T](\d{2}:\d{2}(:\d{2})?))?', s)
    if not m:
        return None
    day = m.group(1)
    hm = (m.group(3) or '')[:8]
    return f'{day} {hm}'.strip()


def fetch_window_news(stocks: List[Dict], start_date: str, end_date: str) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
    """抓窗口期 [start_date, end_date] 新闻。

    返回 (window_news, stock_news_by_code)：
    - window_news：去重后的全窗口新闻（title/time/source/content/_ch），time 全部真实
    - stock_news_by_code：东财个股搜索的分股原始结果（供 extract_stock_events 使用）
    单源失败打印警告继续，绝不抛异常。
    """
    window: List[Dict] = []
    seen = set()

    def _add(items, channel: str):
        got = 0
        for it in items or []:
            title = _norm_title(it.get('title'))
            t = _norm_time(it.get('time'))
            if not title or not t:
                continue
            day = t[:10]
            if not (start_date <= day <= end_date):
                continue
            if title in seen:
                continue
            seen.add(title)
            window.append({
                'title': title,
                'time': t,
                'source': it.get('source', '') or '未知来源',
                'content': (it.get('content') or '')[:300],
                '_ch': channel,
            })
            got += 1
        if got:
            print(f'[回补] {channel}: 窗口内新增 {got} 条')

    # 1) 财联社电报+要闻（akshare 只有"最新"，按 time 归期，能捞多少捞多少）
    try:
        _add(fetch_cls_telegraph(), '财联社电报/要闻')
    except Exception as e:
        print(f'[回补][警告] 财联社电报获取失败（跳过该源）: {e}')

    # 2) 财联社头条/要闻/深度稿通道（同样只有最新首页，按 time 归期）
    try:
        from utils.headline_feed import fetch_cls_headlines, headlines_to_news_pool
        span_days = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days + 1
        _add(headlines_to_news_pool(fetch_cls_headlines(max_age_hours=24 * (span_days + 1))), '财联社头条')
    except Exception as e:
        print(f'[回补][警告] 头条通道获取失败（跳过该源）: {e}')

    # 3) 东财个股搜索（名称+代码+概念三路；结果含 date 字段，窗口历史主通道）
    stock_news_by_code: Dict[str, List[Dict]] = {}
    try:
        name_map = {s['code']: s.get('name', '') for s in stocks}
        res = fetch_stock_news([s['code'] for s in stocks], name_map)
        for code, lst in (res or {}).items():
            stock_news_by_code[code] = lst or []
            _add(lst, f'东财个股:{code}')
    except Exception as e:
        print(f'[回补][警告] 东财个股搜索失败（跳过该源）: {e}')

    # 4) 主题补漏关键词（持仓敏感主题定向搜索，东财搜索带 date 过滤到窗口）
    try:
        kws = _load_topup_keywords()
        span_days = (datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')).days + 2
        for kw in kws:
            try:
                _add(_eastmoney_search(kw, page_size=15, max_age_days=span_days), f'主题:{kw}')
            except Exception as e:
                print(f'[回补][警告] 主题"{kw}"搜索失败（跳过）: {e}')
            time.sleep(0.3)
    except Exception as e:
        print(f'[回补][警告] 主题补漏通道失败（跳过该源）: {e}')

    window.sort(key=lambda x: x['time'])
    return window, stock_news_by_code


# ========== 按新闻自身日期落盘池文件 ==========

def write_daily_pools(window_news: List[Dict], missing_dates: List[str]) -> Dict[str, int]:
    """把窗口新闻按各自 time 归入对应日期文件 data/news_pool_YYYY-MM-DD.json。

    只写有新闻的日期，抓不到的日期跳过（不造数据）。返回 {date: 条数}。
    """
    by_date: Dict[str, List[Dict]] = {d: [] for d in missing_dates}
    for it in window_news:
        day = it['time'][:10]
        if day in by_date:
            by_date[day].append({'title': it['title'], 'time': it['time'][:16],
                                 'source': it['source']})
    written: Dict[str, int] = {}
    for d in missing_dates:
        items = by_date.get(d) or []
        if not items:
            continue  # 该天没抓到，跳过
        items = items[:150]
        fp = os.path.join(DATA_DIR, f'news_pool_{d}.json')
        try:
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump({'date': d, 'count': len(items), 'news': items},
                          f, ensure_ascii=False, indent=1)
            written[d] = len(items)
            print(f'[回补] 写入 {os.path.basename(fp)}: {len(items)} 条')
        except Exception as e:
            print(f'[回补][警告] 写入 {fp} 失败: {e}')
    return written


# ========== 窗口事件识别并并入历史（先读旧文件再合并追加，去重按 title） ==========

def merge_window_events(stocks: List[Dict], window_news: List[Dict],
                        stock_news_by_code: Dict[str, List[Dict]]) -> Dict[str, int]:
    """对窗口期新闻跑持仓股事件识别，合并进 events_history.json 与 event_impact.json。

    - 个股级/板块级/宏观主题事件 → event_impact.json 的 stock_events（按 title 去重合并，不覆盖）
    - 全局宏观事件（identify_events）→ events_history.json（按 type+14天窗口合并，复用 _load_events/_save_events）
    返回 {'stock_events': 新增条数, 'macro_events': 新增条数}
    """
    stats = {'stock_events': 0, 'macro_events': 0}
    today = _today_str()

    # 1) 持仓股事件：个股级 + 板块级 + 宏观主题映射
    stock_events: Dict[str, List[Dict]] = {}
    all_names = [s.get('name', '') for s in stocks]
    for s in stocks:
        code, name = s['code'], s.get('name', '')
        try:
            evts = extract_stock_events(code, name, stock_news_by_code.get(code, []), all_names)
            if evts:
                stock_events.setdefault(code, []).extend(evts)
        except Exception as e:
            print(f'[回补][警告] 个股事件识别失败 {code}（跳过）: {e}')
        try:
            tags = STOCK_CONCEPT_TAGS.get(code)
            if tags:
                cevts = extract_concept_events(code, tags, window_news + stock_news_by_code.get(code, []))
                if cevts:
                    stock_events.setdefault(code, []).extend(cevts)
        except Exception as e:
            print(f'[回补][警告] 板块事件归因失败 {code}（跳过）: {e}')
    try:
        _attach_macro_theme_events(window_news, stock_events, stocks)
    except Exception as e:
        print(f'[回补][警告] 宏观主题映射失败（跳过）: {e}')

    # 2) 合并进 event_impact.json（先读旧再追加，按 title 去重，TTL 清理）
    try:
        ei_path = os.path.join(DATA_DIR, 'event_impact.json')
        report = {}
        if os.path.exists(ei_path):
            with open(ei_path, 'r', encoding='utf-8') as f:
                report = json.load(f) or {}
        existing = report.get('stock_events') or {}
        ttl_cut = (datetime.now() - timedelta(days=STOCK_EVENT_TTL_DAYS)).strftime('%Y-%m-%d')
        for code, evts in stock_events.items():
            cur = existing.setdefault(code, [])
            titles = {e.get('title') for e in cur}
            for e in evts:
                t = e.get('title')
                if t and t not in titles:
                    cur.append(e)
                    titles.add(t)
                    stats['stock_events'] += 1
            existing[code] = [e for e in cur if (e.get('time', '') or '')[:10] >= ttl_cut][:30]
        report['stock_events'] = existing
        with open(ei_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        if stats['stock_events']:
            print(f'[回补] event_impact.json 合并窗口期个股事件 +{stats["stock_events"]} 条')
    except Exception as e:
        print(f'[回补][警告] event_impact.json 合并失败（不中断）: {e}')

    # 3) 全局宏观事件并入 events_history.json（复用 event_tracker 的加载/保存逻辑）
    try:
        new_events = identify_events(window_news) or []
        if new_events:
            history = _load_events()
            now = datetime.now()
            for ev in new_events:
                ex = next((e for e in history
                           if e.get('type') == ev.get('type')
                           and (now - datetime.strptime(e.get('first_date', today), '%Y-%m-%d')).days <= 14), None)
                if ex:
                    ex.update(ev)
                    ex['tracking_days'] = (now - datetime.strptime(
                        ex.get('first_date', today), '%Y-%m-%d')).days + 1
                else:
                    ev['first_date'] = today
                    ev['tracking_days'] = 1
                    history.append(ev)
                    stats['macro_events'] += 1
            cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            history = [e for e in history if e.get('first_date', '2026-01-01') >= cutoff]
            _save_events(history)
            print(f'[回补] events_history.json 合并窗口期宏观事件 +{stats["macro_events"]} 类')
    except Exception as e:
        print(f'[回补][警告] events_history.json 合并失败（不中断）: {e}')

    return stats


# ========== 主流程 ==========

def _load_portfolio() -> List[Dict]:
    fp = os.path.join(DATA_DIR, 'stocks.json')
    with open(fp, 'r', encoding='utf-8') as f:
        return (json.load(f) or {}).get('stocks', [])


def save_last_run(summary: Dict):
    """落盘本次回补标记，供 deep_analysis 渲染"窗口期事件补录"章节时定位窗口。"""
    try:
        with open(LAST_RUN_FILE, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f'[回补][警告] 写标记文件失败（不影响池文件）: {e}')


def load_last_run() -> Optional[Dict]:
    """读取最近一次回补标记；无/损坏返回 None。"""
    try:
        if os.path.exists(LAST_RUN_FILE):
            with open(LAST_RUN_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if d.get('window_start') and d.get('window_end'):
                return d
    except Exception:
        pass
    return None


def run_catchup(days: Optional[int] = None, dry_run: bool = False) -> Dict:
    """检测缺口并回补。days 手动指定回补天数（截至今天）；None=自动按缺口。

    dry_run=True 时只打印计划（不写盘、不合并事件）。
    返回 summary 字典；异常时返回 {'error': ...}（绝不向上抛）。
    """
    try:
        info = detect_gap()
        today = _today_str()
        if days:
            start = (datetime.strptime(today, '%Y-%m-%d') - timedelta(days=days - 1)).strftime('%Y-%m-%d')
            missing = []
            d = datetime.strptime(start, '%Y-%m-%d')
            while d <= datetime.strptime(today, '%Y-%m-%d'):
                missing.append(d.strftime('%Y-%m-%d'))
                d += timedelta(days=1)
            info = {'latest': None, 'gap_days': days, 'missing_dates': missing}
            start_date = start
        else:
            missing = info.get('missing_dates') or []
            start_date = missing[0] if missing else today

        if not missing:
            print(f'[回补] 无缺口（最新池文件 {info.get("latest")}，今天 {today}），无需补录')
            return {'window_start': None, 'window_end': None, 'written': {}}

        end_date = today
        print(f'[回补] 检测到窗口缺口 {info.get("gap_days")} 天：'
              f'{start_date} ~ {end_date}（最新池文件 {info.get("latest")}）')

        stocks = _load_portfolio()
        window_news, stock_by_code = fetch_window_news(stocks, start_date, end_date)
        by_date: Dict[str, int] = {}
        for it in window_news:
            by_date[it['time'][:10]] = by_date.get(it['time'][:10], 0) + 1

        if dry_run:
            print(f'[回补][dry-run] 窗口共采集 {len(window_news)} 条（真实时间，不写盘）：')
            for d in missing:
                print(f'  {d}: {by_date.get(d, 0)} 条')
            return {'window_start': start_date, 'window_end': end_date,
                    'dry_run': True, 'collected': by_date, 'written': {}}

        written = write_daily_pools(window_news, missing)
        ev_stats = {'stock_events': 0, 'macro_events': 0}
        if window_news:
            ev_stats = merge_window_events(stocks, window_news, stock_by_code)
        summary = {
            'window_start': start_date,
            'window_end': end_date,
            'gap_days': info.get('gap_days'),
            'written': written,
            'window_total': len(window_news),
            'stock_events_added': ev_stats.get('stock_events', 0),
            'macro_events_added': ev_stats.get('macro_events', 0),
            'ran_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        save_last_run(summary)
        print(f'[回补] 完成：池文件补录 {sum(written.values())} 条/{len(written)} 天，'
              f'个股事件 +{ev_stats.get("stock_events", 0)}，宏观事件 +{ev_stats.get("macro_events", 0)}')
        return summary
    except Exception as e:
        # 顶层兜底：绝不允许崩溃中断主流程
        print(f'[回补][错误] 回补流程异常（已吞掉，不影响报告生成）: {e}')
        return {'error': str(e)}


# ========== 报告章节数据接口（deep_analysis 调用） ==========

def window_items_for_stock(code: str, stock_name: str, start_date: str, end_date: str,
                           max_items: int = 8) -> List[Dict]:
    """从回补后的池文件里匹配某持仓股的窗口期新闻。

    匹配规则：股票名称变体（含去后缀）或概念标签（STOCK_CONCEPT_TAGS）命中标题，
    复用 _match_macro_themes 标注命中主题（用于影响路径描述）。
    返回 [{title, time, source, matched, via, themes}]，按时间倒序，最多 max_items 条。
    """
    from event_tracker import _match_macro_themes  # 复用宏观主题匹配

    name_variants = []
    n = str(stock_name or '').strip()
    if n:
        name_variants.append(n)
        for suf in ('控股', '股份', '集团', '科技', '有限公司'):
            if n.endswith(suf) and len(n) - len(suf) >= 2:
                name_variants.append(n[:-len(suf)])
    concept_tags = STOCK_CONCEPT_TAGS.get(code, [])

    hits: List[Dict] = []
    seen = set()
    for fp in sorted(glob.glob(os.path.join(DATA_DIR, 'news_pool_*.json'))):
        m = POOL_DATE_RE.match(os.path.basename(fp))
        if not m or not (start_date <= m.group(1) <= end_date):
            continue
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                pool = json.load(f)
        except Exception:
            continue
        for item in pool.get('news') or []:
            title = _norm_title(item.get('title'))
            if not title or title in seen:
                continue
            matched_name = [v for v in name_variants if v and v in title]
            matched_concept = [kw for kw in concept_tags if kw and kw in title]
            if not matched_name and not matched_concept:
                continue
            seen.add(title)
            matched_kws = list(dict.fromkeys(matched_name + matched_concept))[:3]
            hits.append({
                'title': title,
                'time': str(item.get('time', ''))[:16],
                'source': item.get('source', ''),
                'matched': matched_kws,
                'via': '名称' if matched_name else '概念',
                'themes': _match_macro_themes(title, '')[:2],
            })
    hits.sort(key=lambda x: x['time'], reverse=True)
    return hits[:max_items]


def main():
    ap = argparse.ArgumentParser(description='非交易日窗口新闻池/事件回补')
    ap.add_argument('--dry-run', action='store_true', help='只打印缺口与计划补录明细，不写盘')
    ap.add_argument('--days', type=int, default=None, help='手动指定回补天数（截至今天），默认自动按缺口')
    args = ap.parse_args()
    run_catchup(days=args.days, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
