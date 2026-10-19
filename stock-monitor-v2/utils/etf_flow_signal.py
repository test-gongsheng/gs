# -*- coding: utf-8 -*-
"""宽基ETF资金流 信号引擎（阶段2，按设计文档3.2/3.3/3.4实现）

信号规则（阈值全部读 data/etf_flow_config.json，调参只改json不改代码）：
- 底信号 = A(金额) + B(广度) + C(固收未同步流入)；全中=信号级，A+B=观察级
- 顶信号 = A(金额) + B(主题共振流出) + C(固收同步流入代理)；全中=真撤退
  【阶段1修正】货币ETF不在交易所份额接口，credit池仅3只，
  C条件改用 credit+bond 两池合计5日净流入作代理（bond池50只能捕捉避险资金）
- 【v1.1增补·极端量级豁免】broad5日流出≤extreme_out_5d(默认1500亿)时，
  顶B/顶C直接判过：5日3000亿级流出只能是机构整体性撤离（钱去向场外现金/
  货币基金，不在交易所快照内，固收代理看不到），不可能是宽基→主题的轮动。
  2026-01实测：bond池同期同为净赎回，单阈值C无法同时区分1月(真撤退)与
  7月(底信号)，故引入量级豁免
- 风格切换 = 宽基流出+主题流入（差额显著）；风偏上升 = 策略风格流出+宽基流入
- 位置过滤：沪深300的750日价格分位（非PE分位，全本地可算，0-100与文档40/70对齐）

阶段3新增（界面集成配套，设计文档第五节）：
- 收盘跑批自动刷新：缺最近交易日份额文件时先自动采集（utils.etf_flow.save_daily_shares，
  try/except包裹，失败仅警告不中断——优雅降级），份额就绪且价格数据覆盖当日时重建
  净流入历史（utils.etf_flow_calc.build_history），再评估信号
- 信号跃迁历史 data/etf_flow/signal_history.json：regime相对上一条发生状态跃迁时append
  {date, regime, strength, interpretation, hs300_close}；hs300_close取当日沪深300收盘价
  （data/etf_flow/prices/sh000300.csv，与750日分位同文件，全本地可算）

输出 data/market_regime.json。
"""
import json
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)  # 支持 `python3 utils/etf_flow_signal.py` 直接运行
FLOW_DIR = os.path.join(BASE, "data", "etf_flow")
HIST_CSV = os.path.join(FLOW_DIR, "etf_flow_history.csv")
CONFIG_JSON = os.path.join(BASE, "data", "etf_flow_config.json")
REGIME_JSON = os.path.join(BASE, "data", "market_regime.json")
SIGNAL_HISTORY_JSON = os.path.join(FLOW_DIR, "signal_history.json")  # 信号跃迁历史（不入git）
HS300_PRICE_CSV = os.path.join(FLOW_DIR, "prices", "sh000300.csv")  # 与750日分位同源收盘价
POOLS_3 = ["broad", "theme", "credit_bond"]  # 输出展示用三池（credit与bond合并展示）

DEFAULT_CONFIG = {
    "_comment": "宽基ETF资金流信号阈值。credit+bond合并：货币ETF不在交易所份额接口，"
                "credit池仅3只，bond池(国债/政金债/信用债/城投债50只)捕捉避险资金，"
                "两池合计5日净流入作为'固收同步流入'代理（设计文档3.2节C条件阶段1修正）。"
                "extreme_out_5d为v1.1增补：broad5日流出达该量级时豁免顶B/顶C。",
    "broad_in_5d": 500,       # 底信号A：近5日宽基累计净流入≥500亿
    "single_day": 300,        # 底信号A：单日净流入≥300亿
    "breadth_day": 0.6,       # 底信号B：当日宽基净流入只数占比≥60%
    "credit_bond_5d": 120,    # 底信号C上限/顶信号C下限：credit+bond合计5日净流入(亿)
    "broad_out_5d": 500,      # 顶信号A：近5日宽基累计净流出≥500亿
    "single_day_out": 300,    # 顶信号A：单日净流出≥300亿
    "switch_gap": 200,        # 风格切换/风偏上升：两池5日差额显著门槛(亿)
    "position_pct_low": 40,   # 位置过滤：低于40%为低位区
    "position_pct_high": 77,  # 位置过滤：高于77%为高位区(回测定参，见etf_flow_backtest.md)
    "extreme_out_5d": 1500,   # v1.1：broad5日净流出达此量级，豁免顶B/顶C(机构整体性撤离)
}


def load_config() -> dict:
    if os.path.exists(CONFIG_JSON):
        with open(CONFIG_JSON, encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    with open(CONFIG_JSON, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    return dict(DEFAULT_CONFIG)


def pool_series(hist: pd.DataFrame, pool: str, col: str = "flow_yi") -> pd.Series:
    return hist[hist["pool"] == pool].set_index("date")[col]


def evaluate(hist: pd.DataFrame, date: str, cfg: dict) -> dict:
    """对指定交易日评估信号，返回market_regime结构"""
    dates = sorted(hist["date"].unique())
    idx = dates.index(date)
    if idx < 5:
        return {"asof_date": date, "regime": "neutral",
                "reason": "历史不足5日，无5日累计窗口"}

    win_dates = dates[idx - 4:idx + 1]  # 近5日含当日
    day = hist[hist["date"] == date].set_index("pool")
    win = hist[hist["date"].isin(win_dates)]

    def flow5(pool):
        return float(win[win["pool"] == pool]["flow_yi"].sum())

    def flow1(pool):
        return float(day.loc[pool, "flow_yi"]) if pool in day.index else 0.0

    # credit+bond合并（固收代理）
    cb5 = flow5("credit") + flow5("bond")
    cb1 = flow1("credit") + flow1("bond")

    broad5 = flow5("broad")
    broad1 = flow1("broad")
    theme5 = flow5("theme")
    theme1 = flow1("theme")
    style5 = flow5("style")
    style1 = flow1("style")

    broad_win = win[win["pool"] == "broad"]
    inflow_days = int((broad_win["flow_yi"] > 0).sum())
    breadth = float(day.loc["broad", "breadth"]) if "broad" in day.index else 0.0
    pct = float(day.loc["broad", "hs300_price_pct"]) if "broad" in day.index else 50.0

    trigger = []

    # ===== 底信号 A+B+C =====
    a_bottom = broad5 >= cfg["broad_in_5d"] or broad1 >= cfg["single_day"]
    trigger.append({"rule": "底A 金额", "hit": a_bottom,
                    "detail": f"宽基5日累计+{broad5:.0f}亿(门槛{cfg['broad_in_5d']}亿)，"
                              f"单日+{broad1:.0f}亿(门槛{cfg['single_day']}亿)"})
    b_bottom = inflow_days >= 4 or breadth >= cfg["breadth_day"]
    trigger.append({"rule": "底B 广度", "hit": b_bottom,
                    "detail": f"近5日净流入天数{inflow_days}/5(门槛4)，"
                              f"当日广度{breadth * 100:.0f}%(门槛{cfg['breadth_day'] * 100:.0f}%)"})
    c_bottom = cb5 < cfg["credit_bond_5d"]
    trigger.append({"rule": "底C 固收未吸金", "hit": c_bottom,
                    "detail": f"credit+bond 5日合计+{cb5:.0f}亿，"
                              f"{'未达' if c_bottom else '达到/超过'}吸金门槛{cfg['credit_bond_5d']}亿"
                              f"（固收代理，阶段1修正）"})

    # ===== 顶信号 A+B+C（v1.1：极端量级豁免顶B/顶C） =====
    a_top = broad5 <= -cfg["broad_out_5d"] or broad1 <= -cfg["single_day_out"]
    extreme = broad5 <= -cfg.get("extreme_out_5d", 1500)  # 天量级流出=机构整体性撤离
    trigger.append({"rule": "顶A 金额", "hit": a_top,
                    "detail": f"宽基5日累计{broad5:.0f}亿(门槛-{cfg['broad_out_5d']}亿)，"
                              f"单日{broad1:.0f}亿(门槛-{cfg['single_day_out']}亿)"})
    b_top = theme5 < 0 or extreme
    trigger.append({"rule": "顶B 主题共振流出", "hit": b_top,
                    "detail": f"主题池5日累计{theme5:+.0f}亿"
                              + ("；极端量级豁免（5日流出≥1500亿级，非轮动）" if extreme
                                 else "（净流入则降级为风格切换，不得报顶）")})
    c_top = cb5 >= cfg["credit_bond_5d"] or extreme
    trigger.append({"rule": "顶C 固收同步净流入", "hit": c_top,
                    "detail": f"credit+bond 5日合计+{cb5:.0f}亿，"
                              f"{'达到' if c_top else '未达到'}门槛{cfg['credit_bond_5d']}亿"
                              f"（固收代理，阶段1修正{';极端量级豁免' if extreme and cb5 < cfg['credit_bond_5d'] else ''}）"})

    # ===== 风格切换 / 风偏上升 =====
    switch = broad5 < 0 and theme5 > 0 and (theme5 - broad5) >= cfg["switch_gap"]
    risk_up = style5 < 0 and broad5 > 0 and (broad5 - style5) >= cfg["switch_gap"]
    trigger.append({"rule": "风格切换 宽基出+主题进", "hit": switch,
                    "detail": f"宽基5日{broad5:+.0f}亿，主题5日{theme5:+.0f}亿，"
                              f"差额{theme5 - broad5:.0f}亿(门槛{cfg['switch_gap']}亿)"})
    trigger.append({"rule": "风偏上升 红利出+宽基进", "hit": risk_up,
                    "detail": f"策略风格5日{style5:+.0f}亿，宽基5日{broad5:+.0f}亿，"
                              f"差额{broad5 - style5:.0f}亿(门槛{cfg['switch_gap']}亿)"})

    # ===== 判定（优先级：顶 > 底 > 风格切换 > 风偏上升 > 观望/中性） =====
    regime = "neutral"
    strength = 0
    note = ""
    if a_top and b_top and c_top:
        regime = "top_signal"
        strength = 80 if pct >= cfg["position_pct_high"] else (60 if pct >= cfg["position_pct_low"] else 40)
        note = (f"高位流出，真撤退" if pct >= cfg["position_pct_high"]
                else ("中位流出，观望级撤退" if pct >= cfg["position_pct_low"] else "低位流出，可能是调仓，强度弱"))
    elif a_bottom and b_bottom and c_bottom:
        if pct >= cfg["position_pct_high"]:
            regime = "watch"  # 高位流入降级为中继提示
            strength = 30
            note = "高位流入·中继提示（价格分位>%d，底信号降级）" % cfg["position_pct_high"]
        else:
            regime = "bottom_signal"
            strength = 90 if pct <= cfg["position_pct_low"] else 65
            note = ("底部区域（价格分位≤%d%%），强" % cfg["position_pct_low"]
                    if pct <= cfg["position_pct_low"] else "回调窗口（价格分位%d-%d%%），中" % (cfg["position_pct_low"], cfg["position_pct_high"]))
    elif a_top and b_top:
        regime = "watch"
        strength = 35
        note = "宽基主题双流出，但固收未同步吸金，观望级"
    elif a_bottom and b_bottom:
        regime = "watch"
        strength = 30
        note = "宽基放量流入，但固收同步吸金，观察级"
    elif switch:
        regime = "structure_switch"
        strength = 55
        note = "宽基撤向主题，风格切换"
    elif risk_up:
        regime = "risk_up"
        strength = 50
        note = "红利撤向宽基，风偏上升"
    else:
        note = "三池资金无显著异动，中性"

    read = (f"【{date}】{note}：宽基5日{broad5:+.0f}亿/单日{broad1:+.0f}亿，"
            f"主题5日{theme5:+.0f}亿，固收代理(credit+bond)5日{cb5:+.0f}亿，"
            f"广度{breadth * 100:.0f}%，沪深300价格分位{pct:.0f}%")

    return {
        "asof_date": date,
        "regime": regime,
        "strength": strength,
        "pools": {
            "broad": {"flow_1d": round(broad1, 2), "flow_5d": round(broad5, 2),
                      "breadth": round(breadth, 4)},
            "theme": {"flow_1d": round(theme1, 2), "flow_5d": round(theme5, 2)},
            "credit_bond": {"flow_1d": round(cb1, 2), "flow_5d": round(cb5, 2)},
            "style": {"flow_1d": round(style1, 2), "flow_5d": round(style5, 2)},
        },
        "hs300_price_pct": pct,
        "interpretation": read,
        "trigger_detail": trigger,
    }


def load_hs300_closes() -> dict:
    """沪深300收盘价 {date_str(YYYYMMDD): float}，取自 prices/sh000300.csv。
    与750日价格分位同一文件（etf_flow_calc.hs300_price_pct），全本地、无网络依赖。
    文件缺失返回空字典。
    """
    if not os.path.exists(HS300_PRICE_CSV):
        return {}
    df = pd.read_csv(HS300_PRICE_CSV, dtype={"date": str})
    df["date"] = df["date"].str.replace("-", "")
    return dict(zip(df["date"], df["close"].astype(float)))


def hs300_close_on(date_str: str) -> "float | None":
    """取指定交易日沪深300收盘价，无数据返回None"""
    return load_hs300_closes().get(date_str)


def load_signal_history() -> list:
    """读取信号跃迁历史，文件不存在/损坏返回空列表"""
    if not os.path.exists(SIGNAL_HISTORY_JSON):
        return []
    try:
        with open(SIGNAL_HISTORY_JSON, encoding="utf-8") as f:
            store = json.load(f)
    except Exception as e:
        print(f"[信号历史] 读取失败（按空历史处理）: {e}")
        return []
    if isinstance(store, dict):
        return store.get("signals", [])
    return store if isinstance(store, list) else []


def update_signal_history(regime: dict) -> bool:
    """状态跃迁检测：当日regime与历史最后一条不同则append新记录。
    历史为空时直接写入首条（首次运行建立基线）。
    返回是否发生跃迁（True=写入了新记录）。
    """
    signals = load_signal_history()
    cur = {
        "date": regime["asof_date"],
        "regime": regime["regime"],
        "strength": regime.get("strength", 0),
        "interpretation": regime.get("interpretation", ""),
        "hs300_close": hs300_close_on(regime["asof_date"]),  # fwd收益计算基准
    }
    if signals and signals[-1].get("regime") == cur["regime"]:
        return False
    signals.append(cur)
    tmp = SIGNAL_HISTORY_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "signals": signals}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SIGNAL_HISTORY_JSON)  # 原子替换，防跑批中断写坏文件
    print(f"[信号历史] 状态跃迁 {signals[-2]['regime'] if len(signals) > 1 else '(起始)'}"
          f" -> {cur['regime']}（{cur['date']}），已记录")
    return True


def current_streak_days(regime: dict) -> int:
    """当前regime已持续交易日数：最近一条跃迁记录日期→asof_date之间的交易日数
    （用沪深300价格文件里的交易日序列计数，全本地）。无历史时返回1。"""
    signals = load_signal_history()
    if not signals:
        return 1
    last_date = signals[-1]["date"]
    closes = load_hs300_closes()
    days = sorted(d for d in closes if last_date <= d <= regime["asof_date"])
    return max(1, len(days))


def refresh_daily_data() -> None:
    """收盘跑批挂接点（阶段3）：确保信号基于最新交易日数据评估。
    1) 最近两个自然日的份额文件都不存在时，自动采集（上交所T+1发布，当日晚上
       未必就绪，故同时尝试昨日）；2) 采集到的新份额只有在价格数据（sh000300）
       覆盖该日时才能计算净流入，此时重建历史；否则打印警告、沿用既有历史评估。
    任何异常仅打印警告，绝不影响每日任务主流程（优雅降级，与系统既有模式一致）。
    """
    today = datetime.now().strftime("%Y%m%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    candidates = [today, yesterday]
    existing = [d for d in candidates
              if os.path.exists(os.path.join(FLOW_DIR, f"shares_{d}.csv"))]
    hist_dates = set()
    if os.path.exists(HIST_CSV):
        hist_dates = set(pd.read_csv(HIST_CSV, dtype={"date": str})["date"])
    # 份额文件已存在且净流入历史已覆盖 → 无需任何动作
    if existing and all(d in hist_dates for d in existing):
        return
    fdate = None
    if not existing:
        print(f"[数据刷新] 份额快照缺失（{today}/{yesterday}），尝试自动采集...")
        try:
            from utils.etf_flow import save_daily_shares
            for d in candidates:
                fdate = save_daily_shares(d)
                if fdate:
                    break
        except Exception as e:
            print(f"[警告] 份额自动采集失败（不影响主流程，沿用既有历史）: {e}")
            return
        if not fdate:
            print("[警告] 上交所份额数据未就绪（T+1发布），沿用既有历史评估")
            return
    else:
        # 份额在、历史缺（常见于首次挂接），补齐差额日期
        fdate = [d for d in existing if d not in hist_dates]
        if not fdate:
            return
        fdate = fdate[-1]
    # 价格数据必须覆盖新份额日期，否则净流入无法计算（全0日会污染信号）
    closes = load_hs300_closes()
    if fdate not in closes:
        print(f"[警告] ETF价格数据未覆盖 {fdate}（收盘价抓取尚未更新），"
              f"跳过历史重建，沿用既有历史评估")
        return
    try:
        from utils.etf_flow_calc import build_history
        print(f"[数据刷新] 份额/价格就绪，重建净流入历史（新增 {fdate}）...")
        build_history()
    except Exception as e:
        print(f"[警告] 净流入历史重建失败（沿用既有历史评估）: {e}")


def main() -> dict:
    refresh_daily_data()  # 收盘跑批：缺数自动采集，失败优雅降级
    hist = pd.read_csv(HIST_CSV, dtype={"date": str})
    cfg = load_config()
    latest = sorted(hist["date"].unique())[-1]
    regime = evaluate(hist, latest, cfg)
    regime["streak_days"] = current_streak_days(regime)  # 界面"连续天数"展示
    with open(REGIME_JSON, "w", encoding="utf-8") as f:
        json.dump(regime, f, ensure_ascii=False, indent=2)
    update_signal_history(regime)  # 状态跃迁落盘（signal_history.json）
    print(json.dumps(regime, ensure_ascii=False, indent=2))
    return regime


if __name__ == "__main__":
    main()
