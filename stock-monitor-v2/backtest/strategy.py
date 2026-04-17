# -*- coding: utf-8 -*-
"""
中轴价格仓位控制法回测 - 策略模块
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

@dataclass
class Trade:
    """交易记录"""
    date: datetime
    code: str
    action: str  # 'buy' or 'sell'
    price: float
    shares: int
    amount: float
    deviation: float  # 偏离中轴比例
    reason: str

@dataclass
class Position:
    """持仓记录"""
    code: str
    base_shares: int = 0  # 底仓股数
    float_shares: int = 0  # 浮仓股数
    avg_cost: float = 0.0  # 平均成本
    total_cost: float = 0.0  # 总成本
    trades: List[Trade] = field(default_factory=list)
    
    @property
    def total_shares(self) -> int:
        return self.base_shares + self.float_shares
    
    @property
    def market_value(self, price: float = 0) -> float:
        return self.total_shares * price

class AxisGridStrategy:
    """
    中轴价格仓位控制法策略
    
    规则：
    - 单股上限：A股50万/港股150万
    - 底仓50%：长期持有，不操作
    - 浮仓50%：用于网格交易
    - 买入：偏离-8%买入浮仓20%，偏离-16%再买浮仓20%
    - 卖出：偏离+8%卖出浮仓20%，偏离+16%再卖浮仓20%
    """
    
    def __init__(self, code: str, name: str, market: str, max_position: float):
        self.code = code
        self.name = name
        self.market = market
        self.max_position = max_position
        
        # 仓位分配
        self.base_position = max_position * 0.5  # 底仓50%
        self.float_position = max_position * 0.5  # 浮仓50%
        
        # 网格档位 (浮仓的20% = 10%总仓位)
        self.grid_unit = self.float_position * 0.2
        
        # 触发阈值
        self.buy_triggers = [-0.08, -0.16]  # -8%, -16%
        self.sell_triggers = [0.08, 0.16]   # +8%, +16%
        
        # 状态
        self.position = Position(code=code)
        self.cash_used = 0.0  # 已用现金
        self.cash_released = 0.0  # 释放现金
        self.current_grid_level = 0  # 当前网格档位 (-2,-1,0,1,2)
        
    def calculate_axis_price(self, hist_df: pd.DataFrame, current_date: datetime, window: int = 90) -> float:
        """计算中轴价格（近90日均价）"""
        past_data = hist_df[hist_df['date'] < current_date].tail(window)
        if len(past_data) < window * 0.8:  # 至少需要80%数据
            return None
        return past_data['close'].mean()
    
    def get_deviation(self, current_price: float, axis_price: float) -> float:
        """计算偏离度"""
        if axis_price is None or axis_price == 0:
            return 0
        return (current_price - axis_price) / axis_price
    
    def get_target_grid_level(self, deviation: float) -> int:
        """根据偏离度确定目标网格档位"""
        if deviation <= -0.16:
            return -2
        elif deviation <= -0.08:
            return -1
        elif deviation >= 0.16:
            return 2
        elif deviation >= 0.08:
            return 1
        else:
            return 0
    
    def execute(self, date: datetime, price: float, hist_df: pd.DataFrame) -> Optional[Trade]:
        """执行策略，返回交易记录（如有）"""
        # 计算中轴价格和偏离度
        axis_price = self.calculate_axis_price(hist_df, date)
        if axis_price is None:
            return None
        
        deviation = self.get_deviation(price, axis_price)
        target_level = self.get_target_grid_level(deviation)
        
        trade = None
        
        # 买入逻辑：网格档位降低（更负）时买入
        if target_level < self.current_grid_level:
            # 计算应买入的档位数
            grids_to_buy = self.current_grid_level - target_level
            buy_amount = self.grid_unit * grids_to_buy
            shares = int(buy_amount / price)
            
            if shares > 0 and self.cash_used + shares * price <= self.max_position:
                self.position.float_shares += shares
                cost = shares * price
                self.cash_used += cost
                self.position.total_cost += cost
                
                # 更新平均成本
                if self.position.total_shares > 0:
                    self.position.avg_cost = self.position.total_cost / self.position.total_shares
                
                trade = Trade(
                    date=date,
                    code=self.code,
                    action='buy',
                    price=price,
                    shares=shares,
                    amount=cost,
                    deviation=deviation,
                    reason=f"偏离中轴{deviation*100:.1f}%，买入{grids_to_buy}档"
                )
                self.position.trades.append(trade)
                self.current_grid_level = target_level
        
        # 卖出逻辑：网格档位升高（更正）时卖出
        elif target_level > self.current_grid_level and self.position.float_shares > 0:
            # 计算应卖出的档位数
            grids_to_sell = target_level - self.current_grid_level
            sell_amount = self.grid_unit * grids_to_sell
            shares = min(int(sell_amount / price), self.position.float_shares)
            
            if shares > 0:
                self.position.float_shares -= shares
                revenue = shares * price
                self.cash_released += revenue
                
                # 调整总成本（FIFO简化处理）
                cost_basis = shares * self.position.avg_cost if self.position.avg_cost > 0 else revenue
                self.position.total_cost = max(0, self.position.total_cost - cost_basis)
                
                trade = Trade(
                    date=date,
                    code=self.code,
                    action='sell',
                    price=price,
                    shares=shares,
                    amount=revenue,
                    deviation=deviation,
                    reason=f"偏离中轴{deviation*100:.1f}%，卖出{grids_to_sell}档"
                )
                self.position.trades.append(trade)
                self.current_grid_level = target_level
        
        return trade
    
    def get_summary(self, final_price: float) -> Dict:
        """获取策略执行摘要"""
        final_value = self.position.total_shares * final_price
        total_invested = self.cash_used
        total_released = self.cash_released
        
        buy_trades = [t for t in self.position.trades if t.action == 'buy']
        sell_trades = [t for t in self.position.trades if t.action == 'sell']
        
        return {
            'code': self.code,
            'name': self.name,
            'market': self.market,
            'max_position': self.max_position,
            'final_shares': self.position.total_shares,
            'final_value': final_value,
            'total_invested': total_invested,
            'total_released': total_released,
            'net_invested': total_invested - total_released,
            'unrealized_pnl': final_value - self.position.total_cost,
            'realized_pnl': sum(t.amount - t.shares * self.position.avg_cost for t in sell_trades) if sell_trades else 0,
            'total_trades': len(self.position.trades),
            'buy_trades': len(buy_trades),
            'sell_trades': len(sell_trades),
            'avg_cost': self.position.avg_cost,
            'final_price': final_price,
        }
