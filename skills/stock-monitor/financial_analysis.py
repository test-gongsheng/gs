#!/usr/bin/env python3
"""
财报分析模块
获取和分析上市公司财务数据
"""

import requests
import json
from datetime import datetime
from typing import Dict, List, Optional

class FinancialReportAnalyzer:
    """财报分析器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Referer': 'https://f10.eastmoney.com/',
            'Connection': 'keep-alive'
        })
    
    def get_financial_summary(self, code: str) -> Dict:
        """获取财务摘要"""
        # 判断市场
        if code.startswith('6'):
            secid = f"1.{code}"
        elif code.startswith('0') or code.startswith('3'):
            secid = f"0.{code}"
        else:
            return {'success': False, 'error': '股票代码格式不正确'}
        
        url = "https://f10.eastmoney.com/CompanySurvey/CompanySurveyAjax"
        params = {'code': code}
        
        try:
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            
            if data:
                return {
                    'success': True,
                    'data': {
                        'name': data.get('f57', ''),
                        'industry': data.get('f20', ''),
                        'main_business': data.get('f21', ''),
                        'total_shares': data.get('f38', ''),
                        'circulating_shares': data.get('f39', ''),
                        'eps': data.get('f55', ''),  # 每股收益
                        'bvps': data.get('f56', ''),  # 每股净资产
                        'roe': data.get('f37', ''),  # 净资产收益率
                        'revenue': data.get('f40', ''),  # 营业收入
                        'net_profit': data.get('f45', '')  # 净利润
                    }
                }
            return {'success': False, 'error': '未获取到数据'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_financial_ratios(self, code: str) -> Dict:
        """获取关键财务比率"""
        url = "https://f10.eastmoney.com/NewFinanceAnalysis/MainTargetAjax"
        params = {'code': code}
        
        try:
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            
            ratios = []
            if data.get('data'):
                for item in data['data'][:4]:  # 最近4个报告期
                    ratios.append({
                        'report_date': item.get('REPORT_DATE', ''),
                        'eps': item.get('EPSJB', ''),  # 基本每股收益
                        'bps': item.get('BPS', ''),  # 每股净资产
                        'roe': item.get('ROE', ''),  # 净资产收益率
                        'roa': item.get('ROA', ''),  # 总资产报酬率
                        'gross_margin': item.get('XSMLL', ''),  # 销售毛利率
                        'net_margin': item.get('XSJLL', ''),  # 销售净利率
                        'debt_ratio': item.get('ZCFZL', ''),  # 资产负债率
                        'current_ratio': item.get('LD', ''),  # 流动比率
                        'quick_ratio': item.get('SD', '')  # 速动比率
                    })
            
            return {'success': True, 'data': ratios}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_profit_statement(self, code: str) -> Dict:
        """获取利润表"""
        url = "https://f10.eastmoney.com/NewFinanceAnalysis/lrbAjax"
        params = {'companyType': '4', 'code': code}
        
        try:
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            
            profits = []
            if data.get('data'):
                for item in data['data'][:4]:
                    profits.append({
                        'report_date': item.get('REPORT_DATE', ''),
                        'total_revenue': item.get('TOTAL_OPERATE_INCOME', ''),  # 营业总收入
                        'operate_revenue': item.get('OPERATE_INCOME', ''),  # 营业收入
                        'total_cost': item.get('TOTAL_OPERATE_COST', ''),  # 营业总成本
                        'operate_cost': item.get('OPERATE_COST', ''),  # 营业成本
                        'operate_profit': item.get('OPERATE_PROFIT', ''),  # 营业利润
                        'total_profit': item.get('TOTAL_PROFIT', ''),  # 利润总额
                        'net_profit': item.get('NETPROFIT', ''),  # 净利润
                        'parent_net_profit': item.get('PARENT_NETPROFIT', '')  # 归母净利润
                    })
            
            return {'success': True, 'data': profits}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def analyze_financial_health(self, code: str) -> Dict:
        """综合分析财务健康状况"""
        summary = self.get_financial_summary(code)
        ratios = self.get_financial_ratios(code)
        
        if not summary.get('success') or not ratios.get('success'):
            return {'success': False, 'error': '获取数据失败'}
        
        analysis = {
            'basic_info': summary['data'],
            'latest_ratios': ratios['data'][0] if ratios['data'] else {},
            'trend': 'stable',
            'health_score': 0,
            'risk_factors': [],
            'strengths': []
        }
        
        # 简单评分逻辑
        latest = analysis['latest_ratios']
        score = 50  # 基础分
        
        # ROE评分
        roe = float(latest.get('roe', 0)) if latest.get('roe') else 0
        if roe > 15:
            score += 15
            analysis['strengths'].append(f'ROE优秀({roe}%)')
        elif roe > 10:
            score += 10
        elif roe > 0:
            score += 5
        else:
            score -= 10
            analysis['risk_factors'].append('ROE为负，盈利能力弱')
        
        # 毛利率评分
        gross = float(latest.get('gross_margin', 0)) if latest.get('gross_margin') else 0
        if gross > 40:
            score += 10
            analysis['strengths'].append(f'毛利率高({gross}%)')
        elif gross > 20:
            score += 5
        
        # 负债率评分
        debt = float(latest.get('debt_ratio', 0)) if latest.get('debt_ratio') else 0
        if debt < 40:
            score += 10
            analysis['strengths'].append('负债率低，财务稳健')
        elif debt > 70:
            score -= 10
            analysis['risk_factors'].append(f'负债率较高({debt}%)')
        
        # 流动比率
        current = float(latest.get('current_ratio', 0)) if latest.get('current_ratio') else 0
        if current > 2:
            score += 5
        elif current < 1:
            score -= 5
            analysis['risk_factors'].append('流动比率低，短期偿债压力大')
        
        analysis['health_score'] = max(0, min(100, score))
        
        if score >= 80:
            analysis['rating'] = '优秀'
        elif score >= 60:
            analysis['rating'] = '良好'
        elif score >= 40:
            analysis['rating'] = '一般'
        else:
            analysis['rating'] = '较差'
        
        return {'success': True, 'data': analysis}


if __name__ == '__main__':
    analyzer = FinancialReportAnalyzer()
    
    print("=== 财务摘要 (000001 平安银行) ===")
    result = analyzer.get_financial_summary('000001')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    print("\n=== 财务分析 ===")
    result = analyzer.analyze_financial_health('000001')
    print(json.dumps(result, ensure_ascii=False, indent=2))
