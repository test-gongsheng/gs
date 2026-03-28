// 渲染股票列表 - DEBUG版本
function renderStockList() {
    console.log('[renderStockList] ========== 开始执行 ==========');
    console.log('[renderStockList] appState.stocks:', appState.stocks ? appState.stocks.length : 'undefined');
    
    const listEl = document.getElementById('stockList');
    console.log('[renderStockList] listEl:', listEl);
    
    if (!listEl) {
        console.error('[renderStockList] 找不到 stockList 元素');
        return;
    }
    
    // 强制设置 stock-list 样式 - 红色边框便于调试
    listEl.style.cssText = 'flex: 1 1 auto; overflow-y: auto; padding: 8px; min-height: 100px; background: #151b2d; border: 3px solid red !important;';
    listEl.innerHTML = '';
    console.log('[renderStockList] 已清空列表，准备渲染');

    if (!appState.stocks || appState.stocks.length === 0) {
        console.log('[renderStockList] 没有股票数据，显示空状态');
        listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: #9ca3af;">暂无持仓数据</div>';
        return;
    }

    console.log('[renderStockList] 渲染', appState.stocks.length, '只股票');
    console.log('[renderStockList] 股票代码:', appState.stocks.map(s => s.code).join(', '));

    appState.stocks.forEach((stock, index) => {
        console.log(`[renderStockList] 创建第 ${index + 1} 个股票项:`, stock.code);
        
        const item = document.createElement('div');
        item.className = 'stock-item' + (index === 0 ? ' active' : '');
        item.onclick = () => selectStock(index);

        const isUp = stock.change >= 0;
        const isHKStock = stock.market === '港股';
        const exchangeRate = stock.exchangeRate || appState.exchangeRate || 1.0836;

        const quantity = stock.holdQuantity || stock.shares || 0;
        let marketValue;
        if (isHKStock) {
            if (stock.priceCny) {
                marketValue = stock.priceCny * quantity;
            } else {
                const hkdValue = (stock.price || 0) * quantity;
                marketValue = hkdValue / exchangeRate;
            }
        } else {
            marketValue = (stock.price || 0) * quantity;
        }
        
        const marketValueWan = marketValue > 0 ? (marketValue / 10000).toFixed(1) : '0.0';

        let alertBadge = '';
        if (stock.price >= stock.triggerSell) {
            alertBadge = '<span class="stock-item-alert sell">卖</span>';
        } else if (stock.price <= stock.triggerBuy) {
            alertBadge = '<span class="stock-item-alert buy">买</span>';
        }
        
        const hkBadge = isHKStock ? '<span class="stock-item-hk">HK</span>' : '';

        // 强制添加内联样式确保可见 - 绿色边框
        item.style.cssText = 'display: flex !important; align-items: center; padding: 12px 8px; border-radius: 8px; cursor: pointer; margin-bottom: 4px; min-height: 50px; background: #1a1f2e; border: 2px solid #52c41a !important; color: white;';
        
        item.innerHTML = `
            <div class="stock-info" style="flex: 1.5; text-align: left; display: flex; flex-direction: column; gap: 2px;">
                <span class="code" style="font-weight: 600; font-size: 0.875rem; color: #e8eaed;">${stock.code}${hkBadge}${alertBadge}</span>
                <span class="name" style="font-size: 0.75rem; color: #9ca3af;">${stock.name}</span>
            </div>
            <div class="stock-price ${isUp ? 'up' : 'down'}" style="flex: 1; text-align: right; font-weight: 600; color: ${isUp ? '#ff4d4f' : '#52c41a'};">
                ${isHKStock ? (stock.price || 0).toFixed(2) + '<small>HKD</small>' : (stock.price || 0).toFixed(2)}
            </div>
            <div class="stock-change ${isUp ? 'up' : 'down'}" style="flex: 1; text-align: right; font-weight: 600; color: ${isUp ? '#ff4d4f' : '#52c41a'};">
                ${stock.change >= 0 ? '+' : ''}${(stock.changePercent || 0).toFixed(2)}%
            </div>
            <div class="stock-pnl" style="flex: 1; text-align: right; font-size: 0.75rem; color: #e8eaed;">
                ${marketValueWan}万
            </div>
        `;

        listEl.appendChild(item);
        console.log(`[renderStockList] 已添加第 ${index + 1} 个股票项到 DOM`);
    });
    
    console.log('[renderStockList] 渲染完成，列表子元素数量:', listEl.children.length);
    console.log('[renderStockList] ========== 执行结束 ==========');
}
