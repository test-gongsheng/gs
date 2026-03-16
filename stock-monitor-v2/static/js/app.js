/**
 * 股票投资监控系统 v2.1 - 前端逻辑
 * 版本: 2026-03-16 - 添加自动刷新中轴价格功能
 */

// 版本号，用于强制刷新缓存
const APP_VERSION = '2.1.0';

// 全局状态
const appState = {
    stocks: [],
    selectedStock: null,
    hotSectors: [],
    news: [],
    alerts: [],
    totalAssets: 8000000, // 800万
    marketStatus: 'closed',
    version: APP_VERSION
};

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
    // 尝试从 localStorage 读取上次导入的数据
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
    setInterval(simulatePriceUpdate, 3000);

    // 绑定表单提交
    document.getElementById('addStockForm').addEventListener('submit', handleAddStock);
    
    // 页面加载完成后，异步重新计算中轴价格（确保数据最新）
    if (appState.stocks.length > 0) {
        console.log('开始异步刷新中轴价格...');
        await refreshAxisPrices();
    }
}

/**
 * 刷新所有股票的中轴价格
 */
async function refreshAxisPrices() {
    if (appState.stocks.length === 0) {
        if (typeof showNotification === 'function') {
            showNotification('没有持仓数据，请先导入', 'warning');
        }
        return;
    }
    
    console.log('正在重新计算中轴价格...');
    if (typeof showNotification === 'function') {
        showNotification('正在重新计算中轴价格，请稍候...', 'info');
    }
    
    let updatedCount = 0;
    let failedCount = 0;
    let changedStocks = [];
    
    const updatePromises = appState.stocks.map(async (stock) => {
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
            
            if (axisData.success && axisData.data) {
                const oldPivot = parseFloat(stock.pivotPrice) || 0;
                const newPivot = axisData.data.axis_price;
                
                stock.pivotPrice = newPivot;
                stock.triggerBuy = axisData.data.trigger_buy;
                stock.triggerSell = axisData.data.trigger_sell;
                
                // 如果中轴价格有显著变化，记录下来
                if (Math.abs(oldPivot - newPivot) > 0.1) {
                    console.log(`${stock.code} 中轴价格更新: ${oldPivot.toFixed(2)} -> ${newPivot.toFixed(2)}`);
                    changedStocks.push({
                        code: stock.code,
                        name: stock.name,
                        oldPrice: oldPivot,
                        newPrice: newPivot
                    });
                }
                updatedCount++;
                return true;
            } else {
                console.warn(`${stock.code} 获取中轴价格失败:`, axisData.error || '未知错误');
                failedCount++;
                return false;
            }
        } catch (error) {
            console.warn(`${stock.code} 获取中轴价格异常:`, error.message);
            failedCount++;
            return false;
        }
    });
    
    // 等待所有更新完成
    await Promise.all(updatePromises);
    
    console.log(`中轴价格刷新完成: ${updatedCount} 只成功, ${failedCount} 只失败`);
    
    // 更新localStorage中的数据
    localStorage.setItem('import_data_last', JSON.stringify(appState.stocks));
    
    // 重新渲染页面
    renderStockList();
    if (appState.selectedStock) {
        const selected = appState.stocks.find(s => s.code === appState.selectedStock.code);
        if (selected) {
            appState.selectedStock = selected;
            renderStockDetail();
        }
    }
    updateAssetOverview();
    
    // 显示结果通知
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
    // 同时支持A股和港股，取并集：9:30-11:30, 13:00-16:00
    const isTrading = (timeValue >= 930 && timeValue <= 1130) ||
                      (timeValue >= 1300 && timeValue <= 1600);

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
        const isHKStock = stock.market === '港股';
        let marketValue, costValue;
        
        if (isHKStock) {
            // 港股：使用昨日收盘汇率（导入时记录的固定汇率）
            const exchangeRate = stock.exchangeRate || appState.exchangeRate || 1.1339;
            // 实时计算港币市值，转换为人民币
            const hkdValue = (stock.price || 0) * (stock.holdQuantity || 0);
            marketValue = hkdValue / exchangeRate;
            costValue = (stock.holdCost || 0) * (stock.holdQuantity || 0); // holdCost 已是人民币
        } else {
            // A股：直接计算人民币市值
            marketValue = (stock.price || 0) * (stock.holdQuantity || 0);
            costValue = (stock.holdCost || 0) * (stock.holdQuantity || 0);
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
        let marketValue;
        if (isHKStock) {
            const hkdValue = (stock.price || 0) * (stock.holdQuantity || 0);
            marketValue = hkdValue / exchangeRate; // 汇率是1人民币=X港币
        } else {
            marketValue = (stock.price || 0) * (stock.holdQuantity || 0);
        }
        
        const marketValueWan = marketValue > 0 ? (marketValue / 10000).toFixed(1) : '0.0';

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
                    ${isHKStock ? stock.price.toFixed(2) + ' HKD' : stock.price.toFixed(2)}
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
        positionShares = stock.holdQuantity || 0;
        positionValueHkd = stock.price * positionShares; // 港币市值
        marketValue = positionValueHkd / yesterdayRate;   // 转换为人民币（汇率是1人民币=X港币）
        
        // 持仓成本是导入的人民币成本，无需转换
        const holdCostCny = stock.holdCost || 0;
        costValue = holdCostCny * positionShares; // 人民币成本
        
        pnl = marketValue - costValue; // 人民币盈亏
        pnlPercent = costValue > 0 ? (pnl / costValue * 100) : 0;
    } else {
        // A股：都是人民币，实时计算
        positionShares = stock.holdQuantity || 0;
        marketValue = stock.price * positionShares;
        costValue = stock.holdCost * positionShares;
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
    setText('detailStrategy', stock.strategy + '策略');

    // 港股显示实时港币价格
    if (isHKStock) {
        setText('detailPrice', `${stock.price.toFixed(2)} HKD`);
    } else {
        setText('detailPrice', stock.price.toFixed(2));
    }

    const detailPriceEl = document.getElementById('detailPrice');
    if (detailPriceEl) detailPriceEl.className = 'current-price ' + (isUp ? 'up' : 'down');

    const detailChangeEl = document.getElementById('detailChange');
    if (detailChangeEl) {
        detailChangeEl.textContent = `${isUp ? '+' : ''}${stock.change.toFixed(2)} (${isUp ? '+' : ''}${stock.changePercent.toFixed(2)}%)`;
        detailChangeEl.className = 'price-change ' + (isUp ? 'up' : 'down');
    }

    // 策略卡片
    setText('detailLimit', formatMoney(stock.investLimit));
    
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

    // 调试中轴价格
    console.log('中轴价格调试:', stock.code, 'pivotPrice=', stock.pivotPrice, 'type=', typeof stock.pivotPrice);

    // 中轴价格：港股显示港币中轴价格，A股显示人民币中轴价格
    let pivotPriceValue = parseFloat(stock.pivotPrice) || 0;
    
    // 如果是港股且中轴价格看起来像是人民币（比当前价格低很多），需要转换
    // 正常情况下 API 返回的中轴价格是基于港币K线计算的
    if (isHKStock && pivotPriceValue > 0 && stock.price > 0) {
        // 检查中轴价格是否可能是人民币值
        // holdCost 是导入的人民币成本
        const holdCostCny = stock.holdCost || 0;
        const holdCostHkd = holdCostCny * exchangeRate; // 人民币成本换算成港币
        
        // 如果 pivotPrice 接近人民币成本价，但偏离港币成本价，说明 pivotPrice 可能是人民币值
        if (Math.abs(pivotPriceValue - holdCostCny) < 1 && Math.abs(pivotPriceValue - holdCostHkd) > 10) {
            // pivotPrice 可能是人民币值，转换为港币
            console.log('中轴价格疑似人民币值，转换为港币:', pivotPriceValue, '->', (pivotPriceValue / exchangeRate).toFixed(2));
            pivotPriceValue = pivotPriceValue / exchangeRate;
        }
    }

    // 策略卡片中的中轴价格
    const detailPivotEl = document.getElementById('detailPivot');
    console.log('detailPivot元素:', detailPivotEl);
    if (detailPivotEl) {
        if (isHKStock) {
            detailPivotEl.textContent = pivotPriceValue.toFixed(2) + ' HKD';
        } else {
            detailPivotEl.textContent = pivotPriceValue.toFixed(2);
        }
        console.log('已设置中轴价格为:', pivotPriceValue.toFixed(2), isHKStock ? 'HKD' : 'CNY');
    } else {
        console.error('找不到detailPivot元素');
    }

    // 中轴价格可视化区域的中轴价格
    const pivotCenterEl = document.getElementById('pivotCenter');
    if (pivotCenterEl) {
        pivotCenterEl.textContent = pivotPriceValue.toFixed(2);
        console.log('已设置可视化区域中轴价格为:', pivotPriceValue.toFixed(2));
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
window.refreshAxisPrices = refreshAxisPrices;
