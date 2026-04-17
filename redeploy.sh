#!/bin/bash
# 完全清理并重新部署股票监控系统
# 版本：v2.1 - 自动配置每日报告cron

echo "=== 步骤1: 停止所有 Flask 进程 ==="
pkill -f "app.py" 2>/dev/null
sleep 2

echo "=== 步骤2: 删除旧代码（确保没有残留）==="
cd ~
rm -rf gs gs_backup

echo "=== 步骤3: 重新克隆最新代码 ==="
git clone https://github.com/test-gongsheng/gs.git

echo "=== 步骤4: 验证版本 ==="
cd gs/stock-monitor-v2/stock-monitor-v2
git log --oneline -1

echo "=== 步骤5: 创建数据目录 ==="
mkdir -p data

# 创建默认数据文件
cat > data/stocks.json << 'EOF'
{
  "stocks": [],
  "portfolio": {
    "totalValue": 0,
    "totalCost": 0,
    "totalPnl": 0,
    "riskLevel": "normal"
  },
  "lastUpdate": null
}
EOF

echo "=== 步骤6: 配置每日自动报告 (cron) ==="
# 获取当前脚本的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_SCRIPT="$SCRIPT_DIR/generate_daily_report.sh"

# 创建报告脚本（如果不存在）
if [ ! -f "$REPORT_SCRIPT" ]; then
cat > "$REPORT_SCRIPT" << 'REPORTEOF'
#!/bin/bash
# 每日持仓分析报告生成脚本
# 运行时间：每天 16:35（A股收盘后）

LOG_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/reports/cron_$(date +%Y%m%d).log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始生成持仓分析报告..." >> "$LOG_FILE"

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检查虚拟环境
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 警告: 虚拟环境不存在" >> "$LOG_FILE"
fi

# 执行报告生成
if [ -f "update_portfolio_analysis.py" ]; then
    python3 update_portfolio_analysis.py >> "$LOG_FILE" 2>&1
    if [ $? -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 报告生成成功" >> "$LOG_FILE"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 报告生成失败" >> "$LOG_FILE"
    fi
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 错误: update_portfolio_analysis.py 不存在" >> "$LOG_FILE"
fi

echo "---" >> "$LOG_FILE"
REPORTEOF
    chmod +x "$REPORT_SCRIPT"
    echo "已创建报告脚本: $REPORT_SCRIPT"
fi

# 配置 cron（使用动态路径）
CRON_CMD="35 16 * * 1-5 cd '$SCRIPT_DIR' && bash generate_daily_report.sh >> /tmp/cron_portfolio.log 2>&1"

# 删除旧的股票监控 cron 任务
(crontab -l 2>/dev/null | grep -v "stock-monitor-v2" | grep -v "generate_daily_report") | crontab -

# 添加新的 cron 任务
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

# 验证配置
echo "当前 cron 配置:"
crontab -l | grep "generate_daily_report" || echo "未找到配置"

echo ""
echo "=== 步骤7: 启动服务 ==="
python3 app.py &
sleep 3

echo "=== 步骤8: 验证服务 ==="
curl -s http://localhost:8888/api/stocks | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'API 状态: 正常，返回 {len(d)} 只股票')
"

echo ""
echo "=========================================="
echo "=== 部署完成 ==="
echo "访问: http://localhost:8888"
echo ""
echo "【自动报告配置】"
echo "- 执行时间: 工作日 16:35"
echo "- 报告位置: reports/portfolio_analysis_YYYY-MM-DD.json"
echo "- 日志位置: reports/cron_YYYYMMDD.log"
echo "- Cron路径: $SCRIPT_DIR"
echo "=========================================="
echo ""
echo "如果浏览器显示旧版本，请按 Ctrl+Shift+N 打开无痕模式访问"
