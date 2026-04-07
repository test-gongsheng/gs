#!/bin/bash
# 刷新股票类型并推送通知到主会话

cd /root/.openclaw/workspace/stock-monitor-v2

# 1. 清除缓存
python3 -c "
import json
data = json.load(open('data/stocks.json'))
for s in data['stocks']:
    for k in ['stock_type', 'vol_score', 'annual_vol', 'atr_pct', 'stock_type_calculated', 'stock_type_calc_time']:
        s.pop(k, None)
json.dump(data, open('data/stocks.json', 'w'), ensure_ascii=False, indent=2)
print('缓存已清除')
"

# 2. 触发重新计算
curl -s http://localhost:8888/api/stocks > /tmp/stock_types.json

# 3. 生成报告
python3 << 'EOF'
import json
with open('/tmp/stock_types.json') as f:
    data = json.load(f)

high_vol = [s for s in data if s.get('stock_type') == 'high_vol']
normal = [s for s in data if s.get('stock_type') == 'normal']
failed = [s for s in data if not s.get('stock_type_calculated')]

print(f"📊 股票类型刷新完成\n")
print(f"高波动股 ({len(high_vol)}只):")
for s in high_vol:
    print(f"  • {s['name']} ({s['code']}): {s['vol_score']}分")
print(f"\n普通股 ({len(normal)}只):")
for s in normal:
    print(f"  • {s['name']} ({s['code']}): {s['vol_score']}分")
if failed:
    print(f"\n⚠️ 计算失败 ({len(failed)}只):", ", ".join([s['name'] for s in failed]))
EOF
