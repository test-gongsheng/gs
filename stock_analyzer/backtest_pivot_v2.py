import pandas as pd
import numpy as np
from datetime import datetime
import os

class PivotAxisStrategy:
    """
    中轴价格仓位控制策略回测
    
    策略规则：
    1. 初始中轴 = 前90日均价
    2. 底仓 = 投资上限 × 50%（固定不动）
    3. 浮动仓 = 动态调整，上限 = 投资上限 × 100%（即可满仓到150%总仓位）
    4. 触发阈值：股价较中轴 ±8%
    5. 调整幅度：浮动仓的20%（相对于投资上限）
    6. 中轴动态调整：每次交易后，中轴更新为成交价
    7. 无止损
    """
    
    def __init__(self, invest_limit=1000000, trigger_pct=0.08, adjust_pct=0.20):
        """
        参数：
            invest_limit: 投资上限（默认100万）
            trigger_pct: 触发阈值（默认8%）
            adjust_pct: 调整幅度（默认20%，指浮动仓的20%）
        """
        self.invest_limit = invest_limit
        self.trigger_pct = trigger_pct
        self.adjust_pct = adjust_pct
        
        # 固定比例
        self.base_pct = 0.50  # 底仓50%
        self.float_pct = 0.50  # 浮动仓基准50%
        self.float_max_pct = 1.00  # 浮动仓上限100%（相对投资上限）
        
    def calculate_initial_axis(self, df):
        """计算初始中轴价格（前90日均价）"""
        if len(df) < 90:
            # 数据不足，用所有数据的均价
            return df['close'].mean()
        return df['close'].head(90).mean()
    
    def backtest(self, df, initial_capital=1000000):
        """
        执行回测
        
        返回：
            trades: 交易记录列表
            daily_states: 每日状态记录
            stats: 统计指标
        """
        df = df.copy().reset_index(drop=True)
        
        if len(df) < 90:
            print(f"数据不足90天，无法回测")
            return None, None, None
        
        # 计算初始中轴（基于前90天数据，从第90天开始交易）
        initial_axis = self.calculate_initial_axis(df)
        
        trades = []
        daily_states = []
        
        # 初始化状态
        axis_price = initial_axis  # 当前中轴价格
        base_position = 0  # 底仓股数（固定）
        float_position = 0  # 浮动仓股数（动态）
        cash = initial_capital  # 现金
        
        # 建立底仓（第90天开盘买入）
        base_target = self.invest_limit * self.base_pct  # 底仓目标金额
        entry_price = df.iloc[89]['open']  # 第90天开盘价买入
        base_position = int(base_target / entry_price)
        base_cost = base_position * entry_price
        cash -= base_cost
        
        trades.append({
            'date': df.iloc[89]['date'],
            'type': 'BASE',
            'price': entry_price,
            'shares': base_position,
            'value': base_cost,
            'axis_before': axis_price,
            'axis_after': entry_price,  # 建仓后更新中轴
            'cash': cash
        })
        axis_price = entry_price  # 更新中轴为成交价
        
        # 从第90天开始每日监控
        for i in range(89, len(df)):
            row = df.iloc[i]
            date = row['date']
            close = row['close']
            high = row['high']
            low = row['low']
            
            # 计算当前偏离度
            deviation = (close - axis_price) / axis_price
            
            # 当前持仓市值
            total_shares = base_position + float_position
            position_value = total_shares * close
            float_value = float_position * close  # 浮动仓市值
            float_target = self.invest_limit * self.float_pct  # 浮动仓目标市值
            float_max = self.invest_limit * self.float_max_pct  # 浮动仓上限市值
            
            total_value = cash + position_value
            
            # 记录每日状态
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
            
            # 检查触发条件
            trade_executed = False
            
            if deviation >= self.trigger_pct:
                # 上涨超过+8%：减持浮动仓
                # 减持金额 = 投资上限 × 20%
                sell_amount = self.invest_limit * self.adjust_pct
                sell_shares = int(sell_amount / close)
                
                if float_position >= sell_shares and sell_shares > 0:
                    sell_value = sell_shares * close
                    cash += sell_value
                    float_position -= sell_shares
                    
                    trades.append({
                        'date': date,
                        'type': 'SELL',
                        'price': close,
                        'shares': sell_shares,
                        'value': sell_value,
                        'deviation': deviation,
                        'axis_before': axis_price,
                        'axis_after': close,  # 交易后更新中轴
                        'cash': cash,
                        'float_value_after': float_position * close
                    })
                    axis_price = close  # 更新中轴
                    trade_executed = True
                    
            elif deviation <= -self.trigger_pct:
                # 下跌超过-8%：增持浮动仓
                # 增持金额 = 投资上限 × 20%
                buy_amount = self.invest_limit * self.adjust_pct
                
                # 检查是否超过浮动仓上限
                current_float_value = float_position * close
                if current_float_value + buy_amount > float_max:
                    buy_amount = float_max - current_float_value
                
                if buy_amount > 0 and cash >= buy_amount:
                    buy_shares = int(buy_amount / close)
                    if buy_shares > 0:
                        buy_value = buy_shares * close
                        cash -= buy_value
                        float_position += buy_shares
                        
                        trades.append({
                            'date': date,
                            'type': 'BUY',
                            'price': close,
                            'shares': buy_shares,
                            'value': buy_value,
                            'deviation': deviation,
                            'axis_before': axis_price,
                            'axis_after': close,  # 交易后更新中轴
                            'cash': cash,
                            'float_value_after': float_position * close
                        })
                        axis_price = close  # 更新中轴
                        trade_executed = True
        
        # 计算最终权益（按最后一天收盘价）
        final_price = df.iloc[-1]['close']
        final_position_value = (base_position + float_position) * final_price
        final_total = cash + final_position_value
        
        # 统计指标
        stats = self.calculate_stats(trades, daily_states, initial_capital, final_total)
        
        return trades, pd.DataFrame(daily_states), stats
    
    def calculate_stats(self, trades, daily_states, initial_capital, final_equity):
        """计算回测统计指标"""
        if not daily_states:
            return {}
        
        df_daily = pd.DataFrame(daily_states)
        
        # 计算收益率
        total_return = (final_equity - initial_capital) / initial_capital * 100
        
        # 计算年化收益率
        days = len(df_daily)
        annual_return = ((final_equity / initial_capital) ** (252 / days) - 1) * 100 if days > 0 else 0
        
        # 计算最大回撤
        df_daily['peak'] = df_daily['total_value'].cummax()
        df_daily['drawdown'] = (df_daily['total_value'] - df_daily['peak']) / df_daily['peak']
        max_drawdown = df_daily['drawdown'].min() * 100
        
        # 交易统计（不含建仓）
        buy_trades = [t for t in trades if t['type'] == 'BUY']
        sell_trades = [t for t in trades if t['type'] == 'SELL']
        
        # 计算买入后的盈亏（简化：看最终持仓）
        # 这里简化处理，主要看总收益
        
        # 计算夏普比率
        if len(df_daily) > 1:
            daily_returns = df_daily['total_value'].pct_change().dropna()
            sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() != 0 else 0
        else:
            sharpe_ratio = 0
        
        # 最终持仓状态
        final_state = daily_states[-1] if daily_states else {}
        
        return {
            '投资上限': self.invest_limit,
            '初始资金': initial_capital,
            '最终资金': round(final_equity, 2),
            '总收益率': round(total_return, 2),
            '年化收益率': round(annual_return, 2),
            '最大回撤': round(max_drawdown, 2),
            '交易次数': len(buy_trades) + len(sell_trades),
            '买入次数': len(buy_trades),
            '卖出次数': len(sell_trades),
            '底仓股数': final_state.get('base_position', 0),
            '浮动仓股数': final_state.get('float_position', 0),
            '总持仓股数': final_state.get('total_shares', 0),
            '最终持仓市值': round(final_state.get('position_value', 0), 2),
            '剩余现金': round(final_state.get('cash', 0), 2),
            '夏普比率': round(sharpe_ratio, 2)
        }


def run_backtest_for_all_stocks():
    """对所有持仓股运行回测"""
    data_dir = "/root/.openclaw/workspace/stock_analyzer/data"
    combined_file = os.path.join(data_dir, "all_stocks_combined.csv")
    
    if not os.path.exists(combined_file):
        print(f"错误: 找不到数据文件 {combined_file}")
        return
    
    # 读取数据
    df_all = pd.read_csv(combined_file)
    
    # 按股票分组回测
    stocks = df_all['stock_code'].unique()
    
    print("=" * 80)
    print("中轴价格仓位控制策略回测结果")
    print(f"参数: 投资上限=100万, 底仓50%, 浮动仓上限100%, 触发阈值±8%, 调整幅度20%")
    print("=" * 80)
    
    all_stats = []
    
    for stock_code in sorted(stocks):
        df_stock = df_all[df_all['stock_code'] == stock_code].copy()
        stock_name = df_stock['stock_name'].iloc[0]
        
        if len(df_stock) < 100:  # 需要至少90天数据+建仓日
            print(f"\n{stock_code} {stock_name}: 数据不足 ({len(df_stock)} 条)，跳过")
            continue
        
        # 运行回测
        strategy = PivotAxisStrategy(
            invest_limit=1000000,
            trigger_pct=0.08,
            adjust_pct=0.20
        )
        
        trades, daily_states, stats = strategy.backtest(df_stock, initial_capital=1000000)
        
        if stats:
            print(f"\n📈 {stock_code} {stock_name}")
            print("-" * 60)
            for key, value in stats.items():
                if isinstance(value, float):
                    suffix = "%" if any(k in key for k in ['率', '回撤']) else ""
                    print(f"  {key}: {value}{suffix}")
                else:
                    print(f"  {key}: {value}")
            
            # 显示交易明细
            if trades:
                print(f"\n  交易明细:")
                for t in trades[:5]:  # 只显示前5笔
                    print(f"    {t['date']} {t['type']}: {t['shares']}股 @ {t['price']:.2f}")
                if len(trades) > 5:
                    print(f"    ... 共{len(trades)}笔交易")
            
            stats['stock_code'] = stock_code
            stats['stock_name'] = stock_name
            all_stats.append(stats)
    
    # 汇总统计
    if all_stats:
        print("\n" + "=" * 80)
        print("组合汇总")
        print("=" * 80)
        
        df_stats = pd.DataFrame(all_stats)
        avg_return = df_stats['总收益率'].mean()
        avg_annual = df_stats['年化收益率'].mean()
        avg_drawdown = df_stats['最大回撤'].mean()
        
        print(f"  平均总收益率: {avg_return:.2f}%")
        print(f"  平均年化收益率: {avg_annual:.2f}%")
        print(f"  平均最大回撤: {avg_drawdown:.2f}%")
        print(f"  盈利股票数: {(df_stats['总收益率'] > 0).sum()}/{len(df_stats)}")


if __name__ == "__main__":
    run_backtest_for_all_stocks()
