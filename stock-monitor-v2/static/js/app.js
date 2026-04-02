/**
 * 股票投资监控系统 v3.0 - 重构版
 * 基于模块化架构，保持与v2.1完全兼容
 */

// 版本号
const APP_VERSION = "3.0.4-refactor";  // 重构版本

// 检查版本更新
const lastVersion = localStorage.getItem('app_version');
if (lastVersion !== APP_VERSION) {
    console.log(`[版本更新] ${lastVersion || '无版本'} -> ${APP_VERSION}`);
    localStorage.setItem('app_version', APP_VERSION);
}

// 导入模块（使用全局对象模式兼容旧浏览器）
// 模块已在各自文件中定义并挂载到window
const { 
    stateManager, 
    API, 
    southboundModule, 
    Utils,
    Renderers 
} = window;

// 兼容旧代码的全局状态（代理到stateManager）
const appState = new Proxy({}, {
    get(target, key) {
        return stateManager?.get(key);
    },
    set(target, key, value) {
        stateManager?.set(key, value);
        return true;
    }
});

// 挂载到window供旧代码访问
window.appState = appState;

// ==================== 初始化 ====================

let isInitialized = false;

async function init() {
    if (isInitialized) {
        console.log('[init] 已经初始化过，跳过');
        return;
    }
    
    console.log('[init] 系统初始化开始...');
    isInitialized = true;
    
    try {
        // 重置状态
        stateManager.reset();
        
        // 加载股票数据
        await loadStocks();
        
        // 初始化UI
        initUI();
        
        // 启动定时任务
        startTimers();
        
        // 加载市场数据
        loadMarketData();
        
        console.log('[init] 系统初始化完成');
        
    } catch (error) {
        console.error('[init] 初始化失败:', error);
    }
}

// 加载股票列表
async function loadStocks() {
    try {
        const stocks = await API.Stock.getAll();
        
        if (Array.isArray(stocks) && stocks.length > 0) {
            // 转换格式
            const formatted = stocks.map(s => ({
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
            
            stateManager.set('stocks', formatted);
            console.log(`[loadStocks] 加载 ${formatted.length} 只股票`);
            
            // 渲染列表
            Renderers.renderStockList(formatted, {
                onSelect: selectStock
            });
            
            // 获取实时行情
            await updateQuotes();
            
        } else {
            console.warn('[loadStocks] 没有股票数据');
        }
        
    } catch (error) {
        console.error('[loadStocks] 加载失败:', error);
    }
}

// 选择股票
function selectStock(stock, index) {
    console.log(`[selectStock] 选择: ${stock.code}`);
    
    // 更新状态
    stateManager.setSelectedStock(stock);
    
    // 更新UI选中状态
    document.querySelectorAll('.stock-item').forEach((el, i) => {
        el.classList.toggle('active', i === index);
    });
    
    // 渲染详情
    Renderers.renderStockList(stateManager.get('stocks'), {
        selectedCode: stock.code,
        onSelect: selectStock
    });
    
    Renderers.renderStockDetail(stock, {
        onLoadSouthbound: loadSouthboundData
    });
}

// 加载南向资金数据
async function loadSouthboundData(stockCode) {
    try {
        const result = await southboundModule.load(stockCode);
        if (result.success) {
            Renderers.renderSouthbound(result.data, stockCode);
        }
    } catch (error) {
        if (error.message !== 'Request superseded') {
            console.error('[loadSouthboundData] 加载失败:', error);
        }
    }
}

// 更新行情
async function updateQuotes() {
    const stocks = stateManager.get('stocks');
    if (!stocks || stocks.length === 0) return;
    
    return await stateManager.withLock('quotes', async () => {
        try {
            const codes = stocks.map(s => s.code);
            const quotes = await API.Quote.getBatch(codes);
            
            if (Array.isArray(quotes)) {
                quotes.forEach(quote => {
                    const stock = stocks.find(s => s.code === quote.code);
                    if (stock) {
                        stateManager.updateStock(quote.code, {
                            price: quote.price,
                            change: quote.change,
                            changePercent: quote.changePercent
                        });
                    }
                });
                
                // 重新渲染
                const selected = stateManager.getSelectedStock();
                Renderers.renderStockList(stateManager.get('stocks'), {
                    selectedCode: selected?.code,
                    onSelect: selectStock
                });
                
                if (selected) {
                    Renderers.renderStockDetail(selected);
                }
                
                Renderers.renderAssetOverview(8000000, stateManager.get('stocks'));
            }
            
        } catch (error) {
            console.error('[updateQuotes] 更新失败:', error);
        }
    });
}

// 初始化UI
function initUI() {
    // 绑定刷新按钮
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            updateQuotes();
        });
    }
}

// 启动定时器
function startTimers() {
    // 行情刷新（每30秒）
    setInterval(() => {
        updateQuotes();
    }, 30000);
    
    // 市场数据刷新（每5分钟）
    setInterval(() => {
        loadMarketData();
    }, 300000);
}

// 加载市场数据
async function loadMarketData() {
    try {
        // 热点板块
        const sectors = await API.Sentiment.getHotSectors();
        stateManager.set('hotSectors', sectors);
        
        // 市场情绪
        const sentiment = await API.Sentiment.get();
        stateManager.set('sentiment', sentiment);
        
        // 新闻
        const news = await API.News.get();
        stateManager.set('news', news);
        
    } catch (error) {
        console.error('[loadMarketData] 加载失败:', error);
    }
}

// ==================== 兼容旧代码的接口 ====================

// 保持与旧代码兼容的全局函数
window.renderStockList = function(stocks, options) {
    return Renderers.renderStockList(stocks || stateManager.get('stocks'), {
        ...options,
        onSelect: selectStock
    });
};

window.renderStockDetail = function(stock) {
    const s = stock || stateManager.getSelectedStock();
    if (s) {
        Renderers.renderStockDetail(s, {
            onLoadSouthbound: loadSouthboundData
        });
    }
};

window.loadSouthboundStockData = loadSouthboundData;

window.updateStockPricesOnce = updateQuotes;

window.init = init;

// ==================== 页面加载 ====================

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

console.log('[System] v3.0 重构版已加载');
