# -*- coding: utf-8 -*-
"""ETF历史收盘价批量抓取（腾讯proxy.finance.qq.com，断点续传）

阶段2价格源：主域web.ifzq.gtimg.cn被WAF拦截(501)，
proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get 实测可用。
单只一次请求拿全区间（800根K线覆盖2023-06~2026-10），
不复权口径（ETF分红除息日用raw价计算资金流更准确）。
"""
import json
import os
import time
import urllib.request

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRICE_DIR = os.path.join(BASE, "data", "etf_flow", "prices")
CLASS_CSV = os.path.join(BASE, "etf_flow_classification.csv")
URL = ("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
       "?param={mkt}{code},day,2024-01-01,{end},800,")


def _today() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")


def merge_save(fp: str, bars: list) -> int:
    """增量合并：已有数据只追加新日期；但当日本地已有bar时用新值覆盖
    （盘中抓取会写入未完结bar的当前价，收盘后重跑须以收盘价修正——
    修复(2026-10-23)：原实现只追加不覆盖，盘中价一旦写入永久残留）。
    返回新增根数（覆盖不计数）。bars=[(date,close),...]"""
    old = {}
    if os.path.exists(fp):
        try:
            df = pd.read_csv(fp, dtype={"date": str})
            old = dict(zip(df["date"], df["close"].astype(float)))
        except Exception:
            old = {}
    merged = dict(old)
    n_new = 0
    n_override = 0
    today = _today()
    for d, c in bars:
        if d not in merged:
            merged[d] = c
            n_new += 1
        elif d == today:
            merged[d] = c  # 当日bar：以最新抓取值覆盖（收盘后为收盘价）
            n_override += 1
    if n_new > 0 or n_override > 0 or not os.path.exists(fp):
        df = pd.DataFrame(sorted(merged.items()), columns=["date", "close"])
        df.to_csv(fp, index=False)
    return n_new


def ensure_index_price() -> None:
    """沪深300指数收盘价——信号引擎的历史分位与交易日历都依赖它，
    且它不在ETF分类表内，必须单独保证存在并每日增量更新（修复：原实现只在文件
    缺失时抓一次，导致历史分位永远停留在首次抓取日，2026-10-20 用户实测数据日
    停滞的根因之一）。"""
    fp = os.path.join(PRICE_DIR, "sh000300.csv")
    bars = fetch_one("sh", "000300")
    if bars:
        n = merge_save(fp, bars)
        print(f"[指数] 沪深300价格已更新（新增 {n} 根，累计 {len(bars)} 根）")
    else:
        print("[指数] 沪深300抓取失败（下次运行时自动重试）")


def fetch_one(market: str, code: str) -> list:
    """抓取单只ETF日线，返回[(date, close), ...]；失败返回None"""
    url = URL.format(mkt=market, code=code, end=_today())
    req = urllib.request.Request(url, headers={"Referer": "https://gu.qq.com/"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        node = payload["data"][market + code]
        arr = node.get("day") or node.get("qfqday") or []
        return [(row[0], float(row[2])) for row in arr]
    except Exception:
        return None


def main() -> None:
    os.makedirs(PRICE_DIR, exist_ok=True)
    ensure_index_price()
    df = pd.read_csv(CLASS_CSV, dtype={"code": str})
    todo = []
    for _, row in df.iterrows():
        fp = os.path.join(PRICE_DIR, f"{row['market']}{row['code']}.csv")
        # 增量模式：已存在的文件也每日追新（收盘价是流量计算的必需输入，停更即断档）
        todo.append((row["market"], row["code"], fp))
    print(f"总数 {len(df)}，增量更新 {len(todo)}")
    ok = fail = skip = 0
    fails = []
    total_new = 0
    for i, (market, code, fp) in enumerate(todo):
        bars = fetch_one(market, code)
        if bars:
            n = merge_save(fp, bars)
            total_new += n
            if n:
                ok += 1
            else:
                skip += 1
        else:
            fail += 1
            fails.append(market + code)
        if (i + 1) % 100 == 0:
            print(f"进度 {i + 1}/{len(todo)} 新增{ok} 无新bar{skip} 失败{fail}", flush=True)
        time.sleep(0.2)
    print(f"完成：新增 {ok}，无更新 {skip}，失败 {fail}，共新入 {total_new} 根K线")
    if fails:
        print("失败列表：" + ",".join(fails))


if __name__ == "__main__":
    main()
