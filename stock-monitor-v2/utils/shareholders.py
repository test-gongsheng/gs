# -*- coding: utf-8 -*-
"""十大流通股东变动模块（2026-10-30新增）

数据源（本机实测通过，2026-10-30）：
- 新浪财经F10流通股东页：vip.stock.finance.sina.com.cn/corp/go.php/
  vCI_CirculateStockHolder/stockid/{code}.phtml（GBK，pandas.read_html 解析）
  页面含最近4期十大流通股东（名称/持股数量/占流通股比例/股本性质），
  多年稳定，东财F10接口403后的替代通道。

存储：data/shareholders/{code}.json
  {"asof": "YYYY-MM-DD HH:MM",
   "periods": [{"period": "2026-09-30", "announce_date": "2026-10-29",
                "holders": [{"name","shares","pct","nature"}...]}, ...]}
  仅保留最新两期。缓存策略：距上次抓取<7天直接用缓存（股东数据每季度才更新，不天天抓）；
  离线时用缓存+asof标注。

diff_latest(code)：本地 diff 两期名单 -> 新进/退出/增持/减持。
名称归一化仅用于"是不是同一家"的匹配（大写/去空白与标点），展示仍用原始名称。
注意：同名不同主体（如"高盛公司有限责任公司" vs "GOLDMAN SACHS BANK EUROPE SE－
自有资金－QFII"）归一化后仍不同，会如实显示一退一进，不误合并。

港股（如00700）无A股流通股东概念 -> refresh 返回 None，调用方输出"不适用"。
"""
import json
import os
import re
import io
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)  # 支持 `python3 utils/shareholders.py` 直接运行
HOLDER_DIR = os.path.join(BASE, 'data', 'shareholders')
CACHE_DAYS = 7


def _is_a_share(code: str) -> bool:
    return str(code).zfill(6).startswith(('6', '0', '3'))


def _path(code: str) -> str:
    return os.path.join(HOLDER_DIR, f'{code}.json')


def _load(code: str) -> dict:
    try:
        with open(_path(code), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save(code: str, data: dict) -> None:
    os.makedirs(HOLDER_DIR, exist_ok=True)
    data['asof'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    with open(_path(code), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _norm_name(name: str) -> str:
    """归一化名称用于跨期匹配：大写、去空白与常见标点。"""
    s = str(name).upper()
    return re.sub(r'[\s\-—–－_()（）.,，、·&]', '', s)


def _parse_page(code: str) -> list:
    """抓取并解析新浪F10流通股东页，返回最近若干期的股东数据（新->旧）。

    Returns:
        [{'period','announce_date','holders':[{'name','shares','pct','nature'}...]}...]
        失败返回 []
    """
    import requests
    import pandas as pd
    url = (f'https://vip.stock.finance.sina.com.cn/corp/go.php/'
           f'vCI_CirculateStockHolder/stockid/{str(code).zfill(6)}.phtml')
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    r.encoding = 'gbk'
    if r.status_code != 200 or '流通股东' not in r.text:
        return []
    tables = pd.read_html(io.StringIO(r.text))
    periods = []
    for t in tables:
        try:
            vals = t.iloc[:, 0].tolist()
            first_col = [v.strip() if isinstance(v, str) else str(v) for v in vals]
        except Exception:
            continue
        if not any(x == '截止日期' for x in first_col):
            continue
        cur = None
        for _, row in t.iterrows():
            key = str(row.iloc[0]).strip()
            if key == '截止日期':
                if cur and cur.get('holders'):
                    periods.append(cur)
                cur = {'period': str(row.iloc[1]).strip(), 'announce_date': '',
                       'holders': []}
            elif key == '公告日期' and cur is not None:
                cur['announce_date'] = str(row.iloc[1]).strip()
            elif key.isdigit() and cur is not None:
                try:
                    shares = float(str(row.iloc[2]).replace(',', ''))
                except (TypeError, ValueError):
                    continue
                try:
                    pct = float(str(row.iloc[3]).replace('%', ''))
                except (TypeError, ValueError):
                    pct = None
                cur['holders'].append({
                    'name': str(row.iloc[1]).strip(),
                    'shares': shares,
                    'pct': pct,
                    'nature': str(row.iloc[4]).strip() if len(row) > 4 else '',
                })
        if cur and cur.get('holders'):
            periods.append(cur)
    # 去重（同一报告期可能在页面出现多次）
    seen = set()
    out = []
    for p in periods:
        if p['period'] in seen:
            continue
        seen.add(p['period'])
        out.append(p)
    return out


def refresh(code: str, force: bool = False) -> dict:
    """刷新缓存，返回 {'periods': [...], 'asof': ...}。

    - 距上次抓取<7天且非force：直接用缓存
    - 抓取失败但有缓存：降级用缓存（asof标注抓取时间，调用方可提示数据时点）
    - 抓取失败且无缓存：返回 {'periods': [], 'asof': ''}
    """
    code = str(code).zfill(6)
    if not _is_a_share(code):
        return {'periods': [], 'asof': ''}
    cached = _load(code)
    if not force and cached.get('asof'):
        try:
            age = datetime.now() - datetime.strptime(cached['asof'], '%Y-%m-%d %H:%M')
            if age.days < CACHE_DAYS:
                return cached
        except Exception:
            pass
    try:
        periods = _parse_page(code)
        if periods:
            data = {'periods': periods[:2]}  # 只留最新两期
            _save(code, data)
            return data
    except Exception as e:
        print(f'[股东] 抓取失败 {code}: {e}')
    if cached.get('periods'):
        return cached  # 离线降级：用缓存
    return {'periods': [], 'asof': ''}


def diff_latest(code: str) -> dict:
    """最新两期十大流通股东对比。

    Returns:
        {'period_new','ann_new','period_old','ann_old',
         'entered':[{name,shares,pct}], 'exited':[{name,shares,pct}],
         'increased':[{name,delta,pct_new}], 'decreased':[{name,delta,pct_new}],
         'asof', 'cached': bool}
        数据不足返回 None
    """
    code = str(code).zfill(6)
    data = refresh(code)
    periods = data.get('periods') or []
    if len(periods) < 2:
        return None
    new, old = periods[0], periods[1]
    old_map = {_norm_name(h['name']): h for h in old['holders']}
    new_map = {_norm_name(h['name']): h for h in new['holders']}
    entered, exited, increased, decreased = [], [], [], []
    for k, h in new_map.items():
        if k not in old_map:
            entered.append({'name': h['name'], 'shares': h['shares'], 'pct': h.get('pct')})
        else:
            delta = h['shares'] - old_map[k]['shares']
            if delta > 0:
                increased.append({'name': h['name'], 'delta': delta, 'pct_new': h.get('pct')})
            elif delta < 0:
                decreased.append({'name': h['name'], 'delta': delta, 'pct_new': h.get('pct')})
    for k, h in old_map.items():
        if k not in new_map:
            exited.append({'name': h['name'], 'shares': h['shares'], 'pct': h.get('pct')})
    asof = data.get('asof', '')
    cached = False
    if asof:
        try:
            cached = (datetime.now() - datetime.strptime(asof, '%Y-%m-%d %H:%M')).days >= CACHE_DAYS
        except Exception:
            pass
    return {
        'period_new': new['period'], 'ann_new': new.get('announce_date', ''),
        'period_old': old['period'], 'ann_old': old.get('announce_date', ''),
        'entered': entered, 'exited': exited,
        'increased': increased, 'decreased': decreased,
        'asof': asof, 'cached': cached,
    }


def _short_name(name: str) -> str:
    """基金/资管超长名称缩短：仅当中文托管前缀(银行/证券/信托/保险－)存在、
    且末段是完整产品名(含'证券投资基金'/'资产管理计划'或≥8字)时才取末段；
    保险产品代码段(如-005L-CT001沪)、外资行英文名不截断，防误伤。"""
    s = str(name)
    for sep in ('－', '—', '–', '-'):
        if sep in s:
            head = s.split(sep)[0]
            tail = s.split(sep)[-1].strip()
            if any(k in head for k in ('银行', '证券', '信托', '保险')) and tail and (
                    '证券投资基金' in tail or '资产管理计划' in tail or len(tail) >= 8):
                return tail
            return s  # 非托管基金结构，保留全名
    return s


def render_holder_lines(code: str) -> list:
    """供 deep_analysis.py 调用的渲染入口。"""
    code = str(code).zfill(6)
    if not _is_a_share(code):
        return []
    d = diff_latest(code)
    if d is None:
        return ['**机构动向:** 十大流通股东数据暂不可用(数据源受限)', '']
    lines = []
    asof_note = f"(asof {d['asof'][:10]}缓存)" if d.get('cached') else ''
    lines.append(f"**机构动向[一手·十大流通股东公告]{asof_note}:** "
                 f"{d['period_new']}(公告{d['ann_new']}) vs {d['period_old']}(公告{d['ann_old']}):")
    def _fmt(h):
        w = f"{h['shares']/10000:.1f}万股" if h.get('shares') is not None else ''
        p = f"/流通盘{h['pct']}%" if h.get('pct') is not None else ''
        return f"{_short_name(h['name'])}({w}{p})"
    def _fmt_delta(h):
        p = f"/流通盘{h['pct_new']}%" if h.get('pct_new') is not None else ''
        return f"{_short_name(h['name'])}({'+' if h['delta']>0 else ''}{h['delta']/10000:.1f}万股{p})"
    if d['entered']:
        lines.append('- 新进: ' + '、'.join(_fmt(h) for h in d['entered']))
    if d['exited']:
        lines.append('- 退出: ' + '、'.join(_fmt(h) for h in d['exited']))
    if d['increased']:
        lines.append('- 增持: ' + '、'.join(_fmt_delta(h) for h in d['increased']))
    if d['decreased']:
        lines.append('- 减持: ' + '、'.join(_fmt_delta(h) for h in d['decreased']))
    if not (d['entered'] or d['exited'] or d['increased'] or d['decreased']):
        lines.append('- 两期名单无变动。')
    lines.append('')
    return lines


if __name__ == '__main__':
    import sys
    for c in (sys.argv[1:] or ['688795', '002594', '601600']):
        print('====', c)
        for l in render_holder_lines(c):
            print(l)
