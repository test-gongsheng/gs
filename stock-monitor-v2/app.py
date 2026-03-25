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
    try:
        data = load_data()
        new_stock = request.json
        
        print(f"[add_stock] 添加股票: {new_stock.get('code')} {new_stock.get('name')}")
        
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
        data = load_data()
        stocks = data.get('stocks', [])
        
        # 简单的板块映射（基于股票代码或名称）
        portfolio_sectors = set()
        for stock in stocks:
            name = stock.get('name', '')
            code = stock.get('code', '')
            # 根据股票名称判断板块（简化版）
            if any(k in name for k in ['芯', '半', '微', '电']):
                portfolio_sectors.add('半导体')
            if any(k in name for k in ['药', '医', '生物']):
                portfolio_sectors.add('医药')
            if any(k in name for k in ['金', '矿']):
                portfolio_sectors.add('黄金')
            if any(k in name for k in ['券', '银', '保']):
                portfolio_sectors.add('券商')
            if any(k in name for k in ['锂', '光', '风', '新能']):
                portfolio_sectors.add('新能源')
        
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
        current_rate = get_cny_hkd_rate() or 1.09
        yesterday_rate = get_yesterday_cny_hkd_rate() or 1.1339
        
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
                
                # 港股：返回港币价格 + 人民币转换价
                if market == '港股':
                    # 使用昨日收盘汇率计算人民币价格（与交易软件保持一致）
                    price_cny = price / yesterday_rate
                    result[code] = {
                        'price': price,  # 港币价格（显示用）
                        'price_cny': round(price_cny, 2),  # 人民币价格（计算盈亏用）
                        'exchange_rate': round(yesterday_rate, 4),  # 昨日收盘汇率
                        'current_exchange_rate': round(current_rate, 4),  # 当前实时汇率
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
            'exchange_rate': round(yesterday_rate, 4),  # 昨日收盘汇率（用于计算市值）
            'current_exchange_rate': round(current_rate, 4)  # 当前汇率
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


if __name__ == '__main__':
    # 启动时预加载缓存
    preload_axis_cache()
    app.run(debug=False, host='0.0.0.0', port=8888, use_reloader=False)
