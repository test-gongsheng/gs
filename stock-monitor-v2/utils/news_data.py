"""
实时新闻模块 - 财联社快讯 (结构化版)
提供：头条、题材推荐、热闹板块、投资日历、持仓相关
"""

import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json

# 用户持仓相关板块（动态获取）
# 在初始化时会从用户持仓中提取
USER_PORTFOLIO_SECTORS = []

def set_user_portfolio_sectors(sectors: List[str]):
    """设置用户持仓相关板块"""
    global USER_PORTFOLIO_SECTORS
    USER_PORTFOLIO_SECTORS = sectors
    print(f"[新闻模块] 用户持仓板块: {sectors}")

# 投资日历事件（重要财经事件）
INVESTMENT_CALENDAR = [
    # 格式: (日期, 时间, 事件标题, 重要性, 影响板块)
    ("2026-03-17", "10:00", "中国2月工业增加值数据", 2, ["宏观", "周期"]),
    ("2026-03-17", "15:30", "美联储利率决议", 3, ["黄金", "券商", "宏观"]),
    ("2026-03-18", "09:30", "中国LPR报价", 2, ["房地产", "银行"]),
    ("2026-03-20", "20:30", "美国非农就业数据", 2, ["黄金", "宏观"]),
]

# 热门题材/主题映射
THEME_KEYWORDS = {
    '算力': ['算力', 'AI芯片', '服务器', '数据中心', '液冷', 'CPO', '光模块'],
    '机器人': ['机器人', '人形机器人', '减速器', '丝杠', '灵巧手'],
    '低空经济': ['低空经济', '飞行汽车', 'eVTOL', '无人机', '通用航空'],
    '固态电池': ['固态电池', '半固态电池', '电解质', '锂电新技术'],
    '智能驾驶': ['智能驾驶', '自动驾驶', '激光雷达', '车载芯片', '智能座舱'],
    '国企改革': ['国企改革', '央企重组', '国资注入', '混合所有制'],
    '跨境电商': ['跨境电商', '出海', '外贸', '一带一路'],
    '光刻机': ['光刻机', '光刻胶', '半导体设备', '国产替代'],
    '减肥药': ['减肥药', 'GLP-1', '司美格鲁肽', '创新药'],
    '短剧': ['短剧', '微短剧', '影视', '内容创作'],
}

# 头条关键词（重大事件）
HEADLINE_KEYWORDS = [
    '央行', '证监会', '银保监会', '金融监管总局',
    '美联储', '加息', '降息', '降准', '量化宽松',
    '国常会', '政治局', '中央经济工作会议',
    '中美', '贸易战', '关税', '制裁',
    '暴涨', '暴跌', '涨停', '跌停', '千股',
    '熔断', '崩盘', '救市', '停牌', '退市',
    '重大', '突发', '紧急', '震惊', '重磅',
]

# 板块关联关键词
SECTOR_KEYWORDS = {
    '半导体': ['芯片', '半导体', '集成电路', '光刻机', '中芯', '华为芯片', 'AI芯片', '存储芯片', '晶圆'],
    'AI人工智能': ['AI', '人工智能', '大模型', '算力', 'ChatGPT', 'OpenAI', 'DeepSeek', '字节', '阿里云'],
    '黄金': ['黄金', '贵金属', '美联储', '加息', '降息', '美元指数', '通胀'],
    '新能源': ['新能源', '光伏', '锂电', '储能', '宁德时代', '比亚迪', '风电', '氢能源'],
    '稀土': ['稀土', '永磁', '稀有金属', '钨', '锑', '镓', '锗'],
    '券商': ['券商', '证券', '投行', 'A股', '港股', 'IPO', '证监会', '交易所'],
    '医药': ['医药', '创新药', 'CXO', '医疗器械', '医保', '集采'],
    '地产': ['房地产', '地产', '楼市', '房价', 'LPR', '房贷利率'],
    '银行': ['银行', '银行业', '净息差', '不良贷款', '降准'],
    '军工': ['军工', '国防', '武器装备', '航空航天', '航母'],
}


def classify_news(text: str) -> Tuple[str, int, List[str]]:
    """
    分类新闻
    返回: (分类, 重要性, 关联板块列表)
    """
    text = text.lower()
    
    # 1. 检查是否为头条
    headline_score = 0
    for keyword in HEADLINE_KEYWORDS:
        if keyword in text:
            headline_score += 1
    
    if headline_score >= 1:
        category = "头条"
        importance = 3 if headline_score >= 2 else 2
    else:
        category = "快讯"
        importance = 0
    
    # 2. 检查关联题材
    related_themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                related_themes.append(theme)
                if category == "快讯":
                    category = "题材"
                    importance = max(importance, 1)
                break
    
    # 3. 检查关联板块
    related_sectors = []
    for sector, keywords in SECTOR_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                related_sectors.append(sector)
                break
    
    # 4. 计算与用户持仓的关联度
    relevance_score = 0
    for sector in USER_PORTFOLIO_SECTORS:
        if sector in related_sectors:
            relevance_score += 1
            importance += 1  # 持仓相关提升重要性
    
    # 限制重要性范围
    importance = min(3, max(0, importance))
    
    return category, importance, related_sectors


def get_today_calendar() -> List[Dict]:
    """获取今日投资日历"""
    today = datetime.now().strftime("%Y-%m-%d")
    result = []
    
    for date, time, event, importance, sectors in INVESTMENT_CALENDAR:
        if date == today:
            result.append({
                'time': time,
                'title': event,
                'importance': importance,
                'importance_label': '重要' if importance >= 2 else '一般',
                'related_sectors': sectors,
                'type': 'calendar'
            })
    
    return result


def get_hot_themes() -> List[Dict]:
    """获取热门题材（基于当前新闻聚合）"""
    # 实际应该通过API获取，这里返回预设的热门题材
    return [
        {'name': '算力', 'heat': 95, 'change': 3.2, 'stocks': ['中际旭创', '工业富联', '寒武纪']},
        {'name': '机器人', 'heat': 88, 'change': 2.8, 'stocks': ['埃斯顿', '绿的谐波', '三花智控']},
        {'name': '低空经济', 'heat': 82, 'change': 1.9, 'stocks': ['万丰奥威', '中信海直', '宗申动力']},
        {'name': '固态电池', 'heat': 75, 'change': 1.5, 'stocks': ['宁德时代', '比亚迪', '亿纬锂能']},
    ]


def get_cls_structured_news(limit: int = 30, portfolio_sectors: List[str] = None) -> Dict:
    """
    获取结构化的财联社新闻
    返回: {
        'headlines': [...],  # 头条
        'themes': [...],     # 题材相关
        'calendar': [...],   # 投资日历
        'portfolio': [...],  # 持仓相关
        'general': [...],    # 普通快讯
    }
    """
    if portfolio_sectors:
        set_user_portfolio_sectors(portfolio_sectors)
    
    try:
        import akshare as ak
        news_df = ak.stock_info_global_cls()
        
        # 过滤有效新闻
        valid_news = news_df[news_df['标题'].str.len() > 5].head(limit)
        
        headlines = []
        themes = []
        portfolio_related = []
        general = []
        
        for _, row in valid_news.iterrows():
            title = row['标题'].replace('财联社3月17日电，', '').replace('财联社电，', '')
            content = row['内容'] if '内容' in row and pd.notna(row['内容']) else ''
            
            # 提取时间
            time_str = str(row['发布时间'])[:5] if '发布时间' in row and row['发布时间'] else ''
            
            # 分类新闻
            category, importance, related_sectors = classify_news(title + content)
            
            news_item = {
                'time': time_str,
                'title': title,
                'content': content,
                'category': category,
                'importance': importance,
                'importance_label': {3: '重磅', 2: '重要', 1: '关注', 0: '一般'}.get(importance, '一般'),
                'related_sectors': related_sectors,
                'source': '财联社'
            }
            
            # 根据分类放入不同列表
            if category == "头条":
                headlines.append(news_item)
            elif category == "题材":
                themes.append(news_item)
            elif any(s in USER_PORTFOLIO_SECTORS for s in related_sectors):
                portfolio_related.append(news_item)
            else:
                general.append(news_item)
        
        # 获取投资日历
        calendar = get_today_calendar()
        
        # 获取热门题材
        hot_themes = get_hot_themes()
        
        return {
            'success': True,
            'headlines': headlines[:5],      # 最多5条头条
            'themes': themes[:8],             # 最多8条题材
            'hot_themes': hot_themes,         # 热门题材列表
            'calendar': calendar,             # 今日投资日历
            'portfolio': portfolio_related[:5],  # 持仓相关
            'general': general[:10],          # 普通快讯
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
    except Exception as e:
        print(f"获取财联社新闻失败: {e}")
        return {
            'success': False,
            'headlines': [],
            'themes': [],
            'hot_themes': [],
            'calendar': [],
            'portfolio': [],
            'general': [],
            'error': str(e)
        }


# 导入pandas用于数据处理
try:
    import pandas as pd
except:
    pd = None


if __name__ == '__main__':
    # 测试 - 假设用户持仓包含半导体和AI
    result = get_cls_structured_news(limit=20, portfolio_sectors=['半导体', 'AI人工智能'])
    
    print(f"=== 头条 ({len(result['headlines'])}条) ===")
    for n in result['headlines'][:3]:
        print(f"{n['time']} [{n['importance_label']}] {n['title'][:40]}...")
    
    print(f"\n=== 题材 ({len(result['themes'])}条) ===")
    for n in result['themes'][:3]:
        print(f"{n['time']} [{n['importance_label']}] {n['title'][:40]}...")
        if n['related_sectors']:
            print(f"    板块: {', '.join(n['related_sectors'])}")
    
    print(f"\n=== 投资日历 ({len(result['calendar'])}条) ===")
    for c in result['calendar']:
        print(f"{c['time']} [{c['importance_label']}] {c['title']}")
    
    print(f"\n=== 持仓相关 ({len(result['portfolio'])}条) ===")
    for n in result['portfolio'][:3]:
        print(f"{n['time']} [{n['importance_label']}] {n['title'][:40]}...")
