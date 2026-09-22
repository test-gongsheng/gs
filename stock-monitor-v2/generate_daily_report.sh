#!/bin/bash
# 每日持仓分析报告生成脚本
# 运行时间：每天 16:30（A股收盘后）
# 流程：情绪引擎 → 事件引擎 → 深度报告（引用情绪+事件数据）

LOG_FILE="/root/.openclaw/workspace/stock-monitor-v2/stock-monitor-v2/reports/cron_$(date +%Y%m%d).log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始生成持仓分析报告（含LLM增强）..." >> "$LOG_FILE"

cd /root/.openclaw/workspace/stock-monitor-v2/stock-monitor-v2
source venv/bin/activate

# 1. 市场情绪引擎（三四层）
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [1/3] 运行市场情绪引擎..." >> "$LOG_FILE"
python3 emotion_engine.py >> "$LOG_FILE" 2>&1

# 2. 事件驱动引擎（含解禁监控）
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [2/3] 运行事件驱动引擎..." >> "$LOG_FILE"
python3 event_tracker.py >> "$LOG_FILE" 2>&1

# 3. 深度报告（引用情绪+事件数据）
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [3/4] 生成深度分析报告..." >> "$LOG_FILE"
python3 deep_analysis.py >> "$LOG_FILE" 2>&1

# 4. LLM大模型增强（注入《AI实时研判》章节，--think深度思考模式=最高质量，失败自动降级为模板报告）
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [4/4] LLM大模型研判增强（深度思考模式）..." >> "$LOG_FILE"
python3 tools/llm_narrative.py --think >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 报告生成成功" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 报告生成失败" >> "$LOG_FILE"
fi

echo "---" >> "$LOG_FILE"
