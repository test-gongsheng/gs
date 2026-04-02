"""
预加载南向资金数据到缓存
运行方式: python3 preload_southbound_cache.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from utils.southbound_capital import get_southbound_stock_history

# 持仓港股列表
hk_stocks = ['00285', '00700', '09988']

def preload_all():
    print("=" * 50)
    print("预加载南向资金数据到缓存")
    print("=" * 50)
    
    for code in hk_stocks:
        print(f"\n正在加载 {code}...")
        try:
            data = get_southbound_stock_history(code, days=90)
            print(f"✅ {code} 加载完成，共 {len(data)} 条数据")
        except Exception as e:
            print(f"❌ {code} 加载失败: {e}")
    
    print("\n" + "=" * 50)
    print("预加载完成！现在访问这些港股将秒出数据。")
    print("=" * 50)

if __name__ == '__main__':
    preload_all()
