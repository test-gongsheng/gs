import re

# 读取原始文件
with open('update_portfolio_analysis.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 修改 analyze_stock_detailed 函数定义
content = content.replace(
    'def analyze_stock_detailed(stock: Dict, realtime_price: float = 0, realtime_axis: float = 0) -> Dict:',
    'def analyze_stock_detailed(stock: Dict, realtime_price: float = 0, realtime_axis: float = 0, portfolio_data: Dict = None) -> Dict:'
)

# 2. 在 P0技术分析 后插入三个维度计算
old_text = '''    # P0级别技术分析
    tech_data = None
    if analyze_technical_p0:
        print(f"[P0分析] {code} 获取技术指标...")
        tech_data = analyze_technical_p0(code, market, current_price)
    
    # 生成详细分析内容'''

new_text = '''    # P0级别技术分析
    tech_data = None
    if analyze_technical_p0:
        print(f"[P0分析] {code} 获取技术指标...")
        tech_data = analyze_technical_p0(code, market, current_price)
    
    # ========== 新增：三个高价值维度分析 ==========
    
    # 1. 加减仓质量评分（执行点位精准度）
    trade_quality = calculate_trade_quality(stock, trigger_buy, trigger_sell, current_price)
    
    # 2. 高波动股特权利用率（浮动仓使用率）
    privilege_utilization = calculate_privilege_utilization(stock, cost_value, market_value)
    
    # 3. 持仓集中度动态偏离（P0/P2占比偏离）
    concentration_deviation = calculate_concentration_deviation(stock, market_value, portfolio_data)
    
    # ==============================================
    
    # 生成详细分析内容'''

content = content.replace(old_text, new_text)

# 3. 在 result 字典中添加三个新维度
old_result = '''        # P0技术指标
        'technical_indicators': tech_data,
        # 详细分析内容'''

new_result = '''        # P0技术指标
        'technical_indicators': tech_data,
        # 新增：三个高价值维度
        'trade_quality': trade_quality,
        'privilege_utilization': privilege_utilization,
        'concentration_deviation': concentration_deviation,
        # 详细分析内容'''

content = content.replace(old_result, new_result)

# 写回文件
with open('update_portfolio_analysis.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ 文件主体修改完成')
