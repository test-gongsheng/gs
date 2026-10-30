# -*- coding: utf-8 -*-
"""回归辅助：生成单股深度报告文本到指定文件（供git stash前后diff）。"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from deep_analysis import generate_deep_report
code, out = sys.argv[1], sys.argv[2]
stocks = json.load(open('data/stocks.json'))['stocks']
stock = [x for x in stocks if x['code'] == code][0]
text = generate_deep_report(stock, '2026-10-30')
open(out, 'w', encoding='utf-8').write(text)
print('saved', out, len(text))
