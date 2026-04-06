import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

class PivotAxisStrategyV2:
    """
    中轴价格仓位控制策略 - 多方案对比
    
    基础规则：
    1. 初始中轴 = 前90日均价
    2. 底仓 = 投资上限 × 50%（固定不动）
    3. 浮动仓 = 动态调整，上限 = 投资上限 × 100%
    4. 触发阈值：±8%
    5. 基础调整幅度：投资上限 × 20%
    
    优化方案：
    - scheme1: 趋势过滤（只加多头仓）
    - scheme2: 递减加仓（每次加仓金额递减）
    - scheme3: 时间冷却（20交易日间隔）
    - scheme4: 多时间框架（日线+周线确认）
    """
    
    def __init__(self, invest_limit=1000000, trigger_pct=0.08, base_adjust_pct=0.20,
                 scheme='baseline', scheme_params=None):
        self.invest_limit = invest_limit
        self.trigger_pct = trigger_pct
        self.base_adjust_pct = base_adjust_pct
        self.scheme = scheme
        self.scheme_params = scheme_params or {}
        
        self.base_pct = 0.50
        self.float_pct = 0.50
        self.float_max_pct = 1.00
    
    def calculate_initial_axis(self, df, days=90):
        """计算初始中轴价格（前N日均价，默认90天）"""
        if len(df) < days:
            return df['close'].mean()
        return df['close'].head(days).mean()
    
    def calculate_weekly_axis(self, df, current_idx):
        """计算周线中轴（前12周均价）"""
        if current_idx < 60:  # 至少需要60天数据
            return None
        
        # 取最近60天的收盘价计算周均价
        recent_data = df.iloc[max(0, current_idx-60):current_idx]
        if len(recent_data) < 20:
            return None
        return recent_data['close'].mean()
    
    def calculate_atr(self, df, period=14):
        """计算ATR（平均真实波幅）"""
        df = df.copy()
        df['high_low'] = df['high'] - df['low']
        df['high_close'] = np.abs(df['high'] - df['close'].shift())
        df['low_close'] = np.abs(df['low'] - df['close'].shift())
        df['tr'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=period).mean()
        return df['atr']
    
    def get_adaptive_cooldown(self, volatility, atr, close_price, base_cooldown=20):
        """
        自适应冷却期计算
        - 高波动 → 延长冷却（25-30天）
        - 低波动 → 缩短冷却（10-15天）
        """
        # 基于ATR的相对波动率
        atr_pct = (atr / close_price) * 100 if close_price > 0 else 0
        
        # 综合波动率评分（0-100）
        # 年化波动率一般0-100%，ATR一般0-10%
        vol_score = min(100, (volatility * 50) + (atr_pct * 100))
        
        # 映射到冷却期：低波动10天，高波动30天
        if vol_score < 20:  # 低波动
            return 10
        elif vol_score < 40:  # 中低波动
            return 15
        elif vol_score < 60:  # 中等波动
            return 20
        elif vol_score < 80:  # 中高波动
            return 25
        else:  # 高波动
            return 30
    
    def backtest(self, df, initial_capital=1000000):
        """执行回测"""
        df = df.copy().reset_index(drop=True)
        
        if len(df) < 100:
            return None, None, None
        
        initial_axis = self.calculate_initial_axis(df, days=60)
        
        trades = []
        daily_states = []
        
        axis_price = initial_axis
        base_position = 0
        float_position = 0
        cash = initial_capital
        
        # 方案2参数：递减加仓
        add_count = 0  # 加仓次数计数
        
        # 方案3参数：时间冷却
        last_trade_idx = -999  # 上次交易索引
        cool_down_days = self.scheme_params.get('cool_down_days', 20)
        
        # 方案3b参数：分级冷却
        last_trade_type = None  # 上次交易类型
        last_deviation = 0  # 上次触发时的偏离幅度
        
        # 方案3c参数：自适应冷却（基于20日波动率）
        df['volatility'] = df['close'].pct_change().rolling(window=20).std() * np.sqrt(252)  # 年化波动率
        df['atr'] = self.calculate_atr(df)  # ATR指标
        
        # 建仓时判定股票类型（自适应策略用）- 使用60天数据
        stock_type = 'normal'  # 默认
        if self.scheme == 'scheme3c':
            # 计算前60天的波动率（使用20-59天，确保有足够数据）
            prices_60d = df['close'].iloc[20:60] if len(df) >= 60 else df['close'].iloc[20:]
            vol_60d = prices_60d.pct_change().std() * np.sqrt(252) if len(prices_60d) > 10 else 0.3
            # ATR用第59天的值，如果NaN则估算
            atr_60d = df['atr'].iloc[59] if len(df) > 59 and not pd.isna(df['atr'].iloc[59]) else df['close'].iloc[min(59, len(df)-1)] * 0.025
            close_60d = df['close'].iloc[min(59, len(df)-1)]
            atr_pct_60d = (atr_60d / close_60d) * 100 if close_60d > 0 else 2.5
            stock_vol_score = min(100, vol_60d * 50 + atr_pct_60d * 10)  # ATR权重降低
            stock_type = 'high_vol' if stock_vol_score > 60 else 'normal'
            print(f"    股票类型判定(60d): {stock_type} (波动率评分: {stock_vol_score:.1f}, 年化波动: {vol_60d:.1%}, ATR%: {atr_pct_60d:.1f}%)")
        
        # 建仓（第60天）
        entry_idx = 59
        entry_price = df.iloc[entry_idx]['open']
        base_target = self.invest_limit * self.base_pct
        base_position = int(base_target / entry_price)
        base_cost = base_position * entry_price
        cash -= base_cost
        
        trades.append({
            'date': df.iloc[entry_idx]['date'],
            'type': 'BASE',
            'price': entry_price,
            'shares': base_position,
            'value': base_cost,
            'axis_before': axis_price,
            'axis_after': entry_price,
            'cash': cash
        })
        axis_price = entry_price
        last_trade_idx = entry_idx
        
        # 回测循环（从第61天开始）
        for i in range(60, len(df)):
            row = df.iloc[i]
            date = row['date']
            close = row['close']
            
            deviation = (close - axis_price) / axis_price
            total_shares = base_position + float_position
            position_value = total_shares * close
            float_value = float_position * close
            float_max = self.invest_limit * self.float_max_pct
            total_value = cash + position_value
            
            daily_states.append({
                'date': date,
                'close': close,
                'axis_price': axis_price,
                'deviation': deviation,
                'base_position': base_position,
                'float_position': float_position,
                'total_shares': total_shares,
                'position_value': position_value,
                'cash': cash,
                'total_value': total_value,
                'float_value': float_value
            })
            
            # 检查是否满足冷却期（方案3、方案3b、方案3c）
            if self.scheme in ['scheme3', 'scheme3b', 'scheme3c']:
                if self.scheme == 'scheme3':
                    # 原始方案3：固定冷却期
                    if (i - last_trade_idx) < cool_down_days:
                        continue
                elif self.scheme == 'scheme3b':
                    # 方案3b：分级冷却（方案C - 分级+自适应结合）
                    
                    # 计算当前波动率状态
                    volatility = row.get('volatility', 0.3)  # 默认30%
                    atr = row.get('atr', close * 0.03)  # 默认3% ATR
                    atr_pct = (atr / close) * 100 if close > 0 else 0
                    
                    # 综合波动率评分
                    vol_score = min(100, (volatility * 50) + (atr_pct * 100))
                    is_high_volatility = vol_score > 60  # 高波动阈值
                    
                    if last_trade_type == 'SELL':
                        # 卖出后自适应冷却：低波动20天，高波动15天
                        effective_cool_down = 15 if is_high_volatility else 20
                    elif last_trade_type == 'BUY':
                        # 买入后根据偏离幅度和波动率调整
                        # 高波动时阈值放宽到-12%，低波动时严格到-14%
                        deep_threshold = -0.12 if is_high_volatility else -0.14
                        mid_threshold = -0.10 if is_high_volatility else -0.11
                        
                        if last_deviation <= deep_threshold:  # 深度下跌
                            effective_cool_down = 10  # 加速抄底
                        elif last_deviation <= mid_threshold:  # 中度下跌
                            effective_cool_down = 15
                        else:  # 轻度下跌
                            effective_cool_down = 20
                    else:
                        effective_cool_down = 20  # 默认
                    
                    if (i - last_trade_idx) < effective_cool_down:
                        continue
                elif self.scheme == 'scheme3c':
                    # 方案3c：智能自适应（建仓时判定股票类型，之后固定）
                    if stock_type == 'high_vol':
                        # 高波动股 → 用分级冷却（多交易）
                        effective_cool_down = cool_down_days
                        if last_trade_type == 'SELL':
                            effective_cool_down = 15  # 卖出后短冷却
                        elif last_trade_type == 'BUY':
                            if last_deviation <= -0.12:  # 浅阈值
                                effective_cool_down = 10
                            elif last_deviation <= -0.10:
                                effective_cool_down = 15
                            else:
                                effective_cool_down = 20
                    else:
                        # 普通股 → 用标准自适应冷却（少交易）
                        volatility = row.get('volatility', 0.3)
                        atr = row.get('atr', close * 0.03)
                        effective_cool_down = self.get_adaptive_cooldown(volatility, atr, close, cool_down_days)
                    
                    if (i - last_trade_idx) < effective_cool_down:
                        continue
            
            # 卖出逻辑（上涨+8%）
            if deviation >= self.trigger_pct and float_position > 0:
                sell_amount = self.invest_limit * self.base_adjust_pct
                sell_shares = int(sell_amount / close)
                
                if float_position >= sell_shares and sell_shares > 0:
                    sell_value = sell_shares * close
                    cash += sell_value
                    float_position -= sell_shares
                    add_count = max(0, add_count - 1)  # 卖出减少加仓计数
                    
                    trades.append({
                        'date': date, 'type': 'SELL', 'price': close,
                        'shares': sell_shares, 'value': sell_value,
                        'deviation': deviation, 'axis_before': axis_price,
                        'axis_after': close, 'cash': cash
                    })
                    axis_price = close
                    last_trade_idx = i
                    last_trade_type = 'SELL'
                    last_deviation = deviation
            
            # 买入逻辑（下跌-8%）
            elif deviation <= -self.trigger_pct:
                can_buy = True
                buy_amount = self.invest_limit * self.base_adjust_pct
                
                # 方案1：趋势过滤 - 只在多头时加仓
                if self.scheme == 'scheme1':
                    if close < axis_price:  # 当前价格低于中轴，视为空头
                        can_buy = False
                
                # 方案2：递减加仓
                if self.scheme == 'scheme2':
                    decay_factor = self.scheme_params.get('decay_factor', 0.75)
                    buy_amount = buy_amount * (decay_factor ** add_count)
                    if buy_amount < self.invest_limit * 0.05:  # 低于5%不再加仓
                        can_buy = False
                
                # 方案4：多时间框架确认
                if self.scheme == 'scheme4':
                    weekly_axis = self.calculate_weekly_axis(df, i)
                    if weekly_axis and close < weekly_axis:  # 周线也低于中轴
                        can_buy = False
                
                if can_buy and buy_amount > 0:
                    current_float_value = float_position * close
                    if current_float_value + buy_amount > float_max:
                        buy_amount = float_max - current_float_value
                    
                    if buy_amount > 0 and cash >= buy_amount:
                        buy_shares = int(buy_amount / close)
                        if buy_shares > 0:
                            buy_value = buy_shares * close
                            cash -= buy_value
                            float_position += buy_shares
                            add_count += 1
                            
                            trades.append({
                                'date': date, 'type': 'BUY', 'price': close,
                                'shares': buy_shares, 'value': buy_value,
                                'deviation': deviation, 'axis_before': axis_price,
                                'axis_after': close, 'cash': cash,
                                'add_count': add_count if self.scheme == 'scheme2' else None
                            })
                            axis_price = close
                            last_trade_idx = i
                            last_trade_type = 'BUY'
                            last_deviation = deviation
        
        final_price = df.iloc[-1]['close']
        final_position_value = (base_position + float_position) * final_price
        final_total = cash + final_position_value
        
        stats = self.calculate_stats(trades, daily_states, initial_capital, final_total)
        return trades, pd.DataFrame(daily_states), stats
    
    def calculate_stats(self, trades, daily_states, initial_capital, final_equity):
        """计算统计指标"""
        if not daily_states:
            return {}
        
        df_daily = pd.DataFrame(daily_states)
        total_return = (final_equity - initial_capital) / initial_capital * 100
        days = len(df_daily)
        annual_return = ((final_equity / initial_capital) ** (252 / days) - 1) * 100 if days > 0 else 0
        
        df_daily['peak'] = df_daily['total_value'].cummax()
        df_daily['drawdown'] = (df_daily['total_value'] - df_daily['peak']) / df_daily['peak']
        max_drawdown = df_daily['drawdown'].min() * 100
        
        buy_trades = [t for t in trades if t['type'] == 'BUY']
        sell_trades = [t for t in trades if t['type'] == 'SELL']
        
        if len(df_daily) > 1:
            daily_returns = df_daily['total_value'].pct_change().dropna()
            sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() != 0 else 0
        else:
            sharpe_ratio = 0
        
        final_state = daily_states[-1] if daily_states else {}
        
        return {
            '方案': self.scheme,
            '总收益率': round(total_return, 2),
            '年化收益率': round(annual_return, 2),
            '最大回撤': round(max_drawdown, 2),
            '交易次数': len(buy_trades) + len(sell_trades),
            '买入次数': len(buy_trades),
            '卖出次数': len(sell_trades),
            '最终持仓': round(final_state.get('position_value', 0), 0),
            '剩余现金': round(final_state.get('cash', 0), 0),
            '夏普比率': round(sharpe_ratio, 2)
        }


def run_comparison():
    """运行4种方案的对比回测"""
    data_dir = "/root/.openclaw/workspace/stock_analyzer/data"
    combined_file = os.path.join(data_dir, "all_stocks_combined.csv")
    
    if not os.path.exists(combined_file):
        print(f"错误: 找不到数据文件 {combined_file}")
        return
    
    df_all = pd.read_csv(combined_file)
    stocks = df_all['stock_code'].unique()
    
    schemes = [
        ('baseline', '原始策略', {}),
        ('scheme1', '方案1-趋势过滤', {}),
        ('scheme2', '方案2-递减加仓', {'decay_factor': 0.75}),
        ('scheme3', '方案3-时间冷却', {'cool_down_days': 20}),
        ('scheme3b', '方案3b-分级冷却', {}),
        ('scheme3c', '方案3c-自适应冷却', {}),
        ('scheme4', '方案4-多时间框架', {}),
    ]
    
    results = []
    
    for stock_code in sorted(stocks):
        df_stock = df_all[df_all['stock_code'] == stock_code].copy()
        stock_name = df_stock['stock_name'].iloc[0]
        
        if len(df_stock) < 100:
            continue
        
        print(f"\n{'='*80}")
        print(f"📈 {stock_code} {stock_name}")
        print(f"{'='*80}")
        
        stock_results = {'stock_code': stock_code, 'stock_name': stock_name}
        
        for scheme_key, scheme_name, params in schemes:
            strategy = PivotAxisStrategyV2(
                invest_limit=1000000,
                trigger_pct=0.08,
                base_adjust_pct=0.20,
                scheme=scheme_key,
                scheme_params=params
            )
            
            trades, daily_states, stats = strategy.backtest(df_stock, initial_capital=1000000)
            
            if stats:
                stock_results[scheme_key] = stats
                print(f"\n{scheme_name}:")
                print(f"  总收益: {stats['总收益率']:.1f}%  年化: {stats['年化收益率']:.1f}%  回撤: {stats['最大回撤']:.1f}%")
                print(f"  交易: {stats['交易次数']}次(买{stats['买入次数']}/卖{stats['卖出次数']})  夏普: {stats['夏普比率']}")
        
        results.append(stock_results)
    
    # 汇总对比
    print(f"\n{'='*100}")
    print("📊 方案对比汇总")
    print(f"{'='*100}")
    
    for scheme_key, scheme_name, _ in schemes:
        returns = [r[scheme_key]['总收益率'] for r in results if scheme_key in r]
        annuals = [r[scheme_key]['年化收益率'] for r in results if scheme_key in r]
        drawdowns = [r[scheme_key]['最大回撤'] for r in results if scheme_key in r]
        trades = [r[scheme_key]['交易次数'] for r in results if scheme_key in r]
        
        win_count = sum(1 for r in returns if r > 0)
        
        print(f"\n{scheme_name}:")
        print(f"  平均总收益: {np.mean(returns):.1f}%  平均年化: {np.mean(annuals):.1f}%")
        print(f"  平均最大回撤: {np.mean(drawdowns):.1f}%  平均交易次数: {np.mean(trades):.0f}")
        print(f"  盈利股票: {win_count}/{len(returns)} ({win_count/len(returns)*100:.0f}%)")


if __name__ == "__main__":
    run_comparison()
