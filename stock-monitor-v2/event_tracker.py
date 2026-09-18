# -*- coding: utf-8 -*-
"""
事件驱动分析引擎
1. 财联社新闻采集（browser工具抓取 + 备用源）
2. 重大事件识别 → 传导路径推演 → 预期方向标注
3. 反应验证：T+1/T+3 实际涨跌 vs 预期 → 预期差判定
4. 解禁风险监控：东财API（含前后20日验证数据）
"""
import os
import json
import time
import re
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

# ========== 持仓股映射 ==========
SECTOR_MAP = {
    '601133': '半导体设备与服务',
    '688795': '半导体-GPU',
    '301308': '半导体-存储',
    '300316': '光伏设备',
    '300442': '数据中心/IDC',
    '002050': '汽车零部件-热管理',
    '000559': '汽车零部件',
    '002594': '新能源汽车',
    '000878': '有色金属-铜',
    '601600': '有色金属-铝',
    '00285': '消费电子',
    '00700': '互联网-平台',
    '09988': '互联网-电商',
    '300229': 'AI应用-NLP',
}

# ========== 事件-板块映射表 ==========
# 重大事件类型 → 影响的板块 → 预期方向
EVENT_SECTOR_MAP = {
    'AI安全监管': {
        'keywords': ['AI安全', '人工智能安全', 'AI监管', '算法监管', 'AI立法', '人工智能立法',
                     '超级智能', 'AI失控', 'AI风险', '放缓AI', '限制AI', 'AI对齐'],
        'impact_paths': [
            {'sectors': ['AI应用-NLP', '互联网-平台', '互联网-电商'],
             'direction': 'negative',
             'logic': '监管收紧→合规成本上升→应用端承压',
             'confidence': 0.6},
            {'sectors': ['半导体-GPU', '半导体-存储'],
             'direction': 'positive',
             'logic': '限制对华芯片出口→国产替代逻辑强化',
             'confidence': 0.75},
            {'sectors': ['数据中心/IDC'],
             'direction': 'neutral',
             'logic': '算力基建长期需求不变，短期情绪波动',
             'confidence': 0.5},
        ],
    },
    '芯片出口管制': {
        'keywords': ['芯片出口', '半导体出口', '对华芯片', '芯片制裁', '技术封锁', '实体清单'],
        'impact_paths': [
            {'sectors': ['半导体-GPU', '半导体-存储', '半导体设备与服务'],
             'direction': 'positive',
             'logic': '进口受限→国产替代加速',
             'confidence': 0.85},
            {'sectors': ['消费电子', '互联网-平台'],
             'direction': 'negative',
             'logic': '供应链成本上升',
             'confidence': 0.6},
        ],
    },
    '新能源政策': {
        'keywords': ['新能源', '电动车', '锂电', '光伏', '储能', '碳中和', '新能源车补贴'],
        'impact_paths': [
            {'sectors': ['新能源汽车', '光伏设备'],
             'direction': 'positive',
             'logic': '政策支持→行业景气度提升',
             'confidence': 0.7},
        ],
    },
    '降息降准': {
        'keywords': ['降准', '降息', 'LPR', '流动性', '货币政策', 'MLF'],
        'impact_paths': [
            {'sectors': ['半导体-GPU', '半导体-存储', '半导体设备与服务', 'AI应用-NLP',
                         '数据中心/IDC', '光伏设备', '新能源汽车'],
             'direction': 'positive',
             'logic': '流动性宽松→成长股估值修复',
             'confidence': 0.8},
            {'sectors': ['有色金属-铜', '有色金属-铝'],
             'direction': 'positive',
             'logic': '宽松→大宗商品价格走强',
             'confidence': 0.7},
        ],
    },
    '地缘冲突': {
        'keywords': ['战争', '冲突', '制裁', '地缘', '台海', '南海', '中东', '俄乌'],
        'impact_paths': [
            {'sectors': ['有色金属-铜', '有色金属-铝'],
             'direction': 'positive',
             'logic': '避险情绪→大宗商品涨价',
             'confidence': 0.7},
            {'sectors': ['半导体-GPU', '消费电子', '互联网-平台', '互联网-电商'],
             'direction': 'negative',
             'logic': '风险偏好下降→科技股承压',
             'confidence': 0.65},
        ],
    },
    '数据安全': {
        'keywords': ['数据安全', '网络安全', '数据泄露', '黑客', '网络攻击', '信息安全'],
        'impact_paths': [
            {'sectors': ['数据中心/IDC', '互联网-平台', '互联网-电商'],
             'direction': 'negative',
             'logic': '安全事件→信任危机→短期承压',
             'confidence': 0.6},
            {'sectors': ['AI应用-NLP'],
             'direction': 'neutral',
             'logic': '安全需求上升但监管也收紧',
             'confidence': 0.5},
        ],
    },
    '半导体扩产': {
        'keywords': ['存储芯片', '存储器', 'HBM', 'DRAM', 'NAND', '长鑫', '长江存储',
                     '存储涨价', '晶圆厂', '晶圆代工', '扩产', '洁净室', '洁净厂房',
                     '半导体设备', '半导体投资', '先进封装', '封测'],
        'impact_paths': [
            {'sectors': ['半导体-存储'],
             'direction': 'positive',
             'logic': '存储景气上行→涨价+扩产，盈利改善',
             'confidence': 0.8},
            {'sectors': ['半导体设备与服务'],
             'direction': 'positive',
             'logic': '晶圆厂/存储扩产→洁净室与厂务工程需求→订单增长',
             'confidence': 0.85},
            {'sectors': ['半导体-GPU'],
             'direction': 'positive',
             'logic': '算力基建联动→国产芯片需求扩张',
             'confidence': 0.6},
        ],
    },
    '解禁': {
        'keywords': ['解禁', '限售股', '首发原股东', '战略配售'],
        'impact_paths': [],  # 由解禁模块专门处理
        'special': 'unlock',
    },
}

# 事件重要性分级
EVENT_LEVELS = {
    'critical': {'keywords': ['禁令', '制裁', '破产', '退市', '立案', '重大事故', '战争'],
                 'score': 90},
    'high': {'keywords': ['监管', '立法', '出口管制', '降准', '降息', '解禁'],
             'score': 70},
    'medium': {'keywords': ['发布', '上市', '收购', '合作', '突破', '扩产', '涨价', '晶圆'],
               'score': 50},
}

# ========== 个股级重大事件自动发现 ==========
# 不限于预定义事件类型，从个股新闻标题中自动识别事件信号
STOCK_EVENT_SIGNALS = {
    'critical': {
        'label': '重大风险',
        'keywords': ['立案', '退市', '破产', '造假', '违规', '处罚', '警示函',
                     '债务危机', '爆仓', '被执行', '冻结', '问询函', '调查'],
    },
    'high': {
        'label': '重要事件',
        'keywords': ['制裁', '管制', '禁令', '关税', '实体清单', '解禁',
                     '中标', '大单', '收购', '重组', '定增', '回购', '增持',
                     '业绩预告', '超预期', '巨亏', '亏损', '减持', '高管离职',
                     '订单', '投产', '扩产', '涨价', '降价'],
    },
    'medium': {
        'label': '一般动态',
        'keywords': ['发布', '新品', '合作', '签约', '上市', '突破', '专利',
                     '机构调研', '评级', '研报', '分红', '派息',
                     '适配', '集群', '超节点', 'AIDC', '算力', '大模型'],
    },
}

# 事件方向推断关键词
POSITIVE_WORDS = ['中标', '大单', '订单', '超预期', '预增', '增长', '突破', '投产', '扩产',
                  '回购', '增持', '合作', '签约', '新品', '专利', '涨价', '交付', '量产', '盈利']
NEGATIVE_WORDS = ['立案', '退市', '破产', '造假', '违规', '处罚', '警示函', '债务',
                  '爆仓', '冻结', '问询', '调查', '制裁', '管制', '禁令', '关税', '实体清单',
                  '巨亏', '亏损', '减持', '离职', '降价', '违约', '诉讼', '仲裁', '召回',
                  '解禁', '低于预期', '下修']

# ========== 个股概念标签（板块级事件归因） ==========
# 新闻标题不含股票名、但含概念词时，事件归到对应持仓股
# 解决：三花智控这类概念股，机器人板块大事件因标题无"三花智控"被漏掉
STOCK_CONCEPT_TAGS = {
    '002050': ['机器人', '人形机器人', '具身智能', '执行器', '特斯拉链'],
    '002594': ['新能源', '电动车', '插电混', '智驾', '比亚迪'],
    '00285':  ['比亚迪电子', '英伟达链', 'AI服务器', '机器人', '消费电子'],
    '300229': ['AI应用', '大模型', '语料', '数据要素', '信创'],
    '300316': ['半导体设备', '碳化硅', '光伏设备', '晶盛'],
    '300442': ['算力', '数据中心', 'IDC', '液冷', '润泽'],
    '301308': ['存储芯片', '江波龙', 'DRAM', 'NAND', '半导体'],
    '601133': ['半导体', '洁净室', '中芯', '晶圆厂', '柏诚'],
    '601600': ['铝业', '氧化铝', '有色', '中铝'],
    '000878': ['铜业', '电解铜', '有色', '云铜'],
    '000559': ['汽车零部件', '线控底盘', '机器人关节', '万向'],
    '688795': ['GPU', '国产芯片', '信创', '摩尔线程', '算力芯片'],
    '00700':  ['腾讯', '游戏版号', 'AI应用', '微信', '视频号'],
    '09988':  ['阿里', '阿里云', '通义', '电商', 'AI应用'],
}


def extract_concept_events(stock_code: str, concept_tags: List[str], news_pool: List[Dict]) -> List[Dict]:
    """板块级事件归因：新闻标题含概念标签时，归到对应持仓股。
    与个股级 extract_stock_events 互补——那个只看标题是否含股票名，这个只看概念词。"""
    events = []
    seen_titles = set()
    for news in (news_pool or []):
        title = (news.get('title', '') or '').replace('<em>', '').replace('</em>', '')
        if not title or title in seen_titles:
            continue
        matched = [kw for kw in concept_tags if kw in title]
        if not matched:
            continue
        seen_titles.add(title)
        # 跳过纯行情播报类（与个股级一致的降噪规则）
        if any(skip in title for skip in ['涨', '跌', '涨停', '跌停', '龙虎榜', '换手率', '成交额']):
            if not any(sig in title for sig in ['解禁', '减持', '增持', '回购', '订单', '量产', '发布', '突破', '合作', '中标', '量产']):
                continue
        # 方向推断（复用全局限定词）
        pos = sum(1 for w in POSITIVE_WORDS if w in title)
        neg = sum(1 for w in NEGATIVE_WORDS if w in title)
        direction = 'positive' if pos > neg else ('negative' if neg > pos else 'neutral')
        # 概念级最高给到high（critical只留给个股直接事件）
        level = 'high' if any(k in title for k in STOCK_EVENT_SIGNALS['high']['keywords']) else 'medium'
        events.append({
            'level': level,
            'label': '板块事件',
            'title': title,
            'time': news.get('time', ''),
            'source': news.get('source', ''),
            'direction': direction,
            'matched': matched,
            'content': (news.get('content', '') or '')[:200],
        })
    order = {'critical': 0, 'high': 1, 'medium': 2}
    events.sort(key=lambda e: (order.get(e['level'], 9), e.get('time', '')))
    return events[:5]  # 最多5条，避免板块新闻刷屏


def extract_stock_events(stock_code: str, stock_name: str, news_list: List[Dict],
                         all_portfolio_names: List[str] = None) -> List[Dict]:
    """
    从个股新闻中自动发现重大事件
    返回事件列表：{level, label, title, time, source, direction, matched}
    """
    events = []
    seen_titles = set()
    other_names = [n for n in (all_portfolio_names or []) if n and n != stock_name]

    for news in (news_list or []):
        title = (news.get('title', '') or '').replace('<em>', '').replace('</em>', '')
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        
        # 去噪：标题不含本股名称/代码，但明确提到其他持仓股 → 不是本股新闻
        if stock_name and stock_name not in title and stock_code not in title:
            if any(n in title for n in other_names):
                continue

        # 跳过纯行情播报类（但 content 含行业实质信息[大会/政策/产业]的放行）
        if any(skip in title for skip in ['涨', '跌', '涨停', '跌停', '龙虎榜', '换手率', '成交额']):
            if not any(sig in title for sig in ['解禁', '减持', '增持', '回购']):
                content_text = (news.get('content', '') or '')[:150]
                if not any(sub in content_text for sub in ['大会', '政策', '规划', '产业', '行业', '超节点', '智算']):
                    continue

        best_level = None
        best_label = ''
        matched_kws = []
        for level, cfg in STOCK_EVENT_SIGNALS.items():
            hits = [kw for kw in cfg['keywords'] if kw in title]
            if hits:
                # 取最高级别（critical > high > medium）
                if best_level is None or list(STOCK_EVENT_SIGNALS.keys()).index(level) < list(STOCK_EVENT_SIGNALS.keys()).index(best_level):
                    best_level = level
                    best_label = cfg['label']
                    matched_kws = hits

        if not best_level:
            continue

        # 方向推断
        pos = sum(1 for w in POSITIVE_WORDS if w in title)
        neg = sum(1 for w in NEGATIVE_WORDS if w in title)
        if pos > neg:
            direction = 'positive'
        elif neg > pos:
            direction = 'negative'
        else:
            direction = 'neutral'

        events.append({
            'level': best_level,
            'label': best_label,
            'title': title,
            'time': news.get('time', ''),
            'source': news.get('source', ''),
            'direction': direction,
            'matched': matched_kws,
            'content': (news.get('content', '') or '')[:200],
            'article_code': news.get('code', ''),
        })

    # 按级别排序：critical 在前
    order = {'critical': 0, 'high': 1, 'medium': 2}
    events.sort(key=lambda e: (order.get(e['level'], 9), e.get('time', '')), reverse=False)
    return events


# ========== 全文抓取 ==========

def fetch_article_fulltext(article_code: str) -> str:
    """抓东财新闻详情页全文，返回正文文本（失败返回空字符串）"""
    if not article_code:
        return ''
    try:
        url = f'http://finance.eastmoney.com/a/{article_code}.html'
        resp = _session.get(url, timeout=8, headers={
            'Referer': 'https://finance.eastmoney.com/'
        })
        html = resp.text
        body = re.search(r'<div[^>]*class="txtinfos"[^>]*>(.*?)</div>', html, re.DOTALL)
        if body:
            text = re.sub(r'<[^>]+>', '', body.group(1)).strip()
            text = re.sub(r'\s+', ' ', text)
            # 去掉末尾“文章来源：xxx”
            text = re.sub(r'（文章来源：.*?）$', '', text)
            return text
        # 备选：og:description
        og = re.search(r'<meta[^>]*og:description[^>]*content="([^"]+)"', html)
        if og:
            return og.group(1)[:500]
    except Exception:
        pass
    return ''


def enrich_events_with_fulltext(events: List[Dict], max_events: int = 6):
    """对事件列表中有 article_code 的事件抓全文，替换短摘要"""
    for e in events[:max_events]:
        code = e.get('article_code', '')
        if not code:
            continue
        full = fetch_article_fulltext(code)
        if full and len(full) > len(e.get('content', '')):
            e['content'] = full[:600]


# ========== 新闻采集 ==========
def _fetch_akshare_with_timeout(timeout_sec=15) -> Optional[List[Dict]]:
    """akshare调用带超时保护（防止卡死）
    signal.alarm只能在主线程用，后台线程改用线程join超时"""
    import threading as _td
    result = [None]
    def _call():
        try:
            import akshare as ak
            df = ak.stock_info_global_cls(symbol="电报")
            if df is not None and len(df) > 0:
                news = []
                for _, row in df.head(100).iterrows():
                    news.append({
                        'title': str(row.get('标题', '')),
                        'content': str(row.get('内容', ''))[:500],
                        'time': str(row.get('发布日期', '')),
                        'source': '财联社',
                    })
                result[0] = news
        except Exception as e:
            print(f'[财联社] akshare失败: {e}')
    t = _td.Thread(target=_call, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    if t.is_alive():
        print(f'[财联社] akshare超时({timeout_sec}s)，走备用源')
        return None
    return result[0]


def fetch_cls_telegraph() -> List[Dict]:
    """
    财联社电报采集
    方案1：akshare（带超时保护）
    方案2：东财新闻搜索（备用）
    """
    news = []

    # 方案1：akshare（15秒超时）
    ak_news = _fetch_akshare_with_timeout(15)
    if ak_news:
        print(f'[财联社] akshare获取 {len(ak_news)} 条')
        return ak_news

    # 方案2：东财新闻搜索（多关键词）
    keywords = ['AI安全', '芯片出口', '解禁', '降准降息', '人工智能监管']
    for kw in keywords[:3]:  # 限制关键词数量避免太慢
        try:
            encoded = requests.utils.quote(json.dumps({
                "uid": "", "keyword": kw, "type": ["cmsArticleWebOld"],
                "client": "web", "clientVersion": "curr", "clientType": "web",
                "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default", "pageIndex": 1, "pageSize": 20}}
            }, ensure_ascii=False))
            url = f'https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param={encoded}'
            resp = _session.get(url, timeout=8)
            match = re.search(r'jQuery\((.*)\)', resp.text)
            if match:
                data = json.loads(match.group(1))
                inner = data.get('result', {}).get('cmsArticleWebOld', [])
                # inner 可能是 list 或 dict（含 list key）
                if isinstance(inner, dict):
                    articles = inner.get('list', [])
                else:
                    articles = inner  # 直接就是 list
                for art in articles:
                    title = art.get('title', '')
                    if not any(n['title'] == title for n in news):
                        news.append({
                            'title': title,
                            'content': art.get('content', '')[:500],
                            'time': art.get('date', ''),
                            'source': art.get('mediaName', '东方财富'),
                            'code': art.get('code', ''),
                        })
            print(f'[东财] "{kw}" 获取 {len(news)} 条累计')
        except Exception as e:
            print(f'[东财] "{kw}" 失败: {e}')
        time.sleep(0.5)

    return news[:50]  # 限制总量


def fetch_stock_news(stock_codes: List[str], stock_names: Dict[str, str] = None) -> Dict[str, List[Dict]]:
    """获取持仓股相关新闻（代码+名称双路搜索，带超时保护）"""
    result = {}
    stock_names = stock_names or {}
    for code in stock_codes[:14]:  # 限制只查持仓股
        all_news = []
        seen = set()
        # 双路搜索：代码 和 股票名称（名称搜到的更相关）
        keywords = [stock_names.get(code, ''), code] if stock_names.get(code) else [code]
        # 第三路：概念标签搜索（板块新闻标题不含股票名，靠概念词命中）
        concept_kws = STOCK_CONCEPT_TAGS.get(code, [])[:3]
        keywords = [k for k in (keywords + concept_kws) if k]
        for kw in keywords:
            if not kw:
                continue
            try:
                encoded = requests.utils.quote(json.dumps({
                    "uid": "", "keyword": kw, "type": ["cmsArticleWebOld"],
                    "client": "web", "clientVersion": "curr", "clientType": "web",
                    "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default", "pageIndex": 1, "pageSize": 20}}
                }, ensure_ascii=False))
                url = f'https://search-api-web.eastmoney.com/search/jsonp?cb=jQuery&param={encoded}'
                resp = _session.get(url, timeout=8)
                match = re.search(r'jQuery\((.*)\)', resp.text)
                if match:
                    data = json.loads(match.group(1))
                    inner = data.get('result', {}).get('cmsArticleWebOld', [])
                    if isinstance(inner, dict):
                        articles = inner.get('list', [])
                    else:
                        articles = inner
                    for a in (articles if isinstance(articles, list) else []):
                        t = a.get('title', '')
                        if t and t not in seen:
                            seen.add(t)
                            all_news.append({
                                'title': t,
                                'content': (a.get('content', '') or '').replace('<em>', '').replace('</em>', '')[:300],
                                'time': a.get('date', ''),
                                'source': a.get('mediaName', ''),
                                'code': a.get('code', ''),
                            })
            except Exception:
                pass
            time.sleep(0.3)
        result[code] = all_news[:15]  # 每只个股最多15条
    return result


# ========== 解禁监控 ==========
def get_unlock_data(stock_code: str) -> List[Dict]:
    """东财解禁数据"""
    try:
        url = (f'https://datacenter-web.eastmoney.com/api/data/v1/get?'
               f'reportName=RPT_LIFT_STAGE&columns=ALL&'
               f'filter=(SECURITY_CODE%3D%22{stock_code}%22)&pageNumber=1&pageSize=20')
        resp = _session.get(url, timeout=15)
        data = resp.json()

        if not data.get('result') or not data['result'].get('data'):
            return []

        results = []
        for item in data['result']['data']:
            free_date = item.get('FREE_DATE', '')[:10]
            if not free_date:
                continue
            free_shares = float(item.get('FREE_SHARES', 0) or 0)
            total_ratio = float(item.get('TOTALSHARES_RATIO', 0) or 0) * 100
            mkt_cap = float(item.get('LIFT_MARKET_CAP', 0) or 0) / 10000
            free_type = item.get('FREE_SHARES_TYPE', '')
            holder = item.get('BATCH_HOLDER_NUM', 0)
            b20 = item.get('B20_ADJCHRATE')
            a20 = item.get('A20_ADJCHRATE')
            name = item.get('SECURITY_NAME_ABBR', '')

            results.append({
                'date': free_date,
                'type': free_type,
                'shares': free_shares,
                'total_ratio': round(total_ratio, 2),
                'mkt_cap': round(mkt_cap, 0),
                'holder_num': holder,
                'before_20d_chg': round(float(b20), 1) if b20 is not None else None,
                'after_20d_chg': round(float(a20), 1) if a20 is not None else None,
                'name': name,
            })

        results.sort(key=lambda x: x['date'])
        return results
    except Exception as e:
        print(f'[解禁] {stock_code} 获取失败: {e}')
        return []


def analyze_unlock_risk(stock_code: str, stock_name: str = '') -> Dict:
    """
    解禁风险分析
    返回：历史解禁影响 + 未来解禁预警
    """
    records = get_unlock_data(stock_code)
    today = datetime.now().strftime('%Y-%m-%d')

    past = [r for r in records if r['date'] <= today]
    future = [r for r in records if r['date'] > today]

    # 未来解禁预警
    warnings = []
    for r in future:
        days_until = (datetime.strptime(r['date'], '%Y-%m-%d') - datetime.now()).days
        if days_until <= 90:  # 90天内
            risk_level = 'HIGH' if r['total_ratio'] > 30 else ('MEDIUM' if r['total_ratio'] > 10 else 'LOW')
            warnings.append({
                'date': r['date'],
                'days_until': days_until,
                'ratio': r['total_ratio'],
                'type': r['type'],
                'mkt_cap': r['mkt_cap'],
                'risk': risk_level,
            })

    # 历史解禁影响（用于模式学习）
    history = []
    for r in past:
        if r['after_20d_chg'] is not None:
            history.append({
                'date': r['date'],
                'ratio': r['total_ratio'],
                'before_20d': r['before_20d_chg'],
                'after_20d': r['after_20d_chg'],
                'pattern': ('提前下跌' if (r['before_20d_chg'] or 0) < -5 else '正常')
                           + ('，解禁后大跌' if r['after_20d_chg'] < -10 else
                              '，解禁后小跌' if r['after_20d_chg'] < 0 else
                              '，解禁后上涨'),
            })

    return {
        'code': stock_code,
        'name': stock_name,
        'future_warnings': warnings,
        'history': history,
        'has_warning': len(warnings) > 0,
    }


# ========== 事件识别与追踪 ==========
def identify_events(news_list: List[Dict]) -> List[Dict]:
    """从新闻中识别重大事件"""
    events = []

    for news in news_list:
        title = news.get('title', '')
        content = news.get('content', '')

        for event_type, config in EVENT_SECTOR_MAP.items():
            if config.get('special') == 'unlock':
                continue  # 解禁由专门模块处理

            matched_kws = [kw for kw in config['keywords'] if kw in title or kw in content]
            if not matched_kws:
                continue

            # 判断重要性
            level = 'medium'
            for lvl, lvl_cfg in EVENT_LEVELS.items():
                if any(k in title or k in content for k in lvl_cfg['keywords']):
                    level = lvl
                    break

            # 检查是否已有同类型事件（避免重复）
            existing = next((e for e in events if e['type'] == event_type), None)
            if existing:
                # 更新为最新
                existing['latest_news'] = title
                existing['latest_time'] = news.get('time', '')
                existing['count'] = existing.get('count', 1) + 1
                continue

            # 推演影响路径
            impacted_stocks = []
            for path in config['impact_paths']:
                for sector, sec_name in SECTOR_MAP.items():
                    if sec_name in path['sectors']:
                        impacted_stocks.append({
                            'code': sector,
                            'sector': sec_name,
                            'expected': path['direction'],
                            'logic': path['logic'],
                            'confidence': path['confidence'],
                        })

            events.append({
                'type': event_type,
                'level': level,
                'keywords': matched_kws,
                'first_news': title,
                'latest_news': title,
                'latest_time': news.get('time', ''),
                'count': 1,
                'impact_paths': config['impact_paths'],
                'impacted_stocks': impacted_stocks,
                'status': 'tracking',  # tracking / verified / invalidated
            })

    return events


def verify_event_impact(event: Dict, stock_quotes: Dict[str, Dict]) -> Dict:
    """
    验证事件对持仓股的实际影响
    对比预期方向 vs 实际涨跌
    """
    verified = []
    for stock in event.get('impacted_stocks', []):
        code = stock['code']
        quote = stock_quotes.get(code, {})
        actual_chg = quote.get('change_pct', 0)
        expected = stock['expected']

        # 预期差判定
        if expected == 'positive':
            if actual_chg > 1:
                verdict = 'confirmed'      # 预期涨且涨 ✅
                gap_score = min(actual_chg / 3, 1)
            elif actual_chg < -1:
                verdict = 'invalidated'    # 预期涨但跌 ❌ 逻辑证伪
                gap_score = -1
            else:
                verdict = 'pending'        # 未兑现
                gap_score = 0
        elif expected == 'negative':
            if actual_chg < -1:
                verdict = 'confirmed'      # 预期跌且跌
                gap_score = min(abs(actual_chg) / 3, 1)
            elif actual_chg > 1:
                verdict = 'contrarian'     # 预期跌但涨 🔥 有对冲逻辑
                gap_score = 1
            else:
                verdict = 'pending'
                gap_score = 0
        else:  # neutral
            verdict = 'as_expected' if abs(actual_chg) < 1 else 'deviated'
            gap_score = 0

        stock['actual_change'] = actual_chg
        stock['verdict'] = verdict
        stock['gap_score'] = gap_score
        stock['price'] = quote.get('price', 0)
        verified.append(stock)

    event['impacted_stocks'] = verified

    # 事件整体状态
    verdicts = [s['verdict'] for s in verified]
    if 'invalidated' in verdicts:
        event['status'] = 'invalidated'
        event['trend_conclusion'] = '预期被证伪，市场定价了其他逻辑'
    elif 'contrarian' in verdicts:
        event['status'] = 'contrarian'
        event['trend_conclusion'] = '出现预期差，存在隐藏逻辑在对冲，值得深挖'
    elif all(v in ('confirmed', 'as_expected') for v in verdicts if v != 'pending'):
        event['status'] = 'confirmed'
        event['trend_conclusion'] = '预期验证，趋势延续'
    else:
        event['status'] = 'tracking'
        event['trend_conclusion'] = '持续跟踪中，尚未形成明确信号'

    return event


def get_realtime_quotes(codes: List[str]) -> Dict[str, Dict]:
    """腾讯批量行情"""
    result = {}
    for i in range(0, len(codes), 50):
        batch = codes[i:i+50]
        tc = []
        for c in batch:
            if c.startswith('6'):
                tc.append(f'sh{c}')
            elif c.startswith(('0', '3')):
                tc.append(f'sz{c}')
            elif c.startswith(('00', '01', '02', '07', '09')) and len(c) == 5:
                tc.append(f'hk{c}')
            else:
                tc.append(f'sh{c}')
        try:
            resp = _session.get(f'http://qt.gtimg.cn/q={",".join(tc)}', timeout=10)
            resp.encoding = 'gbk'
            for line in resp.text.split(';'):
                if '~' not in line:
                    continue
                parts = line.split('~')
                if len(parts) < 35:
                    continue
                result[parts[2]] = {
                    'name': parts[1],
                    'price': float(parts[3] or 0),
                    'change_pct': float(parts[32] or 0),
                }
        except Exception as e:
            print(f'[行情] 失败: {e}')
        time.sleep(0.2)
    return result


# ========== 主流程 ==========
def run_event_analysis(stocks: List[Dict]) -> Dict:
    """
    每日运行：事件分析主流程
    """
    today = datetime.now().strftime('%Y-%m-%d')
    print(f'[事件引擎] {today} 开始分析...')

    stock_codes = [s['code'] for s in stocks]

    # 1. 采集新闻
    print('[1/5] 采集财联社/东财新闻...')
    news = fetch_cls_telegraph()
    name_map = {s['code']: s.get('name', '') for s in stocks}
    stock_news = fetch_stock_news(stock_codes, name_map)
    
    # 1.5 个股级事件自动发现（每只个股扫描自己的新闻）
    print('[1.5/5] 个股事件自动发现...')
    stock_events = {}
    all_names = [s.get('name', '') for s in stocks]
    for s in stocks:
        code = s['code']
        name = s.get('name', '')
        evts = extract_stock_events(code, name, stock_news.get(code, []), all_names)
        if evts:
            # 抓全文：用新闻详情页正文替换搜索摘要，保留关键细节
            enrich_events_with_fulltext(evts)
            stock_events[code] = evts
            print(f'  [{name}] 发现 {len(evts)} 个事件: {[e["matched"][0] for e in evts[:3]]}')

    # 1.6 板块级事件归因（财联社电报中的板块大事，归到概念股）
    # 解决：三花智控等概念股，板块新闻标题不含股票名导致全部漏掉
    print('[1.6/5] 板块级事件归因...')
    for s in stocks:
        code = s['code']
        concept_tags = STOCK_CONCEPT_TAGS.get(code)
        if not concept_tags:
            continue
        concept_evts = extract_concept_events(code, concept_tags, news + stock_news.get(code, []))
        if concept_evts:
            existing = stock_events.setdefault(code, [])
            existing_titles = {e['title'] for e in existing}
            added = [e for e in concept_evts if e['title'] not in existing_titles]
            existing.extend(added)
            if added:
                print(f"  [{s.get('name')}] 板块归因 +{len(added)} 条: {[e['matched'][0] for e in added[:3]]}")

    # 2. 识别事件
    print('[2/5] 识别重大事件...')
    events = identify_events(news)

    # 3. 加载历史事件（持续追踪）
    history = _load_events()
    for new_ev in events:
        existing = next((e for e in history if e['type'] == new_ev['type'] and
                         (datetime.now() - datetime.strptime(e.get('first_date', today), '%Y-%m-%d')).days <= 14), None)
        if existing:
            existing.update(new_ev)
            existing['tracking_days'] = (datetime.now() - datetime.strptime(existing.get('first_date', today), '%Y-%m-%d')).days + 1
        else:
            new_ev['first_date'] = today
            new_ev['tracking_days'] = 1
            history.append(new_ev)

    # 只保留30天内的事件
    cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    history = [e for e in history if e.get('first_date', '2026-01-01') >= cutoff]

    # 4. 解禁分析
    print('[3/5] 解禁风险扫描...')
    unlock_analysis = {}
    for s in stocks:
        code = s['code']
        if code.startswith(('0', '3', '6')) and len(code) == 6:  # A股
            unlock_analysis[code] = analyze_unlock_risk(code, s.get('name', ''))
            time.sleep(0.3)

    # 5. 验证事件影响
    print('[4/5] 验证事件实际影响...')
    quotes = get_realtime_quotes(stock_codes)
    for event in history:
        if event.get('status') == 'tracking':
            verify_event_impact(event, quotes)

    # 6. 保存
    print('[5/5] 保存分析结果...')
    _save_events(history)

    report = {
        'date': today,
        'events': history,
        'unlock': unlock_analysis,
        'stock_events': stock_events,   # 个股级自动发现事件
        'news_count': len(news),
    }

    # 保存完整报告
    filepath = os.path.join(DATA_DIR, 'event_impact.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    return report


def _load_events() -> List[Dict]:
    filepath = os.path.join(DATA_DIR, 'events_history.json')
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def _save_events(events: List[Dict]):
    filepath = os.path.join(DATA_DIR, 'events_history.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(events, f, ensure_ascii=False, indent=2, default=str)


def _fetch_financial_highlights(stock_code: str) -> List[str]:
    """从东财财务摘要提取最新业绩亮点（营收/净利润同比）
    带文件缓存，同一天不重复调akshare"""
    cache_file = os.path.join(DATA_DIR, 'financial_cache.json')
    today = datetime.now().strftime('%Y-%m-%d')
    try:
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            if cache.get(stock_code, {}).get('date') == today:
                return cache[stock_code].get('lines', [])
    except Exception:
        cache = {}
    
    lines = []
    try:
        import threading as _td
        result = [None]
        def _call():
            try:
                import akshare as ak
                df = ak.stock_financial_abstract(symbol=stock_code)
                if df is not None and len(df) > 0:
                    result[0] = df
            except Exception:
                pass
        t = _td.Thread(target=_call, daemon=True)
        t.start()
        t.join(timeout=12)
        df = result[0]
        if df is None:
            return []
        
        # 找营收和净利润行
        cols = [c for c in df.columns if c not in ('选项', '指标')]
        if len(cols) < 5:
            return []
        latest_col = cols[0]   # 最新报告期
        yoy_col = cols[4]      # 去年同期
        
        def _fmt(v):
            try:
                v = float(v)
                if abs(v) >= 1e8:
                    return f"{v/1e8:.2f}亿"
                elif abs(v) >= 1e4:
                    return f"{v/1e4:.0f}万"
                return f"{v:.0f}"
            except Exception:
                return str(v)
        
        emitted = set()  # 同名指标只出一次（摘要表多类别下有重复行）
        for _, row in df.iterrows():
            indicator = str(row.get('指标', '')).strip()
            # 精确匹配主指标行，避免'营业收入同比增长'等衍生行混入
            if indicator in ('营业总收入', '营业收入', '主营业务收入'):
                is_profit_row = False
            elif indicator in ('归母净利润', '归属净利润'):
                is_profit_row = True
            else:
                continue
            key = 'profit' if is_profit_row else 'revenue'
            if key in emitted:
                continue
            emitted.add(key)
            
            if not is_profit_row:
                rev_cur = row.get(latest_col, 0)
                rev_prev = row.get(yoy_col, 0)
                try:
                    yoy = (float(rev_cur) / float(rev_prev) - 1) * 100 if float(rev_prev) != 0 else 0
                    lines.append(f"营收 {_fmt(rev_cur)}（同比{yoy:+.1f}%）")
                except Exception:
                    lines.append(f"营收 {_fmt(rev_cur)}")
            else:
                profit_cur = row.get(latest_col, 0)
                profit_prev = row.get(yoy_col, 0)
                try:
                    pc, pp = float(profit_cur), float(profit_prev)
                    if pc > 0 and pp > 0:
                        yoy = (pc / pp - 1) * 100
                        lines.append(f"归母净利 {_fmt(pc)}（同比{yoy:+.1f}%）")
                    elif pc > 0 >= pp or (pc > 0 and pp < 0):
                        lines.append(f"归母净利 {_fmt(pc)}（扭亏为盈）")
                    elif pc < 0 and pp < 0:
                        narrow = (1 - abs(pc) / abs(pp)) * 100 if pp != 0 else 0
                        if narrow > 0:
                            lines.append(f"归母净利 {_fmt(pc)}（亏损收窄{narrow:.0f}%）")
                        else:
                            lines.append(f"归母净利 {_fmt(pc)}（亏损扩大{abs(narrow):.0f}%）")
                    else:
                        lines.append(f"归母净利 {_fmt(profit_cur)}")
                except Exception:
                    lines.append(f"归母净利 {_fmt(profit_cur)}")
        
        if lines:
            lines.insert(0, f"最新报告期 {latest_col}：")
    except Exception as e:
        print(f'[财报] {stock_code} 获取失败: {e}')
    
    # 写缓存
    try:
        cache[stock_code] = {'date': today, 'lines': lines}
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass
    
    return lines


def format_event_for_report(stock_code: str) -> List[str]:
    """格式化个股事件影响，供deep_analysis.py引用（东财异动解读风格）"""
    filepath = os.path.join(DATA_DIR, 'event_impact.json')
    if not os.path.exists(filepath):
        return ['事件数据尚未生成']

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    lines = []
    
    # 财报亮点（东财异动解读第一层：业绩数据）
    fin_lines = _fetch_financial_highlights(stock_code)
    
    # 个股级自动发现事件
    stock_evts = data.get('stock_events', {}).get(stock_code, [])

    # 概念级事件（产业链联动）——新鲜度过滤后供行业原因注入
    from datetime import datetime as _dt
    def _parse_news_time(s):
        if not s:
            return None
        s = s.strip()
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                return _dt.strptime(s, fmt)
            except ValueError:
                pass
        return None

    _now = _dt.now()
    EVENT_STALE_DAYS = 7   # 7天无更新即过期
    EVENT_DEAD_DAYS = 3    # 超3天且无跟进/已证伪也清理
    concept_all = []       # (event, stock_impact, date, age) 新鲜概念事件
    for ev in data.get('events', []):
        ev_date = _parse_news_time(ev.get('latest_time', ''))
        age_days = (_now - ev_date).days if ev_date else 0
        if ev_date and age_days > EVENT_STALE_DAYS:
            continue
        if ev_date and age_days > EVENT_DEAD_DAYS:
            if ev.get('count', 1) <= 1 or '证伪' in (ev.get('trend_conclusion') or ''):
                continue
        for s in ev.get('impacted_stocks', []):
            if s['code'] == stock_code:
                concept_all.append((ev, s, ev_date, age_days))
                break  # 每个事件对本股只取一条传导逻辑
    
    # 异动原因标签（东财风格：标签云）
    tags = []
    if fin_lines:
        for fl in fin_lines[1:]:  # 跳过报告期标题
            if ('同比+' in fl or '扭亏' in fl) and '业绩高增' not in tags:
                tags.append('业绩高增')
            elif '收窄' in fl and '亏损收窄' not in tags:
                tags.append('亏损收窄')
    for e in (stock_evts or []):
        for m in (e.get('matched') or []):
            tag_map = {'GPU': '算力芯片', '国产芯片': '国产替代', '订单': '订单落地',
                       '中标': '中标', '合作': '合作签约', '量产': '量产突破',
                       '发布': '新品发布', '突破': '技术突破', '回购': '回购',
                       '增持': '增持', '减持': '减持', '解禁': '解禁',
                       '评级': '券商评级', '调研': '机构调研', '机器人': '机器人概念'}
            t = tag_map.get(m)
            if t and t not in tags:
                tags.append(t)
    
    if tags or fin_lines:
        lines.append(f"**异动原因：** {' + '.join(tags[:6]) if tags else '暂无明确催化剂'}")
        lines.append('')
    
    if fin_lines:
        lines.append('**业绩亮点：** ' + ' ｜ '.join(fin_lines[1:]))
        lines.append('')
    
    if stock_evts or concept_all:
        level_icon = {'critical': '🔴', 'high': '🟠', 'medium': '⚪'}
        dir_cn = {'positive': '偏利好', 'negative': '偏利空', 'neutral': '中性'}
        n_crit = sum(1 for e in stock_evts if e['level'] == 'critical')
        n_neg = sum(1 for e in stock_evts if e['direction'] == 'negative')
        n_pos = sum(1 for e in stock_evts if e['direction'] == 'positive')
        summary_bits = []
        if n_crit: summary_bits.append(f'{n_crit}项重大风险')
        if n_neg: summary_bits.append(f'{n_neg}项偏利空')
        if n_pos: summary_bits.append(f'{n_pos}项偏利好')
        if stock_evts:
            lines.append(f"**近期重大动态（自动发现{len(stock_evts)}项**：{'、'.join(summary_bits) if summary_bits else '均为中性'}）**")
        
        # 行业原因 vs 公司原因 分组——按内容判定，不按来源通道
        # 公司动作关键词：合作/适配/订单/签署/中标/发布/回购/减持/解禁/财报等
        company_kw = ['合作', '适配', '订单', '签署', '中标', '发布', '回购', '减持', '增持',
                      '解禁', '财报', '年报', '半年报', '业绩', '上市', '融资', '定增', '投产', '量产', '共建']
        sector_kw = ['概念', '板块', '行业', '大会', '政策', '走强', '反弹', '震荡', '提振',
                     '回调', '下跌', '上涨', '领涨', '领跌', '异动']
        
        def is_sector_event(e):
            """判定为行业事件：标题/正文以板块走势为主，且不含公司级动作词"""
            title = e.get('title', '')
            content = (e.get('content', '') or '')[:100]
            text = title + ' ' + content
            has_company_action = any(k in title for k in company_kw)
            has_sector_tone = any(k in title for k in sector_kw)
            # 有公司动作词的标题 → 公司原因（即使从板块通道进来）
            if has_company_action:
                return False
            # 板块走势类标题 → 行业原因
            if has_sector_tone:
                return True
            # 默认按原 label
            return e.get('label') == '板块事件'
        
        sector_evts = [e for e in stock_evts if is_sector_event(e)]
        company_evts = [e for e in stock_evts if not is_sector_event(e)]
        
        if sector_evts or concept_all:
            lines.append('')
            lines.append('**行业原因：**')
            for i, e in enumerate(sector_evts[:4], 1):
                icon = level_icon.get(e['level'], '⚪')
                d = dir_cn.get(e['direction'], '中性')
                t = (e.get('time', '') or '')[:10]
                lines.append(f"{i}. {icon} [{d}] {e['title']}")
                if e.get('content'):
                    lines.append(f"   {e['content'][:260]}")
                if t:
                    lines.append(f"   📅 {t} · {e.get('source', '')}")
            # 板块联动：概念级产业链事件注入（如存储扩产→洁净室工程需求）
            for ev, s, ev_date, _age in concept_all[:2]:
                d2 = dir_cn.get(s.get('expected', 'neutral'), '中性')
                t2 = ev_date.strftime('%Y-%m-%d') if ev_date else ''
                # 清洗高亮标签；标题不含事件关键词时（靠正文误匹配）不展示标题
                ev_title = (ev.get('latest_news', '') or '').replace('<em>', '').replace('</em>', '')
                kw_hit = any(k in ev_title for k in (ev.get('keywords') or []))
                title_part = f" {ev_title[:70]}" if (ev_title and kw_hit) else ''
                lines.append(f"- 🔷 [{d2}·板块联动] 【{ev['type']}】{title_part}".rstrip())
                lines.append(f"   传导逻辑：{s.get('logic', '')}")
                if t2:
                    lines.append(f"   📅 {t2}")
        
        if company_evts:
            lines.append('')
            lines.append('**公司原因：**')
            for i, e in enumerate(company_evts[:5], 1):
                icon = level_icon.get(e['level'], '⚪')
                d = dir_cn.get(e['direction'], '中性')
                t = (e.get('time', '') or '')[:10]
                lines.append(f"{i}. {icon} [{d}] {e['title']}")
                if e.get('content'):
                    lines.append(f"   {e['content'][:260]}")
                if t:
                    lines.append(f"   📅 {t} · {e.get('source', '')}")
        lines.append('')
    else:
        lines.append('**近期重大动态：** 近5日无重大事件信号，走势主要由板块和市场情绪驱动')
        lines.append('')

    # 风险类概念事件进入追踪视图（联动类已注入行业原因，不重复展示）
    related_fresh = [(ev, s, d, a) for ev, s, d, a in concept_all if s.get('expected') == 'negative']

    if related_fresh:
        lines.append(f"**重大事件追踪：**")
        for ev, s, ev_date, age_days in related_fresh:
            status_icon = {
                'confirmed': '✅',
                'contrarian': '🔥',
                'invalidated': '❌',
                'tracking': '⏳',
            }.get(ev.get('status', ''), '⏳')

            date_tag = f"📅{ev_date.strftime('%m-%d')} " if ev_date else ''

            expected_cn = {'positive': '预期利好', 'negative': '预期利空', 'neutral': '预期中性'}.get(s.get('expected'), '?')
            verdict_cn = {
                'confirmed': '验证符合',
                'contrarian': '预期差！反向运行',
                'invalidated': '证伪',
                'pending': '未兑现',
                'as_expected': '符合',
            }.get(s.get('verdict'), '?')

            lines.append(f"- {status_icon} {date_tag}【{ev['type']}】{expected_cn} → 实际{s.get('actual_change', 0):+.1f}% → {verdict_cn}")
            lines.append(f"  逻辑：{s.get('logic', '')}")
            if ev.get('trend_conclusion'):
                lines.append(f"  结论：{ev['trend_conclusion']}")
        lines.append('')

    # 解禁风险
    unlock = data.get('unlock', {}).get(stock_code)
    if unlock:
        if unlock.get('has_warning'):
            lines.append(f"**⚠️ 解禁预警：**")
            for w in unlock['future_warnings']:
                risk_cn = {'HIGH': '🔴 高风险', 'MEDIUM': '🟡 中等', 'LOW': '🟢 低风险'}.get(w['risk'], '?')
                lines.append(f"- {w['date']}（{w['days_until']}天后）：解禁{w['ratio']:.1f}%股本，{risk_cn}")
                lines.append(f"  类型：{w['type']}，解禁市值约{w['mkt_cap']:.0f}万元")
            lines.append('')
        if unlock.get('history'):
            lines.append(f"**历史解禁影响：**")
            for h in unlock['history'][-3:]:
                lines.append(f"- {h['date']}（解禁{h['ratio']:.1f}%）：{h['pattern']}")
            lines.append('')

    return lines if lines else ['暂无相关重大事件']


# ========== 主函数 ==========
if __name__ == '__main__':
    from deep_analysis import load_portfolio
    stocks = load_portfolio()
    report = run_event_analysis(stocks)

    print(f"\n{'='*50}")
    print(f"识别事件：{len(report['events'])} 个")
    for ev in report['events']:
        print(f"  【{ev['type']}】{ev.get('status', '?')} - {ev.get('trend_conclusion', '')[:50]}")

    print(f"\n解禁预警：")
    for code, u in report['unlock'].items():
        if u.get('has_warning'):
            print(f"  ⚠️ {code} {u['name']}: {len(u['future_warnings'])} 条预警")
