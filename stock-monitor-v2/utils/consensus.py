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
    东方财富个股研报：近90天评级分布 + 最新3份研报 + 当年分机构盈利预测（EPS口径）。

    Returns:
        {'rating_90d': {'买入': x, '增持': y, ...}, 'rating_total_90d': n,
         'recent_reports': [{'title','org','rating','date'} x3],
         'bull_bear': {'high': {'org','eps','date','title'}, 'low': {...}}  # 当年研报EPS最高/最低机构
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

        return {
            'rating_90d': rating_counts,
            'rating_total_90d': int(len(recent)),
            'recent_reports': recent_reports,
            'bull_bear': bull_bear,
        }
    except Exception as e:
        print(f"[一致预期] 东财研报获取失败 {code}: {e}")
        return None


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
