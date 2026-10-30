# -*- coding: utf-8 -*-
"""离线降级测试：mock 三个新模块的网络函数，验证报告行优雅降级 + deep_analysis 全量生成不崩。

降级语义（与任务规格一致）：
- margin/shareholders：离线有缓存->用缓存(数据asof即最新交易日/报告期)；无缓存->暂不可用
- research_report：抓取失败->暂不可用（因需实时去重，不消费昨日缓存）
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _boom(*a, **kw):
    raise RuntimeError('mock network down')

from utils import margin_balance, shareholders, research_report

# ---------- A. renderer级降级 ----------
margin_balance._fetch_batch = _boom
shareholders._parse_page = _boom
research_report._fetch_df = _boom

# A1. 有缓存+断网 -> margin/holder用缓存（asof即最新交易日/报告期）；
#     research_report设计为当日幂等+实时去重，源挂即报暂不可用（不消费昨日缓存，防陈旧）
tmp_a1 = tempfile.mkdtemp()
research_report.REPORT_DIR = tmp_a1  # 空库 -> 必走fetch -> mock断网 -> 暂不可用
m = margin_balance.render_margin_lines('688795')
s = shareholders.render_holder_lines('688795')
r = research_report.render_report_lines('688795')
assert '融资余额' in m[0] and '10-29' in m[0], m
assert '机构动向' in s[0] and '2026-09-30' in s[0], s
assert r == ['**最新研报捕获+假设拆解[库·东财研报]:** 数据暂不可用(东财研报接口受限)', ''], r
print('A1. 有缓存+断网: margin用缓存(%s...)' % m[0][:40])
print('    holder用缓存(%s...)' % s[0][:46])
print('    report暂不可用 OK')

# A2. 无缓存+断网 -> 全部暂不可用
tmp = tempfile.mkdtemp()
margin_balance.MARGIN_DIR = tmp
shareholders.HOLDER_DIR = tmp
research_report.REPORT_DIR = tmp
m2 = margin_balance.render_margin_lines('688795')
s2 = shareholders.render_holder_lines('688795')
r2 = research_report.render_report_lines('688795')
assert m2 == ['- 融资余额数据暂不可用(交易所两融接口受限)'], m2
assert s2 == ['**机构动向:** 十大流通股东数据暂不可用(数据源受限)', ''], s2
assert r2 == ['**最新研报捕获+假设拆解[库·东财研报]:** 数据暂不可用(东财研报接口受限)', ''], r2
print('A2. 无缓存+断网: 三个renderer全部暂不可用 OK')

# ---------- B. 全量报告集成降级：无缓存+断网下 generate_deep_report 不崩 ----------
import json
from deep_analysis import generate_deep_report
stocks = json.load(open('data/stocks.json'))['stocks']
stock = [x for x in stocks if x['code'] == '000559'][0]
text = generate_deep_report(stock, '2026-10-30')
assert '融资余额数据暂不可用' in text, 'margin降级行缺失'
assert '十大流通股东数据暂不可用' in text, 'holder降级行缺失'
assert '最新研报捕获+假设拆解[库·东财研报]:** 数据暂不可用' in text, 'report降级行缺失'
assert '## 一、' in text and '## 七、' in text, '章节骨架缺失'
print('B. 全量报告集成降级 OK(000559, 无缓存+断网): 三个新块均显示暂不可用, 章节一~七完整, 报告长度', len(text))
