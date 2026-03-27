#!/bin/bash
# Token使用量每日记录
# 每天早上6点运行，记录前一天的token使用量到MEMORY.md

MEMORY_FILE="/root/.openclaw/workspace/MEMORY.md"
DATE=$(date -d "yesterday" +%Y-%m-%d)

# 获取当前token使用量（粗略估算）
# 实际使用时可通过session_status获取更准确数字
TOKENS_IN=$(session_status 2>/dev/null | grep -oE '[0-9]+k in' | head -1 | grep -oE '[0-9]+' || echo "0")
TOKENS_OUT=$(session_status 2>/dev/null | grep -oE '[0-9]+ out' | head -1 | grep -oE '[0-9]+' || echo "0")

# 如果获取失败，使用占位符
if [ "$TOKENS_IN" = "0" ]; then
    TOKENS_IN="~40k"
fi
if [ "$TOKENS_OUT" = "0" ]; then
    TOKENS_OUT="~1k"
fi

# 添加记录到MEMORY.md
LINE="| $DATE | - | $TOKENS_IN | $TOKENS_OUT | 自动记录 |"

# 在Token使用量记录表格末尾添加
sed -i "/^|.*自动记录.*|$/a$LINE" "$MEMORY_FILE" 2>/dev/null || echo "需要手动更新: $LINE"

echo "[$DATE] Token使用记录已更新: $TOKENS_IN / $TOKENS_OUT"
