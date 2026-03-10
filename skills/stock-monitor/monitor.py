#!/usr/bin/env python3
"""
股票监控主程序
整合实时行情、技术分析、市场情绪、财报分析功能
"""

import sys
import json
import argparse
from datetime import datetime

from stock_data import StockDataFetcher, TechnicalAnalyzer
from financial_analysis import FinancialReportAnalyzer

class StockMonitor:
    """股票监控主类"""
    
    def __init__(self):
        self.fetcher = StockDataFetcher()
        self.technical = TechnicalAnalyzer()
        self.financial = FinancialReportAnalyzer()
    
    def show_index_quote(self):
        """显示大盘指数行情"""
        result = self.fetcher.get_index_quote()
        
        if not result.get('success'):
            print(f"❌ 获取行情失败: {result.get('error', '未知错误')}")
            return
        
        print("\n📊 今日大盘行情")
        print("=" * 60)
        print(f"{'指数':<12} {'最新':<10} {'涨跌':<10} {'涨跌幅':<10}")
        print("-" * 60)
        
        for item in result['data']:
            name = item['name']
            price = item['price']
            change = item['change']
            change_pct = item['change_pct']
            
            emoji = "📈" if change >= 0 else "📉"
            change_str = f"+{change:.2f}" if change >= 0 else f"{change:.2f}"
            change_pct_str = f"+{change_pct:.2f}%" if change_pct >= 0 else f"{change_pct:.2f}%"
            
            print(f"{emoji} {name:<8} {price:<10.2f} {change_str:<10} {change_pct_str:<10}")
        
        print("=" * 60)
    
    def show_stock_quote(self, code: str):
        """显示个股行情"""
        result = self.fetcher.get_stock_quote(code)
        
        if not result.get('success'):
            print(f"❌ 获取股票失败: {result.get('error', '未知错误')}")
            return
        
        data = result['data']
        change_pct = (data['price'] - data['prev_close']) / data['prev_close'] * 100 if data['prev_close'] else 0
        
        emoji = "📈" if change_pct >= 0 else "📉"
        
        print(f"\n{emoji} {data['name']} ({data['code']})")
        print("=" * 50)
        print(f"最新价:    {data['price']:.2f}")
        print(f"涨跌额:    {data['change']:.2f}")
        print(f"涨跌幅:    {change_pct:+.2f}%")
        print(f"今开:      {data['open']:.2f}")
        print(f"最高:      {data['high']:.2f}")
        print(f"最低:      {data['low']:.2f}")
        print(f"昨收:      {data['prev_close']:.2f}")
        print(f"成交量:    {data['volume'] / 10000:.2f}万手")
        print(f"成交额:    {data['amount'] / 100000000:.2f}亿")
        print("=" * 50)
    
    def show_technical_analysis(self, code: str):
        """显示技术分析"""
        # 获取K线数据
        kline_result = self.fetcher.get_stock_kline(code, 'day', 100)
        
        if not kline_result.get('success'):
            print(f"❌ 获取K线数据失败: {kline_result.get('error', '未知错误')}")
            return
        
        data = kline_result['data']
        
        if len(data) < 60:
            print("❌ 数据不足，无法进行技术分析")
            return
        
        # 获取股票信息
        quote_result = self.fetcher.get_stock_quote(code)
        stock_name = quote_result['data']['name'] if quote_result.get('success') else code
        
        print(f"\n📈 {stock_name} ({code}) 技术分析")
        print("=" * 60)
        
        # 均线分析
        mas = self.technical.calculate_ma(data)
        print("\n【均线系统】")
        current_price = data[-1]['close']
        for ma_name, ma_value in mas.items():
            status = "↑" if current_price > ma_value else "↓"
            print(f"  {ma_name}: {ma_value:.2f} {status}")
        
        # 判断均线排列
        if mas.get('MA5', 0) > mas.get('MA10', 0) > mas.get('MA20', 0):
            print("  趋势: 多头排列 📈")
        elif mas.get('MA5', 0) < mas.get('MA10', 0) < mas.get('MA20', 0):
            print("  趋势: 空头排列 📉")
        else:
            print("  趋势: 震荡整理 ➡️")
        
        # MACD分析
        macd = self.technical.calculate_macd(data)
        print("\n【MACD指标】")
        print(f"  DIF: {macd.get('DIF', 'N/A')}")
        print(f"  DEA: {macd.get('DEA', 'N/A')}")
        print(f"  MACD: {macd.get('MACD', 'N/A')}")
        print(f"  信号: {macd.get('trend', 'N/A')}")
        
        # RSI分析
        rsi = self.technical.calculate_rsi(data)
        print("\n【RSI指标】")
        print(f"  RSI(14): {rsi.get('RSI', 'N/A')}")
        print(f"  状态: {rsi.get('level', 'N/A')}")
        
        print("=" * 60)
    
    def show_market_sentiment(self):
        """显示市场情绪"""
        result = self.fetcher.get_market_sentiment()
        
        if not result.get('success'):
            print(f"❌ 获取情绪数据失败: {result.get('error', '未知错误')}")
            return
        
        data = result['data']
        
        print("\n🌡️ 市场情绪分析")
        print("=" * 50)
        
        # 根据返回的数据格式显示
        if 'sentiment' in data:
            print(f"整体情绪: {data['sentiment']}")
            print(f"大盘涨跌: {data.get('index_change', 0):.2f}%")
            print(f"上涨占比估算: {data.get('estimated_up_ratio', 0)*100:.0f}%")
            print(f"说明: {data.get('note', '')}")
        else:
            print(f"涨停家数: {data.get('up_limit', 'N/A')} 📈")
            print(f"跌停家数: {data.get('down_limit', 'N/A')} 📉")
            print(f"上涨家数: {data.get('up_count', 'N/A')} 🔺")
            print(f"下跌家数: {data.get('down_count', 'N/A')} 🔻")
        
        print("=" * 50)
        
        # 显示板块情绪
        self.show_sector_sentiment()
    
    def show_sector_sentiment(self):
        """显示板块情绪分析 - 东方财富分类"""
        print("\n📊 板块情绪分析")
        print("=" * 80)
        
        # 行业板块
        sector_result = self.fetcher.get_sector_sentiment()
        if sector_result.get('success') and sector_result.get('data'):
            data = sector_result['data']
            
            # 东方财富行业分类
            sector_categories = {
                '金融类': ['银行', '证券', '保险', '多元金融', '金融科技'],
                '房地产链': ['房地产开发', '房地产服务', '建筑装饰', '建筑材料', '家居用品'],
                '医药医疗': ['化学制药', '生物制品', '医疗器械', '医疗服务', '中药', '医药商业'],
                '大消费': ['白酒', '饮料乳品', '食品加工', '家电', '纺织服饰', '商贸零售', '旅游酒店', '美容护理'],
                '科技类': ['半导体', '电子元件', '光学光电子', '消费电子', '计算机设备', '软件开发', '通信设备', '互联网服务', '传媒', '游戏'],
                '新能源与电力': ['电力', '电网设备', '光伏设备', '风电设备', '电池', '能源金属', '电力行业'],
                '汽车与机械': ['汽车整车', '汽车零部件', '电机', '专用设备', '通用设备', '工程机械', '自动化设备'],
                '军工航天': ['航天航空', '船舶制造', '军工电子'],
                '周期资源': ['贵金属', '有色金属', '煤炭行业', '钢铁行业', '石油行业', '化纤行业', '化学制品', '化学原料', '塑料橡胶', '化肥农药'],
                '交通运输': ['物流', '航运港口', '航空机场', '铁路公路', '交运设备'],
                '公用环保': ['公用事业', '燃气', '水务', '环保'],
                '农林牧渔': ['农牧饲渔', '农药兽药', '林业'],
                '轻工制造': ['造纸印刷', '包装印刷', '文娱用品'],
                '采掘冶炼': ['采掘', '冶炼'],
                '综合类': ['综合']
            }
            
            print("\n【行业板块 - 东方财富分类】")
            for category, names in sector_categories.items():
                category_data = [item for item in data if item['name'] in names]
                if category_data:
                    avg_change = sum(item['change_pct'] for item in category_data) / len(category_data)
                    emoji = "🔥" if avg_change > 2 else ("📈" if avg_change > 0 else "📉")
                    print(f"\n  ▸ {category} (平均: {avg_change:+.2f}%) {emoji}")
                    print(f"  {'板块':<14} {'涨跌幅':<10} {'情绪':<10}")
                    print(f"  {'-' * 45}")
                    # 按涨跌幅排序显示
                    category_data.sort(key=lambda x: x['change_pct'], reverse=True)
                    for item in category_data[:6]:
                        print(f"  {item['name']:<14} {item['change_pct']:>+6.2f}%   {item['sentiment']}")
            
            # 显示涨幅前五和跌幅前五
            print("\n  ▸ 领涨板块 TOP 5")
            for i, item in enumerate(data[:5], 1):
                fire = "🔥" if item['change_pct'] > 3 else ""
                print(f"    {i}. {item['name']:<12} {item['change_pct']:+.2f}% {item['sentiment']} {fire}")
            
            print("\n  ▸ 领跌板块 TOP 5")
            for i, item in enumerate(data[-5:], 1):
                print(f"    {i}. {item['name']:<12} {item['change_pct']:+.2f}% {item['sentiment']}")
        
        # 概念板块
        concept_result = self.fetcher.get_concept_sentiment()
        if concept_result.get('success') and concept_result.get('data'):
            data = concept_result['data']
            
            # 东方财富概念分类（扩展版）
            concept_categories = {
                '科技前沿': ['芯片概念', '半导体概念', '国产芯片', '存储芯片', '5G概念', '6G概念', '人工智能', 'AI芯片', 'ChatGPT', 'AIGC', '云计算', '边缘计算', '大数据', '数据中心', '东数西算', '时空大数据', '物联网', '工业互联网', '区块链', '数字货币', '量子通信', '光刻机', '光刻胶', '高带宽内存', 'Chiplet'],
                '新能源': ['新能源', '锂电池', '固态电池', '钠离子电池', '动力电池回收', '光伏概念', 'HIT电池', '钙钛矿电池', 'TOPCon电池', '储能', '氢能源', '燃料电池', '风电', '核电', '特高压', '智能电网', '充电桩', '换电概念', '虚拟电厂'],
                '新能源汽车': ['新能源汽车', '特斯拉', '比亚迪概念', '蔚来汽车', '小鹏汽车', '理想汽车', '华为汽车', '小米汽车', '无人驾驶', '车联网', '汽车电子', '汽车零部件', '一体化压铸', '汽车热管理'],
                '高端制造': ['机器人', '人形机器人', '机器人执行器', '减速器', '工业母机', '工业4.0', '智能制造', '航空航天', '大飞机', '航母概念', '通用航空', '北斗导航', '军民融合', '成飞概念'],
                '医药医疗': ['创新药', 'CRO', 'CXO', '中药', '新冠药物', '流感', '医疗器械', '医美', '辅助生殖', '基因测序', '精准医疗', '智慧医疗', '减肥药', '阿兹海默'],
                '数字经济': ['元宇宙', 'VR/AR', '虚拟数字人', 'NFT', 'Web3.0', '云游戏', '电子竞技', '网红经济', '直播带货', '短视频', '在线教育', '远程办公'],
                '新基建': ['数据中心', '东数西算', '特高压', '充电桩', '智能电网', '城际高铁', '城市大脑'],
                '新消费': ['新零售', '跨境电商', '免税概念', '预制菜', '社区团购', '宠物经济', '养老概念', '三胎概念', '婴童概念', '智能家居', '冷链物流'],
                '资源材料': ['稀土永磁', '黄金概念', '锂矿', '钴', '镍', '磷化工', '氟化工', '有机硅', '钛白粉', '煤化工', '油气开采', '新材料', '石墨烯', '碳纤维', '超导概念', '纳米材料', '先进封装'],
                '环保碳中和': ['碳中和', '碳交易', '节能环保', '垃圾分类', '污水处理', '大气治理', '土壤修复', '光伏建筑一体化'],
                '国企改革': ['国企改革', '央企改革', '国资云', '军工混改', '乡村振兴', '共同富裕', '一带一路', '雄安新区', '粤港澳大湾区', '长三角一体化', '海南自贸港'],
                '金融科技': ['金融科技', '数字货币', '电子支付', '互联网金融', '参股银行', '参股保险', '参股券商'],
                '信息安全': ['网络安全', '信创', '国产软件', '国产操作系统', '国产替代', '信息安全', '数据安全', '智慧政务'],
                '消费电子': ['无线耳机', '苹果概念', '华为概念', '小米概念', '消费电子', '智能穿戴', '柔性屏', '折叠屏', '3D打印'],
                '市场风格': ['独角兽', '科创板', '北交所', '注册制', '次新股', '高送转', '股权转让', '并购重组', '股权激励', '回购', '举牌', '壳资源', 'ST概念'],
                '机构持仓': ['QFII重仓', '社保重仓', '基金重仓', '信托重仓', '券商重仓', '保险重仓', '养老金'],
                '其他热点': ['无线充电', '超级电容', 'UWB概念', 'MiniLED', 'MicroLED', 'LED', '超清视频', '智能电视', '汽车芯片', 'IGBT', 'MCU芯片']
            }
            
            print("\n【概念板块 - 东方财富分类】")
            for category, names in concept_categories.items():
                category_data = [item for item in data if item['name'] in names]
                if category_data:
                    avg_change = sum(item['change_pct'] for item in category_data) / len(category_data)
                    emoji = "🔥" if avg_change > 2 else ("📈" if avg_change > 0 else "📉")
                    print(f"\n  ▸ {category} (平均: {avg_change:+.2f}%) {emoji}")
                    print(f"  {'概念':<14} {'涨跌幅':<10}")
                    print(f"  {'-' * 35}")
                    category_data.sort(key=lambda x: x['change_pct'], reverse=True)
                    for item in category_data[:5]:
                        trend = "↑" if item['change_pct'] > 0 else "↓"
                        print(f"  {item['name']:<14} {item['change_pct']:>+6.2f}% {trend}")
        
        print("=" * 80)
    
    def show_financial_analysis(self, code: str):
        """显示财报分析"""
        result = self.financial.analyze_financial_health(code)
        
        if not result.get('success'):
            print(f"❌ 获取财报失败: {result.get('error', '未知错误')}")
            return
        
        data = result['data']
        
        print(f"\n📋 {data['basic_info'].get('name', code)} 财报分析")
        print("=" * 60)
        
        print(f"\n【基本信息】")
        print(f"  行业: {data['basic_info'].get('industry', 'N/A')}")
        print(f"  主营业务: {data['basic_info'].get('main_business', 'N/A')[:50]}...")
        
        print(f"\n【最新财务指标】")
        ratios = data['latest_ratios']
        print(f"  每股收益(EPS): {ratios.get('eps', 'N/A')}")
        print(f"  每股净资产(BPS): {ratios.get('bps', 'N/A')}")
        print(f"  净资产收益率(ROE): {ratios.get('roe', 'N/A')}%")
        print(f"  销售毛利率: {ratios.get('gross_margin', 'N/A')}%")
        print(f"  销售净利率: {ratios.get('net_margin', 'N/A')}%")
        print(f"  资产负债率: {ratios.get('debt_ratio', 'N/A')}%")
        
        print(f"\n【综合评估】")
        print(f"  健康评分: {data['health_score']}/100")
        print(f"  评级: {data['rating']}")
        
        if data['strengths']:
            print(f"\n  ✅ 优势:")
            for s in data['strengths']:
                print(f"     • {s}")
        
        if data['risk_factors']:
            print(f"\n  ⚠️ 风险:")
            for r in data['risk_factors']:
                print(f"     • {r}")
        
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='股票监控工具')
    parser.add_argument('command', choices=['index', 'stock', 'tech', 'sentiment', 'sector', 'finance'],
                        help='命令: index(大盘), stock(个股), tech(技术分析), sentiment(情绪), sector(板块), finance(财报)')
    parser.add_argument('--code', '-c', help='股票代码')
    
    args = parser.parse_args()
    
    monitor = StockMonitor()
    
    if args.command == 'index':
        monitor.show_index_quote()
    elif args.command == 'stock':
        if not args.code:
            print("❌ 请提供股票代码，例如: --code 000001")
            return
        monitor.show_stock_quote(args.code)
    elif args.command == 'tech':
        if not args.code:
            print("❌ 请提供股票代码，例如: --code 000001")
            return
        monitor.show_technical_analysis(args.code)
    elif args.command == 'sentiment':
        monitor.show_market_sentiment()
    elif args.command == 'sector':
        monitor.show_sector_sentiment()
    elif args.command == 'finance':
        if not args.code:
            print("❌ 请提供股票代码，例如: --code 000001")
            return
        monitor.show_financial_analysis(args.code)


if __name__ == '__main__':
    main()
