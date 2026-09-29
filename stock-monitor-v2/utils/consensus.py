# -*- coding: utf-8 -*-
"""
投行一致预期模块（卖方研报级数据底座）

合并两类公开数据源：
1. 同花顺盈利预测（ak.stock_profit_forecast_ths）——机构数/净利与EPS预测的 min/mean/max
2. 东方财富个股研报（ak.stock_research_report_em）——评级分布/最新研报/分机构盈利预测

⚠️ 部署注意（重要）：
- 港股（00700/09988/00285 等）东财研报接口会直接报错，同花顺预测页无覆盖，均属预期行为，
  此时 get_consensus 返回 None，调用方必须降级为"暂无机构一致预期数据"，不得编造。
- 部分云主机 IP 段访问东财/同花顺会超时，单接口失败不影响另一接口，全部失败才返回 None。
- 本模块不输出目标价（东财研报接口无目标价字段），分歧度用"最高预测/最低预测"区间宽度代替。

服务器验证记录（2026-09-21）：
- 301308/601600/002594 两个接口均可用；00700 东财接口 KeyError（预期降级路径）。
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional


def _fetch_profit_forecast_ths(code: str) -> Optional[List[Dict]]:
    """
    同花顺盈利预测：未来三个年度的净利润/EPS 机构预测（min/mean/max）。

    Returns:
        [{'year': '2026', 'org_count': 8, 'profit_min': 110.97, 'profit_mean': 142.73,
          'profit_max': 199.69, 'eps_min': ..., 'eps_mean': ..., 'eps_max': ...}, ...]
        失败返回 None。金额单位：亿元，EPS单位：元。
    """
    try:
        import akshare as ak
        df_np = ak.stock_profit_forecast_ths(symbol=code, indicator='预测年报净利润')
        df_eps = ak.stock_profit_forecast_ths(symbol=code, indicator='预测年报每股收益')
        if df_np is None or df_np.empty:
            return None

        def _row_to_float(row, col):
            try:
                return float(row.get(col))
            except (TypeError, ValueError):
                return None

        np_map = {}
        for _, row in df_np.iterrows():
            year = str(row.get('年度', '')).strip()
            if not year:
                continue
            np_map[year] = {
                'org_count': int(_row_to_float(row, '预测机构数') or 0),
                'profit_min': _row_to_float(row, '最小值'),
                'profit_mean': _row_to_float(row, '均值'),
                'profit_max': _row_to_float(row, '最大值'),
            }

        eps_map = {}
        if df_eps is not None and not df_eps.empty:
            for _, row in df_eps.iterrows():
                year = str(row.get('年度', '')).strip()
                if not year:
                    continue
                eps_map[year] = {
                    'eps_min': _row_to_float(row, '最小值'),
                    'eps_mean': _row_to_float(row, '均值'),
                    'eps_max': _row_to_float(row, '最大值'),
                }

        result = []
        for year in sorted(np_map.keys()):
            item = {'year': year}
            item.update(np_map[year])
            item.update(eps_map.get(year, {}))
            result.append(item)
        return result or None
    except Exception as e:
        print(f"[一致预期] 同花顺盈利预测获取失败 {code}: {e}")
        return None


def _fetch_research_reports_em(code: str) -> Optional[Dict]:
    """
    东方财富个股研报：近90天评级分布 + 最新3份研报 + 当年多空代表机构 + 分机构盈利预测明细。

    Returns:
        {'rating_90d': {'买入': x, '增持': y, ...}, 'rating_total_90d': n,
         'recent_reports': [{'title','org','rating','date'} x3],
         'bull_bear': {'high': {...}, 'low': {...}},       # 当年研报EPS最高/最低机构
         'org_eps': [                                       # 分机构最新盈利预测（近180天，每机构取最新一份）
           {'org': '爱建证券', 'rating': '买入', 'date': '2026-08-13',
            'eps': {'2026': 47.2, '2027': 51.78, '2028': 53.75}}, ...]
        }
        失败返回 None。
    """
    try:
        import akshare as ak
        import pandas as pd
        df = ak.stock_research_report_em(symbol=code)
        if df is None or df.empty:
            return None

        df = df.copy()
        df['日期'] = pd.to_datetime(df['日期'])
        cutoff = pd.Timestamp(datetime.now() - timedelta(days=90))
        recent = df[df['日期'] >= cutoff].sort_values('日期', ascending=False)

        rating_counts = {}
        for r in recent['东财评级'].fillna('未知'):
            rating_counts[str(r)] = rating_counts.get(str(r), 0) + 1

        recent_reports = []
        for _, row in recent.head(3).iterrows():
            recent_reports.append({
                'title': str(row.get('报告名称', '')),
                'org': str(row.get('机构', '')),
                'rating': str(row.get('东财评级', '')),
                'date': row['日期'].strftime('%Y-%m-%d'),
            })

        # 多空两派代表机构：取当年研报中盈利预测-EPS最高/最低者（列名随年份变化，动态匹配）
        bull_bear = None
        try:
            cur_year = str(datetime.now().year)
            eps_col = None
            for col in df.columns:
                m = re.match(r'^(\d{4})-盈利预测-收益$', str(col))
                if m and m.group(1) == cur_year:
                    eps_col = col
                    break
            if eps_col:
                year_df = df[(df['日期'] >= pd.Timestamp(f'{cur_year}-01-01'))]
                year_df = year_df[year_df[eps_col].notna() & (year_df[eps_col] > 0)]
                if not year_df.empty:
                    hi = year_df.loc[year_df[eps_col].idxmax()]
                    lo = year_df.loc[year_df[eps_col].idxmin()]
                    bull_bear = {
                        'high': {'org': str(hi.get('机构', '')), 'eps': float(hi[eps_col]),
                                 'date': hi['日期'].strftime('%Y-%m-%d'),
                                 'title': str(hi.get('报告名称', ''))},
                        'low': {'org': str(lo.get('机构', '')), 'eps': float(lo[eps_col]),
                                'date': lo['日期'].strftime('%Y-%m-%d'),
                                'title': str(lo.get('报告名称', ''))},
                    }
        except Exception as e:
            print(f"[一致预期] 多空代表机构提取失败 {code}: {e}")

        # 分机构盈利预测明细：近180天研报，每机构取最新一份的各年EPS预测
        org_eps = []
        try:
            cutoff180 = pd.Timestamp(datetime.now() - timedelta(days=180))
            recent180 = df[df['日期'] >= cutoff180].sort_values('日期', ascending=False)
            seen_orgs = set()
            for _, row in recent180.iterrows():
                org = str(row.get('机构', '')).strip()
                if not org or org in seen_orgs:
                    continue
                eps_map = {}
                for col in df.columns:
                    m = re.match(r'^(\d{4})-盈利预测-收益$', str(col))
                    if m:
                        val = row.get(col)
                        try:
                            fval = float(val)
                            if fval > 0:
                                eps_map[m.group(1)] = round(fval, 2)
                        except (TypeError, ValueError):
                            pass
                seen_orgs.add(org)
                org_eps.append({
                    'org': org,
                    'rating': str(row.get('东财评级', '')),
                    'date': row['日期'].strftime('%Y-%m-%d'),
                    'eps': eps_map,
                })
        except Exception as e:
            print(f"[一致预期] 分机构预测提取失败 {code}: {e}")

        return {
            'rating_90d': rating_counts,
            'rating_total_90d': int(len(recent)),
            'recent_reports': recent_reports,
            'bull_bear': bull_bear,
            'org_eps': org_eps,
        }
    except Exception as e:
        print(f"[一致预期] 东财研报获取失败 {code}: {e}")
        return None


# ========== 港股一致预期（东财港股盈利预测，含国际投行目标价） ==========

# 港股研报市场常见国际投行（按券商简称模糊匹配）
INTL_BROKER_KEYWORDS = [
    '高盛', '摩根士丹利', '摩根大通', '花旗', '瑞银', '美银', '汇丰', '野村',
    '大和', '星展', '大华继显', '麦格理', '巴克莱', '法巴', '巴黎银行', '德银',
    '德意志', '瑞穗', '杰富瑞', '富瑞', '桑福德', '伯恩斯坦', '汇丰前海',
    '东英', '未来资产', '三星证券', '凯基', '元大', '富邦', '群益', '永丰金',
]


def classify_broker(name: str) -> str:
    """券商分类：国际投行 / 中资。未命中外资名录的统一归中资及其他（含港资、台资）。"""
    n = str(name or '')
    for kw in INTL_BROKER_KEYWORDS:
        if kw in n:
            return '国际投行'
    return '中资'


def _norm_hk_code(code: str) -> str:
    """归一化为东财港股接口的5位代码：'hk00700'/'00700'/'700' -> '00700'"""
    digits = ''.join(ch for ch in str(code) if ch.isdigit())
    return digits.zfill(5)[-5:]


def _fetch_hk_forecast_et(code: str) -> Optional[List[Dict]]:
    """
    东财港股盈利预测（ak.stock_hk_profit_forecast_et）：分券商×财年多行。

    Returns:
        [{'year': '2026', 'broker': '高盛', 'type': '国际投行', 'profit_yi': 2475.86,
          'eps': 29.73, 'rating': '买入', 'target_price': 670.0, 'date': '2026-08-31'}, ...]
        利润已换算为亿元（源数据为百万元）；EPS已换算为元/股（源数据为分/仙）。
        失败返回 None。
    """
    try:
        import akshare as ak
        df = ak.stock_hk_profit_forecast_et(symbol=_norm_hk_code(code))
        if df is None or df.empty:
            return None
        rows = []
        for _, r in df.iterrows():
            try:
                profit_m = float(r.get('纯利/亏损'))
            except (TypeError, ValueError):
                profit_m = None
            try:
                eps_raw = float(r.get('每股盈利'))
            except (TypeError, ValueError):
                eps_raw = None
            try:
                tgt = float(r.get('目标价'))
                if tgt != tgt or tgt <= 0:  # NaN或非法值
                    tgt = None
            except (TypeError, ValueError):
                tgt = None
            broker = str(r.get('证券商', '')).strip()
            if not broker:
                continue
            rows.append({
                'year': str(r.get('财政年度', '')).strip(),
                'broker': broker,
                'type': classify_broker(broker),
                'profit_yi': round(profit_m / 100, 2) if profit_m is not None else None,
                'eps': round(eps_raw / 100, 2) if eps_raw is not None else None,
                'rating': str(r.get('评级', '')).strip(),
                'target_price': tgt,
                'date': str(r.get('更新日期', ''))[:10],
            })
        return rows or None
    except Exception as e:
        print(f'[港股一致预期] 东财接口失败 {code}: {e}')
        return None


def _rating_side(rating: str) -> str:
    """评级归一化：bullish / neutral / bearish"""
    r = str(rating or '')
    if any(k in r for k in ('买入', '增持', '优于大市', '跑赢', '推荐', '买进', '确信')):
        return 'bullish'
    if any(k in r for k in ('减持', '卖出', '跑输', '低配', '逊于', '沽出', '沽售')):
        return 'bearish'
    return 'neutral'


def get_hk_consensus(code: str) -> Optional[Dict]:
    """
    港股投行一致预期（东财港股盈利预测，含国际投行目标价与评级）。

    返回结构与 get_consensus 对齐（years/org_count/divergence/rating_90d/recent_reports/
    org_eps/bull_bear），另增港股专属字段：
      'target_price': {'mean','median','max','min','count'} | None
      'intl_summary': {'count','target_mean','target_max','target_min','bull','neutral','bear','names'} | None
      'cn_summary':   同上结构
      'market': '港股'
    纯利单位：亿元；EPS单位：元/股（各券商币种口径可能为人民币或港币，以原始研报为准）。
    无数据/接口失败返回 None。
    """
    rows = _fetch_hk_forecast_et(code)
    if not rows:
        return None

    today = datetime.now()

    def _recent(row, days):
        try:
            d = datetime.strptime(row['date'], '%Y-%m-%d')
            return (today - d).days <= days
        except Exception:
            return False

    # 年度聚合（近365天更新的预测才参与）
    years_agg = {}
    for r in rows:
        if not r['year'] or not _recent(r, 365):
            continue
        a = years_agg.setdefault(r['year'], {'profits': [], 'epses': [], 'brokers': set()})
        if r['profit_yi'] is not None:
            a['profits'].append(r['profit_yi'])
            a['brokers'].add(r['broker'])
        if r['eps'] is not None:
            a['epses'].append(r['eps'])

    years = []
    for y in sorted(years_agg.keys()):
        a = years_agg[y]
        if not a['profits']:
            continue
        years.append({
            'year': y,
            'org_count': len(a['brokers']),
            'profit_min': round(min(a['profits']), 2),
            'profit_mean': round(sum(a['profits']) / len(a['profits']), 2),
            'profit_max': round(max(a['profits']), 2),
            'eps_min': round(min(a['epses']), 2) if a['epses'] else None,
            'eps_mean': round(sum(a['epses']) / len(a['epses']), 2) if a['epses'] else None,
            'eps_max': round(max(a['epses']), 2) if a['epses'] else None,
        })

    if not years:
        return None

    cur = years[0]
    p_min, p_max = cur.get('profit_min'), cur.get('profit_max')
    divergence = round(p_max / p_min, 2) if (p_min and p_max and p_min > 0) else None

    # 多空代表（当年EPS最高/最低券商）
    cur_year = cur['year']
    cy_rows = [r for r in rows if r['year'] == cur_year and r['eps'] is not None and _recent(r, 365)]
    bull_bear = None
    if cy_rows:
        hi = max(cy_rows, key=lambda x: x['eps'])
        lo = min(cy_rows, key=lambda x: x['eps'])
        bull_bear = {
            'high': {'org': hi['broker'], 'eps': hi['eps'], 'date': hi['date'], 'title': f"{cur_year}财年盈利预测"},
            'low': {'org': lo['broker'], 'eps': lo['eps'], 'date': lo['date'], 'title': f"{cur_year}财年盈利预测"},
        }

    # 分券商明细（每券商取最新一行，带各年EPS）
    by_broker = {}
    for r in sorted(rows, key=lambda x: x['date'], reverse=True):
        if r['broker'] not in by_broker:
            by_broker[r['broker']] = {
                'org': r['broker'], 'type': r['type'], 'rating': r['rating'],
                'date': r['date'], 'target_price': r['target_price'], 'eps': {},
            }
        if r['year'] and r['eps'] is not None and r['year'] not in by_broker[r['broker']]['eps']:
            by_broker[r['broker']]['eps'][r['year']] = r['eps']
    org_eps = sorted(by_broker.values(),
                     key=lambda x: (x['type'] != '国际投行',
                                    -(int(x['date'].replace('-', '')) if x['date'] else 0)))

    # 近90天评级分布（原始评级 + 归一化阵营）
    recent90 = [r for r in rows if _recent(r, 90) and r['rating'] and r['rating'] not in ('--', 'nan', 'None')]
    side_cn = {'bullish': '看多', 'neutral': '中性', 'bearish': '看空'}
    rating_90d, rating_side_90d = {}, {}
    for r in recent90:
        rating_90d[r['rating']] = rating_90d.get(r['rating'], 0) + 1
        side = _rating_side(r['rating'])
        rating_side_90d[side_cn[side]] = rating_side_90d.get(side_cn[side], 0) + 1

    # 目标价统计（近365天）
    def _tp_stats(sub):
        tps = [r['target_price'] for r in sub if r['target_price'] is not None and _recent(r, 365)]
        if not tps:
            return None
        tps_s = sorted(tps)
        return {
            'count': len(tps),
            'mean': round(sum(tps) / len(tps), 2),
            'median': round(tps_s[len(tps_s) // 2], 2),
            'max': round(max(tps), 2),
            'min': round(min(tps), 2),
        }

    intl_rows = [r for r in rows if r['type'] == '国际投行']
    cn_rows = [r for r in rows if r['type'] != '国际投行']

    def _grp_summary(sub):
        if not sub:
            return None
        recent_sub = [r for r in sub if _recent(r, 365) and r['rating'] and r['rating'] not in ('--', 'nan', 'None')] or sub
        sides = {'看多': 0, '中性': 0, '看空': 0}
        for r in recent_sub:
            sides[side_cn[_rating_side(r['rating'])]] += 1
        st = _tp_stats(sub) or {}
        return {
            'count': len({r['broker'] for r in recent_sub}),
            'target_mean': st.get('mean'),
            'target_max': st.get('max'),
            'target_min': st.get('min'),
            'bull': sides['看多'], 'neutral': sides['中性'], 'bear': sides['看空'],
            'names': sorted({r['broker'] for r in recent_sub}),
        }

    # 最新3条研报动态（每券商取最新一条且优先有效评级的行，避免同券商多财年行刷屏）
    _best_by_broker: Dict[str, Dict] = {}
    for r in sorted(rows, key=lambda x: x['date'], reverse=True):
        b = r['broker']
        has_rt = bool(r['rating']) and r['rating'] not in ('--', 'nan', 'None')
        if b not in _best_by_broker:
            _best_by_broker[b] = r
        elif has_rt and (_best_by_broker[b]['rating'] in ('--', '', 'nan', 'None')):
            _best_by_broker[b] = r
    _recent_dedup = sorted(_best_by_broker.values(), key=lambda x: x['date'], reverse=True)[:3]
    recent_reports = [{
        'title': f"{r['year']}财年盈利预测", 'org': r['broker'], 'rating': r['rating'],
        'date': r['date'], 'target_price': r['target_price'],
    } for r in _recent_dedup]

    return {
        'market': '港股',
        'years': years,
        'org_count': cur.get('org_count', 0),
        'profit_yoy_pct': None,
        'rating_90d': rating_90d,
        'rating_side_90d': rating_side_90d,
        'rating_total_90d': len(recent90),
        'recent_reports': recent_reports,
        'org_eps': org_eps,
        'divergence': divergence,
        'bull_bear': bull_bear,
        'target_price': _tp_stats(rows),
        'intl_summary': _grp_summary(intl_rows),
        'cn_summary': _grp_summary(cn_rows),
    }


def _parse_cn_amount(text: str) -> Optional[float]:
    """解析中文金额字符串（'1.28亿'/'-5653.97万'）为亿元数值"""
    if not text:
        return None
    m = re.match(r'^(-?[\d.]+)\s*(亿|万)?', str(text).strip())
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2)
    if unit == '万':
        return val / 10000.0
    return val  # 默认按亿


def _fetch_last_year_profit(code: str, last_year: str) -> Optional[float]:
    """
    上年实际归母净利润（亿元），用于一致预期同比计算。
    数据源：同花顺财务摘要（按报告期）。失败返回 None（调用方降级为不展示同比）。
    """
    try:
        import akshare as ak
        df = ak.stock_financial_abstract_ths(symbol=code, indicator='按报告期')
        if df is None or df.empty:
            return None
        target = f'{last_year}-12-31'
        rows = df[df['报告期'].astype(str) == target]
        if rows.empty:
            return None
        val = _parse_cn_amount(str(rows.iloc[0].get('净利润', '')))
        return val
    except Exception as e:
        print(f"[一致预期] 上年实际净利获取失败 {code}: {e}")
        return None


def get_consensus(code: str) -> Optional[Dict]:
    """
    获取投行一致预期（同花顺盈利预测 + 东财研报评级合并视图）。

    Args:
        code: A股代码（如 301308）；港股或无覆盖个股接口会失败

    Returns:
        {
          'years': [{'year','org_count','profit_min/mean/max','eps_min/mean/max'}...],  # 未来三年
          'org_count': int,              # 当年预测机构数
          'profit_yoy_pct': float|None,  # 当年净利均值 vs 上年实际（%），上年亏损时为 None
          'last_year_profit': float|None,
          'rating_90d': {'买入': x, ...},
          'rating_total_90d': int,
          'recent_reports': [x3],
          'divergence': float|None,      # 当年净利最高预测/最低预测比值
          'bull_bear': {...}|None,
        }
        两个接口全部失败/空表时返回 None；单个失败时另一来源的数据仍保留。
    """
    forecasts = _fetch_profit_forecast_ths(code)
    reports = _fetch_research_reports_em(code)

    if forecasts is None and reports is None:
        return None

    result: Dict = {
        'years': forecasts or [],
        'org_count': 0,
        'profit_yoy_pct': None,
        'last_year_profit': None,
        'rating_90d': reports['rating_90d'] if reports else {},
        'rating_total_90d': reports['rating_total_90d'] if reports else 0,
        'recent_reports': reports['recent_reports'] if reports else [],
        'org_eps': reports['org_eps'] if reports else [],
        'divergence': None,
        'bull_bear': reports['bull_bear'] if reports else None,
    }

    # 当年预测（年份最小的一条视为当年）
    if forecasts:
        cur = forecasts[0]
        result['org_count'] = cur.get('org_count', 0)
        p_min, p_max = cur.get('profit_min'), cur.get('profit_max')
        if p_min and p_max and p_min > 0:
            result['divergence'] = round(p_max / p_min, 2)
        # 同比：当年预测均值 vs 上年实际
        try:
            cur_year = int(cur['year'])
        except (TypeError, ValueError):
            cur_year = None
        p_mean = cur.get('profit_mean')
        if cur_year and p_mean is not None:
            last_profit = _fetch_last_year_profit(code, str(cur_year - 1))
            result['last_year_profit'] = last_profit
            if last_profit and last_profit > 0:
                result['profit_yoy_pct'] = round((p_mean - last_profit) / abs(last_profit) * 100, 1)

    return result


if __name__ == '__main__':
    import json
    import sys
    _code = sys.argv[1] if len(sys.argv) > 1 else '301308'
    print(f"测试一致预期: {_code}")
    data = get_consensus(_code)
    if data is None:
        print("结果: None（无机构覆盖/数据源不可用，调用方应降级）")
    else:
        print(json.dumps(data, ensure_ascii=False, indent=1, default=str))
