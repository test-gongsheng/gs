/**
 * 股票投资监控系统 v2.1 - 前端逻辑
 * 版本: 2026-03-27 - 新闻模块已集成
 */

// 版本号，用于强制刷新缓存
const APP_VERSION = "2.8.1";

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
    // 降级备用数据
];

const mockNews = [
    // 降级备用数据，仅在API完全失败时显示
];

// 初始化
// 初始化标记，防止重复初始化
let isInitialized = false;

async function init() {
    if (isInitialized) {
        console.log('[init] 已经初始化过，跳过');
        return;
    }
    isInitialized = true;

    // 清空现有数据，避免重复
    appState.stocks = [];
    let loadedFromBackend = false;
    console.log('[init] 开始初始化，已清空股票列表');
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
                exchangeRate: s.exchange_rate  // 从后端获取汇率
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
    appState.news = { headlines: [], themes: [], calendar: [], portfolio: [], general: mockNews };

    // 直接内联渲染股票列表
    const listEl = document.getElementById('stockList');
    if (listEl) {
        listEl.innerHTML = '';
        if (appState.stocks && appState.stocks.length > 0) {
            appState.stocks.forEach((stock, index) => {
                const item = document.createElement('div');
                item.className = 'stock-item' + (index === 0 ? ' active' : '');
                item.onclick = () => selectStock(index);
                const isUp = stock.change >= 0;
                const isHKStock = stock.market === '港股';
                const exchangeRate = stock.exchangeRate || 1.0836;
                const quantity = stock.holdQuantity || stock.shares || 0;
                let marketValue = isHKStock ? ((stock.priceCny || (stock.price / exchangeRate)) * quantity) : ((stock.price || 0) * quantity);
                const marketValueWan = marketValue > 0 ? (marketValue / 10000).toFixed(1) : '0.0';
                const hkBadge = isHKStock ? '<span class="stock-item-hk">HK</span>' : '';
                item.innerHTML = `<div class="stock-info"><span class="code">${stock.code}${hkBadge}</span><span class="name">${stock.name}</span></div><div class="stock-price ${isUp ? 'up' : 'down'}">${(stock.price || 0).toFixed(2)}</div><div class="stock-change ${isUp ? 'up' : 'down'}">${stock.change >= 0 ? '+' : ''}${(stock.changePercent || 0).toFixed(2)}%</div><div class="stock-pnl">${marketValueWan}万</div>`;
                listEl.appendChild(item);
            });
        } else {
            listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: var(--text-muted);">暂无持仓数据</div>';
        }
    }
    renderHotSectors();
    renderNews();
    updateTime();
    updateMarketStatus();
    // updateAssetOverview(); // 移到获取行情后调用

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
    
    // 定时刷新持仓股分析（每5分钟）
    setInterval(loadPortfolioAnalysis, 300000);

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
    
    // 页面加载完成后，加载持仓股分析报告
    console.log('加载持仓股分析报告...');
    await loadPortfolioAnalysis();
    
    // 页面加载完成后，先刷新中轴价格（后台计算，不渲染）
    if (appState.stocks.length > 0) {
        console.log('开始异步刷新中轴价格...');
        await refreshAxisPrices(false, false);  // forceRefresh=false, shouldRender=false
    }
    
    // 最后获取实时行情并渲染（确保显示最新价格）
    if (appState.stocks.length > 0) {
        console.log('初始化完成，立即获取实时行情...');
        await updateStockPricesOnce();
    }
    
    // 恢复用户折叠偏好
    restoreCollapsedState();
}

/**
 * 刷新所有股票的中轴价格
 * @param {boolean} forceRefresh - 是否强制刷新（清除缓存）
 * @param {boolean} shouldRender - 是否重新渲染（默认true，初始化时为false）
 */
async function refreshAxisPrices(forceRefresh = false, shouldRender = true) {
    console.log('[refreshAxisPrices] 开始执行，股票数量:', appState.stocks.length, '强制刷新:', forceRefresh, '是否渲染:', shouldRender);
    
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
            
            // 使用 AbortController 设置超时
            const controller = new AbortController();
            const timeoutMs = stock.market === '港股' ? 30000 : 20000;
            const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
            
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
                
                // 保存当前的涨跌幅数据（避免被覆盖）
                const currentChange = stock.change;
                const currentChangePercent = stock.changePercent;
                const currentPrice = stock.price;
                const currentPriceCny = stock.priceCny;
                
                // 直接修改 stock 对象
                stock.pivotPrice = newPivot;
                stock.triggerBuy = axisData.data.trigger_buy;
                stock.triggerSell = axisData.data.trigger_sell;
                
                // 恢复涨跌幅数据
                stock.change = currentChange;
                stock.changePercent = currentChangePercent;
                stock.price = currentPrice;
                stock.priceCny = currentPriceCny;
                
                // 同步更新后端数据库（不等待），自动处理股票不存在的情况
                syncAxisPriceToBackend(stock, newPivot);
                
                console.log(`[refreshAxisPrices] ${stock.code} 中轴价: ${oldPivot.toFixed(2)} -> ${newPivot.toFixed(2)}, 涨跌: ${stock.change}, 涨跌幅: ${stock.changePercent}%`);
                
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
                const timeoutSec = stock.market === '港股' ? '15' : '8';
                console.warn(`[refreshAxisPrices] ${stock.code} 请求超时(${timeoutSec}秒)`);
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
    
    // 重新渲染 - 只在需要时渲染
    if (shouldRender) {
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
    }
    
    return { updatedCount, failedCount, changedStocks };
}

/**
 * 同步中轴价格到后端，自动处理股票不存在的情况（404自动创建）
 * @param {Object} stock - 股票对象
 * @param {number} newPivot - 新的中轴价格
 */
async function syncAxisPriceToBackend(stock, newPivot) {
    try {
        // 先尝试更新中轴价格
        const response = await fetch(`/api/stocks/${stock.id}/axis`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                axis_price: newPivot,
                base_position_pct: stock.baseRatio || 50,
                float_position_pct: stock.floatRatio || 50,
                trigger_pct: 8,
                grid_levels: stock.gridLevels || []
            })
        });
        
        if (response.ok) {
            console.log(`[syncAxisPriceToBackend] ${stock.code} 更新成功`);
            return;
        }
        
        // 404 表示股票不存在，需要创建
        if (response.status === 404) {
            console.log(`[syncAxisPriceToBackend] ${stock.code} 不存在，自动创建...`);
            
            const createResponse = await fetch('/api/stocks', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    code: stock.code,
                    name: stock.name,
                    market: stock.market || 'A股',
                    avg_cost: stock.holdCost || 0,
                    shares: stock.holdQuantity || 0,
                    current_price: stock.price || 0,
                    axis_price: newPivot,
                    base_position_pct: stock.baseRatio || 50,
                    float_position_pct: stock.floatRatio || 50,
                    trigger_pct: 8,
                    grid_levels: stock.gridLevels || [],
                    next_buy_price: stock.triggerBuy || 0,
                    next_sell_price: stock.triggerSell || 0,
                    strategy_mode: stock.strategy || '基础',
                    exchange_rate: stock.exchangeRate  // 传递汇率字段
                })
            });
            
            if (createResponse.ok) {
                const result = await createResponse.json();
                if (result.success && result.stock) {
                    // 更新前端股票ID为后端返回的新ID
                    stock.id = result.stock.id;
                    console.log(`[syncAxisPriceToBackend] ${stock.code} 创建成功，新ID: ${stock.id}`);
                }
            } else {
                console.error(`[syncAxisPriceToBackend] ${stock.code} 创建失败:`, createResponse.status);
            }
        } else {
            console.warn(`[syncAxisPriceToBackend] ${stock.code} 更新失败:`, response.status);
        }
    } catch (e) {
        console.warn(`[syncAxisPriceToBackend] ${stock.code} 异常:`, e.message);
    }
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
        let marketValue;
        // 数据文件中字段可能是 shares 或 holdQuantity
        const quantity = stock.holdQuantity || stock.shares || 0;
        
        if (isHKStock) {
            // 港股：优先使用已转换的人民币价格(priceCny)
            // 官方中间价：1港币≈0.9229人民币 => 1人民币≈1.0836港币
            const exchangeRate = stock.exchangeRate || appState.exchangeRate || 1.0836;
            if (stock.priceCny) {
                marketValue = stock.priceCny * quantity;
            } else {
                // 没有 priceCny 时，用港币价格 / 汇率
                const cnyPrice = (stock.price || 0) / exchangeRate;
                marketValue = cnyPrice * quantity;
            }
        } else {
            // A股：直接计算人民币市值
            marketValue = (stock.price || 0) * quantity;
        }
        
        totalPosition += marketValue;
        
        // 当日盈亏 = 持仓数量 × 涨跌额（已转换为人民币）
        // 港股涨跌额是港币，需要转换
        let changeAmount = stock.change || 0;
        if (isHKStock && changeAmount !== 0) {
            const exchangeRate = stock.exchangeRate || appState.exchangeRate || 1.1339;
            changeAmount = changeAmount / exchangeRate; // 港币转人民币
        }
        todayPnL += changeAmount * quantity;
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
    console.log('[renderStockList] ========== 开始执行 ==========');
    console.log('[renderStockList] 函数已被调用，this:', this);
    console.log('[renderStockList] appState:', typeof appState);
    console.log('[renderStockList] appState.stocks:', appState ? (appState.stocks ? appState.stocks.length : 'stocks undefined') : 'appState undefined');
    
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

    // 给所有数值字段加默认值，防止后端数据缺失导致报错
    const safeStock = {
        price: stock.price ?? 0,
        change: stock.change ?? 0,
        changePercent: stock.changePercent ?? 0,
        holdCost: stock.holdCost ?? 0,
        holdQuantity: stock.holdQuantity || stock.shares || 0,
        investLimit: stock.investLimit ?? 0,
        strategy: stock.strategy || '买入持有',
        pivotPrice: stock.pivotPrice ?? 0,
        triggerBuy: stock.triggerBuy ?? 0,
        triggerSell: stock.triggerSell ?? 0,
        floatRatio: stock.floatRatio ?? 0,
        baseRatio: stock.baseRatio ?? 50,
        name: stock.name || '--',
        code: stock.code || '--',
        market: stock.market || 'A股',
        exchangeRate: stock.exchangeRate ?? 0.92,
        ...stock
    };

    const isUp = safeStock.change >= 0;
    const isHKStock = safeStock.market === '港股';

    // 获取汇率
    const exchangeRate = safeStock.exchangeRate || appState.exchangeRate || 0.92;

    // 港股/A股市值计算
    let marketValue = 0, costValue = 0, pnl = 0, pnlPercent = 0, positionShares = 0, positionValueHkd = 0;

    if (isHKStock) {
        const yesterdayRate = safeStock.exchangeRate || exchangeRate || 1.1339;
        positionShares = safeStock.holdQuantity;
        positionValueHkd = safeStock.price * positionShares;
        marketValue = positionValueHkd / yesterdayRate;
        costValue = safeStock.holdCost * positionShares;
        pnl = marketValue - costValue;
        pnlPercent = costValue > 0 ? (pnl / costValue * 100) : 0;
    } else {
        positionShares = safeStock.holdQuantity;
        marketValue = safeStock.price * positionShares;
        costValue = safeStock.holdCost * positionShares;
        pnl = marketValue - costValue;
        pnlPercent = costValue > 0 ? (pnl / costValue * 100) : 0;
    }

    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    // 基础信息
    setText('detailName', safeStock.name);
    setText('detailCode', safeStock.code);
    setText('detailStrategy', safeStock.strategy + '策略');

    // 价格
    if (isHKStock) {
        setText('detailPrice', `${safeStock.price.toFixed(2)} HKD`);
    } else {
        setText('detailPrice', safeStock.price.toFixed(2));
    }

    const detailPriceEl = document.getElementById('detailPrice');
    if (detailPriceEl) detailPriceEl.className = 'current-price ' + (isUp ? 'up' : 'down');

    const detailChangeEl = document.getElementById('detailChange');
    if (detailChangeEl) {
        detailChangeEl.textContent = `${isUp ? '+' : ''}${safeStock.change.toFixed(2)} (${isUp ? '+' : ''}${safeStock.changePercent.toFixed(2)}%)`;
        detailChangeEl.className = 'price-change ' + (isUp ? 'up' : 'down');
    }

    // 策略卡片
    setText('detailLimit', formatMoney(safeStock.investLimit));
    
    // 当前持仓
    if (isHKStock) {
        const cnyValue = positionValueHkd / exchangeRate;
        setText('detailPosition', `${positionShares}股 / ${(cnyValue/10000).toFixed(2)}万`);
    } else {
        setText('detailPosition', `${positionShares}股 / ${formatMoney(marketValue)}`);
    }

    // 持仓成本
    if (isHKStock) {
        setText('detailCost', `${safeStock.holdCost.toFixed(2)} (人民币)`);
    } else {
        setText('detailCost', safeStock.holdCost.toFixed(2));
    }

    const detailPnLEl = document.getElementById('detailPnL');
    if (detailPnLEl) {
        detailPnLEl.textContent = `${pnl >= 0 ? '+' : ''}${formatMoney(pnl)} (${pnlPercent.toFixed(2)}%)`;
        detailPnLEl.style.color = pnl >= 0 ? 'var(--up-color)' : 'var(--down-color)';
    }

    const detailPnLPercentEl = document.getElementById('detailPnLPercent');
    if (detailPnLPercentEl) {
        detailPnLPercentEl.textContent = pnlPercent.toFixed(2) + '%';
        detailPnLPercentEl.className = 'card-value ' + (pnl >= 0 ? 'up' : 'down');
    }

    // 持仓比例 = 市值 / 投资上限
    const investLimit = safeStock.investLimit || 1;
    let positionRatio = 0;
    if (investLimit > 0) {
        positionRatio = (marketValue / investLimit) * 100;
    }
    
    const detailPivotEl = document.getElementById('detailPivot');
    if (detailPivotEl) {
        detailPivotEl.textContent = positionRatio.toFixed(2) + '%';
    }

    // 中轴价格
    let pivotPriceValue = parseFloat(safeStock.pivotPrice) || 0;
    const pivotCenterEl = document.getElementById('pivotCenter');
    if (pivotCenterEl) {
        if (isHKStock) {
            pivotCenterEl.textContent = 'HK$' + pivotPriceValue.toFixed(2);
        } else {
            pivotCenterEl.textContent = pivotPriceValue.toFixed(2);
        }
    }

    const currentPriceLabelEl = document.getElementById('currentPriceLabel');
    if (currentPriceLabelEl) {
        if (isHKStock) {
            currentPriceLabelEl.textContent = 'HK$' + safeStock.price.toFixed(2);
        } else {
            currentPriceLabelEl.textContent = safeStock.price.toFixed(2);
        }
    }

    setText('detailBase', safeStock.baseRatio + '%');
    setText('detailFloat', safeStock.floatRatio + '%');

    // 触发价格
    let triggerBuy = safeStock.triggerBuy || (pivotPriceValue * 0.92);
    let triggerSell = safeStock.triggerSell || (pivotPriceValue * 1.08);
    
    if (isHKStock && safeStock.holdCost > 0) {
        const expectedTriggerSellHkd = pivotPriceValue * 1.08;
        if (triggerSell < expectedTriggerSellHkd * 0.5) {
            triggerBuy = pivotPriceValue * 0.92;
            triggerSell = pivotPriceValue * 1.08;
        }
    }
    
    if (isHKStock) {
        setText('triggerBuy', 'HK$' + triggerBuy.toFixed(2));
        setText('triggerSell', 'HK$' + triggerSell.toFixed(2));
    } else {
        setText('triggerBuy', triggerBuy.toFixed(2));
        setText('triggerSell', triggerSell.toFixed(2));
    }

    // 安全计算距离
    let distBuy = '0.0';
    let distSell = '0.0';
    if (triggerBuy > 0) {
        distBuy = ((safeStock.price - triggerBuy) / triggerBuy * 100).toFixed(1);
    }
    if (safeStock.price > 0) {
        distSell = ((triggerSell - safeStock.price) / safeStock.price * 100).toFixed(1);
    }
    setText('distanceBuy', `距触发 ${distBuy}%`);
    setText('distanceSell', `距触发 ${distSell}%`);

    // 进度条
    const markerCurrentEl = document.getElementById('markerCurrent');
    if (markerCurrentEl && triggerSell !== triggerBuy) {
        const progress = ((safeStock.price - triggerBuy) / (triggerSell - triggerBuy) * 100);
        markerCurrentEl.style.left = Math.max(0, Math.min(100, progress)) + '%';
    }

    // 操作建议
    let suggestion = '';
    if (safeStock.price >= triggerSell) {
        const sellAmount = safeStock.investLimit * (safeStock.floatRatio / 100) * 0.2;
        const sellShares = safeStock.price > 0 ? Math.floor(sellAmount / safeStock.price) : 0;
        suggestion = `⚡ 触发卖出信号！建议减持浮动仓20%，约卖出 ${sellShares} 股，金额约 ${(sellAmount/10000).toFixed(1)} 万元。`;
    } else if (safeStock.price <= triggerBuy) {
        const buyAmount = safeStock.investLimit * (safeStock.floatRatio / 100) * 0.2;
        const buyShares = safeStock.price > 0 ? Math.floor(buyAmount / safeStock.price) : 0;
        suggestion = `⚡ 触发买入信号！建议增持浮动仓20%，约买入 ${buyShares} 股，金额约 ${(buyAmount/10000).toFixed(1)} 万元。`;
    } else {
        suggestion = `📊 当前股价处于中轴附近，建议持有观望。等待股价达到 ${triggerBuy.toFixed(2)}（买入）或 ${triggerSell.toFixed(2)}（卖出）时触发操作。`;
    }
    setText('suggestionContent', suggestion);

    // 渲染网格策略表格
    renderGridStrategy(stock);
    
    // 港股：显示沽空风险提示（调用完整渲染函数）
    if (isHKStock) {
        renderHKShortRiskWarning();
    } else {
        const warningEl = document.getElementById('hkShortRiskWarning');
        if (warningEl) warningEl.style.display = 'none';
    }
}
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

// 缓存：港股沽空数据
const _hkShortCache = {};
const _hkShortCacheTTL = 5 * 60 * 1000;

// 渲染港股沽空风险提示（带缓存，避免闪烁）
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
    
    // 检查缓存
    const cacheKey = stock.code;
    const cached = _hkShortCache[cacheKey];
    const now = Date.now();
    
    // 如果有缓存且在有效期内，直接使用缓存数据
    if (cached && (now - cached.timestamp) < _hkShortCacheTTL) {
        console.log('[renderHKShortRiskWarning] 使用缓存数据，股票:', stock.code);
        renderHKShortDataInternal(cached.data.marketData, cached.data.stockData);
        return;
    }
    
    // 显示容器
    warningEl.style.display = 'block';
    
    // 只在首次加载或无缓存时显示"加载中"
    if (!cached) {
        const setText = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        };
        setText('hkStockShortAmount', '加载中...');
        setText('hkIndividualShortAmount', '加载中...');
    }
    
    try {
        // 并行获取市场数据和个股数据
        const [marketResponse, stockResponse] = await Promise.all([
            fetch('/api/market/sentiment'),
            fetch(`/api/hk-stock/${stock.code}/short-selling`)
        ]);
        
        const marketData = await marketResponse.json();
        const stockData = await stockResponse.json();
        
        // 缓存数据
        _hkShortCache[cacheKey] = {
            data: { marketData, stockData },
            timestamp: now
        };
        
        // 渲染数据
        renderHKShortDataInternal(marketData, stockData);
        console.log('[renderHKShortRiskWarning] 渲染完成');
    } catch (e) {
        console.error('[renderHKShortRiskWarning] 加载失败:', e);
        const setText = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value;
        };
        setText('hkIndividualShortAmount', '加载失败');
        setText('hkIndividualShortRatio', '--');
    }
}

// 内部函数：渲染沽空数据到DOM
function renderHKShortDataInternal(marketData, stockData) {
    // 安全设置文本的辅助函数
    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };
    
    // 安全设置className的辅助函数
    const setClass = (id, className) => {
        const el = document.getElementById(id);
        if (el) el.className = className;
    };
    
    // 1. 渲染恒生科技指数整体数据
    if (marketData.success && marketData.north_south && marketData.north_south.hk_short_selling) {
        const hkShort = marketData.north_south.hk_short_selling;
        
        // 如果数据待披露
        if (hkShort.data_pending) {
            setText('hkStockShortAmount', '待披露');
            setText('hkStockShortRatio', 'T+1');
            setText('hkStockChange3D', '--');
            setText('hkStockChange1W', '--');
            setText('hkStockChange2W', '--');
            setText('hkStockChange1M', '--');
            
            const adviceEl = document.getElementById('hkStockRiskAdvice');
            if (adviceEl) {
                adviceEl.textContent = '⏰ 港交所沽空数据T+1披露，收盘后次日更新。可通过富途/雪球查看实时估算。';
                adviceEl.className = 'hk-risk-advice normal';
            }
            setText('hkShortUpdateTime', hkShort.update_date || '--');
        } else if (hkShort.short_volume_wan !== null && hkShort.short_ratio !== null) {
            // 正常显示数据 - 显示沽空股数（万股）
            setText('hkStockShortAmount', `${hkShort.short_volume_wan}万股`);
            
            setText('hkStockShortRatio', `${hkShort.short_ratio}%`);
            setClass('hkStockShortRatio', `hk-metric-value ${hkShort.short_ratio > 15 ? 'high-risk' : hkShort.short_ratio > 10 ? 'medium-risk' : 'low-risk'}`);
            
            // 变化趋势 - 3天、1周、2周、1月
            const changes = hkShort.changes || {};
            const formatChange = (c) => {
                if (!c || c.volume_change === undefined) return '--';
                const sign = c.volume_change >= 0 ? '+' : '';
                return `${sign}${c.volume_change}万股`;
            };
            
            const change3d = changes['3d'] || {};
            const change1w = changes['1w'] || {};
            const change2w = changes['2w'] || {};
            const change1m = changes['1m'] || {};
            
            setText('hkStockChange3D', formatChange(change3d));
            setClass('hkStockChange3D', `hk-trend-value ${(change3d.volume_change || 0) >= 0 ? 'high-risk' : 'low-risk'}`);
            
            setText('hkStockChange1W', formatChange(change1w));
            setClass('hkStockChange1W', `hk-trend-value ${(change1w.volume_change || 0) >= 0 ? 'high-risk' : 'low-risk'}`);
            
            setText('hkStockChange2W', formatChange(change2w));
            setClass('hkStockChange2W', `hk-trend-value ${(change2w.volume_change || 0) >= 0 ? 'high-risk' : 'low-risk'}`);
            
            setText('hkStockChange1M', formatChange(change1m));
            setClass('hkStockChange1M', `hk-trend-value ${(change1m.volume_change || 0) >= 0 ? 'high-risk' : 'low-risk'}`);
            
            // 恒生科技指数风险提示 - 结合交易信号
            const tradeSignals = hkShort.trade_signals || {};
            const adviceEl = document.getElementById('hkStockRiskAdvice');
            if (adviceEl) {
                let adviceText = '';
                let adviceClass = 'normal';
                
                if (tradeSignals.sell_enhanced) {
                    adviceText = '⚠️ 恒生科技指数沽空比例极高且空头在加仓，科技股整体做空压力大，建议减仓避险。';
                    adviceClass = 'high-risk';
                } else if (tradeSignals.buy_enhanced) {
                    adviceText = '✅ 恒生科技指数沽空压力小且空头在撤退，科技股整体环境较好。';
                    adviceClass = 'low-risk';
                } else if (hkShort.short_ratio > 20) {
                    adviceText = '📉 恒生科技指数沽空比例极高，科技股整体做空情绪浓厚，建议谨慎操作。';
                    adviceClass = 'high-risk';
                } else if (hkShort.short_ratio > 15) {
                    adviceText = '⚠️ 恒生科技指数沽空压力较大，科技股偏空，建议控制仓位。';
                    adviceClass = 'medium-risk';
                } else if (hkShort.short_ratio > 10) {
                    adviceText = '⚖️ 恒生科技指数沽空比例适中，科技股存在分歧，建议关注个股基本面。';
                    adviceClass = 'normal';
                } else {
                    adviceText = '✅ 恒生科技指数沽空比例较低，科技股整体环境较好。';
                    adviceClass = 'low-risk';
                }
                
                // 添加趋势方向
                const trendDirection = hkShort.trend_direction || '';
                if (trendDirection.includes('空头撤退')) {
                    adviceText += ' [空头撤退]';
                } else if (trendDirection.includes('空头聚集')) {
                    adviceText += ' [空头聚集]';
                }
                
                adviceEl.textContent = adviceText;
                adviceEl.className = `hk-risk-advice ${adviceClass}`;
            }
            
            setText('hkShortUpdateTime', hkShort.update_date || '--');
        } else {
            // 数据异常
            setText('hkStockShortAmount', '--');
            setText('hkStockShortRatio', '--');
        }
    }
    
    // 2. 渲染个股沽空数据
    if (stockData.success) {
        const individualShort = stockData;
        
        if (individualShort.data_pending) {
            // 数据待披露
            setText('hkIndividualShortAmount', '待披露');
            setText('hkIndividualShortRatio', 'T+1');
            setText('hkIndividualSignal', '港交所');
            setText('hkIndividualChange3D', '--');
            setText('hkIndividualChange1W', '--');
            setText('hkIndividualChange2W', '--');
            setText('hkIndividualChange1M', '--');
            setText('hkIndividualTrend', '--');
            
            const adviceEl = document.getElementById('hkIndividualAdvice');
            if (adviceEl) {
                adviceEl.textContent = '⏰ 港交所个股沽空数据T+1披露，可通过专业终端查看实时估算。';
                adviceEl.className = 'hk-risk-advice normal';
            }
            setText('hkIndividualUpdateTime', individualShort.update_date || '--');
        } else if (individualShort.short_volume_wan !== null && individualShort.short_ratio !== null) {
            // 正常显示个股数据
            setText('hkIndividualShortAmount', `${individualShort.short_volume_wan}万股`);
            
            setText('hkIndividualShortRatio', `${individualShort.short_ratio}%`);
            setClass('hkIndividualShortRatio', `hk-metric-value ${individualShort.short_ratio > 15 ? 'high-risk' : individualShort.short_ratio > 10 ? 'medium-risk' : 'low-risk'}`);
            
            // 显示信号（偏多/中性/偏空）
            const signalText = individualShort.signal || '--';
            setText('hkIndividualSignal', signalText);
            
            // 根据风险等级设置信号颜色
            const tradeSignals = individualShort.trade_signals || {};
            const riskLevel = tradeSignals.risk_level || 'normal';
            let signalClass = 'neutral';
            if (riskLevel === 'low') signalClass = 'up';
            else if (riskLevel === 'critical' || riskLevel === 'high') signalClass = 'down';
            else signalClass = individualShort.short_ratio > 15 ? 'down' : 'up';
            setClass('hkIndividualSignal', `hk-metric-value ${signalClass}`);
            
            // 个股变化趋势 - 新周期：3天、1周、2周、1月
            const changes = individualShort.changes || {};
            const formatChange = (c) => {
                if (!c || c.volume_change === undefined) return '--';
                const sign = c.volume_change >= 0 ? '+' : '';
                return `${sign}${c.volume_change}万股`;
            };
            
            const change3d = changes['3d'] || {};
            const change1w = changes['1w'] || {};
            const change2w = changes['2w'] || {};
            const change1m = changes['1m'] || {};
            
            // 3天变化
            setText('hkIndividualChange3D', formatChange(change3d));
            setClass('hkIndividualChange3D', `hk-trend-value ${(change3d.volume_change || 0) >= 0 ? 'high-risk' : 'low-risk'}`);
            
            // 1周变化
            setText('hkIndividualChange1W', formatChange(change1w));
            setClass('hkIndividualChange1W', `hk-trend-value ${(change1w.volume_change || 0) >= 0 ? 'high-risk' : 'low-risk'}`);
            
            // 2周变化
            setText('hkIndividualChange2W', formatChange(change2w));
            setClass('hkIndividualChange2W', `hk-trend-value ${(change2w.volume_change || 0) >= 0 ? 'high-risk' : 'low-risk'}`);
            
            // 1月变化
            setText('hkIndividualChange1M', formatChange(change1m));
            setClass('hkIndividualChange1M', `hk-trend-value ${(change1m.volume_change || 0) >= 0 ? 'high-risk' : 'low-risk'}`);
            
            // 渲染趋势迷你图
            renderTrendChart('hkIndividualTrendChart', [change3d, change1w, change2w, change1m]);
            
            // 趋势方向
            const trendDirection = individualShort.trend_direction || '数据不足';
            setText('hkIndividualTrend', trendDirection);
            
            // 个股风险提示 - 结合交易信号
            const adviceEl = document.getElementById('hkIndividualAdvice');
            if (adviceEl) {
                let adviceText = '';
                let adviceClass = 'normal';
                
                if (tradeSignals.sell_enhanced) {
                    // 强烈卖出信号
                    adviceText = '⚠️ 沽空比例极高且空头在加仓，做空压力大，建议减仓或止损避险。';
                    adviceClass = 'high-risk';
                } else if (tradeSignals.buy_enhanced) {
                    // 强烈买入信号
                    adviceText = '✅ 沽空压力小且空头在撤退，可关注买入机会（配合中轴价格策略）。';
                    adviceClass = 'low-risk';
                } else if (individualShort.short_ratio > 20) {
                    adviceText = '📉 该股票沽空比例极高，做空压力巨大，建议高度警惕。';
                    adviceClass = 'high-risk';
                } else if (individualShort.short_ratio > 15) {
                    adviceText = '⚠️ 该股票沽空压力较大，存在做空风险，建议控制仓位。';
                    adviceClass = 'medium-risk';
                } else if (individualShort.short_ratio > 10) {
                    adviceText = '⚖️ 该股票沽空比例适中，需关注市场情绪变化。';
                    adviceClass = 'normal';
                } else {
                    adviceText = '✅ 该股票沽空比例较低，做空压力较小。';
                    adviceClass = 'low-risk';
                }
                
                // 添加趋势信息
                if (trendDirection.includes('空头撤退')) {
                    adviceText += ' [空头撤退]';
                } else if (trendDirection.includes('空头聚集')) {
                    adviceText += ' [空头聚集]';
                }
                
                adviceEl.textContent = adviceText;
                adviceEl.className = `hk-risk-advice ${adviceClass}`;
            }
            
            setText('hkIndividualUpdateTime', individualShort.update_date || '--');
        }
    }
    
    // 渲染90日历史趋势图
    renderHKShortHistoryCharts(stockData);
}

/**
 * 渲染港股沽空90日历史趋势图
 * @param {Object} stockData - 个股沽空数据（包含股票代码）
 */
async function renderHKShortHistoryCharts(stockData) {
    if (!stockData || !stockData.stock_code) return;
    
    try {
        // 并行获取个股和指数历史数据
        const [stockHistoryRes, marketHistoryRes] = await Promise.all([
            fetch(`/api/hk-stock/${stockData.stock_code}/short-selling-history?days=90`),
            fetch('/api/hk-short-selling-history?days=90')
        ]);
        
        const stockHistory = await stockHistoryRes.json();
        const marketHistory = await marketHistoryRes.json();
        
        // 绘制个股历史趋势图
        if (stockHistory.success && stockHistory.history && stockHistory.history.length > 0) {
            drawShortHistoryChart('hkIndividualHistoryChart', stockHistory.history, '个股沽空股数');
        }
        
        // 绘制指数历史趋势图
        if (marketHistory.success && marketHistory.history && marketHistory.history.length > 0) {
            drawShortHistoryChart('hkMarketHistoryChart', marketHistory.history, '指数沽空股数');
        }
    } catch (e) {
        console.error('[renderHKShortHistoryCharts] 加载历史数据失败:', e);
    }
}

/**
 * 绘制沽空历史趋势图（Canvas）
 * @param {string} canvasId - Canvas元素ID
 * @param {Array} history - 历史数据数组 [{date, short_volume}, ...]
 * @param {string} label - 图表标签
 */
function drawShortHistoryChart(canvasId, history, label) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    
    // 清空画布
    ctx.clearRect(0, 0, width, height);
    
    if (history.length === 0) return;
    
    // 边距
    const padding = { top: 20, right: 10, bottom: 30, left: 50 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    
    // 提取数据
    const volumes = history.map(h => h.short_volume);
    const minVolume = Math.min(...volumes);
    const maxVolume = Math.max(...volumes);
    const volumeRange = maxVolume - minVolume || 1;
    
    // 颜色
    const upColor = '#4caf50';
    const downColor = '#f44336';
    const gridColor = 'rgba(255,255,255,0.1)';
    const textColor = 'rgba(255,255,255,0.6)';
    
    // 绘制网格线（水平）
    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = padding.top + (chartHeight / 4) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();
    }
    
    // 绘制Y轴标签
    ctx.fillStyle = textColor;
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (let i = 0; i <= 4; i++) {
        const value = maxVolume - (volumeRange / 4) * i;
        const y = padding.top + (chartHeight / 4) * i;
        ctx.fillText(formatVolume(value), padding.left - 5, y);
    }
    
    // 绘制柱状图
    const barWidth = Math.max(2, chartWidth / history.length * 0.7);
    const gap = chartWidth / history.length * 0.3;
    
    history.forEach((item, index) => {
        const x = padding.left + (chartWidth / history.length) * index + gap / 2;
        const barHeight = ((item.short_volume - minVolume) / volumeRange) * chartHeight;
        const y = padding.top + chartHeight - barHeight;
        
        // 判断涨跌（与前一天比较）
        let color = upColor;
        if (index > 0 && item.short_volume > history[index - 1].short_volume) {
            color = downColor; // 沽空增加为红色
        }
        
        // 绘制柱子
        ctx.fillStyle = color;
        ctx.fillRect(x, y, barWidth, barHeight);
    });
    
    // 绘制X轴标签（只显示部分日期）
    ctx.fillStyle = textColor;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const labelStep = Math.ceil(history.length / 6);
    for (let i = 0; i < history.length; i += labelStep) {
        const x = padding.left + (chartWidth / history.length) * i + gap / 2 + barWidth / 2;
        const date = history[i].date.substring(5); // 只显示 MM-DD
        ctx.fillText(date, x, padding.top + chartHeight + 5);
    }
    
    // 绘制标题
    ctx.fillStyle = textColor;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.font = '11px sans-serif';
    ctx.fillText(label, padding.left, 5);
}

/**
 * 格式化成交量
 * @param {number} volume - 成交量
 * @returns {string} 格式化后的字符串
 */
function formatVolume(volume) {
    if (volume >= 100000000) {
        return (volume / 100000000).toFixed(1) + '亿';
    } else if (volume >= 10000) {
        return (volume / 10000).toFixed(0) + '万';
    } else {
        return volume.toFixed(0);
    }
}

/**
 * 渲染趋势迷你柱状图
 * @param {string} elementId - 容器元素ID
 * @param {Array} changes - 变化数据数组 [{volume_change, ratio_change}, ...]
 */
function renderTrendChart(elementId, changes) {
    const container = document.getElementById(elementId);
    if (!container) return;
    
    // 提取变化值
    const values = changes.map(c => c?.volume_change || 0);
    const maxVal = Math.max(...values.map(Math.abs), 1); // 避免除以0
    
    // 生成柱状图HTML
    const bars = values.map((val, idx) => {
        const height = Math.min(Math.abs(val) / maxVal * 100, 100);
        const color = val >= 0 ? 'var(--danger-color, #f44336)' : 'var(--success-color, #4caf50)';
        const labels = ['3天', '1周', '2周', '1月'];
        return `
            <div style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px;">
                <div style="width: 100%; height: 40px; display: flex; align-items: flex-end; justify-content: center;">
                    <div style="width: 60%; height: ${height}%; background: ${color}; border-radius: 2px 2px 0 0; opacity: 0.8;"></div>
                </div>
                <div style="font-size: 0.65rem; color: var(--text-muted);">${labels[idx]}</div>
                <div style="font-size: 0.7rem; font-weight: 600; color: ${color};">${val >= 0 ? '+' : ''}${val.toFixed(1)}万</div>
            </div>
        `;
    }).join('');
    
    container.innerHTML = bars;
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

// 渲染新闻 - 结构化财联社新闻 (头条/题材/日历/持仓/情绪分析)
function renderNews() {
    const listEl = document.getElementById('newsList');
    if (!listEl) return;
    
    listEl.innerHTML = '';

    // 检查是否有结构化数据
    if (!appState.news || typeof appState.news !== 'object') {
        listEl.innerHTML = '<div class="news-empty">暂无新闻</div>';
        return;
    }

    const { headlines = [], themes = [], calendar = [], portfolio = [], general = [], hot_themes = [], market_sentiment = {} } = appState.news;
    
    // 0. 渲染市场情绪指数
    if (market_sentiment && market_sentiment.index !== undefined) {
        const sentimentSection = document.createElement('div');
        sentimentSection.className = 'news-section sentiment-section';
        const { index = 50, label = '中性', distribution = {} } = market_sentiment;
        const total = (distribution.positive || 0) + (distribution.neutral || 0) + (distribution.negative || 0);
        
        // 根据指数确定颜色
        let sentimentColor = '#888';
        let sentimentBg = '#f0f0f0';
        if (index >= 60) { sentimentColor = '#10b981'; sentimentBg = '#d1fae5'; }
        else if (index <= 40) { sentimentColor = '#ef4444'; sentimentBg = '#fee2e2'; }
        else { sentimentColor = '#f59e0b'; sentimentBg = '#fef3c7'; }
        
        sentimentSection.innerHTML = `
            <div class="market-sentiment-card" style="background: ${sentimentBg}; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-weight: bold; color: #333;">📊 市场情绪</span>
                    <span style="font-size: 24px; font-weight: bold; color: ${sentimentColor};">${index}<span style="font-size: 14px;">/100</span></span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #666;">
                    <span>整体: <b style="color: ${sentimentColor}">${label}</b></span>
                    ${total > 0 ? `
                        <span>🟢${distribution.positive || 0} 🟡${distribution.neutral || 0} 🔴${distribution.negative || 0}</span>
                    ` : ''}
                </div>
            </div>
        `;
        listEl.appendChild(sentimentSection);
    }
    
    // 1. 渲染投资日历（财联社风格 - 未来一周）
    if (calendar.length > 0) {
        const calendarSection = document.createElement('div');
        calendarSection.className = 'news-section calendar-section';
        
        // 统计今天和未来的事件数
        const todayCount = calendar.filter(c => c.is_today).length;
        const futureCount = calendar.filter(c => !c.is_today).length;
        const badgeHtml = futureCount > 0 ? `<span style="color: var(--accent-blue); font-size: 0.85rem;">未来${futureCount}项</span>` : '';
        
        calendarSection.innerHTML = `
            <div class="news-section-title">
                📅 投资日历 ${badgeHtml}
                <span style="float: right; font-size: 0.75rem; color: var(--text-muted); cursor: pointer;" onclick="showCalendarDetail()">查看全部 →</span>
            </div>
        `;
        
        // 财联社风格时间轴
        const timelineEl = document.createElement('div');
        timelineEl.className = 'calendar-timeline';
        
        // 按日期分组
        const groupedByDate = {};
        calendar.slice(0, 8).forEach(item => {  // 最多显示8条
            const dateKey = item.date;
            if (!groupedByDate[dateKey]) {
                groupedByDate[dateKey] = {
                    date: item.date,
                    weekday: item.weekday,
                    is_today: item.is_today,
                    events: []
                };
            }
            groupedByDate[dateKey].events.push(item);
        });
        
        Object.values(groupedByDate).forEach(day => {
            const dayEl = document.createElement('div');
            dayEl.className = `calendar-day ${day.is_today ? 'today' : ''}`;
            
            const todayBadge = day.is_today ? '<span class="today-badge">今天</span>' : '';
            
            dayEl.innerHTML = `
                <div class="calendar-day-header">
                    <span class="calendar-date">${day.date}</span>
                    <span class="calendar-weekday">${day.weekday}</span>
                    ${todayBadge}
                </div>
                <div class="calendar-events">
                    ${day.events.map(event => `
                        <div class="calendar-event-item ${event.importance >= 2 ? 'important' : ''}" onclick="showEventDetail('${encodeURIComponent(event.title)}')">
                            <span class="event-time">${event.time || '--:--'}</span>
                            <span class="event-title">${event.title}</span>
                            ${event.is_portfolio_related ? '<span class="portfolio-badge">持仓</span>' : ''}
                            <span class="event-importance ${event.importance >= 3 ? 'major' : event.importance >= 2 ? 'important' : 'normal'}">${event.importance_label}</span>
                        </div>
                    `).join('')}
                </div>
            `;
            timelineEl.appendChild(dayEl);
        });
        
        calendarSection.appendChild(timelineEl);
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

    // 4. 渲染持仓相关 (带负面预警)
    if (portfolio.length > 0) {
        const portfolioSection = document.createElement('div');
        portfolioSection.className = 'news-section';
        
        // 检查是否有负面新闻
        const negativeCount = portfolio.filter(n => n.sentiment === 'negative').length;
        const warningHtml = negativeCount > 0 ? `<span style="color: #ef4444; font-size: 0.85rem;">⚠️ ${negativeCount}条需关注</span>` : '';
        
        portfolioSection.innerHTML = `<div class="news-section-title">💼 持仓相关 ${warningHtml}</div>`;
        
        portfolio.forEach(news => {
            // 负面新闻添加 warning 类
            const type = news.sentiment === 'negative' ? 'portfolio warning' : 'portfolio';
            const el = createNewsElement(news, type);
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

    // 6. 渲染普通快讯
    if (general.length > 0) {
        const generalSection = document.createElement('div');
        generalSection.className = 'news-section';
        generalSection.innerHTML = '<div class="news-section-title">📋 财经快讯</div>';
        
        general.forEach(news => {
            const el = createNewsElement(news, 'normal');
            generalSection.appendChild(el);
        });
        listEl.appendChild(generalSection);
    }
    
    // 如果完全没有新闻（只有市场情绪卡片）
    if (listEl.children.length <= 1) {
        const emptySection = document.createElement('div');
        emptySection.className = 'news-empty';
        emptySection.innerHTML = '<div style="text-align: center; padding: 20px; color: #666;">暂无新闻数据</div>';
        listEl.appendChild(emptySection);
    }
}

// 创建新闻元素
function createNewsElement(news, type) {
    const item = document.createElement('div');
    item.className = `news-item ${type}`;
    
    const importanceClass = news.importance >= 2 ? 'important' : news.importance === 1 ? 'attention' : 'normal';
    
    // 情绪标签
    const sentimentEmoji = {'positive': '🟢', 'negative': '🔴', 'neutral': '🟡'}[news.sentiment] || '⚪';
    const sentimentClass = news.sentiment || 'neutral';
    
    // 关联板块标签
    let sectorsHtml = '';
    if (news.related_sectors && news.related_sectors.length > 0) {
        sectorsHtml = `<div class="news-sectors">${news.related_sectors.map(s => `<span class="sector-tag">${s}</span>`).join('')}</div>`;
    }
    
    item.innerHTML = `
        <div class="news-header">
            <span class="news-time">${news.time || ''}</span>
            <span class="news-tag ${importanceClass}">${news.importance_label || '一般'}</span>
            <span class="sentiment-tag ${sentimentClass}" title="情绪: ${news.sentiment_label || '中性'}">${sentimentEmoji} ${news.sentiment_label || '中性'}</span>
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

// ========== 新闻详情弹窗 ==========
let currentNewsFilter = 'all';

function showNewsDetailModal() {
    document.getElementById('newsDetailModal').classList.add('active');
    renderNewsDetailList();
}

function hideNewsDetailModal() {
    document.getElementById('newsDetailModal').classList.remove('active');
}

// ========== 投资日历详情 ==========
function showCalendarDetail() {
    // 在新弹窗中显示完整的投资日历
    const modal = document.createElement('div');
    modal.className = 'modal active';
    modal.id = 'calendarDetailModal';
    modal.innerHTML = `
        <div class="modal-content modal-large">
            <div class="modal-header">
                <h3><i class="fas fa-calendar-alt"></i> 投资日历（未来一周）</h3>
                <button class="btn-close" onclick="document.getElementById('calendarDetailModal').remove()"><i class="fas fa-times"></i></button>
            </div>
            <div class="modal-body">
                <div class="calendar-detail-timeline" id="calendarDetailTimeline">
                    <!-- 动态生成 -->
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    // 渲染完整日历
    renderCalendarDetail();
}

function renderCalendarDetail() {
    const timelineEl = document.getElementById('calendarDetailTimeline');
    if (!timelineEl || !appState.news || !appState.news.calendar) {
        timelineEl.innerHTML = '<div class="news-empty">暂无数据</div>';
        return;
    }
    
    const calendar = appState.news.calendar;
    
    // 按日期分组
    const groupedByDate = {};
    calendar.forEach(item => {
        const dateKey = item.date;
        if (!groupedByDate[dateKey]) {
            groupedByDate[dateKey] = {
                date: item.date,
                weekday: item.weekday,
                is_today: item.is_today,
                events: []
            };
        }
        groupedByDate[dateKey].events.push(item);
    });
    
    timelineEl.innerHTML = Object.values(groupedByDate).map(day => `
        <div class="calendar-day ${day.is_today ? 'today' : ''}">
            <div class="calendar-day-header">
                <span class="calendar-date">${day.date}</span>
                <span class="calendar-weekday">${day.weekday}</span>
                ${day.is_today ? '<span class="today-badge">今天</span>' : ''}
            </div>
            <div class="calendar-events">
                ${day.events.map(event => `
                    <div class="calendar-event-item ${event.importance >= 2 ? 'important' : ''}" onclick="showEventDetail('${encodeURIComponent(event.title)}')">
                        <span class="event-time">${event.time || '--:--'}</span>
                        <span class="event-title">${event.title}</span>
                        ${event.is_portfolio_related ? '<span class="portfolio-badge">持仓</span>' : ''}
                        <span class="event-importance ${event.importance >= 3 ? 'major' : event.importance >= 2 ? 'important' : 'normal'}">${event.importance_label}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `).join('');
}

function showEventDetail(titleEncoded) {
    const title = decodeURIComponent(titleEncoded);
    alert(`事件详情：\n\n${title}\n\n（后续可接入详细解读）`);
}

function filterNews(type) {
    currentNewsFilter = type;
    // 更新标签样式
    document.querySelectorAll('.news-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === type);
    });
    renderNewsDetailList();
}

function renderNewsDetailList() {
    const listEl = document.getElementById('newsDetailList');
    if (!listEl || !appState.news) {
        listEl.innerHTML = '<div class="news-empty">暂无新闻</div>';
        return;
    }
    
    const { headlines = [], themes = [], portfolio = [], general = [] } = appState.news;
    
    // 根据过滤条件选择新闻
    let allNews = [];
    switch(currentNewsFilter) {
        case 'headline':
            allNews = [...headlines];
            break;
        case 'portfolio':
            allNews = [...portfolio];
            break;
        case 'theme':
            allNews = [...themes];
            break;
        case 'all':
        default:
            allNews = [...headlines, ...themes, ...portfolio, ...general];
    }
    
    if (allNews.length === 0) {
        listEl.innerHTML = '<div class="news-empty" style="text-align: center; padding: 40px; color: #666;">该分类暂无新闻</div>';
        return;
    }
    
    // 按时间排序
    allNews.sort((a, b) => (b.time || '').localeCompare(a.time || ''));
    
    listEl.innerHTML = allNews.map(news => {
        const sentimentClass = news.sentiment || 'neutral';
        const sentimentLabel = news.sentiment_label || '中性';
        const tagClass = news.importance >= 2 ? 'important' : news.importance === 1 ? 'attention' : 'normal';
        
        return `
            <div class="news-detail-item">
                <div class="news-detail-header">
                    <span class="news-detail-time">${news.time || ''}</span>
                    <span class="news-detail-tag ${tagClass}">${news.importance_label || '一般'}</span>
                    <span class="news-detail-sentiment ${sentimentClass}">${sentimentLabel}</span>
                </div>
                <div class="news-detail-title">${news.title}</div>
                ${news.content ? `<div class="news-detail-content">${news.content}</div>` : ''}
                ${news.related_sectors?.length ? `
                    <div class="news-detail-sectors">
                        ${news.related_sectors.map(s => `<span>${s}</span>`).join('')}
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
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
            console.log('[updateStockPricesOnce] 请求超时(20秒)，中止');
            controller.abort();
        }, 20000); // 20秒超时
        
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
            let updatedCount = 0;
            appState.stocks.forEach(stock => {
                const quote = data.quotes[stock.code];
                if (quote) {
                    console.log(`[updateStockPricesOnce] ${stock.code}: 价格 ${stock.price} -> ${quote.price}, 涨跌 ${quote.change}, 涨跌幅 ${quote.change_percent}%`);
                    stock.price = quote.price;
                    stock.change = quote.change;
                    stock.changePercent = quote.change_percent;
                    updatedCount++;

                    // 港股：保存人民币转换价格和汇率
                    if (quote.market === '港股') {
                        stock.priceCny = quote.price_cny;
                        stock.exchangeRate = quote.exchange_rate;
                    }
                } else {
                    console.warn(`[updateStockPricesOnce] ${stock.code}: 无报价数据`);
                }
            });

            console.log(`[updateStockPricesOnce] 成功更新 ${updatedCount}/${appState.stocks.length} 只股票`);

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
            // 如果API返回失败，尝试重新获取
            if (retryCount < maxRetries) {
                retryCount++;
                console.log(`[updateStockPricesOnce] 第 ${retryCount} 次重试...`);
                setTimeout(() => updateStockPricesOnceWithRetry(retryCount, maxRetries), 2000);
            }
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
    console.log('[DEBUG] renderSentiment 开始执行, appState.sentiment:', appState.sentiment);
    if (!appState.sentiment) {
        console.log('[DEBUG] appState.sentiment 为空, 返回');
        return;
    }
    
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
    const northInflowEl = document.getElementById('northInflow');
    if (northInflowEl) {
        if (northSouth.north_inflow === 0 && northSouth.north_sentiment === '待接入') {
            northInflowEl.textContent = '待接入';
            northInflowEl.className = 'metric-value neutral';
        } else {
            northInflowEl.textContent = `${northSouth.north_inflow >= 0 ? '+' : ''}${northSouth.north_inflow}亿`;
            northInflowEl.className = `metric-value ${northSouth.north_inflow >= 0 ? 'up' : 'down'}`;
        }
    }
    document.getElementById('northCumulative').textContent = `${northSouth.north_cumulative}亿`;
    
    // 4. 渲染南向资金卡片
    updateCard('south', northSouth.south_inflow, northSouth.south_sentiment);
    const southInflowEl = document.getElementById('southInflow');
    if (southInflowEl) {
        if (northSouth.south_inflow === 0 && northSouth.south_sentiment === '待接入') {
            southInflowEl.textContent = '待接入';
            southInflowEl.className = 'metric-value neutral';
        } else {
            southInflowEl.textContent = `${northSouth.south_inflow >= 0 ? '+' : ''}${northSouth.south_inflow}亿`;
            southInflowEl.className = `metric-value ${northSouth.south_inflow >= 0 ? 'up' : 'down'}`;
        }
    }
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
    
    // 8. 加载持仓股分析报告
    console.log('[DEBUG] 准备调用 loadPortfolioAnalysis');
    loadPortfolioAnalysis();
    console.log('[DEBUG] loadPortfolioAnalysis 调用完成');
    
    // 9. 加载持仓港股沽空风险分析
    console.log('[DEBUG] 准备调用 loadHKPortfolioRisk');
    loadHKPortfolioRisk();
    console.log('[DEBUG] loadHKPortfolioRisk 调用完成');
}

// 加载持仓股分析报告
async function loadPortfolioAnalysis() {
    try {
        console.log('[DEBUG] loadPortfolioAnalysis 开始执行');
        const response = await fetch('/api/portfolio-analysis');
        console.log('[DEBUG] 持仓分析 API 响应状态:', response.status);
        if (!response.ok) {
            console.log('[DEBUG] 持仓分析 API 响应不成功, 返回');
            return;
        }
        
        const result = await response.json();
        console.log('[DEBUG] 持仓分析 API 返回:', result);
        if (!result.success || !result.data) {
            console.log('[DEBUG] 持仓分析数据无效, 返回');
            return;
        }
        
        appState.portfolioAnalysis = result.data;
        renderPortfolioAnalysis();
    } catch (error) {
        console.error('[DEBUG] 加载持仓分析出错:', error);
    }
}

// 渲染持仓股分析报告
function renderPortfolioAnalysis() {
    console.log('[DEBUG] renderPortfolioAnalysis 开始执行');
    const data = appState.portfolioAnalysis;
    if (!data) {
        console.log('[DEBUG] 没有持仓分析数据, 返回');
        return;
    }
    
    // 1. 更新健康度分数和等级
    const scoreEl = document.getElementById('portfolioHealthScore');
    if (scoreEl && data.summary) {
        scoreEl.textContent = data.summary.health_score + '分';
        const healthLevel = data.summary.health_level || {};
        scoreEl.style.color = healthLevel.color || '#10b981';
    }
    
    // 2. 更新报告日期
    const dateEl = document.getElementById('portfolioReportDate');
    if (dateEl && data.report_date) {
        dateEl.textContent = data.report_date;
    }
    
    // 3. 更新总体分析内容（组合层面）
    const contentEl = document.getElementById('portfolioAnalysisContent');
    if (contentEl && data.portfolio_analysis) {
        const portfolio = data.portfolio_analysis;
        const summary = data.summary;
        
        let html = `
            <div style="font-size: 0.8rem; color: var(--text-secondary); line-height: 1.6;">
                <!-- 健康度 -->
                <div style="margin-bottom: 12px; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span>📊 组合健康度</span>
                        <span style="color: ${summary.health_level?.color || '#fff'}; font-weight: 600;">${summary.health_level?.label || '--'} (${summary.health_score}分)</span>
                    </div>
                    <div style="font-size: 0.75rem; color: var(--text-muted);">${summary.health_level?.desc || ''}</div>
                </div>
                
                <!-- 仓位建议 -->
                <div style="margin-bottom: 12px; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span>💰 仓位建议</span>
                        <span style="color: #3b82f6; font-weight: 600;">建议现金${portfolio.position?.suggested_cash_ratio || 30}%</span>
                    </div>
                    <div style="font-size: 0.75rem; color: var(--text-muted);">${portfolio.position?.position_advice || ''}</div>
                    <div style="margin-top: 8px; display: flex; gap: 12px; font-size: 0.7rem;">
                        <span>💡 机会股: ${portfolio.position?.oversold_count || 0}只</span>
                        <span>⚠️ 风险股: ${portfolio.position?.overbought_count || 0}只</span>
                    </div>
                </div>
                
                <!-- 板块分析 -->
                <div style="margin-bottom: 12px; padding: 10px; background: rgba(255,255,255,0.05); border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span>🏭 板块集中</span>
                        <span style="color: ${portfolio.sector?.sector_risk === '高' ? '#ef4444' : portfolio.sector?.sector_risk === '中高' ? '#f59e0b' : '#10b981'}; font-weight: 600;">${portfolio.sector?.max_sector || '--'} ${portfolio.sector?.max_sector_ratio || 0}%</span>
                    </div>
                    <div style="font-size: 0.75rem; color: var(--text-muted);">${portfolio.sector?.sector_advice || ''}</div>
                </div>
                
                <!-- 风险提示 -->
                ${portfolio.risks && portfolio.risks.length > 0 ? `
                <div style="margin-bottom: 12px; padding: 10px; background: rgba(239,68,68,0.1); border-radius: 8px; border-left: 3px solid #ef4444;">
                    <div style="font-weight: 600; color: #ef4444; margin-bottom: 8px;">⚠️ 风险提示</div>
                    ${portfolio.risks.map(r => `
                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 4px;">
                            ${r.level === 'high' ? '🔴' : '🟡'} ${r.desc}
                        </div>
                    `).join('')}
                </div>
                ` : ''}
                
                <!-- 调仓建议 -->
                ${portfolio.rebalance && portfolio.rebalance.actions && portfolio.rebalance.actions.length > 0 ? `
                <div style="margin-bottom: 12px;">
                    <div style="font-weight: 600; margin-bottom: 8px;">🔄 调仓建议</div>
                    ${portfolio.rebalance.actions.map(a => `
                        <div style="padding: 8px; background: rgba(255,255,255,0.03); border-radius: 6px; margin-bottom: 6px; border-left: 3px solid ${a.action === 'reduce' ? '#ef4444' : '#10b981'};">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <span style="font-weight: 600; font-size: 0.8rem;">${a.name} (${a.code})</span>
                                <span style="font-size: 0.7rem; padding: 2px 8px; border-radius: 4px; background: ${a.action === 'reduce' ? '#ef444420' : '#10b98120'}; color: ${a.action === 'reduce' ? '#ef4444' : '#10b981'};">${a.action === 'reduce' ? '减仓' : '加仓'}</span>
                            </div>
                            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;">${a.suggestion}</div>
                        </div>
                    `).join('')}
                </div>
                ` : '<div style="padding: 10px; background: rgba(16,185,129,0.1); border-radius: 8px; font-size: 0.8rem; color: #10b981;">✅ 当前持仓无需调仓</div>'}
            </div>
        `;
        contentEl.innerHTML = html;
    }
    
    // 4. 渲染个股列表
    const countEl = document.getElementById('portfolioStockCount');
    const itemsEl = document.getElementById('portfolioStockItems');
    if (itemsEl && data.stock_analyses) {
        const stocks = data.stock_analyses;
        if (countEl) countEl.textContent = `${stocks.length}只`;
        
        itemsEl.innerHTML = stocks.map(stock => {
            const signalColor = stock.technical_status === 'overbought' ? '#ef4444' : 
                               stock.technical_status === 'oversold' ? '#10b981' : '#f59e0b';
            const signalText = stock.technical_status === 'overbought' ? '减仓' : 
                              stock.technical_status === 'oversold' ? '买入' : '持有';
            const statusIcon = stock.status_icon || '⚪';
            return `
                <div onclick="showStockAnalysisDetail('${stock.code}')" style="padding: 8px 10px; background: rgba(255,255,255,0.03); border-radius: 6px; cursor: pointer; transition: all 0.2s; display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;" onmouseover="this.style.background='rgba(255,255,255,0.08)'" onmouseout="this.style.background='rgba(255,255,255,0.03)'">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 0.9rem;">${statusIcon}</span>
                        <div>
                            <div style="font-weight: 600; font-size: 0.8rem; color: var(--text-primary);">${stock.code}</div>
                            <div style="font-size: 0.7rem; color: var(--text-secondary);">${stock.name}</div>
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 0.7rem; color: ${signalColor}; background: ${signalColor}20; padding: 2px 8px; border-radius: 4px;">${signalText}</span>
                        <span style="font-size: 0.7rem; color: var(--text-muted);">${stock.axis_deviation > 0 ? '+' : ''}${stock.axis_deviation.toFixed(1)}%</span>
                        <i class="fas fa-chevron-right" style="font-size: 0.65rem; color: var(--text-muted);"></i>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    // 5. 渲染板块分析
    const sectorCountEl = document.getElementById('portfolioSectorCount');
    const sectorItemsEl = document.getElementById('portfolioSectorItems');
    if (sectorItemsEl && data.sector_analysis) {
        const sectors = data.sector_analysis;
        if (sectorCountEl) sectorCountEl.textContent = `${sectors.length}个`;
        
        sectorItemsEl.innerHTML = sectors.map(sector => {
            const statusColor = sector.status?.includes('超买') || sector.status?.includes('过热') ? '#ef4444' : 
                               sector.status?.includes('超卖') ? '#10b981' : '#f59e0b';
            return `
                <div style="padding: 8px 10px; background: rgba(255,255,255,0.03); border-radius: 6px; margin-bottom: 6px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <span style="font-weight: 600; font-size: 0.8rem; color: var(--text-primary);">${sector.name}</span>
                        <span style="font-size: 0.7rem; color: ${statusColor};">${sector.status}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.7rem; color: var(--text-secondary);">
                        <span>${sector.stock_count}只</span>
                        <span>¥${(sector.market_value / 10000).toFixed(0)}万</span>
                        <span style="color: ${sector.pnl_percent >= 0 ? '#10b981' : '#ef4444'};">${sector.pnl_percent >= 0 ? '+' : ''}${sector.pnl_percent}%</span>
                    </div>
                </div>
            `;
        }).join('');
    }
}

// 显示个股分析详情弹窗
function showStockAnalysisDetail(code) {
    const data = appState.portfolioAnalysis;
    if (!data || !data.stock_analyses) return;
    
    const stockAnalysis = data.stock_analyses.find(s => s.code === code);
    if (!stockAnalysis) return;
    
    // 从 stocks 中获取完整的股票数据（包括价格、市场等）
    const stock = appState.stocks.find(s => s.code === code) || {};
    const isHK = stock.market === '港股';
    const currency = isHK ? 'HK$' : '¥';
    
    // 获取价格和轴价格
    const currentPrice = stock.price || stockAnalysis.current_price || 0;
    const pivotPrice = stock.pivotPrice || stockAnalysis.axis_price || 0;
    
    // 创建弹窗
    const modal = document.createElement('div');
    modal.className = 'modal active';
    modal.id = 'stockAnalysisDetailModal';
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 500px;">
            <div class="modal-header">
                <h3><i class="fas fa-chart-line"></i> ${stockAnalysis.name} (${stockAnalysis.code}) 分析报告</h3>
                <button class="btn-close" onclick="document.getElementById('stockAnalysisDetailModal').remove()"><i class="fas fa-times"></i></button>
            </div>
            <div class="modal-body" style="max-height: 70vh; overflow-y: auto;">
                <!-- 价格信息 -->
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px;">
                    <div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px;">
                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 4px;">当前价格</div>
                        <div style="font-size: 1.2rem; font-weight: 600; margin-top: 4px;">${currency}${currentPrice.toFixed(2)}</div>
                    </div>
                    <div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px;">
                        <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 4px;">中轴价格</div>
                        <div style="font-size: 1.2rem; font-weight: 600; margin-top: 4px;">${currency}${pivotPrice.toFixed(2)}</div>
                    </div>
                </div>
                
                <div style="margin-bottom: 16px;">
                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 4px;">健康度评分</div>
                    <div style="font-size: 1.5rem; font-weight: 700; color: ${stockAnalysis.health_score >= 80 ? '#10b981' : stockAnalysis.health_score >= 60 ? '#f59e0b' : '#ef4444'};">${stockAnalysis.health_score || '--'}/100</div>
                </div>
                
                ${stockAnalysis.analysis ? `
                <div style="background: rgba(255,255,255,0.05); padding: 12px; border-radius: 8px; margin-bottom: 12px;">
                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 6px;">📊 分析结论</div>
                    <div style="font-size: 0.85rem; color: var(--text-primary); line-height: 1.6;">${stockAnalysis.analysis}</div>
                </div>
                ` : ''}
                
                ${stockAnalysis.recommendation ? `
                <div style="background: rgba(16,185,129,0.1); padding: 12px; border-radius: 8px; margin-bottom: 12px; border-left: 3px solid #10b981;">
                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 4px;">💡 操作建议</div>
                    <div style="font-size: 0.9rem; font-weight: 600; color: ${stockAnalysis.signal === 'buy' ? '#10b981' : stockAnalysis.signal === 'sell' ? '#ef4444' : '#f59e0b'};">${stockAnalysis.recommendation}</div>
                </div>
                ` : ''}
                
                ${stockAnalysis.technical ? `
                <div style="margin-top: 16px; padding-top: 16px; border-top: 1px solid rgba(255,255,255,0.1);">
                    <div style="font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 8px;">📈 技术指标</div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.8rem;">
                        ${stockAnalysis.technical.ma ? `<div>均线: ${stockAnalysis.technical.ma}</div>` : ''}
                        ${stockAnalysis.technical.macd ? `<div>MACD: ${stockAnalysis.technical.macd}</div>` : ''}
                        ${stockAnalysis.technical.volume ? `<div>量能: ${stockAnalysis.technical.volume}</div>` : ''}
                    </div>
                </div>
                ` : ''}
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

// 加载持仓港股沽空风险分析
async function loadHKPortfolioRisk() {
    try {
        console.log('[DEBUG] loadHKPortfolioRisk 开始执行');
        const response = await fetch('/api/portfolio/hk-short-analysis');
        console.log('[DEBUG] API 响应状态:', response.status);
        if (!response.ok) {
            console.log('[DEBUG] API 响应不成功, 返回');
            return;
        }
        
        const data = await response.json();
        console.log('[DEBUG] API 返回数据:', data);
        if (!data.success) {
            console.log('[DEBUG] data.success 为 false, 返回');
            return;
        }
        
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
        
        // 变化趋势 - 使用与个股一致的维度：3天、1周、2周、1月
        const changes = marketShort.changes || {};
        console.log('[DEBUG] changes type:', typeof changes, 'keys:', Object.keys(changes));
        console.log('[DEBUG] changes[3d]:', changes['3d']);
        console.log('[DEBUG] changes[1w]:', changes['1w']);
        
        // 直接显示数值，不经过 formatChange
        const c3d = changes['3d'] || {};
        const c1w = changes['1w'] || {};
        const c2w = changes['2w'] || {};
        const c1m = changes['1m'] || {};
        
        document.getElementById('hkShort1W').textContent = (c3d.volume_change !== undefined && c3d.volume_change !== null) ? (c3d.volume_change >= 0 ? '+' : '') + c3d.volume_change + '万股' : '--';
        document.getElementById('hkShort1W').className = `metric-value ${(c3d.volume_change || 0) >= 0 ? 'down' : 'up'}`;
        
        document.getElementById('hkShort1M').textContent = (c1w.volume_change !== undefined && c1w.volume_change !== null) ? (c1w.volume_change >= 0 ? '+' : '') + c1w.volume_change + '万股' : '--';
        document.getElementById('hkShort1M').className = `metric-value ${(c1w.volume_change || 0) >= 0 ? 'down' : 'up'}`;
        
        document.getElementById('hkShort2W').textContent = (c2w.volume_change !== undefined && c2w.volume_change !== null) ? (c2w.volume_change >= 0 ? '+' : '') + c2w.volume_change + '万股' : '--';
        document.getElementById('hkShort2W').className = `metric-value ${(c2w.volume_change || 0) >= 0 ? 'down' : 'up'}`;
        
        document.getElementById('hkShort1Mo').textContent = (c1m.volume_change !== undefined && c1m.volume_change !== null) ? (c1m.volume_change >= 0 ? '+' : '') + c1m.volume_change + '万股' : '--';
        document.getElementById('hkShort1Mo').className = `metric-value ${(c1m.volume_change || 0) >= 0 ? 'down' : 'up'}`;
        
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
    
    // 确保DOM加载完成后再初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
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

// ========== 可折叠区域控制 ==========

/**
 * 切换区域的折叠/展开状态
 * @param {string} sectionId - 区域元素ID
 */
function toggleSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (!section) return;
    
    const isCollapsed = section.classList.toggle('collapsed');
    console.log(`[toggleSection] ${sectionId} ${isCollapsed ? '折叠' : '展开'}`);
    
    // 保存用户偏好到 localStorage
    const collapsedSections = JSON.parse(localStorage.getItem('collapsedSections') || '{}');
    collapsedSections[sectionId] = isCollapsed;
    localStorage.setItem('collapsedSections', JSON.stringify(collapsedSections));
}
window.toggleSection = toggleSection;

/**
 * 恢复用户的折叠偏好
 */
function restoreCollapsedState() {
    try {
        // 清除分析模块的折叠状态，确保默认展开
        const collapsedSections = JSON.parse(localStorage.getItem('collapsedSections') || '{}');
        delete collapsedSections['ibAnalysisSection'];
        delete collapsedSections['portfolioAnalysisSection'];
        localStorage.setItem('collapsedSections', JSON.stringify(collapsedSections));
        
        // 不再恢复这两个分析模块的折叠状态
        console.log('[restoreCollapsedState] 分析模块默认展开');
    } catch (e) {
        console.warn('[restoreCollapsedState] 恢复失败:', e);
    }
}
