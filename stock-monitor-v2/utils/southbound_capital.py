"""
南向资金（港股通）数据模块
获取港股通整体资金流向和个股资金流向
"""
import os
import json
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import akshare as ak
import pandas as pd

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'southbound.db')

# SQLite缓存（多进程共享，避免每次请求都调用akshare）
CACHE_TTL = 300  # 缓存5分钟

def _init_cache_db():
    """初始化缓存数据库"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS southbound_cache (
            cache_key TEXT PRIMARY KEY,
            stock_code TEXT,
            data TEXT,  -- JSON格式
            created_at INTEGER,
            expires_at INTEGER
        )
    ''')
    # 南向资金个股数据缓存表（原生表结构，更可靠）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS southbound_stock_cache (
            stock_code TEXT PRIMARY KEY,
            stock_name TEXT,
            data_json TEXT,  -- 整组数据的JSON
            record_count INTEGER,
            created_at INTEGER,
            expires_at INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def _get_cache(stock_code):
    """从SQLite获取缓存数据（直接用stock_code作为key）"""
    try:
        _init_cache_db()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = int(time.time())
        cursor.execute('''
            SELECT data_json, stock_name FROM southbound_stock_cache 
            WHERE stock_code = ? AND expires_at > ?
        ''', (stock_code, now))
        row = cursor.fetchone()
        conn.close()
        if row:
            data = json.loads(row[0])
            print(f"[Cache] 命中: {stock_code}, {len(data)}条, 名称={row[1]}")
            return data
    except Exception as e:
        print(f"[Cache] 读取失败: {e}")
    return None

def _set_cache(stock_code, data):
    """保存数据到SQLite缓存（简化版）"""
    try:
        if not data or len(data) == 0:
            return
        
        _init_cache_db()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = int(time.time())
        expires_at = now + CACHE_TTL
        
        stock_name = data[0].get('stock_name', stock_code)
        
        # 转换为简单类型确保JSON可序列化
        clean_data = []
        for item in data:
            clean_item = {}
            for k, v in item.items():
                # 转换numpy类型和普通类型
                if hasattr(v, 'item'):  # numpy类型
                    clean_item[k] = v.item()
                else:
                    clean_item[k] = v
            clean_data.append(clean_item)
        
        json_data = json.dumps(clean_data, ensure_ascii=False)
        
        cursor.execute('''
            INSERT OR REPLACE INTO southbound_stock_cache 
            (stock_code, stock_name, data_json, record_count, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (stock_code, stock_name, json_data, len(clean_data), now, expires_at))
        conn.commit()
        conn.close()
        print(f"[Cache] 已保存: {stock_code}, {len(clean_data)}条")
    except Exception as e:
        print(f"[Cache] 写入失败: {e}")
        import traceback
        traceback.print_exc()

def init_db():
    """初始化数据库"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 南向资金整体流向表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS southbound_overall (
            date TEXT PRIMARY KEY,
            net_inflow REAL,           -- 当日净买入额（亿元）
            buy_amount REAL,           -- 买入成交额
            sell_amount REAL,          -- 卖出成交额
            cumulative_30d REAL,       -- 近30日累计
            cumulative_90d REAL,       -- 近90日累计
            update_time TEXT
        )
    ''')
    
    # 港股通个股资金流向表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS southbound_stock (
            date TEXT,
            stock_code TEXT,
            stock_name TEXT,
            net_inflow REAL,           -- 当日净买入（亿港元）
            buy_amount REAL,           -- 买入成交额
            sell_amount REAL,          -- 卖出成交额
            hold_ratio REAL,           -- 港股通持股比例
            hold_shares REAL,          -- 持股数量
            hold_change REAL,          -- 持股变化
            PRIMARY KEY (date, stock_code)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_southbound_overall_history(days: int = 90) -> List[Dict]:
    """
    获取南向资金整体历史流向
    返回最近N个有效交易日的数据
    """
    try:
        # 使用akshare获取南向资金历史数据
        df = ak.stock_hsgt_hist_em(symbol="南向资金")
        
        if df is None or len(df) == 0:
            return []
        
        # 取最近N条数据
        df = df.tail(days).copy()
        df = df.sort_values('日期', ascending=True)
        
        result = []
        for _, row in df.iterrows():
            # 转换日期为字符串
            date_val = row['日期']
            if isinstance(date_val, pd.Timestamp):
                date_str = date_val.strftime('%Y-%m-%d')
            else:
                date_str = str(date_val)
            
            result.append({
                'date': date_str,
                'net_inflow': round(float(row['当日成交净买额']), 2),
                'buy_amount': round(float(row['买入成交额']), 2),
                'sell_amount': round(float(row['卖出成交额']), 2)
            })
        
        # 计算累计值
        for i, item in enumerate(result):
            if i >= 30:
                item['cumulative_30d'] = round(sum(r['net_inflow'] for r in result[i-29:i+1]), 2)
            else:
                item['cumulative_30d'] = round(sum(r['net_inflow'] for r in result[:i+1]), 2)
            
            if i >= 90:
                item['cumulative_90d'] = round(sum(r['net_inflow'] for r in result[i-89:i+1]), 2)
            else:
                item['cumulative_90d'] = round(sum(r['net_inflow'] for r in result[:i+1]), 2)
        
        return result
    except Exception as e:
        print(f"获取南向资金历史数据失败: {e}")
        return []

def get_southbound_stock_history(stock_code: str, days: int = 90) -> List[Dict]:
    """
    获取指定港股通股票的南向资金流向历史
    使用SQLite缓存，5分钟内重复请求直接返回缓存数据
    """
    # 先尝试从缓存读取
    cached = _get_cache(stock_code)
    if cached:
        return cached
    
    try:
        # 从 stocks.json 获取正确的股票名称
        stock_name = stock_code  # 默认使用代码作为名称
        try:
            stocks_json_path = os.path.join(DATA_DIR, 'stocks.json')
            if os.path.exists(stocks_json_path):
                with open(stocks_json_path, 'r', encoding='utf-8') as f:
                    stocks_data = json.load(f)
                    for stock in stocks_data.get('stocks', []):
                        if stock.get('code') == stock_code:
                            stock_name = stock.get('name', stock_code)
                            break
        except Exception as e:
            print(f"[Southbound] 读取stocks.json失败: {e}")
        
        print(f"[Southbound] 从akshare获取数据: {stock_code} ({stock_name})")
        start_time = time.time()
        
        # 标准化股票代码：去掉前导零，用于匹配
        hk_code_normalized = stock_code.lstrip('0')
        if not hk_code_normalized:
            hk_code_normalized = stock_code
        
        # 获取最近N个交易日的日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 30)
        
        # 调用akshare获取南向持股数据
        df = ak.stock_hsgt_stock_statistics_em(
            symbol="南向持股",
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d')
        )
        
        elapsed = time.time() - start_time
        print(f"[Southbound] akshare请求耗时: {elapsed:.2f}秒")
        
        if df is None or len(df) == 0:
            print(f"[Southbound] 无南向持股数据")
            return []
        
        # 将 DataFrame 中的代码标准化为字符串并去掉前导零
        df['code_normalized'] = df['股票代码'].astype(str).str.lstrip('0')
        
        # 筛选指定股票的数据（使用标准化后的代码匹配）
        stock_data = df[df['code_normalized'] == hk_code_normalized].copy()
        
        # 如果匹配不到，尝试原始代码匹配
        if len(stock_data) == 0:
            stock_data = df[df['股票代码'].astype(str) == stock_code].copy()
        
        # 如果还匹配不到，尝试用原始代码去掉前导零后的各种变体
        if len(stock_data) == 0:
            # 可能是带 .HK 后缀的情况
            stock_code_clean = stock_code.replace('.HK', '').replace('.hk', '')
            if stock_code_clean != stock_code:
                hk_code_normalized = stock_code_clean.lstrip('0')
                stock_data = df[df['code_normalized'] == hk_code_normalized].copy()
        
        if len(stock_data) == 0:
            # 打印调试信息
            available_codes = df['股票代码'].astype(str).unique()[:10]
            print(f"[Southbound] 未找到股票 {stock_code} (标准化: {hk_code_normalized})")
            print(f"[Southbound] 可用代码样例: {list(available_codes)}")
            return []
        
        # 按日期排序
        stock_data = stock_data.sort_values('持股日期', ascending=True)
        stock_data = stock_data.tail(days)
        
        result = []
        prev_shares = None
        
        for _, row in stock_data.iterrows():
            date_str = row['持股日期']
            if isinstance(date_str, pd.Timestamp):
                date_str = date_str.strftime('%Y-%m-%d')
            
            hold_shares = float(row.get('持股数量', 0))
            hold_ratio = float(row.get('持股数量占发行股百分比', 0))
            close_price = float(row.get('当日收盘价', 0))
            
            # 计算持股变化（与前一日比较）
            hold_change = 0
            if prev_shares is not None:
                hold_change = hold_shares - prev_shares
            prev_shares = hold_shares
            
            # 估算净流入（持股变化 × 当日收盘价 / 100000000）
            net_inflow = round(hold_change * close_price / 100000000, 2)
            
            result.append({
                'date': str(date_str),
                'stock_code': stock_code,
                'stock_name': stock_name,  # 使用正确的名称
                'net_inflow': net_inflow,
                'hold_ratio': round(hold_ratio, 2),
                'hold_shares': round(hold_shares, 2),
                'hold_change': round(hold_change, 2),
                'close_price': close_price
            })
        
        print(f"[Southbound] 股票 {stock_code} 返回 {len(result)} 条数据")
        
        # 保存到缓存
        _set_cache(stock_code, result)
        
        return result
        
    except Exception as e:
        print(f"获取个股南向资金数据失败 {stock_code}: {e}")
        import traceback
        traceback.print_exc()
        return []

def update_southbound_data():
    """更新南向资金数据到数据库"""
    try:
        init_db()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. 更新整体流向数据
        overall_data = get_southbound_overall_history(days=90)
        for item in overall_data:
            cursor.execute('''
                INSERT OR REPLACE INTO southbound_overall 
                (date, net_inflow, buy_amount, sell_amount, cumulative_30d, cumulative_90d, update_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['date'], item['net_inflow'], item['buy_amount'], item['sell_amount'],
                item.get('cumulative_30d', 0), item.get('cumulative_90d', 0),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ))
        
        conn.commit()
        conn.close()
        
        print(f"[南向资金] 已更新 {len(overall_data)} 条整体流向数据")
        return True
    except Exception as e:
        print(f"更新南向资金数据失败: {e}")
        return False

def get_southbound_overall_from_db(days: int = 90) -> List[Dict]:
    """从数据库获取南向资金整体流向"""
    try:
        if not os.path.exists(DB_PATH):
            # 数据库不存在，先更新数据
            update_southbound_data()
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT date, net_inflow, buy_amount, sell_amount, cumulative_30d, cumulative_90d
            FROM southbound_overall
            ORDER BY date DESC
            LIMIT ?
        ''', (days,))
        
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in reversed(rows):  # 反转，按日期升序
            result.append({
                'date': row[0],
                'net_inflow': row[1],
                'buy_amount': row[2],
                'sell_amount': row[3],
                'cumulative_30d': row[4],
                'cumulative_90d': row[5]
            })
        
        return result
    except Exception as e:
        print(f"从数据库获取南向资金数据失败: {e}")
        return []

def get_southbound_signal() -> Dict:
    """
    获取南向资金买卖信号
    基于近30日净流入判断
    """
    try:
        data = get_southbound_overall_from_db(days=30)
        if len(data) == 0:
            return {'signal': '暂无数据', 'score': 50, 'reason': '无法获取南向资金数据'}
        
        # 计算近30日累计净流入
        total_inflow = sum(item['net_inflow'] for item in data)
        avg_daily = total_inflow / len(data)
        
        # 判断信号
        if total_inflow > 200:
            signal = '强烈买入'
            score = 80
            reason = f'近30日南向资金净流入{total_inflow:.0f}亿元，外资大幅增持港股'
        elif total_inflow > 100:
            signal = '买入'
            score = 65
            reason = f'近30日南向资金净流入{total_inflow:.0f}亿元，外资持续流入'
        elif total_inflow < -200:
            signal = '强烈卖出'
            score = 20
            reason = f'近30日南向资金净流出{abs(total_inflow):.0f}亿元，外资大幅减持'
        elif total_inflow < -100:
            signal = '卖出'
            score = 35
            reason = f'近30日南向资金净流出{abs(total_inflow):.0f}亿元，外资持续流出'
        else:
            signal = '中性'
            score = 50
            reason = f'近30日南向资金净流入{total_inflow:.0f}亿元，资金流向平稳'
        
        return {
            'signal': signal,
            'score': score,
            'reason': reason,
            'total_30d': round(total_inflow, 2),
            'avg_daily': round(avg_daily, 2),
            'days_count': len(data)
        }
    except Exception as e:
        print(f"获取南向资金信号失败: {e}")
        return {'signal': '错误', 'score': 50, 'reason': str(e)}

# 模块加载时初始化
_init_cache_db()
