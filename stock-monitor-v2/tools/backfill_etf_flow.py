# -*- coding: utf-8 -*-
"""
宽基ETF资金流——沪市历史回填（2026-10-19 阶段1）

回填 2024-01-01 至最近交易日的沪市逐日ETF份额，
落盘 data/etf_flow/shares_YYYYMMDD.csv（每日期一个文件，仅沪市——
深交所无历史回溯接口，T+1起每日增量由 utils/etf_flow.py 采集）。

规则（docs/ETF_FLOW_DESIGN.md 四）：
- 交易日判定：简单跳过周末；法定节假日不管——上交所非交易日返回的
  统计日期会是最近交易日，检测到 统计日期≠请求日期 则跳过该日期文件
- 每次请求 sleep 0.4 秒防频控
- 断点续传：已存在的日期文件直接跳过
- 进度每 50 天打印一次

用法：./venv/bin/python tools/backfill_etf_flow.py
"""
import os
import sys
import time
from datetime import datetime, timedelta

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from utils.etf_flow import collect_shares_sse, classify_etf, DATA_DIR

import pandas as pd

# 回填区间
START_DATE = datetime(2024, 1, 1)
END_DATE = datetime(2026, 10, 16)  # 最近交易日（10/17-18为周末）


def _daterange(start: datetime, end: datetime):
    """逐日迭代 [start, end]"""
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def backfill() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    total = ok = skip = fail = 0
    t0 = time.time()
    for d in _daterange(START_DATE, END_DATE):
        total += 1
        if d.weekday() >= 5:  # 周六日直接跳过
            skip += 1
            continue
        date_str = d.strftime('%Y%m%d')
        path = os.path.join(DATA_DIR, f'shares_{date_str}.csv')
        if os.path.exists(path):  # 断点续传
            skip += 1
            continue

        data, stat_date = collect_shares_sse(date_str)
        if not data:
            fail += 1
            continue
        # 上交所非交易日返回最近交易日的数据：统计日期≠请求日期则跳过
        if stat_date != d.strftime('%Y-%m-%d'):
            print(f"[回填] {date_str} 非交易日（统计日期={stat_date}），跳过")
            skip += 1
            time.sleep(0.4)
            continue

        rows = [{'code': code, 'name': info['name'],
                 'pool': classify_etf(info['name']),
                 'shares': info['shares'], 'market': 'sh'}
                for code, info in data.items()]
        df = pd.DataFrame(rows, columns=['code', 'name', 'pool', 'shares', 'market'])
        df.to_csv(path, index=False, encoding='utf-8-sig')
        ok += 1
        if ok % 50 == 0:
            el = time.time() - t0
            print(f"[回填进度] 成功{ok}天 跳过{skip} 失败{fail} "
                  f"当前{d.strftime('%Y-%m-%d')} 已耗时{el:.0f}秒")
        time.sleep(0.4)  # 防频控

    el = time.time() - t0
    print(f"\n===== 回填完成 =====")
    print(f"区间: {START_DATE.date()} ~ {END_DATE.date()}  总天数{total}")
    print(f"成功: {ok} 天   跳过: {skip} 天   失败: {fail} 天   耗时: {el:.0f} 秒")


if __name__ == '__main__':
    backfill()
