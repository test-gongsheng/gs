#!/bin/bash
cd /root/.openclaw/workspace/stock-monitor-v2
pkill -f "python.*app.py" 2>/dev/null
sleep 2
venv/bin/python app.py > /tmp/stock_monitor.log 2>&1 &
echo "服务已启动"
