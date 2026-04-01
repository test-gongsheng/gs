"""
南向资金（港股通）数据模块
获取港股通整体资金流向和个股资金流向
"""
import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import akshare as ak
import pandas as pd

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'southbound.db')

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
    通过获取多日期的南向持股数据，筛选出特定股票的历史记录
    """
    try:
        from datetime import datetime, timedelta
        
        # 转换股票代码格式（去掉前导零）
        hk_code = stock_code.lstrip('0')
        if len(hk_code) < 4:
            hk_code = stock_code  # 保持原格式
        
        # 获取最近N个交易日的日期列表
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 30)  # 多取一些天数确保有足够交易日
        
        # 调用akshare获取南向持股数据（指定日期范围）
        df = ak.stock_hsgt_stock_statistics_em(
            symbol="南向持股",
            start_date=start_date.strftime('%Y%m%d'),
            end_date=end_date.strftime('%Y%m%d')
        )
        
        if df is None or len(df) == 0:
            return []
        
        # 筛选指定股票的数据
        # 股票代码需要匹配（可能带前导零）
        stock_data = df[df['股票代码'].astype(str).str.lstrip('0') == hk_code].copy()
        
        if len(stock_data) == 0:
            # 尝试直接匹配
            stock_data = df[df['股票代码'].astype(str) == stock_code].copy()
        
        if len(stock_data) == 0:
            return []
        
        # 按日期排序
        stock_data = stock_data.sort_values('持股日期', ascending=True)
        
        # 取最近N条
        stock_data = stock_data.tail(days)
        
        result = []
        prev_shares = None
        
        for _, row in stock_data.iterrows():
            date_str = row['持股日期']
            if isinstance(date_str, pd.Timestamp):
                date_str = date_str.strftime('%Y-%m-%d')
            
            hold_shares = float(row.get('持股数量', 0))
            hold_ratio = float(row.get('持股数量占发行股百分比', 0))
            
            # 计算持股变化（与前一日比较）
            hold_change = 0
            if prev_shares is not None:
                hold_change = hold_shares - prev_shares
            prev_shares = hold_shares
            
            # 估算净流入（简化计算：持股变化 × 当日收盘价 / 100000000）
            close_price = float(row.get('当日收盘价', 0))
            net_inflow = round(hold_change * close_price / 100000000, 2)  # 转换为亿港元
            
            result.append({
                'date': str(date_str),
                'stock_code': stock_code,
                'stock_name': row.get('股票简称', ''),
                'net_inflow': net_inflow,
                'hold_ratio': round(hold_ratio, 2),
                'hold_shares': round(hold_shares, 2),
                'hold_change': round(hold_change, 2),
                'close_price': close_price
            })
        
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
        
        if len(rows) < days:
            # 数据不足，重新获取
            update_southbound_data()
            return get_southbound_overall_history(days)
        
        result = []
        for row in reversed(rows):  # 按日期升序排列
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
        return get_southbound_overall_history(days)

def get_southbound_signal() -> Dict:
    """
    获取南向资金情绪信号
    """
    try:
        data = get_southbound_overall_from_db(days=30)
        if len(data) == 0:
            return {'signal': 'neutral', 'score': 50, 'reason': '暂无数据'}
        
        # 计算近30日累计净流入
        cumulative_30d = sum(d['net_inflow'] for d in data[-30:])
        
        # 计算近5日趋势
        recent_5d = sum(d['net_inflow'] for d in data[-5:])
        
        # 判断信号
        if cumulative_30d > 500:
            signal = '强烈看多'
            score = 80
        elif cumulative_30d > 200:
            signal = '看多'
            score = 65
        elif cumulative_30d < -100:
            signal = '看空'
            score = 35
        else:
            signal = '中性'
            score = 50
        
        return {
            'signal': signal,
            'score': score,
            'cumulative_30d': round(cumulative_30d, 2),
            'recent_5d': round(recent_5d, 2),
            'reason': f'近30日累计净流入{cumulative_30d:.1f}亿元'
        }
    except Exception as e:
        print(f"获取南向资金信号失败: {e}")
        return {'signal': 'neutral', 'score': 50, 'reason': '数据异常'}

if __name__ == '__main__':
    # 测试
    print("测试南向资金数据获取...")
    
    # 测试整体流向
    overall = get_southbound_overall_history(days=10)
    print(f"\n整体流向数据（最近10天）:")
    for item in overall[-5:]:
        print(f"  {item['date']}: 净买入{item['net_inflow']}亿元")
    
    # 测试信号
    signal = get_southbound_signal()
    print(f"\n情绪信号: {signal}")
