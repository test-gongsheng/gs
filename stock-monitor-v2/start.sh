#!/bin/bash
# 股票投资监控系统 v2.0 启动脚本

echo "================================"
echo "股票投资监控系统 v2.0"
echo "================================"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "错误：未找到 Python3"
    exit 1
fi

# 检查依赖
echo "检查依赖..."
pip3 install flask flask-cors -q

# 启动应用
echo "启动系统..."
echo "访问地址: http://localhost:5000"
echo ""

cd "$(dirname "$0")"
python3 app.py
