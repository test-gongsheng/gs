# -*- coding: utf-8 -*-
"""新研报捕获 + 假设拆解模块（2026-10-30新增）

数据源（本机实测通过，2026-10-30）：
- ak.stock_research_report_em(symbol=code)（reportapi.eastmoney.com 域名，
  与 datacenter-web 不同，未被403）：标题/券商/日期/东财评级/各年盈利预测EPS与市盈率。
  注意：该接口只有EPS与预测PE字段，无营收/净利绝对值、无目标价——
  拆不了的维度如实省略，不编造。

存储：data/research_reports/{code}.json
  {"asof": "YYYY-MM-DD",
   "reports": [{org,title,date,rating,eps:{year:val},url}...],   # 近30天窗口去重后
   "org_history": {org: {"rating": ..., "date": ...}}}           # 全量研报最新一条，判评级变化

捕获规则：最近30天覆盖个股的新研报，与库内按(券商+日期+标题)去重。
同一自然日重复跑只采一次（asof==today 直接返回缓存）。

假设拆解（纯规则，不用LLM——Windows跑批环境无LLM）：
- 每份新研报：评级变化（首次覆盖/调升/调降/维持），判定依据东财研报库全量历史中
  该券商上一份研报（本地org_history滚动维护）
- 与一致预期偏离：新研报当年EPS预测 vs utils/consensus.get_consensus 当年EPS均值，
  [推算] 偏离%=(研报EPS-一致预期均值)/一致预期均值×100
- 机构间分歧：近30天各研报当年EPS预测的最大/最小值及对应券商[推算]
- 隐含剩余季度环比：需要"当年已披露季报累计营收+全年预测营收"，东财研报接口只有EPS
  无营收，且东财业绩报表接口(datacenter-web)本机403——该维度如实跳过，不硬算。

港股（如00700）东财研报接口直接报错 -> 返回 None，调用方输出"不适用"。
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)  # 支持 `python3 utils/research_report.py` 直接运行
REPORT_DIR = os.path.join(BASE, 'data', 'research_reports')
CAPTURE_DAYS = 30
MAX_STORE = 80  # 单股本地库上限，防膨胀

# 评级强弱序（用于调升/调降判定，[阈值]人为规则）
_RATING_ORDER = {'买入': 4, '推荐': 4, '增持': 3, '中性': 2, '持有': 2,
                 '减持': 1, '卖出': 0}


def _is_a_share(code: str) -> bool:
    return str(code).zfill(6).startswith(('6', '0', '3'))


def _path(code: str) -> str:
    return os.path.join(REPORT_DIR, f'{code}.json')


def _load(code: str) -> dict:
    try:
        with open(_path(code), 'r', encoding='utf-8') as f:
            d = json.load(f)
            d.setdefault('reports', [])
            d.setdefault('org_history', {})
            return d
    except Exception:
        return {'reports': [], 'org_history': {}, 'asof': ''}


def _save(code: str, data: dict) -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    data['reports'] = data['reports'][-MAX_STORE:]
    data['asof'] = datetime.now().strftime('%Y-%m-%d')
    with open(_path(code), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _fetch_df(code: str):
    try:
        import akshare as ak
        df = ak.stock_research_report_em(symbol=str(code).zfill(6))
        return df
    except Exception as e:
        print(f'[研报] 东财接口失败 {code}: {e}')
        return None


def refresh(code: str) -> dict:
    """捕获最近30天新研报并入库（同日日幂等）。

    Returns:
        {'reports': [...], 'org_history': {...}, 'asof': ..., 'fetch_ok': bool}
        fetch_ok=False 表示东财接口本次抓取失败（调用方应报'暂不可用'而非'无新研报'）。
    """
    code = str(code).zfill(6)
    if not _is_a_share(code):
        return {'reports': [], 'org_history': {}, 'asof': '', 'fetch_ok': False}
    data = _load(code)
    today = datetime.now().strftime('%Y-%m-%d')
    if data.get('asof') == today and data.get('reports'):
        data['fetch_ok'] = True
        return data
    try:
        df = _fetch_df(code)
    except Exception as e:
        print(f'[研报] 东财接口异常 {code}: {e}')
        df = None
    if df is None or df.empty:
        data['fetch_ok'] = False
        return data
    try:
        import pandas as pd
        df = df.copy()
        df['日期'] = pd.to_datetime(df['日期'])
        cutoff = pd.Timestamp(datetime.now() - timedelta(days=CAPTURE_DAYS))
        window = df[df['日期'] >= cutoff]

        def _eps_map(row) -> dict:
            m = {}
            for col in df.columns:
                mm = re.match(r'^(\d{4})-盈利预测-收益$', str(col))
                if mm:
                    try:
                        v = float(row.get(col))
                        if v > 0:
                            m[mm.group(1)] = round(v, 2)
                    except (TypeError, ValueError):
                        pass
            return m

        existing = {(r['org'], r['date'], r['title']) for r in data['reports']}
        new_reports = []
        full_sorted = df.sort_values('日期')
        for _, row in window.iterrows():
            rec = {
                'org': str(row.get('机构', '')).strip(),
                'title': str(row.get('报告名称', '')).strip(),
                'date': row['日期'].strftime('%Y-%m-%d'),
                'rating': str(row.get('东财评级', '')).strip(),
                'eps': _eps_map(row),
                'url': str(row.get('报告PDF链接', '') or ''),
                'prev': None,
            }
            if not rec['org'] or not rec['title']:
                continue
            key = (rec['org'], rec['date'], rec['title'])
            if key not in existing:
                # 该券商在本报告之前的上一份研报（全量df内），用于评级变化判定
                try:
                    org_rows = full_sorted[full_sorted['机构'].astype(str).str.strip() == rec['org']]
                    past = org_rows[org_rows['日期'] < row['日期']]
                    if not past.empty:
                        prow = past.iloc[-1]
                        rec['prev'] = {'rating': str(prow.get('东财评级', '')).strip(),
                                       'date': prow['日期'].strftime('%Y-%m-%d')}
                except Exception:
                    pass
                new_reports.append(rec)
        if new_reports:
            data['reports'].extend(new_reports)
            # 全库按(券商+日期+标题)再保险去重
            seen = set()
            uniq = []
            for r in sorted(data['reports'], key=lambda x: x['date']):
                k = (r['org'], r['date'], r['title'])
                if k in seen:
                    continue
                seen.add(k)
                uniq.append(r)
            data['reports'] = uniq
        # org_history：全量df每机构最新一条（用于评级变化判定）
        try:
            full = df.sort_values('日期')
            for _, row in full.iterrows():
                org = str(row.get('机构', '')).strip()
                if not org:
                    continue
                data['org_history'][org] = {
                    'rating': str(row.get('东财评级', '')).strip(),
                    'date': row['日期'].strftime('%Y-%m-%d'),
                }
        except Exception as e:
            print(f'[研报] org_history维护失败 {code}: {e}')
        _save(code, data)
    except Exception as e:
        print(f'[研报] 解析入库失败 {code}: {e}')
        data['fetch_ok'] = False
        return data
    data['fetch_ok'] = True
    return data


def _rating_change(prev: dict, cur_rating: str) -> str:
    """评级变化判定（[阈值]规则）。prev=该券商在本报告前的上一份研报（东财库全量口径）。"""
    if not prev:
        return '首次覆盖(东财库无该机构更早记录)'
    po = _RATING_ORDER.get(prev.get('rating', ''), None)
    co = _RATING_ORDER.get(cur_rating, None)
    if po is None or co is None:
        return f"评级维持({cur_rating})"
    if co > po:
        return f"调升:{prev.get('rating')}→{cur_rating}"
    if co < po:
        return f"调降:{prev.get('rating')}→{cur_rating}"
    return f"评级维持({cur_rating})"


def assumption_breakdown(code: str, cons: dict = None) -> dict:
    """假设拆解（纯规则）。cons 为 deep_analysis 已抓的 get_consensus 结果，避免重复请求。

    Returns:
        {'reports': [{org,title,date,rating,eps,rating_change,deviation_pct,deviation_basis}],
         'divergence': {'max': {...}, 'min': {...}} | None,
         'notes': [...]}
    """
    code = str(code).zfill(6)
    data = refresh(code)
    cutoff = (datetime.now() - timedelta(days=CAPTURE_DAYS)).strftime('%Y-%m-%d')
    recent = [r for r in data['reports'] if r['date'] >= cutoff]
    if not recent:
        return {'reports': [], 'divergence': None, 'notes': [], 'fetch_ok': data.get('fetch_ok', True)}
    cur_year = str(datetime.now().year)
    # 一致预期当年EPS均值（传入cons则免重采；脚本直跑时先修sys.path）
    cons_eps_mean = None
    try:
        if cons is None:
            try:
                from utils.consensus import get_consensus
            except ImportError:
                from consensus import get_consensus  # 兼容utils目录直跑
            cons = get_consensus(code)
        for y in (cons or {}).get('years') or []:
            if str(y.get('year')) == cur_year and y.get('eps_mean'):
                cons_eps_mean = float(y['eps_mean'])
                break
    except Exception as e:
        print(f'[研报拆解] 一致预期获取失败 {code}: {e}')
    notes = []
    out_reports = []
    for r in sorted(recent, key=lambda x: x['date'], reverse=True):
        item = dict(r)
        item['rating_change'] = _rating_change(r.get('prev'), r.get('rating', ''))
        item['deviation_pct'] = None
        eps_cur = (r.get('eps') or {}).get(cur_year)
        if eps_cur and cons_eps_mean:
            if cons_eps_mean > 0:
                item['deviation_pct'] = round((eps_cur - cons_eps_mean) / cons_eps_mean * 100, 1)
                item['deviation_basis'] = f"[推算](研报{cur_year}E EPS {eps_cur} - 一致预期均值 {cons_eps_mean}) / 一致预期均值"
            else:
                # 一致预期均值为负(机构整体预计亏损)时百分比无意义，改报方向性分歧
                item['deviation_text'] = (f"一致预期当年EPS均值为负({cons_eps_mean}元,机构整体预计仍亏损)，"
                                          f"本研报预测+{eps_cur}元，属方向性分歧[推算]")
        out_reports.append(item)
    # 机构间分歧（近30天各研报当年EPS预测）
    divergence = None
    cands = [x for x in out_reports if (x.get('eps') or {}).get(cur_year)]
    if len(cands) >= 2:
        hi = max(cands, key=lambda x: x['eps'][cur_year])
        lo = min(cands, key=lambda x: x['eps'][cur_year])
        if hi['eps'][cur_year] != lo['eps'][cur_year]:
            divergence = {
                'max': {'org': hi['org'], 'eps': hi['eps'][cur_year], 'date': hi['date']},
                'min': {'org': lo['org'], 'eps': lo['eps'][cur_year], 'date': lo['date']},
                'year': cur_year,
            }
    if cons_eps_mean is None:
        notes.append('一致预期当年EPS均值缺失（无机构覆盖或接口受限），偏离度维度跳过。')
    notes.append('东财研报接口无营收/净利绝对值与目标价字段，隐含剩余季度环比维度无法规则化拆解，如实省略。')
    return {'reports': out_reports, 'divergence': divergence, 'notes': notes, 'fetch_ok': data.get('fetch_ok', True)}


def render_report_lines(code: str, cons: dict = None) -> list:
    """供 deep_analysis.py 调用的渲染入口。"""
    code = str(code).zfill(6)
    if not _is_a_share(code):
        return []
    try:
        bd = assumption_breakdown(code, cons=cons)
    except Exception as e:
        print(f'[研报拆解] 生成失败 {code}: {e}')
        return ['**最新研报捕获+假设拆解:** 数据暂不可用(东财研报接口受限)', '']
    if bd.get('fetch_ok') is False:
        return ['**最新研报捕获+假设拆解[库·东财研报]:** 数据暂不可用(东财研报接口受限)', '']
    if not bd['reports']:
        return [f'**最新研报捕获+假设拆解[库·东财研报]:** 近{CAPTURE_DAYS}日无新研报入池。', '']
    lines = [f"**最新研报捕获+假设拆解[库·东财研报]:** 近{CAPTURE_DAYS}日新入池 {len(bd['reports'])} 份——"]
    for r in bd['reports']:
        eps_bits = []
        for y, v in sorted((r.get('eps') or {}).items()):
            eps_bits.append(f"{y}E EPS {v}")
        eps_txt = f"({'/'.join(eps_bits)})" if eps_bits else '(接口未给盈利预测)'
        lines.append(f"- {r['date']} {r['org']}《{r['title']}》评级:{r.get('rating','-')};"
                     f"评级变化[阈值]:{r.get('rating_change','-')}{eps_txt}")
        if r.get('deviation_pct') is not None:
            lines.append(f"  - 与一致预期偏离[推算]: 当年EPS预测较一致预期均值{'+' if r['deviation_pct']>=0 else ''}{r['deviation_pct']}%"
                         f"({r.get('deviation_basis','')})")
        elif r.get('deviation_text'):
            lines.append(f"  - 与一致预期偏离: {r['deviation_text']}")
    if bd.get('divergence'):
        dv = bd['divergence']
        lines.append(f"- 机构间预测分歧[推算]: {dv['year']}E EPS最高 {dv['max']['eps']}({dv['max']['org']} {dv['max']['date']})"
                     f" vs 最低 {dv['min']['eps']}({dv['min']['org']} {dv['min']['date']}),"
                     f"区间宽度{(dv['max']['eps']/dv['min']['eps']):.2f}倍(=最高/最低,口径同一致预期分歧度)")
    for n in bd.get('notes') or []:
        lines.append(f"- 备注: {n}")
    lines.append('')
    return lines


if __name__ == '__main__':
    import sys
    for c in (sys.argv[1:] or ['688795', '601600', '002594']):
        print('====', c)
        for l in render_report_lines(c):
            print(l)
