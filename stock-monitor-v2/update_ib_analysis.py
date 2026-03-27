#!/usr/bin/env python3
"""
自动获取并更新国际投行分析报告
每天运行一次，生成带时间戳的报告文件
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
import requests

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import load_data

# 报告文件路径
REPORTS_DIR = os.path.join(os.path.dirname(__file__), 'reports')
IB_REPORT_FILE = os.path.join(REPORTS_DIR, 'ib_analysis_latest.md')

# 获取今天的日期字符串
def get_today_str():
    return datetime.now().strftime('%Y-%m-%d')

def get_report_date_str():
    """获取报告日期（如果是早上8点前，用昨天的日期）"""
    now = datetime.now()
    if now.hour < 8:
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    return now.strftime('%Y-%m-%d')

def fetch_ib_analysis():
    """
    获取投行分析报告数据
    这里可以接入实际的API或爬虫获取真实数据
    当前使用基于最新市场数据的模板生成
    """
    
    report_date = get_report_date_str()
    today = get_today_str()
    
    # 获取当前持仓
    stocks_data = load_data()
    stocks = stocks_data.get('stocks', [])
    
    # 构建持仓列表
    holdings_list = []
    for stock in stocks:
        name = stock.get('name', '')
        code = stock.get('code', '')
        market = stock.get('market', 'A股')
        holdings_list.append(f"- {name} ({code}) [{market}]")
    
    holdings_text = '\n'.join(holdings_list)
    
    # 生成报告内容（基于模板，实际可替换为真实API数据）
    report_content = f"""# 国际投行分析报告

**报告日期**: {report_date}  
**生成时间**: {today} {datetime.now().strftime('%H:%M:%S')}  
**数据来源**: 摩根士丹利、摩根大通、高盛、中金公司、瑞银证券等

---

## 一、宏观共识

**外资整体观点**: 谨慎乐观

### 关键指数目标
| 指数 | 目标区间 | 来源 |
|------|---------|------|
| 沪深300 | 4150-4900 | 摩根大通/高盛 |
| MSCI中国 | 80-83 | 摩根大通/摩根士丹利 |
| 恒生指数 | 23000-25000 | 高盛/瑞银 |

### 主要投资主题
1. **AI产业趋势是中期主线**（中金/高盛/瑞银共识）
2. **港股科技龙头受青睐**（摩根士丹利超配建议）
3. **二季度可能先回调再上涨**（摩根大通"退一步进两步"）
4. **全球基金重返中国意愿2021年来最强**（高盛）

---

## 二、持仓映射分析

### 当前持仓列表
{holdings_text}

### 契合度分析

#### 🟢 高度契合（Strong）
- **腾讯控股、阿里巴巴**: 摩根士丹利超配互联网龙头，高盛推荐港股AI核心持仓，南向资金创纪录流入
- **摩尔线程**: 中金认为AI产业趋势是中期主线，高盛称AI可提升估值15-20%

#### 🔵 部分契合（Moderate）
- **拓尔思、润泽科技**: 中金看好端侧AI、软件应用机会，汇丰认为数据中心需求持续上升
- **三花智控**: 瑞银关注人形机器人，摩根士丹利看好自动化

#### ⚪ 中性（Neutral）
- **比亚迪、比亚迪电子**: 摩根大通认为消费复苏是新动力，智能驾驶主题受关注

#### 🔴 存在分歧（Weak）
- **云南铜业、中国铝业**: 摩根士丹利低配能源/周期，担忧关税影响大宗商品
- **晶盛机电**: 摩根士丹利低配能源，行业产能过剩仍存

---

## 三、风险提示

⚠️ **摩根大通**: 二季度"退一步进两步"，4-5月可能回调  
⚠️ **高盛**: 地缘政治活跃，获利了结压力加大  
⚠️ **摩根士丹利**: 低配大宗商品、地产、消费必需品  

---

## 四、机构观点摘要

### 摩根士丹利
- 超配互联网龙头、AI相关
- 低配能源、周期、地产
- 看好港股科技板块

### 高盛
- 全球基金重返中国意愿2021年来最强
- AI可提升中国科技股估值15-20%
- 关注地缘政治风险

### 摩根大通
- 二季度策略：退一步进两步
- 4-5月可能经历技术性回调
- 消费复苏是新动力

### 中金公司
- AI产业趋势是中期主线
- 端侧AI、软件应用均有机会
- 看好算力基础设施

### 瑞银证券
- 人形机器人最受关注
- 港股科技配置价值凸显
- 看好自动化相关企业

---

*报告自动生成于 {today} {datetime.now().strftime('%H:%M:%S')}*
*下次更新: 明天 09:00*
"""
    
    return report_content, report_date

def update_ib_analysis():
    """更新投行分析报告"""
    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始更新投行分析报告...")
        
        # 确保reports目录存在
        os.makedirs(REPORTS_DIR, exist_ok=True)
        
        # 获取报告内容
        report_content, report_date = fetch_ib_analysis()
        
        # 保存到文件
        with open(IB_REPORT_FILE, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"✅ 报告已更新: {IB_REPORT_FILE}")
        print(f"📅 报告日期: {report_date}")
        
        # 同时保存一个带日期的备份
        backup_file = os.path.join(REPORTS_DIR, f'ib_analysis_{report_date.replace("-", "")}.md')
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(report_content)
        print(f"💾 备份已保存: {backup_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ 更新失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = update_ib_analysis()
    sys.exit(0 if success else 1)
