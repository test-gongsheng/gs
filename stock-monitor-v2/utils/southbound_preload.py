"""
南向资金预加载服务
每日定时预加载所有持仓港股数据到缓存
"""
import os
import json
import sqlite3
import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'southbound.db')

# 内存缓存（比SQLite快10倍）
_memory_cache = {}
_cache_lock = threading.RLock()

# 预加载配置
PRELOAD_CONFIG = {
    'batch_size': 5,      # 每批处理5只股票（避免akshare超时）
    'batch_interval': 3,  # 批次间隔3秒（降低服务器压力）
    'max_retries': 3,     # 单只股票最大重试次数
}

def _init_preload_table():
    """初始化预加载缓存表"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS southbound_preload_cache (
            stock_code TEXT PRIMARY KEY,
            stock_name TEXT,
            data_json TEXT,           -- 90日数据JSON
            record_count INTEGER,
            updated_at INTEGER,       -- Unix时间戳
            is_preloaded INTEGER DEFAULT 0,  -- 是否预加载成功
            error_count INTEGER DEFAULT 0,   -- 连续失败次数
            last_error TEXT          -- 最后一次错误信息
        )
    ''')
    conn.commit()
    conn.close()

def get_preload_cache(stock_code: str) -> Optional[List[Dict]]:
    """从内存缓存获取数据（最快）"""
    with _cache_lock:
        cached = _memory_cache.get(stock_code)
        if cached:
            # 检查是否过期（5分钟）
            if time.time() - cached['timestamp'] < 300:
                return cached['data']
    return None

def set_preload_cache(stock_code: str, data: List[Dict], stock_name: str = ""):
    """设置内存缓存和SQLite缓存"""
    # 1. 更新内存缓存
    with _cache_lock:
        _memory_cache[stock_code] = {
            'data': data,
            'timestamp': time.time()
        }
    
    # 2. 更新SQLite（持久化）
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO southbound_preload_cache 
            (stock_code, stock_name, data_json, record_count, updated_at, is_preloaded, error_count)
            VALUES (?, ?, ?, ?, ?, 1, 0)
        ''', (
            stock_code,
            stock_name,
            json.dumps(data),
            len(data),
            int(time.time())
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Preload] 保存SQLite失败: {stock_code}, {e}")

def load_memory_cache_from_db():
    """Flask启动时从SQLite加载到内存"""
    global _memory_cache
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT stock_code, data_json, updated_at FROM southbound_preload_cache 
            WHERE is_preloaded = 1 AND updated_at > ?
        ''', (int(time.time()) - 3600,))  # 1小时内的数据
        
        rows = cursor.fetchall()
        conn.close()
        
        with _cache_lock:
            for row in rows:
                stock_code, data_json, updated_at = row
                try:
                    _memory_cache[stock_code] = {
                        'data': json.loads(data_json),
                        'timestamp': updated_at
                    }
                except:
                    pass
        
        print(f"[Preload] 从SQLite加载 {len(_memory_cache)} 只股票到内存缓存")
        
    except Exception as e:
        print(f"[Preload] 加载内存缓存失败: {e}")

def get_all_hk_stocks() -> List[str]:
    """获取所有持仓港股代码"""
    try:
        stocks_json_path = os.path.join(DATA_DIR, 'stocks.json')
        if os.path.exists(stocks_json_path):
            with open(stocks_json_path, 'r', encoding='utf-8') as f:
                stocks_data = json.load(f)
                hk_stocks = []
                for stock in stocks_data.get('stocks', []):
                    if stock.get('market') == '港股':
                        hk_stocks.append(stock.get('code'))
                return hk_stocks
    except Exception as e:
        print(f"[Preload] 读取stocks.json失败: {e}")
    return []

def preload_single_stock(stock_code: str) -> bool:
    """
    预加载单只股票的南向资金数据
    返回是否成功
    """
    from southbound_capital import get_southbound_stock_history
    
    for retry in range(PRELOAD_CONFIG['max_retries']):
        try:
            print(f"[Preload] 加载 {stock_code} (尝试 {retry+1}/{PRELOAD_CONFIG['max_retries']})")
            data = get_southbound_stock_history(stock_code, days=90)
            
            if data and len(data) > 0:
                stock_name = data[0].get('stock_name', '')
                set_preload_cache(stock_code, data, stock_name)
                print(f"[Preload] ✅ {stock_code} 成功，{len(data)}条数据")
                return True
            else:
                print(f"[Preload] ⚠️ {stock_code} 无数据")
                
        except Exception as e:
            print(f"[Preload] ❌ {stock_code} 失败: {e}")
            time.sleep(1)
    
    # 记录失败
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO southbound_preload_cache 
            (stock_code, is_preloaded, error_count, last_error)
            VALUES (?, 0, COALESCE((SELECT error_count FROM southbound_preload_cache WHERE stock_code=?), 0) + 1, ?)
        ''', (stock_code, stock_code, str(e)))
        conn.commit()
        conn.close()
    except:
        pass
    
    return False

def preload_all_hk_stocks():
    """
    预加载所有持仓港股数据
    分批处理，避免服务器压力
    """
    _init_preload_table()
    
    hk_stocks = get_all_hk_stocks()
    if not hk_stocks:
        print("[Preload] 无持仓港股")
        return
    
    print(f"[Preload] 开始预加载 {len(hk_stocks)} 只港股...")
    start_time = time.time()
    
    success_count = 0
    fail_count = 0
    
    for i, stock_code in enumerate(hk_stocks):
        if preload_single_stock(stock_code):
            success_count += 1
        else:
            fail_count += 1
        
        # 批次间隔（避免服务器压力）
        if (i + 1) % PRELOAD_CONFIG['batch_size'] == 0:
            print(f"[Preload] 批次完成 {i+1}/{len(hk_stocks)}，休息{PRELOAD_CONFIG['batch_interval']}秒...")
            time.sleep(PRELOAD_CONFIG['batch_interval'])
    
    elapsed = time.time() - start_time
    print(f"[Preload] 完成! 成功:{success_count} 失败:{fail_count} 耗时:{elapsed:.1f}秒")

# ============ 定时任务入口 ============

def run_preload_job():
    """定时任务入口"""
    print(f"\n{'='*50}")
    print(f"[Preload] 定时任务启动 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    preload_all_hk_stocks()

if __name__ == "__main__":
    # 手动运行预加载
    run_preload_job()
