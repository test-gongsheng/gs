# -*- coding: utf-8 -*-
"""
财联社头条/要闻采集通道
与电报流（akshare stock_info_global_cls）互补：电报是匀速滚动快讯，
头条/要闻/深度稿是另一条编辑精选通道，重要产业新闻常以头条形式发布
但不进电报流（2026-09-21案例：机器人IPO门槛收紧 08:57发布，电报池0命中）。

数据源：cls.cn 首页 __NEXT_DATA__ 服务端渲染JSON（无需JS执行、无需API鉴权）
覆盖位：assembleData.top_article（头条位） + assembleData.depth_list（深度稿）
        + hotArticleData（热门文章） + assembleData.roll_bar（滚动条）

防御：任何失败返回空列表，不抛异常；请求间隔>=3秒；失败重试最多2次；结果带缓存。
"""
import os
import json
import time
import re
import requests
from datetime import datetime
from typing import Dict, List, Optional

CLS_HOME_URL = 'https://www.cls.cn/'
DETAIL_URL_FMT = 'https://www.cls.cn/detail/{id}'

# 缓存：30分钟内重复调用直接返回缓存（避免高频请求被单IP封禁）
_CACHE_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'cache', 'headline_feed_cache.json')
_CACHE_TTL_SECONDS = 1800  # 30分钟
_REQUEST_INTERVAL = 3.0    # 请求间隔>=3秒
_MAX_RETRIES = 2

_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})


def _read_cache() -> Optional[List[Dict]]:
    """读缓存，未过期返回缓存数据，否则None"""
    try:
        if not os.path.exists(_CACHE_FILE):
            return None
        with open(_CACHE_FILE, 'r', encoding='utf-8') as f:
            c = json.load(f)
        if time.time() - c.get('fetched_at', 0) < _CACHE_TTL_SECONDS:
            return c.get('headlines', [])
    except Exception:
        pass
    return None


def _write_cache(headlines: List[Dict]):
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({'fetched_at': time.time(), 'headlines': headlines},
                      f, ensure_ascii=False)
    except Exception:
        pass


def _parse_next_data(html: str) -> Optional[Dict]:
    """从首页HTML提取 __NEXT_DATA__ JSON"""
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None


def _norm_item(item: Dict, section: str) -> Optional[Dict]:
    """标准化单条头条为 {title, url, time, summary}"""
    try:
        title = (item.get('title') or '').strip()
        if not title:
            return None
        art_id = item.get('id')
        url = DETAIL_URL_FMT.format(id=art_id) if art_id else CLS_HOME_URL
        ctime = item.get('ctime')
        if ctime:
            try:
                time_str = datetime.fromtimestamp(int(ctime)).strftime('%Y-%m-%d %H:%M:%S')
            except (OSError, ValueError, OverflowError):
                time_str = ''
        else:
            time_str = ''
        summary = (item.get('brief') or '').strip()[:300]
        return {
            'title': title,
            'url': url,
            'time': time_str,
            'summary': summary,
            'section': section,  # 来源区块：头条/深度/热门/滚动
            'level': item.get('level', ''),  # A/B/C 级（头条位有）
        }
    except Exception:
        return None


def _extract_headlines(next_data: Dict) -> List[Dict]:
    """从 __NEXT_DATA__ 提取所有头条区块的文章列表"""
    headlines = []
    seen_ids = set()

    try:
        pp = next_data.get('props', {}).get('pageProps', {})
    except AttributeError:
        return headlines

    # ---- 区块1: assembleData.top_article（头条位，通常3条，level A/B/C）----
    assemble = pp.get('assembleData', {})
    if isinstance(assemble, dict):
        for item in (assemble.get('top_article') or []):
            if not isinstance(item, dict):
                continue
            nid = item.get('id')
            if nid and nid in seen_ids:
                continue
            norm = _norm_item(item, '头条')
            if norm:
                if nid:
                    seen_ids.add(nid)
                headlines.append(norm)

        # ---- 区块2: assembleData.depth_list（深度稿，通常~30条）----
        for item in (assemble.get('depth_list') or []):
            if not isinstance(item, dict):
                continue
            nid = item.get('id')
            if nid and nid in seen_ids:
                continue
            norm = _norm_item(item, '深度')
            if norm:
                if nid:
                    seen_ids.add(nid)
                headlines.append(norm)

        # ---- 区块3: assembleData.roll_bar（滚动条，单条）----
        roll = assemble.get('roll_bar')
        if isinstance(roll, dict) and roll.get('title'):
            nid = roll.get('id')
            if not nid or nid not in seen_ids:
                norm = _norm_item(roll, '滚动')
                if norm:
                    if nid:
                        seen_ids.add(nid)
                    headlines.append(norm)

    # ---- 区块4: hotArticleData（热门文章，通常~13条）----
    for item in (pp.get('hotArticleData') or []):
        if not isinstance(item, dict):
            continue
        nid = item.get('id')
        if nid and nid in seen_ids:
            continue
        norm = _norm_item(item, '热门')
        if norm:
            if nid:
                seen_ids.add(nid)
            headlines.append(norm)

    # 按时间倒序（最新的在前）
    headlines.sort(key=lambda x: x.get('time', ''), reverse=True)
    return headlines


def fetch_cls_headlines(max_age_hours: int = 72) -> List[Dict]:
    """
    抓财联社首页头条/要闻/深度稿列表。

    参数:
        max_age_hours: 时效窗口（小时），默认72小时——周末/非交易日发布的
                       头条也要能被下一个交易日扫描捞到。
    返回:
        [{title, url, time, summary, section, level}], 任何失败返回 []
    """
    # 缓存命中直接返回
    cached = _read_cache()
    if cached is not None:
        return _filter_by_age(cached, max_age_hours)

    headlines = []
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = _session.get(CLS_HOME_URL, timeout=10)
            resp.encoding = 'utf-8'
            next_data = _parse_next_data(resp.text)
            if next_data:
                headlines = _extract_headlines(next_data)
                if headlines:
                    _write_cache(headlines)
                    break
        except Exception:
            pass
        if attempt < _MAX_RETRIES:
            time.sleep(_REQUEST_INTERVAL)

    return _filter_by_age(headlines, max_age_hours)


def _filter_by_age(headlines: List[Dict], max_age_hours: int) -> List[Dict]:
    """按时效窗口过滤，超龄条目丢弃"""
    if not max_age_hours or not headlines:
        return headlines
    cutoff = time.time() - max_age_hours * 3600
    result = []
    for h in headlines:
        t_str = h.get('time', '')
        try:
            t = datetime.strptime(t_str, '%Y-%m-%d %H:%M:%S').timestamp()
            if t >= cutoff:
                result.append(h)
        except (ValueError, TypeError, OSError):
            # 无时间信息的保留（不丢潜在重要新闻）
            result.append(h)
    return result


def headlines_to_news_pool(headlines: List[Dict]) -> List[Dict]:
    """
    把头条列表转成事件引擎 news_pool 标准格式，
    可直接并入 fetch_cls_telegraph() 的输出统一扫描。
    """
    pool = []
    for h in (headlines or []):
        pool.append({
            'title': h.get('title', ''),
            'content': h.get('summary', ''),
            'time': h.get('time', ''),
            'source': f"财联社-{h.get('section', '头条')}",
        })
    return pool


# ========== 自测 ==========
if __name__ == '__main__':
    print('测试财联社头条采集...\n')
    items = fetch_cls_headlines()
    print(f'获取 {len(items)} 条头条（72小时窗口）\n')
    for i, h in enumerate(items[:15], 1):
        print(f'{i:2d}. [{h["section"]}] {h["title"][:65]}')
        print(f'    {h["time"]} | {h["url"]}')
        if h.get('summary'):
            print(f'    摘要: {h["summary"][:80]}')
        print()
