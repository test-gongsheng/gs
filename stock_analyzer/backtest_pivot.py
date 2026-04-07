import pandas as pd
import numpy as np
from datetime import datetime
import os

class PivotAxisStrategy:
    """
    中轴价格策略回测
    
    策略逻辑：
    1. 计算 N 日价格中轴（Pivot Axis）= (High + Low + Close) / 3
    2. 计算中轴的 M 日移动平均线作为趋势基准
    3. 当日收盘价 > 中轴均线 + 阈值：买入信号
    4. 当日收盘价 < 中轴均线 - 阈值：卖出信号
    5. 持仓期间根据波动幅度动态止盈止损
    """
    
    def __init__(self, pivot_period=20, ma_period=5, threshold_pct=0.02, 
                 stop_loss_pct=0.08, take_profit_pct=0.15):
        """
        参数：
            pivot_period: 计算中轴的周期（默认20日）
            ma_period: 中轴均线的周期（默认5日）
            threshold_pct: 触发交易的阈值百分比（默认2%）
            stop_loss_pct: 止损百分比（默认8%）
            take_profit_pct: 止盈百分比（默认15%）
        """
        self.pivot_period = pivot_period
        self.ma_period = ma_period
        self.threshold_pct = threshold_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        
    def calculate_pivot_axis(self, df):
        """计算价格中轴及其均线"""
        df = df.copy()
        
        # 计算日度枢轴点 (Pivot Point)
        df['pivot'] = (df['high'] + df['low'] + df['close']) / 3
        
        # 计算 N 日平均中轴
        df['pivot_ma'] = df['pivot'].rolling(window=self.pivot_period).mean()
        
        # 计算中轴的 M 日均线（信号线）
        df['signal_line'] = df['pivot_ma'].rolling(window=self.ma_period).mean()
        
        # 计算中轴的标准差（用于波动率过滤）
        df['pivot_std'] = df['pivot'].rolling(window=self.pivot_period).std()
        df['upper_band'] = df['signal_line'] + 2 * df['pivot_std'] / np.sqrt(self.pivot_period)
        df['lower_band'] = df['signal_line'] - 2 * df['pivot_std'] / np.sqrt(self.pivot_period)
        
        return df
    
    def generate_signals(self, df):
        """生成交易信号"""
        df = self.calculate_pivot_axis(df)
        
        # 计算价格相对中轴均线的偏离度
        df['deviation'] = (df['close'] - df['signal_line']) / df['signal_line']
        
        # 生成信号
        # 买入：收盘价突破上轨且偏离度超过阈值
        df['buy_signal'] = (df['close'] > df['upper_band']) & (df['deviation'] > self.threshold_pct)
        
        # 卖出：收盘价跌破下轨或偏离度过低
        df['sell_signal'] = (df['close'] < df['lower_band']) | (df['deviation'] < -self.threshold_pct)
        
        return df
    
    def backtest(self, df, initial_capital=100000):
        """
        执行回测
        
        返回：
            trades: 交易记录列表
            equity_curve: 权益曲线DataFrame
            stats: 统计指标
        """
        df = self.generate_signals(df)
        df = df.dropna()
        
        if len(df) == 0:
            return None, None, None
        
        trades = []
        equity_curve = []
        
        position = 0  # 持仓数量
        cash = initial_capital
        entry_price = 0
        entry_date = None
        max_price = 0  # 持仓期间最高价（用于移动止盈）
        
        for i, row in df.iterrows():
            date = row['date']
            close = row['close']
            buy_signal = row['buy_signal']
            sell_signal = row['sell_signal']
            
            equity = cash + position * close
            equity_curve.append({'date': date, 'equity': equity, 'close': close})
            
            if position == 0:  # 空仓
                if buy_signal:
                    # 买入
                    position = int(cash / close)
                    if position > 0:
                        entry_price = close
                        entry_date = date
                        max_price = close
                        cash -= position * close
                        trades.append({
                            'type': 'BUY',
                            'date': date,
                            'price': close,
                            'shares': position,
                            'value': position * close
                        })
            else:  # 持仓中
                max_price = max(max_price, close)
                
                # 计算当前盈亏
                unrealized_pnl = (close - entry_price) / entry_price
                max_drawdown_from_peak = (max_price - close) / max_price
                
                # 止损条件
                stop_loss_triggered = unrealized_pnl < -self.stop_loss_pct
                
                # 止盈条件（固定止盈或回撤止盈）
                take_profit_triggered = unrealized_pnl > self.take_profit_pct
                trailing_stop_triggered = max_drawdown_from_peak > 0.05 and unrealized_pnl > 0.02
                
                if sell_signal or stop_loss_triggered or take_profit_triggered or trailing_stop_triggered:
                    # 卖出
                    sell_value = position * close
                    pnl = sell_value - (position * entry_price)
                    pnl_pct = pnl / (position * entry_price) * 100
                    
                    exit_reason = 'SIGNAL'
                    if stop_loss_triggered:
                        exit_reason = 'STOP_LOSS'
                    elif take_profit_triggered:
                        exit_reason = 'TAKE_PROFIT'
                    elif trailing_stop_triggered:
                        exit_reason = 'TRAILING_STOP'
                    
                    trades.append({
                        'type': 'SELL',
                        'date': date,
                        'price': close,
                        'shares': position,
                        'value': sell_value,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct,
                        'exit_reason': exit_reason,
                        'hold_days': (datetime.strptime(date, '%Y-%m-%d') - datetime.strptime(entry_date, '%Y-%m-%d')).days
                    })
                    
                    cash = sell_value
                    position = 0
                    entry_price = 0
        
        # 计算最终权益
        final_equity = cash + position * df.iloc[-1]['close']
        
        # 统计指标
        stats = self.calculate_stats(trades, equity_curve, initial_capital, final_equity)
        
        return trades, pd.DataFrame(equity_curve), stats
    
    def calculate_stats(self, trades, equity_curve, initial_capital, final_equity):
        """计算回测统计指标"""
        if not trades:
            return {}
        
        df_equity = pd.DataFrame(equity_curve)
        if len(df_equity) == 0:
            return {}
        
        # 计算收益率
        total_return = (final_equity - initial_capital) / initial_capital * 100
        
        # 计算年化收益率
        days = len(df_equity)
        annual_return = ((final_equity / initial_capital) ** (252 / days) - 1) * 100 if days > 0 else 0
        
        # 计算最大回撤
        df_equity['peak'] = df_equity['equity'].cummax()
        df_equity['drawdown'] = (df_equity['equity'] - df_equity['peak']) / df_equity['peak']
        max_drawdown = df_equity['drawdown'].min() * 100
        
        # 交易统计
        sell_trades = [t for t in trades if t['type'] == 'SELL']
        if sell_trades:
            win_trades = [t for t in sell_trades if t['pnl'] > 0]
            loss_trades = [t for t in sell_trades if t['pnl'] <= 0]
            
            win_rate = len(win_trades) / len(sell_trades) * 100
            avg_win = np.mean([t['pnl_pct'] for t in win_trades]) if win_trades else 0
            avg_loss = np.mean([t['pnl_pct'] for t in loss_trades]) if loss_trades else 0
            avg_hold_days = np.mean([t['hold_days'] for t in sell_trades])
        else:
            win_rate = avg_win = avg_loss = avg_hold_days = 0
        
        # 计算夏普比率（简化版，假设无风险利率为0）
        if len(df_equity) > 1:
            daily_returns = df_equity['equity'].pct_change().dropna()
            sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() != 0 else 0
        else:
            sharpe_ratio = 0
        
        return {
            '初始资金': initial_capital,
            '最终资金': round(final_equity, 2),
            '总收益率': round(total_return, 2),
            '年化收益率': round(annual_return, 2),
            '最大回撤': round(max_drawdown, 2),
            '交易次数': len(sell_trades),
            '胜率': round(win_rate, 2),
            '平均盈利': round(avg_win, 2),
            '平均亏损': round(avg_loss, 2),
            '平均持仓天数': round(avg_hold_days, 1),
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
    print("中轴价格策略回测结果")
    print(f"参数: 中轴周期=20日, 均线周期=5日, 阈值=2%, 止损=8%, 止盈=15%")
    print("=" * 80)
    
    all_stats = []
    
    for stock_code in sorted(stocks):
        df_stock = df_all[df_all['stock_code'] == stock_code].copy()
        stock_name = df_stock['stock_name'].iloc[0]
        
        if len(df_stock) < 60:  # 数据太少跳过
            print(f"\n{stock_code} {stock_name}: 数据不足 ({len(df_stock)} 条)，跳过")
            continue
        
        # 运行回测
        strategy = PivotAxisStrategy(
            pivot_period=20,
            ma_period=5,
            threshold_pct=0.02,
            stop_loss_pct=0.08,
            take_profit_pct=0.15
        )
        
        trades, equity_curve, stats = strategy.backtest(df_stock, initial_capital=100000)
        
        if stats:
            print(f"\n📈 {stock_code} {stock_name}")
            print("-" * 60)
            for key, value in stats.items():
                if isinstance(value, float):
                    print(f"  {key}: {value}%" if '率' in key or '回撤' in key or '盈利' in key or '亏损' in key else f"  {key}: {value}")
                else:
                    print(f"  {key}: {value}")
            
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
        avg_win_rate = df_stats['胜率'].mean()
        
        print(f"  平均总收益率: {avg_return:.2f}%")
        print(f"  平均年化收益率: {avg_annual:.2f}%")
        print(f"  平均最大回撤: {avg_drawdown:.2f}%")
        print(f"  平均胜率: {avg_win_rate:.2f}%")
        print(f"  盈利股票数: {(df_stats['总收益率'] > 0).sum()}/{len(df_stats)}")


if __name__ == "__main__":
    run_backtest_for_all_stocks()
