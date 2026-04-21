#!/bin/bash
# 数据备份/恢复脚本
# 解决重新部署时数据丢失问题

# 配置：数据持久化目录（在 git 仓库之外）
DATA_DIR="$HOME/stock-monitor-data"
REPO_DIR="/root/.openclaw/workspace/stock-monitor-v2/stock-monitor-v2"

# 创建持久化目录
mkdir -p "$DATA_DIR"

# 备份当前数据
backup() {
    echo "[备份] 保存当前数据到 $DATA_DIR"
    if [ -f "$REPO_DIR/data/stocks.json" ]; then
        cp "$REPO_DIR/data/stocks.json" "$DATA_DIR/stocks.json.bak"
        echo "[备份] stocks.json 已备份"
    fi
    if [ -f "$REPO_DIR/data/stocks.db" ]; then
        cp "$REPO_DIR/data/stocks.db" "$DATA_DIR/stocks.db.bak"
        echo "[备份] stocks.db 已备份"
    fi
    if [ -f "$REPO_DIR/reports/portfolio_analysis_latest.json" ]; then
        cp "$REPO_DIR/reports/portfolio_analysis_latest.json" "$DATA_DIR/portfolio_analysis_latest.json.bak"
        echo "[备份] 最新报告已备份"
    fi
    echo "[备份] 完成"
}

# 恢复数据到新的部署目录
restore() {
    echo "[恢复] 从 $DATA_DIR 恢复数据到 $REPO_DIR"
    
    # 确保目标目录存在
    mkdir -p "$REPO_DIR/data"
    mkdir -p "$REPO_DIR/reports"
    
    if [ -f "$DATA_DIR/stocks.json.bak" ]; then
        cp "$DATA_DIR/stocks.json.bak" "$REPO_DIR/data/stocks.json"
        echo "[恢复] stocks.json 已恢复"
    else
        echo "[恢复] 警告：找不到 stocks.json 备份"
    fi
    
    if [ -f "$DATA_DIR/stocks.db.bak" ]; then
        cp "$DATA_DIR/stocks.db.bak" "$REPO_DIR/data/stocks.db"
        echo "[恢复] stocks.db 已恢复"
    fi
    
    if [ -f "$DATA_DIR/portfolio_analysis_latest.json.bak" ]; then
        cp "$DATA_DIR/portfolio_analysis_latest.json.bak" "$REPO_DIR/reports/portfolio_analysis_latest.json"
        echo "[恢复] 最新报告已恢复"
    fi
    
    echo "[恢复] 完成"
}

# 显示当前数据状态
status() {
    echo "=== 持久化数据目录 ==="
    ls -la "$DATA_DIR"
    echo ""
    echo "=== 当前仓库数据 ==="
    ls -la "$REPO_DIR/data/" 2>/dev/null || echo "无数据目录"
}

# 主命令
case "$1" in
    backup)
        backup
        ;;
    restore)
        restore
        ;;
    status)
        status
        ;;
    *)
        echo "用法: $0 {backup|restore|status}"
        echo ""
        echo "  backup  - 备份当前持仓数据到持久化目录"
        echo "  restore - 从持久化目录恢复数据到当前部署"
        echo "  status  - 查看备份和当前数据状态"
        echo ""
        echo "数据持久化目录: $DATA_DIR"
        exit 1
        ;;
esac
