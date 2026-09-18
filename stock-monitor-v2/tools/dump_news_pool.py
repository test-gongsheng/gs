#!/usr/bin/env python3
"""
tools/dump_news_pool.py
导出当日新闻池供AI事件关联分析（Layer-LLM）使用。
用法: python3 tools/dump_news_pool.py
输出: data/news_pool_YYYY-MM-DD.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from event_tracker import fetch_cls_telegraph  # noqa: E402


def main():
    news = fetch_cls_telegraph() or []
    # 过滤：只保留可能有事件价值的长标题，截断到150条控制token
    filtered = []
    for n in news:
        title = (n.get('title') or '').strip()
        if len(title) < 8:
            continue
        filtered.append({
            'title': title,
            'time': n.get('time', '')[:16],
            'source': n.get('source', '财联社'),
        })
    filtered = filtered[:150]

    today = __import__('datetime').datetime.now().strftime('%Y-%m-%d')
    out = os.path.join(os.path.dirname(__file__), '..', 'data', f'news_pool_{today}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'date': today, 'count': len(filtered), 'news': filtered},
                  f, ensure_ascii=False, indent=1)
    print(f'[OK] 新闻池已导出 {len(filtered)} 条 -> {out}')


if __name__ == '__main__':
    main()
