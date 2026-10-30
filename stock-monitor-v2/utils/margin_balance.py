# -*- coding: utf-8 -*-
"""A股个股融资余额采集模块（交易所两融，2026-10-30新增）

数据源（本机实测通过，2026-10-30）：
- 沪市：ak.stock_margin_detail_sse(date='YYYYMMDD')，底层 query.sse.com.cn，
  返回当日全市场两融明细（约2000只），按标的证券代码过滤
- 深市：ak.stock_margin_detail_szse(date='YYYYMMDD')，底层 www.szse.cn/api，
  返回当日全市场两融明细，按证券代码过滤

存储：data/margin/{code}.json
  {"records": [{"date","rzye","rqyl","rzmr","rzch"}], "updated": "YYYY-MM-DD HH:MM"}
  - 按日追加；历史日期绝不重采重写（写入前检查日期是否已存在且已有更晚日期，存在则跳过）
  - 仅最新交易日允许覆盖（交易所当日修订口径）

每日增量 refresh_daily(codes)：回扫最近10个自然日，补采交易所已发布但本地缺失的
交易日（参照 utils/etf_flow_signal.py 的 seen 回扫模式——周一/节后第一天必漏数据的坑）。
按市场整批拉取（一个日期一次请求覆盖该市场全部持仓），不是每股票一次请求。

趋势指标 trend_metrics(code)：最新融资余额、5日/20日变化率、距60日峰值偏离。
占流通市值比例因流通股本口径无稳定免费来源，本模块不输出，避免瞎编。

港股（如00700）无A股两融 -> 各函数返回 None，调用方应输出"不适用"。
"""
import json
import os
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARGIN_DIR = os.path.join(BASE, 'data', 'margin')


def _is_a_share(code: str) -> bool:
    c = str(code).zfill(6)
    return c.startswith(('6', '0', '3'))


def _market_of(code: str) -> str:
    """A股代码 -> 'sh' / 'sz'；非A股 -> ''"""
    c = str(code).zfill(6)
    if not _is_a_share(c):
        return ''
    return 'sh' if c.startswith('6') else 'sz'


def _path(code: str) -> str:
    return os.path.join(MARGIN_DIR, f'{code}.json')


def _load(code: str) -> dict:
    try:
        with open(_path(code), 'r', encoding='utf-8') as f:
            d = json.load(f)
            if 'records' not in d:
                d['records'] = []
            return d
    except Exception:
        return {'records': [], 'updated': ''}


def _save(code: str, data: dict) -> None:
    os.makedirs(MARGIN_DIR, exist_ok=True)
    data['records'].sort(key=lambda r: r['date'])
    data['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    with open(_path(code), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def fetch_one(code: str, date: str) -> dict:
    """采集单只股票单个交易日的两融数据。

    Args:
        code: A股代码（6/0/3开头）
        date: 'YYYY-MM-DD'

    Returns:
        {'date','rzye','rqyl','rzmr','rzch'} 单位：元（交易所原始口径）
        该日无数据/接口失败/非两融标的 -> None
    """
    mkt = _market_of(code)
    if not mkt:
        return None
    try:
        import akshare as ak
        ds8 = date.replace('-', '')
        if mkt == 'sh':
            df = ak.stock_margin_detail_sse(date=ds8)
            if df is None or df.empty:
                return None
            col_code = '标的证券代码'
            sub = df[df[col_code].astype(str).str.zfill(6) == str(code).zfill(6)]
            if sub.empty:
                return None
            row = sub.iloc[0]
            return {
                'date': date,
                'rzye': float(row.get('融资余额', 0) or 0),
                'rqyl': float(row.get('融券余量', 0) or 0),
                'rzmr': float(row.get('融资买入额', 0) or 0),
                'rzch': float(row.get('融资偿还额', 0) or 0),
            }
        else:
            df = ak.stock_margin_detail_szse(date=ds8)
            if df is None or df.empty:
                return None
            sub = df[df['证券代码'].astype(str).str.zfill(6) == str(code).zfill(6)]
            if sub.empty:
                return None
            row = sub.iloc[0]
            _rzch = row.get('融资偿还额')  # 深市接口无此字段，缺失记None不记0
            return {
                'date': date,
                'rzye': float(row.get('融资余额', 0) or 0),
                'rqyl': float(row.get('融券余量', 0) or 0),
                'rzmr': float(row.get('融资买入额', 0) or 0),
                'rzch': float(_rzch) if _rzch is not None else None,
            }
    except Exception as e:
        print(f'[融资余额] 采集失败 {code} {date}: {e}')
        return None


def _fetch_batch(market: str, ds8: str):
    """按市场整批拉取某交易日两融明细（单一网络接缝，便于降级测试mock）。

    Args:
        market: 'sh'|'sz'
        ds8: YYYYMMDD
    Returns:
        DataFrame或None；异常向上抛（调用方逐日try）
    """
    import akshare as ak
    if market == 'sh':
        return ak.stock_margin_detail_sse(date=ds8)
    return ak.stock_margin_detail_szse(date=ds8)


def refresh_daily(codes) -> dict:
    """每日增量采集：回扫最近10个自然日，补采本地缺失的交易日。

    按市场整批拉取：同一交易日沪市全部持仓一次请求、深市一次请求。
    写入纪律：历史日期绝不重写；仅最新已有日期允许覆盖（交易所当日修订）。

    Returns:
        {'added': int, 'updated_codes': [code...]}
    """
    codes = [str(c).zfill(6) for c in codes if _is_a_share(str(c).zfill(6))]
    if not codes:
        return {'added': 0, 'updated_codes': []}
    sh_codes = [c for c in codes if _market_of(c) == 'sh']
    sz_codes = [c for c in codes if _market_of(c) == 'sz']
    store = {c: _load(c) for c in codes}
    today = datetime.now().date()
    added = 0
    touched = set()

    def _upsert(code: str, rec: dict) -> None:
        nonlocal added
        d = store[code]
        dates = {r['date'] for r in d['records']}
        if rec['date'] in dates:
            # 仅当它是本地最新日期时允许覆盖（交易所当日修订），历史日期跳过
            latest = max(dates)
            if rec['date'] == latest:
                for r in d['records']:
                    if r['date'] == rec['date']:
                        r.update(rec)
                        break
                added += 1
                touched.add(code)
        else:
            d['records'].append(rec)
            added += 1
            touched.add(code)

    for offset in range(0, 10):
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            continue  # 周末交易所不发布两融数据，跳过（节假日由接口空返回自然跳过）
        ds = d.strftime('%Y-%m-%d')
        if sh_codes:
            try:
                df = _fetch_batch('sh', ds.replace('-', ''))
                if df is not None and not df.empty:
                    df = df[df['标的证券代码'].astype(str).str.zfill(6).isin(sh_codes)]
                    for _, row in df.iterrows():
                        c = str(row['标的证券代码']).zfill(6)
                        _upsert(c, {
                            'date': ds,
                            'rzye': float(row.get('融资余额', 0) or 0),
                            'rqyl': float(row.get('融券余量', 0) or 0),
                            'rzmr': float(row.get('融资买入额', 0) or 0),
                            'rzch': float(row.get('融资偿还额', 0) or 0),
                        })
            except Exception as e:
                print(f'[融资余额] 沪市{ds}批量采集失败: {e}')
        if sz_codes:
            try:
                df = _fetch_batch('sz', ds.replace('-', ''))
                if df is not None and not df.empty:
                    df = df[df['证券代码'].astype(str).str.zfill(6).isin(sz_codes)]
                    for _, row in df.iterrows():
                        c = str(row['证券代码']).zfill(6)
                        _rzch = row.get('融资偿还额')  # 深市接口无此字段
                        _upsert(c, {
                            'date': ds,
                            'rzye': float(row.get('融资余额', 0) or 0),
                            'rqyl': float(row.get('融券余量', 0) or 0),
                            'rzmr': float(row.get('融资买入额', 0) or 0),
                            'rzch': float(_rzch) if _rzch is not None else None,
                        })
            except Exception as e:
                print(f'[融资余额] 深市{ds}批量采集失败: {e}')

    for c in touched:
        _save(c, store[c])
    return {'added': added, 'updated_codes': sorted(touched)}


def trend_metrics(code: str) -> dict:
    """本地融资余额趋势指标（全本地计算，无网络）。

    Returns:
        {'date', 'rzye', 'chg_5d_pct', 'chg_20d_pct', 'off_peak_60d_pct',
         'peak_60d', 'days': int}  变化率不足样本时为 None
        无本地数据/非A股 -> None
    """
    mkt = _market_of(code)
    if not mkt:
        return None
    d = _load(code)
    recs = d['records']
    if not recs:
        return None
    latest = recs[-1]
    out = {
        'date': latest['date'],
        'rzye': latest['rzye'],
        'rqyl': latest.get('rqyl'),
        'chg_5d_pct': None,
        'chg_20d_pct': None,
        'off_peak_60d_pct': None,
        'peak_60d': None,
        'days': len(recs),
    }
    if len(recs) >= 6 and recs[-6]['rzye'] > 0:
        out['chg_5d_pct'] = round((latest['rzye'] / recs[-6]['rzye'] - 1) * 100, 2)
    if len(recs) >= 21 and recs[-21]['rzye'] > 0:
        out['chg_20d_pct'] = round((latest['rzye'] / recs[-21]['rzye'] - 1) * 100, 2)
    win = recs[-60:]
    peak = max(r['rzye'] for r in win)
    out['peak_60d'] = peak
    if peak > 0:
        out['off_peak_60d_pct'] = round((latest['rzye'] / peak - 1) * 100, 2)
    return out


def render_margin_lines(code: str) -> list:
    """供 deep_analysis.py 调用的渲染入口：本地无数据时先尝试一次增量采集，
    再输出趋势行。全部异常由调用方兜底，这里不再抛。
    """
    mkt = _market_of(code)
    if not mkt:
        return []
    d = _load(code)
    if not d['records']:
        try:
            refresh_daily([code])
        except Exception as e:
            print(f'[融资余额] 兜底增量采集失败 {code}: {e}')
    m = trend_metrics(code)
    if not m:
        return [f'- 融资余额数据暂不可用(交易所两融接口受限)']
    lines = []
    yi = m['rzye'] / 100000000
    bits = [f"最新 {m['date'][5:]} 融资余额 ¥{yi:.2f}亿[库·交易所两融]"]
    if m['chg_5d_pct'] is not None:
        bits.append(f"5日 {m['chg_5d_pct']:+.1f}%")
    if m['chg_20d_pct'] is not None:
        bits.append(f"20日 {m['chg_20d_pct']:+.1f}%")
    if m['off_peak_60d_pct'] is not None:
        bits.append(f"距60日峰值({m['peak_60d']/100000000:.2f}亿) {m['off_peak_60d_pct']:+.1f}%")
    lines.append('- ' + ','.join(bits) + '。')
    # 杠杆情绪判定（[阈值]人为规则，非市场数据）
    verdict = []
    if m['chg_5d_pct'] is not None:
        if m['chg_5d_pct'] <= -3:
            verdict.append('近5日杠杆资金明显撤退')
        elif m['chg_5d_pct'] >= 3:
            verdict.append('近5日杠杆资金明显升温')
        else:
            verdict.append('近5日杠杆资金平稳')
    if m['off_peak_60d_pct'] is not None:
        if m['off_peak_60d_pct'] <= -15:
            verdict.append(f'较高点已大幅出清({m["off_peak_60d_pct"]:.0f}%)')
        elif m['off_peak_60d_pct'] >= -3:
            verdict.append('融资余额处于60日高位区')
    if verdict:
        lines.append(f'- 杠杆情绪判定[阈值]:' + ';'.join(verdict) + '。')
    return lines


if __name__ == '__main__':
    import sys
    codes = sys.argv[1:] or ['688795', '002594']
    print('refresh_daily:', refresh_daily(codes))
    for c in codes:
        print(c, json.dumps(trend_metrics(c), ensure_ascii=False))
        for l in render_margin_lines(c):
            print(' ', l)
