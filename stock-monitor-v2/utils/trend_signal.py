"""
趋势信号引擎 (Trend Signal Engine)
===================================
汇聚多层信号源，为每只股票输出趋势状态 + 中轴策略冻结/解冻判断 + 一句话结论。

信号分层（按时间先后）：
  第一层·领先信号（比价格早1-4周）
    ① ETF资金流（大盘级，market_regime.json）
    ② 融资余额趋势（个股级，margin/*.json）
    ③ 产业资本动向（个股级，shareholders/*.json + 解禁/大宗/减持预披露）
    ④ 投行评级边际变化（个股级，research_reports/*.json）
  第二层·同步确认
    ⑤ 事件验证率（主题级，event_verification_stats.json）
    ⑥ 板块强弱（后续接入）
  第三层·滞后过滤
    ⑦ 均线排列（个股级，tech_snapshot_*.json）→ 只调仓位上限，不产生买卖信号

数据滞后自动降权：asof距今>7天 权重×0.5；>30天 标记stale不计分。
输出: data/trend_signals.json

用法：
  python utils/trend_signal.py            # 全量计算
  python utils/trend_signal.py --code 688795  # 单只股票调试
"""

import json
import os
import sys
import math
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, 'data')

# ============ 信号权重配置 ============
WEIGHTS = {
    'etf_flow': 25,
    'etf_flow_hk': 10,  # 港股：A股ETF信号参考性弱，降权
    'margin': 15,
    'industrial_capital': 10,
    'research': 15,
    'event_verification': 10,
}

# 冻结/解冻阈值
FREEZE_THRESHOLD = -15
UNFREEZE_THRESHOLD = 25

# 数据滞后降权
STALE_DAYS_WARN = 7
STALE_DAYS_SKIP = 30

# 机构名称归一化映射（同一机构在不同数据源里的不同写法）
INSTITUTION_ALIAS = {
    'UBSAG': 'UBS',
    'UBS AG': 'UBS',
    'MORGANSTANLEY&CO.INTERNATIONALPLC.': 'MORGAN_STANLEY',
    'MORGAN STANLEY & CO. INTERNATIONAL PLC.': 'MORGAN_STANLEY',
    'MORGAN STANLEY': 'MORGAN_STANLEY',
    'GOLDMANSACHSBANKEUROPESE－自有资金－QFII': 'GOLDMAN_SACHS',
    'GOLDMAN SACHS BANK EUROPE SE': 'GOLDMAN_SACHS',
    'GOLDMAN SACHS': 'GOLDMAN_SACHS',
    'J.P.MorganSecuritiesPLC－自有资金': 'JPMORGAN',
    'J.P. MORGAN SECURITIES PLC': 'JPMORGAN',
    'J.P.MORGAN': 'JPMORGAN',
    'JPMORGAN': 'JPMORGAN',
}


def normalize_institution(name):
    """归一化机构名称，避免同一机构因格式差异被误判为新进/退出"""
    upper = name.upper().strip()
    # 先查精确映射
    if upper in INSTITUTION_ALIAS:
        return INSTITUTION_ALIAS[upper]
    # 关键词模糊匹配
    if 'UBS' in upper:
        return 'UBS'
    if 'MORGAN' in upper and 'STANLEY' in upper:
        return 'MORGAN_STANLEY'
    if 'GOLDMAN' in upper and 'SACHS' in upper:
        return 'GOLDMAN_SACHS'
    if 'J.P.MORGAN' in upper.replace(' ', '') or 'JPMORGAN' in upper.replace(' ', ''):
        return 'JPMORGAN'
    if 'HSBC' in upper:
        return 'HSBC'
    if 'BARCLAYS' in upper:
        return 'BARCLAYS'
    if 'DEUTSCHE' in upper:
        return 'DEUTSCHE'
    if 'CITIGROUP' in upper or 'CITI ' in upper:
        return 'CITI'
    if 'NOMURA' in upper:
        return 'NOMURA'
    if 'SCHRODERS' in upper:
        return 'SCHRODERS'
    if 'FIDELITY' in upper:
        return 'FIDELITY'
    if 'POINT72' in upper:
        return 'POINT72'
    if 'BRIDGEWATER' in upper:
        return 'BRIDGEWATER'
    return upper  # 无法归一化的保留原名

# 板块→主题映射（事件验证率按主题统计，需映射到个股所属主题）
SECTOR_THEME_MAP = {
    '半导体': ['算力基建', 'AI军备', '存储周期', '出口管制'],
    '新能源汽车': ['机器人产业'],
    '汽车零部件': ['机器人产业'],
    '光伏设备': [],
    '消费电子': ['AI军备'],
    '算力': ['算力基建', 'AI军备'],
    '存储': ['存储周期', '算力基建'],
    '铜': ['资源周期'],
    '铝': ['资源周期'],
    '有色': ['资源周期'],
    'AI': ['AI军备', '算力基建'],
    '信创': ['AI军备'],
    '软件': ['AI军备'],
    '互联网': ['AI军备'],
    '电子': ['AI军备', '存储周期'],
}

# 个股→板块映射（stocks.json无板块字段时用代码前缀判断）
CODE_SECTOR_MAP = {
    '000559': '汽车零部件',
    '000878': '铜',
    '002050': '汽车零部件',
    '002594': '新能源汽车',
    '300229': '软件',
    '300316': '光伏设备',
    '300442': '算力',
    '301308': '存储',
    '601133': '半导体',
    '601600': '铝',
    '688795': '半导体',
    '00285': '消费电子',
    '00700': '互联网',
    '09988': '互联网',
}


def load_json(path, default=None):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def days_since(date_str):
    """计算距今天数，支持 YYYY-MM-DD / YYYYMMDD / YYYY-MM-DD HH:MM"""
    if not date_str:
        return 999
    try:
        s = str(date_str).strip().replace('-', '').replace(':', '').replace(' ', '')
        if len(s) >= 8:
            d = datetime.strptime(s[:8], '%Y%m%d')
            return (datetime.now() - d).days
    except Exception:
        pass
    return 999


def weight_with_stale_penalty(weight, age_days):
    """数据滞后降权"""
    if age_days > STALE_DAYS_SKIP:
        return 0  # stale，不计分
    if age_days > STALE_DAYS_WARN:
        return weight * 0.5
    return weight


# ============================================================
# ① ETF资金流信号（大盘级）
# ============================================================
def signal_etf_flow(regime_data, market='A股'):
    """
    regime: bottom_signal → 底部信号（看多）
            top_signal → 顶部信号（看空）
            observation → 观察中，看strength
    港股降权：A股ETF资金流对港股仅作弱参考
    """
    base_weight = WEIGHTS['etf_flow_hk'] if market == '港股' else WEIGHTS['etf_flow']

    if not regime_data:
        return {
            'key': 'etf_flow', 'label': 'ETF资金流',
            'state': 'stale', 'score': 0, 'weight': 0,
            'detail': '市场状态数据不可用', 'asof': None,
        }

    asof = regime_data.get('asof_date', '')
    regime = regime_data.get('regime', '')
    strength = regime_data.get('strength', 50)
    w = weight_with_stale_penalty(base_weight, days_since(asof))

    if w == 0:
        return {
            'key': 'etf_flow', 'label': 'ETF资金流',
            'state': 'stale', 'score': 0, 'weight': 0,
            'detail': f'数据截至{asof}，已过期未更新', 'asof': asof,
        }

    pools = regime_data.get('pools', {})
    broad = pools.get('broad', {})

    if regime == 'bottom_signal':
        score = 60
        detail = f'底部信号确认（宽基5日+{broad.get("flow_5d", 0):.0f}亿/单日+{broad.get("flow_1d", 0):.0f}亿，资金在吸筹）'
    elif regime == 'top_signal':
        score = -60
        detail = f'顶部信号确认（宽基资金持续流出，聪明钱在派发）'
    elif regime == 'observation':
        # 观察期：strength 0-100 映射到 -20 ~ +20
        score = round((strength - 50) * 0.4)
        detail = f'观察期（强度{strength}，宽基5日{broad.get("flow_5d", 0):+.0f}亿）'
    else:
        score = 0
        detail = f'无明显信号（状态{regime}）'

    return {
        'key': 'etf_flow', 'label': 'ETF资金流',
        'state': 'positive' if score > 10 else 'negative' if score < -10 else 'neutral',
        'score': score, 'weight': w,
        'detail': detail, 'asof': asof,
    }


# ============================================================
# ② 融资余额趋势（个股级）
# ============================================================
def signal_margin(code):
    """
    取最近20条记录，线性回归判断趋势：
      斜率显著为负 + 持续天数>=5 → 杠杆在出清（领先见底信号，但对中轴是"还在跌"）
      斜率显著为正 → 杠杆回流
      高位+暴升 → 散户在追杠杆，警惕
    """
    path = os.path.join(DATA_DIR, 'margin', f'{code}.json')
    data = load_json(path)
    records = data.get('records', []) if data else []

    if len(records) < 10:
        return {
            'key': 'margin', 'label': '融资余额',
            'state': 'stale', 'score': 0, 'weight': 0,
            'detail': '融资余额数据不足', 'asof': None,
        }

    last = records[-1]
    asof = last.get('date', '')
    age = days_since(asof)
    w = weight_with_stale_penalty(WEIGHTS['margin'], age)

    if w == 0:
        return {
            'key': 'margin', 'label': '融资余额',
            'state': 'stale', 'score': 0, 'weight': 0,
            'detail': f'数据截至{asof}，已{age}天未更新', 'asof': asof,
        }

    # 最近20条
    recent = records[-20:]
    rzye = [r.get('rzye', 0) for r in recent]

    if len(rzye) < 5 or all(v == 0 for v in rzye):
        return {
            'key': 'margin', 'label': '融资余额',
            'state': 'neutral', 'score': 0, 'weight': w,
            'detail': '该股两融余额为零或数据缺失（可能非两融标的）', 'asof': asof,
        }

    # 线性回归斜率
    n = len(rzye)
    x = list(range(n))
    x_mean = sum(x) / n
    y_mean = sum(rzye) / n
    numerator = sum((x[i] - x_mean) * (rzye[i] - y_mean) for i in range(n))
    denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
    slope = numerator / denominator if denominator != 0 else 0
    slope_pct = (slope * n) / y_mean * 100 if y_mean != 0 else 0  # 20日累计变化%

    # 高位判断：当前余额 vs 窗口内最大
    max_rzye = max(rzye)
    current_pct = rzye[-1] / max_rzye * 100 if max_rzye > 0 else 100

    # 连续下降天数
    down_days = 0
    for i in range(len(rzye) - 1, 0, -1):
        if rzye[i] < rzye[i - 1]:
            down_days += 1
        else:
            break

    if slope_pct < -8 and down_days >= 5:
        # 持续去杠杆中：杠杆出清领先见底，但当前对中轴是"还没跌完"
        score = -40
        detail = f'融资余额持续下降{down_days}天（20日{slope_pct:+.1f}%），杠杆在出清，尚未止跌'
    elif slope_pct < -3:
        score = -20
        detail = f'融资余额缓慢下降（20日{slope_pct:+.1f}%）'
    elif slope_pct > 8:
        if current_pct > 95:
            # 高位+杠杆暴升 = 散户追杠杆，警惕
            score = -30
            detail = f'融资余额20日{slope_pct:+.1f}%且处高位，杠杆资金在追高，警惕回撤'
        else:
            score = 35
            detail = f'融资余额持续回升（20日{slope_pct:+.1f}%），杠杆资金回流'
    elif slope_pct > 3:
        score = 15
        detail = f'融资余额小幅回升（20日{slope_pct:+.1f}%）'
    else:
        score = 0
        detail = f'融资余额平稳（20日{slope_pct:+.1f}%）'

    return {
        'key': 'margin', 'label': '融资余额',
        'state': 'positive' if score > 10 else 'negative' if score < -10 else 'neutral',
        'score': score, 'weight': w,
        'detail': detail, 'asof': asof,
    }


# ============================================================
# ③ 产业资本动向（个股级）
# ============================================================
def signal_industrial_capital(code):
    """
    三层信号：
      已落地：十大流通股东变动（QFII/外资进出）
      预警：解禁日历（30天内）
      计划：减持预披露（待接入）
    扣分逻辑：
      外资新进/增持 → +30
      外资退出/减持 → -40
      30天内有解禁 → -20
      无数据 → 0
    """
    path = os.path.join(DATA_DIR, 'shareholders', f'{code}.json')
    data = load_json(path)

    if not data or not data.get('periods') or len(data['periods']) < 2:
        return {
            'key': 'industrial_capital', 'label': '产业资本',
            'state': 'neutral', 'score': 0, 'weight': WEIGHTS['industrial_capital'],
            'detail': '股东变动数据不足（至少需要两期对比）', 'asof': None,
        }

    periods = data['periods']
    latest = periods[0]
    prev = periods[1]
    asof = latest.get('announce_date', latest.get('period', ''))
    age = days_since(asof)

    w = weight_with_stale_penalty(WEIGHTS['industrial_capital'], age)
    if w == 0:
        return {
            'key': 'industrial_capital', 'label': '产业资本',
            'state': 'stale', 'score': 0, 'weight': 0,
            'detail': f'股东数据截至{asof}，已{age}天未更新', 'asof': asof,
        }

    latest_holders = {normalize_institution(h['name']): h for h in latest.get('holders', [])}
    prev_holders = {normalize_institution(h['name']): h for h in prev.get('holders', [])}

    def is_foreign(name):
        return any(kw in name for kw in [
            'UBS', 'MORGAN_STANLEY', 'GOLDMAN_SACHS', 'JPMORGAN',
            'HSBC', 'BARCLAYS', 'DEUTSCHE', 'CITI', 'NOMURA',
            'SCHRODERS', 'FIDELITY', 'POINT72', 'BRIDGEWATER', 'MERRILL',
        ])

    foreign_new = []
    foreign_gone = []
    for name, h in latest_holders.items():
        if is_foreign(name) and name not in prev_holders:
            foreign_new.append(h.get('name', name))
    for name in prev_holders:
        if is_foreign(name) and name not in latest_holders:
            foreign_gone.append(prev_holders[name].get('name', name))

    score = 0
    details = []

    if foreign_new:
        score += 30
        details.append(f'外资新进：{"、".join(foreign_new[:3])}')
    if foreign_gone:
        score -= 40
        details.append(f'外资退出：{"、".join(foreign_gone[:3])}')

    # 解禁日历检查（如已有数据文件）
    unlock = check_unlock_schedule(code)
    if unlock:
        score += unlock['score']
        details.append(unlock['detail'])

    if not details:
        detail = f'股东结构无显著变化（{latest.get("period", "?")}期 vs 上期）'
    else:
        detail = '；'.join(details)

    return {
        'key': 'industrial_capital', 'label': '产业资本',
        'state': 'positive' if score > 10 else 'negative' if score < -10 else 'neutral',
        'score': score, 'weight': w,
        'detail': detail, 'asof': asof,
    }


def check_unlock_schedule(code):
    """解禁日历预警（如data/unlock_schedule/{code}.json存在则使用）"""
    path = os.path.join(DATA_DIR, 'unlock_schedule', f'{code}.json')
    data = load_json(path)
    if not data or not data.get('unlocks'):
        return None
    today = datetime.now()
    for u in data['unlocks']:
        try:
            d = datetime.strptime(u['date'], '%Y-%m-%d')
            days_until = (d - today).days
            if 0 <= days_until <= 30:
                return {
                    'score': -20,
                    'detail': f'{u["date"]}解禁{u.get("shares", "?")}股（占总股本{u.get("pct", "?")}%），还有{days_until}天',
                }
            elif 30 < days_until <= 90:
                return {
                    'score': -5,
                    'detail': f'{u["date"]}解禁{u.get("pct", "?")}%（还有{days_until}天，日历预警）',
                }
        except Exception:
            continue
    return None


# ============================================================
# ④ 投行评级边际变化（个股级）
# ============================================================
def signal_research(code):
    """
    看近30天研报的变化：
      首次覆盖（prev=null 或 新org）→ +30
      评级维持买入/增持且无下调 → +10
      评级下调 → -30
      近90天无任何研报 → 0（无人问津）
    """
    path = os.path.join(DATA_DIR, 'research_reports', f'{code}.json')
    data = load_json(path)
    reports = data.get('reports', []) if data else []
    asof = data.get('asof', '') if data else ''

    if not reports:
        return {
            'key': 'research', 'label': '投行评级',
            'state': 'neutral', 'score': 0, 'weight': WEIGHTS['research'],
            'detail': '近90天无研报覆盖', 'asof': asof,
        }

    age = days_since(asof)
    w = weight_with_stale_penalty(WEIGHTS['research'], age)
    if w == 0:
        return {
            'key': 'research', 'label': '投行评级',
            'state': 'stale', 'score': 0, 'weight': 0,
            'detail': f'研报数据截至{asof}，已{age}天未更新', 'asof': asof,
        }

    # 最新一篇研报
    latest = reports[-1]
    rating = latest.get('rating', '')
    org = latest.get('org', '?')
    date = latest.get('date', '')
    prev = latest.get('prev')  # 同机构上一篇

    RATING_ORDER = {'卖出': -3, '减持': -2, '中性': -1, '持有': -1, '增持': 1, '买入': 2, '强烈推荐': 3}

    score = 0
    details = []

    if prev:
        prev_rating = prev.get('rating', '')
        cur_level = RATING_ORDER.get(rating, 0)
        prev_level = RATING_ORDER.get(prev_rating, 0)
        if cur_level > prev_level:
            score = 35
            details.append(f'{org}上调评级至「{rating}」（原「{prev_rating}」）')
        elif cur_level < prev_level:
            score = -35
            details.append(f'{org}下调评级至「{rating}」（原「{prev_rating}」）')
        else:
            score = 10
            details.append(f'{org}维持「{rating}」')
    else:
        # 首次覆盖
        score = 30
        details.append(f'{org}首次覆盖（{date}），评级「{rating}」')

    # 多机构覆盖加分
    org_history = data.get('org_history', {})
    active_orgs = sum(1 for o, v in org_history.items()
                      if days_since(v.get('date', '')) <= 90)
    if active_orgs >= 3:
        score += 5
        details.append(f'近90天{active_orgs}家机构覆盖')

    detail = '；'.join(details)

    return {
        'key': 'research', 'label': '投行评级',
        'state': 'positive' if score > 10 else 'negative' if score < -10 else 'neutral',
        'score': score, 'weight': w,
        'detail': detail, 'asof': asof,
    }


# ============================================================
# ⑤ 事件验证率（主题级）
# ============================================================
def signal_event_verification(code):
    """
    所属主题的验证率均值：
      hit_rate > 0.40 → 板块新闻可信，叙事有效 +20
      hit_rate < 0.25 → 新闻多为噪音，叙事泡沫 -30
      中间 → 0
    """
    stats = load_json(os.path.join(DATA_DIR, 'event_verification_stats.json'))
    if not stats or not stats.get('themes'):
        return {
            'key': 'event_verification', 'label': '事件验证率',
            'state': 'stale', 'score': 0, 'weight': 0,
            'detail': '事件验证数据不可用', 'asof': None,
        }

    asof = stats.get('updated_at', '')
    age = days_since(asof)
    w = weight_with_stale_penalty(WEIGHTS['event_verification'], age)
    if w == 0:
        return {
            'key': 'event_verification', 'label': '事件验证率',
            'state': 'stale', 'score': 0, 'weight': 0,
            'detail': f'事件验证数据截至{asof}，已过期', 'asof': asof,
        }

    sector = CODE_SECTOR_MAP.get(code, '')
    themes = SECTOR_THEME_MAP.get(sector, [])

    if not themes:
        return {
            'key': 'event_verification', 'label': '事件验证率',
            'state': 'neutral', 'score': 0, 'weight': w,
            'detail': f'板块「{sector or "未知"}」无对应主题映射', 'asof': asof,
        }

    rates = []
    for t in themes:
        tdata = stats['themes'].get(t)
        if tdata and tdata.get('total', 0) >= 5:
            rates.append((t, tdata['hit_rate'], tdata['total']))

    if not rates:
        return {
            'key': 'event_verification', 'label': '事件验证率',
            'state': 'neutral', 'score': 0, 'weight': w,
            'detail': '相关主题样本不足', 'asof': asof,
        }

    avg_rate = sum(r[1] for r in rates) / len(rates)
    theme_str = '、'.join(f'{t}({r:.0%},n={n})' for t, r, n in rates)

    if avg_rate > 0.40:
        score = 20
        detail = f'板块新闻验证率{avg_rate:.0%}（{theme_str}），事件驱动有效'
    elif avg_rate < 0.25:
        score = -30
        detail = f'板块新闻验证率仅{avg_rate:.0%}（{theme_str}），新闻多为噪音，勿当真'
    else:
        score = 0
        detail = f'板块新闻验证率{avg_rate:.0%}（{theme_str}），一般'

    return {
        'key': 'event_verification', 'label': '事件验证率',
        'state': 'positive' if score > 10 else 'negative' if score < -10 else 'neutral',
        'score': score, 'weight': w,
        'detail': detail, 'asof': asof,
    }


# ============================================================
# ⑦ 均线排列（滞后过滤 → 仓位上限）
# ============================================================
def calc_ma_trend_live(code, market='A股'):
    """
    从K线实时计算均线排列状态（不再依赖 deep_analysis 的 tech_snapshot 副产品）。
    返回 {'limit': 仓位上限, 'ma_trend': 描述, 'asof': 最新K线日期}
    """
    try:
        from utils.stock_quote import get_stock_kline
        kline = get_stock_kline(code, market, days=120)
        if len(kline) < 61:
            return {'limit': 0.7, 'ma_trend': '数据不足', 'asof': None}

        closes = [k['close'] for k in kline]
        asof = kline[-1].get('date', '')

        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60
        px = closes[-1]

        # 均线斜率（近20日MA60的变化方向）
        if len(closes) >= 80:
            ma60_prev = sum(closes[-80:-20]) / 60
            ma60_slope = (ma60 - ma60_prev) / ma60_prev * 100
        else:
            ma60_slope = 0

        if ma20 > ma60 and ma60_slope > -0.5:
            trend = '多头排列'
            limit = 1.0
        elif ma20 < ma60 and ma60_slope < 0.5:
            trend = '空头排列'
            limit = 0.5
        else:
            trend = '震荡排列'
            limit = 0.7

        px_pos = '上方' if px >= ma20 else '下方'
        return {
            'limit': limit,
            'ma_trend': f'{trend}(价在MA20{px_pos})',
            'ma_trend_raw': trend,
            'asof': asof,
            'ma20': round(ma20, 2),
            'ma60': round(ma60, 2),
        }
    except Exception as e:
        return {'limit': 0.7, 'ma_trend': f'计算失败({e})', 'asof': None}


def get_ma_position_limit(code, market='A股'):
    """
    返回仓位上限系数（K线现算，tech_snapshot仅作兜底）：
      多头 → 1.0
      震荡 → 0.7
      空头 → 0.5
    """
    # 优先实时计算
    live = calc_ma_trend_live(code, market)
    if live.get('asof') and days_since(live['asof']) <= 3:
        return live

    # 兜底：tech_snapshot 旧文件
    data = load_json(os.path.join(DATA_DIR, f'tech_snapshot_{code}.json'))
    if not data:
        return {'limit': 0.7, 'ma_trend': '无数据', 'asof': None}

    asof = data.get('saved_at', '')
    age = days_since(asof)
    ma_trend = data.get('ma_trend', '震荡排列')
    if '多头' in ma_trend:
        limit = 1.0
    elif '空头' in ma_trend:
        limit = 0.5
    else:
        limit = 0.7
    return {'limit': limit, 'ma_trend': f'{ma_trend}(兜底快照,过期{age}天)', 'asof': asof}


# ============================================================
# 综合计算
# ============================================================
def compute_stock_signal(code, regime_data, event_stats, market='A股'):
    """对单只股票计算全部信号"""
    signals = [
        signal_etf_flow(regime_data, market),
        signal_margin(code),
        signal_industrial_capital(code),
        signal_research(code),
        signal_event_verification(code),
    ]

    # 加权总分（权重已含滞后降权）
    total_weight = sum(s['weight'] for s in signals)
    if total_weight > 0:
        score = round(sum(s['score'] * s['weight'] for s in signals) / 100)
        score = max(-100, min(100, score))
    else:
        score = 0

    # 状态判定
    if score < FREEZE_THRESHOLD:
        state = 'downtrend'
    elif score > UNFREEZE_THRESHOLD:
        state = 'uptrend'
    else:
        state = 'range'

    frozen = score < FREEZE_THRESHOLD

    # 均线仓位上限
    ma = get_ma_position_limit(code, market)

    # 结论生成
    conclusion = generate_conclusion(code, signals, score, state, frozen, ma)

    return {
        'code': code,
        'score': score,
        'state': state,
        'strategy_frozen': frozen,
        'position_limit': ma['limit'],
        'ma_trend': ma['ma_trend'],
        'ma_asof': ma['asof'],
        'signals': signals,
        'conclusion': conclusion,
    }


def generate_conclusion(code, signals, score, state, frozen, ma):
    """生成一句话结论"""
    negative = [s for s in signals if s['score'] < -10 and s['weight'] > 0]
    positive = [s for s in signals if s['score'] > 10 and s['weight'] > 0]

    if frozen:
        parts = [f'中轴策略已冻结（信号分{score}）。']
        if negative:
            names = '、'.join(s['label'] for s in negative)
            parts.append(f'{len(negative)}个信号同向恶化：{names}。')
        parts.append('价格即使回到中轴下方也不触发加仓。')
        if positive:
            names = '、'.join(s['label'] for s in positive)
            parts.append(f'{names}偏正面，但不构成解冻条件。')
        # 解冻条件
        unfreeze_conditions = []
        for s in negative:
            if s['key'] == 'etf_flow':
                unfreeze_conditions.append('ETF资金净流入转正')
            elif s['key'] == 'margin':
                unfreeze_conditions.append('融资余额止跌回升')
            elif s['key'] == 'industrial_capital':
                unfreeze_conditions.append('产业资本动向改善（增持/无解禁压力）')
            elif s['key'] == 'research':
                unfreeze_conditions.append('评级企稳')
        if unfreeze_conditions:
            parts.append(f'解冻参考：{" + ".join(unfreeze_conditions[:2])}。')
        parts.append(f'当前只持有，不补仓。均线{ma["ma_trend"]}，仓位上限{ma["limit"]:.0%}。')
        return ''.join(parts)

    if state == 'uptrend':
        parts = [f'中轴策略正常运行（信号分{score:+d}）。']
        if positive:
            names = '、'.join(s['label'] for s in positive)
            parts.append(f'{names}偏正面。')
        parts.append(f'均线{ma["ma_trend"]}，仓位上限{ma["limit"]:.0%}。中轴下方回调可考虑加仓。')
        return ''.join(parts)

    # range
    parts = [f'中轴策略正常运行（信号分{score:+d}，震荡区间）。']
    if negative:
        names = '、'.join(s['label'] for s in negative)
        parts.append(f'但注意：{names}偏弱。')
    parts.append(f'均线{ma["ma_trend"]}，仓位上限{ma["limit"]:.0%}。按中轴±8%区间操作，不重仓。')
    return ''.join(parts)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--code', help='单只股票代码（调试用）')
    args = parser.parse_args()

    print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] 趋势信号引擎启动')

    # 加载全局数据
    regime_data = load_json(os.path.join(DATA_DIR, 'market_regime.json'))
    event_stats = load_json(os.path.join(DATA_DIR, 'event_verification_stats.json'))

    if args.code:
        result = compute_stock_signal(args.code, regime_data, event_stats)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 全量：从stocks.json读取持仓
    stocks_data = load_json(os.path.join(DATA_DIR, 'stocks.json'))
    stocks = stocks_data.get('stocks', []) if stocks_data else []

    if not stocks:
        print('[ERROR] stocks.json中没有持仓')
        return

    results = {}
    for s in stocks:
        code = s.get('code', '')
        market = s.get('market', 'A股')
        if not code:
            continue
        print(f'  计算 {code} {s.get("name", "")}...', end=' ')
        r = compute_stock_signal(code, regime_data, event_stats, market)
        results[code] = r
        frozen_tag = '🚫冻结' if r['strategy_frozen'] else '✅正常'
        print(f'信号分{r["score"]:+4d} {r["state"]:9s} {frozen_tag}')

    # 保存
    output = {
        'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'data_asof': {
            'market_regime': regime_data.get('asof_date', '') if regime_data else '',
            'event_verification': event_stats.get('updated_at', '') if event_stats else '',
        },
        'thresholds': {
            'freeze': FREEZE_THRESHOLD,
            'unfreeze': UNFREEZE_THRESHOLD,
        },
        'stocks': results,
    }
    out_path = os.path.join(DATA_DIR, 'trend_signals.json')
    save_json(out_path, output)
    print(f'\n[OK] 已保存 {len(results)} 只股票信号 → {out_path}')

    # 摘要
    frozen_count = sum(1 for r in results.values() if r['strategy_frozen'])
    uptrend_count = sum(1 for r in results.values() if r['state'] == 'uptrend')
    print(f'[SUMMARY] 冻结{frozen_count}只 / 上升{uptrend_count}只 / 正常{len(results) - frozen_count - uptrend_count}只')


if __name__ == '__main__':
    main()
