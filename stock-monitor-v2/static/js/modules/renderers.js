/**
 * Renderers - 渲染函数集合
 * 所有DOM操作集中管理，保持与原有界面兼容
 */

// 渲染股票列表
function renderStockList(stocks, options = {}) {
    const { 
        containerId = 'stockList', 
        selectedCode = null,
        onSelect = null 
    } = options;
    
    const container = document.getElementById(containerId);
    if (!container) {
        console.warn(`[Render] 容器 #${containerId} 不存在`);
        return;
    }
    
    if (!stocks || stocks.length === 0) {
        container.innerHTML = '<div class="empty-state">暂无股票</div>';
        return;
    }
    
    container.innerHTML = '';
    
    stocks.forEach((stock, index) => {
        const item = document.createElement('div');
        item.className = `stock-item ${stock.code === selectedCode ? 'active' : ''}`;
        item.dataset.code = stock.code;
        item.dataset.index = index;
        
        const isUp = (stock.changePercent || 0) >= 0;
        const isHK = stock.market === '港股';
        const marketValueWan = ((stock.price || 0) * (stock.holdQuantity || 0) / 10000).toFixed(0);
        
        item.innerHTML = `
            <div class="stock-info">
                <span class="code">${stock.code}${isHK ? '<span class="hk-badge">港</span>' : ''}</span>
                <span class="name">${stock.name || '--'}</span>
            </div>
            <div class="stock-price ${isUp ? 'up' : 'down'}">${(stock.price || 0).toFixed(2)}</div>
            <div class="stock-change ${isUp ? 'up' : 'down'}">${isUp ? '+' : ''}${(stock.changePercent || 0).toFixed(2)}%</div>
            <div class="stock-pnl">${marketValueWan}万</div>
        `;
        
        if (onSelect) {
            item.addEventListener('click', () => onSelect(stock, index));
        }
        
        container.appendChild(item);
    });
}

// 渲染股票详情
function renderStockDetail(stock, options = {}) {
    if (!stock) {
        console.warn('[Render] 没有股票数据');
        return;
    }
    
    const { 
        onRefreshAxis = null,
        onLoadSouthbound = null 
    } = options;
    
    // 安全获取字段
    const safe = (val, def = 0) => val ?? def;
    const safeStr = (val, def = '--') => val || def;
    
    const isHK = stock.market === '港股';
    const currency = isHK ? 'HK$' : '¥';
    const isUp = safe(stock.change) >= 0;
    
    // 更新基础信息
    const nameEl = document.getElementById('stockName');
    const codeEl = document.getElementById('stockCode');
    const priceEl = document.getElementById('stockPrice');
    const changeEl = document.getElementById('stockChange');
    
    if (nameEl) nameEl.textContent = safeStr(stock.name);
    if (codeEl) codeEl.textContent = safeStr(stock.code) + (isHK ? ' 港股' : ' A股');
    if (priceEl) priceEl.textContent = currency + safe(stock.price).toFixed(2);
    if (changeEl) {
        changeEl.textContent = `${isUp ? '+' : ''}${safe(stock.change).toFixed(2)} (${isUp ? '+' : ''}${safe(stock.changePercent).toFixed(2)}%)`;
        changeEl.className = `stock-change ${isUp ? 'up' : 'down'}`;
    }
    
    // 更新持仓信息
    const holdQtyEl = document.getElementById('holdQuantity');
    const holdCostEl = document.getElementById('holdCost');
    const marketValueEl = document.getElementById('marketValue');
    const pnlEl = document.getElementById('pnl');
    
    const marketValue = safe(stock.price) * safe(stock.holdQuantity);
    const costValue = safe(stock.holdCost) * safe(stock.holdQuantity);
    const pnl = marketValue - costValue;
    const pnlPercent = costValue > 0 ? (pnl / costValue) * 100 : 0;
    
    if (holdQtyEl) holdQtyEl.textContent = safe(stock.holdQuantity).toLocaleString();
    if (holdCostEl) holdCostEl.textContent = currency + safe(stock.holdCost).toFixed(2);
    if (marketValueEl) marketValueEl.textContent = currency + (marketValue / 10000).toFixed(2) + '万';
    if (pnlEl) {
        pnlEl.textContent = `${pnl >= 0 ? '+' : ''}${currency}${(pnl / 10000).toFixed(2)}万 (${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%)`;
        pnlEl.className = `pnl ${pnl >= 0 ? 'up' : 'down'}`;
    }
    
    // 更新中轴价格
    const pivotEl = document.getElementById('pivotPrice');
    const buyTriggerEl = document.getElementById('triggerBuy');
    const sellTriggerEl = document.getElementById('triggerSell');
    
    if (pivotEl) {
        pivotEl.textContent = safe(stock.pivotPrice) > 0 
            ? currency + safe(stock.pivotPrice).toFixed(2)
            : '未设置';
    }
    if (buyTriggerEl) buyTriggerEl.textContent = safe(stock.triggerBuy) > 0 ? currency + safe(stock.triggerBuy).toFixed(2) : '--';
    if (sellTriggerEl) sellTriggerEl.textContent = safe(stock.triggerSell) > 0 ? currency + safe(stock.triggerSell).toFixed(2) : '--';
    
    // 港股特殊处理
    const southboundSection = document.getElementById('southboundSection');
    const hkShortSection = document.getElementById('hkShortRiskWarning');
    
    if (isHK) {
        if (southboundSection) {
            southboundSection.style.display = 'block';
            if (onLoadSouthbound) onLoadSouthbound(stock.code);
        }
        if (hkShortSection) hkShortSection.style.display = 'block';
    } else {
        if (southboundSection) southboundSection.style.display = 'none';
        if (hkShortSection) hkShortSection.style.display = 'none';
    }
}

// 渲染南向资金数据
function renderSouthbound(data, stockCode) {
    if (!data) {
        console.warn('[Render] 没有南向资金数据');
        return;
    }
    
    console.log(`[Render] 渲染南向资金: ${stockCode}`);
    
    const { stats, stockName } = data;
    
    // 更新统计卡片
    const ratioEl = document.getElementById('stockSouthboundRatio');
    const net30dEl = document.getElementById('stockSouthbound30d');
    const signalEl = document.getElementById('stockSouthboundSignal');
    
    if (ratioEl) ratioEl.textContent = stats ? `${stats.count}日数据` : '--';
    if (net30dEl) {
        const net30d = stats?.total30d || 0;
        const isInflow = net30d >= 0;
        // 后端返回的已经是亿港元单位
        net30dEl.textContent = `${isInflow ? '+' : ''}${net30d.toFixed(2)}亿港元`;
        net30dEl.className = isInflow ? 'up' : 'down';
    }
    if (signalEl) {
        const signal = stats?.total30d > 0 ? '增持' : stats?.total30d < 0 ? '减持' : '中性';
        signalEl.textContent = signal;
    }
    
    // 触发图表渲染事件
    window.dispatchEvent(new CustomEvent('southboundDataLoaded', { 
        detail: { data, stockCode, stockName } 
    }));
}

// 渲染资产总览
function renderAssetOverview(totalAssets, stocks) {
    if (!stocks || stocks.length === 0) return;
    
    const totalMarketValue = stocks.reduce((sum, s) => 
        sum + (s.price || 0) * (s.holdQuantity || 0), 0
    );
    const totalCost = stocks.reduce((sum, s) => 
        sum + (s.holdCost || 0) * (s.holdQuantity || 0), 0
    );
    const totalPnl = totalMarketValue - totalCost;
    const pnlPercent = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0;
    
    const marketValueEl = document.getElementById('totalMarketValue');
    const pnlEl = document.getElementById('totalPnl');
    const cashEl = document.getElementById('cashPosition');
    
    if (marketValueEl) marketValueEl.textContent = `¥${(totalMarketValue / 10000).toFixed(0)}万`;
    if (pnlEl) {
        pnlEl.textContent = `${totalPnl >= 0 ? '+' : ''}¥${(totalPnl / 10000).toFixed(0)}万 (${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%)`;
        pnlEl.className = totalPnl >= 0 ? 'up' : 'down';
    }
    if (cashEl) cashEl.textContent = `¥${((totalAssets - totalMarketValue) / 10000).toFixed(0)}万`;
}

// 导出
window.Renderers = {
    renderStockList,
    renderStockDetail,
    renderSouthbound,
    renderAssetOverview
};

export {
    renderStockList,
    renderStockDetail,
    renderSouthbound,
    renderAssetOverview
};
