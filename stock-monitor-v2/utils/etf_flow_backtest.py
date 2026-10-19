# -*- coding: utf-8 -*-
"""六节点回测验收（设计文档第四节，上线生死关）

全历史逐日跑信号引擎：
- 全部信号触发记录表 + 之后5/10/20日沪深300涨跌幅
- 六节点专项验收：PASS/FAIL + 当时三池数据快照
节点FAIL允许调config重跑（改json不改代码），直至全节点PASS。
输出 reports/etf_flow_backtest.md。
"""
import json
import os
import sys

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "utils"))
from etf_flow_signal import evaluate, load_config  # noqa: E402

HIST_CSV = os.path.join(BASE, "data", "etf_flow", "etf_flow_history.csv")
OUT_MD = os.path.join(BASE, "reports", "etf_flow_backtest.md")

# 六节点验收基准（设计文档第四节）
NODES = [
    {"id": 1, "window": ("20240201", "20240209"), "require": "bottom_signal",
     "desc": "2024-02上旬（国家队救市底）→ 必须出底信号"},
    {"id": 2, "window": ("20241008", "20241015"), "require": "top_or_extreme",
     "desc": "2024-10-08（3674顶）→ 顶信号或极值预警"},
    {"id": 3, "window": ("20260105", "20260131"), "require": "top_signal",
     "desc": "2026-01（天量流出8440亿+固收吸金）→ 真撤退命中"},
    {"id": 4, "window": ("20260701", "20260731"), "require": "bottom_signal",
     "desc": "2026-07（调整中连续10日净流入760亿）→ 底信号"},
    {"id": 5, "window": ("20260801", "20260831"), "require": "structure_switch_no_top",
     "desc": "2026-08（宽基流出755亿但主题流入291亿）→ 必须判风格切换，不得报顶"},
    {"id": 6, "window": ("20261015", "20261016"), "require": "triggered_relay",
     "desc": "2026-10-15（高位446亿流入+主力大卖）→ 触发但降级为中继提示"},
]


def node_check(regimes: dict, node: dict) -> tuple:
    """返回 (PASS/FAIL, 命中明细, 快照)"""
    lo, hi = node["window"]
    inwin = {d: r for d, r in regimes.items() if lo <= d <= hi}
    req = node["require"]
    if req == "bottom_signal":
        hits = [d for d, r in inwin.items() if r["regime"] == "bottom_signal"]
    elif req == "top_signal":
        hits = [d for d, r in inwin.items() if r["regime"] == "top_signal"]
    elif req == "top_or_extreme":
        hits = [d for d, r in inwin.items()
                if r["regime"] == "top_signal"
                or "中继" in r["interpretation"]  # 高位天量流入降级=极值预警
                or (r["regime"] == "watch" and any(t["rule"].startswith("顶") and t["hit"] for t in r["trigger_detail"]))]
    elif req == "structure_switch_no_top":
        tops = [d for d, r in inwin.items() if r["regime"] == "top_signal"]
        sw = [d for d, r in inwin.items() if r["regime"] == "structure_switch"]
        if tops:
            return "FAIL", f"窗口内出现顶信号{tops}（应判风格切换）", ""
        if sw:
            return "PASS", f"风格切换命中{sw}，无顶信号", ""
        return "FAIL", "窗口内无structure_switch", ""
    else:  # triggered_relay：底触发(A+B)成立但被固收C/位置过滤降级，不得为干净底信号
        hits = [d for d, r in inwin.items()
                if r["regime"] == "watch"
                and any(t["rule"] == "底A 金额" and t["hit"] for t in r["trigger_detail"])
                and any(t["rule"] == "底B 广度" and t["hit"] for t in r["trigger_detail"])]
    ok = "PASS" if hits else "FAIL"
    snap = ""
    if hits:
        r = inwin[hits[0]]
        snap = (f"宽基5日{r['pools']['broad']['flow_5d']:+.0f}亿/单日"
                f"{r['pools']['broad']['flow_1d']:+.0f}亿，主题5日{r['pools']['theme']['flow_5d']:+.0f}亿，"
                f"固收代理5日{r['pools']['credit_bond']['flow_5d']:+.0f}亿，"
                f"广度{r['pools']['broad']['breadth'] * 100:.0f}%，价格分位{r['hs300_price_pct']:.0f}%")
    return ok, f"命中{hits}" if hits else "窗口内无命中", snap


def main() -> None:
    hist = pd.read_csv(HIST_CSV, dtype={"date": str})
    cfg = load_config()
    dates = sorted(hist["date"].unique())

    # 全历史逐日评估
    regimes = {}
    for d in dates:
        r = evaluate(hist, d, cfg)
        if r.get("regime"):
            regimes[d] = r

    # 沪深300前向收益
    idx_df = pd.read_csv(os.path.join(BASE, "data", "etf_flow", "prices", "sh000300.csv"),
                         dtype={"date": str})
    idx_df["date"] = idx_df["date"].str.replace("-", "")
    closes = idx_df.set_index("date")["close"].astype(float)

    def fwd(d: str, n: int):
        ds = dates
        i = ds.index(d)
        if i + n >= len(ds):
            return None
        try:
            return round((closes[ds[i + n]] / closes[d] - 1) * 100, 2)
        except KeyError:
            return None

    sig_dates = [d for d, r in regimes.items()
                 if r["regime"] in ("bottom_signal", "top_signal", "structure_switch", "risk_up")]

    # 统计
    stats = {}
    for kind in ("bottom_signal", "top_signal", "structure_switch"):
        ds = [d for d in sig_dates if regimes[d]["regime"] == kind]
        rets = [fwd(d, 20) for d in ds]
        rets = [x for x in rets if x is not None]
        med = sorted(rets)[len(rets) // 2] if rets else None
        stats[kind] = {"count": len(ds), "median_20d": med, "dates": ds}

    lines = ["# 宽基ETF资金流信号 全历史回测\n",
             f"- 数据区间：{dates[0]} ~ {dates[-1]}（{len(dates)}交易日）",
             "- 注意：历史回填为沪市口径（深交所份额接口仅提供最新一日，设计文档2.1节；"
             "深市宽基约占全市场15-20%）。2026-10-15沪市口径宽基净流入338.9亿，"
             "新浪全市场口径446亿，差额≈深市宽基（文中可验证：创业板ETF易方达55.28+"
             "创业板50华安9.44+创业板广发7.86+中证1000华夏5.39+A500国泰5.39-"
             "A500华泰柏瑞5.31-中证500嘉实0.97≈77.1亿，余为深市小品种）。",
             f"- 阈值config：`data/etf_flow_config.json`",
             f"- 固收代理：credit+bond两池合计5日净流入（货币ETF不在交易所份额接口，阶段1修正）",
             f"- v1.1极端量级豁免：broad5日流出≥1500亿时豁免顶B/顶C（机构整体性撤离，"
             f"钱去向场外现金/货币基金不可见，非主题轮动）\n"]
    lines.append("## 信号触发统计\n")
    lines.append("| 信号 | 次数 | 其后20日沪深300中位收益 |")
    lines.append("|---|---|---|")
    for kind, s in stats.items():
        lines.append(f"| {kind} | {s['count']} | {s['median_20d']}% |")
    lines.append("")

    lines.append("## 全部信号触发记录\n")
    lines.append("| 日期 | 信号 | 强度 | 宽基5日(亿) | 主题5日(亿) | 固收代理5日(亿) | 价格分位 | 后5日% | 后10日% | 后20日% |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for d in sig_dates:
        r = regimes[d]
        p = r["pools"]
        lines.append(f"| {d} | {r['regime']} | {r['strength']} | "
                     f"{p['broad']['flow_5d']:+.0f} | {p['theme']['flow_5d']:+.0f} | "
                     f"{p['credit_bond']['flow_5d']:+.0f} | {r['hs300_price_pct']:.0f} | "
                     f"{fwd(d, 5)} | {fwd(d, 10)} | {fwd(d, 20)} |")
    lines.append("")

    lines.append("## 六节点专项验收\n")
    lines.append("| 节点 | 验收要求 | 结果 | 命中 | 数据快照 |")
    lines.append("|---|---|---|---|---|")
    all_pass = True
    for node in NODES:
        ok, detail, snap = node_check(regimes, node)
        all_pass = all_pass and (ok == "PASS")
        lines.append(f"| {node['id']} | {node['desc']} | **{ok}** | {detail} | {snap} |")
    lines.append("")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"落盘 {OUT_MD}")
    print(f"统计：{json.dumps({k: v['count'] for k, v in stats.items()}, ensure_ascii=False)}")
    print("六节点：" + ("全PASS" if all_pass else "存在FAIL，需调config重跑"))


if __name__ == "__main__":
    main()
