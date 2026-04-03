/**
 * 股票投资监控系统 v3.0 - 重构版
 * 使用模块化架构：StateManager + API层 + 渲染层
 */

const APP_VERSION = "3.1.0";

// 版本检查与缓存清理
const lastVersion = localStorage.getItem('app_version');
if (lastVersion !== APP_VERSION) {
    console.log(`[版本更新] ${lastVersion || '无版本'} -> ${APP_VERSION}`);
    localStorage.removeItem('import_data_last');
    localStorage.removeItem('stock-monitor-cache');
    for (let i = localStorage.length - 1; i >= 0; i--) {
        const key = localStorage.key(i);
        if (key && key.startsWith('import_data_')) {
            localStorage.removeItem(key);
        }
    }
    localStorage.setItem('app_version', APP_VERSION);
}

// 全局状态（保持兼容，实际由 StateManager 代理）
const appState = {
    stocks: [],
    selectedStock: null,
    hotSectors: [],
    news: [],
    alerts: [],
    sentiment: null,
    totalAssets: 8000000,
    marketStatus: 'closed',
    version: APP_VERSION,
    _updatingQuotes: false
};
window.appState = appState;

// 初始化标记
let isInitialized = false;

// ============ 初始化 ============
async function init() {
    if (isInitialized) {
        console.log('[init] 已初始化，跳过');
        return;
    }
    isInitialized = true;
    
    console.log('[init] 股票监控系统 v3.0 启动...');
    
    // 加载股票数据
    await loadStocks();
    
    // 初始化渲染
    renderStockList();
    updateAssetOverview();
    
    // 默认选中第一只股票
    if (appState.stocks.length > 0) {
        selectStock(0);
    }
    
    // 启动定时任务
    startPeriodicTasks();
    
    console.log('[init] 初始化完成');
}

// 加载股票数据
async function loadStocks() {
    try {
        const response = await fetch('/api/stocks');
        const stocks = await response.json();
        
        if (Array.isArray(stocks) && stocks.length > 0) {
            appState.stocks = stocks.map(s => ({
                id: s.id,
                code: s.code,
                name: s.name,
                market: s.market || 'A股',
                price: s.current_price || 0,
                holdCost: s.avg_cost || 0,
                holdQuantity: s.shares || 0,
                pivotPrice: s.axis_price || 0,
                triggerBuy: s.next_buy_price || 0,
                triggerSell: s.next_sell_price || 0,
                investLimit: s.market === '港股' ? 1500000 : 500000,
                baseRatio: s.base_position_pct || 50,
                floatRatio: s.float_position_pct || 50,
                strategy: s.strategy_mode || '基础',
                gridLevels: s.grid_levels || [],
                change: 0,
                changePercent: 0,
                exchangeRate: s.exchange_rate
            }));
            localStorage.setItem('import_data_last', JSON.stringify(appState.stocks));
            console.log(`[init] 加载 ${appState.stocks.length} 只股票`);
        }
    } catch (e) {
        console.error('[init] 加载失败:', e);
        // 从 localStorage 恢复
        const saved = localStorage.getItem('import_data_last');
        if (saved) {
            try {
                appState.stocks = JSON.parse(saved);
                console.log('[init] 从缓存恢复', appState.stocks.length, '只股票');
            } catch (err) {
                console.error('[init] 恢复失败:', err);
            }
        }
    }
}

// ============ 股票选择 ============
function selectStock(index) {
    appState.selectedStock = appState.stocks[index];
    
    // 更新列表选中状态
    document.querySelectorAll('.stock-item').forEach((el, i) => {
        el.classList.toggle('active', i === index);
    });
    
    renderStockDetail();
}

// ============ 渲染函数 ============
function renderStockList() {
    const listEl = document.getElementById('stockList');
    if (!listEl) return;
    
    listEl.innerHTML = '';
    
    appState.stocks.forEach((stock, index) => {
        const isUp = stock.change >= 0;
        const isHK = stock.market === '港股';
        const currency = isHK ? 'HK$' : '¥';
        
        const item = document.createElement('div');
        item.className = `stock-item ${appState.selectedStock?.id === stock.id ? 'active' : ''}`;
        item.onclick = () => selectStock(index);
        
        item.innerHTML = `
            <div class="stock-info">
                <div class="stock-name">${stock.name}</div>
                <div class="stock-code">${stock.code}</div>
            </div>
            <div class="stock-price ${isUp ? 'up' : 'down'}">
                ${currency}${stock.price.toFixed(2)}
            </div>
            <div class="stock-change ${isUp ? 'up' : 'down'}">
                ${isUp ? '+' : ''}${stock.changePercent.toFixed(2)}%
            </div>
        `;
        
        listEl.appendChild(item);
    });
}

function renderStockDetail() {
    const stock = appState.selectedStock;
    if (!stock) return;
    
    const isHK = stock.market === '港股';
    const currency = isHK ? 'HK$' : '¥';
    
    // 基本信息
    setText('stockName', stock.name);
    setText('stockCode', stock.code);
    setText('stockMarket', stock.market);
    
    // 价格信息
    setText('currentPrice', `${currency}${stock.price.toFixed(2)}`);
    setText('priceChange', `${stock.change >= 0 ? '+' : ''}${stock.change.toFixed(2)} (${stock.changePercent >= 0 ? '+' : ''}${stock.changePercent.toFixed(2)}%)`);
    
    // 中轴价格区间
    setText('pivotRange', `${currency}${stock.triggerBuy.toFixed(2)} - ${currency}${stock.triggerSell.toFixed(2)}`);
    
    // 港股显示南向资金
    const southboundEl = document.getElementById('southboundSection');
    if (southboundEl) {
        southboundEl.style.display = isHK ? 'block' : 'none';
        if (isHK && typeof loadSouthboundStockData === 'function') {
            loadSouthboundStockData(stock.code);
        }
    }
}

function updateAssetOverview() {
    let totalMarketValue = 0;
    let totalCost = 0;
    
    appState.stocks.forEach(stock => {
        const isHK = stock.market === '港股';
        const rate = isHK ? (stock.exchangeRate || 0.92) : 1;
        totalMarketValue += stock.price * stock.holdQuantity * rate;
        totalCost += stock.holdCost * stock.holdQuantity * rate;
    });
    
    const pnl = totalMarketValue - totalCost;
    const pnlPercent = totalCost > 0 ? (pnl / totalCost) * 100 : 0;
    
    setText('totalAssets', `¥${(totalMarketValue / 10000).toFixed(2)}万`);
    setText('totalPnl', `${pnl >= 0 ? '+' : ''}¥${(pnl / 10000).toFixed(2)}万 (${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%)`);
}

// 辅助函数
function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

// ============ 定时任务 ============
function startPeriodicTasks() {
    // 更新行情（每30秒）
    setInterval(updateStockPricesOnce, 30000);
    
    // 立即更新一次
    updateStockPricesOnce();
}

async function updateStockPricesOnce() {
    if (appState._updatingQuotes) return;
    appState._updatingQuotes = true;
    
    try {
        const codes = appState.stocks.map(s => s.code).join(',');
        const response = await fetch(`/api/quotes?codes=${codes}`);
        const quotes = await response.json();
        
        if (quotes.success) {
            quotes.data.forEach(quote => {
                const stock = appState.stocks.find(s => s.code === quote.code);
                if (stock) {
                    stock.price = quote.price;
                    stock.change = quote.change;
                    stock.changePercent = quote.changePercent;
                }
            });
            
            renderStockList();
            updateAssetOverview();
            if (appState.selectedStock) {
                renderStockDetail();
            }
        }
    } catch (e) {
        console.error('[updateQuotes] 失败:', e);
    } finally {
        appState._updatingQuotes = false;
    }
}

// ============ 全局接口 ============
window.selectStock = selectStock;
window.renderStockList = renderStockList;
window.renderStockDetail = renderStockDetail;
window.updateStockPricesOnce = updateStockPricesOnce;
window.init = init;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', init);
