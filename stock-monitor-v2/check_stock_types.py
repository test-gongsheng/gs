import json
import sys

# API returns list directly
data = json.load(sys.stdin)

# Handle both list and dict formats
if isinstance(data, list):
    stocks = data
else:
    stocks = data.get('stocks', [])

print('=' * 60)
print('📊 股票类型刷新完成')
print('=' * 60)

high_vol = []
normal = []

for stock in stocks:
    name = stock.get('name', '未知')
    code = stock.get('code', '未知')
    stock_type = stock.get('stock_type', 'unknown')
    vol_score = stock.get('vol_score', 0)
    annual_vol = stock.get('annual_vol', 0)
    atr_pct = stock.get('atr_pct', 0)
    
    info = f'  {name} ({code}) - 波动率得分: {vol_score:.1f}, 年化波动: {annual_vol:.2f}, ATR%: {atr_pct:.2f}%'
    
    if stock_type == 'high_vol':
        high_vol.append(info)
    else:
        normal.append(info)

print()
print(f'🔥 高波动股 ({len(high_vol)}只):')
print('-' * 40)
for item in high_vol:
    print(item)

print()
print(f'📈 普通股 ({len(normal)}只):')
print('-' * 40)
for item in normal:
    print(item)

print()
print(f'总计: {len(stocks)} 只股票已重新计算')
print('=' * 60)
