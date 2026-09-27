# -*- coding: utf-8 -*-
"""
持仓价格刷新模块 - 把真实行情写回 stocks.json

根因修复（2026-09-27）：
  原链路每天 16:05 拉取实时价格只用于生成报告，从不写回 stocks.json，
  导致 git 里的持仓价格长期陈旧（案例：阿里显示 89.161 vs 实际收盘 108.4，
  比亚迪电子 19.789 vs 23.52，中国铝业 4.63 vs 8.88），
  所有依赖 current_price 的计算（浮动盈亏/买卖点/市值/中轴偏离）全部失真。

本模块职责：
  腾讯API批量取价(单次HTTP) → 合理性校验(防脏数据) → 备份 → 原子写回。
  只动 current_price 及行情衍生字段，绝不触碰 avg_cost / shares / trades / axis_price。
"""

import json
import os
import shutil
from datetime import datetime
from typing import Dict, Optional

from utils.stock_quote import get_stock_quotes, normalize_tencent_code

# 与昨收对比，单日波动超过此比例视为脏数据拒绝写入。
# 取 ±50%：港股无涨跌停，需容纳极端行情，但足以拦死接口串码/字段错位类的离谱值
MAX_DAILY_MOVE = 0.50

# 行情衍生字段（写回时允许覆盖的字段白名单思路：只更新这里列出的键）
QUOTE_FIELDS = ('price', 'prev_close', 'change', 'change_percent', 'volume', 'quote_time')


def _backup(data_file: str) -> Optional[str]:
    """写回前备份，保留原文件可追溯"""
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    bak = f"{data_file}.bak-{ts}"
    try:
        shutil.copy2(data_file, bak)
        return bak
    except Exception as e:
        print(f"[价格刷新] 备份失败(不阻断写入): {e}")
        return None


def _sanitize(code: str, quote: Dict, old_price: float):
    """行情合理性校验。返回 (accepted: bool, reason: str)"""
    price = float(quote.get('price') or 0)
    if price <= 0:
        return False, '价格<=0'

    prev = float(quote.get('prev_close') or 0)
    if prev > 0:
        move = abs(price - prev) / prev
        if move > MAX_DAILY_MOVE:
            return False, f'单日波动{move:.1%}超阈值(昨收{prev})'

    if old_price and old_price > 0 and prev > 0:
        dev_old = abs(price - old_price) / old_price
        dev_prev = abs(price - prev) / prev
        # 与持仓旧价、昨收同时大幅背离 → 高度疑似脏数据
        if dev_old > MAX_DAILY_MOVE and dev_prev > MAX_DAILY_MOVE:
            return False, f'与旧价偏离{dev_old:.1%}且与昨收背离{dev_prev:.1%}'

    return True, 'ok'


def refresh_stocks_file(data_file: Optional[str] = None, dry_run: bool = False) -> Dict:
    """
    刷新 stocks.json 中所有持仓的价格。

    Args:
        data_file: stocks.json 路径，默认取本文件上级目录 data/stocks.json
        dry_run: 只校验和打印，不写文件

    Returns:
        {
          'updated': [{'code','name','old','new','quote_time'}...],
          'skipped': [{'code','reason'}...],   # 校验拒绝或接口未返回
          'failed':  [{'code','reason'}...],   # 接口失败
          'backup':  str | None,
          'saved':   bool
        }
    """
    if data_file is None:
        data_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'data', 'stocks.json')

    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    stocks = data.get('stocks', [])

    # 批量取价（单次HTTP请求全部持仓）
    stock_list = [{'code': s.get('code', ''), 'market': s.get('market', 'A股')} for s in stocks]
    quotes = get_stock_quotes(stock_list)

    updated, skipped, failed = [], [], []

    for stock in stocks:
        code = stock.get('code', '')
        name = stock.get('name', '')
        market = stock.get('market', 'A股')
        tencent_code = normalize_tencent_code(code, market)

        quote = quotes.get(tencent_code)
        if not quote:
            failed.append({'code': code, 'name': name, 'reason': '接口未返回该股票'})
            continue

        old_price = float(stock.get('current_price') or 0)
        accepted, reason = _sanitize(code, quote, old_price)
        if not accepted:
            skipped.append({'code': code, 'name': name, 'reason': reason,
                            '接口价': quote.get('price'), '持仓价': old_price})
            continue

        new_price = float(quote['price'])
        changed = (new_price != old_price)
        if changed:
            stock['current_price'] = new_price
            stock['change'] = quote.get('change', 0)
            stock['change_percent'] = quote.get('change_percent', 0)
            stock['quote_time'] = quote.get('quote_time', '')      # 行情源时间戳（A股:20260924161442 / 港股:2026/09/25 16:08:20）
            stock['price_update_time'] = datetime.now().isoformat(timespec='seconds')
            shares = stock.get('shares', 0)
            if shares > 0:
                stock['market_value'] = round(new_price * shares, 2)
            updated.append({'code': code, 'name': name,
                            'old': round(old_price, 3), 'new': round(new_price, 3),
                            'quote_time': stock['quote_time']})

    saved, backup = False, None
    if updated and not dry_run:
        backup = _backup(data_file)
        tmp = data_file + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, data_file)   # 原子写回，写中断不留半文件
        saved = True

    return {'updated': updated, 'skipped': skipped, 'failed': failed,
            'backup': backup, 'saved': saved, 'dry_run': dry_run}


def format_summary(result: Dict) -> str:
    """人类可读的刷新结果汇报"""
    lines = []
    lines.append('=' * 64)
    lines.append(f"持仓价格刷新{'(试运行)' if result['dry_run'] else ''}结果  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append('=' * 64)

    if result['updated']:
        lines.append(f"\n✅ 已更新 {len(result['updated'])} 只:")
        for u in result['updated']:
            lines.append(f"  {u['name']}({u['code']}): {u['old']} → {u['new']}   行情时间:{u['quote_time'] or '未知'}")
    if result['skipped']:
        lines.append(f"\n⚠️ 校验拒绝 {len(result['skipped'])} 只(保留旧价):")
        for s in result['skipped']:
            lines.append(f"  {s['name']}({s['code']}): {s['reason']}  接口价={s.get('接口价')} 持仓价={s.get('持仓价')}")
    if result['failed']:
        lines.append(f"\n❌ 接口失败 {len(result['failed'])} 只:")
        for s in result['failed']:
            lines.append(f"  {s['name']}({s['code']}): {s['reason']}")
    if not (result['updated'] or result['skipped'] or result['failed']):
        lines.append("\n无持仓记录。")

    lines.append(f"\n备份: {result['backup'] or '无'}")
    lines.append(f"写回: {'是' if result['saved'] else '否'}")
    lines.append('=' * 64)
    return '\n'.join(lines)


if __name__ == '__main__':
    # 模块自测：python -m utils.price_refresh --dry-run
    import sys
    dry = '--dry-run' in sys.argv
    res = refresh_stocks_file(dry_run=dry)
    print(format_summary(res))
    sys.exit(1 if res['failed'] else 0)
