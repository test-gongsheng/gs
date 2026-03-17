"""
板块热点数据获取模块 - 真实实时数据版
使用腾讯财经API获取实时行情
"""

import requests
import re
from typing import Dict, List, Optional
from datetime import datetime

# 热门板块配置
HOT_SECTORS_CONFIG = [
    {
        "name": "半导体",
        "stocks": ["002371", "603160", "300782", "688981", "002049", "603501", "300661", "688012"],
        "desc": "芯片、集成电路、半导体设备"
    },
    {
        "name": "AI人工智能", 
        "stocks": ["002230", "300418", "603019", "002415", "300058", "000938", "300033", "600728"],
        "desc": "大模型、算力、AI应用"
    },
    {
        "name": "黄金",
        "stocks": ["600547", "600489", "002155", "600988", "600362", "601899", "000975", "002237"],
        "desc": "贵金属、金矿开采"
    },
    {
        "name": "新能源",
        "stocks": ["300750", "002594", "601012", "300274", "600438", "002812", "002460", "603659"],
        "desc": "锂电池、光伏、风电"
    },
    {
        "name": "稀土",
        "stocks": ["600111", "000831", "600259", "600392", "000970", "600549", "300748", "600010"],
        "desc": "稀土永磁、稀有金属"
    },
    {
        "name": "券商",
        "stocks": ["600030", "300059", "601688", "600837", "000776", "601211", "002500", "600999"],
        "desc": "证券、投行、财富管理"
    }
]


def normalize_tencent_code(code: str) -> str:
    """转换为腾讯代码格式"""
    code = code.strip()
    if code.startswith(('sh', 'sz', 'hk')):
        return code
    if code.startswith(('60', '688', '900')):
        return f"sh{code}"
    return f"sz{code}"


def get_realtime_quotes(codes: List[str]) -> Dict:
    """
    获取实时行情数据（腾讯财经）
    """
    if not codes:
        return {}
    
    tencent_codes = [normalize_tencent_code(c) for c in codes]
    codes_str = ','.join(tencent_codes)
    url = f"http://qt.gtimg.cn/q={codes_str}"
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'http://qt.gtimg.cn'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gb2312'
        
        result = {}
        pattern = r'v_([\w]+)="([^"]*)"'
        matches = re.findall(pattern, response.text)
        
        for code_key, data_str in matches:
            if not data_str:
                continue
            
            parts = data_str.split('~')
            if len(parts) < 35:
                continue
            
            try:
                name = parts[1]
                price = float(parts[3]) if parts[3] else 0
                prev_close = float(parts[4]) if parts[4] else 0
                change = float(parts[31]) if len(parts) > 31 and parts[31] else 0
                change_percent = float(parts[32]) if len(parts) > 32 and parts[32] else 0
                volume = int(float(parts[36])) if len(parts) > 36 and parts[36] else 0
                
                result[code_key] = {
                    'name': name,
                    'price': price,
                    'prev_close': prev_close,
                    'change': change,
                    'change_percent': change_percent,
                    'volume': volume
                }
            except Exception as e:
                print(f"解析 {code_key} 出错: {e}")
        
        return result
    except Exception as e:
        print(f"获取行情失败: {e}")
        return {}


def get_sector_detail_data(sector_name: str, stock_codes: List[str]) -> Dict:
    """
    获取板块详细数据（真实实时）
    """
    quotes = get_realtime_quotes(stock_codes)
    
    stock_details = []
    limit_up_count = 0
    limit_down_count = 0
    up_count = 0
    down_count = 0
    flat_count = 0
    total_volume = 0
    
    changes = []
    total_market_value = 0
    
    for code_key, quote in quotes.items():
        change_pct = quote['change_percent']
        changes.append(change_pct)
        
        stock_details.append({
            'code': code_key.replace('sh', '').replace('sz', ''),
            'name': quote['name'],
            'change_percent': change_pct,
            'price': quote['price'],
            'volume': quote['volume']
        })
        
        # 统计
        if change_pct > 9.5:
            limit_up_count += 1
            up_count += 1
        elif change_pct < -9.5:
            limit_down_count += 1
            down_count += 1
        elif change_pct > 0:
            up_count += 1
        elif change_pct < 0:
            down_count += 1
        else:
            flat_count += 1
        
        total_volume += quote['volume']
    
    total_stocks = len(stock_details)
    up_ratio = (up_count / total_stocks * 100) if total_stocks > 0 else 0
    avg_change = sum(changes) / len(changes) if changes else 0
    
    # 板块整体涨跌幅 = 成分股平均涨跌幅
    sector_change = avg_change
    
    # 按涨跌幅排序取TOP3
    stock_details.sort(key=lambda x: x['change_percent'], reverse=True)
    top_stocks = stock_details[:3]
    
    return {
        'sector_change': round(sector_change, 2),
        'stock_details': stock_details,
        'top_stocks': top_stocks,
        'limit_up_count': limit_up_count,
        'limit_down_count': limit_down_count,
        'up_count': up_count,
        'down_count': down_count,
        'flat_count': flat_count,
        'total_stocks': total_stocks,
        'up_ratio': round(up_ratio, 1),
        'avg_change': round(avg_change, 2),
        'total_volume': total_volume
    }


def estimate_money_flow(sector_data: Dict) -> Dict:
    """
    根据成交量和涨跌幅估算资金流向
    """
    avg_change = sector_data.get('avg_change', 0)
    total_volume = sector_data.get('total_volume', 0)
    up_ratio = sector_data.get('up_ratio', 0)
    
    # 基于涨跌和成交量估算资金（万元）
    base_amount = total_volume * 0.01  # 假设均价10元，转化为万元
    
    if avg_change > 3:
        multiplier = 2.5
    elif avg_change > 1:
        multiplier = 1.5
    elif avg_change > 0:
        multiplier = 0.8
    elif avg_change > -1:
        multiplier = -0.5
    elif avg_change > -3:
        multiplier = -1.5
    else:
        multiplier = -2.5
    
    main_inflow = base_amount * multiplier
    
    # 细分资金（估算）
    institutional = main_inflow * 0.7  # 机构占70%
    retail = main_inflow * 0.3         # 散户占30%
    
    return {
        'main_inflow': round(main_inflow, 2),
        'institutional': round(institutional, 2),
        'retail': round(retail, 2),
        'super_large': round(institutional * 0.6, 2),
        'large': round(institutional * 0.4, 2),
        'medium': round(retail * 0.6, 2),
        'small': round(retail * 0.4, 2),
    }


def calculate_sentiment(sector_data: Dict, money_flow: Dict) -> Dict:
    """计算情绪得分"""
    change = sector_data.get('sector_change', 0)
    up_ratio = sector_data.get('up_ratio', 0)
    limit_up = sector_data.get('limit_up_count', 0)
    main_inflow = money_flow.get('main_inflow', 0)
    
    # 各项得分
    change_score = min(max(change * 5, -30), 30)
    up_ratio_score = (up_ratio - 50) * 0.4
    limit_up_score = limit_up * 3
    money_score = min(max(main_inflow / 500, -20), 20)
    
    total = 50 + change_score + up_ratio_score + limit_up_score + money_score
    score = max(0, min(100, total))
    
    if score >= 80:
        label, cls = '极度乐观', 'extreme-bull'
    elif score >= 60:
        label, cls = '乐观', 'bull'
    elif score >= 40:
        label, cls = '中性', 'neutral'
    elif score >= 20:
        label, cls = '谨慎', 'bear'
    else:
        label, cls = '恐慌', 'extreme-bear'
    
    return {
        'score': round(score, 0),
        'sentiment': label,
        'sentiment_class': cls
    }


def get_signals(sector_data: Dict, money_flow: Dict) -> Dict:
    """获取技术信号"""
    change = sector_data.get('sector_change', 0)
    up_ratio = sector_data.get('up_ratio', 0)
    limit_up = sector_data.get('limit_up_count', 0)
    main_inflow = money_flow.get('main_inflow', 0)
    
    signals = []
    
    if main_inflow > 1000:
        signals.append({'type': 'buy', 'text': '主力大幅流入'})
    elif main_inflow > 0:
        signals.append({'type': 'buy', 'text': '资金净流入'})
    elif main_inflow < -500:
        signals.append({'type': 'sell', 'text': '资金净流出'})
    
    if change > 4:
        signals.append({'type': 'strong', 'text': '强势上涨'})
    elif change > 2:
        signals.append({'type': 'buy', 'text': '量价齐升'})
    elif change < -2:
        signals.append({'type': 'sell', 'text': '回调风险'})
    
    if limit_up >= 2:
        signals.append({'type': 'strong', 'text': f'{limit_up}股涨停'})
    
    if up_ratio >= 70:
        signals.append({'type': 'buy', 'text': '板块普涨'})
    elif up_ratio <= 30:
        signals.append({'type': 'sell', 'text': '板块走弱'})
    
    return {
        'signals': signals,
        'signal_count': len(signals),
        'main_signal': signals[0] if signals else {'type': 'neutral', 'text': '震荡'}
    }


def get_news_tags(sector_name: str) -> List[str]:
    """新闻标签"""
    tags = {
        '半导体': ['国产替代', '周期见底'],
        'AI人工智能': ['大模型', '算力'],
        '黄金': ['降息预期', '避险'],
        '新能源': ['碳中和', '出海'],
        '稀土': ['战略资源', '出口管制'],
        '券商': ['资本市场改革', '并购']
    }
    return tags.get(sector_name, ['政策驱动'])


def get_hot_sectors_data() -> List[Dict]:
    """
    获取完整热门板块数据（真实实时）
    """
    sectors_data = []
    
    # 获取所有板块数据
    for sector in HOT_SECTORS_CONFIG:
        try:
            # 获取板块详细数据
            detail = get_sector_detail_data(sector['name'], sector['stocks'])
            
            # 估算资金流向
            money_flow = estimate_money_flow(detail)
            
            # 情绪得分
            sentiment = calculate_sentiment(detail, money_flow)
            
            # 技术信号
            technical = get_signals(detail, money_flow)
            
            sectors_data.append({
                'name': sector['name'],
                'desc': sector['desc'],
                'change': detail['sector_change'],
                'rank': 0,  # 稍后计算
                'money_flow': money_flow,
                'limit_up_count': detail['limit_up_count'],
                'limit_down_count': detail['limit_down_count'],
                'up_count': detail['up_count'],
                'down_count': detail['down_count'],
                'total_stocks': detail['total_stocks'],
                'up_ratio': detail['up_ratio'],
                'avg_change': detail['avg_change'],
                'top_stocks': detail['top_stocks'],
                'sentiment': sentiment,
                'technical': technical,
                'news_tags': get_news_tags(sector['name'])
            })
        except Exception as e:
            print(f"获取板块 {sector['name']} 失败: {e}")
    
    # 按涨跌幅排序，计算排名
    sectors_data.sort(key=lambda x: x['change'], reverse=True)
    for i, sector in enumerate(sectors_data):
        sector['rank'] = i + 1
    
    return sectors_data


if __name__ == '__main__':
    data = get_hot_sectors_data()
    for s in data:
        print(f"\n{s['rank']}. {s['name']} {s['change']:+.2f}%")
        print(f"   主力: {s['money_flow']['main_inflow']:+.0f}万 | 上涨: {s['up_ratio']:.0f}% | 涨停: {s['limit_up_count']}家")
        print(f"   情绪: {s['sentiment']['sentiment']} ({s['sentiment']['score']})")
        top_stocks_str = ', '.join([f"{st['name']} {st['change_percent']:+.1f}%" for st in s['top_stocks']])
        print(f"   领涨: {top_stocks_str}")
