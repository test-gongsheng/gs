#!/bin/bash
# 完全清理并重新部署股票监控系统

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

echo "=== 步骤6: 启动服务 ==="
python3 app.py &
sleep 3

echo "=== 步骤7: 验证服务 ==="
curl -s http://localhost:8888/api/stocks | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f'API 状态: 正常，返回 {len(d)} 只股票')
"

echo ""
echo "=== 部署完成 ==="
echo "访问: http://localhost:8888"
echo ""
echo "如果浏览器显示旧版本，请按 Ctrl+Shift+N 打开无痕模式访问"
