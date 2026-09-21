# -*- coding: utf-8 -*-
"""
资金流向数据模块（东方财富 fflow 接口）

获取个股近N日主力资金净流入（主力/超大单/大单/中单/小单），含今日盘中实时数据。

⚠️ 部署注意（重要）：
- 本模块依赖东方财富 push2his.eastmoney.com / push2.eastmoney.com 的 fflow 接口。
- 部分云主机 IP 段会被东方财富封禁（连接超时/重置/空data），此时所有函数返回 None，
  调用方必须优雅降级（如显示"资金流向数据暂不可用"），不得让异常向上传播。
- 家用宽带 IP（本地用户实例）通常可正常访问。部署后请手动验证一次：
      python3 utils/fund_flow.py 301308 A股
- 服务器端（本机）无法测试属预期行为，不代表本地实例不可用。
"""

import requests
from datetime import datetime
from typing import Dict, List, Optional

_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

# fields2 字段约定：f51=日期 f52=主力净流入 f53=小单净流入 f54=中单净流入 f55=大单净流入 f56=超大单净流入
_FIELDS2 = "f51,f52,f53,f54,f55,f56"


def _secid(code: str, market: str = 'A股') -> Optional[str]:
    """转东财 secid：沪市 1.xxxxxx，深市 0.xxxxxx；港股不支持返回 None"""
    code = (code or '').strip()
    if not code:
        return None
    if market == '港股' or len(code) == 5:
        return None  # 东财 fflow 无港股资金流数据
    if code.startswith(('60', '68', '90', '11', '5')):
        return f"1.{code}"
    return f"0.{code}"


def _parse_klines(klines: List[str]) -> List[Dict]:
    """解析 fflow klines 行为结构化字典（金额单位：元）"""
    rows = []
    for item in klines or []:
        try:
            parts = item.split(',')
            if len(parts) < 6:
                continue
            rows.append({
                'date': parts[0],
                'main': float(parts[1]),          # 主力净流入
                'small': float(parts[2]),         # 小单净流入
                'medium': float(parts[3]),        # 中单净流入
                'large': float(parts[4]),         # 大单净流入
                'super_large': float(parts[5]),   # 超大单净流入
                'is_today': False,
            })
        except (ValueError, IndexError):
            continue
    return rows


def _fetch_daykline(secid: str, days: int) -> Optional[List[Dict]]:
    """历史日频资金流向（含今日，但盘中刷新慢）"""
    try:
        url = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
        params = {
            'secid': secid,
            'fields1': "f1,f2,f3,f7",
            'fields2': _FIELDS2,
            'klt': 101,
            'lmt': max(int(days), 5),
        }
        r = _session.get(url, params=params, timeout=12)
        data = r.json()
        klines = (data.get('data') or {}).get('klines') or []
        rows = _parse_klines(klines)
        return rows if rows else None
    except Exception as e:
        print(f"[资金流] 历史daykline获取失败 {secid}: {e}")
        return None


def _fetch_today_realtime(secid: str) -> Optional[Dict]:
    """今日盘中实时资金流向（fflow 实时通道，数据更新更快）"""
    try:
        url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
        params = {
            'secid': secid,
            'fields1': "f1,f2,f3,f7",
            'fields2': _FIELDS2,
            'klt': 101,
            'lmt': 1,
        }
        r = _session.get(url, params=params, timeout=12)
        data = r.json()
        klines = (data.get('data') or {}).get('klines') or []
        rows = _parse_klines(klines)
        return rows[-1] if rows else None
    except Exception as e:
        print(f"[资金流] 今日实时获取失败 {secid}: {e}")
        return None


def get_fund_flow(code: str, market: str = 'A股', days: int = 10) -> Optional[List[Dict]]:
    """
    获取近N日资金流向（按日期升序，含今日盘中实时值）。

    Args:
        code: 股票代码（如 301308）
        market: A股 / 港股
        days: 取近多少个交易日，默认10

    Returns:
        [{'date': '2026-09-21', 'main': 1234567.0, 'super_large': ..., 'large': ...,
          'medium': ..., 'small': ..., 'is_today': True/False}, ...]
        任何失败（网络/封禁/无数据/港股）均返回 None，调用方自行降级。
    """
    secid = _secid(code, market)
    if not secid:
        return None

    try:
        rows = _fetch_daykline(secid, days)
        if rows is None:
            return None

        # 用实时通道覆盖/补齐今日数据（盘中刷新更及时）
        today_row = _fetch_today_realtime(secid)
        if today_row:
            if rows and rows[-1]['date'] == today_row['date']:
                rows[-1] = today_row
            else:
                rows.append(today_row)

        today_str = datetime.now().strftime('%Y-%m-%d')
        for r in rows:
            r['is_today'] = (r['date'] == today_str)

        return rows[-days:] if rows else None
    except Exception as e:
        print(f"[资金流] {code} 获取异常: {e}")
        return None


if __name__ == '__main__':
    # 本地实例手动验证用：python3 utils/fund_flow.py 301308 A股
    import sys
    _code = sys.argv[1] if len(sys.argv) > 1 else '301308'
    _market = sys.argv[2] if len(sys.argv) > 2 else 'A股'
    print(f"测试资金流: {_code}({_market})")
    result = get_fund_flow(_code, _market, days=10)
    if result is None:
        print("结果: None（数据源不可用/被封禁/港股不支持）")
    else:
        print(f"共 {len(result)} 日:")
        for r in result:
            flag = " [今日盘中]" if r['is_today'] else ""
            print(f"  {r['date']} 主力: {r['main']/10000:+.2f}万 超大单: {r['super_large']/10000:+.2f}万{flag}")
