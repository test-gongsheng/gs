# -*- coding: utf-8 -*-
"""宽基ETF资金流 净流入计算引擎（阶段2）

口径：单只净流入(亿) = (当日份额-前日份额) × 当日收盘价 / 1e8
- 相邻两日取ETF代码交集算Δ（新上市首日无Δ不计，中途退市自动消失）
- 按池汇总：净流入合计 / 广度(净流入只数占比) / top3集中度
- 沪深300价格分位：750日滚动价格分位(0-100)，全本地计算
- 落盘 data/etf_flow/etf_flow_history.csv
"""
import glob
import os
import re

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOW_DIR = os.path.join(BASE, "data", "etf_flow")
PRICE_DIR = os.path.join(FLOW_DIR, "prices")
OUT_CSV = os.path.join(FLOW_DIR, "etf_flow_history.csv")
POOLS = ["broad", "theme", "credit", "style", "bond", "cross_border"]
CLASS_CSV = os.path.join(BASE, "etf_flow_classification.csv")


def load_class_map() -> dict:
    """分类表为池归属的唯一权威（人工可维护），key=market+code -> pool"""
    df = pd.read_csv(CLASS_CSV, dtype={"code": str})
    return dict(zip(df["market"] + df["code"], df["pool"]))


def load_prices() -> dict:
    """读取全部ETF收盘价 {code: {date_str(无横线): close}}"""
    prices = {}
    for fp in glob.glob(os.path.join(PRICE_DIR, "*.csv")):
        code = os.path.basename(fp)[:-4]  # 如 sh510300
        df = pd.read_csv(fp, dtype={"date": str})
        # 统一日期键为无横线格式（与shares_YYYYMMDD.csv对齐）
        df["date"] = df["date"].str.replace("-", "")
        prices[code] = dict(zip(df["date"], df["close"]))
    return prices


def load_shares_files() -> list:
    """按日期排序返回 [(date_str, DataFrame)]"""
    files = sorted(glob.glob(os.path.join(FLOW_DIR, "shares_*.csv")))
    out = []
    for fp in files:
        m = re.search(r"shares_(\d{8})\.csv$", fp)
        if not m:
            continue
        df = pd.read_csv(fp, dtype={"code": str})
        df["key"] = df["market"] + df["code"]
        out.append((m.group(1), df))
    return out


def hs300_price_pct() -> dict:
    """沪深300收盘价750日滚动分位(0-100)，返回 {date_str: pct}"""
    fp = os.path.join(PRICE_DIR, "sh000300.csv")
    df = pd.read_csv(fp, dtype={"date": str})
    df["date"] = df["date"].str.replace("-", "")
    closes = df["close"].astype(float).tolist()
    dates = df["date"].tolist()
    win = 750
    out = {}
    for i in range(len(closes)):
        lo = max(0, i - win + 1)
        window = closes[lo:i + 1]
        cur = closes[i]
        # 分位 = 窗口内 <= 当前价的交易日占比
        pct = sum(1 for v in window if v <= cur) / len(window) * 100.0
        out[dates[i]] = round(pct, 1)
    return out


def build_history() -> pd.DataFrame:
    prices = load_prices()
    pct_map = hs300_price_pct()
    cls_map = load_class_map()
    snapshots = load_shares_files()
    print(f"份额快照 {len(snapshots)} 天，价格表 {len(prices)} 只")

    rows = []
    for i in range(1, len(snapshots)):
        date_prev, df_prev = snapshots[i - 1]
        date_cur, df_cur = snapshots[i]
        # 相邻两日代码交集（新股首日无Δ不计，退市自动消失）
        cur_keys = set(df_cur["key"])
        prev_map = dict(zip(df_prev["key"], df_prev["shares"]))
        flows = []  # (pool, key, flow_yi)
        for _, row in df_cur.iterrows():
            key = row["key"]
            if key not in prev_map:
                continue
            d_shares = row["shares"] - prev_map[key]
            if d_shares == 0:
                continue
            px = prices.get(key, {}).get(date_cur)
            if px is None:
                continue
            flow_yi = d_shares * px / 1e8
            pool = cls_map.get(key, row["pool"])  # 分类表优先
            flows.append((pool, key, flow_yi))

        cur_df = df_cur.set_index("key")
        for pool in POOLS:
            pf = [f for f in flows if f[0] == pool]
            total = sum(f[2] for f in pf)
            in_cnt = sum(1 for f in pf if f[2] > 0)
            pool_size = int((cur_df["pool"] == pool).sum())
            breadth = round(in_cnt / pool_size, 4) if pool_size else 0.0
            pos = sorted((f[2] for f in pf), reverse=True)
            pos_sum = sum(v for v in pos if v > 0)
            top3 = sum(pos[:3]) if pos_sum > 0 else 0.0
            top3_ratio = round(top3 / pos_sum, 4) if pos_sum > 0 else 0.0
            rows.append({
                "date": date_cur,
                "pool": pool,
                "flow_yi": round(total, 2),
                "breadth": breadth,
                "top3_ratio": top3_ratio,
                "hs300_price_pct": pct_map.get(date_cur, ""),
            })
    hist = pd.DataFrame(rows)
    hist.to_csv(OUT_CSV, index=False)
    print(f"落盘 {OUT_CSV}：{len(hist)} 行")
    return hist


if __name__ == "__main__":
    hist = build_history()
    # 校验锚点：2026-10-15 宽基池单日净流入应落在 350~500 亿（新浪口径446亿）
    anchor = hist[hist["date"] == "20261015"]
    print("\n===== 2026-10-15 各池数据（新浪锚点：宽基全市场净流入446亿）=====")
    print(anchor.to_string(index=False))
