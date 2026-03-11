from flask import Flask, render_template, jsonify, request
import json
import os
from datetime import datetime
from utils.stock_quote import get_stock_quotes, get_dynamic_axis_price

app = Flask(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'stocks.json')

def load_data():
    """加载股票数据"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading data: {e}")
        return {
            "portfolio": {
                "total_capital": 8000000,
                "a_stock_limit": 500000,
                "a_stock_focus_limit": 1000000,
                "hk_stock_limit": 1500000,
                "strategy": "左侧交易+中轴价格仓位控制法+个性化网格策略"
            },
            "stocks": [],
            "market_sentiment": {},
            "hot_sectors": [],
            "alerts": [],
            "risk_control": {}
        }

def save_data(data):
    """保存股票数据"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')

@app.route('/api/portfolio')
def get_portfolio():
    """获取投资组合配置"""
    data = load_data()
    return jsonify(data['portfolio'])

@app.route('/api/stocks')
def get_stocks():
    """获取所有股票"""
    data = load_data()
    return jsonify(data['stocks'])

@app.route('/api/stocks', methods=['POST'])
def add_stock():
    """添加股票"""
    data = load_data()
    new_stock = request.json
    
    # 生成唯一ID
    max_id = max([int(s['id']) for s in data['stocks']], default=0)
    new_stock['id'] = str(max_id + 1)
    new_stock['status'] = '监控中'
    
    # 计算市值
    new_stock['market_value'] = new_stock.get('current_price', 0) * new_stock.get('shares', 0)
    
    data['stocks'].append(new_stock)
    
    # 更新风险控制数据
    update_risk_control(data)
    
    if save_data(data):
        return jsonify({'success': True, 'stock': new_stock})
    return jsonify({'success': False, 'error': '保存失败'}), 500

@app.route('/api/stocks/<stock_id>', methods=['PUT'])
def update_stock(stock_id):
    """更新股票信息"""
    data = load_data()
    update_data = request.json
    
    for stock in data['stocks']:
        if stock['id'] == stock_id:
            stock.update(update_data)
            # 重新计算市值
            stock['market_value'] = stock.get('current_price', 0) * stock.get('shares', 0)
            
            # 更新风险控制数据
            update_risk_control(data)
            
            if save_data(data):
                return jsonify({'success': True, 'stock': stock})
            return jsonify({'success': False, 'error': '保存失败'}), 500
    
    return jsonify({'success': False, 'error': '股票不存在'}), 404

@app.route('/api/stocks/<stock_id>', methods=['DELETE'])
def delete_stock(stock_id):
    """删除股票"""
    data = load_data()
    data['stocks'] = [s for s in data['stocks'] if s['id'] != stock_id]
    
    # 更新风险控制数据
    update_risk_control(data)
    
    if save_data(data):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': '保存失败'}), 500

@app.route('/api/stocks/<stock_id>/axis', methods=['PUT'])
def update_axis_price(stock_id):
    """更新中轴价格"""
    data = load_data()
    axis_data = request.json
    
    for stock in data['stocks']:
        if stock['id'] == stock_id:
            stock['axis_price'] = axis_data.get('axis_price')
            stock['base_position_pct'] = axis_data.get('base_position_pct', 50)
            stock['float_position_pct'] = axis_data.get('float_position_pct', 50)
            stock['trigger_pct'] = axis_data.get('trigger_pct', 8)
            
            # 更新网格
            if 'grid_levels' in axis_data:
                stock['grid_levels'] = axis_data['grid_levels']
            
            if save_data(data):
                return jsonify({'success': True, 'stock': stock})
            return jsonify({'success': False, 'error': '保存失败'}), 500
    
    return jsonify({'success': False, 'error': '股票不存在'}), 404

@app.route('/api/market/sentiment')
def get_market_sentiment():
    """获取市场情绪"""
    data = load_data()
    return jsonify(data['market_sentiment'])

@app.route('/api/market/hot-sectors')
def get_hot_sectors():
    """获取热点板块"""
    data = load_data()
    return jsonify(data['hot_sectors'])

@app.route('/api/alerts')
def get_alerts():
    """获取所有提醒"""
    data = load_data()
    return jsonify(data['alerts'])

@app.route('/api/alerts', methods=['POST'])
def add_alert():
    """添加提醒"""
    data = load_data()
    new_alert = request.json
    
    max_id = max([int(a['id']) for a in data['alerts']], default=0)
    new_alert['id'] = str(max_id + 1)
    new_alert['trigger_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    new_alert['status'] = 'active'
    
    data['alerts'].append(new_alert)
    
    if save_data(data):
        return jsonify({'success': True, 'alert': new_alert})
    return jsonify({'success': False, 'error': '保存失败'}), 500

@app.route('/api/alerts/<alert_id>/ack', methods=['POST'])
def acknowledge_alert(alert_id):
    """确认提醒"""
    data = load_data()
    
    for alert in data['alerts']:
        if alert['id'] == alert_id:
            alert['status'] = 'acknowledged'
            if save_data(data):
                return jsonify({'success': True, 'alert': alert})
            return jsonify({'success': False, 'error': '保存失败'}), 500
    
    return jsonify({'success': False, 'error': '提醒不存在'}), 404

@app.route('/api/alerts/<alert_id>', methods=['DELETE'])
def delete_alert(alert_id):
    """删除提醒"""
    data = load_data()
    data['alerts'] = [a for a in data['alerts'] if a['id'] != alert_id]
    
    if save_data(data):
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': '保存失败'}), 500

@app.route('/api/risk/control')
def get_risk_control():
    """获取风险控制数据"""
    data = load_data()
    return jsonify(data['risk_control'])

@app.route('/api/dashboard')
def get_dashboard():
    """获取仪表盘数据"""
    data = load_data()
    return jsonify({
        'portfolio': data['portfolio'],
        'stocks': data['stocks'],
        'market_sentiment': data['market_sentiment'],
        'hot_sectors': data['hot_sectors'],
        'alerts': data['alerts'],
        'risk_control': data['risk_control']
    })

@app.route('/api/reports/summary')
def get_report_summary():
    """获取报表摘要"""
    data = load_data()
    stocks = data['stocks']
    
    total_cost = sum(s.get('avg_cost', 0) * s.get('shares', 0) for s in stocks)
    total_value = sum(s.get('market_value', 0) for s in stocks)
    total_profit = total_value - total_cost
    profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0
    
    a_stocks = [s for s in stocks if s.get('market') == 'A股']
    hk_stocks = [s for s in stocks if s.get('market') == '港股']
    
    return jsonify({
        'total_cost': total_cost,
        'total_value': total_value,
        'total_profit': total_profit,
        'profit_pct': profit_pct,
        'stock_count': len(stocks),
        'a_stock_count': len(a_stocks),
        'hk_stock_count': len(hk_stocks),
        'position_ratio': data['risk_control'].get('position_ratio', 0)
    })

def update_risk_control(data):
    """更新风险控制数据"""
    stocks = data['stocks']
    portfolio = data['portfolio']
    
    total_value = sum(s.get('market_value', 0) for s in stocks)
    a_stock_exposure = sum(s.get('market_value', 0) for s in stocks if s.get('market') == 'A股')
    hk_stock_exposure = sum(s.get('market_value', 0) for s in stocks if s.get('market') == '港股')
    
    # 检查止损触发
    stop_loss_triggered = sum(1 for s in stocks 
                              if s.get('current_price', 0) < s.get('stop_loss', float('inf')))
    
    data['risk_control'] = {
        'total_position_value': total_value,
        'position_ratio': round(total_value / portfolio['total_capital'] * 100, 2),
        'max_position_ratio': 80,
        'a_stock_exposure': a_stock_exposure,
        'hk_stock_exposure': hk_stock_exposure,
        'stop_loss_triggered': stop_loss_triggered,
        'base_position_protected': True
    }

@app.route('/api/quotes', methods=['POST'])
def get_quotes():
    """获取实时行情"""
    try:
        stocks = request.json.get('stocks', [])
        if not stocks:
            return jsonify({'success': False, 'error': '股票列表为空'}), 400
        
        quotes = get_stock_quotes(stocks)
        
        # 转换为前端格式
        result = {}
        for stock in stocks:
            code = stock.get('code', '')
            market = stock.get('market', 'A股')
            
            # 构造新浪代码key
            from utils.stock_quote import normalize_stock_code
            sina_code = normalize_stock_code(code, market)
            
            quote = quotes.get(sina_code)
            if quote:
                result[code] = {
                    'price': quote['price'],
                    'change': quote['change'],
                    'change_percent': quote['change_percent'],
                    'open': quote['open'],
                    'high': quote['high'],
                    'low': quote['low'],
                    'prev_close': quote['prev_close'],
                    'volume': quote['volume'],
                    'name': quote['name']
                }
        
        return jsonify({'success': True, 'quotes': result})
    except Exception as e:
        print(f"获取行情失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/axis-price', methods=['POST'])
def get_axis_price():
    """
    获取动态中轴价格（基于3个月历史数据）
    
    请求体: {"code": "000559", "market": "A股", "days": 90}
    """
    try:
        data = request.json
        code = data.get('code', '')
        market = data.get('market', 'A股')
        days = data.get('days', 90)
        
        if not code:
            return jsonify({'success': False, 'error': '股票代码不能为空'}), 400
        
        axis_data = get_dynamic_axis_price(code, market, days)
        
        if not axis_data:
            return jsonify({'success': False, 'error': '获取历史数据失败'}), 500
        
        return jsonify({
            'success': True,
            'data': axis_data
        })
    except Exception as e:
        print(f"获取中轴价格失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
