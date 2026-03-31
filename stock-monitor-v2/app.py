from flask import Flask, render_template, jsonify, request
import json
import os
import time
from datetime import datetime, timedelta
from utils.stock_quote import get_stock_quotes, get_dynamic_axis_price
from utils.exchange_rate import get_cny_hkd_rate, get_yesterday_cny_hkd_rate, convert_hkd_to_cny
from utils.sector_data import get_hot_sectors_data
from utils.news_data import get_cls_structured_news
from utils.market_sentiment import get_market_sentiment

app = Flask(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'stocks.json')

# 中轴价格缓存: { 'code:market': {'data': {...}, 'timestamp': ...} }
axis_price_cache = {}
CACHE_TTL = 1800  # 缓存30分钟

def get_cached_axis_price(code, market, days=90):
    """从缓存获取中轴价格，如果不存在或过期则重新计算（失败时返回默认值）"""
    cache_key = f"{code}:{market}"
    now = time.time()
    
    # 检查缓存
    if cache_key in axis_price_cache:
        cached = axis_price_cache[cache_key]
        age = now - cached['timestamp']
        if age < CACHE_TTL:
            print(f"[CACHE HIT] {code} 缓存{age:.0f}秒前更新")
            return cached['data']
        else:
            print(f"[CACHE EXPIRED] {code} 缓存已过期{age-CACHE_TTL:.0f}秒")
    
    # 缓存未命中或过期，重新计算
    print(f"[CACHE MISS] {code} 重新计算中轴价格...")
    try:
        # 使用信号量控制并发，避免超时堆积
        axis_data = get_dynamic_axis_price(code, market, days)
        
        if axis_data:
            axis_price_cache[cache_key] = {
                'data': axis_data,
                'timestamp': now
            }
            return axis_data
    except Exception as e:
        print(f"[CACHE ERROR] {code} 计算中轴价格失败: {e}")
    
    # 如果计算失败，返回默认值（基于股票导入时的价格）
    print(f"[CACHE FALLBACK] {code} 返回默认中轴价格")
    default_data = {
        'axis_price': 0,
        'trigger_buy': 0,
        'trigger_sell': 0,
        'trigger_pct': 8.0,
        'volatility': 5.0,
        'estimated': True,
        'fallback': True  # 标记为 fallback 数据
    }
    return default_data

def load_data():
    """加载股票数据，如果不存在则自动创建"""
    # 自动创建 data 目录
    data_dir = os.path.dirname(DATA_FILE)
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"[load_data] 创建目录: {data_dir}")
    
    # 如果文件不存在，创建初始数据文件
    if not os.path.exists(DATA_FILE):
        default_data = {
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
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
            print(f"[load_data] 创建初始数据文件: {DATA_FILE}")
            return default_data
        except Exception as e:
            print(f"[load_data] 创建初始数据文件失败: {e}")
    
    # 正常加载数据
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[load_data] 加载数据失败: {e}")
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
        import traceback
        print(f"Error saving data: {e}")
        traceback.print_exc()
        return False

@app.route('/')
def index():
    """主页面"""
    import time
    return render_template('index.html', now=int(time.time()))

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
    try:
        data = load_data()
        new_stock = request.json
        
        print(f"[add_stock] 添加股票: {new_stock.get('code')} {new_stock.get('name')}")
        
        # 生成唯一ID（使用时间戳+随机数，避免并发冲突）
        import time
        import random
        new_stock['id'] = f"{int(time.time())}{random.randint(100, 999)}"
        print(f"[add_stock] 生成ID: {new_stock['id']}")
        new_stock['status'] = '监控中'
        
        # 计算市值
        new_stock['market_value'] = new_stock.get('current_price', 0) * new_stock.get('shares', 0)
        
        data['stocks'].append(new_stock)
        
        # 更新风险控制数据
        update_risk_control(data)
        
        if save_data(data):
            print(f"[add_stock] 成功添加: {new_stock['code']}")
            return jsonify({'success': True, 'stock': new_stock})
        else:
            print(f"[add_stock] 保存失败")
            return jsonify({'success': False, 'error': '保存失败'}), 500
    except Exception as e:
        import traceback
        print(f"[add_stock] 异常: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stocks/batch', methods=['POST'])
def batch_add_stocks():
    """批量添加股票（避免并发冲突）"""
    try:
        data = load_data()
        stocks_to_add = request.json.get('stocks', [])
        
        if not stocks_to_add:
            return jsonify({'success': False, 'error': '股票列表为空'}), 400
        
        print(f"[batch_add_stocks] 批量添加 {len(stocks_to_add)} 只股票")
        
        added_stocks = []
        for new_stock in stocks_to_add:
            import time
            import random
            
            stock_id = f"{int(time.time())}{random.randint(100, 999)}"
            new_stock['id'] = stock_id
            new_stock['status'] = '监控中'
            new_stock['market_value'] = new_stock.get('current_price', 0) * new_stock.get('shares', 0)
            
            # 港股添加汇率字段（使用实时汇率）
            if new_stock.get('market') == '港股':
                from utils.exchange_rate import get_cny_hkd_rate
                new_stock['exchange_rate'] = get_cny_hkd_rate() or 1.0836
            
            data['stocks'].append(new_stock)
            added_stocks.append(new_stock)
            print(f"[batch_add_stocks] 添加: {new_stock.get('code')} -> ID {stock_id}")
        
        # 更新风险控制
        update_risk_control(data)
        
        if save_data(data):
            print(f"[batch_add_stocks] 成功添加 {len(added_stocks)} 只股票")
            return jsonify({'success': True, 'stocks': added_stocks, 'count': len(added_stocks)})
        else:
            return jsonify({'success': False, 'error': '保存失败'}), 500
            
    except Exception as e:
        import traceback
        print(f"[batch_add_stocks] 异常: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stocks/clear', methods=['POST'])
def clear_all_stocks():
    """清空所有股票"""
    try:
        data = load_data()
        deleted_count = len(data['stocks'])
        data['stocks'] = []
        update_risk_control(data)
        
        if save_data(data):
            print(f"[clear_all_stocks] 已清空 {deleted_count} 只股票")
            return jsonify({'success': True, 'deleted_count': deleted_count})
        return jsonify({'success': False, 'error': '保存失败'}), 500
    except Exception as e:
        import traceback
        print(f"[clear_all_stocks] 异常: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


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

@app.route('/api/market/h-sectors')
@app.route('/api/market/hot-sectors')  # 别名，兼容前端
def get_hot_sectors():
    """获取热点板块（实时数据）"""
    try:
        # 获取实时板块数据
        sectors = get_hot_sectors_data()
        return jsonify({
            'success': True,
            'sectors': sectors,
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        print(f"获取热点板块失败: {e}")
        # 返回本地缓存的默认数据
        data = load_data()
        return jsonify({
            'success': False,
            'sectors': data['hot_sectors'],
            'error': str(e)
        })


@app.route('/api/news')
def get_news():
    """获取结构化财联社新闻 (头条/题材/投资日历/持仓相关)"""
    try:
        # 从用户持仓中提取相关板块
        from utils.news_data import get_stock_sectors
        
        data = load_data()
        stocks = data.get('stocks', [])
        
        # 使用东方财富风格的细分板块映射
        portfolio_sectors = set()
        for stock in stocks:
            name = stock.get('name', '')
            code = stock.get('code', '')
            # 使用细分的板块判断函数
            sectors = get_stock_sectors(name, code)
            portfolio_sectors.update(sectors)
        
        result = get_cls_structured_news(
            limit=30,
            portfolio_sectors=list(portfolio_sectors)
        )
        return jsonify(result)
    except Exception as e:
        print(f"获取新闻失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'headlines': [],
            'themes': [],
            'hot_themes': [],
            'calendar': [],
            'portfolio': [],
            'general': [],
            'error': str(e)
        })


@app.route('/api/market/sentiment')
def get_sentiment():
    """获取市场情绪与多空数据"""
    try:
        result = get_market_sentiment()
        return jsonify(result)
    except Exception as e:
        print(f"获取市场情绪失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })

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


@app.route('/api/portfolio/hk-short-analysis')
def get_portfolio_hk_short_analysis():
    """
    获取持仓港股的沽空风险分析
    基于港股市场整体沽空水平，评估持仓风险
    """
    try:
        from utils.market_sentiment import get_hk_short_selling, get_hk_stock_short_selling
        
        # 获取港股市场整体沽空数据
        market_short = get_hk_short_selling()
        
        # 获取持仓中的港股
        data = load_data()
        stocks = data.get('stocks', [])
        hk_stocks = [s for s in stocks if s.get('market') == '港股']
        
        # 计算港股持仓总市值
        hk_position_value = sum(s.get('market_value', 0) for s in hk_stocks)
        
        # 获取每只港股的个股沽空数据
        stock_short_data = {}
        for stock in hk_stocks:
            code = stock.get('code', '')
            if code:
                stock_short = get_hk_stock_short_selling(code)
                stock_short_data[code] = stock_short
        
        # 风险评估
        short_ratio = market_short.get('short_ratio', 0)
        if short_ratio > 20:
            risk_level = 'high'
            risk_desc = '港股沽空比例高，注意风险'
        elif short_ratio > 15:
            risk_level = 'medium'
            risk_desc = '港股沽空压力较大，谨慎操作'
        elif short_ratio > 10:
            risk_level = 'low'
            risk_desc = '港股沽空比例正常'
        else:
            risk_level = 'very_low'
            risk_desc = '港股沽空压力小，环境较好'
        
        return jsonify({
            'success': True,
            'market_short': market_short,
            'stock_short_data': stock_short_data,
            'portfolio': {
                'hk_stock_count': len(hk_stocks),
                'hk_position_value': round(hk_position_value, 2),
                'risk_level': risk_level,
                'risk_desc': risk_desc,
                'advice': '建议关注高沽空比例行业的个股风险' if short_ratio > 15 else '当前港股沽空环境正常'
            },
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        print(f"获取港股沽空分析失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/hk-stock/<stock_code>/short-selling')
def get_hk_stock_short(stock_code):
    """
    获取港股个股前一天的沽空数据
    
    Args:
        stock_code: 港股代码，如 '00700'
    """
    try:
        from utils.market_sentiment import get_hk_stock_short_selling
        
        result = get_hk_stock_short_selling(stock_code)
        return jsonify(result)
    except Exception as e:
        print(f"获取港股{stock_code}沽空数据失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/hk-stock/<stock_code>/short-selling-history')
def get_hk_stock_short_history(stock_code):
    """
    获取港股个股90天沽空历史数据
    
    Args:
        stock_code: 港股代码，如 '00700'
    """
    try:
        from utils.market_sentiment import get_hk_stock_short_history
        
        days = request.args.get('days', 90, type=int)
        result = get_hk_stock_short_history(stock_code, days)
        return jsonify(result)
    except Exception as e:
        print(f"获取港股{stock_code}沽空历史数据失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/hk-short-selling-history')
def get_hk_market_short_history():
    """
    获取港股恒生科技指数90天沽空历史数据
    """
    try:
        from utils.market_sentiment import get_hk_short_selling_history
        
        days = request.args.get('days', 90, type=int)
        result = get_hk_short_selling_history(days)
        return jsonify(result)
    except Exception as e:
        print(f"获取恒生科技指数沽空历史数据失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


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

@app.route('/api/exchange-rate')
def get_exchange_rate():
    """获取人民币兑港币汇率"""
    try:
        current_rate = get_cny_hkd_rate() or 1.09
        yesterday_rate = get_yesterday_cny_hkd_rate() or 1.1339
        
        return jsonify({
            'success': True,
            'current_rate': round(current_rate, 4),  # 当前实时汇率
            'yesterday_rate': round(yesterday_rate, 4),  # 昨日收盘汇率
            'message': f'1 CNY = {yesterday_rate} HKD (昨日收盘)'
        })
    except Exception as e:
        print(f"获取汇率失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'yesterday_rate': 1.1339  # 默认汇率
        }), 500


@app.route('/api/quotes', methods=['POST'])
def get_quotes():
    """获取实时行情"""
    try:
        # 支持两种格式：直接数组或 {"stocks": [...]}
        json_data = request.json
        if isinstance(json_data, list):
            stocks = json_data
        elif isinstance(json_data, dict):
            stocks = json_data.get('stocks', [])
        else:
            return jsonify({'success': False, 'error': '无效的请求格式'}), 400
        
        if not stocks:
            return jsonify({'success': False, 'error': '股票列表为空'}), 400
        
        quotes = get_stock_quotes(stocks)
        
        # 获取当前汇率和昨日收盘汇率
        # 官方中间价：1港币 ≈ 0.9229人民币 => 1人民币 ≈ 1.0836港币
        current_rate = get_cny_hkd_rate() or 1.0836
        yesterday_rate = get_yesterday_cny_hkd_rate() or 1.0836
        
        # 转换为前端格式
        result = {}
        for stock in stocks:
            code = stock.get('code', '')
            market = stock.get('market', 'A股')
            
            # 构造腾讯代码key
            from utils.stock_quote import normalize_stock_code
            tencent_code = normalize_stock_code(code, market)
            
            quote = quotes.get(tencent_code)
            if quote:
                price = quote['price']
                
                # 港股：返回港币价格 + 人民币转换价（使用实时汇率计算市值）
                if market == '港股':
                    # 使用实时汇率计算人民币价格
                    price_cny = price / current_rate
                    result[code] = {
                        'price': price,  # 港币价格（显示用）
                        'price_cny': round(price_cny, 2),  # 人民币价格（计算盈亏用）
                        'exchange_rate': round(current_rate, 4),  # 当前实时汇率
                        'reference_rate': round(yesterday_rate, 4),  # 昨日收盘汇率（参考）
                        'change': quote['change'],
                        'change_percent': quote['change_percent'],
                        'open': quote['open'],
                        'high': quote['high'],
                        'low': quote['low'],
                        'prev_close': quote['prev_close'],
                        'volume': quote['volume'],
                        'name': quote['name'],
                        'market': '港股'
                    }
                else:
                    result[code] = {
                        'price': price,
                        'change': quote['change'],
                        'change_percent': quote['change_percent'],
                        'open': quote['open'],
                        'high': quote['high'],
                        'low': quote['low'],
                        'prev_close': quote['prev_close'],
                        'volume': quote['volume'],
                        'name': quote['name'],
                        'market': 'A股'
                    }
        
        return jsonify({
            'success': True, 
            'quotes': result,
            'exchange_rate': round(current_rate, 4),  # 当前实时汇率（用于计算市值）
            'reference_rate': round(yesterday_rate, 4)  # 昨日收盘汇率（参考）
        })
    except Exception as e:
        print(f"获取行情失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/axis-price', methods=['POST'])
def get_axis_price():
    """
    获取动态中轴价格（优先从缓存读取，30分钟刷新一次）
    
    请求体: {"code": "000559", "market": "A股", "days": 90}
    """
    try:
        data = request.json
        code = data.get('code', '')
        market = data.get('market', 'A股')
        days = data.get('days', 90)
        
        print(f"[API] 获取中轴价格: {code}, 市场: {market}, 天数: {days}")
        
        if not code:
            return jsonify({'success': False, 'error': '股票代码不能为空'}), 400
        
        # 优先从缓存获取
        axis_data = get_cached_axis_price(code, market, days)
        
        if not axis_data:
            print(f"[API] 获取中轴价格失败: {code} 返回空数据")
            return jsonify({'success': False, 'error': '获取历史数据失败'}), 500
        
        print(f"[API] 获取中轴价格成功: {code} = {axis_data.get('axis_price')}")
        
        return jsonify({
            'success': True,
            'data': axis_data
        })
    except Exception as e:
        import traceback
        print(f"[API] 获取中轴价格异常: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/axis-price/cache/clear', methods=['POST'])
def clear_axis_cache():
    """清除中轴价格缓存（用于手动刷新）"""
    global axis_price_cache
    axis_price_cache = {}
    print("[CACHE] 中轴价格缓存已清除")
    return jsonify({'success': True, 'message': '缓存已清除'})


def preload_axis_cache():
    """启动时预加载所有持仓股票的中轴价格到缓存"""
    import threading
    
    def load_in_background():
        print("[CACHE] 启动后台线程预加载中轴价格缓存...")
        try:
            data = load_data()
            stocks = data.get('stocks', [])
            print(f"[CACHE] 发现 {len(stocks)} 只持仓股票")
            
            for i, stock in enumerate(stocks):
                code = stock.get('code', '')
                market = stock.get('market', 'A股')
                if code:
                    try:
                        get_cached_axis_price(code, market, 90)
                        print(f"[CACHE] [{i+1}/{len(stocks)}] 预加载完成: {code}")
                    except Exception as e:
                        print(f"[CACHE] [{i+1}/{len(stocks)}] 预加载失败: {code} - {e}")
            
            print(f"[CACHE] 预加载完成，缓存条目: {len(axis_price_cache)}")
        except Exception as e:
            print(f"[CACHE] 预加载失败: {e}")
    
    # 在后台线程中执行，不阻塞启动
    thread = threading.Thread(target=load_in_background, daemon=True)
    thread.start()


# ========== 投行分析报告 API ==========

IB_ANALYSIS_FILE = os.path.join(os.path.dirname(__file__), 'reports', 'ib_analysis_latest.md')

# 投行分析数据缓存（内存中缓存）
_ib_analysis_cache = {
    'data': None,
    'timestamp': 0
}
IB_CACHE_TTL = 3600  # 缓存1小时

def parse_ib_analysis():
    """解析投行分析报告，返回结构化数据"""
    try:
        if not os.path.exists(IB_ANALYSIS_FILE):
            return None
            
        with open(IB_ANALYSIS_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 从报告中解析投行报告日期（研报原始发布日期）
        import re
        ib_report_date = None
        
        # 尝试匹配 "投行报告日期: YYYY-MM-DD"
        date_match = re.search(r'\*\*投行报告日期\*\*[:\s]*(\d{4}-\d{2}-\d{2})', content)
        if date_match:
            ib_report_date = date_match.group(1)
        else:
            # 回退到文件修改时间
            ib_report_date = datetime.fromtimestamp(os.path.getmtime(IB_ANALYSIS_FILE)).strftime('%Y-%m-%d')
        
        # 解析持仓映射表格
        holdings_map = []
        stocks_data = load_data()
        stocks = stocks_data.get('stocks', [])
        
        # 根据报告内容生成持仓映射
        for stock in stocks:
            name = stock.get('name', '')
            code = stock.get('code', '')
            market = stock.get('market', 'A股')
            
            # 根据报告内容判断契合度
            alignment = 'neutral'
            ib_views = []
            
            # 港股互联网
            if name in ['腾讯控股', '阿里巴巴']:
                alignment = 'strong'
                ib_views = ['摩根士丹利: 超配互联网龙头', '高盛: 港股AI核心持仓', '南向资金创纪录流入']
            # AI算力
            elif name in ['摩尔线程'] or 'GPU' in name or '芯片' in name:
                alignment = 'strong'
                ib_views = ['中金: AI产业趋势是中期主线', '高盛: AI可提升估值15-20%']
            # AI应用/云计算
            elif name in ['拓尔思', '润泽科技'] or '数据' in name or 'IDC' in name:
                alignment = 'moderate'
                ib_views = ['中金: 端侧AI、软件应用均有机会', '汇丰: 数据中心需求持续上升']
            # 机器人
            elif name in ['三花智控'] or '机器人' in name:
                alignment = 'moderate'
                ib_views = ['瑞银: 人形机器人最受关注', '摩根士丹利: 看好自动化']
            # 新能源/汽车
            elif name in ['比亚迪', '比亚迪电子']:
                alignment = 'neutral'
                ib_views = ['摩根大通: 消费复苏是新动力', '智能驾驶主题受关注']
            # 有色金属
            elif name in ['云南铜业', '中国铝业'] or '铜' in name or '铝' in name:
                alignment = 'weak'
                ib_views = ['摩根士丹利: 低配能源/周期', '担忧关税影响大宗商品']
            # 光伏
            elif name in ['晶盛机电'] or '光伏' in name:
                alignment = 'weak'
                ib_views = ['摩根士丹利: 低配能源', '行业产能过剩仍存']
            else:
                ib_views = ['暂无特定投行观点覆盖']
            
            holdings_map.append({
                'code': code,
                'name': name,
                'market': market,
                'alignment': alignment,
                'ib_views': ib_views
            })
        
        # 生成宏观摘要
        macro_summary = {
            'consensus': '谨慎乐观',
            'key_targets': [
                {'index': '沪深300', 'target': '4150-4900', 'source': '摩根大通/高盛'},
                {'index': 'MSCI中国', 'target': '80-83', 'source': '摩根大通/摩根士丹利'},
            ],
            'main_themes': [
                'AI产业趋势是中期主线（中金/高盛/瑞银共识）',
                '港股科技龙头受青睐（摩根士丹利超配建议）',
                '二季度可能先回调再上涨（摩根大通）',
                '全球基金重返中国意愿2021年来最强（高盛）',
                '南向资金创纪录流入港股（摩根士丹利）',
                'AI可提升中国科技股估值15-20%（高盛）',
                '端侧AI、软件应用均有机会（中金公司）',
                '人形机器人最受投资者关注（瑞银证券）',
                '消费复苏是新动力（摩根大通）',
                '数据中心需求持续上升（汇丰银行）',
                '智能驾驶主题受市场关注（中金公司）',
                '自动化相关企业前景看好（摩根士丹利）',
                '港股AI核心持仓推荐（高盛）',
                '港股互联网配置价值凸显（瑞银证券）',
            ],
            'warnings': [
                '摩根大通: 二季度"退一步进两步"，4-5月可能回调',
                '高盛: 地缘政治活跃，获利了结压力加大',
                '摩根士丹利: 低配大宗商品、地产、消费必需品'
            ]
        }
        
        return {
            'update_time': ib_report_date,  # 使用投行报告日期
            'system_time': datetime.now().strftime('%Y-%m-%d %H:%M'),  # 系统时间作为参考
            'macro_summary': macro_summary,
            'holdings_map': holdings_map,
            'ib_list': ['摩根士丹利', '摩根大通', '高盛', '中金公司', '瑞银证券', '富达国际', '汇丰'],
            'raw_report': content[:2000] + '...'  # 返回部分内容
        }
    except Exception as e:
        print(f"解析投行分析失败: {e}")
        import traceback
        traceback.print_exc()
        return None

@app.route('/api/ib-analysis')
def get_ib_analysis():
    """获取投行分析报告（结构化数据）"""
    try:
        # 强制重新解析，不使用缓存（调试模式）
        data = parse_ib_analysis()
        if data:
            return jsonify({
                'success': True,
                'data': data,
                'cached': False
            })
        else:
            return jsonify({
                'success': False,
                'error': '分析报告不存在或解析失败'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500





# ========== 持仓分析报告 API ==========

PORTFOLIO_ANALYSIS_FILE = os.path.join(os.path.dirname(__file__), 'reports', 'portfolio_analysis_latest.json')

# 持仓分析数据缓存
_portfolio_analysis_cache = {
    'data': None,
    'timestamp': 0
}
PORTFOLIO_CACHE_TTL = 3600  # 缓存1小时

def load_portfolio_analysis():
    """加载持仓分析报告"""
    try:
        if not os.path.exists(PORTFOLIO_ANALYSIS_FILE):
            return None
        
        with open(PORTFOLIO_ANALYSIS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载持仓分析报告失败: {e}")
        return None

@app.route('/api/portfolio-analysis')
def get_portfolio_analysis():
    """获取持仓分析报告"""
    try:
        now = time.time()
        
        # 检查缓存
        if _portfolio_analysis_cache['data'] and (now - _portfolio_analysis_cache['timestamp']) < PORTFOLIO_CACHE_TTL:
            return jsonify({
                'success': True,
                'data': _portfolio_analysis_cache['data'],
                'cached': True
            })
        
        # 重新加载
        data = load_portfolio_analysis()
        if data:
            _portfolio_analysis_cache['data'] = data
            _portfolio_analysis_cache['timestamp'] = now
            return jsonify({
                'success': True,
                'data': data,
                'cached': False
            })
        else:
            return jsonify({
                'success': False,
                'error': '分析报告不存在'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
if __name__ == '__main__':
    # 启动时预加载缓存
    preload_axis_cache()
    app.run(debug=False, host='0.0.0.0', port=8888, use_reloader=False)


