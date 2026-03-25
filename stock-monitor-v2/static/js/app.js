/**
 * 股票投资监控系统 v2.1 - 前端逻辑
 * 版本: 2026-03-16 - 添加自动刷新中轴价格功能
 */

// 版本号，用于强制刷新缓存
const APP_VERSION = '2.5.1';

// 检查版本，如果不匹配则强制刷新
const lastVersion = localStorage.getItem('app_version');
if (lastVersion !== APP_VERSION) {
    console.log(`[版本更新] ${lastVersion || '无版本'} -> ${APP_VERSION}，清除所有缓存...`);
    // 清除所有相关缓存
    localStorage.removeItem('import_data_last');
    localStorage.removeItem('stock-monitor-cache');
    // 清除所有导入历史
    for (let i = localStorage.length - 1; i >= 0; i--) {
        const key = localStorage.key(i);
        if (key && key.startsWith('import_data_')) {
            localStorage.removeItem(key);
        }
    }
    localStorage.setItem('app_version', APP_VERSION);
    console.log('[版本更新] 缓存清除完成');
}

// 全局状态
const appState = {
    stocks: [],
    selectedStock: null,
    hotSectors: [],
    news: [],
    alerts: [],
    sentiment: null,  // 市场情绪数据
    totalAssets: 8000000, // 800万
    marketStatus: 'closed',
    version: APP_VERSION
};

// 挂载到 window 对象，供其他脚本访问
window.appState = appState;

// 模拟数据 - 初始为空，从localStorage读取或等待数据导入
const mockStocks = [];

const mockHotSectors = [
    { name: '半导体', change: 3.2 },
    { name: '黄金', change: 2.8 },
    { name: 'AI人工智能', change: 2.5 },
    { name: '新能源', change: 1.9 },
    { name: '稀土', change: 1.5 }
];

const mockNews = [
    { time: '10:30', title: '阿里巴巴财报超预期，云业务增长34%', tag: 'important' },
    { time: '10:15', title: '美联储3月议息会议在即，黄金价格上涨', tag: 'normal' },
    { time: '09:45', title: '半导体板块资金净流入超50亿', tag: 'normal' },
    { time: '09:30', title: '港股通今日净流入港股25亿港元', tag: 'normal' }
];

// 初始化
async function init() {
    // 首先尝试从后端 API 加载数据
    let loadedFromBackend = false;
    try {
        const response = await fetch('/api/stocks');
        const stocks = await response.json();
        if (Array.isArray(stocks) && stocks.length > 0) {
            // 转换后端数据格式为前端格式
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
                exchangeRate: s.exchange_rate || 1.1339
            }));
            loadedFromBackend = true;
            console.log('已从后端 API 加载', appState.stocks.length, '只股票');
            // 同时保存到 localStorage 作为备份
            localStorage.setItem('import_data_last', JSON.stringify(appState.stocks));
        }
    } catch (e) {
        console.error('从后端加载数据失败:', e);
    }
    
    // 如果后端没有数据，尝试从 localStorage 读取
    if (!loadedFromBackend) {
        const savedStocks = localStorage.getItem('import_data_last');
        if (savedStocks) {
            try {
                const stocks = JSON.parse(savedStocks);
                if (stocks && stocks.length > 0) {
                    appState.stocks = stocks;
                    console.log('已从 localStorage 恢复', stocks.length, '只股票');
                } else {
                    appState.stocks = mockStocks;
                }
            } catch (e) {
                console.error('读取本地数据失败:', e);
                appState.stocks = mockStocks;
            }
        } else {
            appState.stocks = mockStocks;
        }
    }
    
    appState.hotSectors = mockHotSectors;
    appState.news = mockNews;  // 先显示模拟数据，然后异步加载真实数据

    renderStockList();
    renderHotSectors();
    renderNews();
    updateTime();
    updateMarketStatus();
    updateAssetOverview();

    // 默认选中第一个股票
    if (appState.stocks.length > 0) {
        selectStock(0);
    }

    // 定时更新
    setInterval(updateTime, 1000);
    setInterval(simulatePriceUpdate, 3000);
    
    // 定时刷新热点板块（每30秒）
    setInterval(loadHotSectors, 30000);
    
    // 定时刷新市场情绪（每60秒）
    setInterval(loadSentiment, 60000);
    
    // 定时刷新新闻（每60秒）
    setInterval(loadNews, 60000);

    // 绑定表单提交
    document.getElementById('addStockForm').addEventListener('submit', handleAddStock);
    
    // 页面加载完成后，加载实时热点板块数据
    console.log('加载热点板块数据...');
    await loadHotSectors();
    
    // 页面加载完成后，加载市场情绪数据
    console.log('加载市场情绪数据...');
    await loadSentiment();
    
    // 页面加载完成后，加载实时新闻
    console.log('加载财联社实时新闻...');
    await loadNews();
    
    // 页面加载完成后，立即获取一次实时行情（获取当天收盘价）
    if (appState.stocks.length > 0) {
        console.log('初始化完成，立即获取实时行情...');
        await updateStockPricesOnce();
    }
    
    // 页面加载完成后，异步重新计算中轴价格（确保数据最新）
    if (appState.stocks.length > 0) {
        console.log('开始异步刷新中轴价格...');
        await refreshAxisPrices();
    }
}

/**
 * 刷新所有股票的中轴价格
 * @param {boolean} forceRefresh - 是否强制刷新（清除缓存）
 */
async function refreshAxisPrices(forceRefresh = false) {
    console.log('[refreshAxisPrices] 开始执行，股票数量:', appState.stocks.length, '强制刷新:', forceRefresh);
    
    // 如果强制刷新，先清除后端缓存
    if (forceRefresh) {
        console.log('[refreshAxisPrices] 清除后端缓存...');
        try {
            await fetch('/api/axis-price/cache/clear', { method: 'POST' });
            console.log('[refreshAxisPrices] 缓存已清除');
        } catch (e) {
            console.warn('[refreshAxisPrices] 清除缓存失败:', e);
        }
    }
    
    console.log('[refreshAxisPrices] 股票列表:', appState.stocks.map(s => s.code).join(', '));
    
    if (appState.stocks.length === 0) {
        console.log('[refreshAxisPrices] 没有持仓数据，跳过');
        return;
    }
    
    let updatedCount = 0;
    let failedCount = 0;
    let changedStocks = [];
    
    // 并行处理所有股票，大幅提升速度（有缓存时 < 1秒完成）
    console.log(`[refreshAxisPrices] 开始并行处理 ${appState.stocks.length} 只股票...`);
    
    const promises = appState.stocks.map(async (stock) => {
        try {
            console.log(`[refreshAxisPrices] 调用API: ${stock.code}`);
            
            // 使用 AbortController 设置8秒超时
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 8000);
            
            const response = await fetch('/api/axis-price', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    code: stock.code, 
                    market: stock.market || 'A股', 
                    days: 90 
                }),
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                console.error(`[refreshAxisPrices] ${stock.code} HTTP错误: ${response.status}`);
                return { stock, success: false };
            }
            
            const axisData = await response.json();
            
            if (axisData.success && axisData.data && axisData.data.axis_price) {
                const oldPivot = parseFloat(stock.pivotPrice) || 0;
                const newPivot = axisData.data.axis_price;
                
                // 直接修改 stock 对象
                stock.pivotPrice = newPivot;
                stock.triggerBuy = axisData.data.trigger_buy;
                stock.triggerSell = axisData.data.trigger_sell;
                
                // 同步更新后端数据库（不等待）
                fetch(`/api/stocks/${stock.id}/axis`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        axis_price: newPivot,
                        base_position_pct: stock.baseRatio || 50,
                        float_position_pct: stock.floatRatio || 50,
                        trigger_pct: 8,
                        grid_levels: stock.gridLevels || []
                    })
                }).catch(e => console.warn(`[refreshAxisPrices] ${stock.code} 保存到后端失败:`, e));
                
                console.log(`[refreshAxisPrices] ${stock.code} 更新: ${oldPivot.toFixed(2)} -> ${newPivot.toFixed(2)}`);
                
                return { 
                    stock, 
                    success: true, 
                    changed: Math.abs(oldPivot - newPivot) > 0.1,
                    oldPrice: oldPivot,
                    newPrice: newPivot
                };
            } else {
                console.warn(`[refreshAxisPrices] ${stock.code} API返回失败:`, axisData.error || '无数据');
                return { stock, success: false };
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                console.warn(`[refreshAxisPrices] ${stock.code} 请求超时(8秒)`);
            } else {
                console.error(`[refreshAxisPrices] ${stock.code} 异常:`, error.message);
            }
            return { stock, success: false };
        }
    });
    
    // 等待所有请求完成
    const results = await Promise.all(promises);
    
    // 统计结果
    results.forEach(result => {
        if (result.success) {
            updatedCount++;
            if (result.changed) {
                changedStocks.push({
                    code: result.stock.code,
                    name: result.stock.name,
                    oldPrice: result.oldPrice,
                    newPrice: result.newPrice
                });
            }
        } else {
            failedCount++;
        }
    });
    
    console.log(`[refreshAxisPrices] 完成: ${updatedCount}只成功, ${failedCount}只失败, ${changedStocks.length}只变化`);
    
    // 保存到 localStorage
    try {
        localStorage.setItem('import_data_last', JSON.stringify(appState.stocks));
        console.log('[refreshAxisPrices] 已保存到 localStorage');
    } catch (e) {
        console.error('[refreshAxisPrices] 保存到 localStorage 失败:', e);
    }
    
    // 重新渲染 - 确保使用最新的数据
    renderStockList();
    
    // 强制重新获取选中的股票对象（确保引用正确）
    if (appState.selectedStock) {
        const updatedStock = appState.stocks.find(s => s.code === appState.selectedStock.code);
        if (updatedStock) {
            // 完全替换 selectedStock 对象，确保所有字段都是最新的
            appState.selectedStock = updatedStock;
            console.log('[refreshAxisPrices] 已更新 selectedStock:', updatedStock.code, 'pivotPrice=', updatedStock.pivotPrice);
            renderStockDetail();
        }
    }
    updateAssetOverview();
    
    // 显示通知（如果函数可用）
    if (typeof showNotification === 'function') {
        if (changedStocks.length > 0) {
            const changes = changedStocks.slice(0, 3).map(s => `${s.name}: ${s.oldPrice.toFixed(2)}→${s.newPrice.toFixed(2)}`).join(', ');
            const more = changedStocks.length > 3 ? ` 等${changedStocks.length}只` : '';
            showNotification(`已更新${changedStocks.length}只股票中轴价格: ${changes}${more}`, 'success');
        } else {
            showNotification(`中轴价格已是最新 (${updatedCount}只成功${failedCount > 0 ? ', ' + failedCount + '只失败' : ''})`, 'success');
        }
    }
    
    return { updatedCount, failedCount, changedStocks };
}

// 更新时间
function updateTime() {
    const now = new Date();
    const timeStr = now.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    document.getElementById('currentTime').textContent = timeStr;
}

// 更新市场状态
function updateMarketStatus() {
    const now = new Date();
    const hour = now.getHours();
    const minute = now.getMinutes();
    const day = now.getDay(); // 0=周日, 1=周一, ..., 6=周六
    const timeValue = hour * 100 + minute;

    // 周末休市
    if (day === 0 || day === 6) {
        appState.marketStatus = 'closed';
        const dot = document.getElementById('marketStatusDot');
        const text = document.getElementById('marketStatusText');
        if (dot) dot.style.background = '#f44336';
        if (text) text.textContent = '周末休市';
        return;
    }

    // A股交易时间：9:30-11:30, 13:00-15:00
    // 港股交易时间：9:30-12:00, 13:00-16:00
    // 同时支持A股和港股，取并集：9:30-11:30, 13:00-16:00
    const isTrading = (timeValue >= 930 && timeValue <= 1130) ||
                      (timeValue >= 1300 && timeValue <= 1600);

    appState.marketStatus = isTrading ? 'open' : 'closed';

    const dot = document.getElementById('marketStatusDot');
    const text = document.getElementById('marketStatusText');

    if (!dot || !text) return;

    if (isTrading) {
        dot.style.background = '#4caf50';
        text.textContent = '交易中';
    } else {
        dot.style.background = '#f44336';
        // 区分是午休还是已收盘
        if (timeValue >= 1130 && timeValue < 1300) {
            text.textContent = '午间休市';
        } else {
            text.textContent = '休市中';
        }
    }
}

// 更新资产概览
function updateAssetOverview() {
    let totalPosition = 0;
    let todayPnL = 0;

    appState.stocks.forEach(stock => {
        const isHKStock = stock.market === '港股';
        let marketValue, costValue;
        // 数据文件中字段可能是 shares 或 holdQuantity
        const quantity = stock.holdQuantity || stock.shares || 0;
        
        if (isHKStock) {
            // 港股：使用昨日收盘汇率（导入时记录的固定汇率）
            const exchangeRate = stock.exchangeRate || appState.exchangeRate || 1.1339;
            // 实时计算港币市值，转换为人民币
            const hkdValue = (stock.price || 0) * quantity;
            marketValue = hkdValue / exchangeRate;
            costValue = (stock.holdCost || 0) * quantity; // holdCost 已是人民币
        } else {
            // A股：直接计算人民币市值
            marketValue = (stock.price || 0) * quantity;
            costValue = (stock.holdCost || 0) * quantity;
        }
        
        totalPosition += marketValue;
        todayPnL += (marketValue - costValue) * ((stock.changePercent || 0) / 100);
    });

    const availableCash = appState.totalAssets - totalPosition;
    const pnlPercent = totalPosition > 0 ? (todayPnL / totalPosition * 100).toFixed(2) : '0.00';
    const positionRatio = appState.totalAssets > 0 ? (totalPosition / appState.totalAssets * 100).toFixed(1) : '0.0';

    // 更新总资产
    const totalAssetsEl = document.getElementById('totalAssets');
    if (totalAssetsEl) totalAssetsEl.textContent = formatMoney(appState.totalAssets);

    // 更新持仓市值和可用资金
    document.getElementById('totalPosition').textContent = formatMoney(totalPosition);
    document.getElementById('availableCash').textContent = formatMoney(availableCash);

    // 更新当日盈亏
    const pnlValueEl = document.getElementById('todayPnLValue');
    const pnlPercentEl = document.getElementById('todayPnLPercent');

    if (pnlValueEl) pnlValueEl.textContent = (todayPnL >= 0 ? '+' : '') + formatMoney(todayPnL);
    if (pnlPercentEl) {
        pnlPercentEl.textContent = (todayPnL >= 0 ? '+' : '') + pnlPercent + '%';
        pnlPercentEl.className = 'pnl-percent ' + (todayPnL >= 0 ? '' : 'down');
    }

    // 更新仓位比例
    const positionRatioEl = document.getElementById('positionRatio');
    if (positionRatioEl) positionRatioEl.textContent = positionRatio + '%';

    // 更新仓位圆环
    const positionRingEl = document.getElementById('positionRing');
    if (positionRingEl) {
        positionRingEl.setAttribute('stroke-dasharray', `${positionRatio}, 100`);
    }
}

// 渲染股票列表
function renderStockList() {
    const listEl = document.getElementById('stockList');
    listEl.innerHTML = '';

    appState.stocks.forEach((stock, index) => {
        const item = document.createElement('div');
        item.className = 'stock-item' + (index === 0 ? ' active' : '');
        item.onclick = () => selectStock(index);

        const isUp = stock.change >= 0;
        const isHKStock = stock.market === '港股';
        // 港股使用昨日收盘汇率（导入时记录的固定汇率）
        const exchangeRate = stock.exchangeRate || appState.exchangeRate || 1.1339;

        // 港股市值实时计算（港币价格 × 持仓数量 ÷ 汇率 = 人民币市值）
        // 注意：数据文件中字段可能是 shares 或 holdQuantity
        const quantity = stock.holdQuantity || stock.shares || 0;
        let marketValue;
        if (isHKStock) {
            const hkdValue = (stock.price || 0) * quantity;
            marketValue = hkdValue / exchangeRate; // 汇率是1人民币=X港币
        } else {
            marketValue = (stock.price || 0) * quantity;
        }
        
        const marketValueWan = marketValue > 0 ? (marketValue / 10000).toFixed(1) : '0.0';

        // 检查是否触发买卖
        let alertBadge = '';
        if (stock.price >= stock.triggerSell) {
            alertBadge = '<span class="stock-item-alert sell">卖</span>';
        } else if (stock.price <= stock.triggerBuy) {
            alertBadge = '<span class="stock-item-alert buy">买</span>';
        }
        
        // 港股标识
        const hkBadge = isHKStock ? '<span class="stock-item-hk">HK</span>' : '';

        item.innerHTML = `
            <div class="stock-item-header">
                <div>
                    <span class="stock-item-name">${stock.name}</span>
                    <span class="stock-item-code">${stock.code}</span>
                    ${hkBadge}
                    ${alertBadge}
                </div>
                <div class="stock-item-price ${isUp ? 'up' : 'down'}">
                    ${isHKStock ? (stock.price || 0).toFixed(2) + ' HKD' : (stock.price || 0).toFixed(2)}
                </div>
            </div>
            <div class="stock-item-info">
                <span>${stock.change >= 0 ? '+' : ''}${(stock.changePercent || 0).toFixed(2)}%</span>
                <span>持仓: ${marketValueWan}万</span>
            </div>
        `;

        listEl.appendChild(item);
    });
}

// 选择股票
function selectStock(index) {
    appState.selectedStock = appState.stocks[index];

    // 更新列表选中状态
    document.querySelectorAll('.stock-item').forEach((el, i) => {
        el.classList.toggle('active', i === index);
    });

    renderStockDetail();
}

// 渲染股票详情
function renderStockDetail() {
    const stock = appState.selectedStock;
    if (!stock) return;

    const isUp = stock.change >= 0;
    const isHKStock = stock.market === '港股';

    // 获取汇率（用于港股港币/人民币转换）
    const exchangeRate = stock.exchangeRate || appState.exchangeRate || 0.92;

    // 港股：
    // - 显示实时港币价格 (stock.price)
    // - 市值实时计算：港币价格 × 持仓数量 ÷ 昨日收盘汇率 = 人民币市值
    // - 盈亏 = 人民币市值 - 人民币成本
    let marketValue, costValue, pnl, pnlPercent, positionShares, positionValueHkd;

    if (isHKStock) {
        // 港股使用昨日收盘汇率（导入时记录的固定汇率）
        const yesterdayRate = stock.exchangeRate || exchangeRate || 1.1339;
        // 港股当前持仓 = 股数 × 港股实时价格（港币）÷ 昨日收盘汇率 = 人民币市值
        // 注意：数据文件中字段可能是 shares 或 holdQuantity
        positionShares = stock.holdQuantity || stock.shares || 0;
        const priceHk = stock.price ?? 0;
        positionValueHkd = priceHk * positionShares; // 港币市值
        marketValue = positionValueHkd / yesterdayRate;   // 转换为人民币（汇率是1人民币=X港币）
        
        // 持仓成本是导入的人民币成本，无需转换
        const holdCostCny = stock.holdCost || 0;
        costValue = holdCostCny * positionShares; // 人民币成本
        
        pnl = marketValue - costValue; // 人民币盈亏
        pnlPercent = costValue > 0 ? (pnl / costValue * 100) : 0;
    } else {
        // A股：都是人民币，实时计算
        positionShares = stock.holdQuantity || stock.shares || 0;
        const priceA = stock.price ?? 0;
        const holdCostA = stock.holdCost ?? 0;
        marketValue = priceA * positionShares;
        costValue = holdCostA * positionShares;
        pnl = marketValue - costValue;
        pnlPercent = costValue > 0 ? (pnl / costValue * 100) : 0;
    }

    // 安全设置元素内容的辅助函数
    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    // 基础信息
    setText('detailName', stock.name);
    setText('detailCode', stock.code);
    setText('detailStrategy', (stock.strategy || '买入持有') + '策略');

    // 港股显示实时港币价格
    const price = stock.price ?? 0;
    if (isHKStock) {
        setText('detailPrice', `${price.toFixed(2)} HKD`);
    } else {
        setText('detailPrice', price.toFixed(2));
    }

    const detailPriceEl = document.getElementById('detailPrice');
    if (detailPriceEl) detailPriceEl.className = 'current-price ' + (isUp ? 'up' : 'down');

    const detailChangeEl = document.getElementById('detailChange');
    if (detailChangeEl) {
        const change = stock.change ?? 0;
        const changePercent = stock.changePercent ?? 0;
        detailChangeEl.textContent = `${isUp ? '+' : ''}${change.toFixed(2)} (${isUp ? '+' : ''}${changePercent.toFixed(2)}%)`;
        detailChangeEl.className = 'price-change ' + (isUp ? 'up' : 'down');
    }

    // 策略卡片
    setText('detailLimit', formatMoney(stock.investLimit ?? 0));
    
    // 当前持仓：显示持仓数量和人民币市值
    if (isHKStock) {
        // 港股显示：数量 + 人民币市值（港币市值 ÷ 汇率）
        const hkdValue = positionValueHkd || 0;
        const cnyValue = hkdValue / exchangeRate; // 转换为人民币（汇率是1人民币=X港币）
        const shares = positionShares || 0;
        setText('detailPosition', `${shares}股 / ${(cnyValue/10000).toFixed(2)}万`);
    } else {
        // A股显示：数量 + 人民币市值
        const shares = positionShares || 0;
        setText('detailPosition', `${shares}股 / ${formatMoney(marketValue)}`);
    }

    // 港股持仓成本是导入的人民币成本
    if (isHKStock) {
        setText('detailCost', `${(stock.holdCost || 0).toFixed(2)} (人民币)`);
    } else {
        setText('detailCost', (stock.holdCost || 0).toFixed(2));
    }

    const detailPnLEl = document.getElementById('detailPnL');
    if (detailPnLEl) {
        detailPnLEl.textContent = `${pnl >= 0 ? '+' : ''}${formatMoney(pnl)} (${pnlPercent.toFixed(2)}%)`;
        detailPnLEl.style.color = pnl >= 0 ? 'var(--up-color)' : 'var(--down-color)';
    }

    // 盈亏比例
    const detailPnLPercentEl = document.getElementById('detailPnLPercent');
    if (detailPnLPercentEl) {
        detailPnLPercentEl.textContent = pnlPercent.toFixed(2) + '%';
        detailPnLPercentEl.className = 'card-value ' + (pnl >= 0 ? 'up' : 'down');
    }

    // 计算持仓比例 = 该股票市值 / 个股投资上限
    const investLimit = stock.investLimit || 1;
    let positionRatio = 0;
    if (investLimit > 0) {
        positionRatio = (marketValue / investLimit) * 100;
    }
    
    // 持仓比例卡片（原中轴价格位置）
    const detailPivotEl = document.getElementById('detailPivot');
    if (detailPivotEl) {
        detailPivotEl.textContent = positionRatio.toFixed(2) + '%';
        console.log('[renderStockDetail] 持仓比例:', positionRatio.toFixed(2) + '%');
    }

    // 中轴价格可视化区域的中轴价格
    let pivotPriceValue = parseFloat(stock.pivotPrice) || 0;
    const pivotCenterEl = document.getElementById('pivotCenter');
    if (pivotCenterEl) {
        pivotCenterEl.textContent = pivotPriceValue.toFixed(2);
    }

    // 当前价格标签
    const currentPriceLabelEl = document.getElementById('currentPriceLabel');
    if (currentPriceLabelEl) {
        currentPriceLabelEl.textContent = stock.price.toFixed(2);
    }

    setText('detailBase', (stock.baseRatio || 50) + '%');
    setText('detailFloat', (stock.floatRatio || 50) + '%');

    // 触发价格（基于中轴价格计算）
    // 港股使用港币中轴价格计算触发价，然后显示触发价
    let triggerBuy = stock.triggerBuy || (pivotPriceValue * 0.92);
    let triggerSell = stock.triggerSell || (pivotPriceValue * 1.08);
    
    // 如果是港股且触发价看起来太小（可能是基于人民币计算的），需要调整
    if (isHKStock && stock.holdCost > 0) {
        const expectedTriggerSellHkd = pivotPriceValue * 1.08;
        // 如果现有的 triggerSell 比期望的港币触发价小很多，可能是人民币值
        if (triggerSell < expectedTriggerSellHkd * 0.5) {
            // 重新基于港币中轴价格计算
            triggerBuy = pivotPriceValue * 0.92;
            triggerSell = pivotPriceValue * 1.08;
        }
    }
    
    setText('triggerBuy', triggerBuy.toFixed(2));
    setText('triggerSell', triggerSell.toFixed(2));

    // 安全计算距离
    let distBuy = '0.0';
    let distSell = '0.0';
    if (stock.triggerBuy > 0) {
        distBuy = ((stock.price - stock.triggerBuy) / stock.triggerBuy * 100).toFixed(1);
    }
    if (stock.price > 0) {
        distSell = ((stock.triggerSell - stock.price) / stock.price * 100).toFixed(1);
    }
    setText('distanceBuy', `距触发 ${distBuy}%`);
    setText('distanceSell', `距触发 ${distSell}%`);

    // 进度条
    const markerCurrentEl = document.getElementById('markerCurrent');
    if (markerCurrentEl && stock.triggerSell !== stock.triggerBuy) {
        const progress = ((stock.price - stock.triggerBuy) / (stock.triggerSell - stock.triggerBuy) * 100);
        markerCurrentEl.style.left = Math.max(0, Math.min(100, progress)) + '%';
    }

    // 操作建议
    let suggestion = '';
    if (stock.price >= stock.triggerSell) {
        const sellAmount = stock.investLimit * (stock.floatRatio / 100) * 0.2;
        const sellShares = Math.floor(sellAmount / stock.price);
        suggestion = `⚡ 触发卖出信号！建议减持浮动仓20%，约卖出 ${sellShares} 股，金额约 ${(sellAmount/10000).toFixed(1)} 万元。`;
    } else if (stock.price <= stock.triggerBuy) {
        const buyAmount = stock.investLimit * (stock.floatRatio / 100) * 0.2;
        const buyShares = Math.floor(buyAmount / stock.price);
        suggestion = `⚡ 触发买入信号！建议增持浮动仓20%，约买入 ${buyShares} 股，金额约 ${(buyAmount/10000).toFixed(1)} 万元。`;
    } else {
        suggestion = `📊 当前股价处于中轴附近，建议持有观望。等待股价达到 ${stock.triggerBuy.toFixed(2)}（买入）或 ${stock.triggerSell.toFixed(2)}（卖出）时触发操作。`;
    }
    setText('suggestionContent', suggestion);

    // 渲染网格策略表格
    renderGridStrategy(stock);
    
    // 港股：显示沽空风险提示
    if (isHKStock) {
        console.log('[renderStockDetail] 检测到港股:', stock.code, stock.name);
        renderHKShortRiskWarning();
    } else {
        // 非港股隐藏沽空提示
        const warningEl = document.getElementById('hkShortRiskWarning');
        if (warningEl) {
            warningEl.style.display = 'none';
            console.log('[renderStockDetail] 非港股,隐藏沽空提示:', stock.code);
        }
    }
}

// 渲染网格策略表格
function renderGridStrategy(stock) {
    const tbody = document.getElementById('gridTableBody');
    const gridInfoEl = document.getElementById('gridStrategyInfo');
    if (!tbody) return;

    // 港股使用港币中轴价格，A股使用人民币中轴价格
    const isHKStock = stock.market === '港股';
    const exchangeRate = stock.exchangeRate || appState.exchangeRate || 0.92;
    
    let pivotPrice = parseFloat(stock.pivotPrice) || stock.holdCost || stock.price || 0;
    
    // 如果是港股，检查中轴价格是否需要货币转换
    if (isHKStock && pivotPrice > 0 && stock.holdCost > 0) {
        const holdCostHkd = stock.holdCost;
        const holdCostCny = holdCostHkd * exchangeRate;
        
        // 如果 pivotPrice 接近人民币成本价，但偏离港币成本价，说明可能是人民币值
        if (Math.abs(pivotPrice - holdCostCny) < 1 && Math.abs(pivotPrice - holdCostHkd) > 10) {
            pivotPrice = pivotPrice / exchangeRate;
        }
    }
    
    if (pivotPrice <= 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-muted)">暂无中轴价格数据</td></tr>';
        return;
    }

    // 生成5档网格（-4%到+4%，每档2%）
    const gridLevels = [-4, -3, -2, -1, 0, 1, 2, 3, 4];
    const gridData = gridLevels.map(level => {
        const triggerPrice = pivotPrice * (1 + level * 0.02);
        const isBuy = level < 0;
        const isSell = level > 0;
        const isCenter = level === 0;

        // 计算数量：每档交易浮动仓的20%
        const tradeAmount = stock.investLimit * (stock.floatRatio / 100) * 0.2;
        const shares = Math.floor(tradeAmount / triggerPrice);

        // 判断状态：当前价格是否触发
        let status = '未触发';
        let statusClass = '';
        if (isCenter) {
            status = '中轴';
            statusClass = 'center';
        } else if (isBuy && stock.price <= triggerPrice) {
            status = '已触发';
            statusClass = 'triggered-buy';
        } else if (isSell && stock.price >= triggerPrice) {
            status = '已触发';
            statusClass = 'triggered-sell';
        }

        return {
            level: level > 0 ? `+${level}` : level,
            price: triggerPrice,
            action: isBuy ? '买入' : isSell ? '卖出' : '持有',
            actionClass: isBuy ? 'buy' : isSell ? 'sell' : 'hold',
            shares: shares,
            status: status,
            statusClass: statusClass,
            isCenter: isCenter
        };
    });

    // 更新网格策略信息
    if (gridInfoEl) {
        gridInfoEl.textContent = `${gridData.length}档网格 · 中轴${pivotPrice.toFixed(2)} · 每档2%`;
    }

    // 渲染表格
    tbody.innerHTML = gridData.map(row => `
        <tr class="${row.isCenter ? 'grid-center-row' : ''}">
            <td><span class="grid-level">${row.level}</span></td>
            <td>${row.price.toFixed(2)}</td>
            <td><span class="grid-action ${row.actionClass}">${row.action}</span></td>
            <td>${row.shares > 0 ? row.shares + '股' : '--'}</td>
            <td><span class="grid-status ${row.statusClass}">${row.status}</span></td>
        </tr>
    `).join('');
}

// 渲染港股沽空风险提示
async function renderHKShortRiskWarning() {
    const warningEl = document.getElementById('hkShortRiskWarning');
    if (!warningEl) {
        console.error('[renderHKShortRiskWarning] 未找到警告元素');
        return;
    }
    
    const stock = appState.selectedStock;
    if (!stock || stock.market !== '港股') {
        console.warn('[renderHKShortRiskWarning] 当前不是港股，不显示');
        warningEl.style.display = 'none';
        return;
    }
    
    console.log('[renderHKShortRiskWarning] 开始渲染港股沽空提示，股票:', stock.code, stock.name);
    
    // 显示容器
    warningEl.style.display = 'block';
    
    // 设置加载状态
    document.getElementById('hkStockShortAmount').textContent = '加载中...';
    document.getElementById('hkIndividualShortAmount').textContent = '加载中...';
    
    try {
        // 并行获取市场数据和个股数据
        const [marketResponse, stockResponse] = await Promise.all([
            fetch('/api/market/sentiment'),
            fetch(`/api/hk-stock/${stock.code}/short-selling`)
        ]);
        
        const marketData = await marketResponse.json();
        const stockData = await stockResponse.json();
        
        // 1. 渲染市场整体数据
        if (marketData.success && marketData.north_south && marketData.north_south.hk_short_selling) {
            const hkShort = marketData.north_south.hk_short_selling;
            
            // 如果数据待披露
            if (hkShort.data_pending) {
                document.getElementById('hkStockShortAmount').textContent = '待披露';
                document.getElementById('hkStockShortRatio').textContent = 'T+1';
                document.getElementById('hkStockSignal').textContent = '港交所';
                document.getElementById('hkStockChange1W').textContent = '--';
                document.getElementById('hkStockChange1M').textContent = '--';
                document.getElementById('hkStockChange3M').textContent = '--';
                
                const adviceEl = document.getElementById('hkStockRiskAdvice');
                adviceEl.textContent = '⏰ 港交所沽空数据T+1披露，收盘后次日更新。可通过富途/雪球查看实时估算。';
                adviceEl.className = 'hk-risk-advice normal';
                document.getElementById('hkShortUpdateTime').textContent = hkShort.update_date || '--';
            } else if (hkShort.short_volume_wan !== null && hkShort.short_ratio !== null) {
                // 正常显示数据 - 显示沽空股数（万股）
                document.getElementById('hkStockShortAmount').textContent = `${hkShort.short_volume_wan}万股`;
                
                const ratioEl = document.getElementById('hkStockShortRatio');
                ratioEl.textContent = `${hkShort.short_ratio}%`;
                ratioEl.className = `hk-metric-value ${hkShort.short_ratio > 15 ? 'high-risk' : hkShort.short_ratio > 10 ? 'medium-risk' : 'low-risk'}`;
                
                const signalEl = document.getElementById('hkStockSignal');
                signalEl.textContent = hkShort.signal || '--';
                signalEl.className = `hk-metric-value ${hkShort.short_ratio > 15 ? 'high-risk' : hkShort.short_ratio > 10 ? 'medium-risk' : 'low-risk'}`;
                
                // 变化趋势
                const changes = hkShort.changes || {};
                const formatChange = (c) => {
                    if (!c || c.volume_change === undefined) return '--';
                    const sign = c.volume_change >= 0 ? '+' : '';
                    return `${sign}${c.volume_change}万股`;
                };
                
                const change1w = changes['1w'] || {};
                const change1m = changes['1m'] || {};
                const change3m = changes['3m'] || {};
                
                document.getElementById('hkStockChange1W').textContent = formatChange(change1w);
                document.getElementById('hkStockChange1W').className = `hk-trend-value ${(change1w.volume_change || 0) >= 0 ? 'high-risk' : 'low-risk'}`;
                
                document.getElementById('hkStockChange1M').textContent = formatChange(change1m);
                document.getElementById('hkStockChange1M').className = `hk-trend-value ${(change1m.volume_change || 0) >= 0 ? 'high-risk' : 'low-risk'}`;
                
                document.getElementById('hkStockChange3M').textContent = formatChange(change3m);
                document.getElementById('hkStockChange3M').className = `hk-trend-value ${(change3m.volume_change || 0) >= 0 ? 'high-risk' : 'low-risk'}`;
                
                // 市场整体风险提示
                const adviceEl = document.getElementById('hkStockRiskAdvice');
                if (hkShort.short_ratio > 20) {
                    adviceEl.textContent = '⚠️ 当前港股沽空比例极高，市场整体做空情绪浓厚，建议谨慎操作，考虑减仓避险。';
                    adviceEl.className = 'hk-risk-advice high-risk';
                } else if (hkShort.short_ratio > 15) {
                    adviceEl.textContent = '📉 港股沽空压力较大，市场偏空，建议控制仓位，避免追高。';
                    adviceEl.className = 'hk-risk-advice medium-risk';
                } else if (hkShort.short_ratio > 10) {
                    adviceEl.textContent = '➡️ 港股沽空比例处于正常水平，可按正常策略操作。';
                    adviceEl.className = 'hk-risk-advice normal';
                } else {
                    adviceEl.textContent = '📈 港股沽空压力较小，市场环境较好，可积极布局。';
                    adviceEl.className = 'hk-risk-advice low-risk';
                }
            
            document.getElementById('hkShortUpdateTime').textContent = hkShort.update_date || '--';
            }
        }
        
        // 2. 渲染个股沽空数据
        if (stockData.success) {
            const individual = stockData;
            
            document.getElementById('hkIndividualShortAmount').textContent = 
                individual.short_volume_wan !== null ? `${individual.short_volume_wan}万股` : '--';
            
            const ratioEl = document.getElementById('hkIndividualShortRatio');
            if (individual.short_ratio !== null) {
                ratioEl.textContent = `${individual.short_ratio}%`;
                ratioEl.className = `hk-metric-value ${individual.short_ratio > 25 ? 'high-risk' : individual.short_ratio > 15 ? 'medium-risk' : 'low-risk'}`;
            } else {
                ratioEl.textContent = '--';
            }
            
            const sourceEl = document.getElementById('hkIndividualDataSource');
            if (individual.data_pending) {
                sourceEl.textContent = '港交所T+1披露';
                sourceEl.className = 'hk-metric-value medium-risk';
                sourceEl.title = '港交所每日收盘后披露沽空数据，次日可用';
            } else if (individual.estimated) {
                sourceEl.textContent = '估算数据';
                sourceEl.className = 'hk-metric-value medium-risk';
            } else {
                sourceEl.textContent = '港交所';
                sourceEl.className = 'hk-metric-value low-risk';
            }
            
            // 渲染趋势数据（1周、1月）
            const changes = individual.changes || {};
            
            // 1周变化
            const change1wEl = document.getElementById('hkIndividualChange1W');
            if (changes['1w']) {
                const ratioChange = changes['1w'].ratio_change;
                const sign = ratioChange >= 0 ? '+' : '';
                change1wEl.textContent = `${sign}${ratioChange}%`;
                change1wEl.style.color = ratioChange > 0 ? '#ff4757' : '#2ed573';
            } else {
                change1wEl.textContent = '--';
            }
            
            // 1月变化
            const change1mEl = document.getElementById('hkIndividualChange1M');
            if (changes['1m']) {
                const ratioChange = changes['1m'].ratio_change;
                const sign = ratioChange >= 0 ? '+' : '';
                change1mEl.textContent = `${sign}${ratioChange}%`;
                change1mEl.style.color = ratioChange > 0 ? '#ff4757' : '#2ed573';
            } else {
                change1mEl.textContent = '--';
            }
            
            // 趋势方向
            const trendEl = document.getElementById('hkIndividualTrend');
            if (changes['1w'] && changes['1m']) {
                const w1Change = changes['1w'].ratio_change;
                const m1Change = changes['1m'].ratio_change;
                
                if (w1Change > 3 && m1Change > 5) {
                    trendEl.textContent = '↗️ 上升';
                    trendEl.style.color = '#ff4757';
                } else if (w1Change < -3 && m1Change < -5) {
                    trendEl.textContent = '↘️ 下降';
                    trendEl.style.color = '#2ed573';
                } else if (Math.abs(w1Change) < 2 && Math.abs(m1Change) < 3) {
                    trendEl.textContent = '→ 平稳';
                    trendEl.style.color = '#ffa502';
                } else {
                    trendEl.textContent = '↗↘ 波动';
                    trendEl.style.color = '#ffa502';
                }
            } else {
                trendEl.textContent = '--';
            }
            
            // 个股风险提示
            const individualAdviceEl = document.getElementById('hkIndividualAdvice');
            const stockName = stock.name || '';
            if (individual.short_ratio !== null) {
                // 构建趋势描述
                let trendDesc = '';
                if (changes['1w'] && changes['1m']) {
                    const w1Change = changes['1w'].ratio_change;
                    const m1Change = changes['1m'].ratio_change;
                    
                    if (w1Change > 3) {
                        trendDesc = `（1周+${w1Change}%）`;
                    } else if (w1Change < -3) {
                        trendDesc = `（1周${w1Change}%）`;
                    }
                }
                
                if (individual.short_ratio > 30) {
                    individualAdviceEl.innerHTML = `⚠️ <strong>${stockName}</strong> 昨日沽空比率达 <span style="color:#ff4757;font-weight:bold">${individual.short_ratio}%</span> ${trendDesc}，做空压力极大，建议密切关注并考虑减仓避险。`;
                    individualAdviceEl.className = 'hk-individual-advice high-risk';
                } else if (individual.short_ratio > 20) {
                    individualAdviceEl.innerHTML = `📉 <strong>${stockName}</strong> 昨日沽空比率为 <span style="color:#ffa502;font-weight:bold">${individual.short_ratio}%</span> ${trendDesc}，沽空压力较大，建议谨慎操作。`;
                    individualAdviceEl.className = 'hk-individual-advice medium-risk';
                } else if (individual.short_ratio > 10) {
                    individualAdviceEl.innerHTML = `➡️ <strong>${stockName}</strong> 昨日沽空比率为 <span style="color:#ffa502">${individual.short_ratio}%</span> ${trendDesc}，处于正常水平。`;
                    individualAdviceEl.className = 'hk-individual-advice normal';
                } else {
                    individualAdviceEl.innerHTML = `📈 <strong>${stockName}</strong> 昨日沽空比率仅 <span style="color:#2ed573">${individual.short_ratio}%</span> ${trendDesc}，做空压力较小。`;
                    individualAdviceEl.className = 'hk-individual-advice low-risk';
                }
            } else {
                individualAdviceEl.textContent = '暂无个股沽空数据';
            }
        } else {
            document.getElementById('hkIndividualShortAmount').textContent = '获取失败';
            document.getElementById('hkIndividualChange1W').textContent = '--';
            document.getElementById('hkIndividualChange1M').textContent = '--';
            document.getElementById('hkIndividualTrend').textContent = '--';
            document.getElementById('hkIndividualAdvice').textContent = '个股沽空数据获取失败';
        }
        
        console.log('[renderHKShortRiskWarning] 渲染完成');
        
    } catch (e) {
        console.error('[renderHKShortRiskWarning] 加载失败:', e);
        document.getElementById('hkStockShortAmount').textContent = '错误';
        document.getElementById('hkIndividualShortAmount').textContent = '错误';
        document.getElementById('hkStockRiskAdvice').textContent = '数据加载异常。';
        document.getElementById('hkIndividualAdvice').textContent = '数据加载异常。';
    }
}
function renderHotSectors() {
    const listEl = document.getElementById('hotSectors');
    if (!listEl) return;
    
    listEl.innerHTML = '';

    if (!appState.hotSectors || appState.hotSectors.length === 0) {
        listEl.innerHTML = '<div class="sector-empty">加载中...</div>';
        return;
    }

    appState.hotSectors.forEach((sector, index) => {
        const item = document.createElement('div');
        item.className = 'sector-item';
        
        const isUp = sector.change >= 0;
        const changeClass = isUp ? 'up' : 'down';
        const changeSign = isUp ? '+' : '';
        
        // 资金流向
        const moneyFlow = sector.money_flow || {};
        const mainInflow = moneyFlow.main_inflow || 0;
        const inflowClass = mainInflow >= 0 ? 'inflow' : 'outflow';
        const inflowSign = mainInflow >= 0 ? '+' : '';
        const inflowText = Math.abs(mainInflow) >= 10000 ? 
            `${inflowSign}${(mainInflow / 10000).toFixed(1)}亿` : 
            `${inflowSign}${mainInflow.toFixed(0)}万`;
        
        // 情绪得分
        const sentiment = sector.sentiment || {};
        const sentimentClass = sentiment.sentiment_class || 'neutral';
        const sentimentScore = Math.round(sentiment.score || 50);
        
        // 技术信号
        const technical = sector.technical || {};
        const signals = technical.signals || [];
        let signalsHtml = '';
        if (signals.length > 0) {
            signalsHtml = '<div class="sector-signals">';
            signals.slice(0, 2).forEach(sig => {
                const sigClass = sig.type === 'buy' ? 'buy' : sig.type === 'sell' ? 'sell' : 'strong';
                signalsHtml += `<span class="signal-tag ${sigClass}">${sig.text}</span>`;
            });
            signalsHtml += '</div>';
        }
        
        // 涨停家数
        const limitUp = sector.limit_up_count || 0;
        const limitUpHtml = limitUp > 0 ? `<span class="limit-up-tag">${limitUp}股涨停</span>` : '';
        
        // 上涨家数占比
        const upRatio = sector.up_ratio || 0;
        const totalStocks = sector.total_stocks || 0;
        
        // 排名
        const rank = sector.rank || (index + 1);
        
        // 新闻标签
        const newsTags = sector.news_tags || [];
        let tagsHtml = '';
        if (newsTags.length > 0) {
            tagsHtml = '<div class="sector-tags">';
            newsTags.slice(0, 2).forEach(tag => {
                tagsHtml += `<span class="news-tag">${tag}</span>`;
            });
            tagsHtml += '</div>';
        }
        
        // 领涨股 TOP 3
        const topStocks = sector.top_stocks || [];
        let stocksHtml = '';
        if (topStocks.length > 0) {
            stocksHtml = '<div class="sector-stocks">';
            topStocks.forEach((stock, i) => {
                const stockUp = stock.change_percent >= 0;
                const stockClass = stockUp ? 'up' : 'down';
                const stockSign = stockUp ? '+' : '';
                stocksHtml += `<span class="sector-stock ${stockClass}">${stock.name} ${stockSign}${stock.change_percent.toFixed(1)}%</span>`;
            });
            stocksHtml += '</div>';
        }
        
        item.innerHTML = `
            <div class="sector-header">
                <div class="sector-info">
                    <span class="sector-rank">${rank}</span>
                    <div class="sector-title">
                        <span class="sector-name">${sector.name}</span>
                        ${limitUpHtml}
                    </div>
                </div>
                <div class="sector-change-group">
                    <span class="sector-change ${changeClass}">${changeSign}${sector.change.toFixed(2)}%</span>
                    <span class="sentiment-badge ${sentimentClass}">${sentimentScore}</span>
                </div>
            </div>
            
            <div class="sector-stats">
                <span class="sector-flow ${inflowClass}">
                    <i class="fas fa-${mainInflow >= 0 ? 'arrow-up' : 'arrow-down'}"></i>
                    主力${inflowText}
                </span>
                <span class="up-ratio">
                    <i class="fas fa-chart-bar"></i>
                    ${upRatio.toFixed(0)}%个股上涨
                </span>
                <span class="stock-count">
                    ${sector.up_count || 0}/${totalStocks}家涨
                </span>
            </div>
            
            ${signalsHtml}
            ${tagsHtml}
            ${stocksHtml}
        `;
        
        listEl.appendChild(item);
    });
}

// 加载热点板块数据
async function loadHotSectors() {
    try {
        const response = await fetch('/api/market/hot-sectors');
        const data = await response.json();
        
        if (data.success && data.sectors) {
            appState.hotSectors = data.sectors;
            renderHotSectors();
            console.log('[热点板块] 已更新', data.sectors.length, '个板块');
        } else {
            console.warn('[热点板块] 获取失败:', data.error);
        }
    } catch (e) {
        console.error('[热点板块] 加载失败:', e);
    }
}

// 渲染新闻 - 结构化财联社新闻 (头条/题材/日历/持仓)
function renderNews() {
    const listEl = document.getElementById('newsList');
    if (!listEl) return;
    
    listEl.innerHTML = '';

    // 检查是否有结构化数据
    if (!appState.news || typeof appState.news !== 'object') {
        listEl.innerHTML = '<div class="news-empty">暂无新闻</div>';
        return;
    }

    const { headlines = [], themes = [], calendar = [], portfolio = [], general = [], hot_themes = [] } = appState.news;
    
    // 1. 渲染投资日历（今日重要事件）
    if (calendar.length > 0) {
        const calendarSection = document.createElement('div');
        calendarSection.className = 'news-section';
        calendarSection.innerHTML = '<div class="news-section-title">📅 投资日历</div>';
        
        calendar.forEach(item => {
            const el = document.createElement('div');
            el.className = 'news-calendar-item';
            el.innerHTML = `
                <div class="calendar-time">${item.time}</div>
                <div class="calendar-content">
                    <div class="calendar-title">${item.title}</div>
                    ${item.related_sectors ? `<div class="calendar-sectors">${item.related_sectors.map(s => `<span>${s}</span>`).join('')}</div>` : ''}
                </div>
                <span class="calendar-tag ${item.importance >= 2 ? 'important' : ''}">${item.importance_label}</span>
            `;
            calendarSection.appendChild(el);
        });
        listEl.appendChild(calendarSection);
    }

    // 2. 渲染热门题材
    if (hot_themes && hot_themes.length > 0) {
        const themeSection = document.createElement('div');
        themeSection.className = 'news-section';
        themeSection.innerHTML = '<div class="news-section-title">🔥 热门题材</div>';
        
        const themeGrid = document.createElement('div');
        themeGrid.className = 'hot-themes-grid';
        
        hot_themes.slice(0, 4).forEach(theme => {
            const isUp = theme.change >= 0;
            const el = document.createElement('div');
            el.className = `theme-card ${isUp ? 'up' : 'down'}`;
            el.innerHTML = `
                <div class="theme-name">${theme.name}</div>
                <div class="theme-heat">热度 ${theme.heat}</div>
                <div class="theme-change">${isUp ? '+' : ''}${theme.change}%</div>
            `;
            themeGrid.appendChild(el);
        });
        
        themeSection.appendChild(themeGrid);
        listEl.appendChild(themeSection);
    }

    // 3. 渲染头条
    if (headlines.length > 0) {
        const headlineSection = document.createElement('div');
        headlineSection.className = 'news-section';
        headlineSection.innerHTML = '<div class="news-section-title">📰 头条</div>';
        
        headlines.forEach(news => {
            const el = createNewsElement(news, 'headline');
            headlineSection.appendChild(el);
        });
        listEl.appendChild(headlineSection);
    }

    // 4. 渲染持仓相关
    if (portfolio.length > 0) {
        const portfolioSection = document.createElement('div');
        portfolioSection.className = 'news-section';
        portfolioSection.innerHTML = '<div class="news-section-title">💼 持仓相关</div>';
        
        portfolio.forEach(news => {
            const el = createNewsElement(news, 'portfolio');
            portfolioSection.appendChild(el);
        });
        listEl.appendChild(portfolioSection);
    }

    // 5. 渲染题材推荐
    if (themes.length > 0) {
        const themeNewsSection = document.createElement('div');
        themeNewsSection.className = 'news-section';
        themeNewsSection.innerHTML = '<div class="news-section-title">💡 题材推荐</div>';
        
        themes.forEach(news => {
            const el = createNewsElement(news, 'theme');
            themeNewsSection.appendChild(el);
        });
        listEl.appendChild(themeNewsSection);
    }

    // 6. 渲染普通快讯（如果没有其他内容）
    if (listEl.children.length === 0 && general.length > 0) {
        general.forEach(news => {
            const el = createNewsElement(news, 'normal');
            listEl.appendChild(el);
        });
    }
}

// 创建新闻元素
function createNewsElement(news, type) {
    const item = document.createElement('div');
    item.className = `news-item ${type}`;
    
    const importanceClass = news.importance >= 2 ? 'important' : news.importance === 1 ? 'attention' : 'normal';
    
    // 关联板块标签
    let sectorsHtml = '';
    if (news.related_sectors && news.related_sectors.length > 0) {
        sectorsHtml = `<div class="news-sectors">${news.related_sectors.map(s => `<span class="sector-tag">${s}</span>`).join('')}</div>`;
    }
    
    item.innerHTML = `
        <div class="news-header">
            <span class="news-time">${news.time || ''}</span>
            <span class="news-tag ${importanceClass}">${news.importance_label || '一般'}</span>
        </div>
        <div class="news-title" title="${news.content || news.title}">${news.title}</div>
        ${sectorsHtml}
    `;
    
    return item;
}

// 加载结构化财联社新闻
async function loadNews() {
    try {
        console.log('加载结构化财联社新闻...');
        const response = await fetch('/api/news');
        const data = await response.json();
        
        if (data.success) {
            appState.news = data;
            renderNews();
            console.log(`新闻加载完成: 头条${data.headlines?.length || 0}条, 题材${data.themes?.length || 0}条, 日历${data.calendar?.length || 0}条`);
        } else {
            console.warn('新闻加载失败:', data.error);
            // 使用模拟数据
            appState.news = { headlines: [], themes: [], calendar: [], portfolio: [], general: mockNews };
            renderNews();
        }
    } catch (error) {
        console.error('加载新闻出错:', error);
        appState.news = { headlines: [], themes: [], calendar: [], portfolio: [], general: mockNews };
        renderNews();
    }
}

// 显示添加股票弹窗
function showAddStockModal() {
    document.getElementById('addStockModal').classList.add('active');
}

// 隐藏添加股票弹窗
function hideAddStockModal() {
    document.getElementById('addStockModal').classList.remove('active');
}

// 显示数据分析弹窗
function showAnalysisModal() {
    document.getElementById('analysisModal').classList.add('active');
}

// 隐藏数据分析弹窗
function hideAnalysisModal() {
    document.getElementById('analysisModal').classList.remove('active');
}

// 处理添加股票
function handleAddStock(e) {
    e.preventDefault();

    const stock = {
        code: document.getElementById('stockCode').value,
        name: document.getElementById('stockName').value,
        market: document.getElementById('marketType').value,
        investLimit: parseFloat(document.getElementById('investLimit').value) * 10000,
        holdQuantity: parseInt(document.getElementById('holdQuantity').value) || 0,
        holdCost: parseFloat(document.getElementById('holdCost').value) || 0,
        strategy: document.getElementById('strategyMode').value,
        price: 0,
        change: 0,
        changePercent: 0,
        pivotPrice: 0,
        baseRatio: 50,
        floatRatio: 50,
        triggerBuy: 0,
        triggerSell: 0
    };

    // 计算中轴价格和触发价（简化版，实际应由AI计算）
    stock.pivotPrice = stock.holdCost || 100;
    stock.triggerBuy = stock.pivotPrice * 0.92;
    stock.triggerSell = stock.pivotPrice * 1.08;

    appState.stocks.push(stock);
    renderStockList();
    hideAddStockModal();

    // 重置表单
    e.target.reset();
}

// 模拟价格更新
async function simulatePriceUpdate() {
    // 只在开市时更新价格
    if (appState.marketStatus !== 'open') {
        return;
    }

    if (appState.stocks.length === 0) {
        return;
    }

    try {
        // 调用后端API获取真实行情
        const response = await fetch('/api/quotes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                stocks: appState.stocks.map(s => ({
                    code: s.code,
                    market: s.market
                }))
            })
        });

        const data = await response.json();

        if (data.success && data.quotes) {
            // 保存全局汇率
            if (data.exchange_rate) {
                appState.exchangeRate = data.exchange_rate;
            }

            // 更新股票价格和涨跌幅
            appState.stocks.forEach(stock => {
                const quote = data.quotes[stock.code];
                if (quote) {
                    stock.price = quote.price;
                    stock.change = quote.change;
                    stock.changePercent = quote.change_percent;

                    // 港股：保存人民币转换价格和汇率
                    if (quote.market === '港股') {
                        stock.priceCny = quote.price_cny;
                        stock.exchangeRate = quote.exchange_rate;
                    }

                    // 检查是否触发买卖提醒
                    if (stock.price >= stock.triggerSell || stock.price <= stock.triggerBuy) {
                        showTradeAlert(stock);
                    }
                }
            });

            renderStockList();
            if (appState.selectedStock) {
                const selected = appState.stocks.find(s => s.code === appState.selectedStock.code);
                if (selected) {
                    appState.selectedStock = selected;
                    renderStockDetail();
                }
            }
            updateAssetOverview();
        }
    } catch (error) {
        console.error('获取行情失败:', error);
    }
}

/**
 * 初始化时获取一次实时行情（获取当天收盘价）
 * 与 simulatePriceUpdate 不同，这个函数不检查市场状态，强制更新一次
 */
async function updateStockPricesOnce() {
    if (appState.stocks.length === 0) {
        console.log('[updateStockPricesOnce] 没有股票数据，跳过');
        return;
    }

    try {
        console.log('[updateStockPricesOnce] 获取实时行情...');
        console.log('[updateStockPricesOnce] 股票列表:', appState.stocks.map(s => s.code));
        
        const requestBody = {
            stocks: appState.stocks.map(s => ({
                code: s.code,
                market: s.market
            }))
        };
        console.log('[updateStockPricesOnce] 请求体:', JSON.stringify(requestBody));
        
        // 调用后端API获取真实行情，添加超时
        const controller = new AbortController();
        const timeoutId = setTimeout(() => {
            console.log('[updateStockPricesOnce] 请求超时(5秒)，中止');
            controller.abort();
        }, 5000); // 5秒超时
        
        console.log('[updateStockPricesOnce] 发起 fetch 请求...');
        let response;
        try {
            response = await fetch('/api/quotes', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody),
                signal: controller.signal
            });
        } catch (fetchError) {
            console.error('[updateStockPricesOnce] fetch 异常:', fetchError.name, fetchError.message);
            clearTimeout(timeoutId);
            throw fetchError;
        }
        clearTimeout(timeoutId);
        
        console.log('[updateStockPricesOnce] fetch 完成，状态:', response.status);

        if (!response.ok) {
            console.error('[updateStockPricesOnce] HTTP 错误:', response.status, response.statusText);
            return;
        }

        const data = await response.json();
        console.log('[updateStockPricesOnce] 响应数据:', data);

        if (data.success && data.quotes) {
            // 保存全局汇率
            if (data.exchange_rate) {
                appState.exchangeRate = data.exchange_rate;
            }

            // 更新股票价格和涨跌幅
            appState.stocks.forEach(stock => {
                const quote = data.quotes[stock.code];
                if (quote) {
                    console.log(`[updateStockPricesOnce] ${stock.code}: ${stock.price} -> ${quote.price}`);
                    stock.price = quote.price;
                    stock.change = quote.change;
                    stock.changePercent = quote.change_percent;

                    // 港股：保存人民币转换价格和汇率
                    if (quote.market === '港股') {
                        stock.priceCny = quote.price_cny;
                        stock.exchangeRate = quote.exchange_rate;
                    }
                } else {
                    console.log(`[updateStockPricesOnce] ${stock.code}: 无报价数据`);
                }
            });

            // 重新渲染
            renderStockList();
            if (appState.selectedStock) {
                const selected = appState.stocks.find(s => s.code === appState.selectedStock.code);
                if (selected) {
                    appState.selectedStock = selected;
                    renderStockDetail();
                }
            }
            updateAssetOverview();
            
            console.log('[updateStockPricesOnce] 实时行情更新完成');
        } else {
            console.error('[updateStockPricesOnce] API返回失败:', data);
        }
    } catch (error) {
        console.error('[updateStockPricesOnce] 获取行情失败:', error.name, error.message);
        if (error.name === 'AbortError') {
            console.error('[updateStockPricesOnce] 请求超时(5秒)');
        }
    }
}

// 显示买卖提醒 - 每天只提醒一次
const ALERT_DATE_KEY = 'trade_alert_date';
const ALERTED_STOCKS_KEY = 'trade_alerted_stocks';

function showTradeAlert(stock) {
    // 检查今天是否已经提醒过这只股票
    const today = new Date().toDateString();
    const lastAlertDate = localStorage.getItem(ALERT_DATE_KEY);
    let alertedStocks = [];

    try {
        alertedStocks = JSON.parse(localStorage.getItem(ALERTED_STOCKS_KEY) || '[]');
    } catch (e) {
        alertedStocks = [];
    }

    // 如果是新的一天，清空已提醒列表
    if (lastAlertDate !== today) {
        localStorage.setItem(ALERT_DATE_KEY, today);
        alertedStocks = [];
        localStorage.setItem(ALERTED_STOCKS_KEY, JSON.stringify(alertedStocks));
    }

    // 如果今天已经提醒过这只股票，不再提醒
    if (alertedStocks.includes(stock.code)) {
        return;
    }

    // 记录已提醒
    alertedStocks.push(stock.code);
    localStorage.setItem(ALERTED_STOCKS_KEY, JSON.stringify(alertedStocks));

    const isSell = stock.price >= stock.triggerSell;
    const modal = document.getElementById('tradeAlertModal');
    const content = document.getElementById('tradeAlertContent');

    const amount = stock.investLimit * (stock.floatRatio / 100) * 0.2;
    const shares = Math.floor(amount / stock.price);

    content.innerHTML = `
        <div class="alert-stock">${stock.name} (${stock.code})</div>
        <div class="alert-price ${isSell ? 'up' : 'down'}">${stock.price.toFixed(2)}</div>
        <div class="alert-change ${isSell ? 'up' : 'down'}">
            ${isSell ? '上涨' : '下跌'}触发 ${isSell ? '+' : '-'}8%
        </div>
        <div class="alert-action">
            <div class="alert-action-title">建议操作</div>
            <div class="alert-action-detail">
                ${isSell ? '减持' : '增持'}浮动仓20%<br>
                约${isSell ? '卖出' : '买入'} ${shares} 股<br>
                金额约 ${(amount/10000).toFixed(1)} 万元
            </div>
        </div>
    `;

    modal.classList.add('active');
}

// 确认交易
function confirmTrade() {
    document.getElementById('tradeAlertModal').classList.remove('active');
    addAlertLog('已确认交易操作');
}

// 稍后提醒
function snoozeAlert() {
    document.getElementById('tradeAlertModal').classList.remove('active');
    addAlertLog('已设置稍后提醒');
}

// 忽略提醒
function ignoreAlert() {
    document.getElementById('tradeAlertModal').classList.remove('active');
    addAlertLog('已忽略本次提醒');
}

// 添加提醒日志
function addAlertLog(message) {
    const logEl = document.getElementById('alertLog');
    if (!logEl) {
        console.warn('alertLog 元素不存在，跳过日志记录:', message);
        return;
    }
    const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    logEl.innerHTML = `[${time}] ${message}`;
}

// 加载市场情绪数据
async function loadSentiment() {
    try {
        console.log('加载市场情绪数据...');
        const response = await fetch('/api/market/sentiment');
        const data = await response.json();
        
        if (data.success) {
            appState.sentiment = data;
            renderSentiment();
            console.log('市场情绪加载完成:', data.sentiment_index?.label);
        } else {
            console.warn('市场情绪加载失败:', data.error);
        }
    } catch (error) {
        console.error('加载市场情绪出错:', error);
    }
}

// 渲染市场情绪面板
function renderSentiment() {
    if (!appState.sentiment) return;
    
    const data = appState.sentiment;
    const index = data.sentiment_index;
    const margin = data.margin;
    const northSouth = data.north_south;
    const capitalFlow = data.capital_flow;
    const breadth = data.breadth;
    
    // 更新更新时间
    const updateTimeEl = document.getElementById('sentimentUpdateTime');
    if (updateTimeEl) {
        updateTimeEl.textContent = `更新: ${data.update_time?.split(' ')[1] || '--'}`;
    }
    
    // 1. 渲染情绪指数仪表盘
    const scoreEl = document.getElementById('sentimentScore');
    const labelEl = document.getElementById('sentimentLabel');
    const gaugeFillEl = document.getElementById('sentimentGaugeFill');
    const gaugeNeedleEl = document.getElementById('gaugeNeedle');
    
    if (scoreEl) scoreEl.textContent = index.score;
    if (labelEl) {
        labelEl.textContent = index.label;
        labelEl.className = `gauge-label ${index.class}`;
    }
    
    // 仪表盘弧形填充 (0-100映射到0-180度)
    if (gaugeFillEl) {
        const percentage = index.score / 100;
        const endAngle = percentage * 180;
        const rad = (endAngle * Math.PI) / 180;
        const x = 100 - 80 * Math.cos(rad);
        const y = 100 - 80 * Math.sin(rad);
        const largeArc = endAngle > 90 ? 1 : 0;
        gaugeFillEl.setAttribute('d', `M 20 100 A 80 80 0 ${largeArc} 1 ${x} ${y}`);
        gaugeFillEl.setAttribute('class', `gauge-fill ${index.class}`);
    }
    
    // 仪表盘指针旋转 (0-100映射到0-180度，从左侧开始)
    if (gaugeNeedleEl) {
        const percentage = index.score / 100;
        const angle = percentage * 180; // 0-180度
        const rad = (angle * Math.PI) / 180;
        // 计算指针终点位置 (半径70，留一些边距)
        const needleLength = 70;
        const x2 = 100 - needleLength * Math.cos(rad);
        const y2 = 100 - needleLength * Math.sin(rad);
        gaugeNeedleEl.setAttribute('x2', x2);
        gaugeNeedleEl.setAttribute('y2', y2);
        // 根据情绪等级设置指针颜色
        const needleColors = {
            'extreme-fear': '#ff4757',
            'fear': '#ff6b6b',
            'neutral': '#ffa502',
            'greed': '#2ed573',
            'extreme-greed': '#00d4aa'
        };
        gaugeNeedleEl.setAttribute('stroke', needleColors[index.class] || '#fff');
    }
    
    // 2. 渲染多空力量条
    updateForceBar('north', northSouth.north_inflow, 100);
    updateForceBar('margin', margin.margin_change, 200);
    updateForceBar('mainForce', capitalFlow.main_inflow, 150);
    
    // 3. 渲染北向资金卡片
    updateCard('north', northSouth.north_inflow, northSouth.north_sentiment);
    document.getElementById('northInflow').textContent = `${northSouth.north_inflow >= 0 ? '+' : ''}${northSouth.north_inflow}亿`;
    document.getElementById('northInflow').className = `metric-value ${northSouth.north_inflow >= 0 ? 'up' : 'down'}`;
    document.getElementById('northCumulative').textContent = `${northSouth.north_cumulative}亿`;
    
    // 4. 渲染南向资金卡片
    updateCard('south', northSouth.south_inflow, northSouth.south_sentiment);
    document.getElementById('southInflow').textContent = `${northSouth.south_inflow >= 0 ? '+' : ''}${northSouth.south_inflow}亿`;
    document.getElementById('southInflow').className = `metric-value ${northSouth.south_inflow >= 0 ? 'up' : 'down'}`;
    document.getElementById('southSentiment').textContent = northSouth.south_sentiment;
    document.getElementById('southSentiment').className = `metric-value ${northSouth.south_inflow >= 0 ? 'up' : 'down'}`;
    
    // 渲染港股沽空数据
    const hkShort = northSouth.hk_short_selling || {};
    if (hkShort.success) {
        document.getElementById('hkShortAmount').textContent = `${hkShort.short_volume_wan}万股`;
        document.getElementById('hkShortRatio').textContent = `${hkShort.short_ratio}%`;
        document.getElementById('hkShortRatio').className = `metric-value ${hkShort.short_ratio > 15 ? 'down' : 'up'}`;
        
        // 变化趋势
        const changes = hkShort.changes || {};
        const change1w = changes['1w'] || {};
        const change1m = changes['1m'] || {};
        const change3m = changes['3m'] || {};
        
        const formatChange = (c) => {
            if (!c || c.volume_change === undefined) return '--';
            const sign = c.volume_change >= 0 ? '+' : '';
            return `${sign}${c.volume_change}万股`;
        };
        
        document.getElementById('hkShortChange1W').textContent = formatChange(change1w);
        document.getElementById('hkShortChange1W').className = `metric-value ${(change1w.volume_change || 0) >= 0 ? 'down' : 'up'}`;
        
        document.getElementById('hkShortChange1M').textContent = formatChange(change1m);
        document.getElementById('hkShortChange1M').className = `metric-value ${(change1m.volume_change || 0) >= 0 ? 'down' : 'up'}`;
        
        document.getElementById('hkShortChange3M').textContent = formatChange(change3m);
        document.getElementById('hkShortChange3M').className = `metric-value ${(change3m.volume_change || 0) >= 0 ? 'down' : 'up'}`;
    }
    
    // 5. 渲染融资融券卡片
    updateCard('margin', margin.margin_change, margin.sentiment);
    document.getElementById('marginBalance').textContent = `${margin.total_margin_balance}亿`;
    document.getElementById('marginChange').textContent = `${margin.margin_change >= 0 ? '+' : ''}${margin.margin_change}亿 (${margin.margin_change_pct}%)`;
    document.getElementById('marginChange').className = `metric-value ${margin.margin_change >= 0 ? 'up' : 'down'}`;
    
    // 6. 渲染主力资金卡片
    updateCard('mainForce', capitalFlow.main_inflow, capitalFlow.main_inflow >= 0 ? '看多' : '看空');
    document.getElementById('superLargeFlow').textContent = `${capitalFlow.super_large >= 0 ? '+' : ''}${capitalFlow.super_large}亿`;
    document.getElementById('superLargeFlow').className = `metric-value ${capitalFlow.super_large >= 0 ? 'up' : 'down'}`;
    document.getElementById('largeFlow').textContent = `${capitalFlow.large >= 0 ? '+' : ''}${capitalFlow.large}亿`;
    document.getElementById('largeFlow').className = `metric-value ${capitalFlow.large >= 0 ? 'up' : 'down'}`;
    document.getElementById('mediumFlow').textContent = `${capitalFlow.medium >= 0 ? '+' : ''}${capitalFlow.medium}亿`;
    document.getElementById('mediumFlow').className = `metric-value ${capitalFlow.medium >= 0 ? 'up' : 'down'}`;
    document.getElementById('smallFlow').textContent = `${capitalFlow.small >= 0 ? '+' : ''}${capitalFlow.small}亿`;
    document.getElementById('smallFlow').className = `metric-value ${capitalFlow.small >= 0 ? 'up' : 'down'}`;
    
    // 7. 渲染市场宽度
    document.getElementById('upCount').textContent = breadth.up_count;
    document.getElementById('downCount').textContent = breadth.down_count;
    document.getElementById('ztCount').textContent = breadth.zt_count;
    document.getElementById('dtCount').textContent = breadth.dt_count;
    document.getElementById('newHigh').textContent = breadth.new_high;
    document.getElementById('newLow').textContent = breadth.new_low;
    
    // 8. 加载持仓港股沽空风险分析
    loadHKPortfolioRisk();
}

// 加载持仓港股沽空风险分析
async function loadHKPortfolioRisk() {
    try {
        const response = await fetch('/api/portfolio/hk-short-analysis');
        if (!response.ok) return;
        
        const data = await response.json();
        if (!data.success) return;
        
        const portfolio = data.portfolio;
        const marketShort = data.market_short;
        
        // 只有在有港股持仓时才显示
        if (portfolio.hk_stock_count === 0) {
            document.getElementById('hkPortfolioRiskCard').style.display = 'none';
            return;
        }
        
        document.getElementById('hkPortfolioRiskCard').style.display = 'block';
        
        // 更新风险等级样式
        const riskCard = document.getElementById('hkPortfolioRiskCard');
        riskCard.className = `sentiment-card wide ${portfolio.risk_level === 'high' ? 'bear' : portfolio.risk_level === 'medium' ? 'neutral' : 'bull'}`;
        
        // 更新数据
        document.getElementById('hkRiskTrend').textContent = marketShort.signal || '--';
        document.getElementById('hkPositionCount').textContent = `${portfolio.hk_stock_count}只`;
        document.getElementById('hkPositionValue').textContent = `¥${formatMoney(portfolio.hk_position_value)}`;
        document.getElementById('hkMarketShortRatio').textContent = `${marketShort.short_ratio}%`;
        document.getElementById('hkMarketShortRatio').className = `metric-value ${marketShort.short_ratio > 15 ? 'down' : 'up'}`;
        
        // 变化趋势
        const changes = marketShort.changes || {};
        const formatChange = (c) => {
            if (!c || c.amount_change === undefined) return '--';
            const sign = c.amount_change >= 0 ? '+' : '';
            return `${sign}${c.amount_change}亿`;
        };
        
        const change1w = changes['1w'] || {};
        const change1m = changes['1m'] || {};
        const change3m = changes['3m'] || {};
        
        document.getElementById('hkShort1W').textContent = formatChange(change1w);
        document.getElementById('hkShort1W').className = `metric-value ${(change1w.amount_change || 0) >= 0 ? 'down' : 'up'}`;
        
        document.getElementById('hkShort1M').textContent = formatChange(change1m);
        document.getElementById('hkShort1M').className = `metric-value ${(change1m.amount_change || 0) >= 0 ? 'down' : 'up'}`;
        
        document.getElementById('hkShort3M').textContent = formatChange(change3m);
        document.getElementById('hkShort3M').className = `metric-value ${(change3m.amount_change || 0) >= 0 ? 'down' : 'up'}`;
        
        document.getElementById('hkRiskAdvice').textContent = portfolio.advice || '--';
        
    } catch (e) {
        console.error('加载港股沽空风险分析失败:', e);
    }
}

// 更新多空力量条
function updateForceBar(type, value, maxValue) {
    const barEl = document.getElementById(`${type}Bar`);
    const valueEl = document.getElementById(`${type}Value`);
    
    if (!barEl || !valueEl) return;
    
    // 计算百分比 (0-100)
    const normalizedValue = Math.max(-maxValue, Math.min(maxValue, value));
    const percentage = 50 + (normalizedValue / maxValue) * 50;
    
    barEl.style.width = `${Math.abs(percentage)}%`;
    barEl.className = `bar-fill ${value >= 0 ? 'bull' : 'bear'}`;
    valueEl.textContent = `${value >= 0 ? '+' : ''}${value}亿`;
    valueEl.className = `bar-value ${value >= 0 ? 'up' : 'down'}`;
}

// 更新卡片状态
function updateCard(type, value, sentiment) {
    const cardEl = document.getElementById(`${type}Card`);
    const trendEl = document.getElementById(`${type}Trend`);
    
    if (!cardEl || !trendEl) return;
    
    const isBull = value >= 0;
    cardEl.className = `sentiment-card ${isBull ? 'bull' : 'bear'}`;
    trendEl.textContent = sentiment;
    trendEl.className = `trend-badge ${isBull ? 'up' : 'down'}`;
}

// 格式化金额
function formatMoney(amount) {
    const val = Number(amount) || 0;
    if (val >= 100000000) {
        return (val / 100000000).toFixed(2) + '亿';
    } else if (val >= 10000) {
        return (val / 10000).toFixed(1) + '万';
    } else {
        return val.toFixed(2);
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    // 检查是否需要强制刷新（URL参数带 ?refresh=1）
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('refresh') === '1') {
        console.log('强制刷新模式：清除localStorage并重新加载');
        localStorage.removeItem('import_data_last');
        // 清除URL参数
        window.history.replaceState({}, document.title, window.location.pathname);
    }
    
    init();
    // 数据导入功能在import.js中初始化 - v2
    console.log('Checking initDataImport...', typeof initDataImport);
    if (typeof initDataImport === 'function') {
        console.log('Calling initDataImport...');
        initDataImport();
    } else {
        console.warn('initDataImport not found, will retry in 100ms');
        setTimeout(() => {
            if (typeof initDataImport === 'function') {
                console.log('Calling initDataImport (retry)...');
                initDataImport();
            }
        }, 100);
    }
});

// 确保函数在全局作用域可用（用于HTML内联事件）
window.showAddStockModal = showAddStockModal;
window.hideAddStockModal = hideAddStockModal;
window.showAnalysisModal = showAnalysisModal;
window.hideAnalysisModal = hideAnalysisModal;
window.renderStockList = renderStockList;
window.updateAssetOverview = updateAssetOverview;
window.selectStock = selectStock;
window.refreshAxisPrices = refreshAxisPrices;
window.loadHotSectors = loadHotSectors;

/**
 * 强制重置 - 清除所有缓存并重新加载页面
 */
function forceReset() {
    if (confirm('确定要清除所有缓存数据并重新加载页面吗？\n这将清除本地保存的持仓数据。')) {
        console.log('强制重置：清除所有localStorage数据');
        localStorage.clear();
        alert('缓存已清除，请重新导入持仓数据');
        setTimeout(() => {
            window.location.reload(true);
        }, 500);
    }
}
window.forceReset = forceReset;

/**
 * 手动修复单只股票中轴价格（调试用）
 */
async function fixStockAxis(code) {
    const stock = appState.stocks.find(s => s.code === code);
    if (!stock) {
        console.error(`找不到股票 ${code}`);
        return;
    }
    
    console.log(`[fixStockAxis] 手动修复 ${code} 中轴价格...`);
    console.log(`[fixStockAxis] 当前值: ${stock.pivotPrice}`);
    
    try {
        const response = await fetch('/api/axis-price', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                code: stock.code, 
                market: stock.market || 'A股', 
                days: 90 
            })
        });
        
        const axisData = await response.json();
        console.log(`[fixStockAxis] API返回:`, axisData);
        
        if (axisData.success && axisData.data && axisData.data.axis_price) {
            const oldPivot = stock.pivotPrice;
            stock.pivotPrice = axisData.data.axis_price;
            stock.triggerBuy = axisData.data.trigger_buy;
            stock.triggerSell = axisData.data.trigger_sell;
            
            console.log(`[fixStockAxis] 修复成功: ${oldPivot} -> ${stock.pivotPrice}`);
            
            // 保存并刷新
            localStorage.setItem('import_data_last', JSON.stringify(appState.stocks));
            renderStockDetail();
            
            alert(`${stock.name}(${code}) 中轴价格已更新:\n${oldPivot} -> ${stock.pivotPrice}`);
        } else {
            console.error(`[fixStockAxis] API返回失败:`, axisData);
            alert(`获取中轴价格失败: ${axisData.error || '未知错误'}`);
        }
    } catch (error) {
        console.error(`[fixStockAxis] 异常:`, error);
        alert(`修复失败: ${error.message}`);
    }
}
window.fixStockAxis = fixStockAxis;
