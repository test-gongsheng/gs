# -*- coding: utf-8 -*-
"""
持仓价格刷新入口 - 把真实行情写回 data/stocks.json

用途：
  1. 手动修复：双击 / cron 直接运行本脚本，立即校正所有持仓价格
  2. 每日自愈已内置于 update_portfolio_analysis.py（16:05 任务会写回），
     本脚本用于随时手动触发或独立排程

退出码：0=全部成功(或有校验拒绝但接口正常)  1=存在接口失败
"""

import os
import sys

# 允许从仓库任意位置以 `python refresh_stocks_prices.py` 运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.price_refresh import refresh_stocks_file, format_summary


def main():
    dry_run = '--dry-run' in sys.argv

    result = refresh_stocks_file(dry_run=dry_run)
    print(format_summary(result))

    # 有接口失败时以非零码退出，便于计划任务/监控发现
    return 1 if result['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
