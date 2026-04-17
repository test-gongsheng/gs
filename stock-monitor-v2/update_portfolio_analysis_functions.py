# -*- coding: utf-8 -*-


# ========== 三个高价值维度分析函数 ==========

def calculate_trade_quality(stock, trigger_buy, trigger_sell, current_price):
    """计算加减仓质量评分"""
    last_trade_price = stock.get('last_trade_price', 0)
    last_trade_type = stock.get('last_trade_type', '')
    shares = stock.get('shares', 0)
    
    if not last_trade_price or not last_trade_type:
        return {
            'has_trade': False,
            'grade': '无交易记录',
            'detail': '暂无近期交易记录，无法评估执行质量'
        }
    
    if last_trade_type == 'buy':
        deviation = ((last_trade_price - trigger_buy) / trigger_buy * 100) if trigger_buy > 0 else 0
        if deviation <= 0:
            grade = 'A'
            detail = f'买入执行优秀，比理论买点低{abs(deviation):.1f}%，省了约{shares*abs(deviation/100)*trigger_buy:.0f}元'
        elif deviation <= 2:
            grade = 'B'
            detail = f'买入执行良好，比理论买点高{deviation:.1f}%，在合理范围'
        elif deviation <= 5:
            grade = 'C'
            detail = f'买入执行一般，比理论买点贵{deviation:.1f}%，多花约{shares*(deviation/100)*trigger_buy:.0f}元'
        else:
            grade = 'D'
            detail = f'买入执行较差，比理论买点贵{deviation:.1f}%，建议检查刷新延迟或执行犹豫'
    else:
        deviation = ((last_trade_price - trigger_sell) / trigger_sell * 100) if trigger_sell > 0 else 0
        if deviation >= 0:
            grade = 'A'
            detail = f'卖出执行优秀，比理论卖点高{deviation:.1f}%，多赚约{shares*(deviation/100)*trigger_sell:.0f}元'
        elif deviation >= -2:
            grade = 'B'
            detail = f'卖出执行良好，比理论卖点低{abs(deviation):.1f}%，基本达标'
        elif deviation >= -5:
            grade = 'C'
            detail = f'卖出执行一般，比理论卖点低{abs(deviation):.1f}%，少赚约{shares*(abs(deviation)/100)*trigger_sell:.0f}元'
        else:
            grade = 'D'
            detail = f'卖出执行较差，比理论卖点低{abs(deviation):.1f}%，提前离场损失较大'
    
    return {
        'has_trade': True,
        'last_trade_type': last_trade_type,
        'deviation': round(deviation, 2),
        'grade': grade,
        'detail': detail
    }


def calculate_privilege_utilization(stock, cost_value, market_value):
    """计算高波动股特权利用率"""
    stock_type = stock.get('stock_type', 'normal')
    
    if stock_type != 'high_vol':
        return {
            'is_high_vol': False,
            'grade': '普通股',
            'detail': '普通股浮动上限150%，无高波动特权'
        }
    
    base_pct = stock.get('base_position_pct', 50)
    privilege_limit = 200
    
    if cost_value > 0:
        actual_position_pct = (market_value / cost_value) * 100
    else:
        actual_position_pct = 100
    
    base_value = cost_value * (base_pct / 100)
    float_value = market_value - base_value
    max_float = cost_value * (privilege_limit / 100)
    
    utilization = (float_value / max_float * 100) if max_float > 0 else 0
    utilization = max(0, min(100, utilization))
    
    if utilization >= 80:
        grade = '优秀'
        detail = f'浮动仓位用到{utilization:.0f}%，接近200%上限，最大化享受波动收益'
    elif utilization >= 50:
        grade = '良好'
        detail = f'浮动仓位用到{utilization:.0f}%，还有提升空间'
    elif utilization >= 20:
        grade = '一般'
        detail = f'浮动仓位仅{utilization:.0f}%，建议更积极执行网格'
    else:
        grade = '严重不足'
        detail = f'浮动仓位仅{utilization:.0f}%，白扔了高波动优势。同类平均80%+'
    
    return {
        'is_high_vol': True,
        'utilization_rate': round(utilization, 1),
        'grade': grade,
        'detail': detail,
        'potential': f'若用到80%可多赚约{cost_value * 0.8 * 0.08:.0f}元/轮' if utilization < 80 else '已充分利用'
    }


def calculate_concentration_deviation(stock, market_value, portfolio_data):
    """计算持仓集中度动态偏离"""
    priority = stock.get('priority', 'P2')
    code = stock.get('code', '')
    
    if not portfolio_data:
        return {'priority': priority, 'grade': '无数据', 'detail': '无法获取组合数据'}
    
    total = sum(s.get('market_value', 0) for s in portfolio_data.get('stocks', []))
    if total == 0:
        return {'priority': priority, 'grade': '无数据', 'detail': '总市值为零'}
    
    current_weight = (market_value / total) * 100
    stocks = portfolio_data.get('stocks', [])
    p0_cnt = sum(1 for s in stocks if s.get('priority') == 'P0')
    p2_cnt = sum(1 for s in stocks if s.get('priority') == 'P2')
    
    target = (60 / p0_cnt) if priority == 'P0' and p0_cnt > 0 else (40 / p2_cnt if p2_cnt > 0 else 10)
    deviation = current_weight - target
    
    p0_actual = sum(s.get('market_value', 0) for s in stocks if s.get('priority') == 'P0') / total * 100
    p2_actual = sum(s.get('market_value', 0) for s in stocks if s.get('priority') == 'P2') / total * 100
    
    if abs(deviation) <= 5:
        grade = '正常'
        detail = f'占比合理，实际{current_weight:.1f}% vs 目标{target:.1f}%'
    elif deviation > 10:
        grade = '⚠️ 超配'
        detail = f'{code}占比{current_weight:.1f}%超配{deviation:.1f}%，违背优先级设定'
    elif deviation > 5:
        grade = '略超配'
        detail = f'{code}占比{current_weight:.1f}%略超配{deviation:.1f}%'
    elif deviation < -10:
        grade = '⚠️ 低配'
        detail = f'{code}占比{current_weight:.1f}%低配{abs(deviation):.1f}%，资金被占用'
    else:
        grade = '略低配'
        detail = f'{code}占比{current_weight:.1f}%略低配{abs(deviation):.1f}%'
    
    return {
        'priority': priority,
        'current_weight': round(current_weight, 1),
        'target_weight': round(target, 1),
        'deviation': round(deviation, 1),
        'p0_actual_total': round(p0_actual, 1),
        'p2_actual_total': round(p2_actual, 1),
        'grade': grade,
        'detail': detail
    }

# ==============================================
