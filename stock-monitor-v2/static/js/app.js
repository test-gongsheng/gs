/**
 * 股票投资监控系统 v2.0 - 前端逻辑
 */

// 全局状态
const appState = {
    stocks: [],
    selectedStock: null,
    hotSectors: [],
    news: [],
    alerts: [],
    totalAssets: 8000000, // 800万
    marketStatus: 'closed'
};

// 模拟数据 - 实际开发时从后端API获取
const mockStocks = [
    {
        code: '09988.HK',
        name: '阿里巴巴-W',
        market: '港股',
        price: 110.50,
        change: 5.2,
        changePercent: 4.94,
        investLimit: 1000000,
        holdQuantity: 8000,
        holdCost: 87.50,
        strategy: '进阶',
        pivotPrice: 95,
        baseRatio: 60,
        floatRatio: 40,
        triggerBuy: 83.12,
        triggerSell: 94.50
    },
    {
        code: '000001.SZ',
        name: '平安银行',
        market: 'A股',
        price: 12.35,
        change: -0.15,
        changePercent: -1.20,
        investLimit: 500000,
        holdQuantity: 20000,
        holdCost: 11.80,
        strategy: '基础',
        pivotPrice: 12.00,
        baseRatio: 50,
        floatRatio: 50,
        triggerBuy: 11.04,
        triggerSell: 12.96
    },
    {
        code: '00700.HK',
        name: '腾讯控股',
        market: '港股',
        price: 385.20,
        change: 8.40,
        changePercent: 2.23,
        investLimit: 1500000,
        holdQuantity: 3000,
        holdCost: 360.00,
        strategy: '基础',
        pivotPrice: 375.00,
        baseRatio: 50,
        floatRatio: 50,
        triggerBuy: 345.00,
        triggerSell: 405.00
    }
];

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
function init() {
    appState.stocks = mockStocks;
    appState.hotSectors = mockHotSectors;
    appState.news = mockNews;
    
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
    setInterval(simulatePriceUpdate, 5000);
    
    // 绑定表单提交
    document.getElementById('addStockForm').addEventListener('submit', handleAddStock);
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
    const timeValue = hour * 100 + minute;
    
    // A股交易时间：9:30-11:30, 13:00-15:00
    // 港股交易时间：9:30-12:00, 13:00-16:00
    const isTrading = (timeValue >= 930 && timeValue <= 1130) || 
                      (timeValue >= 1300 && timeValue <= 1500);
    
    appState.marketStatus = isTrading ? 'open' : 'closed';
    
    const dot = document.getElementById('marketStatusDot');
    const text = document.getElementById('marketStatusText');
    
    if (isTrading) {
        dot.style.background = '#4caf50';
        text.textContent = '交易中';
    } else {
        dot.style.background = '#f44336';
        text.textContent = '休市中';
    }
}

// 更新资产概览
function updateAssetOverview() {
    let totalPosition = 0;
    let todayPnL = 0;
    
    appState.stocks.forEach(stock => {
        const marketValue = stock.price * stock.holdQuantity;
        const costValue = stock.holdCost * stock.holdQuantity;
        totalPosition += marketValue;
        todayPnL += (marketValue - costValue) * (stock.changePercent / 100);
    });
    
    const availableCash = appState.totalAssets - totalPosition;
    const pnlPercent = (todayPnL / totalPosition * 100).toFixed(2);
    
    document.getElementById('totalPosition').textContent = formatMoney(totalPosition);
    document.getElementById('availableCash').textContent = formatMoney(availableCash);
    
    const pnlValueEl = document.getElementById('todayPnLValue');
    const pnlPercentEl = document.getElementById('todayPnLPercent');
    
    if (pnlValueEl) pnlValueEl.textContent = (todayPnL >= 0 ? '+' : '') + formatMoney(todayPnL);
    if (pnlPercentEl) {
        pnlPercentEl.textContent = (todayPnL >= 0 ? '+' : '') + pnlPercent + '%';
        pnlPercentEl.className = 'pnl-percent ' + (todayPnL >= 0 ? '' : 'down');
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
        const marketValue = (stock.price * stock.holdQuantity / 10000).toFixed(1);
        
        // 检查是否触发买卖
        let alertBadge = '';
        if (stock.price >= stock.triggerSell) {
            alertBadge = '<span class="stock-item-alert sell">卖</span>';
        } else if (stock.price <= stock.triggerBuy) {
            alertBadge = '<span class="stock-item-alert buy">买</span>';
        }
        
        item.innerHTML = `
            <div class="stock-item-header">
                <div>
                    <span class="stock-item-name">${stock.name}</span>
                    <span class="stock-item-code">${stock.code}</span>
                    ${alertBadge}
                </div>
                <div class="stock-item-price ${isUp ? 'up' : 'down'}">
                    ${stock.price.toFixed(2)}
                </div>
            </div>
            <div class="stock-item-info">
                <span>${stock.change >= 0 ? '+' : ''}${stock.changePercent.toFixed(2)}%</span>
                <span>持仓: ${marketValue}万</span>
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
    const marketValue = stock.price * stock.holdQuantity;
    const costValue = stock.holdCost * stock.holdQuantity;
    const pnl = marketValue - costValue;
    const pnlPercent = (pnl / costValue * 100).toFixed(2);
    
    // 基础信息
    document.getElementById('detailName').textContent = stock.name;
    document.getElementById('detailCode').textContent = stock.code;
    document.getElementById('detailStrategy').textContent = stock.strategy + '策略';
    document.getElementById('detailPrice').textContent = stock.price.toFixed(2);
    document.getElementById('detailPrice').className = 'current-price ' + (isUp ? 'up' : 'down');
    document.getElementById('detailChange').textContent = 
        `${isUp ? '+' : ''}${stock.change.toFixed(2)} (${isUp ? '+' : ''}${stock.changePercent.toFixed(2)}%)`;
    document.getElementById('detailChange').className = 'price-change ' + (isUp ? 'up' : 'down');
    
    // 策略卡片
    document.getElementById('detailLimit').textContent = formatMoney(stock.investLimit);
    document.getElementById('detailPosition').textContent = formatMoney(marketValue);
    document.getElementById('detailPnL').textContent = 
        `${pnl >= 0 ? '+' : ''}${formatMoney(pnl)} (${pnlPercent}%)`;
    document.getElementById('detailPnL').style.color = pnl >= 0 ? 'var(--up-color)' : 'var(--down-color)';
    document.getElementById('detailPivot').textContent = stock.pivotPrice.toFixed(2);
    document.getElementById('detailBase').textContent = stock.baseRatio + '%';
    document.getElementById('detailFloat').textContent = stock.floatRatio + '%';
    
    // 触发价格
    document.getElementById('triggerBuy').textContent = stock.triggerBuy.toFixed(2);
    document.getElementById('triggerSell').textContent = stock.triggerSell.toFixed(2);
    
    const distBuy = ((stock.price - stock.triggerBuy) / stock.triggerBuy * 100).toFixed(1);
    const distSell = ((stock.triggerSell - stock.price) / stock.price * 100).toFixed(1);
    document.getElementById('distanceBuy').textContent = `距触发 ${distBuy}%`;
    document.getElementById('distanceSell').textContent = `距触发 ${distSell}%`;
    
    // 进度条
    const progress = ((stock.price - stock.triggerBuy) / (stock.triggerSell - stock.triggerBuy) * 100);
    document.getElementById('markerCurrent').style.left = Math.max(0, Math.min(100, progress)) + '%';
    
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
    document.getElementById('suggestionContent').textContent = suggestion;
}

// 渲染热点板块
function renderHotSectors() {
    const listEl = document.getElementById('hotSectors');
    listEl.innerHTML = '';
    
    appState.hotSectors.forEach((sector, index) => {
        const item = document.createElement('div');
        item.className = 'sector-item';
        item.innerHTML = `
            <div>
                <span class="sector-rank">${index + 1}</span>
                <span class="sector-name">${sector.name}</span>
            </div>
            <span class="sector-change up">+${sector.change}%</span>
        `;
        listEl.appendChild(item);
    });
}

// 渲染新闻
function renderNews() {
    const listEl = document.getElementById('newsList');
    listEl.innerHTML = '';
    
    appState.news.forEach(news => {
        const item = document.createElement('div');
        item.className = 'news-item';
        item.innerHTML = `
            <div class="news-time">${news.time}</div>
            <div class="news-title">${news.title}</div>
            <span class="news-tag ${news.tag}">${news.tag === 'important' ? '重要' : '一般'}</span>
        `;
        listEl.appendChild(item);
    });
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
function simulatePriceUpdate() {
    appState.stocks.forEach(stock => {
        const change = (Math.random() - 0.5) * 0.5;
        stock.price += change;
        stock.change += change;
        stock.changePercent = (stock.change / (stock.price - stock.change) * 100);
        
        // 检查是否触发买卖提醒
        if (stock.price >= stock.triggerSell || stock.price <= stock.triggerBuy) {
            showTradeAlert(stock);
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

// 显示买卖提醒
function showTradeAlert(stock) {
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
    const time = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    logEl.innerHTML = `[${time}] ${message}`;
}

// 格式化金额
function formatMoney(amount) {
    if (amount >= 100000000) {
        return (amount / 100000000).toFixed(2) + '亿';
    } else if (amount >= 10000) {
        return (amount / 10000).toFixed(1) + '万';
    } else {
        return amount.toFixed(2);
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
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
