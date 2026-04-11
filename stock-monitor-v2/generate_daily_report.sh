#!/bin/bash
# 每日持仓分析报告生成脚本
# 运行时间：每天 16:30（A股收盘后）

LOG_FILE="/root/.openclaw/workspace/stock-monitor-v2/stock-monitor-v2/reports/cron_$(date +%Y%m%d).log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始生成持仓分析报告..." >> "$LOG_FILE"

cd /root/.openclaw/workspace/stock-monitor-v2/stock-monitor-v2
source venv/bin/activate
python3 update_portfolio_analysis.py >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 报告生成成功" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 报告生成失败" >> "$LOG_FILE"
fi

echo "---" >> "$LOG_FILE"
