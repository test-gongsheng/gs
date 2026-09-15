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
    'medium': {'keywords': ['发布', '上市', '收购', '合作', '突破'],
               'score': 50},
}


# ========== 新闻采集 ==========
def _fetch_akshare_with_timeout(timeout_sec=15) -> Optional[List[Dict]]:
    """akshare调用带超时保护（防止卡死）"""
    import signal
    def handler(signum, frame):
        raise TimeoutError('akshare timeout')
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout_sec)
    try:
        import akshare as ak
        df = ak.stock_info_global_cls(symbol="电报")
        signal.alarm(0)
        if df is not None and len(df) > 0:
            news = []
            for _, row in df.head(100).iterrows():
                news.append({
                    'title': str(row.get('标题', '')),
                    'content': str(row.get('内容', ''))[:500],
                    'time': str(row.get('发布日期', '')),
                    'source': '财联社',
                })
            return news
    except Exception as e:
        signal.alarm(0)
        print(f'[财联社] akshare失败: {e}')
    return None


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
                "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "time", "pageIndex": 1, "pageSize": 20}}
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
                        })
            print(f'[东财] "{kw}" 获取 {len(news)} 条累计')
        except Exception as e:
            print(f'[东财] "{kw}" 失败: {e}')
        time.sleep(0.5)

    return news[:50]  # 限制总量


def fetch_stock_news(stock_codes: List[str]) -> Dict[str, List[Dict]]:
    """获取持仓股相关新闻（带超时保护）"""
    result = {}
    for code in stock_codes[:14]:  # 限制只查持仓股
        try:
            encoded = requests.utils.quote(json.dumps({
                "uid": "", "keyword": code, "type": ["cmsArticleWebOld"],
                "client": "web", "clientVersion": "curr", "clientType": "web",
                "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "time", "pageIndex": 1, "pageSize": 5}}
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
                result[code] = [{
                    'title': a.get('title', ''),
                    'time': a.get('date', ''),
                    'source': a.get('mediaName', ''),
                } for a in (articles[:5] if isinstance(articles, list) else [])]
            else:
                result[code] = []
        except Exception as e:
            result[code] = []
        time.sleep(0.3)
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
    stock_news = fetch_stock_news(stock_codes)

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


def format_event_for_report(stock_code: str) -> List[str]:
    """格式化个股事件影响，供deep_analysis.py引用"""
    filepath = os.path.join(DATA_DIR, 'event_impact.json')
    if not os.path.exists(filepath):
        return ['事件数据尚未生成']

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    lines = []

    # 相关事件
    related = []
    for ev in data.get('events', []):
        for s in ev.get('impacted_stocks', []):
            if s['code'] == stock_code:
                related.append((ev, s))

    if related:
        lines.append(f"**重大事件追踪：**")
        for ev, s in related:
            status_icon = {
                'confirmed': '✅',
                'contrarian': '🔥',
                'invalidated': '❌',
                'tracking': '⏳',
            }.get(ev.get('status', ''), '⏳')

            expected_cn = {'positive': '预期利好', 'negative': '预期利空', 'neutral': '预期中性'}.get(s.get('expected'), '?')
            verdict_cn = {
                'confirmed': '验证符合',
                'contrarian': '预期差！反向运行',
                'invalidated': '证伪',
                'pending': '未兑现',
                'as_expected': '符合',
            }.get(s.get('verdict'), '?')

            lines.append(f"- {status_icon} 【{ev['type']}】{expected_cn} → 实际{s.get('actual_change', 0):+.1f}% → {verdict_cn}")
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
