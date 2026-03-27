#!/usr/bin/env python3
"""
技术分析数据获取模块 (P0级别)
- 均线系统 (MA5/10/20/60)
- MACD指标
- 资金流向
"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple


def get_stock_hist_data(code: str, market: str, days: int = 120) -> Optional[pd.DataFrame]:
    """获取股票历史行情数据"""
    try:
        if market == 'A股':
            # A股代码格式
            if code.startswith('6'):
                symbol = f"sh{code}"
            else:
                symbol = f"sz{code}"
            
            # 获取历史数据
            start_date = (datetime.now() - timedelta(days=days+30)).strftime('%Y%m%d')
            df = ak.stock_zh_a_daily(symbol=symbol, start_date=start_date)
            
            if df.empty:
                return None
            
            # 标准化列名
            df.columns = [c.lower() for c in df.columns]
            return df
        else:
            # 港股暂不支持详细技术分析
            return None
    except Exception as e:
        print(f"[ERROR] 获取{code}历史数据失败: {e}")
        return None


def calculate_ma(df: pd.DataFrame, periods: list = [5, 10, 20, 60]) -> Dict[int, float]:
    """计算多周期均线"""
    mas = {}
    for period in periods:
        if len(df) >= period:
            ma = df['close'].tail(period).mean()
            mas[period] = round(float(ma), 2)
        else:
            mas[period] = 0
    return mas


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Dict]:
    """计算MACD指标"""
    try:
        if len(df) < slow + signal:
            return None
        
        # 计算EMA
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        
        # DIF线
        dif = ema_fast - ema_slow
        
        # DEA线 (DIF的EMA)
        dea = dif.ewm(span=signal, adjust=False).mean()
        
        # MACD柱状图
        macd_hist = (dif - dea) * 2
        
        # 获取最新值
        latest_dif = round(float(dif.iloc[-1]), 3)
        latest_dea = round(float(dea.iloc[-1]), 3)
        latest_hist = round(float(macd_hist.iloc[-1]), 3)
        
        # 判断MACD状态
        prev_hist = float(macd_hist.iloc[-2]) if len(macd_hist) > 1 else 0
        
        macd_status = 'neutral'
        macd_signal = '观望'
        
        if latest_hist > 0 and prev_hist <= 0:
            macd_status = 'golden_cross'
            macd_signal = '金叉买入'
        elif latest_hist < 0 and prev_hist >= 0:
            macd_status = 'death_cross'
            macd_signal = '死叉卖出'
        elif latest_hist > 0 and latest_hist > prev_hist:
            macd_status = 'bullish'
            macd_signal = '多头增强'
        elif latest_hist > 0 and latest_hist < prev_hist:
            macd_status = 'bullish_weakening'
            macd_signal = '多头减弱'
        elif latest_hist < 0 and latest_hist < prev_hist:
            macd_status = 'bearish'
            macd_signal = '空头增强'
        elif latest_hist < 0 and latest_hist > prev_hist:
            macd_status = 'bearish_weakening'
            macd_signal = '空头减弱'
        
        return {
            'dif': latest_dif,
            'dea': latest_dea,
            'hist': latest_hist,
            'status': macd_status,
            'signal': macd_signal,
            'prev_hist': round(prev_hist, 3)
        }
    except Exception as e:
        print(f"[ERROR] 计算MACD失败: {e}")
        return None


def get_capital_flow(code: str) -> Optional[Dict]:
    """获取资金流向数据"""
    try:
        # 使用akshare获取资金流向
        df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith('6') else "sz")
        
        if df.empty:
            return None
        
        # 解析数据
        df.columns = [c.lower() for c in df.columns]
        
        # 获取最新一天的数据
        latest = df.iloc[0]
        
        # 主力净流入 (超大单+大单)
        main_inflow = float(latest.get('主力净流入-净额', 0)) / 10000  # 转换为万元
        
        # 散户净流入 (中单+小单)
        retail_inflow = float(latest.get('散户净流入-净额', 0)) / 10000
        
        # 判断资金流向
        flow_status = 'neutral'
        if main_inflow > 500:
            flow_status = 'strong_inflow'
        elif main_inflow > 100:
            flow_status = 'inflow'
        elif main_inflow < -500:
            flow_status = 'strong_outflow'
        elif main_inflow < -100:
            flow_status = 'outflow'
        
        # 获取日期并转换为字符串
        flow_date = latest.get('日期', '')
        if hasattr(flow_date, 'strftime'):
            flow_date = flow_date.strftime('%Y-%m-%d')
        else:
            flow_date = str(flow_date)
        
        return {
            'main_inflow': round(main_inflow, 2),
            'retail_inflow': round(retail_inflow, 2),
            'status': flow_status,
            'date': flow_date
        }
    except Exception as e:
        print(f"[WARN] 获取{code}资金流向失败: {e}")
        return None


def analyze_technical_p0(code: str, market: str, current_price: float) -> Optional[Dict]:
    """P0级别技术分析入口"""
    if market != 'A股':
        return None  # 港股暂不支持
    
    try:
        # 获取历史数据
        df = get_stock_hist_data(code, market, days=120)
        if df is None or df.empty:
            return None
        
        # 计算均线
        mas = calculate_ma(df, [5, 10, 20, 60])
        
        # 计算MACD
        macd = calculate_macd(df)
        
        # 获取资金流向
        capital_flow = get_capital_flow(code)
        
        # 判断均线排列
        ma_trend = 'neutral'
        if mas[5] > mas[10] > mas[20]:
            ma_trend = 'bullish'  # 多头排列
        elif mas[5] < mas[10] < mas[20]:
            ma_trend = 'bearish'  # 空头排列
        
        # 判断价格与均线关系
        price_vs_ma = {}
        for period in [5, 10, 20, 60]:
            if mas[period] > 0:
                deviation = round((current_price - mas[period]) / mas[period] * 100, 2)
                price_vs_ma[f'ma{period}'] = {
                    'value': mas[period],
                    'deviation': deviation,
                    'above': current_price > mas[period]
                }
        
        return {
            'ma': mas,
            'ma_trend': ma_trend,
            'price_vs_ma': price_vs_ma,
            'macd': macd,
            'capital_flow': capital_flow,
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
    except Exception as e:
        print(f"[ERROR] {code} 技术分析失败: {e}")
        return None


def generate_technical_analysis_text(tech_data: Dict, name: str, current_price: float) -> Dict:
    """生成技术分析的文字描述"""
    if not tech_data:
        return {'ma_analysis': '暂无数据', 'macd_analysis': '暂无数据', 'flow_analysis': '暂无数据'}
    
    # 均线分析
    ma_text = []
    price_vs_ma = tech_data.get('price_vs_ma', {})
    
    ma5 = price_vs_ma.get('ma5', {})
    ma20 = price_vs_ma.get('ma20', {})
    ma60 = price_vs_ma.get('ma60', {})
    
    if ma5.get('above') and ma20.get('above'):
        ma_text.append(f"股价站上MA5(¥{ma5['value']})和MA20(¥{ma20['value']})，短期趋势向好。")
    elif not ma5.get('above') and not ma20.get('above'):
        ma_text.append(f"股价跌破MA5(¥{ma5['value']})和MA20(¥{ma20['value']})，短期趋势走弱。")
    else:
        ma_text.append(f"股价在MA5(¥{ma5['value']})附近震荡，方向待确认。")
    
    if ma60.get('value'):
        if current_price > ma60['value']:
            ma_text.append(f"股价位于MA60(¥{ma60['value']})之上，中长期趋势偏多。")
        else:
            ma_text.append(f"股价跌破MA60(¥{ma60['value']})，中长期趋势偏空。")
    
    # MACD分析
    macd = tech_data.get('macd', {})
    macd_text = []
    if macd:
        macd_text.append(f"MACD指标显示：DIF={macd.get('dif')}, DEA={macd.get('dea')}, 柱状图={macd.get('hist')}。")
        macd_text.append(f"信号解读：{macd.get('signal', '暂无明确信号')}。")
    
    # 资金流向分析
    flow = tech_data.get('capital_flow', {})
    flow_text = []
    if flow:
        main_inflow = flow.get('main_inflow', 0)
        if main_inflow > 0:
            flow_text.append(f"主力净流入¥{main_inflow}万元，资金呈流入态势。")
        else:
            flow_text.append(f"主力净流出¥{abs(main_inflow)}万元，资金呈流出态势。")
    
    return {
        'ma_analysis': '\n'.join(ma_text) if ma_text else '均线数据暂不可用',
        'macd_analysis': '\n'.join(macd_text) if macd_text else 'MACD数据暂不可用',
        'flow_analysis': '\n'.join(flow_text) if flow_text else '资金流向数据暂不可用'
    }


if __name__ == '__main__':
    # 测试
    result = analyze_technical_p0('000559', 'A股', 15.8)
    print(json.dumps(result, ensure_ascii=False, indent=2))
