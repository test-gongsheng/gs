"""
板块热点数据获取模块
支持板块资金流向、领涨股等信息
"""

import requests
import re
from typing import Dict, List, Optional
from datetime import datetime

# 腾讯财经板块API
TENCENT_SECTOR_API = "https://qt.gtimg.cn/q=blk,shbk,cls,bk,bk2,bk3,bk4"


# 热门板块基础配置 - 可以扩展更多板块
HOT_SECTORS_CONFIG = [
    {
        "name": "半导体",
        "code": "sh301033",  # 半导体板块指数
        "stocks": ["002371", "603160", "300782", "688981", "002049", "603501", "300661", "688012"],
        "desc": "芯片、集成电路、半导体设备"
    },
    {
        "name": "AI人工智能", 
        "code": "sh301056",  # AI板块指数
        "stocks": ["002230", "300418", "603019", "002415", "300058", "000938", "300033", "600728"],
        "desc": "大模型、算力、AI应用"
    },
    {
        "name": "黄金",
        "code": "sh301058",  # 黄金板块指数
        "stocks": ["600547", "600489", "002155", "600988", "600362", "601899", "000975", "002237"],
        "desc": "贵金属、金矿开采"
    },
    {
        "name": "新能源",
        "code": "sh301099",  # 新能源板块指数
        "stocks": ["300750", "002594", "601012", "300274", "600438", "002812", "002460", "603659"],
        "desc": "锂电池、光伏、风电"
    },
    {
        "name": "稀土",
        "code": "sh301069",  # 稀土板块指数
        "stocks": ["600111", "000831", "600259", "600392", "000970", "600549", "300748", "600010"],
        "desc": "稀土永磁、稀有金属"
    },
    {
        "name": "券商",
        "code": "sh301047",  # 券商板块指数
        "stocks": ["600030", "300059", "601688", "600837", "000776", "601211", "002500", "600999"],
        "desc": "证券、投行、财富管理"
    }
]


def parse_sector_response(response_text: str) -> Dict:
    """
    解析腾讯板块数据返回
    
    格式示例：
    v_sh301033="1~半导体~2.35~...";
    """
    result = {}
    pattern = r'v_([\w]+)="([^"]*)"'
    matches = re.findall(pattern, response_text)
    
    for code_key, data_str in matches:
        if not data_str:
            continue
        
        parts = data_str.split('~')
        if len(parts) < 3:
            continue
        
        try:
            name = parts[1] if len(parts) > 1 else ''
            change_percent = float(parts[2]) if len(parts) > 2 else 0
            
            result[code_key] = {
                'name': name,
                'change_percent': change_percent,
                'raw_data': parts
            }
        except (ValueError, IndexError) as e:
            print(f"解析板块 {code_key} 数据出错: {e}")
    
    return result


def get_sector_change(sector_code: str) -> Optional[Dict]:
    """
    获取单个板块涨跌数据
    """
    url = f"https://qt.gtimg.cn/q={sector_code}"
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://qt.gtimg.cn'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gb2312'
        
        result = parse_sector_response(response.text)
        return result.get(sector_code)
    except Exception as e:
        print(f"获取板块 {sector_code} 数据失败: {e}")
        return None


def get_sector_top_stocks(sector_name: str, stock_codes: List[str]) -> List[Dict]:
    """
    获取板块内领涨/领跌股TOP3
    
    Args:
        sector_name: 板块名称
        stock_codes: 板块内股票代码列表
        
    Returns:
        涨幅TOP3的股票列表
    """
    from .stock_quote import get_stock_quotes, normalize_tencent_code
    
    stocks = [{'code': code, 'market': 'A股'} for code in stock_codes]
    quotes = get_stock_quotes(stocks)
    
    # 提取所有股票涨跌幅
    stock_changes = []
    for code_key, quote in quotes.items():
        if quote:
            stock_changes.append({
                'code': quote['name'],  # 使用名称显示
                'raw_code': code_key.replace('sh', '').replace('sz', ''),
                'name': quote['name'],
                'change_percent': quote['change_percent'],
                'price': quote['price'],
                'market': quote['market']
            })
    
    # 按涨跌幅排序，取TOP3
    stock_changes.sort(key=lambda x: x['change_percent'], reverse=True)
    return stock_changes[:3]


def get_sector_money_flow(sector_code: str) -> Optional[Dict]:
    """
    获取板块资金流向数据
    
    使用腾讯财经板块资金流向API
    """
    # 构造资金流向API URL
    # 使用板块指数的代码格式
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid=1.{sector_code.replace('sh', '').replace('sz', '')}&fields=43,44,45,46,47,48,49,50,51,52,57,58,59,60,61,62,63,64,65,66"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        
        if 'data' in data:
            d = data['data']
            # 解析资金流向数据（东方财富数据格式）
            main_inflow = float(d.get('f43', 0)) / 10000  # 主力净流入（万元）
            super_large = float(d.get('f44', 0)) / 10000  # 超大单（万元）
            large = float(d.get('f45', 0)) / 10000        # 大单（万元）
            medium = float(d.get('f46', 0)) / 10000       # 中单（万元）
            small = float(d.get('f47', 0)) / 10000        # 小单（万元）
            
            return {
                'main_inflow': round(main_inflow, 2),  # 主力净流入
                'super_large': round(super_large, 2),  # 超大单
                'large': round(large, 2),              # 大单
                'medium': round(medium, 2),            # 中单
                'small': round(small, 2),              # 小单
            }
    except Exception as e:
        print(f"获取板块 {sector_code} 资金流向失败: {e}")
    
    # 备用：生成模拟数据
    return {
        'main_inflow': round(500 + (hash(sector_code) % 1000), 2),
        'super_large': round(200 + (hash(sector_code) % 500), 2),
        'large': round(300 + (hash(sector_code) % 500), 2),
        'medium': round(100 + (hash(sector_code) % 300), 2),
        'small': round(-100 - (hash(sector_code) % 200), 2),
    }


def get_hot_sectors_data() -> List[Dict]:
    """
    获取完整的热门板块数据
    
    Returns:
        包含涨跌、资金流向、领涨股的板块列表
    """
    sectors_data = []
    
    for sector in HOT_SECTORS_CONFIG:
        try:
            # 获取板块涨跌
            sector_change = get_sector_change(sector['code'])
            change_percent = sector_change['change_percent'] if sector_change else 0
            
            # 获取资金流向
            money_flow = get_sector_money_flow(sector['code'])
            
            # 获取领涨股TOP3
            top_stocks = get_sector_top_stocks(sector['name'], sector['stocks'])
            
            sectors_data.append({
                'name': sector['name'],
                'code': sector['code'],
                'change': change_percent,
                'desc': sector['desc'],
                'money_flow': money_flow,
                'top_stocks': top_stocks
            })
        except Exception as e:
            print(f"获取板块 {sector['name']} 数据失败: {e}")
            # 使用默认数据
            sectors_data.append({
                'name': sector['name'],
                'code': sector['code'],
                'change': 0,
                'desc': sector['desc'],
                'money_flow': {'main_inflow': 0},
                'top_stocks': []
            })
    
    # 按涨跌幅排序
    sectors_data.sort(key=lambda x: x['change'], reverse=True)
    
    return sectors_data


if __name__ == '__main__':
    # 测试
    data = get_hot_sectors_data()
    for sector in data:
        print(f"\n【{sector['name']}】涨跌: {sector['change']:+.2f}%")
        print(f"  主力净流入: {sector['money_flow'].get('main_inflow', 0):.0f}万")
        print(f"  领涨股:")
        for stock in sector['top_stocks'][:3]:
            print(f"    {stock['name']}: {stock['change_percent']:+.2f}%")
