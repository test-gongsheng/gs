#!/usr/bin/env python3
"""
Token使用量记录脚本
每日运行，记录前一天的token使用量到MEMORY.md
"""

import os
import re
import json
from datetime import datetime, timedelta

WORKSPACE_DIR = '/root/.openclaw/workspace'
MEMORY_FILE = os.path.join(WORKSPACE_DIR, 'MEMORY.md')

def get_token_usage():
    """获取当前token使用量"""
    try:
        # 读取session status
        import subprocess
        result = subprocess.run(
            ['openclaw', 'status', '--json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            tokens = data.get('tokens', {})
            return {
                'in': tokens.get('in', 0),
                'out': tokens.get('out', 0)
            }
    except Exception as e:
        print(f"获取token使用量失败: {e}")
    
    return {'in': 0, 'out': 0}

def update_memory_md(date_str, tokens_in, tokens_out, note=""):
    """更新MEMORY.md中的token记录表"""
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 构建新行
        new_line = f"| {date_str} | - | ~{tokens_in//1000}k | ~{tokens_out//1000}k | {note} |\n"
        
        # 查找表格位置
        pattern = r'(## Token使用量记录\n\n\| 日期 \| 会话数 \| Tokens \(in\) \| Tokens \(out\) \| 备注 \|\n\|[-| ]+\|[-| ]+\|[-| ]+\|[-| ]+\|[-| ]+\|)\n'
        match = re.search(pattern, content)
        
        if match:
            # 在表格末尾插入新行
            insert_pos = match.end()
            content = content[:insert_pos] + new_line + content[insert_pos:]
            
            with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✅ 已记录 {date_str} 的token使用量")
            return True
        else:
            print("⚠️ 未找到token记录表格")
            return False
            
    except Exception as e:
        print(f"更新MEMORY.md失败: {e}")
        return False

def main():
    """主函数"""
    # 获取昨天日期（因为是记录前一天的用量）
    yesterday = datetime.now() - timedelta(days=1)
    date_str = yesterday.strftime('%Y-%m-%d')
    
    # 获取token使用量
    tokens = get_token_usage()
    
    # 更新记录
    success = update_memory_md(
        date_str, 
        tokens.get('in', 0), 
        tokens.get('out', 0),
        note="自动记录"
    )
    
    return 0 if success else 1

if __name__ == '__main__':
    exit(main())
