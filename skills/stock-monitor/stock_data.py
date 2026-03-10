#!/usr/bin/env python3
"""
股票数据获取模块 - 新浪财经版本
支持A股实时行情、历史数据、技术指标计算
"""

import requests
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

class StockDataFetcher:
    """股票数据获取器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'https://finance.sina.com.cn/'
        })
    
    def _get_sina_code(self, code: str) -> str:
        """转换为新浪股票代码格式"""
        if code.startswith('6'):
            return f"sh{code}"
        elif code.startswith('0') or code.startswith('3'):
            return f"sz{code}"
        return code
    
    def get_index_quote(self) -> Dict:
        """获取主要指数实时行情 - 使用新浪财经"""
        url = "https://hq.sinajs.cn/list=s_sh000001,s_sz399001,s_sz399006,s_sh000300,s_sz399005"
        
        try:
            resp = self.session.get(url, timeout=10)
            resp.encoding = 'gb2312'
            
            index_names = {
                'sh000001': '上证指数',
                'sz399001': '深证成指',
                'sz399006': '创业板指',
                'sh000300': '沪深300',
                'sz399005': '中小板指'
            }
            
            results = []
            lines = resp.text.strip().split('\n')
            
            for line in lines:
                match = re.search(r'hq_str_(s_\w+)="([^"]*)"', line)
                if match:
                    code_key = match.group(1).replace('s_', '')
                    data_str = match.group(2)
                    parts = data_str.split(',')
                    
                    if len(parts) >= 4:
                        results.append({
                            'name': index_names.get(code_key, parts[0]),
                            'code': code_key,
                            'price': float(parts[1]) if parts[1] else 0,
                            'change': float(parts[2]) if parts[2] else 0,
                            'change_pct': float(parts[3]) if parts[3] else 0,
                            'volume': 0,
                            'amount': 0
                        })
            
            return {'success': True, 'data': results}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_stock_quote(self, code: str) -> Dict:
        """获取个股实时行情"""
        sina_code = self._get_sina_code(code)
        url = f"https://hq.sinajs.cn/list={sina_code}"
        
        try:
            resp = self.session.get(url, timeout=10)
            resp.encoding = 'gb2312'
            
            match = re.search(r'hq_str_\w+="([^"]*)"', resp.text)
            if not match:
                return {'success': False, 'error': '未获取到数据'}
            
            data_str = match.group(1)
            parts = data_str.split(',')
            
            if len(parts) < 30:
                return {'success': False, 'error': '数据格式错误'}
            
            return {
                'success': True,
                'data': {
                    'name': parts[0],
                    'code': code,
                    'price': float(parts[3]),
                    'open': float(parts[1]),
                    'high': float(parts[4]),
                    'low': float(parts[5]),
                    'prev_close': float(parts[2]),
                    'change': float(parts[3]) - float(parts[2]),
                    'volume': int(parts[8]),
                    'amount': float(parts[9])
                }
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_market_sentiment(self) -> Dict:
        """获取市场情绪数据"""
        url = "https://hq.sinajs.cn/list=s_sh000001,s_sz399001"
        
        try:
            resp = self.session.get(url, timeout=10)
            resp.encoding = 'gb2312'
            
            sh_match = re.search(r'hq_str_s_sh000001="([^"]*)"', resp.text)
            
            if sh_match:
                parts = sh_match.group(1).split(',')
                change_pct = float(parts[3]) if len(parts) > 3 else 0
                
                if change_pct > 1:
                    sentiment = "乐观 😊"
                    up_ratio = 0.7
                elif change_pct > 0:
                    sentiment = "偏乐观 🙂"
                    up_ratio = 0.6
                elif change_pct > -1:
                    sentiment = "偏谨慎 😐"
                    up_ratio = 0.4
                else:
                    sentiment = "悲观 😟"
                    up_ratio = 0.3
                
                return {
                    'success': True,
                    'data': {
                        'sentiment': sentiment,
                        'index_change': change_pct,
                        'estimated_up_ratio': up_ratio,
                        'note': '基于大盘指数涨跌估算'
                    }
                }
            
            return {'success': False, 'error': '解析失败'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_stock_kline(self, code: str, period: str = 'day', count: int = 60) -> Dict:
        """获取K线数据用于技术分析 - 使用腾讯财经接口"""
        if code.startswith('6'):
            full_code = f"sh{code}"
        elif code.startswith('0') or code.startswith('3'):
            full_code = f"sz{code}"
        else:
            return {'success': False, 'error': '股票代码格式不正确'}
        
        url = f"http://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        period_map = {'day': 'day', 'week': 'week', 'month': 'month'}
        kline_type = period_map.get(period, 'day')
        
        import random
        rand = random.random()
        
        params = {
            '_var': f'kline_{kline_type}qfq',
            'param': f"{full_code},{kline_type},,,{count},qfq",
            'r': str(rand)
        }
        
        try:
            resp = self.session.get(url, params=params, timeout=15)
            
            text = resp.text
            prefix = f'kline_{kline_type}qfq='
            if text.startswith(prefix):
                text = text[len(prefix):]
            
            data = json.loads(text)
            
            klines = []
            data_keys = [kline_type, f'qfq{kline_type}']
            
            stock_data = None
            if data.get('data') and data['data'].get(full_code):
                stock_data = data['data'][full_code]
                
            if stock_data:
                kline_data = None
                for key in data_keys:
                    if key in stock_data:
                        kline_data = stock_data[key]
                        break
                
                if kline_data:
                    for item in kline_data:
                        if len(item) >= 6:
                            klines.append({
                                'date': item[0],
                                'open': float(item[1]),
                                'close': float(item[2]),
                                'low': float(item[3]),
                                'high': float(item[4]),
                                'volume': float(item[5]),
                                'amount': 0
                            })
            
            return {'success': True, 'data': klines}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_sector_sentiment(self) -> Dict:
        """获取板块情绪分析 - 东方财富行业分类（完整版）"""
        sector_indices = {
            # 金融类
            '银行': 's_sh000947',
            '证券': 's_sz399975',
            '保险': 's_sz399809',
            '多元金融': 's_sz399966',
            '金融科技': 's_sh000038',
            
            # 房地产链
            '房地产开发': 's_sh000006',
            '房地产服务': 's_sz399241',
            '建筑装饰': 's_sz399235',
            '建筑材料': 's_sz399394',
            '装修建材': 's_sz399394',
            '家居用品': 's_sz399976',
            
            # 医药医疗（细分）
            '化学制药': 's_sz399413',
            '生物制品': 's_sz399411',
            '医疗器械': 's_sz399989',
            '医疗服务': 's_sz399412',
            '中药': 's_sz399440',
            '医药商业': 's_sz399414',
            '医疗美容': 's_sz399413',
            
            # 大消费
            '白酒': 's_sz399997',
            '饮料乳品': 's_sz399396',
            '食品加工': 's_sz399397',
            '家电': 's_sz399967',
            '纺织服饰': 's_sz399234',
            '商贸零售': 's_sz399280',
            '旅游酒店': 's_sz399396',
            '美容护理': 's_sz399413',
            
            # 科技类（细分）
            '半导体': 's_sz399811',
            '电子元件': 's_sz399398',
            '光学光电子': 's_sz399414',
            '消费电子': 's_sz399997',
            '计算机设备': 's_sz399935',
            '软件开发': 's_sz399936',
            '通信设备': 's_sz399994',
            '互联网服务': 's_sz399970',
            '传媒': 's_sz399971',
            '游戏': 's_sz399971',
            
            # 新能源与电力（细分）
            '电力': 's_sz399991',
            '电网设备': 's_sz399991',
            '光伏设备': 's_sz399994',
            '风电设备': 's_sz399808',
            '电池': 's_sz399976',
            '能源金属': 's_sh000819',
            '电力行业': 's_sz399991',
            
            # 汽车与机械（细分）
            '汽车整车': 's_sz399417',
            '汽车零部件': 's_sz399431',
            '电机': 's_sz399233',
            '专用设备': 's_sz399233',
            '通用设备': 's_sz399233',
            '工程机械': 's_sz399233',
            '自动化设备': 's_sz399233',
            
            # 军工航天（细分）
            '航天航空': 's_sz399959',
            '船舶制造': 's_sz399959',
            '军工电子': 's_sz399959',
            '地面兵装': 's_sz399959',
            '航海装备': 's_sz399959',
            
            # 周期资源（细分）
            '贵金属': 's_sh000819',
            '有色金属': 's_sh000819',
            '能源金属': 's_sh000819',
            '煤炭行业': 's_sz399998',
            '钢铁行业': 's_sz399440',
            '石油行业': 's_sz399310',
            '化纤行业': 's_sz399240',
            '化学制品': 's_sz399240',
            '化学原料': 's_sz399240',
            '塑料橡胶': 's_sz399240',
            '化肥农药': 's_sz399240',
            '非金属材料': 's_sz399240',
            
            # 交通运输（细分）
            '物流': 's_sz399433',
            '航运港口': 's_sz399433',
            '航空机场': 's_sz399433',
            '铁路公路': 's_sz399433',
            '交运设备': 's_sz399433',
            
            # 公用环保（细分）
            '公用事业': 's_sz399321',
            '燃气': 's_sz399321',
            '水务': 's_sz399321',
            '环保': 's_sz399358',
            
            # 农林牧渔（细分）
            '农牧饲渔': 's_sz399110',
            '农药兽药': 's_sz399110',
            '林业': 's_sz399110',
            '渔业': 's_sz399110',
            
            # 轻工制造（细分）
            '造纸印刷': 's_sz399235',
            '包装印刷': 's_sz399235',
            '文娱用品': 's_sz399235',
            '家用轻工': 's_sz399235',
            
            # 采掘与冶炼
            '采掘': 's_sh000819',
            '冶炼': 's_sh000819',
            
            # 工程服务
            '工程咨询服务': 's_sz399235',
            '专业服务': 's_sz399235',
            
            # 综合类
            '综合': 's_sz399300'
        }
        
        results = []
        
        try:
            codes = ','.join(sector_indices.values())
            url = f"https://hq.sinajs.cn/list={codes}"
            
            resp = self.session.get(url, timeout=15)
            resp.encoding = 'gb2312'
            
            lines = resp.text.strip().split('\n')
            
            for line in lines:
                match = re.search(r'hq_str_(s_\w+)="([^"]*)"', line)
                if match:
                    code_key = match.group(1)
                    data_str = match.group(2)
                    parts = data_str.split(',')
                    
                    if len(parts) >= 4:
                        sector_name = [k for k, v in sector_indices.items() if v == code_key]
                        if sector_name:
                            name = sector_name[0]
                            change_pct = float(parts[3]) if parts[3] else 0
                            
                            if change_pct >= 3:
                                sentiment = '🔥 强势'
                            elif change_pct >= 1.5:
                                sentiment = '📈 活跃'
                            elif change_pct >= 0:
                                sentiment = '🙂 平稳'
                            elif change_pct >= -1.5:
                                sentiment = '😐 偏弱'
                            elif change_pct >= -3:
                                sentiment = '📉 低迷'
                            else:
                                sentiment = '❄️ 弱势'
                            
                            results.append({
                                'name': name,
                                'code': code_key,
                                'price': float(parts[1]) if parts[1] else 0,
                                'change_pct': change_pct,
                                'sentiment': sentiment
                            })
            
            results.sort(key=lambda x: x['change_pct'], reverse=True)
            return {'success': True, 'data': results}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_concept_sentiment(self) -> Dict:
        """获取概念板块情绪 - 东方财富概念分类（完整版）"""
        concept_indices = {
            # 科技前沿（细分）
            '芯片概念': 's_sz980017',
            '半导体概念': 's_sz980017',
            '国产芯片': 's_sz980017',
            '存储芯片': 's_sz980017',
            '5G概念': 's_sz980032',
            '6G概念': 's_sz980032',
            '人工智能': 's_sz930713',
            'AI芯片': 's_sz980017',
            'ChatGPT': 's_sz930713',
            'AIGC': 's_sz930713',
            '云计算': 's_sz930851',
            '边缘计算': 's_sz980032',
            '大数据': 's_sz930994',
            '数据中心': 's_sz930851',
            '东数西算': 's_sz930851',
            '时空大数据': 's_sz930994',
            '物联网': 's_sz930654',
            '工业互联网': 's_sz930654',
            '区块链': 's_sz930994',
            '数字货币': 's_sz399006',
            '量子通信': 's_sz980032',
            '光刻机': 's_sz980017',
            '光刻胶': 's_sz980017',
            '高带宽内存': 's_sz980017',
            'Chiplet': 's_sz980017',
            
            # 新能源（细分）
            '新能源': 's_sz399808',
            '锂电池': 's_sz399976',
            '固态电池': 's_sz399976',
            '钠离子电池': 's_sz399976',
            '动力电池回收': 's_sz399976',
            '光伏概念': 's_sz399994',
            'HIT电池': 's_sz399994',
            '钙钛矿电池': 's_sz399994',
            'TOPCon电池': 's_sz399994',
            '储能': 's_sz399994',
            '氢能源': 's_sz399808',
            '燃料电池': 's_sz399808',
            '风电': 's_sz399991',
            '核电': 's_sz399991',
            '特高压': 's_sz399991',
            '智能电网': 's_sz399991',
            '充电桩': 's_sz399417',
            '换电概念': 's_sz399417',
            '虚拟电厂': 's_sz399991',
            
            # 新能源汽车（细分）
            '新能源汽车': 's_sz399417',
            '特斯拉': 's_sz399417',
            '比亚迪概念': 's_sz399417',
            '蔚来汽车': 's_sz399417',
            '小鹏汽车': 's_sz399417',
            '理想汽车': 's_sz399417',
            '华为汽车': 's_sz399417',
            '小米汽车': 's_sz399417',
            '无人驾驶': 's_sz399417',
            '车联网': 's_sz399417',
            '汽车电子': 's_sz399417',
            '汽车零部件': 's_sz399431',
            '一体化压铸': 's_sz399431',
            '汽车热管理': 's_sz399431',
            
            # 高端制造（细分）
            '机器人': 's_sz399959',
            '人形机器人': 's_sz399959',
            '机器人执行器': 's_sz399959',
            '减速器': 's_sz399959',
            '工业母机': 's_sz399233',
            '工业4.0': 's_sz399959',
            '智能制造': 's_sz399233',
            '航空航天': 's_sz399959',
            '大飞机': 's_sz399959',
            '航母概念': 's_sz399959',
            '通用航空': 's_sz399959',
            '北斗导航': 's_sz399959',
            '军民融合': 's_sz399959',
            '成飞概念': 's_sz399959',
            
            # 医药医疗（细分）
            '创新药': 's_sz399413',
            'CRO': 's_sz399413',
            'CXO': 's_sz399413',
            '中药': 's_sz399440',
            '新冠药物': 's_sz399413',
            '流感': 's_sz399413',
            '医疗器械': 's_sz399989',
            '医美': 's_sz399413',
            '辅助生殖': 's_sz399413',
            '基因测序': 's_sz399413',
            '精准医疗': 's_sz399413',
            '智慧医疗': 's_sz399989',
            '减肥药': 's_sz399413',
            '阿兹海默': 's_sz399413',
            
            # 数字经济（细分）
            '元宇宙': 's_sz399971',
            'VR/AR': 's_sz399971',
            '虚拟数字人': 's_sz399971',
            'NFT': 's_sz399971',
            'Web3.0': 's_sz399971',
            '云游戏': 's_sz399971',
            '电子竞技': 's_sz399971',
            '网红经济': 's_sz399971',
            '直播带货': 's_sz399971',
            '短视频': 's_sz399971',
            '在线教育': 's_sz399970',
            '远程办公': 's_sz399935',
            
            # 新基建（细分）
            '数据中心': 's_sz930851',
            '东数西算': 's_sz930851',
            '特高压': 's_sz399991',
            '充电桩': 's_sz399417',
            '智能电网': 's_sz399991',
            '城际高铁': 's_sz399995',
            '城市大脑': 's_sz399935',
            
            # 新消费（细分）
            '新零售': 's_sz399280',
            '跨境电商': 's_sz399280',
            '免税概念': 's_sz399280',
            '预制菜': 's_sz399396',
            '社区团购': 's_sz399396',
            '宠物经济': 's_sz399396',
            '养老概念': 's_sz399989',
            '三胎概念': 's_sz399413',
            '婴童概念': 's_sz399413',
            '智能家居': 's_sz399967',
            '冷链物流': 's_sz399433',
            
            # 资源（细分）
            '稀土永磁': 's_sh000819',
            '黄金概念': 's_sh000819',
            '锂矿': 's_sz399976',
            '钴': 's_sz399976',
            '镍': 's_sh000819',
            '磷化工': 's_sz399240',
            '氟化工': 's_sz399240',
            '有机硅': 's_sz399240',
            '钛白粉': 's_sz399240',
            '煤化工': 's_sz399998',
            '油气开采': 's_sz399310',
            
            # 新材料
            '新材料': 's_sz399240',
            '石墨烯': 's_sz399240',
            '碳纤维': 's_sz399240',
            '超导概念': 's_sz399240',
            '纳米材料': 's_sz399240',
            '先进封装': 's_sz980017',
            
            # 环保碳中和（细分）
            '碳中和': 's_sz399358',
            '碳交易': 's_sz399358',
            '节能环保': 's_sz399358',
            '垃圾分类': 's_sz399358',
            '污水处理': 's_sz399358',
            '大气治理': 's_sz399358',
            '土壤修复': 's_sz399358',
            '光伏建筑一体化': 's_sz399994',
            
            # 国企改革（细分）
            '国企改革': 's_sh000038',
            '央企改革': 's_sh000038',
            '国资云': 's_sz399935',
            '军工混改': 's_sz399959',
            '乡村振兴': 's_sz399110',
            '共同富裕': 's_sz399967',
            '一带一路': 's_sz399433',
            '雄安新区': 's_sz399235',
            '粤港澳大湾区': 's_sz399235',
            '长三角一体化': 's_sz399235',
            '海南自贸港': 's_sz399280',
            
            # 金融科技
            '金融科技': 's_sh000038',
            '数字货币': 's_sz399006',
            '电子支付': 's_sz399975',
            '互联网金融': 's_sz399975',
            '参股银行': 's_sz399975',
            '参股保险': 's_sz399809',
            '参股券商': 's_sz399975',
            
            # 信息安全（细分）
            '网络安全': 's_sz399935',
            '信创': 's_sz399935',
            '国产软件': 's_sz399935',
            '国产操作系统': 's_sz399935',
            '国产替代': 's_sz980017',
            '信息安全': 's_sz399935',
            '数据安全': 's_sz399935',
            '智慧政务': 's_sz399935',
            
            # 消费电子（细分）
            '无线耳机': 's_sz399997',
            '苹果概念': 's_sz399997',
            '华为概念': 's_sz399997',
            '小米概念': 's_sz399997',
            '消费电子': 's_sz399997',
            '智能穿戴': 's_sz399997',
            '柔性屏': 's_sz399398',
            '折叠屏': 's_sz399398',
            '3D打印': 's_sz399233',
            
            # 市场风格（细分）
            '独角兽': 's_sz399006',
            '科创板': 's_sh000683',
            '北交所': 's_sz399006',
            '注册制': 's_sz399006',
            '次新股': 's_sz399006',
            '高送转': 's_sz399300',
            '股权转让': 's_sz399300',
            '并购重组': 's_sz399300',
            '股权激励': 's_sz399300',
            '回购': 's_sz399300',
            '举牌': 's_sz399300',
            '壳资源': 's_sz399300',
            'ST概念': 's_sz399300',
            
            # 机构持仓
            'QFII重仓': 's_sz399300',
            '社保重仓': 's_sz399300',
            '基金重仓': 's_sz399300',
            '信托重仓': 's_sz399300',
            '券商重仓': 's_sz399975',
            '保险重仓': 's_sz399809',
            '养老金': 's_sz399300',
            
            # 其他热点
            '无线充电': 's_sz399997',
            '燃料电池': 's_sz399808',
            '超级电容': 's_sz399976',
            'UWB概念': 's_sz980032',
            'MiniLED': 's_sz399398',
            'MicroLED': 's_sz399398',
            'LED': 's_sz399398',
            '超清视频': 's_sz399971',
            '智能电视': 's_sz399967',
            '汽车芯片': 's_sz980017',
            'IGBT': 's_sz980017',
            'MCU芯片': 's_sz980017'
        }
            
            # 新消费
            '新零售': 's_sz399280',
            '跨境电商': 's_sz399280',
            '免税概念': 's_sz399280',
            '预制菜': 's_sz399396',
            '宠物经济': 's_sz399396',
            '养老概念': 's_sz399989',
            
            # 资源
            '稀土永磁': 's_sh000819',
            '黄金概念': 's_sh000819',
            '锂矿': 's_sz399976',
            
            # 环保碳中和
            '碳中和': 's_sz399358',
            '碳交易': 's_sz399358',
            '节能环保': 's_sz399358',
            
            # 国企改革
            '国企改革': 's_sh000038',
            '央企改革': 's_sh000038',
            '乡村振兴': 's_sz399110',
            
            # 信息安全
            '网络安全': 's_sz399935',
            '信创': 's_sz399935',
            '国产替代': 's_sz980017',
            
            # 市场风格
            '科创板': 's_sh000683',
            '北交所': 's_sz399006',
            '次新股': 's_sz399006'
        }
        
        results = []
        
        try:
            codes = ','.join(concept_indices.values())
            url = f"https://hq.sinajs.cn/list={codes}"
            
            resp = self.session.get(url, timeout=15)
            resp.encoding = 'gb2312'
            
            lines = resp.text.strip().split('\n')
            seen_names = set()
            
            for line in lines:
                match = re.search(r'hq_str_(s_\w+)="([^"]*)"', line)
                if match:
                    code_key = match.group(1)
                    data_str = match.group(2)
                    parts = data_str.split(',')
                    
                    if len(parts) >= 4:
                        concept_names = [k for k, v in concept_indices.items() if v == code_key]
                        for name in concept_names:
                            if name not in seen_names:
                                seen_names.add(name)
                                change_pct = float(parts[3]) if parts[3] else 0
                                
                                results.append({
                                    'name': name,
                                    'code': code_key,
                                    'change_pct': change_pct
                                })
            
            results.sort(key=lambda x: x['change_pct'], reverse=True)
            return {'success': True, 'data': results}
        except Exception as e:
            return {'success': False, 'error': str(e)}


class TechnicalAnalyzer:
    """技术分析器"""
    
    @staticmethod
    def calculate_ma(data: List[Dict], periods: List[int] = [5, 10, 20, 60]) -> Dict:
        """计算移动平均线"""
        closes = [d['close'] for d in data]
        mas = {}
        
        for period in periods:
            if len(closes) >= period:
                ma = sum(closes[-period:]) / period
                mas[f'MA{period}'] = round(ma, 2)
        
        return mas
    
    @staticmethod
    def calculate_macd(data: List[Dict], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        """计算MACD指标"""
        closes = [d['close'] for d in data]
        
        if len(closes) < slow + signal:
            return {'error': '数据不足'}
        
        def ema(values, period):
            multiplier = 2 / (period + 1)
            ema_values = [values[0]]
            for price in values[1:]:
                ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
            return ema_values
        
        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)
        
        dif = [f - s for f, s in zip(ema_fast, ema_slow)]
        dea = ema(dif, signal)
        macd_hist = [2 * (d - e) for d, e in zip(dif, dea)]
        
        return {
            'DIF': round(dif[-1], 3),
            'DEA': round(dea[-1], 3),
            'MACD': round(macd_hist[-1], 3),
            'trend': '金叉' if dif[-1] > dea[-1] and dif[-2] <= dea[-2] else (
                '死叉' if dif[-1] < dea[-1] and dif[-2] >= dea[-2] else '延续'
            )
        }
    
    @staticmethod
    def calculate_rsi(data: List[Dict], period: int = 14) -> Dict:
        """计算RSI指标"""
        closes = [d['close'] for d in data]
        
        if len(closes) < period + 1:
            return {'error': '数据不足'}
        
        gains = []
        losses = []
        
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            gains.append(max(change, 0))
            losses.append(abs(min(change, 0)))
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        
        return {
            'RSI': round(rsi, 2),
            'level': '超买' if rsi > 70 else ('超卖' if rsi < 30 else '正常')
        }


if __name__ == '__main__':
    fetcher = StockDataFetcher()
    
    print("=== 指数行情 ===")
    result = fetcher.get_index_quote()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    print("\n=== 个股行情 (000001 平安银行) ===")
    result = fetcher.get_stock_quote('000001')
    print(json.dumps(result, ensure_ascii=False, indent=2))
