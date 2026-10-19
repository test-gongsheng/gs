# -*- coding: utf-8 -*-
"""
宽基ETF资金流信号系统——采集与分类模块（2026-10-19 阶段1）

数据源（docs/ETF_FLOW_DESIGN.md 2.1节，服务器实测结论）：
- 沪市：ak.fund_etf_scale_sse(date='YYYYMMDD')，逐日可回溯2024，约922只，主源
- 深市：fund.szse.cn/api/report/ShowReport（xlsx），仅最新一天，约1074只
  （akshare 的 fund_etf_scale_szse 有 bytes 兼容 bug，故手动 requests + BytesIO）
- 东财全部接口禁用（服务器IP被403）

分类规则（优先级：固收 > 固收其他(bond) > 策略风格 > 宽基 > 跨境 > 主题）：
- credit       货币/添益/日利/短融
- bond         含"债"/国开/政金（固收其他，第六类不入三池信号，避免污染主题池）
- style        红利/低波/自由现金流（含"红利"即归此类，优先于宽基）
- broad        沪深300/上证50/中证500/1000/2000/创业板/科创50/100/A500/A50/
               上证指数/深证100/中证800/MSCI
- cross_border 标普/纳指/日经/德国/法国/沙特/东南亚/港股通/恒生/中概/H股（第五类，单独跟踪不入三池信号）
- theme        其余行业主题

份额单位：份（原始值，未除以1e8）。落盘 data/etf_flow/shares_YYYYMMDD.csv。
"""
import io
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 落盘目录（data/etf_flow/，不入git）
DATA_DIR = os.path.join(_PROJECT_ROOT, 'data', 'etf_flow')

# ---- 分类关键词（小写匹配，优先级自上而下）----

# 固收池：只放货币+短融（机构常规配置不构成撤退信号）
# 说明：上交所份额接口不含货币ETF（实测其ETF类型仅跨市/单市/跨境/其他），
# 本池实际可得标的极少（511360短融ETF+深市个别货币ETF），固收信号阶段2再议
_CREDIT_KW = ['货币', '添益', '日利', '短融', '快线']

# 固收其他（第六类，不入三池）：政金债/国债/信用债/可转债等——
# 按设计文档2.2节"机构常规配置不构成撤退信号"，单独打标排除，避免污染主题池
_BOND_KW = ['债', '国开', '政金']

# 策略风格池：红利/低波/自由现金流
_STYLE_KW = ['红利', '低波', '自由现金流']

# 宽基池：核心宽基指数关键词
_BROAD_KW = ['300', '上证50', '中证500', '中证1000', '中证2000', '创业板',
             '科创50', '科创100', 'a500', 'a50', '上证指数', '深证100',
             '中证800', 'msci']

# 跨境池：第五类，单独跟踪不入三池信号
_CROSS_BORDER_KW = ['标普', '纳指', '日经', '德国', '法国', '沙特',
                    '东南亚', '港股通', '恒生', '中概', 'h股']


def classify_etf(name: str) -> str:
    """按基金简称关键词规则分类，返回池标识：credit/style/broad/cross_border/theme。

    优先级：固收 > 固收其他 > 策略风格 > 宽基 > 跨境 > 主题（兜底）。
    说明：宽基关键词里的 '300' 是裸匹配（命中"沪深300"），若名称同时含
    策略风格关键词（如"红利300"）已被上面拦截，不会被误判为宽基。
    """
    n = str(name).lower()
    for kw in _CREDIT_KW:
        if kw in n:
            return 'credit'
    for kw in _BOND_KW:
        if kw in n:
            return 'bond'
    for kw in _STYLE_KW:
        if kw in n:
            return 'style'
    for kw in _BROAD_KW:
        if kw in n:
            return 'broad'
    for kw in _CROSS_BORDER_KW:
        if kw in n:
            return 'cross_border'
    return 'theme'


def collect_shares_sse(date_str: str) -> Tuple[Dict[str, dict], Optional[str]]:
    """采集沪市全量ETF份额。

    参数：date_str 格式 'YYYYMMDD'
    返回：( {代码: {'name': 简称, 'shares': 份额(份), 'stat_date': 统计日期}}, 统计日期 )
    统计日期 = 上交所实际返回的'统计日期'（YYYY-MM-DD）。
    非交易日时上交所返回的是最近交易日的数据，此时 stat_date != 请求日期，
    调用方据此跳过该日期文件。
    采集失败返回 ( {}, None )。
    """
    import akshare as ak
    req_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    try:
        df = ak.fund_etf_scale_sse(date=date_str)
    except Exception as e:
        print(f"[沪市采集] {req_date} 请求异常: {e}")
        return {}, None
    if df is None or df.empty:
        print(f"[沪市采集] {req_date} 返回空数据")
        return {}, None
    stat_date = str(df['统计日期'].iloc[0])[:10]
    result: Dict[str, dict] = {}
    for _, row in df.iterrows():
        code = str(row['基金代码']).strip().zfill(6)
        try:
            shares = float(row['基金份额'])
        except (TypeError, ValueError):
            continue
        result[code] = {
            'name': str(row['基金简称']).strip(),
            'shares': shares,
            'stat_date': stat_date,
        }
    return result, stat_date


def collect_shares_szse() -> Tuple[Dict[str, dict], Optional[str]]:
    """采集深市全量ETF份额（仅最新一天，深交所无历史回溯接口）。

    返回：( {代码: {'name': 简称, 'shares': 份额(份), 'stat_date': None}}, None )
    深交所接口不返回统计日期，stat_date 置 None，由调用方决定落盘日期。
    采集失败返回 ( {}, None )。
    """
    url = 'https://fund.szse.cn/api/report/ShowReport'
    params = {'SHOWTYPE': 'xlsx', 'CATALOGID': '1000_lf', 'TABKEY': 'tab1',
              'random': '0.07610353191740105'}
    headers = {'Referer': 'https://fund.szse.cn/marketdata/fundslist/index.html'}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        df = pd.read_excel(io.BytesIO(r.content))
    except Exception as e:
        print(f"[深市采集] 请求异常: {e}")
        return {}, None
    if df is None or df.empty:
        print("[深市采集] 返回空数据")
        return {}, None
    # 深交所该接口混有LOF/不动产基金（实测761只ETF+285只LOF+28只REITs），
    # 仅保留基金类别为ETF的行（设计文档口径：全量ETF）
    df = df[df['基金类别'] == 'ETF']
    result: Dict[str, dict] = {}
    for _, row in df.iterrows():
        code = str(row['基金代码']).strip().zfill(6)
        raw = str(row['当前规模(份)']).replace(',', '').strip()
        try:
            shares = float(raw)
        except (TypeError, ValueError):
            continue
        result[code] = {
            'name': str(row['基金简称']).strip(),
            'shares': shares,
            'stat_date': None,
        }
    return result, None


def save_daily_shares(date_str: str) -> Optional[str]:
    """合并两市份额+分类，落盘 data/etf_flow/shares_YYYYMMDD.csv。

    文件名以上交所实际统计日期为准（若上交所返回的统计日期与请求日期不符，
    用实际统计日期命名——处理周末/节假日后的日期漂移）。
    返回落盘文件对应的日期串（YYYYMMDD），失败返回 None。
    列：code,name,pool,shares,market
    """
    sse, stat_date = collect_shares_sse(date_str)
    if not sse:
        print(f"[落盘] {date_str} 沪市数据为空，放弃本次采集")
        return None
    # 上交所统计日期为准命名文件
    file_date = (stat_date or date_str).replace('-', '')
    szse, _ = collect_shares_szse()

    rows: List[dict] = []
    for code, info in sse.items():
        rows.append({'code': code, 'name': info['name'],
                     'pool': classify_etf(info['name']),
                     'shares': info['shares'], 'market': 'sh'})
    for code, info in szse.items():
        rows.append({'code': code, 'name': info['name'],
                     'pool': classify_etf(info['name']),
                     'shares': info['shares'], 'market': 'sz'})

    os.makedirs(DATA_DIR, exist_ok=True)
    df = pd.DataFrame(rows, columns=['code', 'name', 'pool', 'shares', 'market'])
    path = os.path.join(DATA_DIR, f'shares_{file_date}.csv')
    df.to_csv(path, index=False, encoding='utf-8-sig')
    print(f"[落盘] {path} 共{len(df)}只（沪市{len(sse)}+深市{len(szse)}）")
    return file_date


if __name__ == '__main__':
    # 自测：采集最近交易日并打印三池ETF数量和宽基池top5
    today = datetime.now().strftime('%Y%m%d')
    fdate = save_daily_shares(today)
    if fdate is None:
        # 今天数据未发布时回退到昨天（上交所T+1发布）
        from datetime import timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
        print(f"[自测] 今日数据未就绪，回退请求昨日 {yesterday}")
        fdate = save_daily_shares(yesterday)
    if fdate:
        df = pd.read_csv(os.path.join(DATA_DIR, f'shares_{fdate}.csv'))
        print('\n===== 自测输出 =====')
        for pool in ['broad', 'theme', 'credit', 'style', 'bond', 'cross_border']:
            sub = df[df['pool'] == pool]
            print(f"{pool:>12s}: {len(sub)} 只")
        broad = df[df['pool'] == 'broad'].nlargest(5, 'shares')
        print('\n宽基池 top5（份额，亿份）：')
        for _, r in broad.iterrows():
            print(f"  {r['code']} {r['name']}  {r['shares'] / 1e8:.2f}")
