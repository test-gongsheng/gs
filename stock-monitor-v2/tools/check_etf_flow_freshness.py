#!/usr/bin/env python3
"""宽基ETF信号新鲜度体检（2026-10-26起，工作日17:20由OpenClaw cron调用）。

判定规则：交易所T+1发布份额——今天收盘后最多只能算到"最新一个小于今天的
交易日"（交易日历取自 sh000300 价格表，其日期均为真实交易日）。
asof 落后即断链（历史上10-20/10-22已发生三次，均由用户先发现，本体检为此而设）。

输出：FRESH=新鲜（退出0）；STALE=停滞（退出1，附诊断信息）。
"""
import datetime
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGIME = os.path.join(BASE, "data", "market_regime.json")
HS300 = os.path.join(BASE, "data", "etf_flow", "prices", "sh000300.csv")


def main() -> int:
    today = datetime.date.today()
    dates = []
    with open(HS300, encoding="utf-8") as f:
        next(f)  # header: date,close
        for line in f:
            d = line.split(",")[0].strip()
            if d:
                dates.append(datetime.date.fromisoformat(d))
    past = [d for d in dates if d < today]
    expected = max(past).strftime("%Y%m%d") if past else "N/A"

    with open(REGIME, encoding="utf-8") as f:
        asof = json.load(f).get("asof_date", "N/A")

    if asof >= expected:  # YYYYMMDD 等宽字符串比较安全
        print(f"FRESH asof={asof} expected<={expected}")
        return 0

    print(f"STALE 宽基ETF信号数据停滞：asof={asof}，期望至少到 {expected}"
          f"（最新已发布交易日）")
    for p in ["data/etf_flow/etf_flow_history.csv",
              f"data/etf_flow/shares_{expected}.csv"]:
        fp = os.path.join(BASE, p)
        if os.path.exists(fp):
            m = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
            print(f"  {p} mtime={m.strftime('%m-%d %H:%M')}")
        else:
            print(f"  {p} 不存在")
    return 1


if __name__ == "__main__":
    sys.exit(main())
