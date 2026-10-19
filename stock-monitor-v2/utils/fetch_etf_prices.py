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
       "?param={mkt}{code},day,2024-01-01,2026-10-16,800,")


def ensure_index_price() -> None:
    """沪深300指数收盘价——信号引擎的历史分位与交易日历都依赖它，
    且它不在ETF分类表内，必须单独保证存在（修复全新部署引导链缺口）。"""
    fp = os.path.join(PRICE_DIR, "sh000300.csv")
    if os.path.exists(fp):
        return
    bars = fetch_one("sh", "000300")
    if bars:
        pd.DataFrame(bars, columns=["date", "close"]).to_csv(fp, index=False)
        print(f"[指数] 沪深300价格已抓取 {len(bars)} 根")
    else:
        print("[指数] 沪深300抓取失败（下次运行时自动重试）")


def fetch_one(market: str, code: str) -> list:
    """抓取单只ETF日线，返回[(date, close), ...]；失败返回None"""
    url = URL.format(mkt=market, code=code)
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
        if not os.path.exists(fp):
            todo.append((row["market"], row["code"], fp))
    print(f"总数 {len(df)}，待抓取 {len(todo)}")
    ok = fail = 0
    fails = []
    for i, (market, code, fp) in enumerate(todo):
        bars = fetch_one(market, code)
        if bars:
            pd.DataFrame(bars, columns=["date", "close"]).to_csv(fp, index=False)
            ok += 1
        else:
            fail += 1
            fails.append(market + code)
        if (i + 1) % 100 == 0:
            print(f"进度 {i + 1}/{len(todo)} 成功{ok} 失败{fail}", flush=True)
        time.sleep(0.25)
    print(f"完成：成功 {ok}，失败 {fail}")
    if fails:
        print("失败列表：" + ",".join(fails))


if __name__ == "__main__":
    main()
