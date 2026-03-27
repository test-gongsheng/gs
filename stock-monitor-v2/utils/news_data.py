"""
实时新闻模块 - 财联社快讯 (结构化版) + LLM情绪分析
提供：头条、题材推荐、热闹板块、投资日历、持仓相关、情绪分析
"""

import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json
import hashlib
import os

# ============ 缓存配置 ============
CACHE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

# 情绪缓存: {hash: {sentiment, score, timestamp}}
_sentiment_cache = {}
CACHE_TTL_HOURS = 24  # 缓存24小时

# 用户持仓相关板块（动态获取）
USER_PORTFOLIO_SECTORS = []

def set_user_portfolio_sectors(sectors: List[str]):
    """设置用户持仓相关板块"""
    global USER_PORTFOLIO_SECTORS
    USER_PORTFOLIO_SECTORS = sectors
    print(f"[新闻模块] 用户持仓板块: {sectors}")

# ============ LLM 情绪分析 ============

def _get_cache_key(text: str) -> str:
    """生成文本的缓存key"""
    return hashlib.md5(text.encode()).hexdigest()[:12]

def _get_cached_sentiment(cache_key: str) -> Optional[Dict]:
    """从缓存获取情绪分析结果"""
    if cache_key in _sentiment_cache:
        data = _sentiment_cache[cache_key]
        # 检查是否过期
        if datetime.now() - data['timestamp'] < timedelta(hours=CACHE_TTL_HOURS):
            return data
    return None

def _cache_sentiment(cache_key: str, result: Dict):
    """缓存情绪分析结果"""
    _sentiment_cache[cache_key] = {
        **result,
        'timestamp': datetime.now()
    }

def analyze_sentiment_llm(title: str, content: str = "") -> Dict:
    """
    使用LLM分析新闻情绪
    返回: {'sentiment': 'positive'|'neutral'|'negative', 'score': 0-100, 'label': '标签'}
    """
    text = f"{title} {content}".strip()
    cache_key = _get_cache_key(text)
    
    # 检查缓存
    cached = _get_cached_sentiment(cache_key)
    if cached:
        return {k: v for k, v in cached.items() if k != 'timestamp'}
    
    # 构建提示词
    prompt = f"""分析以下财经新闻的情绪倾向，从投资者角度判断是利好还是利空。

新闻：{title}
内容：{content[:200] if content else '无'}

请严格按以下JSON格式返回（不要其他内容）：
{{
  "sentiment": "positive" | "neutral" | "negative",
  "score": 0-100的整数（50为中性，越高越积极）,
  "label": "用2-4个字概括，如：利好、利空、中性、关注、警示、机会、风险"
}}
"""
    
    try:
        # 调用 Kimi API (OpenClaw 环境内置)
        response = requests.post(
            'http://localhost:8000/v1/chat/completions',
            json={
                "model": "kimi-coding/k2p5",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 150
            },
            timeout=5
        )
        
        if response.status_code == 200:
            result_text = response.json()['choices'][0]['message']['content']
            # 提取JSON
            import re
            json_match = re.search(r'\{[^}]+\}', result_text)
            if json_match:
                result = json.loads(json_match.group())
                _cache_sentiment(cache_key, result)
                return result
    except Exception as e:
        print(f"[情绪分析] LLM失败: {e}")
    
    # 降级：规则匹配
    return _analyze_sentiment_rule(title)

def _analyze_sentiment_rule(text: str) -> Dict:
    """规则匹配情绪分析（降级方案）"""
    text = text.lower()
    
    positive = ['利好', '大涨', '涨停', '突破', '创新高', '超预期', '业绩大增', '增长', '盈利', '签约', '订单', '获批']
    negative = ['利空', '大跌', '跌停', '暴跌', '业绩下滑', '亏损', '减持', '监管', '调查', '处罚', '暴雷', '风险']
    
    score = 50
    for w in positive:
        if w in text: score += 10
    for w in negative:
        if w in text: score -= 10
    
    score = max(0, min(100, score))
    
    if score >= 60:
        return {'sentiment': 'positive', 'score': score, 'label': '利好'}
    elif score <= 40:
        return {'sentiment': 'negative', 'score': score, 'label': '利空'}
    else:
        return {'sentiment': 'neutral', 'score': score, 'label': '中性'}

def batch_analyze_sentiment(news_list: List[Dict], max_batch: int = 10) -> List[Dict]:
    """批量分析新闻情绪（限制数量控制成本）"""
    results = []
    for news in news_list[:max_batch]:
        sentiment = analyze_sentiment_llm(news['title'], news.get('content', ''))
        news['sentiment'] = sentiment['sentiment']
        news['sentiment_score'] = sentiment['score']
        news['sentiment_label'] = sentiment['label']
        results.append(news)
    # 剩余的直接标记为中性
    for news in news_list[max_batch:]:
        news['sentiment'] = 'neutral'
        news['sentiment_score'] = 50
        news['sentiment_label'] = '未分析'
        results.append(news)
    return results

# ============ 热门题材/主题映射 ============
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

# 投资日历 - 从财联社新闻中提取重大事件
# 重大事件关键词
CALENDAR_EVENT_KEYWORDS = [
    # 央行/货币政策
    '利率决议', '美联储加息', '美联储降息', '央行降准', '央行降息', 'LPR', 
    # 经济数据
    'GDP', 'CPI', 'PPI', 'PMI', '非农就业', '失业率', '工业增加值',
    # 政策会议
    '国常会', '政治局会议', '中央经济工作会议', '两会', '政府工作报告',
    # 国际事件
    'G20', 'APEC', '中美贸易', '关税', '制裁',
    # 公司重大事件
    '财报', '年报', '季报', '业绩预告', '分红', '派息', '除权除息',
]

def extract_calendar_events_from_news(news_list: List[Dict], portfolio_sectors: List[str]) -> List[Dict]:
    """
    从财联社新闻中提取投资日历事件
    只返回与持仓板块相关或重大事件
    """
    calendar = []
    
    # 重大事件基础关键词
    major_keywords = ['美联储', '央行', '利率决议', 'GDP', 'CPI', 'PPI', '非农就业', 
                      '国常会', '政治局', '两会', '关税', '制裁', '贸易战']
    
    for news in news_list:
        title = news.get('title', '')
        content = news.get('content', '')
        text = f"{title} {content}"
        
        # 检查是否是重大事件
        is_major = any(kw in text for kw in major_keywords)
        
        # 检查是否与持仓板块相关
        related_sectors = []
        for sector, keywords in SECTOR_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                related_sectors.append(sector)
        
        is_portfolio_related = any(s in portfolio_sectors for s in related_sectors)
        
        # 只保留：重大事件 或 与持仓相关的
        if not (is_major or is_portfolio_related):
            continue
        
        # 判断重要性
        importance = 1
        if any(kw in text for kw in ['美联储', '央行', '利率决议', '政治局', '国常会', '关税', '制裁']):
            importance = 3
        elif any(kw in text for kw in ['GDP', 'CPI', 'PPI', '非农就业', '两会']):
            importance = 2
        
        # 提取时间（新闻中的时间或当前时间）
        time_str = news.get('time', '')
        
        calendar.append({
            'time': time_str,
            'title': title,
            'importance': importance,
            'importance_label': {3: '重磅', 2: '重要', 1: '关注'}.get(importance, '一般'),
            'related_sectors': related_sectors if related_sectors else ['宏观'],
            'type': 'calendar',
            'source': '财联社',
            'is_major': is_major
        })
    
    # 按重要性排序
    calendar.sort(key=lambda x: x['importance'], reverse=True)
    
    return calendar[:10]  # 最多返回10条

def get_investment_calendar(news_list: List[Dict] = None, portfolio_sectors: List[str] = None) -> List[Dict]:
    """
    获取投资日历
    优先从财联社新闻中提取，同时尝试新浪财经作为补充
    """
    calendar = []
    
    # 1. 从财联社新闻中提取事件
    if news_list and portfolio_sectors:
        calendar = extract_calendar_events_from_news(news_list, portfolio_sectors)
    
    # 2. 如果财联社提取的事件太少，尝试新浪财经补充
    if len(calendar) < 3:
        try:
            import akshare as ak
            df = ak.stock_jsy_event(date=datetime.now().strftime("%Y%m%d"))
            
            for _, row in df.iterrows():
                event = row.get('事件', '')
                
                # 只保留重大事件或与持仓相关的
                is_major = any(kw in event for kw in ['美联储', '央行', '利率决议', 'GDP', 'CPI', '非农'])
                
                if not is_major:
                    continue
                
                # 判断重要性
                importance = 1
                sectors = ['宏观']
                if any(k in event for k in ['美联储', '央行', '利率决议', '非农就业']):
                    importance = 3
                    sectors = ['黄金', '券商', '宏观']
                elif any(k in event for k in ['GDP', 'CPI', 'PPI']):
                    importance = 2
                    sectors = ['宏观', '周期']
                
                # 检查是否已存在（去重）
                if not any(c['title'] == event for c in calendar):
                    calendar.append({
                        'time': str(row.get('时间', ''))[:5],
                        'title': event,
                        'importance': importance,
                        'importance_label': {3: '重磅', 2: '重要', 1: '一般'}.get(importance, '一般'),
                        'related_sectors': sectors,
                        'type': 'calendar',
                        'source': '新浪财经'
                    })
        except Exception as e:
            print(f"[投资日历] 新浪财经补充获取失败: {e}")
    
    # 去重并排序
    seen = set()
    unique_calendar = []
    for item in calendar:
        key = item['title'][:30]  # 取前30字作为去重key
        if key not in seen:
            seen.add(key)
            unique_calendar.append(item)
    
    return sorted(unique_calendar, key=lambda x: x['importance'], reverse=True)[:10]

def classify_news(text: str) -> Tuple[str, int, List[str]]:
    """分类新闻，返回: (分类, 重要性, 关联板块列表)"""
    text = text.lower()
    
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
    
    related_themes = []
    for theme, keywords in THEME_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                related_themes.append(theme)
                if category == "快讯":
                    category = "题材"
                    importance = max(importance, 1)
                break
    
    related_sectors = []
    for sector, keywords in SECTOR_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                related_sectors.append(sector)
                break
    
    relevance_score = 0
    for sector in USER_PORTFOLIO_SECTORS:
        if sector in related_sectors:
            relevance_score += 1
            importance += 1
    
    importance = min(3, max(0, importance))
    return category, importance, related_sectors


def get_hot_themes() -> List[Dict]:
    """获取热门题材（基于实时概念板块数据）"""
    try:
        import akshare as ak
        df = ak.stock_board_concept_name_em()
        df = df.sort_values('最新涨跌幅', ascending=False).head(6)
        
        themes = []
        for _, row in df.iterrows():
            change = float(row['最新涨跌幅']) if pd.notna(row['最新涨跌幅']) else 0
            heat = min(100, max(50, 50 + change * 5))
            themes.append({
                'name': row['板块名称'],
                'heat': round(heat),
                'change': round(change, 2),
                'stocks': []
            })
        return themes
    except Exception as e:
        print(f"[热门题材] 获取实时数据失败: {e}")
        return []

def calculate_market_sentiment(news_list: List[Dict]) -> Dict:
    """计算整体市场情绪指数"""
    if not news_list:
        return {'index': 50, 'label': '中性', 'distribution': {'positive': 0, 'neutral': 0, 'negative': 0}}
    
    total = len(news_list)
    positive = sum(1 for n in news_list if n.get('sentiment') == 'positive')
    negative = sum(1 for n in news_list if n.get('sentiment') == 'negative')
    neutral = total - positive - negative
    
    # 情绪指数 0-100
    index = int(50 + (positive - negative) * 50 / total)
    index = max(0, min(100, index))
    
    if index >= 60:
        label = '乐观'
    elif index <= 40:
        label = '谨慎'
    else:
        label = '中性'
    
    return {
        'index': index,
        'label': label,
        'distribution': {
            'positive': positive,
            'neutral': neutral,
            'negative': negative
        }
    }

def get_cls_structured_news(limit: int = 30, portfolio_sectors: List[str] = None, analyze_sentiment: bool = True) -> Dict:
    """
    获取结构化的财联社新闻 + 情绪分析
    """
    if portfolio_sectors:
        set_user_portfolio_sectors(portfolio_sectors)
    
    try:
        import akshare as ak
        news_df = ak.stock_info_global_cls()
        
        valid_news = news_df[news_df['标题'].str.len() > 5].head(limit)
        
        headlines = []
        themes = []
        portfolio_related = []
        general = []
        
        for _, row in valid_news.iterrows():
            title = row['标题'].replace('财联社3月17日电，', '').replace('财联社电，', '')
            content = row['内容'] if '内容' in row and pd.notna(row['内容']) else ''
            time_str = str(row['发布时间'])[:5] if '发布时间' in row and row['发布时间'] else ''
            
            category, importance, related_sectors = classify_news(title + content)
            
            news_item = {
                'time': time_str,
                'title': title,
                'content': content[:100] if content else '',
                'category': category,
                'importance': importance,
                'importance_label': {3: '重磅', 2: '重要', 1: '关注', 0: '一般'}.get(importance, '一般'),
                'related_sectors': related_sectors,
                'source': '财联社'
            }
            
            if category == "头条":
                headlines.append(news_item)
            elif category == "题材":
                themes.append(news_item)
            elif any(s in USER_PORTFOLIO_SECTORS for s in related_sectors):
                portfolio_related.append(news_item)
            else:
                general.append(news_item)
        
        # 情绪分析（批量，限制数量）- 直接修改原始对象
        if analyze_sentiment:
            all_news = headlines + themes + portfolio_related + general
            batch_analyze_sentiment(all_news, max_batch=15)
            market_sentiment = calculate_market_sentiment(all_news)
        else:
            market_sentiment = {'index': 50, 'label': '未分析', 'distribution': {'positive': 0, 'neutral': 0, 'negative': 0}}
        
        # 从财联社新闻中提取投资日历（基于持仓板块过滤）
        all_news_for_calendar = headlines + themes + portfolio_related + general
        calendar = get_investment_calendar(all_news_for_calendar, portfolio_sectors)
        
        hot_themes = get_hot_themes()
        
        return {
            'success': True,
            'market_sentiment': market_sentiment,
            'headlines': headlines[:5],
            'themes': themes[:8],
            'hot_themes': hot_themes,
            'calendar': calendar,
            'portfolio': portfolio_related[:5],
            'general': general[:10],
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
    except Exception as e:
        print(f"获取财联社新闻失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'market_sentiment': {'index': 50, 'label': '错误', 'distribution': {}},
            'headlines': [],
            'themes': [],
            'hot_themes': [],
            'calendar': [],
            'portfolio': [],
            'general': [],
            'error': str(e)
        }

try:
    import pandas as pd
except:
    pd = None

if __name__ == '__main__':
    result = get_cls_structured_news(limit=10, portfolio_sectors=['半导体', 'AI人工智能'])
    print(f"市场情绪: {result['market_sentiment']['index']}/100 ({result['market_sentiment']['label']})")
    print(f"头条 ({len(result['headlines'])}条):")
    for n in result['headlines'][:3]:
        emoji = {'positive': '🟢', 'negative': '🔴', 'neutral': '🟡'}.get(n.get('sentiment'), '⚪')
        print(f"  {emoji} [{n.get('sentiment_label')}] {n['title'][:40]}...")
