from flask import Flask, render_template, jsonify, request, make_response
import json
import os
import time
import threading
from datetime import datetime, timedelta
from utils.stock_quote import get_stock_quotes, get_dynamic_axis_price
from utils.exchange_rate import get_cny_hkd_rate, get_yesterday_cny_hkd_rate, convert_hkd_to_cny
from utils.sector_data import get_hot_sectors_data
from utils.news_data import get_cls_structured_news
from utils.market_sentiment import get_market_sentiment
from utils.southbound_capital import get_southbound_overall_history, get_southbound_signal, get_southbound_stock_history

app = Flask(__name__)

# 数据文件锁，防止并发读写导致数据丢失
data_file_lock = threading.Lock()

# 彻底禁用静态文件缓存
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['STATIC_FOLDER'] = 'static'

# 添加自定义模板过滤器：自动为静态文件添加版本号（基于文件修改时间）
@app.template_filter('autoversion')
def autoversion_filter(url):
    """为静态文件 URL 添加基于修改时间的版本号，彻底避免缓存问题
    
    用法: {{ url_for('static', filename='js/app.js') | autoversion }}
    输出: /static/js/app.js?v=1774924800
    """
    # 从 URL 中提取文件路径
    if '/static/' in url:
        # 提取 /static/ 后面的部分
        filepath = url.split('/static/', 1)[1]
        full_path = os.path.join(app.static_folder, filepath)
        if os.path.exists(full_path):
            mtime = int(os.path.getmtime(full_path))
            return f"{url}?v={mtime}"
    return url

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'stocks.json')

# 为所有静态文件响应添加禁用缓存头部
@app.after_request
def add_header(response):
    """为所有响应添加禁用缓存头部"""
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# 中轴价格缓存: { 'code:market': {'data': {...}, 'timestamp': ...} }
axis_price_cache = {}
CACHE_TTL = 1800  # 缓存30分钟

# 南向资金预加载标志
_southbound_preload_started = False

def start_southbound_preload():
    """启动后台线程预加载南向资金数据"""
    global _southbound_preload_started
    if _southbound_preload_started:
        return
    _southbound_preload_started = True
    
    import threading
    def _preload():
        import time
        time.sleep(5)  # 等待Flask完全启动
        print("\n" + "="*50)
        print("[Preload] 开始后台预加载南向资金数据...")
        print("="*50)
        hk_stocks = ['00285', '00700', '09988']
        for code in hk_stocks:
            try:
                print(f"[Preload] 正在加载 {code}...")
                result = get_southbound_stock_history(code, days=120)
                print(f"[Preload] [OK] {code} 预加载完成，{len(result)}条数据")
            except Exception as e:
                print(f"[Preload] [FAIL] {code} 预加载失败: {e}")
                import traceback
                traceback.print_exc()
        print("="*50)
        print("[Preload] 南向资金预加载完成，现在访问港股将秒出数据")
        print("="*50 + "\n")
    
    thread = threading.Thread(target=_preload, daemon=True)
    thread.start()
    print("[Preload] 南向资金预加载线程已启动，5秒后开始...")

# 启动时自动开始预加载
start_southbound_preload()


def calculate_stock_type(code, market):
    """
    计算股票类型（高波动/普通）
    基于90天历史数据的波动率评分
    
    Returns:
        dict: {
            'stockType': 'high_vol' | 'normal',
            'volScore': float,
            'annualVol': float,
            'atrPct': float,
            'calculated': bool  # 是否成功计算（True=真的算出来的，False=失败用的默认值）
        }
    """
    try:
        from utils.stock_quote import get_stock_kline
        
        print(f"[calculate_stock_type] 开始计算 {code} ({market})...")
        
        # 获取90天历史数据（使用腾讯K线作为备选）
        hist = get_stock_kline(code, market, days=90, max_retries=2)
        
        if len(hist) < 30:  # 降低要求，至少30天数据就能算
            print(f"[calculate_stock_type] {code} 数据不足: {len(hist)}天")
            return {'stockType': 'normal', 'volScore': 30, 'annualVol': 0.3, 'atrPct': 2.5, 'calculated': False}
        
        # 计算收盘价序列
        closes = [h['close'] for h in hist[-60:] if h['close'] > 0]  # 使用后60天有效数据
        
        if len(closes) < 20:
            print(f"[calculate_stock_type] {code} 有效收盘价不足: {len(closes)}")
            return {'stockType': 'normal', 'volScore': 30, 'annualVol': 0.3, 'atrPct': 2.5, 'calculated': False}
        
        # 计算日收益率
        returns = []
        for i in range(1, len(closes)):
            if closes[i-1] > 0:
                returns.append((closes[i] - closes[i-1]) / closes[i-1])
        
        if len(returns) < 10:
            print(f"[calculate_stock_type] {code} 收益率数据不足: {len(returns)}")
            return {'stockType': 'normal', 'volScore': 30, 'annualVol': 0.3, 'atrPct': 2.5, 'calculated': False}
        
        # 计算年化波动率
        import statistics
        daily_vol = statistics.stdev(returns) if len(returns) > 1 else 0
        annual_vol = daily_vol * (252 ** 0.5)
        
        # 计算ATR%
        atr_values = []
        hist_for_atr = hist[-20:] if len(hist) >= 20 else hist
        for i in range(1, len(hist_for_atr)):
            h = hist_for_atr[i]
            h_prev = hist_for_atr[i-1]
            tr = max(
                h['high'] - h['low'],
                abs(h['high'] - h_prev['close']),
                abs(h['low'] - h_prev['close'])
            )
            atr_values.append(tr)
        
        avg_atr = sum(atr_values) / len(atr_values) if atr_values else 0
        current_price = closes[-1] if closes else 1
        atr_pct = (avg_atr / current_price) * 100 if current_price > 0 else 2.5
        
        # 综合波动率评分
        vol_score = min(100, annual_vol * 50 + atr_pct * 10)
        stock_type = 'high_vol' if vol_score > 60 else 'normal'
        
        print(f"[calculate_stock_type] {code} 计算完成: type={stock_type}, score={vol_score:.1f}, vol={annual_vol:.2f}")
        
        return {
            'stockType': stock_type,
            'volScore': round(vol_score, 1),
            'annualVol': round(annual_vol, 2),
            'atrPct': round(atr_pct, 2),
            'calculated': True
        }
        
    except Exception as e:
        print(f"[calculate_stock_type] 计算失败 {code}: {e}")
        return {'stockType': 'normal', 'volScore': 30, 'annualVol': 0.3, 'atrPct': 2.5, 'calculated': False}


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
    """加载股票数据，如果不存在则自动创建（线程安全）"""
    with data_file_lock:
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
    """保存股票数据（线程安全）"""
    with data_file_lock:
        temp_file = None
        try:
            # 先写入临时文件，成功后重命名（原子操作，避免写入中断导致数据损坏）
            temp_file = DATA_FILE + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # 原子重命名
            os.replace(temp_file, DATA_FILE)
            return True
        except Exception as e:
            import traceback
            print(f"Error saving data: {e}")
            traceback.print_exc()
            # 清理临时文件
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            return False

@app.route('/')
def index():
    """主页面"""
    import time
    response = make_response(render_template('index.html', now=int(time.time())))
    # 禁用缓存，确保每次都能加载最新JS
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/portfolio')
def get_portfolio():
    """获取投资组合配置"""
    data = load_data()
    return jsonify(data['portfolio'])

@app.route('/api/stocks')
def get_stocks():
    """获取所有股票，包含股票类型和方案3C买卖点，实时刷新价格"""
    data = load_data()
    stocks = data['stocks']
    
    # 【新增】批量获取实时行情
    try:
        stock_list = [{'code': s.get('code', ''), 'market': s.get('market', 'A股')} for s in stocks]
        realtime_quotes = get_stock_quotes(stock_list)
        
        # 更新每只股票的价格
        for stock in stocks:
            code = stock.get('code', '')
            market = stock.get('market', 'A股')
            
            # 构造匹配的code key
            if market == '港股' or len(code) == 5:
                quote_key = f"hk{code}"
            elif code.startswith(('6', '688')):
                quote_key = f"sh{code}"
            else:
                quote_key = f"sz{code}"
            
            # 更新实时价格
            if quote_key in realtime_quotes:
                quote = realtime_quotes[quote_key]
                if quote and quote.get('price', 0) > 0:
                    old_price = stock.get('current_price', 0)
                    new_price = quote['price']
                    stock['current_price'] = new_price
                    stock['price_update_time'] = datetime.now().isoformat()
                    
                    # 如果有涨跌额/涨跌幅也更新
                    if 'change' in quote:
                        stock['change'] = quote['change']
                    if 'change_percent' in quote:
                        stock['change_percent'] = quote['change_percent']
                    
                    # 计算市值
                    shares = stock.get('shares', 0)
                    if shares > 0:
                        stock['market_value'] = new_price * shares
                    
                    # 打印更新日志（只打印价格变化超过1%的）
                    if old_price > 0 and abs(new_price - old_price) / old_price > 0.01:
                        print(f"[get_stocks] {code} 价格更新: ¥{old_price:.2f} → ¥{new_price:.2f}")
    except Exception as e:
        print(f"[get_stocks] 实时行情刷新失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 为每只股票添加类型和执行数据
    for stock in stocks:
        # 如果还没有计算过股票类型，或者需要重新计算（之前失败了）
        need_calc = 'stock_type' not in stock or stock.get('stock_type_calculated') == False
        
        if need_calc:
            type_info = calculate_stock_type(stock.get('code'), stock.get('market', 'A股'))
            
            # 只有成功计算才保存到文件
            if type_info.get('calculated', False):
                stock['stock_type'] = type_info['stockType']
                stock['vol_score'] = type_info['volScore']
                stock['annual_vol'] = type_info['annualVol']
                stock['atr_pct'] = type_info['atrPct']
                stock['stock_type_calculated'] = True
                stock['stock_type_calc_time'] = datetime.now().isoformat()
                print(f"[get_stocks] {stock.get('code')} 股票类型计算成功: {type_info['stockType']}")
            else:
                # 计算失败，使用临时值但不保存
                stock['stock_type'] = 'normal'  # 临时显示普通
                stock['vol_score'] = type_info['volScore']
                stock['stock_type_calculated'] = False  # 标记为未计算成功
                print(f"[get_stocks] {stock.get('code')} 股票类型计算失败，下次重试")
        
        # 添加执行策略数据（如果没有）
        if 'last_trade_time' not in stock:
            stock['last_trade_time'] = None
        if 'last_trade_type' not in stock:
            stock['last_trade_type'] = None
        if 'cooldown_days' not in stock:
            # 根据股票类型设置默认冷却期
            stock['cooldown_days'] = 15 if stock.get('stock_type') == 'high_vol' else 20
        
        # 【新增】使用方案3C计算买点和卖点
        buy_info = calculate_3c_buy_points(stock)
        sell_info = calculate_3c_sell_point(stock)
        
        stock['next_buy_price'] = buy_info['buy_price'] if buy_info['can_buy'] else 0
        stock['next_sell_price'] = sell_info['sell_price']
        stock['can_buy'] = buy_info['can_buy']
        stock['buy_type'] = buy_info['buy_type']
        stock['cooldown_remaining'] = buy_info['cooldown_remaining']
        stock['strategy_reason'] = buy_info['reason']
    
    # 【修复】只在确实需要保存时才保存（避免竞态条件覆盖导入数据）
    # 检查是否有新计算的股票类型需要持久化
    need_save = False
    for stock in stocks:
        # 如果股票类型刚计算成功且需要保存，则标记需要保存
        if stock.get('stock_type_calculated') and 'stock_type_calc_time' in stock:
            # 检查是否是本次会话新计算的（通过时间戳判断）
            calc_time = stock.get('stock_type_calc_time', '')
            if calc_time and datetime.now().isoformat()[:10] == calc_time[:10]:
                need_save = True
                break
    
    if need_save:
        # 重新加载最新数据，合并后再保存（避免覆盖其他并发修改）
        fresh_data = load_data()
        fresh_codes = {s['id']: s for s in fresh_data['stocks']}
        
        # 1. 更新文件中已存在的股票
        for stock in stocks:
            if stock['id'] in fresh_codes:
                fresh_codes[stock['id']].update({
                    'stock_type': stock.get('stock_type'),
                    'vol_score': stock.get('vol_score'),
                    'annual_vol': stock.get('annual_vol'),
                    'atr_pct': stock.get('atr_pct'),
                    'stock_type_calculated': stock.get('stock_type_calculated'),
                    'stock_type_calc_time': stock.get('stock_type_calc_time')
                })
        
        # 2. 【修复】添加内存中有但文件中没有的股票（新导入的）
        current_ids = {s['id'] for s in stocks}
        fresh_ids = {s['id'] for s in fresh_data['stocks']}
        new_ids = current_ids - fresh_ids
        
        for stock in stocks:
            if stock['id'] in new_ids:
                fresh_data['stocks'].append(stock)
                print(f"[get_stocks] 添加新股票到文件: {stock.get('code')} {stock.get('name')}")
        
        save_data(fresh_data)
        print(f"[get_stocks] 已保存 {len([s for s in stocks if s.get('stock_type_calculated')])} 只股票类型，新增 {len(new_ids)} 只")
    
    return jsonify(stocks)

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
    """批量添加股票（避免并发冲突），支持自动记录交易"""
    import time
    import random
    
    try:
        data = load_data()
        request_data = request.json
        stocks_to_add = request_data.get('stocks', [])
        trades = request_data.get('trades', [])  # 【新增】获取交易记录
        
        if not stocks_to_add:
            return jsonify({'success': False, 'error': '股票列表为空'}), 400
        
        print(f"[batch_add_stocks] 批量添加 {len(stocks_to_add)} 只股票")
        print(f"[batch_add_stocks] 接收到的交易记录: {len(trades)} 笔")
        
        # 【新增】处理交易记录，更新股票的 last_trade 信息
        trade_map = {}
        for trade in trades:
            code = trade.get('stock_code')
            if code:
                if code not in trade_map:
                    trade_map[code] = []
                trade_map[code].append(trade)
                
                # 同时保存到全局交易日志
                if 'trade_logs' not in data:
                    data['trade_logs'] = []
                trade_record = {
                    'id': f"{int(time.time())}_{code}_{trade.get('trade_type')}",
                    'time': trade.get('time', datetime.now().isoformat()),
                    'stock_code': code,
                    'stock_name': trade.get('stock_name', ''),
                    'trade_type': trade.get('trade_type'),
                    'price': trade.get('price', 0),
                    'shares': trade.get('shares', 0),
                    'amount': trade.get('price', 0) * trade.get('shares', 0),
                    'note': trade.get('note', '')
                }
                data['trade_logs'].append(trade_record)
        
        added_stocks = []
        for new_stock in stocks_to_add:
            stock_id = f"{int(time.time())}{random.randint(100, 999)}"
            new_stock['id'] = stock_id
            new_stock['status'] = '监控中'
            new_stock['market_value'] = new_stock.get('current_price', 0) * new_stock.get('shares', 0)
            
            # 【新增】如果有该股票的交易记录，更新 last_trade 信息
            code = new_stock.get('code', '')
            if code in trade_map:
                # 找到最新的交易（通常是卖出）
                sell_trades = [t for t in trade_map[code] if t.get('trade_type') == 'sell']
                buy_trades = [t for t in trade_map[code] if t.get('trade_type') == 'buy']
                
                if sell_trades:
                    # 有卖出交易，更新卖出记录（用于计算冷却期）
                    latest_sell = max(sell_trades, key=lambda x: x.get('time', ''))
                    new_stock['last_trade_time'] = latest_sell.get('time')
                    new_stock['last_trade_type'] = 'sell'
                    new_stock['last_trade_price'] = latest_sell.get('price', 0)
                    new_stock['last_trade_shares'] = latest_sell.get('shares', 0)
                    print(f"[batch_add_stocks] {code} 更新卖出记录: {latest_sell.get('time')}")
                elif buy_trades:
                    # 只有买入交易
                    latest_buy = max(buy_trades, key=lambda x: x.get('time', ''))
                    new_stock['last_trade_time'] = latest_buy.get('time')
                    new_stock['last_trade_type'] = 'buy'
                    new_stock['last_trade_price'] = latest_buy.get('price', 0)
                    new_stock['last_trade_shares'] = latest_buy.get('shares', 0)
            
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
            print(f"[batch_add_stocks] 成功添加 {len(added_stocks)} 只股票，记录 {len(trades)} 笔交易")
            
            # 【新增】导入成功后自动生成持仓分析报告
            try:
                import threading
                def generate_report_async():
                    try:
                        print("[batch_add_stocks] 开始异步生成持仓分析报告...")
                        # 调用报告生成脚本
                        import subprocess
                        result = subprocess.run(
                            ['venv/bin/python', 'update_portfolio_analysis.py'],
                            cwd=os.path.dirname(__file__),
                            capture_output=True,
                            text=True,
                            timeout=120
                        )
                        if result.returncode == 0:
                            print("[batch_add_stocks] 持仓分析报告生成成功")
                            # 清除缓存，让新报告立即生效
                            _portfolio_analysis_cache['data'] = None
                            _portfolio_analysis_cache['timestamp'] = 0
                        else:
                            print(f"[batch_add_stocks] 报告生成失败: {result.stderr}")
                    except Exception as e:
                        print(f"[batch_add_stocks] 异步生成报告异常: {e}")
                
                # 启动后台线程生成报告，不阻塞导入响应
                threading.Thread(target=generate_report_async, daemon=True).start()
            except Exception as e:
                print(f"[batch_add_stocks] 启动报告生成线程失败: {e}")
            
            return jsonify({
                'success': True, 
                'stocks': added_stocks, 
                'count': len(added_stocks),
                'trades_recorded': len(trades)
            })
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

# ========== 南向资金 API ==========
from utils.southbound_capital import (
    get_southbound_overall_history,
    get_southbound_stock_history,
    get_southbound_signal,
    update_southbound_data
)

@app.route('/api/southbound/overall')
def get_southbound_overall():
    """获取南向资金整体流向（120个交易日）"""
    try:
        days = request.args.get('days', 120, type=int)
        data = get_southbound_overall_history(days=days)
        signal = get_southbound_signal()
        
        return jsonify({
            'success': True,
            'data': data,
            'signal': signal,
            'count': len(data)
        })
    except Exception as e:
        print(f"获取南向资金整体流向失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/southbound/stock/<stock_code>')
def get_southbound_stock(stock_code):
    """获取指定港股通股票的南向资金流向（120个交易日）"""
    try:
        days = request.args.get('days', 120, type=int)
        print(f"[API] 请求南向资金数据: {stock_code}, days={days}")
        data = get_southbound_stock_history(stock_code, days=days)
        
        # 打印第一条和最后一条数据的股票名称，用于调试
        if data:
            print(f"[API] 返回数据: {stock_code}, count={len(data)}, name={data[0].get('stock_name', 'N/A')}")
        else:
            print(f"[API] 返回数据: {stock_code}, count=0, 无数据")
        
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'data': data,
            'count': len(data)
        })
    except Exception as e:
        print(f"获取个股南向资金数据失败 {stock_code}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/southbound/update', methods=['POST'])
def trigger_southbound_update():
    """手动触发南向资金数据更新"""
    try:
        success = update_southbound_data()
        return jsonify({
            'success': success,
            'message': '更新成功' if success else '更新失败'
        })
    except Exception as e:
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


# ========== 方案3C：智能自适应冷却策略 ==========

def calculate_3c_buy_points(stock):
    """
    根据方案3C计算买入点
    
    规则：
    - 高波动股(high_vol): 卖出后15天冷却期
      - 冷却期内：-12%(深度) 或 -10%(中度) 可买入
      - 冷却期后：按中轴价格正常买入
    - 普通股(normal): 动态冷却期10-30天
      - 冷却期内：不能买入
      - 冷却期后：按中轴价格正常买入
    
    Returns:
        {
            'can_buy': bool,           # 是否可以买入
            'buy_price': float,        # 建议买入价格
            'buy_type': str,           # '深度回调'/'中度回调'/'正常'
            'cooldown_remaining': int, # 冷却期剩余天数
            'reason': str              # 说明
        }
    """
    try:
        code = stock.get('code', '')
        name = stock.get('name', '')
        current_price = stock.get('current_price', 0)
        axis_price = stock.get('axis_price', 0)
        stock_type = stock.get('stock_type', 'normal')
        last_trade_time = stock.get('last_trade_time')
        last_trade_type = stock.get('last_trade_type')
        
        # 如果没有中轴价格，用当前价格
        base_price = axis_price if axis_price > 0 else current_price
        
        now = datetime.now()
        
        # 计算冷却期
        if stock_type == 'high_vol':
            cooldown_days = 15
        else:
            # 普通股：基于波动率评分动态计算
            vol_score = stock.get('vol_score', 30)
            cooldown_days = max(10, min(30, int(30 - vol_score / 2)))
        
        # 如果没有卖出记录，按正常买入逻辑
        if not last_trade_time or last_trade_type != 'sell':
            # 正常买入点：中轴价格附近
            buy_price = base_price * 0.93  # 中轴下方7%作为正常买入点
            return {
                'can_buy': True,
                'buy_price': round(buy_price, 2),
                'buy_type': '正常',
                'cooldown_remaining': 0,
                'reason': '无卖出记录，按正常策略买入'
            }
        
        # 计算上次卖出后的天数
        try:
            last_trade = datetime.fromisoformat(last_trade_time)
            days_since_sell = (now - last_trade).days
        except:
            days_since_sell = 999  # 解析失败，视为已过期
        
        remaining = max(0, cooldown_days - days_since_sell)
        
        # 冷却期内特殊逻辑
        if remaining > 0:
            if stock_type == 'high_vol':
                # 高波动股：深度回调-12% 或 中度回调-10%
                last_sell_price = stock.get('last_trade_price', base_price)
                if last_sell_price <= 0:
                    last_sell_price = base_price
                
                deep_buy = last_sell_price * 0.88  # -12%
                mid_buy = last_sell_price * 0.90    # -10%
                
                # 优先深度回调
                if current_price <= deep_buy:
                    return {
                        'can_buy': True,
                        'buy_price': round(deep_buy, 2),
                        'buy_type': '深度回调(-12%)',
                        'cooldown_remaining': remaining,
                        'reason': f'冷却期内({remaining}天剩余)，触发深度回调买入条件'
                    }
                # 次选中度回调
                elif current_price <= mid_buy:
                    return {
                        'can_buy': True,
                        'buy_price': round(mid_buy, 2),
                        'buy_type': '中度回调(-10%)',
                        'cooldown_remaining': remaining,
                        'reason': f'冷却期内({remaining}天剩余)，触发中度回调买入条件'
                    }
                else:
                    return {
                        'can_buy': False,
                        'buy_price': round(mid_buy, 2),
                        'buy_type': None,
                        'cooldown_remaining': remaining,
                        'reason': f'冷却期内({remaining}天剩余)，需跌-10%或-12%才能买入'
                    }
            else:
                # 普通股：冷却期内不能买入
                return {
                    'can_buy': False,
                    'buy_price': round(base_price * 0.93, 2),
                    'buy_type': None,
                    'cooldown_remaining': remaining,
                    'reason': f'冷却期内({remaining}天剩余)，普通股需等冷却结束'
                }
        
        # 冷却期结束，正常买入
        buy_price = base_price * 0.93
        return {
            'can_buy': True,
            'buy_price': round(buy_price, 2),
            'buy_type': '正常',
            'cooldown_remaining': 0,
            'reason': '冷却期已结束，可按正常策略买入'
        }
        
    except Exception as e:
        print(f"[calculate_3c_buy_points] 计算失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            'can_buy': False,
            'buy_price': 0,
            'buy_type': None,
            'cooldown_remaining': 0,
            'reason': f'计算错误: {str(e)}'
        }


def calculate_3c_sell_point(stock):
    """
    根据方案3C计算卖出点
    
    规则：
    - 高波动股：中轴价格+10%
    - 普通股：中轴价格+7%
    
    Returns:
        {
            'sell_price': float,
            'reason': str
        }
    """
    try:
        axis_price = stock.get('axis_price', 0)
        stock_type = stock.get('stock_type', 'normal')
        current_price = stock.get('current_price', axis_price)
        
        base_price = axis_price if axis_price > 0 else current_price
        
        if stock_type == 'high_vol':
            sell_price = base_price * 1.10  # +10%
            return {
                'sell_price': round(sell_price, 2),
                'reason': '高波动股卖点：中轴上方+10%'
            }
        else:
            sell_price = base_price * 1.07  # +7%
            return {
                'sell_price': round(sell_price, 2),
                'reason': '普通股卖点：中轴上方+7%'
            }
    except Exception as e:
        print(f"[calculate_3c_sell_point] 计算失败: {e}")
        return {
            'sell_price': 0,
            'reason': f'计算错误: {str(e)}'
        }


@app.route('/api/3c/strategy/<stock_code>')
def get_3c_strategy(stock_code):
    """获取指定股票的方案3C策略详情"""
    try:
        data = load_data()
        stock = next((s for s in data.get('stocks', []) if s.get('code') == stock_code), None)
        
        if not stock:
            return jsonify({'success': False, 'error': '股票不存在'}), 404
        
        buy_info = calculate_3c_buy_points(stock)
        sell_info = calculate_3c_sell_point(stock)
        
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'stock_name': stock.get('name'),
            'stock_type': stock.get('stock_type', 'normal'),
            'current_price': stock.get('current_price', 0),
            'axis_price': stock.get('axis_price', 0),
            'last_trade': {
                'time': stock.get('last_trade_time'),
                'type': stock.get('last_trade_type'),
                'price': stock.get('last_trade_price', 0)
            },
            'buy_strategy': buy_info,
            'sell_strategy': sell_info
        })
        
    except Exception as e:
        print(f"[get_3c_strategy] 异常: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/trade/log', methods=['POST'])
def log_trade():
    """记录交易"""
    try:
        data = load_data()
        trade = request.json
        
        # 必填字段检查
        required = ['stock_code', 'trade_type', 'price', 'shares']
        for field in required:
            if field not in trade:
                return jsonify({'success': False, 'error': f'缺少字段: {field}'}), 400
        
        # 记录交易
        trade_record = {
            'id': f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{trade['stock_code']}",
            'time': datetime.now().isoformat(),
            'stock_code': trade['stock_code'],
            'stock_name': trade.get('stock_name', ''),
            'trade_type': trade['trade_type'],  # 'buy' or 'sell'
            'price': trade['price'],
            'shares': trade['shares'],
            'amount': trade['price'] * trade['shares'],
            'note': trade.get('note', '')
        }
        
        # 添加到交易日志
        if 'trade_logs' not in data:
            data['trade_logs'] = []
        data['trade_logs'].append(trade_record)
        
        # 更新股票的 last_trade 信息
        stock = next((s for s in data.get('stocks', []) if s.get('code') == trade['stock_code']), None)
        if stock:
            stock['last_trade_time'] = trade_record['time']
            stock['last_trade_type'] = trade['trade_type']
            stock['last_trade_price'] = trade['price']
            # 更新持仓数量
            if trade['trade_type'] == 'buy':
                stock['shares'] = stock.get('shares', 0) + trade['shares']
            elif trade['trade_type'] == 'sell':
                stock['shares'] = max(0, stock.get('shares', 0) - trade['shares'])
        
        if save_data(data):
            return jsonify({'success': True, 'trade': trade_record})
        return jsonify({'success': False, 'error': '保存失败'}), 500
        
    except Exception as e:
        print(f"[log_trade] 异常: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/trade/logs/<stock_code>')
def get_trade_logs(stock_code):
    """获取指定股票的交易记录"""
    try:
        data = load_data()
        logs = data.get('trade_logs', [])
        stock_logs = [log for log in logs if log.get('stock_code') == stock_code]
        # 按时间倒序
        stock_logs.sort(key=lambda x: x.get('time', ''), reverse=True)
        return jsonify({'success': True, 'logs': stock_logs[:20]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========== 买卖点实时监控 API (方案3C版本) ==========
# 用于前端轮询获取触发的买卖点
_price_alert_cache = {
    'last_check_time': None,
    'triggered_alerts': [],  # 当前触发的警报
    'alert_history': [],     # 历史警报（去重用）
}

@app.route('/api/price-alerts')
def get_price_alerts():
    """
    获取当前触发的买卖点警报 (方案3C版本)
    前端每30秒轮询一次
    
    Returns:
        {
            'alerts': [{'stock_code', 'stock_name', 'type': 'buy'|'sell', 'price', 'trigger_price', 'time'}],
            'has_new': bool  # 是否有新的触发
        }
    """
    try:
        data = load_data()
        stocks = data.get('stocks', [])
        
        now = datetime.now()
        current_time_str = now.strftime('%Y-%m-%d %H:%M:%S')
        
        triggered = []
        new_alerts = []
        
        for stock in stocks:
            code = stock.get('code', '')
            name = stock.get('name', '')
            price = stock.get('current_price', 0)
            
            if price <= 0:
                continue
            
            # 使用方案3C计算买点
            buy_info = calculate_3c_buy_points(stock)
            sell_info = calculate_3c_sell_point(stock)
            
            # 检查买点触发 (can_buy为True且价格触及买入价)
            if buy_info['can_buy'] and buy_info['buy_price'] > 0 and price <= buy_info['buy_price']:
                alert_key = f"{code}:3cbuy:{now.strftime('%Y%m%d')}"
                alert = {
                    'stock_code': code,
                    'stock_name': name,
                    'type': 'buy',
                    'subtype': buy_info['buy_type'],  # 正常/深度回调/中度回调
                    'price': price,
                    'trigger_price': buy_info['buy_price'],
                    'time': current_time_str,
                    'key': alert_key,
                    'diff_pct': round((price - buy_info['buy_price']) / buy_info['buy_price'] * 100, 2),
                    'reason': buy_info['reason']
                }
                triggered.append(alert)
                
                # 检查是否是新触发
                if alert_key not in [a.get('key') for a in _price_alert_cache['alert_history']]:
                    new_alerts.append(alert)
                    _price_alert_cache['alert_history'].append(alert)
            
            # 检查卖点触发
            sell_price = sell_info['sell_price']
            if sell_price > 0 and price >= sell_price:
                alert_key = f"{code}:3csell:{now.strftime('%Y%m%d')}"
                alert = {
                    'stock_code': code,
                    'stock_name': name,
                    'type': 'sell',
                    'subtype': '方案3C卖点',
                    'price': price,
                    'trigger_price': sell_price,
                    'time': current_time_str,
                    'key': alert_key,
                    'diff_pct': round((price - sell_price) / sell_price * 100, 2),
                    'reason': sell_info['reason']
                }
                triggered.append(alert)
                
                if alert_key not in [a.get('key') for a in _price_alert_cache['alert_history']]:
                    new_alerts.append(alert)
                    _price_alert_cache['alert_history'].append(alert)
        
        # 清理历史（保留最近3天的）
        cutoff_date = (now - timedelta(days=3)).strftime('%Y%m%d')
        _price_alert_cache['alert_history'] = [
            a for a in _price_alert_cache['alert_history'] 
            if not a.get('key', '').endswith(f':{cutoff_date}')
        ]
        
        _price_alert_cache['last_check_time'] = current_time_str
        _price_alert_cache['triggered_alerts'] = triggered
        
        return jsonify({
            'success': True,
            'alerts': triggered,
            'new_alerts': new_alerts,
            'has_new': len(new_alerts) > 0,
            'check_time': current_time_str
        })
        
    except Exception as e:
        print(f"[price-alerts] 获取警报失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

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
    # 启动时预加载中轴价格缓存
    preload_axis_cache()
    
    # 启动南向资金预加载定时任务
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))
        from southbound_scheduler import init_preload_scheduler
        init_preload_scheduler()
    except Exception as e:
        print(f"[Startup] 南向资金预加载调度器启动失败: {e}")
    
    app.run(debug=False, host='0.0.0.0', port=8888, use_reloader=False)


