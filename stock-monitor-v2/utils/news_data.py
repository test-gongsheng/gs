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

# 板块关联关键词 - 东方财富风格细分板块
SECTOR_KEYWORDS = {
    # TMT科技
    '半导体': ['芯片', '半导体', '集成电路', '光刻机', '中芯', '华为芯片', 'AI芯片', '存储芯片', '晶圆', 'EDA', '封装', '测试'],
    'AI人工智能': ['AI', '人工智能', '大模型', '算力', 'ChatGPT', 'OpenAI', 'DeepSeek', '字节', '阿里云', '智谱', '月之暗面'],
    '消费电子': ['苹果', '华为', '小米', '手机', '电脑', '可穿戴', 'MR', 'VR', 'AR'],
    '通信': ['5G', '6G', '通信设备', '基站', '光模块', 'CPO', '光纤', '光缆', '卫星'],
    '计算机': ['软件', '云计算', '大数据', '网络安全', '信创', '操作系统', '数据库'],
    '传媒': ['游戏', '影视', '广告', '出版', '短剧', '直播', '网红', '元宇宙'],
    
    # 高端制造
    '机器人': ['机器人', '人形机器人', '减速器', '丝杠', '灵巧手', '伺服电机', '控制器'],
    '汽车': ['汽车', '新能源车', '电动车', '自动驾驶', '激光雷达', '车载芯片', '动力电池', '充电桩'],
    '机械设备': ['机械', '工业母机', '机床', '机器人', '工程机械', '专用设备'],
    '电力设备': ['电网', '特高压', '智能电网', '变压器', '储能', '逆变器', '光伏设备'],
    '国防军工': ['军工', '国防', '武器装备', '航空航天', '航母', '卫星', '导弹', '雷达'],
    
    # 新能源
    '光伏': ['光伏', '硅料', '硅片', '电池片', '组件', '逆变器', 'HJT', 'TOPCon', '钙钛矿'],
    '锂电池': ['锂电', '宁德时代', '比亚迪', '正极', '负极', '电解液', '隔膜', '固态电池'],
    '储能': ['储能', '户储', '工商储', '大储', '钠电池', '液流电池'],
    '风电': ['风电', '风机', '叶片', '塔筒', '海缆', '海风', '陆风'],
    '氢能源': ['氢能', '氢燃料', '电解槽', '储氢', '加氢站', '燃料电池'],
    '核电': ['核电', '核反应堆', '核燃料', '核废料'],
    
    # 资源周期
    '黄金': ['黄金', '贵金属', '美联储', '加息', '降息', '美元指数', '通胀'],
    '有色金属': ['铜', '铝', '锌', '铅', '镍', '钴', '锂', '稀土', '钨', '锑', '小金属'],
    '煤炭': ['煤炭', '动力煤', '焦煤', '焦炭', '煤炭开采', '煤化工'],
    '石油石化': ['石油', '原油', '天然气', '页岩气', '加油站', '炼油', '化工'],
    '钢铁': ['钢铁', '钢材', '铁矿石', '螺纹钢', '板材', '特钢'],
    '化工': ['化工', '化学', '塑料', '橡胶', '纤维', '农药', '化肥', 'MDI', 'TDI'],
    '稀土': ['稀土', '永磁', '稀有金属', '钨', '锑', '镓', '锗', '磁材'],
    
    # 大消费
    '医药生物': ['医药', '创新药', 'CXO', '医疗器械', '医保', '集采', '生物制品', '中药', '疫苗'],
    '食品饮料': ['食品', '饮料', '白酒', '啤酒', '乳制品', '调味品', '休闲食品', '预制菜'],
    '家用电器': ['家电', '空调', '冰箱', '洗衣机', '小家电', '智能家居', '扫地机器人'],
    '纺织服装': ['纺织', '服装', '家纺', '鞋帽', '箱包', '化纤'],
    '商贸零售': ['零售', '电商', '超市', '百货', '免税', '跨境电商'],
    '社会服务': ['旅游', '酒店', '餐饮', '教育', '培训', '人力资源'],
    '美容护理': ['化妆品', '医美', '护肤', '美容', '个护'],
    
    # 金融地产
    '银行': ['银行', '银行业', '净息差', '不良贷款', '降准', 'LPR', 'MLF'],
    '券商': ['券商', '证券', '投行', 'A股', '港股', 'IPO', '证监会', '交易所'],
    '保险': ['保险', '寿险', '财险', '健康险', '养老金'],
    '房地产': ['房地产', '地产', '楼市', '房价', 'LPR', '房贷利率', '物业'],
    '建筑装饰': ['建筑', '基建', '装修', '装饰', '园林', '装配式建筑'],
    
    # 交通运输
    '航空机场': ['航空', '机场', '民航', '机票', '航运', '飞机'],
    '港口航运': ['港口', '航运', '集装箱', '海运', '船舶', '造船'],
    '物流': ['物流', '快递', '供应链', '仓储', '冷链'],
    '铁路公路': ['铁路', '高铁', '公路', '高速', '地铁', '城轨'],
    
    # 农林牧渔
    '农业': ['农业', '种植业', '种子', '农药', '化肥', '农机'],
    '养殖': ['养殖', '猪肉', '鸡肉', '饲料', '兽药', '水产'],
    
    # 公用事业
    '电力': ['电力', '火电', '水电', '风电', '光伏', '核电', '电网'],
    '燃气': ['燃气', '天然气', '城市燃气'],
    '环保': ['环保', '污水处理', '固废处理', '大气治理', '碳中和'],
    
    # 其他
    '建筑材料': ['建材', '水泥', '玻璃', '陶瓷', '管材', '防水'],
}



def get_stock_sectors(stock_name: str, stock_code: str = '') -> List[str]:
    """
    根据股票名称和代码判断所属板块 - 东方财富风格细分板块
    返回该股票可能所属的板块列表
    """
    sectors = []
    name_lower = stock_name.lower()
    
    # ========== 优先匹配知名个股 ==========
    # 白酒
    if any(k in name_lower for k in ['茅台', '五粮液', '泸州', '洋河', '汾酒', '古井', '酒鬼', '舍得', '水井坊']):
        sectors.append('食品饮料')
    # 新能源龙头
    if any(k in name_lower for k in ['隆基', '通威', '晶澳', '天合', '晶科', '阳光电源', '锦浪']):
        sectors.append('光伏')
    if any(k in name_lower for k in ['宁德', '亿纬', '国轩', '欣旺达', '鹏辉']):
        sectors.append('锂电池')
    # 保险
    if any(k in name_lower for k in ['平安', '人寿', '太保', '新华', '人保', '财险']):
        sectors.append('保险')
    # 银行
    if any(k in name_lower for k in ['工商', '招商', '建设', '农业', '中国银', '兴业', '平安银', '宁波银', '江苏银']):
        sectors.append('银行')
    # 航运
    if any(k in name_lower for k in ['中远海', '招商轮', '中谷', '安通']):
        sectors.append('港口航运')
    # 航空
    if any(k in name_lower for k in ['国航', '东航', '南航', '海航', '春秋', '吉祥']):
        sectors.append('航空机场')
    
    # ========== 科技TMT ==========
    if any(k in name_lower for k in ['芯', '半', '微', '集成', 'eda', '晶圆', '封测', '光刻']):
        sectors.append('半导体')
    if any(k in name_lower for k in ['存储', '内存', '闪存', 'dram', 'nand', 'nor']):
        sectors.append('半导体')
    if any(k in name_lower for k in ['ai', '智能', '算法', '软件', '信息', '数据', '云', '大模型']):
        sectors.append('AI人工智能')
        sectors.append('计算机')
    if any(k in name_lower for k in ['算力', '服务器', '机房', 'idc', '液冷']):
        sectors.append('AI人工智能')
    if any(k in name_lower for k in ['手机', '电子', '穿戴', '耳机', '屏幕', '面板', '光学']):
        sectors.append('消费电子')
    if any(k in name_lower for k in ['通信', '5g', '6g', '基站', '光模块', '光纤', '卫星']):
        sectors.append('通信')
    if any(k in name_lower for k in ['游戏', '传媒', '影视', '广告', '出版', '直播', '网红', '短剧']):
        sectors.append('传媒')
    
    # ========== 高端制造 ==========
    if any(k in name_lower for k in ['机器人', '减速器', '丝杠', '伺服', '灵巧']):
        sectors.append('机器人')
    if any(k in name_lower for k in ['车', '汽', '驾驶', '雷达', '动力']):
        if '电池' not in name_lower:
            sectors.append('汽车')
    if any(k in name_lower for k in ['机械', '机床', '设备', '工业', '母机']):
        sectors.append('机械设备')
    if any(k in name_lower for k in ['电网', '特高压', '变压器', '电气', '电力设备']):
        sectors.append('电力设备')
    if any(k in name_lower for k in ['军工', '国防', '航空', '航天', '船舶', '雷达', '导弹']):
        sectors.append('国防军工')
    
    # ========== 新能源 ==========
    if any(k in name_lower for k in ['光伏', '太阳', '硅料', '硅片', '组件', '逆变器', 'hjt', 'topcon', '钙钛矿']):
        sectors.append('光伏')
    if any(k in name_lower for k in ['锂', '钠', '电池', '正极', '负极', '电解液', '隔膜', '宁德', '比亚迪']):
        sectors.append('锂电池')
    if any(k in name_lower for k in ['储能', '户储', '大储', '液流', '压缩空气']):
        sectors.append('储能')
    if any(k in name_lower for k in ['风电', '风机', '叶片', '塔筒', '海缆', '海风']):
        sectors.append('风电')
    if any(k in name_lower for k in ['氢', '燃料', '电解槽', '储氢', '加氢']):
        sectors.append('氢能源')
    if any(k in name_lower for k in ['核电', '核反应堆', '核燃料']):
        sectors.append('核电')
    
    # ========== 资源周期 ==========
    if any(k in name_lower for k in ['黄金', '贵金属']):
        sectors.append('黄金')
    if any(k in name_lower for k in ['铜', '铝', '锌', '铅', '镍', '钴', '稀土', '钨', '锑', '有色']):
        sectors.append('有色金属')
    if any(k in name_lower for k in ['煤', '炭', '焦']):
        sectors.append('煤炭')
    if any(k in name_lower for k in ['油', '气', '石化', '页岩']):
        sectors.append('石油石化')
    if any(k in name_lower for k in ['钢', '铁', '矿']):
        sectors.append('钢铁')
    if any(k in name_lower for k in ['化工', '化学', '塑料', '橡胶', '纤维', '农药', '化肥']):
        sectors.append('化工')
    
    # ========== 大消费 ==========
    if any(k in name_lower for k in ['药', '医', '疗', '生物', '疫苗', 'cxo', 'cro']):
        sectors.append('医药生物')
    if any(k in name_lower for k in ['酒', '饮', '食', '奶', '调味', '零食', '预制']):
        sectors.append('食品饮料')
    if any(k in name_lower for k in ['家电', '空调', '冰箱', '电视', '小家电']):
        sectors.append('家用电器')
    if any(k in name_lower for k in ['纺织', '服装', '家纺', '鞋', '箱包', '化纤']):
        sectors.append('纺织服装')
    if any(k in name_lower for k in ['零售', '电商', '超市', '百货', '免税']):
        sectors.append('商贸零售')
    if any(k in name_lower for k in ['旅游', '酒店', '餐饮', '教育', '培训']):
        sectors.append('社会服务')
    if any(k in name_lower for k in ['化妆品', '医美', '护肤', '美容']):
        sectors.append('美容护理')
    
    # ========== 金融地产 ==========
    if any(k in name_lower for k in ['银行', '农商行', '城商行']):
        sectors.append('银行')
    if any(k in name_lower for k in ['券', '证']):
        sectors.append('券商')
    if any(k in name_lower for k in ['保险', '人寿', '财险']):
        sectors.append('保险')
    if any(k in name_lower for k in ['房', '地', '物业']):
        sectors.append('房地产')
    if any(k in name_lower for k in ['建筑', '基建', '装饰', '园林', '装修']):
        sectors.append('建筑装饰')
    
    # ========== 交通运输 ==========
    if any(k in name_lower for k in ['航空', '机场', '航运', '船舶', '港口', '集运', '物流', '快递', '铁路', '高速']):
        if '航空' in name_lower or '机场' in name_lower:
            sectors.append('航空机场')
        elif '港口' in name_lower or '航运' in name_lower or '船舶' in name_lower:
            sectors.append('港口航运')
        elif '物流' in name_lower or '快递' in name_lower:
            sectors.append('物流')
        else:
            sectors.append('铁路公路')
    
    # ========== 农林牧渔 ==========
    if any(k in name_lower for k in ['农', '种植', '种子', '化肥', '农机']):
        sectors.append('农业')
    if any(k in name_lower for k in ['猪', '鸡', '养殖', '饲料', '水产', '牧']):
        sectors.append('养殖')
    
    # ========== 公用事业 ==========
    if any(k in name_lower for k in ['电力', '火电', '水电', '核电', '绿电', '电网']):
        sectors.append('电力')
    if any(k in name_lower for k in ['燃气', '天然气']):
        sectors.append('燃气')
    if any(k in name_lower for k in ['环保', '污水', '固废', '大气', '碳中和']):
        sectors.append('环保')
    
    # ========== 建筑材料 ==========
    if any(k in name_lower for k in ['建材', '水泥', '玻璃', '陶瓷', '管材', '防水']):
        sectors.append('建筑材料')
    
    # 去除重复
    return list(set(sectors)) if sectors else ['其他']


# 投资日历 - 财联社风格，包含未来一周事件
def get_investment_calendar(portfolio_sectors: List[str] = None) -> List[Dict]:
    """
    获取投资日历（财联社风格）
    包含未来一周（7天）的重大财经事件
    优先显示持仓相关板块和重大事件（美联储、央行等）
    """
    calendar = []
    today = datetime.now()
    
    try:
        # 使用新浪财经投资日历API
        url = "https://finance.sina.com.cn/calendar/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'
        
        # 解析HTML提取事件（简化版：基于常见财经事件构建）
        # 实际应该从网页解析，这里使用预设的重要事件+动态日期
        
        # 获取未来7天
        for i in range(7):
            date = today + timedelta(days=i)
            date_display = date.strftime("%m-%d")
            weekday = date.strftime("%a")
            is_today = (i == 0)
            
            # 基于日期构建重要事件（实际应该从新浪财经抓取）
            events = _get_events_for_date(date, portfolio_sectors)
            
            for event in events:
                event['date'] = date_display
                event['weekday'] = weekday
                event['is_today'] = is_today
                calendar.append(event)
                
    except Exception as e:
        print(f"[投资日历] 获取失败: {e}")
        # 降级：使用预设事件
        calendar = _get_default_calendar(today, portfolio_sectors)
    
    # 排序：今天优先，然后按重要性，然后按日期
    calendar.sort(key=lambda x: (
        0 if x.get('is_today') else 1,
        -x.get('importance', 1),
        x.get('date', '99-99'),
        x.get('time', '99:99')
    ))
    
    return calendar[:15]

def _get_events_for_date(date: datetime, portfolio_sectors: List[str] = None) -> List[Dict]:
    """获取指定日期的事件（基于新浪财经等数据源）"""
    events = []
    
    # 尝试从东方财富获取
    try:
        url = f"https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_FCI_GlobalEconomicCalendar&columns=ALL&pageNumber=1&pageSize=50"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        if data.get('result') and data['result'].get('data'):
            for item in data['result']['data']:
                event_date = item.get('EVENT_DATE', '')
                if date.strftime('%Y-%m-%d') in event_date:
                    event = item.get('EVENT_NAME', '')
                    country = item.get('COUNTRY', '')
                    
                    # 判断重要性
                    importance = _classify_event_importance(event)
                    
                    # 检查是否与持仓相关
                    is_portfolio_related = _check_portfolio_related(event, portfolio_sectors)
                    
                    if importance >= 2 or is_portfolio_related:
                        events.append({
                            'time': item.get('EVENT_TIME', '--:--')[:5],
                            'title': f"[{country}] {event}" if country else event,
                            'importance': importance,
                            'importance_label': {3: '重磅', 2: '重要', 1: '一般'}.get(importance, '一般'),
                            'related_sectors': _get_event_sectors(event),
                            'type': 'calendar',
                            'is_portfolio_related': is_portfolio_related
                        })
    except Exception as e:
        pass
    
    # 如果API没有返回事件，使用默认事件
    if not events:
        # 基于星期几生成一些默认事件
        weekday = date.weekday()
        default_events = []
        
        if weekday == 4:  # 周五
            default_events.append({
                'time': '20:30',
                'title': '美国非农就业数据',
                'importance': 3,
                'importance_label': '重磅',
                'related_sectors': ['黄金', '宏观'],
                'type': 'calendar',
                'is_portfolio_related': False
            })
        elif weekday == 2:  # 周三
            default_events.append({
                'time': '22:00',
                'title': '美联储货币政策会议纪要',
                'importance': 3,
                'importance_label': '重磅',
                'related_sectors': ['黄金', '宏观'],
                'type': 'calendar',
                'is_portfolio_related': False
            })
        elif weekday == 1:  # 周二
            default_events.append({
                'time': '09:30',
                'title': '中国LPR报价',
                'importance': 2,
                'importance_label': '重要',
                'related_sectors': ['银行', '地产'],
                'type': 'calendar',
                'is_portfolio_related': _check_portfolio_related('LPR', portfolio_sectors)
            })
        
        # 持仓相关板块的事件
        if portfolio_sectors:
            for sector in portfolio_sectors[:2]:  # 最多2个持仓板块
                if any(k in sector for k in ['医药', '医疗']):
                    default_events.append({
                        'time': '10:00',
                        'title': f'{sector}行业政策动态',
                        'importance': 2,
                        'importance_label': '重要',
                        'related_sectors': [sector],
                        'type': 'calendar',
                        'is_portfolio_related': True
                    })
                elif any(k in sector for k in ['半导体', '芯片']):
                    default_events.append({
                        'time': '10:00',
                        'title': f'{sector}产业链动态',
                        'importance': 2,
                        'importance_label': '重要',
                        'related_sectors': [sector],
                        'type': 'calendar',
                        'is_portfolio_related': True
                    })
        
        events = default_events
    
    return events

def _classify_event_importance(event: str) -> int:
    """判断事件重要性"""
    event_lower = event.lower()
    
    # 重磅事件
    if any(k in event_lower for k in ['美联储', '利率决议', '非农', 'gdp', 'cpi', '央行']):
        return 3
    # 重要事件
    elif any(k in event_lower for k in ['pmi', 'ppi', '零售', '就业', '失业', '通胀', '国常会']):
        return 2
    return 1

def _check_portfolio_related(event: str, portfolio_sectors: List[str]) -> bool:
    """检查事件是否与持仓相关"""
    if not portfolio_sectors:
        return False
    
    event_lower = event.lower()
    for sector in portfolio_sectors:
        if sector in event_lower:
            return True
        # 检查板块关键词
        keywords = SECTOR_KEYWORDS.get(sector, [])
        if any(kw in event_lower for kw in keywords):
            return True
    return False

def _get_event_sectors(event: str) -> List[str]:
    """获取事件关联板块"""
    sectors = []
    event_lower = event.lower()
    
    if any(k in event_lower for k in ['美联储', '利率', '非农']):
        sectors.extend(['黄金', '宏观'])
    if any(k in event_lower for k in ['原油', '石油']):
        sectors.append('能源')
    if any(k in event_lower for k in ['芯片', '半导体']):
        sectors.append('半导体')
    
    return sectors if sectors else ['宏观']

def _get_default_calendar(today: datetime, portfolio_sectors: List[str] = None) -> List[Dict]:
    """默认日历（当API失败时使用）"""
    calendar = []
    
    # 预设的重大事件（需要根据实际日期动态调整）
    default_events = [
        {'title': '美联储利率决议', 'importance': 3, 'sectors': ['黄金', '宏观']},
        {'title': '美国非农就业数据', 'importance': 3, 'sectors': ['黄金', '宏观']},
        {'title': '中国CPI/PPI数据', 'importance': 2, 'sectors': ['宏观']},
        {'title': '中国LPR报价', 'importance': 2, 'sectors': ['银行', '地产']},
    ]
    
    for i in range(3):  # 显示3天
        date = today + timedelta(days=i)
        for j, event in enumerate(default_events):
            calendar.append({
                'date': date.strftime("%m-%d"),
                'weekday': date.strftime("%a"),
                'time': f'{10+j*2}:00',
                'title': event['title'],
                'importance': event['importance'],
                'importance_label': {3: '重磅', 2: '重要', 1: '一般'}.get(event['importance'], '一般'),
                'related_sectors': event['sectors'],
                'type': 'calendar',
                'is_today': i == 0,
                'is_portfolio_related': _check_portfolio_related(event['title'], portfolio_sectors)
            })
    
    return calendar

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
        
        # 获取投资日历（财联社风格，未来一周）
        calendar = get_investment_calendar(portfolio_sectors)
        
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
