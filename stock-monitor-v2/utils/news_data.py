"""
实时新闻模块 - 财联社快讯
提供7×24小时财经新闻推送
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime, timedelta

# 新闻重要性判断关键词
IMPORTANT_KEYWORDS = [
    '央行', '美联储', '加息', '降息', '降准', '降息',
    '证监会', '监管', '政策', '重大', '突发',
    '涨停', '跌停', '大涨', '大跌', '暴跌', '暴涨',
    '业绩', '财报', '预增', '亏损', '盈利',
    '收购', '并购', '重组', '上市', '退市',
    '战争', '冲突', '制裁', '协议', '谈判'
]

# 板块关联关键词
SECTOR_KEYWORDS = {
    '半导体': ['芯片', '半导体', '集成电路', '光刻机', '中芯', '华为', 'AI芯片'],
    'AI人工智能': ['AI', '人工智能', '大模型', '算力', 'ChatGPT', 'OpenAI', '字节'],
    '黄金': ['黄金', '贵金属', '美联储', '加息', '降息'],
    '新能源': ['新能源', '光伏', '锂电', '储能', '宁德时代', '比亚迪', '风电'],
    '稀土': ['稀土', '永磁', '稀有金属'],
    '券商': ['券商', '证券', '投行', 'A股', '港股', 'IPO', '证监会']
}


def get_cls_news(limit: int = 20) -> List[Dict]:
    """
    获取财联社实时新闻
    """
    try:
        import akshare as ak
        news_df = ak.stock_info_global_cls()
        
        # 过滤有效新闻
        valid_news = news_df[news_df['标题'].str.len() > 5].head(limit)
        
        result = []
        for _, row in valid_news.iterrows():
            title = row['标题'].replace('财联社3月17日电，', '').replace('财联社电，', '')
            content = row['内容'] if pd.notna(row['内容']) else ''
            
            # 提取时间
            time_str = str(row['发布时间'])[:5] if row['发布时间'] else ''
            
            # 判断重要性
            importance = judge_importance(title + content)
            
            # 关联板块
            related_sectors = get_related_sectors(title + content)
            
            result.append({
                'time': time_str,
                'title': title,
                'content': content,
                'importance': importance,
                'importance_label': get_importance_label(importance),
                'related_sectors': related_sectors,
                'source': '财联社'
            })
        
        return result
    except Exception as e:
        print(f"获取财联社新闻失败: {e}")
        # 返回模拟数据
        return get_mock_news()


def judge_importance(text: str) -> int:
    """
    判断新闻重要性
    返回: 0=一般, 1=关注, 2=重要
    """
    text = text.lower()
    score = 0
    
    for keyword in IMPORTANT_KEYWORDS:
        if keyword in text:
            score += 1
    
    if score >= 3:
        return 2  # 重要
    elif score >= 1:
        return 1  # 关注
    return 0  # 一般


def get_importance_label(level: int) -> str:
    """获取重要性标签文字"""
    labels = {0: '一般', 1: '关注', 2: '重要'}
    return labels.get(level, '一般')


def get_related_sectors(text: str) -> List[str]:
    """获取关联板块"""
    text = text.lower()
    related = []
    
    for sector, keywords in SECTOR_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                related.append(sector)
                break
    
    return related[:2]  # 最多返回2个


def get_mock_news() -> List[Dict]:
    """模拟新闻数据（备用）"""
    return [
        {
            'time': '10:30',
            'title': '阿里巴巴财报超预期，云业务增长34%',
            'content': '阿里巴巴发布最新财报，云计算业务营收增长34%，超出市场预期。',
            'importance': 2,
            'importance_label': '重要',
            'related_sectors': ['AI人工智能'],
            'source': '财联社'
        },
        {
            'time': '10:15',
            'title': '美联储3月议息会议在即，黄金价格上涨',
            'content': '市场普遍预期美联储将维持利率不变，黄金价格小幅上涨。',
            'importance': 1,
            'importance_label': '关注',
            'related_sectors': ['黄金'],
            'source': '财联社'
        },
        {
            'time': '09:45',
            'title': '半导体板块资金净流入超50亿',
            'content': '北向资金今日大幅买入半导体板块，多只个股获机构加仓。',
            'importance': 1,
            'importance_label': '关注',
            'related_sectors': ['半导体'],
            'source': '财联社'
        },
        {
            'time': '09:30',
            'title': '港股通今日净流入港股25亿港元',
            'content': '港股通开盘半小时净流入25亿港元，科技股获资金追捧。',
            'importance': 0,
            'importance_label': '一般',
            'related_sectors': ['券商'],
            'source': '财联社'
        }
    ]


# 导入pandas用于数据处理
try:
    import pandas as pd
except:
    pd = None


if __name__ == '__main__':
    news = get_cls_news(10)
    for n in news[:5]:
        print(f"{n['time']} | {n['importance_label']} | {n['title'][:30]}...")
        if n['related_sectors']:
            print(f"    关联: {', '.join(n['related_sectors'])}")
