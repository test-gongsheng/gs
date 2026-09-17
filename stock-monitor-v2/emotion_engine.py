# -*- coding: utf-8 -*-
"""
市场情绪引擎
第三层：群体心理周期（涨跌家数、涨停、连板、炸板率）
第四层：板块生态（板块强度、龙头识别、轮动状态）
数据源：腾讯行情API（稳定，不依赖akshare）
"""
import os
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

_session = requests.Session()
_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

# ========== 板块映射（与deep_analysis.py保持一致） ==========
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

# 板块成分股（用于计算板块情绪和个股地位，手动维护核心标的）
SECTOR_COMPONENTS = {
    '半导体-GPU': ['688795', '688256', '688521', '688041', '603893'],
    '半导体-存储': ['301308', '688525', '603986', '002049', '688347'],
    '半导体设备与服务': ['601133', '688012', '002371', '603690', '688082'],
    '数据中心/IDC': ['300442', '600845', '000977', '603296', '300383'],
    'AI应用-NLP': ['300229', '002230', '688228', '300624', '002415'],
    '光伏设备': ['300316', '601012', '002459', '600438', '688599'],
    '汽车零部件-热管理': ['002050', '603786', '600741', '002126'],
    '汽车零部件': ['000559', '000887', '601799', '603305'],
    '新能源汽车': ['002594', '601127', '600104', '000625'],
    '有色金属-铜': ['000878', '600362', '601899', '000630'],
    '有色金属-铝': ['601600', '600219', '000807', '601702'],
    '消费电子': ['00285', '002475', '000049', '300433'],
    '互联网-平台': ['00700', '09626', '01024', '09999'],
    '互联网-电商': ['09988', '09618', '01024', '03690'],
}

# 主要指数
INDEX_CODES = {
    'sh000001': '上证指数',
    'sz399001': '深证成指',
    'sz399006': '创业板指',
    'sh000688': '科创50',
    'hkHSI': '恒生指数',
}

# 情绪周期阈值
SENTIMENT_STAGES = [
    (0, 20, '冰点期', '市场情绪冰冻，跌停>涨停，强势股补跌。策略：减仓/观望，等待恐慌释放完毕'),
    (20, 40, '修复期', '涨停回升，高度1-2板，资金试探。策略：轻仓试探主线龙头'),
    (40, 70, '发酵期', '连板梯队成形，主线清晰，赚钱效应扩散。策略：积极参与主线'),
    (70, 90, '高潮期', '涨停潮，情绪过热，百股涨停。策略：持股待抛，不追高，准备撤退'),
    (90, 101, '退潮期', '高位股炸板，中位掉队，亏钱效应蔓延。策略：快速撤离，空仓观望'),
]


@dataclass
class MarketSentiment:
    """市场情绪快照"""
    date: str
    # 大盘
    index_changes: Dict[str, float] = field(default_factory=dict)  # 指数涨跌幅
    total_amount: float = 0  # 总成交额（亿）
    amount_change_pct: float = 0  # 成交额环比
    # 涨跌家数
    up_count: int = 0
    down_count: int = 0
    flat_count: int = 0
    up_down_ratio: float = 0  # 涨跌比
    # 涨停跌停
    limit_up_count: int = 0
    limit_down_count: int = 0
    broken_limit_count: int = 0  # 炸板家数（估算）
    limit_up_ratio: float = 0  # 涨停/跌停比
    # 连板
    max_continuous_limit: int = 0  # 最高连板
    continuous_2plus: int = 0  # 2板以上家数
    # 评分
    sentiment_score: float = 50  # 0-100
    stage: str = '中性'
    stage_advice: str = ''
    # 历史
    prev_score: Optional[float] = None
    score_change: float = 0


@dataclass
class SectorSentiment:
    """板块情绪"""
    sector: str
    avg_change: float = 0  # 板块平均涨跌幅
    limit_up_count: int = 0  # 板块内涨停家数
    leader_code: str = ''  # 龙头代码
    leader_name: str = ''
    leader_change: float = 0  # 龙头涨幅
    rank: int = 0  # 板块强度排名（1=最强）
    rotation_state: str = 'unknown'  # main_line / rotation / cooling
    # 个股地位
    stock_rank_in_sector: int = 0  # 个股在板块内涨幅排名
    stock_position: str = 'unknown'  # leader / mid / follower


def get_realtime_quotes(codes: List[str]) -> Dict[str, Dict]:
    """腾讯批量行情，每次最多约50只"""
    result = {}
    for i in range(0, len(codes), 50):
        batch = codes[i:i+50]
        tc_codes = []
        for c in batch:
            if c.startswith('6'):
                tc_codes.append(f'sh{c}')
            elif c.startswith(('0', '3')):
                tc_codes.append(f'sz{c}')
            elif c.startswith(('00', '01', '02', '03', '07', '09')) and len(c) == 5:
                tc_codes.append(f'hk{c}')
            else:
                tc_codes.append(f'sh{c}')  # 指数等
        url = f'http://qt.gtimg.cn/q={",".join(tc_codes)}'
        try:
            resp = _session.get(url, timeout=10)
            resp.encoding = 'gbk'
            for line in resp.text.split(';'):
                if '~' not in line:
                    continue
                parts = line.split('~')
                if len(parts) < 35:
                    continue
                code = parts[2]
                result[code] = {
                    'name': parts[1],
                    'price': float(parts[3]) if parts[3] else 0,
                    'prev_close': float(parts[4]) if parts[4] else 0,
                    'open': float(parts[5]) if parts[5] else 0,
                    'high': float(parts[6]) if parts[6] else 0,
                    'low': float(parts[7]) if parts[7] else 0,
                    'volume': float(parts[8]) if parts[8] else 0,  # 手
                    'amount': float(parts[9]) if parts[9] else 0,  # 万元
                    'change_pct': float(parts[32]) if parts[32] else 0,
                    'turnover': float(parts[38]) if len(parts) > 38 and parts[38] else 0,  # 换手率
                    'pe': float(parts[39]) if len(parts) > 39 and parts[39] else 0,
                    'mkt_cap': float(parts[45]) if len(parts) > 45 and parts[45] else 0,  # 总市值(亿)
                    'float_cap': float(parts[44]) if len(parts) > 44 and parts[44] else 0,  # 流通市值(亿)
                }
        except Exception as e:
            print(f'[行情] 批次 {i} 失败: {e}')
        time.sleep(0.2)
    return result


def is_limit_up(change_pct: float, code: str) -> bool:
    """判断是否涨停"""
    if code.startswith(('300', '301', '688')):
        return change_pct >= 19.5  # 20cm
    elif code.startswith(('8', '4')):
        return change_pct >= 29.5  # 30cm（北交所）
    else:
        return change_pct >= 9.5  # 10cm


def is_limit_down(change_pct: float, code: str) -> bool:
    """判断是否跌停"""
    if code.startswith(('300', '301', '688')):
        return change_pct <= -19.5
    elif code.startswith(('8', '4')):
        return change_pct <= -29.5
    else:
        return change_pct <= -9.5


def get_all_a_share_codes() -> List[str]:
    """获取全市场A股代码（用腾讯接口的板块数据估算）"""
    # 由于全市场扫描太慢，用主要指数成分+活跃股代替
    # 更实用的方案：扫描主要板块指数+持仓股板块
    codes = []
    # 上证指数范围（主要股票）
    # 实际采用：抓取腾讯涨速榜/成交额榜
    url = 'http://qt.gtimg.cn/q=sh000001,sz399001,sz399006,sh000688'
    try:
        resp = _session.get(url, timeout=10)
        resp.encoding = 'gbk'
        # 无法直接获取全量，用静态列表+动态更新
    except:
        pass

    # 使用一个实用的近似：沪深两市主板+创业板+科创板常见代码段
    # 只扫描有实际意义的（避免扫描全部5000+只，太慢）
    # 实际方案：通过成交额排行获取活跃股
    return codes


def scan_market_breadth() -> Tuple[int, int, int, int, int]:
    """
    扫描市场涨跌家数和涨停跌停数
    方案：由于全市场5000+只扫描太慢（腾讯API每批50只，需要100+次请求），
    采用抽样扫描：主要指数成分 + 各板块成分股 + 成交额活跃股
    """
    # 收集所有需要扫描的代码
    scan_codes = set()

    # 1. 持仓股板块成分
    for sector, codes in SECTOR_COMPONENTS.items():
        scan_codes.update(codes)

    # 2. 主要指数（通过腾讯的板块接口获取成分）
    # 用东方财富的行业板块数据补充
    try:
        url = 'http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=500&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f2,f3,f12,f14'
        resp = _session.get(url, timeout=15)
        data = resp.json()
        if data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff']:
                code = str(item.get('f12', ''))
                if code:
                    scan_codes.add(code)
    except Exception as e:
        print(f'[东财] 成分获取失败: {e}')

    # 3. 扫描所有收集到的代码
    all_codes = list(scan_codes)
    print(f'[扫描] 共 {len(all_codes)} 只样本股')

    quotes = get_realtime_quotes(all_codes)

    up = down = flat = limit_up = limit_down = 0
    for code, q in quotes.items():
        chg = q['change_pct']
        if chg > 0.01:
            up += 1
        elif chg < -0.01:
            down += 1
        else:
            flat += 1

        if is_limit_up(chg, code):
            limit_up += 1
        elif is_limit_down(chg, code):
            limit_down += 1

    return up, down, flat, limit_up, limit_down


def get_limit_up_pool() -> List[Dict]:
    """获取今日涨停池（东财数据）"""
    try:
        url = ('https://push2ex.eastmoney.com/getTopicZTPool?'
               'ut=7eea3edcaed734bea9chwe2ab2d6c49d&dpt=wz.ztzt&'
               'Pageindex=0&pagesize=100&sort=fbt%3Aasc')
        resp = _session.get(url, timeout=15)
        data = resp.json()
        pool = []
        if data.get('data') and data['data'].get('pool'):
            for item in data['data']['pool']:
                pool.append({
                    'code': item.get('c', ''),
                    'name': item.get('n', ''),
                    'price': item.get('p', 0) / 1000,
                    'change_pct': item.get('zdp', 0),
                    'continuous': item.get('days', 0),  # 连板天数
                    'first_time': item.get('fbt', ''),  # 首次封板时间
                    'broken': item.get('fund', 0) > 0,  # 是否炸板
                    'amount': item.get('amount', 0),
                })
        return pool
    except Exception as e:
        print(f'[涨停池] 获取失败: {e}')
        return []


def get_sector_sentiment(portfolio_sectors: List[str] = None) -> List[SectorSentiment]:
    """计算板块情绪"""
    sectors = portfolio_sectors or list(SECTOR_COMPONENTS.keys())
    results = []

    for sector in sectors:
        codes = SECTOR_COMPONENTS.get(sector, [])
        if not codes:
            continue

        quotes = get_realtime_quotes(codes)
        if not quotes:
            continue

        changes = [(c, q['change_pct']) for c, q in quotes.items()]
        avg_chg = sum(c for _, c in changes) / len(changes)

        # 板块内涨停数
        sector_limit_up = sum(1 for c, chg in changes if is_limit_up(chg, c))

        # 龙头（涨幅最高的）
        changes.sort(key=lambda x: x[1], reverse=True)
        leader_code, leader_chg = changes[0]
        leader_name = quotes.get(leader_code, {}).get('name', '')

        results.append(SectorSentiment(
            sector=sector,
            avg_change=round(avg_chg, 2),
            limit_up_count=sector_limit_up,
            leader_code=leader_code,
            leader_name=leader_name,
            leader_change=round(leader_chg, 2),
        ))

    # 排名
    results.sort(key=lambda x: x.avg_change, reverse=True)
    for i, s in enumerate(results):
        s.rank = i + 1

    # 轮动判断
    if results:
        top_changes = [s.avg_change for s in results[:3]]
        bottom_changes = [s.avg_change for s in results[-3:]]
        spread = top_changes[0] - bottom_changes[-1] if bottom_changes else 0

        if spread > 3:
            top_sector = results[0].sector
            for s in results:
                if s.rank == 1 and s.limit_up_count >= 2:
                    s.rotation_state = 'main_line'
                elif s.avg_change < 0:
                    s.rotation_state = 'cooling'
                else:
                    s.rotation_state = 'rotation'
        else:
            for s in results:
                s.rotation_state = 'rotation'

    return results


def calc_sentiment_score(up: int, down: int, limit_up: int, limit_down: int,
                         max_board: int, board_2plus: int,
                         prev_score: float = None) -> Tuple[float, str, str]:
    """
    计算情绪评分（0-100）
    综合：涨跌比、涨停跌停比、连板高度
    """
    score = 50.0  # 基准中性

    # 涨跌比贡献（-15 ~ +15）
    total = up + down
    if total > 0:
        ud_ratio = up / total
        score += (ud_ratio - 0.5) * 30  # 全涨+15，全跌-15

    # 涨停跌停贡献（-20 ~ +20）
    if limit_down > 0:
        ld_ratio = limit_up / limit_down
        score += min(ld_ratio * 5, 20) - 10
    elif limit_up > 0:
        score += min(limit_up * 0.5, 20)  # 无跌停时涨停加分

    # 连板高度贡献（-10 ~ +10）
    if max_board >= 5:
        score += 10
    elif max_board >= 3:
        score += 5
    elif max_board <= 1 and limit_up > 0:
        score -= 5
    elif max_board == 0:
        score -= 10

    score = max(0, min(100, score))

    # 判定阶段
    stage = '中性'
    advice = ''
    for lo, hi, name, desc in SENTIMENT_STAGES:
        if lo <= score < hi:
            stage = name
            advice = desc
            break

    return round(score, 1), stage, advice


def analyze_portfolio_sentiment(stocks: List[Dict]) -> List[Dict]:
    """
    分析每只持仓股的情绪影响
    返回：个股情绪分析列表
    """
    results = []

    # 获取板块情绪
    portfolio_sectors = list(set(SECTOR_MAP.get(s['code'], '未知') for s in stocks))
    sector_sentiments = get_sector_sentiment(portfolio_sectors)

    # 获取行情
    all_codes = [s['code'] for s in stocks]
    quotes = get_realtime_quotes(all_codes)

    # 获取大盘
    index_quotes = get_realtime_quotes(list(INDEX_CODES.keys()))

    for stock in stocks:
        code = stock['code']
        sector = SECTOR_MAP.get(code, '未知')
        quote = quotes.get(code, {})
        price = quote.get('price', 0)
        change_pct = quote.get('change_pct', 0)
        avg_cost = stock.get('avg_cost', 0)
        shares = stock.get('shares', 0)

        # 找板块情绪
        sector_senti = next((s for s in sector_sentiments if s.sector == sector), None)

        # 个股在板块内的地位
        position = 'unknown'
        if sector_senti:
            # 与龙头对比
            if code == sector_senti.leader_code:
                position = 'leader'
            elif change_pct > sector_senti.avg_change:
                position = 'strong_follower'
            elif change_pct > 0:
                position = 'follower'
            else:
                position = 'laggard'

        # 情绪beta（简化：近期波动率，可用历史数据改进）
        # 用换手率+振幅估算
        amplitude = 0
        prev = quote.get('prev_close', 0)
        if quote.get('high') and quote.get('low') and prev and prev > 0.01:
            amplitude = (quote['high'] - quote['low']) / prev * 100
            amplitude = min(amplitude, 25)  # 上限保护，排除数据异常

        # 成本位置
        cost_position = ''
        if avg_cost > 0 and price > 0:
            gap = (price / avg_cost - 1) * 100
            if gap < -30:
                cost_position = f'深度套牢({gap:.0f}%)，反弹至成本区有解套抛压'
            elif gap < -10:
                cost_position = f'中度浮亏({gap:.0f}%)'
            elif gap < 0:
                cost_position = f'轻度浮亏({gap:.0f}%)'
            elif gap < 10:
                cost_position = f'小幅盈利(+{gap:.0f}%)'
            else:
                cost_position = f'盈利(+{gap:.0f}%)，注意止盈节奏'

        # 综合情绪判断
        sentiment_impact = ''
        if sector_senti:
            if sector_senti.rotation_state == 'main_line' and position in ('leader', 'strong_follower'):
                sentiment_impact = f'🔥 板块主线+个股强势，情绪顺风'
            elif sector_senti.rotation_state == 'main_line':
                sentiment_impact = f'✅ 板块主线，但个股偏弱，关注补涨机会'
            elif sector_senti.rotation_state == 'cooling':
                sentiment_impact = f'⚠️ 板块退潮，注意减仓'
            elif sector_senti.avg_change < -1:
                sentiment_impact = f'❌ 板块领跌，情绪逆风'
            else:
                sentiment_impact = f'➡️ 板块震荡，情绪中性'

        results.append({
            'code': code,
            'name': stock.get('name', ''),
            'sector': sector,
            'price': price,
            'change_pct': change_pct,
            'position_in_sector': position,
            'sector_avg_change': sector_senti.avg_change if sector_senti else 0,
            'sector_rank': sector_senti.rank if sector_senti else 0,
            'sector_limit_up': sector_senti.limit_up_count if sector_senti else 0,
            'leader': f"{sector_senti.leader_name}({sector_senti.leader_change:+.1f}%)" if sector_senti else '',
            'rotation_state': sector_senti.rotation_state if sector_senti else 'unknown',
            'amplitude': round(amplitude, 2),
            'cost_position': cost_position,
            'sentiment_impact': sentiment_impact,
        })

    return results


def generate_sentiment_report(stocks: List[Dict]) -> Dict:
    """
    生成完整市场情绪报告
    每日收盘后运行
    """
    today = datetime.now().strftime('%Y-%m-%d')
    print(f'[情绪引擎] {today} 开始分析...')

    # 1. 扫描市场广度
    up, down, flat, limit_up, limit_down = scan_market_breadth()
    print(f'[扫描] 涨{up} 跌{down} 平{flat} | 涨停{limit_up} 跌停{limit_down}')

    # 2. 涨停池和连板数据
    limit_pool = get_limit_up_pool()
    max_board = max((s.get('continuous', 0) for s in limit_pool), default=0)
    board_2plus = sum(1 for s in limit_pool if s.get('continuous', 0) >= 2)
    broken = sum(1 for s in limit_pool if s.get('broken'))
    print(f'[连板] 最高{max_board}板，2板+{board_2plus}家，炸板{broken}家')

    # 3. 大盘指数
    index_quotes = get_realtime_quotes(list(INDEX_CODES.keys()))
    index_changes = {INDEX_CODES.get(k, k): q['change_pct'] for k, q in index_quotes.items()}

    # 4. 计算情绪评分
    prev_data = _load_latest_sentiment()
    prev_score = prev_data.get('sentiment_score') if prev_data else None

    score, stage, advice = calc_sentiment_score(
        up, down, limit_up, limit_down, max_board, board_2plus, prev_score
    )

    # 5. 板块情绪
    portfolio_sectors = list(set(SECTOR_MAP.get(s['code'], '未知') for s in stocks))
    sector_sentiments = get_sector_sentiment(portfolio_sectors)

    # 6. 个股情绪分析
    stock_sentiments = analyze_portfolio_sentiment(stocks)

    # 汇总
    report = {
        'date': today,
        'sentiment_score': score,
        'stage': stage,
        'stage_advice': advice,
        'score_change': round(score - prev_score, 1) if prev_score else 0,
        'market_breadth': {
            'up': up, 'down': down, 'flat': flat,
            'up_down_ratio': round(up / max(down, 1), 2),
        },
        'limit_up_down': {
            'limit_up': limit_up,
            'limit_down': limit_down,
            'broken': broken,
            'max_continuous': max_board,
            'board_2plus': board_2plus,
        },
        'index_changes': index_changes,
        'sectors': [asdict(s) for s in sector_sentiments],
        'stocks': stock_sentiments,
    }

    # 保存
    _save_sentiment(report)
    return report


def _save_sentiment(data: Dict):
    """保存情绪数据（历史累积）"""
    filepath = os.path.join(DATA_DIR, 'market_sentiment.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 也保存历史
    history_file = os.path.join(DATA_DIR, 'sentiment_history.json')
    history = []
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
    history.append({'date': data['date'], 'score': data['sentiment_score'], 'stage': data['stage']})
    # 只保留最近90天
    history = history[-90:]
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _load_latest_sentiment() -> Optional[Dict]:
    filepath = os.path.join(DATA_DIR, 'market_sentiment.json')
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def format_sentiment_for_report(stock_code: str) -> List[str]:
    """格式化个股情绪分析，供deep_analysis.py引用"""
    filepath = os.path.join(DATA_DIR, 'market_sentiment.json')
    if not os.path.exists(filepath):
        return ['市场情绪数据尚未生成']

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    lines = []
    data_date = data.get('date', '')
    date_tag = f"（数据时间：{data_date}）" if data_date else ''
    lines.append(f"**市场情绪周期：** {data['stage']}（评分 {data['sentiment_score']}/100，"
                 f"较昨日{data.get('score_change', 0):+.0f}分）{date_tag}")
    lines.append(f"- {data['stage_advice']}")
    lines.append(f"- 今日涨跌：涨{data['market_breadth']['up']}家 / 跌{data['market_breadth']['down']}家，"
                 f"涨停{data['limit_up_down']['limit_up']}家 / 跌停{data['limit_up_down']['limit_down']}家")
    if data['limit_up_down']['max_continuous'] > 0:
        lines.append(f"- 最高连板：{data['limit_up_down']['max_continuous']}板，"
                     f"2板以上{data['limit_up_down']['board_2plus']}家")
    lines.append('')

    # 找个股情绪
    stock_s = next((s for s in data.get('stocks', []) if s['code'] == stock_code), None)
    if stock_s:
        lines.append(f"**板块情绪（{stock_s['sector']}）：**")
        lines.append(f"- 板块涨幅：{stock_s['sector_avg_change']:+.2f}%（排名第{stock_s['sector_rank']}）")
        lines.append(f"- 板块涨停：{stock_s['sector_limit_up']}家"
                     + (f"，龙头：{stock_s['leader']}" if stock_s['leader'] else ''))
        state_desc = {
            'main_line': '主线板块',
            'rotation': '轮动中',
            'cooling': '退潮冷却',
            'unknown': '未知',
        }
        lines.append(f"- 轮动状态：{state_desc.get(stock_s['rotation_state'], stock_s['rotation_state'])}")
        lines.append('')

        lines.append(f"**个股情绪地位：**")
        pos_desc = {
            'leader': '板块龙头',
            'strong_follower': '强势跟风',
            'follower': '跟风',
            'laggard': '滞涨',
            'unknown': '未知',
        }
        lines.append(f"- 今日涨跌：{stock_s['change_pct']:+.2f}%，"
                     f"板块内定位：{pos_desc.get(stock_s['position_in_sector'], '?')}")
        lines.append(f"- 振幅：{min(stock_s['amplitude'], 25):.1f}%（情绪敏感度参考）")
        lines.append(f"- {stock_s['sentiment_impact']}")
        if stock_s.get('cost_position'):
            lines.append(f"- 持仓状态：{stock_s['cost_position']}")
        lines.append('')

    return lines


# ========== 主函数 ==========
if __name__ == '__main__':
    # 测试
    from deep_analysis import load_portfolio
    stocks = load_portfolio()
    report = generate_sentiment_report(stocks)

    print(f"\n{'='*50}")
    print(f"情绪评分：{report['sentiment_score']}/100 → {report['stage']}")
    print(f"建议：{report['stage_advice']}")
    print(f"涨跌：{report['market_breadth']['up']}涨 "
          f"{report['market_breadth']['down']}跌 | "
          f"涨停{report['limit_up_down']['limit_up']} "
          f"跌停{report['limit_up_down']['limit_down']}")
    print(f"最高连板：{report['limit_up_down']['max_continuous']}板")

    print(f"\n板块排名：")
    for s in report['sectors'][:5]:
        print(f"  #{s['rank']} {s['sector']}: {s['avg_change']:+.2f}% "
              f"(涨停{s['limit_up_count']}) [{s['rotation_state']}]")

    print(f"\n持仓情绪影响：")
    for s in report['stocks']:
        print(f"  {s['code']} {s['name']}: {s['sentiment_impact']}")
