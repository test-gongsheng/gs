# -*- coding: utf-8 -*-
from flask import Flask, render_template, jsonify, request, make_response, g
import json
import os
import sys
import time
import threading
from datetime import datetime, timedelta
from utils.stock_quote import get_stock_quotes, get_dynamic_axis_price
from utils.exchange_rate import get_cny_hkd_rate, get_yesterday_cny_hkd_rate, convert_hkd_to_cny
from utils.sector_data import get_hot_sectors_data
from utils.news_data import get_cls_structured_news
# 注意：不再 import get_market_sentiment（旧版同步慢扫描，已由 emotion_engine 缓存版替代）
from utils.southbound_capital import get_southbound_overall_history, get_southbound_signal, get_southbound_stock_history

app = Flask(__name__)

# ========== 公网访问口令 ==========
# 防全网扫描器暴露持仓数据。data/access_token.txt 存在即启用（文件不入git）。
# 127.0.0.1/::1 豁免（服务器本机cron与SSH隧道不受影响）；
# 外部首次访问需带 ?token=xxx，校验通过种180天cookie，之后直接访问。
def _load_access_token():
    try:
        p = os.path.join(os.path.dirname(__file__), 'data', 'access_token.txt')
        t = open(p, encoding='utf-8').read().strip()
        return t or None
    except Exception:
        return None

ACCESS_TOKEN = _load_access_token()

@app.before_request
def _access_gate():
    if not ACCESS_TOKEN:
        return None
    ip = request.remote_addr or ''
    if ip.startswith('127.') or ip in ('::1', 'localhost'):
        return None
    if request.cookies.get('smv2_token') == ACCESS_TOKEN:
        return None
    if request.args.get('token') == ACCESS_TOKEN:
        g._grant_token_cookie = True
        return None
    return jsonify({'error': '未授权访问：请使用带口令的完整链接打开'}), 403

@app.after_request
def _grant_token_cookie(response):
    if getattr(g, '_grant_token_cookie', False):
        response.set_cookie('smv2_token', ACCESS_TOKEN, max_age=180 * 24 * 3600, httponly=True, samesite='Lax')
    return response

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
        
        # 【关键性能修复】中轴价格只在缓存命中时用，未命中不阻塞等待重算
        # （后台预加载线程会慢慢填缓存，下个请求周期就能用上）
        # 之前这里同步重算14只×akshare，页面请求几分钟不返回，拖死浏览器全部连接
        for stock in stocks:
            code = stock.get('code', '')
            market = stock.get('market', 'A股')
            cache_key = f"{code}:{market}"
            cached = axis_price_cache.get(cache_key)
            if cached and (time.time() - cached['timestamp']) < CACHE_TTL and cached['data'].get('axis_price', 0) > 0:
                stock['axis_price'] = cached['data']['axis_price']
            else:
                # 缓存未命中：先用当前价格占位，后台预加载填缓存后下个周期自动更新
                stock['axis_price'] = stock.get('current_price', 0)
        
    except Exception as e:
        print(f"[get_stocks] 实时行情刷新失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 为每只股票添加类型和执行数据
    # 【性能修复】股票类型不在请求线程同步算（每次akshare拉124根K线，14只串行要几分钟）
    # 已有值直接用；缺失时用默认值展示，后台线程补算后写回stocks.json
    _need_type_calc = []
    for stock in stocks:
        need_calc = 'stock_type' not in stock or stock.get('stock_type_calculated') == False
        
        if need_calc:
            # 请求线程不做重计算，先给默认值，后台补
            if 'stock_type' not in stock:
                stock['stock_type'] = 'normal'
                stock['vol_score'] = 50
            _need_type_calc.append(stock.get('code'))
        
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
    
    # 有缺失的股票类型，先快速返回响应，后台线程慢慢补算并写回文件
    if _need_type_calc:
        _codes = list(_need_type_calc)
        def _bg_calc_types():
            try:
                _d = load_data()
                changed = False
                for st in _d.get('stocks', []):
                    if st.get('code') not in _codes:
                        continue
                    if st.get('stock_type_calculated'):
                        continue  # 已被其他线程算好
                    ti = calculate_stock_type(st.get('code'), st.get('market', 'A股'))
                    if ti.get('calculated', False):
                        st['stock_type'] = ti['stockType']
                        st['vol_score'] = ti['volScore']
                        st['annual_vol'] = ti['annualVol']
                        st['atr_pct'] = ti['atrPct']
                        st['stock_type_calculated'] = True
                        st['stock_type_calc_time'] = datetime.now().isoformat()
                        changed = True
                        print(f"[BG-CalcType] {st.get('code')} 补算完成: {ti['stockType']}")
                if changed:
                    save_data(_d)
                    print(f'[BG-CalcType] 已保存 {_codes} 的股票类型')
            except Exception as e:
                print(f'[BG-CalcType] 后台补算失败: {e}')
        threading.Thread(target=_bg_calc_types, daemon=True).start()
    
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
            
            # 【修复】强制清空 last_trade 字段，只从真实交易记录设置
            # 防止前端传来的误解析值影响报告
            new_stock['last_trade_price'] = 0
            new_stock['last_trade_type'] = ''
            new_stock['last_trade_time'] = ''
            new_stock['last_trade_shares'] = 0
            
            # 【修复】不再根据交易记录重新计算持仓数量
            # 原因：detectTrades 生成的交易记录不完整（只包含变化量），
            # 重新计算会导致持仓数量错误。持仓数量应以前端传入的为准。
            code = new_stock.get('code', '')
            if code in trade_map:
                trades_for_stock = trade_map[code]
                
                # 只更新 last_trade 信息（使用最新真实交易）
                real_trades = [t for t in trades_for_stock if t.get('note') not in ['初始持仓导入', '导入时检测：加仓', '导入时检测：减仓卖出']]
                buy_trades = [t for t in real_trades if t.get('trade_type') == 'buy']
                sell_trades = [t for t in real_trades if t.get('trade_type') == 'sell']
                
                if sell_trades:
                    latest_sell = max(sell_trades, key=lambda x: x.get('time', ''))
                    new_stock['last_trade_time'] = latest_sell.get('time')
                    new_stock['last_trade_type'] = 'sell'
                    new_stock['last_trade_price'] = latest_sell.get('price', 0)
                    new_stock['last_trade_shares'] = latest_sell.get('shares', 0)
                elif buy_trades:
                    latest_buy = max(buy_trades, key=lambda x: x.get('time', ''))
                    new_stock['last_trade_time'] = latest_buy.get('time')
                    new_stock['last_trade_type'] = 'buy'
                    new_stock['last_trade_price'] = latest_buy.get('price', 0)
                    new_stock['last_trade_shares'] = latest_buy.get('shares', 0)
                # 如果没有真实交易记录，不设置 last_trade（保持为空）
            
            # 港股添加汇率字段（使用实时汇率）
            if new_stock.get('market') == '港股':
                from utils.exchange_rate import get_cny_hkd_rate
                new_stock['exchange_rate'] = get_cny_hkd_rate() or 1.0836
            
            data['stocks'].append(new_stock)
            added_stocks.append(new_stock)
            print(f"[batch_add_stocks] 添加: {new_stock.get('code')} -> ID {stock_id}")
        
        # 更新风险控制
        update_risk_control(data)
        
        # 【修复】从 trade_logs 恢复 last_trade 信息（避免导入持仓时清空交易记录）
        trade_logs = data.get('trade_logs', [])
        if trade_logs:
            # 按股票分组，找每只股票最新的真实交易
            from collections import defaultdict
            code_trades = defaultdict(list)
            for log in trade_logs:
                code = log.get('stock_code')
                if code and log.get('trade_type') in ['buy', 'sell']:
                    code_trades[code].append(log)
            
            for stock in added_stocks:
                code = stock.get('code')
                if code in code_trades:
                    # 按时间排序，取最新一笔
                    latest = max(code_trades[code], key=lambda x: x.get('time', ''))
                    stock['last_trade_price'] = latest.get('price', 0)
                    stock['last_trade_type'] = latest.get('trade_type', '')
                    stock['last_trade_time'] = latest.get('time', '')
                    stock['last_trade_shares'] = latest.get('shares', 0)
                    print(f"[batch_add_stocks] 从 trade_logs 恢复 {code} 交易记录: {latest.get('trade_type')} @ {latest.get('price')}")
        
        if save_data(data):
            print(f"[batch_add_stocks] 成功添加 {len(added_stocks)} 只股票，记录 {len(trades)} 笔交易")
            
            # 【修复】强制刷新数据，确保导入的数据已持久化
            import time
            time.sleep(0.1)  # 给文件系统一点时间
            verify_data = load_data()
            verify_codes = [s.get('code') for s in verify_data.get('stocks', [])]
            added_codes = [s.get('code') for s in added_stocks]
            missing = [c for c in added_codes if c not in verify_codes]
            if missing:
                print(f"[batch_add_stocks] [WARN] 验证发现缺失股票: {missing}")
            else:
                print(f"[batch_add_stocks] [OK] 数据验证通过，所有股票已持久化")
            
            # 【新增】导入成功后同步生成持仓分析报告（确保立即可用）
            report_result = None
            try:
                print("[batch_add_stocks] 开始生成持仓分析报告...")
                import subprocess
                
                # 【修复】先等待中轴价格计算完成，确保数据就绪
                print("[batch_add_stocks] 等待中轴价格计算...")
                time.sleep(2)
                
                result = subprocess.run(
                    [sys.executable, 'deep_analysis.py'],
                    cwd=os.path.dirname(__file__),
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                if result.returncode == 0:
                    print("[batch_add_stocks] 深度分析报告生成成功")
                    report_result = 'success'
                else:
                    error_msg = result.stderr[:200] if result.stderr else '未知错误'
                    print(f"[batch_add_stocks] 报告生成失败: {error_msg}")
                    report_result = f'failed: {error_msg}'
            except subprocess.TimeoutExpired:
                print("[batch_add_stocks] 报告生成超时，请稍后手动执行")
                report_result = 'timeout'
            except Exception as e:
                print(f"[batch_add_stocks] 生成报告异常: {e}")
                report_result = f'error: {str(e)}'
            
            return jsonify({
                'success': True, 
                'stocks': added_stocks, 
                'count': len(added_stocks),
                'trades_recorded': len(trades),
                'report_status': report_result
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


# ========== 新闻缓存（90秒TTL，防慢请求堵死浏览器连接） ==========
_news_cache = {'data': None, 'time': 0}

@app.route('/api/news')
def get_news():
    """获取结构化财联社新闻 (头条/题材/投资日历/持仓相关)
    带90秒缓存：首次请求实时抓取（12-20s），后续请求直接返回缓存
    解决：新闻接口是页面加载最慢的请求，长期占住浏览器连接导致其他请求排队超时"""
    global _news_cache
    import time as _t
    now = _t.time()
    if _news_cache['data'] and now - _news_cache['time'] < 90:
        return jsonify(_news_cache['data'])
    
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
        _news_cache['data'] = result
        _news_cache['time'] = now
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


# 情绪接口缓存：新引擎数据文件 + 内存TTL，避免每次页面加载都同步跑扫描
_sentiment_api_cache = {'data': None, 'time': 0.0}
SENTIMENT_API_TTL = 1800  # 30分钟
_sentiment_scanning = {'active': False}

def _load_emotion_sentiment():
    """从 emotion_engine 的数据文件加载今日情绪，并映射为前端旧格式"""
    filepath = os.path.join(os.path.dirname(__file__), 'data', 'market_sentiment.json')
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            d = json.load(f)
    except Exception:
        return None
    if not d.get('sentiment_score'):
        return None
    
    stage = d.get('stage', '未知')
    stage_class_map = {
        '冰点期': 'cold', '修复期': 'neutral', '发酵期': 'warm',
        '高潮期': 'hot', '退潮期': 'cool'
    }
    breadth = d.get('market_breadth', {}) or {}
    lud = d.get('limit_up_down', {}) or {}
    
    return {
        'success': True,
        'sentiment_index': {
            'score': d.get('sentiment_score', 50),
            'label': stage,
            'class': stage_class_map.get(stage, 'neutral'),
            'change': d.get('score_change', 0),
            'advice': d.get('stage_advice', ''),
        },
        # 新引擎独有数据（前端可选展示）
        'emotion_detail': {
            'sectors': d.get('sectors', []),
            'stocks': (d.get('stocks') or [])[:30],
            'date': d.get('date', ''),
        },
        # 旧版字段占位（新引擎不采集，前端优雅降级为空）
        'margin': {},
        'north_south': {},
        'capital_flow': {},
        'breadth': {
            'up_count': breadth.get('up', 0),
            'down_count': breadth.get('down', 0),
            'limit_up': lud.get('limit_up', 0),
            'limit_down': lud.get('limit_down', 0),
            'max_continuous': lud.get('max_continuous', 0),
        },
        'update_time': d.get('date', '') + ' 收盘',
        'source': 'emotion_engine'
    }

def _trigger_emotion_scan():
    """后台线程跑一次情绪扫描（不阻塞请求）
    用HEAVY_TASK_SEM串行化：另一个重任务在跑时直接跳过，避免GIL争抢饿死请求
    扫描完成后自动调度今日报告重生成（与事件扫描防抖合并，只跑一次）"""
    if _sentiment_scanning['active']:
        return
    if not HEAVY_TASK_SEM.acquire(blocking=False):
        print('[Sentiment API] 跳过一次情绪扫描（其他重任务进行中）')
        return
    _sentiment_scanning['active'] = True
    
    def _scan():
        try:
            from emotion_engine import generate_sentiment_report
            data = load_data()
            generate_sentiment_report(data.get('stocks', []))
            print('[Sentiment API] 后台情绪扫描完成')
            _schedule_report_regen()
        except Exception as e:
            print(f'[Sentiment API] 后台情绪扫描失败: {e}')
        finally:
            _sentiment_scanning['active'] = False
            HEAVY_TASK_SEM.release()
    
    import threading
    threading.Thread(target=_scan, daemon=True).start()

def _maybe_refresh_sentiment(max_age_sec=1200):
    """情绪数据超龄则后台异步刷新（不阻塞，本次生成仍用现有数据，下次生效）
    仅在交易时段自动触发；非交易时段收盘数据天然有效，不浪费扫描"""
    try:
        import os as _os, time as _t
        f = _os.path.join(_os.path.dirname(__file__), 'data', 'market_sentiment.json')
        if not _os.path.exists(f):
            _trigger_emotion_scan()
            return
        age = _t.time() - _os.path.getmtime(f)
        if age > max_age_sec:
            if not _is_trading_hours_now():
                return
            print(f'[DeepAnalysis] 情绪数据已{age/60:.0f}分钟未更新，触后台刷新')
            _trigger_emotion_scan()
    except Exception:
        pass


def _is_trading_hours_now() -> bool:
    """当前是否处于A股交易时段（周一~周五 09:00-16:05）"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    mins = now.hour * 60 + now.minute
    return 9 * 60 <= mins <= 16 * 60 + 5


# ========== 扫描完成 → 今日报告自动重生成（实时闭环核心） ==========
_report_regen_state = {'timer': None, 'running': False, 'last_done': ''}


def _schedule_report_regen(delay: int = 8):
    """扫描完成后调度今日报告重生成（防抖：情绪+事件扫描完成只触发一次）"""
    import threading
    old = _report_regen_state.get('timer')
    if old and old.is_alive():
        old.cancel()
    t = threading.Timer(delay, _regenerate_today_reports)
    t.daemon = True
    _report_regen_state['timer'] = t
    t.start()


def _regenerate_today_reports():
    """基于最新扫描数据后台重生成今日深度报告（不阻塞请求）"""
    if _report_regen_state['running']:
        return
    if not HEAVY_TASK_SEM.acquire(blocking=False):
        print('[ReportRegen] 跳过今日报告重生成（其他重任务进行中），30秒后重试')
        _schedule_report_regen(delay=30)
        return
    _report_regen_state['running'] = True

    def _run():
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            print(f'[ReportRegen] 基于最新扫描数据重生成今日({today})报告...')
            result = subprocess.run(
                [sys.executable, 'deep_analysis.py'],
                cwd=os.path.dirname(__file__),
                capture_output=True, text=True, timeout=600
            )
            if result.returncode == 0:
                # 重生成会覆盖报告全文，必须接力LLM增强，否则AI研判节被洗掉
                try:
                    llm = subprocess.run(
                        [sys.executable, 'tools/llm_narrative.py'],
                        cwd=os.path.dirname(__file__),
                        capture_output=True, text=True, timeout=900
                    )
                    print(f'[ReportRegen] LLM增强: {llm.stdout.strip().splitlines()[-1] if llm.stdout.strip() else "无输出"}')
                except Exception as e:
                    print(f'[ReportRegen] LLM增强跳过: {e}')
                _report_regen_state['last_done'] = today
                print('[ReportRegen] ✅ 今日报告重生成完成，页面刷新即可见最新数据')
            else:
                print(f'[ReportRegen] ⚠️ 重生成失败: {result.stderr[:300]}')
        except Exception as e:
            print(f'[ReportRegen] 出错: {e}')
        finally:
            _report_regen_state['running'] = False
            HEAVY_TASK_SEM.release()

    import threading
    threading.Thread(target=_run, daemon=True).start()


# ========== 事件引擎后台刷新（与情绪扫描同模式） ==========
_event_scanning = {'active': False}

def _trigger_event_scan():
    """后台线程跑一次事件分析（财联社电报+东财新闻+板块归因），不阻塞请求
    用HEAVY_TASK_SEM串行化：另一个重任务在跑时直接跳过"""
    if _event_scanning['active']:
        return
    if not HEAVY_TASK_SEM.acquire(blocking=False):
        print('[Event API] 跳过事件扫描（其他重任务进行中）')
        return
    _event_scanning['active'] = True
    
    def _scan():
        try:
            from event_tracker import run_event_analysis
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                _d = json.load(f)
            report = run_event_analysis(_d.get('stocks', []))
            print(f"[Event API] 后台事件分析完成: {report.get('news_count', 0)}条新闻, "
                  f"{len(report.get('stock_events', {}))}只股票有事件")
            _schedule_report_regen()
        except Exception as e:
            print(f'[Event API] 后台事件分析失败: {e}')
        finally:
            _event_scanning['active'] = False
            HEAVY_TASK_SEM.release()
    
    threading.Thread(target=_scan, daemon=True).start()

def _maybe_refresh_events(max_age_sec=3600):
    """事件数据超龄（默认1小时）则后台异步刷新
    解决：event_impact.json 只有手动跑 event_tracker.py 才更新，日常流程从不触发"""
    try:
        import os as _os, time as _t
        f = _os.path.join(_os.path.dirname(__file__), 'data', 'event_impact.json')
        if not _os.path.exists(f):
            _trigger_event_scan()
            return
        age = _t.time() - _os.path.getmtime(f)
        if age > max_age_sec:
            if not _is_trading_hours_now():
                return
            print(f'[DeepAnalysis] 事件数据已{age/60:.0f}分钟未更新，触后台刷新')
            _trigger_event_scan()
    except Exception:
        pass

@app.route('/api/market/sentiment')
def get_sentiment():
    """获取市场情绪（新引擎缓存版，永不同步跑重扫描）"""
    import time as _time
    try:
        # 1. 内存缓存命中
        now = _time.time()
        if _sentiment_api_cache['data'] and now - _sentiment_api_cache['time'] < SENTIMENT_API_TTL:
            return jsonify(_sentiment_api_cache['data'])
        
        # 2. 读新引擎数据文件（返回前检查新鲜度：交易时段超龄自动后台刷新+重生成报告）
        result = _load_emotion_sentiment()
        if result:
            _maybe_refresh_sentiment()
            _maybe_refresh_events()
            _sentiment_api_cache['data'] = result
            _sentiment_api_cache['time'] = now
            return jsonify(result)
        
        # 3. 没有数据：触发后台扫描，返回友好提示
        _trigger_emotion_scan()
        return jsonify({
            'success': False,
            'error': '情绪数据首次生成中，约1-2分钟，请稍后刷新',
            'generating': True
        })
    except Exception as e:
        print(f"获取市场情绪失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/data-freshness')
def data_freshness():
    """数据新鲜度状态。前端页面加载时查询：
    交易时段数据超龄会自动触发后台扫描+今日报告重生成，前端随后自动刷新页面"""
    try:
        import os as _os, time as _t, glob as _glob
        now = datetime.now()
        today = now.strftime('%Y-%m-%d')

        def _age_min(path):
            return round((_t.time() - _os.path.getmtime(path)) / 60) if _os.path.exists(path) else None

        base = _os.path.join(_os.path.dirname(__file__), 'data')
        emotion_age = _age_min(_os.path.join(base, 'market_sentiment.json'))
        events_age = _age_min(_os.path.join(base, 'event_impact.json'))
        reports_n = len(_glob.glob(_os.path.join(
            _os.path.dirname(__file__), 'reports', f'deep_analysis_*_{today}.md')))
        scanning = bool(_report_regen_state.get('running')
                        or _sentiment_scanning.get('active')
                        or _event_scanning.get('active'))
        # 页面打开即触发新鲜度检查（交易时段才会真扫描）
        _maybe_refresh_sentiment()
        _maybe_refresh_events()
        return jsonify({
            'success': True,
            'trading_hours': _is_trading_hours_now(),
            'emotion_age_min': emotion_age,
            'events_age_min': events_age,
            'today_reports': reports_n,
            'scanning': scanning,
            'stale': (emotion_age is not None and emotion_age > 20 and _is_trading_hours_now()),
            'time': now.strftime('%H:%M:%S'),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


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
        print(f"[DEBUG] 尝试加载报告，路径: {PORTFOLIO_ANALYSIS_FILE}")
        print(f"[DEBUG] 当前工作目录: {os.getcwd()}")
        print(f"[DEBUG] 文件是否存在: {os.path.exists(PORTFOLIO_ANALYSIS_FILE)}")
        if not os.path.exists(PORTFOLIO_ANALYSIS_FILE):
            print(f"[DEBUG] 报告文件不存在")
            return None
        
        with open(PORTFOLIO_ANALYSIS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"[DEBUG] 报告加载成功，股票数: {len(data.get('stock_analyses', []))}")
        return data
    except Exception as e:
        print(f"[DEBUG] 加载持仓分析报告失败: {e}")
        import traceback
        traceback.print_exc()
        return None

@app.route('/api/portfolio-analysis')
def get_portfolio_analysis():
    """获取持仓分析报告 - 禁用服务器缓存，确保数据实时"""
    
    def add_no_cache_headers(response):
        """添加防缓存头"""
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Vary'] = '*'
        return response
    
    try:
        # 强制每次都从文件重新加载
        print(f"[Portfolio Analysis] 收到请求，强制重新加载文件...")
        
        # 确定要读取的文件路径
        file_to_read = PORTFOLIO_ANALYSIS_FILE
        
        # 先检查 latest 文件是否存在
        if not os.path.exists(file_to_read):
            print(f"[Portfolio Analysis] latest 文件不存在，尝试查找日期文件...")
            # 查找 reports 目录下最新的 portfolio_analysis_YYYY-MM-DD.json 文件
            reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
            if os.path.exists(reports_dir):
                import glob
                date_files = glob.glob(os.path.join(reports_dir, 'portfolio_analysis_202[0-9]-[0-9][0-9]-[0-9][0-9].json'))
                if date_files:
                    # 按修改时间排序，取最新的
                    date_files.sort(key=os.path.getmtime, reverse=True)
                    file_to_read = date_files[0]
                    print(f"[Portfolio Analysis] 找到日期文件: {file_to_read}")
        
        # 检查文件是否存在（可能是 latest 或日期文件）
        if not os.path.exists(file_to_read):
            print(f"[Portfolio Analysis] 文件不存在: {file_to_read}")
            # 返回占位数据
            response = jsonify({
                'success': True,
                'data': {
                    'summary': {
                        'health_score': 0,
                        'health_level': {'label': '待生成', 'color': '#999', 'desc': '报告正在生成中，请稍后再试'},
                        'total_stocks': len(load_data().get('stocks', [])),
                        'total_pnl': 0,
                        'total_pnl_percent': 0
                    },
                    'stock_analyses': [],
                    'sector_analysis': [],
                    'portfolio_analysis': {
                        'position': {'position_advice': '报告正在生成，请稍后再试'},
                        'risks': []
                    },
                    'alerts': [],
                    'highlights': [],
                    'generated_at': '生成中...',
                    'report_date': datetime.now().strftime('%Y-%m-%d')
                },
                'cached': False,
                'generating': True
            })
            return add_no_cache_headers(response)
        
        # 文件存在，直接读取
        print(f"[Portfolio Analysis] 读取文件: {file_to_read}")
        with open(file_to_read, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        stock_count = len(data.get('stock_analyses', []))
        health_score = data.get('summary', {}).get('health_score', 0)
        print(f"[Portfolio Analysis] 读取成功: {stock_count} 只股票, 健康分: {health_score}")
        
        # 添加调试信息
        file_stat = os.stat(file_to_read)
        data['_debug'] = {
            'file_mtime': file_stat.st_mtime,
            'file_size': file_stat.st_size,
            'stock_count': stock_count,
            'server_time': datetime.now().isoformat(),
            'read_from': file_to_read
        }
        
        response = jsonify({
            'success': True,
            'data': data,
            'cached': False
        })
        return add_no_cache_headers(response)
        
    except Exception as e:
        print(f"[Portfolio Analysis] 获取报告异常: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': False,
            'error': str(e)
        })
        return add_no_cache_headers(response)


# ========== 报告自动检查与生成 API ==========

@app.route('/api/reports/check')
def check_report_exists():
    """
    检查指定日期的报告是否存在
    参数: date (YYYY-MM-DD)，默认今天
    """
    try:
        date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        # 检查日期格式
        try:
            check_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'error': '日期格式错误，应为 YYYY-MM-DD'
            }), 400
        
        # 检查最新的报告文件
        reports_dir = os.path.join(os.path.dirname(__file__), 'reports')
        
        # 检查两种方式：1. latest 文件  2. 日期文件
        latest_file = os.path.join(reports_dir, 'portfolio_analysis_latest.json')
        date_file = os.path.join(reports_dir, f'portfolio_analysis_{date_str}.json')
        
        exists = False
        report_file = None
        report_mtime = None
        
        # 优先检查日期文件
        if os.path.exists(date_file):
            exists = True
            report_file = date_file
            report_mtime = os.path.getmtime(date_file)
        # 其次检查 latest 文件
        elif os.path.exists(latest_file):
            # 检查 latest 文件的修改时间是否匹配请求日期
            latest_mtime = os.path.getmtime(latest_file)
            latest_date = datetime.fromtimestamp(latest_mtime).strftime('%Y-%m-%d')
            if latest_date == date_str:
                exists = True
                report_file = latest_file
                report_mtime = latest_mtime
        
        result = {
            'success': True,
            'date': date_str,
            'exists': exists,
            'report_file': report_file,
            'server_time': datetime.now().isoformat()
        }
        
        if exists and report_mtime:
            result['report_mtime'] = datetime.fromtimestamp(report_mtime).isoformat()
            result['report_mtime_timestamp'] = report_mtime
        
        print(f"[Report Check] 日期: {date_str}, 存在: {exists}")
        return jsonify(result)
        
    except Exception as e:
        print(f"[Report Check] 错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/reports/generate', methods=['POST'])
def generate_report():
    """
    手动触发生成持仓深度分析报告（深度版）
    流程：deep_analysis.py 重建14只正文 → tools/llm_narrative.py --think 深度AI研判
    全程后台异步执行（约60-70分钟），接口立即返回；期间勿重复点击
    """
    try:
        if _report_regen_state.get('running'):
            return jsonify({'success': False, 'error': '已有生成任务进行中，请等待完成后再点击'}), 409
        if not HEAVY_TASK_SEM.acquire(blocking=False):
            return jsonify({'success': False, 'error': '系统正忙（扫描或生成中），请稍后重试'}), 409

        _report_regen_state['running'] = True

        def _bg_deep_gen():
            try:
                print('[ManualGen] 深度生成启动：重建14只正文（deep_analysis.py）...')
                r1 = subprocess.run(
                    [sys.executable, 'deep_analysis.py'],
                    cwd=os.path.dirname(__file__),
                    capture_output=True, text=True, timeout=900
                )
                if r1.returncode != 0:
                    print(f'[ManualGen] ⚠️ 正文生成失败: {r1.stderr[:300]}')
                    return
                print('[ManualGen] 正文完成，接力深度LLM研判（--think，单只约4.5分钟×14）...')
                r2 = subprocess.run(
                    [sys.executable, 'tools/llm_narrative.py', '--think'],
                    cwd=os.path.dirname(__file__),
                    capture_output=True, text=True, timeout=7200
                )
                tail = r2.stdout.strip().splitlines()[-1] if r2.stdout.strip() else '无输出'
                print(f'[ManualGen] ✅ 深度生成全部完成: {tail}')
            except Exception as e:
                print(f'[ManualGen] 出错: {e}')
            finally:
                _report_regen_state['running'] = False
                HEAVY_TASK_SEM.release()

        import threading
        threading.Thread(target=_bg_deep_gen, daemon=True).start()
        return jsonify({
            'success': True,
            'message': '深度生成已在后台启动：14只报告将依次重建正文+深度AI研判（约60-70分钟），逐只完成后刷新页面即可查看'
        })
    except Exception as e:
        print(f"[Report Generate] 异常: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def setup_cron_job():
    """启动时自动检查并设置 crontab 定时任务"""
    try:
        import subprocess
        
        # 当前脚本路径
        script_path = os.path.join(os.path.dirname(__file__), 'generate_daily_report.sh')
        
        # 检查 crontab 中是否已存在该任务
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        current_crontab = result.stdout if result.returncode == 0 else ''
        
        if script_path in current_crontab:
            print(f"[Cron] 定时任务已存在，跳过设置")
            return
        
        # 构建新的 crontab 内容
        cron_line = f"30 16 * * * {script_path}"
        new_crontab = current_crontab.strip() + '\n' + cron_line + '\n'
        
        # 写入 crontab
        proc = subprocess.Popen(['crontab', '-'], stdin=subprocess.PIPE, text=True)
        proc.communicate(input=new_crontab)
        
        if proc.returncode == 0:
            print(f"[Cron] ✅ 定时任务已自动设置: 每天 16:30 生成持仓分析报告")
        else:
            print(f"[Cron] ⚠️ 设置定时任务失败，请手动执行: crontab -e")
            print(f"[Cron] 添加此行: {cron_line}")
            
    except Exception as e:
        print(f"[Cron] ⚠️ 自动设置定时任务出错: {e}")
        print(f"[Cron] 如需定时生成报告，请手动配置 crontab")


def ensure_portfolio_analysis():
    """启动时检查深度分析报告是否存在，不存在则自动生成"""
    try:
        report_dir = os.path.join(os.path.dirname(__file__), 'reports')
        today = datetime.now().strftime('%Y-%m-%d')
        import glob
        files = glob.glob(os.path.join(report_dir, f'deep_analysis_*_{today}.md'))
        
        if files:
            print(f"[Report] 今日深度分析报告已存在: {len(files)} 份")
            return
        
        # 先检查 stocks.json 数据
        data = load_data()
        stocks = data.get('stocks', [])
        print(f"[Report] 当前持仓股票数量: {len(stocks)}")
        if stocks:
            print(f"[Report] 前3只股票: {[s.get('code') for s in stocks[:3]]}")
        
        print("[Report] 深度分析报告不存在，正在自动生成...")
        import subprocess
        result = subprocess.run(
            [sys.executable, 'deep_analysis.py'],
            cwd=os.path.dirname(__file__),
            capture_output=True,
            text=True,
            timeout=600
        )
        if result.returncode == 0:
            print("[Report] ✅ 深度分析报告生成成功")
            files = glob.glob(os.path.join(report_dir, f'deep_analysis_*_{today}.md'))
            print(f"[Report] 生成报告数: {len(files)} 份")
        else:
            print(f"[Report] ⚠️ 报告生成失败: {result.stderr}")
            print(f"[Report] stdout: {result.stdout}")
    except Exception as e:
        print(f"[Report] ⚠️ 检查/生成报告时出错: {e}")
        import traceback
        traceback.print_exc()


@app.route('/api/trades/import', methods=['POST'])
def import_trades():
    """
    导入历史成交记录，更新持仓股的 last_trade 信息
    """
    try:
        data = request.json
        trades = data.get('trades', [])
        
        if not trades:
            return jsonify({
                'success': False,
                'error': '交易记录为空'
            }), 400
        
        print(f"[TradeImport] 接收 {len(trades)} 笔交易记录")
        
        # 加载现有持仓数据
        portfolio_data = load_data()
        stocks = portfolio_data.get('stocks', [])
        
        # 建立股票代码索引
        stock_map = {s.get('code'): s for s in stocks}
        
        # 按股票分组交易，找到每只股票最新的一笔
        latest_trades = {}
        for trade in trades:
            code = trade.get('code')
            if not code:
                continue
            
            # 只处理持仓中存在的股票
            if code not in stock_map:
                print(f"[TradeImport] 跳过非持仓股交易: {code}")
                continue
            
            # 记录最新交易（按时间）
            if code not in latest_trades:
                latest_trades[code] = trade
            else:
                # 比较时间，保留更新的
                current_time = latest_trades[code].get('time', '')
                new_time = trade.get('time', '')
                if new_time > current_time:
                    latest_trades[code] = trade
        
        # 【修复】不再用交易记录重新计算持仓数量
        # 原因：交易记录通常不完整，缺少历史初始持仓
        # 持仓数量应以持仓导入的数据为准
        updated_count = 0
        for code, trade in latest_trades.items():
            stock = stock_map[code]
            
            # 只更新 last_trade 信息（只更新真实交易，跳过初始持仓导入）
            note = trade.get('note', '')
            if note != '初始持仓导入':
                stock['last_trade_price'] = trade.get('price', 0)
                stock['last_trade_type'] = trade.get('tradeType', '')
                stock['last_trade_time'] = trade.get('time', '')
                stock['last_trade_shares'] = trade.get('shares', 0)
                updated_count += 1
                print(f"[TradeImport] 更新 {code}: {trade.get('tradeType')} @ {trade.get('price')} ({trade.get('time')})")
            else:
                print(f"[TradeImport] 跳过初始持仓记录: {code}")
        
        # 同时保存到交易日志
        if 'trade_logs' not in portfolio_data:
            portfolio_data['trade_logs'] = []
        
        for trade in trades:
            trade_record = {
                'id': f"{int(time.time())}_{trade.get('code')}_{trade.get('tradeType')}",
                'time': trade.get('time', datetime.now().isoformat()),
                'stock_code': trade.get('code'),
                'stock_name': trade.get('name', ''),
                'trade_type': trade.get('tradeType'),
                'price': trade.get('price', 0),
                'shares': trade.get('shares', 0),
                'amount': trade.get('price', 0) * trade.get('shares', 0),
                'imported_at': datetime.now().isoformat()
            }
            portfolio_data['trade_logs'].append(trade_record)
        
        # 保存数据
        if save_data(portfolio_data):
            print(f"[TradeImport] 成功更新 {updated_count} 只股票的交易记录")
            return jsonify({
                'success': True,
                'updated': updated_count,
                'total_trades': len(trades),
                'message': f'成功更新 {updated_count} 只股票的交易记录'
            })
        else:
            return jsonify({
                'success': False,
                'error': '保存数据失败'
            }), 500
            
    except Exception as e:
        print(f"[TradeImport] 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    # 启动时自动设置 crontab
    setup_cron_job()
    
    # ========== 深度分析报告 API ==========
@app.route('/api/deep-analysis/<stock_code>')
def get_deep_analysis(stock_code):
    """获取指定股票的深度分析报告（Markdown格式）
    轻量路径：直读文件不抢全局锁，保证高负载下也能快速返回"""
    try:
        # 打开报告页时顺带检查数据新鲜度（交易时段超龄→自动后台扫描并重生成今日报告）
        _maybe_refresh_sentiment()
        _maybe_refresh_events()
        # 轻量读 stocks.json（不抢 data_file_lock）
        stock = None
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                _data = json.load(f)
            for s in _data.get('stocks', []):
                if s.get('code') == stock_code:
                    stock = s
                    break
        except Exception:
            pass
        
        if not stock:
            return jsonify({'success': False, 'error': '股票不存在'}), 404
        
        # 构建报告文件路径
        report_dir = os.path.join(os.path.dirname(__file__), 'reports')
        today = datetime.now().strftime('%Y-%m-%d')
        report_file = os.path.join(report_dir, f'deep_analysis_{stock_code}_{today}.md')
        
        # 如果今天的报告不存在，尝试找最近的报告
        report_content = None
        actual_date = today
        is_stale = False
        if os.path.exists(report_file):
            with open(report_file, 'r', encoding='utf-8') as f:
                report_content = f.read()
        else:
            # 查找最近的报告文件
            import glob
            pattern = os.path.join(report_dir, f'deep_analysis_{stock_code}_*.md')
            files = glob.glob(pattern)
            if files:
                # 按修改时间排序，取最新的
                files.sort(key=os.path.getmtime, reverse=True)
                with open(files[0], 'r', encoding='utf-8') as f:
                    report_content = f.read()
                # 提取文件名中的实际日期
                fname = os.path.basename(files[0])
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', fname)
                if date_match:
                    actual_date = date_match.group(1)
                is_stale = (actual_date != today)
        
        if report_content:
            return jsonify({
                'success': True,
                'stock_code': stock_code,
                'stock_name': stock.get('name', ''),
                'report_date': actual_date,
                'is_stale': is_stale,
                'content': report_content,
                'has_report': True
            })
        else:
            return jsonify({
                'success': True,
                'stock_code': stock_code,
                'stock_name': stock.get('name', ''),
                'report_date': today,
                'content': '报告生成中，请稍后刷新...',
                'has_report': False
            })
    except Exception as e:
        print(f"[DeepAnalysis API] 错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# 盘中生成任务状态（内存 dict，重启后清空）
GEN_STATUS = {}  # code -> {'status': 'queued'/'generating'/'done'/'error', 'started': ts, 'error': msg}
GEN_SEMAPHORE = threading.Semaphore(2)  # 最多同时生成2只，其余排队，防止CPU打满请求饿死
# 全局重任务串行化：情绪扫描/事件扫描/类型补算同时只允许一个跑
# 这些任务全是 akshare+pandas 重CPU活，并发跑会把 GIL 抢光导致请求超时
HEAVY_TASK_SEM = threading.Semaphore(1)
APP_VERSION = '3.3.4'
import time as _time

@app.route('/api/deep-analysis/generate/<stock_code>', methods=['POST'])
def generate_deep_analysis_single(stock_code):
    """触发单只股票深度报告生成（异步，立即返回，轮询 status 获取结果）
    设计原则：请求线程只做毫秒级操作，绝不在这里等锁/等重算"""
    try:
        # 轻量读文件，不抢 data_file_lock（读操作，JSON一次性load是原子的）
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = {'stocks': []}
        stock = None
        for s in data.get('stocks', []):
            if s.get('code') == stock_code:
                stock = s
                break
        
        if not stock:
            return jsonify({'success': False, 'error': '股票不存在', 'v': APP_VERSION}), 404
        
        # 已在生成/排队中，直接返回当前状态（防重复点击）
        cur = GEN_STATUS.get(stock_code, {})
        if cur.get('status') in ('generating', 'queued'):
            return jsonify({'success': True, 'status': cur.get('status'),
                            'stock_code': stock_code, 'v': APP_VERSION})
        
        GEN_STATUS[stock_code] = {'status': 'queued', 'started': _time.time()}
        
        def _gen():
            # 信号量限流：最多2个并发生成，其余线程在此等待空位
            GEN_SEMAPHORE.acquire()
            try:
                GEN_STATUS[stock_code] = {'status': 'generating', 'started': _time.time()}
                # 优先生成报告（用户在等），情绪/事件刷新放后面慢慢跑
                from deep_analysis import generate_deep_report
                report_content = generate_deep_report(stock)
                
                report_dir = os.path.join(os.path.dirname(__file__), 'reports')
                os.makedirs(report_dir, exist_ok=True)
                today = datetime.now().strftime('%Y-%m-%d')
                report_file = os.path.join(report_dir, f'deep_analysis_{stock_code}_{today}.md')
                with open(report_file, 'w', encoding='utf-8') as f:
                    f.write(report_content)
                
                GEN_STATUS[stock_code] = {'status': 'generating', 'started': _time.time()}
                print(f"[DeepAnalysis Generate] {stock_code} 盘中报告已生成")
                # 接力深度AI研判（--think单只约4.5分钟）；status保持generating让前端继续等
                try:
                    import subprocess as _sp
                    llm = _sp.run(
                        [sys.executable, 'tools/llm_narrative.py', '--think', stock_code],
                        cwd=os.path.dirname(__file__),
                        capture_output=True, text=True, timeout=900
                    )
                    tail = llm.stdout.strip().splitlines()[-1] if llm.stdout.strip() else '无输出'
                    print(f'[DeepAnalysis Generate] {stock_code} AI研判完成: {tail}')
                except Exception as e:
                    print(f'[DeepAnalysis Generate] {stock_code} AI研判跳过: {e}')
                GEN_STATUS[stock_code] = {'status': 'done', 'finished': _time.time(), 'report_date': today}
                
                # 不在这里触发情绪/事件刷新——127项事件扫描会饿死请求线程导致前端超时
                # 情绪/事件数据由每日cron定时刷新，不阻塞用户交互路径
            except Exception as e:
                import traceback
                traceback.print_exc()
                GEN_STATUS[stock_code] = {'status': 'error', 'error': str(e)}
            finally:
                GEN_SEMAPHORE.release()
        
        import threading
        threading.Thread(target=_gen, daemon=True).start()
        
        return jsonify({
            'success': True,
            'status': 'queued',
            'stock_code': stock_code,
            'stock_name': stock.get('name', ''),
            'v': APP_VERSION
        })
    except Exception as e:
        print(f"[DeepAnalysis Generate] 错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'v': APP_VERSION}), 500

@app.route('/api/deep-analysis/status/<stock_code>')
def deep_analysis_gen_status(stock_code):
    """查询盘中生成任务状态"""
    info = GEN_STATUS.get(stock_code, {'status': 'unknown'})
    return jsonify({'success': True, 'stock_code': stock_code, **info})


@app.route('/api/deep-analysis/batch', methods=['POST'])
def generate_deep_analysis_batch():
    """批量生成深度分析报告（异步任务入口）"""
    try:
        data = load_data()
        stocks = data.get('stocks', [])
        
        # 异步在后台生成报告
        def _generate_reports():
            import subprocess
            try:
                result = subprocess.run(
                    [sys.executable, 'deep_analysis.py'],
                    cwd=os.path.dirname(__file__),
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                print(f"[DeepAnalysis Batch] 生成完成: {result.returncode}")
                if result.returncode != 0:
                    print(f"[DeepAnalysis Batch] 错误: {result.stderr[:500]}")
            except Exception as e:
                print(f"[DeepAnalysis Batch] 异常: {e}")
        
        thread = threading.Thread(target=_generate_reports, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': f'已在后台开始生成 {len(stocks)} 只股票的深度分析报告',
            'stock_count': len(stocks)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    # 启动时检查报告文件——放后台线程，绝不阻塞服务器启动
    # （之前同步跑subprocess最长卡10分钟，服务器期间完全不响应）
    def _defer_ensure_reports():
        try:
            ensure_portfolio_analysis()
        except Exception as e:
            print(f'[Report] 后台生成检查失败: {e}')
    threading.Thread(target=_defer_ensure_reports, daemon=True).start()
    
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
    
    app.run(debug=False, host='0.0.0.0', port=8888, use_reloader=False, threaded=True)


