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
    
    const pnlElement = document.getElementById('todayPnL');
    const pnlValue = pnlElement.querySelector('.pnl-value');
    const pnlPercentEl = pnlElement.querySelector('.pnl-percent');
    
    pnlValue.textContent = (todayPnL >= 0 ? '+' : '') + formatMoney(todayPnL);
    pnlPercentEl.textContent = (todayPnL >= 0 ? '+' : '') + pnlPercent + '%';
    pnlPercentEl.className = 'pnl-percent ' + (todayPnL >= 0 ? '' : 'down');
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
    document.getElementById('addStockModal').classList.add('show');
}

// 隐藏添加股票弹窗
function hideAddStockModal() {
    document.getElementById('addStockModal').classList.remove('show');
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
    
    modal.classList.add('show');
}

// 确认交易
function confirmTrade() {
    document.getElementById('tradeAlertModal').classList.remove('show');
    addAlertLog('已确认交易操作');
}

// 稍后提醒
function snoozeAlert() {
    document.getElementById('tradeAlertModal').classList.remove('show');
    addAlertLog('已设置稍后提醒');
}

// 忽略提醒
function ignoreAlert() {
    document.getElementById('tradeAlertModal').classList.remove('show');
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

// 数据导入功能
function initDataImport() {
    console.log('开始初始化数据导入功能...');
    
    // 获取数据导入相关的DOM元素
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    
    console.log('获取到的元素:', { 
        uploadArea: uploadArea ? '找到' : '未找到', 
        fileInput: fileInput ? '找到' : '未找到'
    });
    
    // 绑定文件上传区域事件
    if (uploadArea && fileInput) {
        console.log('开始绑定上传区域事件...');
        
        // 点击上传区域触发文件选择
        uploadArea.addEventListener('click', (e) => {
            console.log('点击上传区域');
            if (e.target !== fileInput) {
                fileInput.click();
            }
        });
        
        // 文件选择事件
        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            console.log('文件选择事件触发:', file ? file.name : '无文件');
            if (file) {
                handleFileUpload(file);
            }
        });
        
        // 拖拽上传事件 - 使用捕获阶段确保事件被捕获
        uploadArea.addEventListener('dragenter', (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('dragenter事件触发');
            uploadArea.classList.add('dragover');
        }, true);
        
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            // 必须调用preventDefault才能允许drop
            if (e.dataTransfer) {
                e.dataTransfer.dropEffect = 'copy';
            }
        }, true);
        
        uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('dragleave事件触发');
            // 检查是否真的离开了uploadArea（而不是进入了子元素）
            if (!uploadArea.contains(e.relatedTarget)) {
                uploadArea.classList.remove('dragover');
            }
        }, true);
        
        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('drop事件触发');
            uploadArea.classList.remove('dragover');
            
            // 获取拖拽的文件
            const files = e.dataTransfer ? e.dataTransfer.files : null;
            console.log('拖拽的文件数量:', files ? files.length : 0);
            
            if (files && files.length > 0) {
                const file = files[0];
                console.log('拖拽的文件:', file.name, '类型:', file.type, '大小:', file.size);
                handleFileUpload(file);
            } else {
                console.error('没有获取到文件');
                alert('未能获取到文件，请重试');
            }
        }, true);
        
        console.log('上传区域事件绑定完成');
    } else {
        console.error('uploadArea或fileInput元素未找到');
    }
    
    // 绑定导入标签页切换
    const importTabs = document.querySelectorAll('.import-tab');
    importTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchImportTab(tabName);
        });
    });
    
    console.log('数据导入初始化完成');
}

// 处理文件上传
function handleFileUpload(file) {
    if (!file.name.endsWith('.txt')) {
        alert('请上传记事本格式的.txt文件');
        return;
    }
    
    const reader = new FileReader();
    reader.onload = (e) => {
        const content = e.target.result;
        parseStockData(content);
    };
    reader.readAsText(file, 'GBK'); // 券商导出文件通常是GBK编码
}

// 解析持仓数据（适配券商导出格式）
function parseStockData(content) {
    // 使用GBK编码读取（券商软件通常使用GBK）
    const lines = content.split('\n');
    const stocks = [];
    let isDataSection = false;
    let headers = [];
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        
        // 跳过空行和分隔线
        if (!line || line.includes('---') || line.includes('===')) continue;
        
        // 检测表头行
        if (line.includes('证券代码') && line.includes('证券名称')) {
            isDataSection = true;
            headers = line.split(/\s+/);
            continue;
        }
        
        // 解析数据行（以数字开头的行）
        if (isDataSection && /^\d/.test(line)) {
            const stock = parseStockLine(line);
            if (stock) stocks.push(stock);
        }
    }
    
    if (stocks.length > 0) {
        updateStocksFromImport(stocks);
        alert(`成功导入 ${stocks.length} 只股票数据！\n\n已更新持仓信息和中轴价格。`);
        addAlertLog(`导入持仓数据：${stocks.length}只股票`);
    } else {
        alert('未能解析到股票数据，请检查文件格式是否为券商导出的持仓查询文件');
    }
}

// 显示数据导入弹窗
function showDataImportModal() {
    const modal = document.getElementById('dataImportModal');
    if (modal) {
        modal.classList.add('active');
        console.log('显示数据导入弹窗');
    } else {
        console.error('找不到dataImportModal元素');
    }
}

// 隐藏数据导入弹窗
function hideDataImportModal() {
    const modal = document.getElementById('dataImportModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

// 显示数据分析弹窗
function showAnalysisModal() {
    const modal = document.getElementById('analysisModal');
    if (modal) {
        modal.classList.add('active');
        console.log('显示数据分析弹窗');
    } else {
        console.error('找不到analysisModal元素');
    }
}

// 隐藏数据分析弹窗
function hideAnalysisModal() {
    const modal = document.getElementById('analysisModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

// 切换导入标签页
function switchImportTab(tabName) {
    // 更新标签按钮状态
    document.querySelectorAll('.import-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });
    
    // 更新内容区域显示
    document.querySelectorAll('.import-content').forEach(content => {
        content.classList.remove('active');
    });
    
    const targetContent = document.getElementById(tabName + 'Tab');
    if (targetContent) {
        targetContent.classList.add('active');
    }
}

// 清除已选文件
function clearFile() {
    const fileInput = document.getElementById('fileInput');
    const filePreview = document.getElementById('filePreview');
    const uploadArea = document.getElementById('uploadArea');
    
    if (fileInput) fileInput.value = '';
    if (filePreview) filePreview.style.display = 'none';
    if (uploadArea) uploadArea.style.display = 'block';
}
function parseStockLine(line) {
    try {
        // 按空白字符分割
        const parts = line.trim().split(/\s+/);
        if (parts.length < 10) return null;
        
        // 提取字段（根据实际格式）
        const code = parts[0];
        const name = parts[1];
        const shares = parseInt(parts[2]) || 0;  // 证券数量
        const costPrice = parseFloat(parts[5]) || 0;  // 参考成本价
        const currentPrice = parseFloat(parts[6]) || 0;  // 当前价
        const marketValue = parseFloat(parts[7]) || 0;  // 最新市值
        const pnl = parseFloat(parts[8]) || 0;  // 浮动盈亏
        const pnlPercent = parseFloat(parts[9]) || 0;  // 盈亏比例
        const exchange = parts[14] || '';  // 交易所名称
        
        // 判断市场类型
        let market = 'A股';
        if (exchange.includes('港股') || exchange.includes('沪港通') || exchange.includes('深港通')) {
            market = '港股';
        } else if (code.length === 5) {
            market = '港股';
        }
        
        // 处理异常成本价（如比亚迪的-1912.943可能是送转股后未调整）
        let validCostPrice = costPrice;
        if (costPrice <= 0 || costPrice > currentPrice * 10) {
            // 如果成本价异常，使用当前价的90%作为估算
            validCostPrice = currentPrice * 0.9;
        }
        
        // 计算中轴价格
        const pivotPrice = validCostPrice > 0 ? validCostPrice : currentPrice;
        
        // 确定投资上限
        const investLimit = market === '港股' ? 1500000 : 500000;
        
        return {
            code: code,
            name: name,
            market: market,
            price: currentPrice,
            change: 0,
            changePercent: 0,
            investLimit: investLimit,
            holdQuantity: shares,
            holdCost: validCostPrice,
            strategy: '基础',
            pivotPrice: pivotPrice,
            baseRatio: 50,
            floatRatio: 50,
            triggerBuy: pivotPrice * 0.92,
            triggerSell: pivotPrice * 1.08,
            stopLoss: pivotPrice * 0.85,  // 止损线设为-15%
            marketValue: marketValue,
            pnl: pnl,
            pnlPercent: pnlPercent
        };
    } catch (e) {
        console.error('解析股票数据失败:', e, '行内容:', line);
        return null;
    }
}

// 更新股票数据
function updateStocksFromImport(newStocks) {
    // 合并或替换现有数据
    newStocks.forEach(newStock => {
        const existingIndex = appState.stocks.findIndex(s => s.code === newStock.code);
        if (existingIndex >= 0) {
            // 更新现有股票
            appState.stocks[existingIndex] = { ...appState.stocks[existingIndex], ...newStock };
        } else {
            // 添加新股票
            appState.stocks.push(newStock);
        }
    });
    
    // 重新渲染
    renderStockList();
    updateAssetOverview();
    
    // 默认选中第一个
    if (appState.stocks.length > 0) {
        selectStock(0);
    }
}

// 数据分析
function analyzeData() {
    if (appState.stocks.length === 0) {
        alert('请先导入持仓数据');
        return;
    }
    
    const totalValue = appState.stocks.reduce((sum, s) => sum + (s.price * s.holdQuantity), 0);
    const totalCost = appState.stocks.reduce((sum, s) => sum + (s.holdCost * s.holdQuantity), 0);
    const totalPnl = totalValue - totalCost;
    const pnlPercent = (totalPnl / totalCost * 100).toFixed(2);
    
    const aStocks = appState.stocks.filter(s => s.market === 'A股');
    const hkStocks = appState.stocks.filter(s => s.market === '港股');
    
    alert(`持仓分析报告：

总持仓市值：${(totalValue/10000).toFixed(2)}万
总持仓成本：${(totalCost/10000).toFixed(2)}万
浮动盈亏：${totalPnl >= 0 ? '+' : ''}${(totalPnl/10000).toFixed(2)}万 (${pnlPercent}%)

A股持仓：${aStocks.length}只
港股持仓：${hkStocks.length}只

建议：${totalPnl < 0 ? '当前整体亏损，建议关注止损线' : '当前整体盈利，可考虑适当止盈'}`);
}

// 查看历史
function viewHistory() {
    alert('历史记录功能开发中...\n\n将记录每日持仓变化、交易操作、盈亏走势等数据。');
}

// 显示数据分析弹窗
function showAnalysisModal() {
    analyzeData();
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    init();
    // 数据导入功能在import.js中初始化
    if (typeof initDataImport === 'function') {
        initDataImport();
    }
});

// 确保函数在全局作用域可用（用于HTML内联事件）
window.showDataImportModal = showDataImportModal;
window.hideDataImportModal = hideDataImportModal;
window.showAnalysisModal = showAnalysisModal;
window.hideAnalysisModal = hideAnalysisModal;
window.handleFileUpload = handleFileUpload;
window.clearFile = clearFile;
window.switchImportTab = switchImportTab;
window.analyzeData = analyzeData;
window.viewHistory = viewHistory;
