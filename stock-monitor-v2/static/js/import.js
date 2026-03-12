/**
 * 数据导入功能 - 增强版
 * 支持：文件上传预览、手动录入、导入历史、多券商格式识别
 */

// 导入历史存储键
const IMPORT_HISTORY_KEY = 'stock_import_history';
const MAX_HISTORY_ITEMS = 10;

// 当前待导入的数据
let pendingImportData = null;

/**
 * 初始化数据导入模块
 */
function initDataImport() {
    console.log('初始化数据导入模块...');
    
    initFileUpload();
    initManualInput();
    initImportHistory();
    initTemplateDownload();
    
    console.log('数据导入模块初始化完成');
}

/**
 * 初始化文件上传功能
 */
function initFileUpload() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    
    if (!uploadArea || !fileInput) {
        console.error('找不到上传相关元素');
        return;
    }
    
    // 点击上传
    uploadArea.onclick = function(e) {
        if (e.target.tagName !== 'INPUT' && !e.target.closest('.preview-content')) {
            fileInput.click();
        }
    };
    
    // 文件选择
    fileInput.onchange = function(e) {
        const file = e.target.files[0];
        if (file) processFile(file);
    };
    
    // 拖拽事件
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });
    
    ['dragenter', 'dragover'].forEach(eventName => {
        uploadArea.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, unhighlight, false);
    });
    
    uploadArea.addEventListener('drop', handleDrop, false);
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight(e) {
        uploadArea.classList.add('dragover');
    }
    
    function unhighlight(e) {
        uploadArea.classList.remove('dragover');
    }
    
    function handleDrop(e) {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            processFile(files[0]);
        }
    }
}

/**
 * 处理文件
 */
function processFile(file) {
    console.log('处理文件:', file.name, '类型:', file.type, '大小:', file.size);
    
    // 检查文件类型
    const validTypes = ['.txt', '.csv', '.xls', '.xlsx'];
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    
    if (!validTypes.includes(ext)) {
        showNotification('不支持的文件格式，请上传 .txt、.csv 或 Excel 文件', 'error');
        return;
    }
    
    // 检查文件大小 (限制10MB)
    if (file.size > 10 * 1024 * 1024) {
        showNotification('文件过大，请上传小于10MB的文件', 'error');
        return;
    }
    
    const reader = new FileReader();
    
    reader.onload = function(e) {
        const content = e.target.result;
        try {
            const result = parseStockData(content, file.name);
            if (result.success && result.stocks.length > 0) {
                pendingImportData = {
                    fileName: file.name,
                    stocks: result.stocks,
                    stats: result.stats,
                    timestamp: new Date().toISOString()
                };
                showFilePreview(pendingImportData);
                enableConfirmButton(true);
                showNotification(`成功解析 ${result.stocks.length} 只股票`, 'success');
            } else {
                showNotification(result.error || '未能解析到股票数据', 'error');
            }
        } catch (err) {
            console.error('解析文件出错:', err);
            showNotification('文件解析失败，请检查格式是否正确', 'error');
        }
    };
    
    reader.onerror = function() {
        showNotification('文件读取失败', 'error');
    };
    
    // 根据编码读取
    if (ext === '.txt') {
        reader.readAsText(file, 'GBK');
    } else {
        reader.readAsText(file, 'UTF-8');
    }
}

/**
 * 解析股票数据 - 支持多种券商格式
 */
function parseStockData(content, fileName) {
    const lines = content.split('\n').filter(line => line.trim());
    const stocks = [];
    let stats = {
        totalMarketValue: 0,
        totalCost: 0,
        aShareCount: 0,
        hkShareCount: 0,
        profitCount: 0,
        lossCount: 0
    };
    
    // 检测格式类型
    const formatType = detectFormat(lines);
    console.log('检测到格式类型:', formatType);
    
    let headerFound = false;
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        
        // 跳过空行和分隔线
        if (!line || line.match(/^[-=]+$/)) continue;
        
        // 检测表头
        if (!headerFound && (
            line.includes('证券代码') || 
            line.includes('股票代码') ||
            line.includes('代码')
        )) {
            headerFound = true;
            continue;
        }
        
        // 解析数据行
        if (headerFound || formatType === 'simple') {
            const stock = parseStockLine(line, formatType);
            if (stock) {
                // 计算市值和盈亏
                const marketValue = stock.currentPrice * stock.shares;
                const costValue = stock.costPrice * stock.shares;
                const pnl = marketValue - costValue;
                
                stock.marketValue = marketValue;
                stock.pnl = pnl;
                stock.pnlPercent = costValue > 0 ? (pnl / costValue * 100) : 0;
                
                // 计算中轴价格和触发价
                stock.pivotPrice = stock.costPrice > 0 ? stock.costPrice : stock.currentPrice;
                stock.triggerBuy = stock.pivotPrice * 0.92;
                stock.triggerSell = stock.pivotPrice * 1.08;
                stock.investLimit = stock.market === '港股' ? 1500000 : 500000;
                stock.strategy = '基础';
                stock.baseRatio = 50;
                stock.floatRatio = 50;
                
                stocks.push(stock);
                
                // 更新统计
                stats.totalMarketValue += marketValue;
                stats.totalCost += costValue;
                if (stock.market === '港股') {
                    stats.hkShareCount++;
                } else {
                    stats.aShareCount++;
                }
                if (pnl >= 0) {
                    stats.profitCount++;
                } else {
                    stats.lossCount++;
                }
            }
        }
    }
    
    if (stocks.length === 0) {
        return { success: false, error: '未能解析到股票数据，请检查文件格式' };
    }
    
    return { success: true, stocks, stats };
}

/**
 * 检测数据格式类型
 */
function detectFormat(lines) {
    for (const line of lines) {
        // 同花顺格式
        if (line.includes('证券代码') && line.includes('证券数量')) {
            return 'ths';
        }
        // 东方财富格式
        if (line.includes('股票代码') && line.includes('持仓数量')) {
            return 'eastmoney';
        }
        // 通达信格式
        if (line.includes('代码') && line.includes('名称') && line.includes('数量')) {
            return 'tdx';
        }
    }
    return 'simple';
}

/**
 * 解析单行股票数据
 */
function parseStockLine(line, formatType) {
    try {
        // 清理行内容
        line = line.replace(/"/g, '').trim();
        const parts = line.split(/\s+|,/); // 支持空格或逗号分隔
        
        if (parts.length < 3) return null;
        
        // 第一个字段应该是代码（数字开头）
        const firstPart = parts[0].trim();
        if (!/^\d/.test(firstPart)) return null;
        
        // 提取基本信息
        let code = firstPart;
        let name = parts[1] || '';
        let shares = 0;
        let costPrice = 0;
        let currentPrice = 0;
        let exchange = '';
        
        // 根据不同格式解析
        let marketValue = 0;
        if (formatType === 'ths' || parts.length >= 10) {
            // 同花顺格式: 代码 名称 数量 可用 冻结 成本价 当前价 市值 盈亏 盈亏率 代码
            shares = parseInt(parts[2]) || 0;
            costPrice = parseFloat(parts[5]) || 0;
            currentPrice = parseFloat(parts[6]) || 0;
            marketValue = parseFloat(parts[7]) || 0;  // 最新市值
            exchange = parts[parts.length - 1] || '';
        } else if (formatType === 'eastmoney') {
            // 东方财富格式
            shares = parseInt(parts[2]) || 0;
            costPrice = parseFloat(parts[3]) || 0;
            currentPrice = parseFloat(parts[4]) || 0;
        } else {
            // 简单格式: 尝试自动识别数值字段
            const numbers = parts.slice(2).map(p => parseFloat(p.replace(/,/g, ''))).filter(n => !isNaN(n));
            if (numbers.length >= 1) shares = numbers[0];
            if (numbers.length >= 2) costPrice = numbers[1];
            if (numbers.length >= 3) currentPrice = numbers[2];
        }
        
        // 判断市场类型
        let market = 'A股';
        if (exchange.includes('港股') || exchange.includes('沪港通') || exchange.includes('深港通') || code.length === 5) {
            market = '港股';
        }
        
        // 处理异常成本价
        if (costPrice <= 0 || costPrice > currentPrice * 10) {
            costPrice = currentPrice * 0.9; // 估算成本
        }
        
        return {
            code,
            name,
            market,
            shares,
            costPrice,
            currentPrice,
            marketValue  // 券商提供的最新市值
        };
    } catch (e) {
        console.error('解析行失败:', line, e);
        return null;
    }
}

/**
 * 显示文件预览
 */
function showFilePreview(data) {
    const uploadArea = document.getElementById('uploadArea');
    const filePreview = document.getElementById('filePreview');
    const previewFileName = document.getElementById('previewFileName');
    const previewTable = document.getElementById('previewTable');
    const previewStats = document.getElementById('previewStats');
    
    if (!uploadArea || !filePreview) return;
    
    // 隐藏上传区域，显示预览
    uploadArea.style.display = 'none';
    filePreview.style.display = 'block';
    
    // 显示文件名
    if (previewFileName) {
        previewFileName.textContent = data.fileName;
    }
    
    // 生成预览表格
    if (previewTable) {
        const stocks = data.stocks.slice(0, 10); // 最多显示10条
        const hasMore = data.stocks.length > 10;
        
        let html = `
            <thead>
                <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th>市场</th>
                    <th>持仓</th>
                    <th>成本价</th>
                    <th>现价</th>
                    <th>盈亏</th>
                </tr>
            </thead>
            <tbody>
        `;
        
        stocks.forEach(stock => {
            const pnlClass = stock.pnl >= 0 ? 'up' : 'down';
            const pnlSign = stock.pnl >= 0 ? '+' : '';
            html += `
                <tr>
                    <td>${stock.code}</td>
                    <td>${stock.name}</td>
                    <td>${stock.market}</td>
                    <td>${stock.shares}</td>
                    <td>${stock.costPrice.toFixed(2)}</td>
                    <td>${stock.currentPrice.toFixed(2)}</td>
                    <td class="${pnlClass}">${pnlSign}${stock.pnl.toFixed(0)}</td>
                </tr>
            `;
        });
        
        if (hasMore) {
            html += `<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">...还有 ${data.stocks.length - 10} 只股票...</td></tr>`;
        }
        
        html += '</tbody>';
        previewTable.innerHTML = html;
    }
    
    // 显示统计信息
    if (previewStats) {
        const stats = data.stats;
        const totalPnl = stats.totalMarketValue - stats.totalCost;
        const pnlClass = totalPnl >= 0 ? 'up' : 'down';
        const pnlSign = totalPnl >= 0 ? '+' : '';
        
        previewStats.innerHTML = `
            <div class="preview-stat">
                <span class="label">股票数量</span>
                <span class="value">${data.stocks.length}只</span>
            </div>
            <div class="preview-stat">
                <span class="label">总市值</span>
                <span class="value">${(stats.totalMarketValue / 10000).toFixed(1)}万</span>
            </div>
            <div class="preview-stat">
                <span class="label">总盈亏</span>
                <span class="value ${pnlClass}">${pnlSign}${(totalPnl / 10000).toFixed(1)}万</span>
            </div>
            <div class="preview-stat">
                <span class="label">盈利/亏损</span>
                <span class="value">${stats.profitCount}/${stats.lossCount}</span>
            </div>
        `;
    }
}

/**
 * 清空文件
 */
function clearFile() {
    const fileInput = document.getElementById('fileInput');
    const uploadArea = document.getElementById('uploadArea');
    const filePreview = document.getElementById('filePreview');
    
    if (fileInput) fileInput.value = '';
    if (uploadArea) uploadArea.style.display = 'block';
    if (filePreview) filePreview.style.display = 'none';
    
    pendingImportData = null;
    enableConfirmButton(false);
}

/**
 * 初始化手动录入功能
 */
function initManualInput() {
    const manualDataInput = document.getElementById('manualDataInput');
    
    if (manualDataInput) {
        // 自动调整高度
        manualDataInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.max(200, this.scrollHeight) + 'px';
        });
    }
}

/**
 * 解析手动录入的数据
 */
function parseManualData() {
    const textarea = document.getElementById('manualDataInput');
    if (!textarea || !textarea.value.trim()) {
        showNotification('请输入数据', 'warning');
        return;
    }
    
    const content = textarea.value;
    const result = parseStockData(content, 'manual.txt');
    
    if (result.success && result.stocks.length > 0) {
        pendingImportData = {
            fileName: '手动录入数据',
            stocks: result.stocks,
            stats: result.stats,
            timestamp: new Date().toISOString()
        };
        
        // 切换到文件上传标签页显示预览
        switchImportTab('upload');
        showFilePreview(pendingImportData);
        enableConfirmButton(true);
        showNotification(`成功解析 ${result.stocks.length} 只股票`, 'success');
    } else {
        showNotification(result.error || '未能解析到股票数据', 'error');
    }
}

/**
 * 清空手动录入
 */
function clearManualData() {
    const textarea = document.getElementById('manualDataInput');
    if (textarea) {
        textarea.value = '';
        textarea.style.height = '200px';
    }
}

/**
 * 初始化导入历史
 */
function initImportHistory() {
    renderImportHistory();
}

/**
 * 获取导入历史
 */
function getImportHistory() {
    try {
        const history = localStorage.getItem(IMPORT_HISTORY_KEY);
        return history ? JSON.parse(history) : [];
    } catch (e) {
        console.error('读取导入历史失败:', e);
        return [];
    }
}

/**
 * 保存导入历史
 */
function saveImportHistory(history) {
    try {
        localStorage.setItem(IMPORT_HISTORY_KEY, JSON.stringify(history));
    } catch (e) {
        console.error('保存导入历史失败:', e);
    }
}

/**
 * 添加导入历史记录
 */
function addImportHistory(record) {
    const history = getImportHistory();
    history.unshift(record);
    // 限制历史记录数量
    if (history.length > MAX_HISTORY_ITEMS) {
        history.pop();
    }
    saveImportHistory(history);
    renderImportHistory();
}

/**
 * 渲染导入历史
 */
function renderImportHistory() {
    const container = document.getElementById('importHistoryList');
    if (!container) return;
    
    const history = getImportHistory();
    
    if (history.length === 0) {
        container.innerHTML = `
            <div class="history-empty">
                <i class="fas fa-inbox"></i>
                <p>暂无导入记录</p>
                <span style="font-size:0.75rem;color:var(--text-muted)">导入的数据将保存在这里</span>
            </div>
        `;
        return;
    }
    
    let html = '';
    history.forEach((item, index) => {
        const date = new Date(item.timestamp);
        const dateStr = date.toLocaleDateString('zh-CN');
        const timeStr = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        
        html += `
            <div class="history-item">
                <div class="history-info">
                    <span class="history-date">${dateStr} ${timeStr}</span>
                    <span class="history-detail">
                        ${item.fileName} · ${item.stockCount}只股票 · 总市值${(item.totalValue / 10000).toFixed(1)}万
                    </span>
                </div>
                <div class="history-actions">
                    <button class="btn-text" onclick="restoreFromHistory(${index})">
                        <i class="fas fa-redo"></i> 恢复
                    </button>
                    <span class="status-badge success">成功</span>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

/**
 * 从历史记录恢复数据
 */
function restoreFromHistory(index) {
    const history = getImportHistory();
    if (index >= 0 && index < history.length) {
        const item = history[index];
        
        // 从localStorage获取完整数据
        const key = `import_data_${item.timestamp}`;
        const dataStr = localStorage.getItem(key);
        
        if (dataStr) {
            try {
                const stocks = JSON.parse(dataStr);
                pendingImportData = {
                    fileName: item.fileName + ' (历史记录)',
                    stocks: stocks,
                    stats: item.stats,
                    timestamp: new Date().toISOString()
                };
                
                // 切换到上传标签页显示预览
                switchImportTab('upload');
                showFilePreview(pendingImportData);
                enableConfirmButton(true);
                showNotification('已恢复历史数据', 'success');
            } catch (e) {
                showNotification('恢复失败，数据可能已过期', 'error');
            }
        }
    }
}

/**
 * 确认导入
 */
async function confirmImport() {
    console.log('确认导入被调用', pendingImportData);
    
    try {
        if (!pendingImportData || !pendingImportData.stocks.length) {
            showNotification('没有待导入的数据', 'warning');
            return;
        }
        
        // 检查 appState 是否可用
        if (typeof appState === 'undefined') {
            console.error('appState 未定义');
            showNotification('应用状态未初始化，请刷新页面重试', 'error');
            return;
        }
        
        if (!Array.isArray(appState.stocks)) {
            console.error('appState.stocks 不是数组', appState.stocks);
            appState.stocks = [];
        }
        
        const stocks = pendingImportData.stocks;
        let updated = 0;
        let added = 0;
        
        // 清空原有数据，以新导入的数据为准
        appState.stocks = [];
        
        // 显示加载提示
        showNotification('正在获取中轴价格，请稍候...', 'info');
        
        // fetch 带超时
        const fetchWithTimeout = (url, options, timeout = 10000) => {
            return Promise.race([
                fetch(url, options),
                new Promise((_, reject) => 
                    setTimeout(() => reject(new Error('请求超时')), timeout)
                )
            ]);
        };
        
        // 获取动态中轴价格并创建股票数据
        const stockPromises = stocks.map(async (newStock, index) => {
            try {
                let pivotPrice, triggerBuy, triggerSell;
                
                // 所有股票都调用API获取动态中轴价格
                const response = await fetchWithTimeout('/api/axis-price', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        code: newStock.code, 
                        market: newStock.market || 'A股', 
                        days: 90 
                    })
                }, 10000);
                
                const axisData = await response.json();
                
                if (axisData.success) {
                    pivotPrice = axisData.data.axis_price;
                    triggerBuy = axisData.data.trigger_buy;
                    triggerSell = axisData.data.trigger_sell;
                    console.log(`${newStock.code} 动态中轴: ${pivotPrice}, 触发区间: ${triggerBuy} - ${triggerSell}`);
                } else {
                    // API失败时回退到成本价
                    pivotPrice = newStock.costPrice || newStock.currentPrice || 0;
                    triggerBuy = pivotPrice * 0.92;
                    triggerSell = pivotPrice * 1.08;
                }
                
                // 港股保存导入的人民币成本，但价格后续会从API获取港币
                const isHKStock = newStock.market === '港股';
                
                return {
                    ...newStock,
                    price: newStock.currentPrice || newStock.price || 0,  // 先存导入的价格，后续会被API覆盖
                    change: 0,
                    changePercent: 0,
                    holdQuantity: newStock.shares || newStock.holdQuantity || 0,
                    holdCost: newStock.costPrice || newStock.holdCost || 0,  // 人民币成本
                    importedMarketValue: newStock.marketValue || 0,  // 保存券商导入的市值（人民币）
                    triggerBuy: triggerBuy,
                    triggerSell: triggerSell,
                    strategy: newStock.strategy || '基础',
                    investLimit: newStock.investLimit || (isHKStock ? 1500000 : 500000),
                    pivotPrice: pivotPrice,
                    baseRatio: newStock.baseRatio || 50,
                    floatRatio: newStock.floatRatio || 50,
                    id: String(index + 1),
                    status: '监控中',
                    market: newStock.market || 'A股'
                };
            } catch (error) {
                console.warn(`获取 ${newStock.code} 中轴价格失败: ${error.message}，使用成本价`);
                const pivotPrice = newStock.costPrice || newStock.currentPrice || 0;
                return {
                    ...newStock,
                    price: newStock.currentPrice || newStock.price || 0,
                    change: 0,
                    changePercent: 0,
                    holdQuantity: newStock.shares || newStock.holdQuantity || 0,
                    holdCost: newStock.costPrice || newStock.holdCost || 0,
                    marketValue: newStock.marketValue || 0,
                    triggerBuy: pivotPrice * 0.92,
                    triggerSell: pivotPrice * 1.08,
                    strategy: newStock.strategy || '基础',
                    investLimit: newStock.investLimit || (newStock.market === '港股' ? 1500000 : 500000),
                    pivotPrice: pivotPrice,
                    baseRatio: newStock.baseRatio || 50,
                    floatRatio: newStock.floatRatio || 50,
                    id: String(index + 1),
                    status: '监控中',
                    market: newStock.market || 'A股'
                };
            }
        });
        
        // 等待所有中轴价格获取完成（设置总超时）
        try {
            appState.stocks = await Promise.all(stockPromises);
        } catch (error) {
            console.error('部分股票获取中轴价格失败:', error);
            // 如果有失败的，使用已完成的
            const results = await Promise.allSettled(stockPromises);
            appState.stocks = results
                .filter(r => r.status === 'fulfilled')
                .map(r => r.value);
        }
        added = appState.stocks.length;
        
        // 重新渲染
        renderStockList();
        updateAssetOverview();
        
        // 保存到历史记录
        const stats = pendingImportData.stats;
        const historyRecord = {
            timestamp: pendingImportData.timestamp,
            fileName: pendingImportData.fileName,
            stockCount: stocks.length,
            totalValue: stats.totalMarketValue,
            stats: stats
        };
        
        addImportHistory(historyRecord);
        
        // 保存完整数据到localStorage（用于恢复）
        const key = `import_data_${pendingImportData.timestamp}`;
        localStorage.setItem(key, JSON.stringify(stocks));
        
        // 清理
        clearFile();
        hideDataImportModal();
        
        showNotification(`导入完成！共 ${appState.stocks.length} 只股票`, 'success');
        
        // 默认选中第一个
        if (appState.stocks.length > 0) {
            selectStock(0);
        }
        
        // 导入后立即获取实时行情（不受开市时间限制）
        await refreshStockQuotes();
        
    } catch (error) {
        console.error('导入失败:', error);
        showNotification('导入失败: ' + error.message, 'error');
    }
}

/**
 * 立即刷新股票行情（不检查开市状态）
 */
async function refreshStockQuotes() {
    if (appState.stocks.length === 0) return;
    
    try {
        const response = await fetch('/api/quotes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                stocks: appState.stocks.map(s => ({ code: s.code, market: s.market }))
            })
        });
        
        const data = await response.json();
        
        if (data.success && data.quotes) {
            if (data.exchange_rate) appState.exchangeRate = data.exchange_rate;
            
            appState.stocks.forEach(stock => {
                const quote = data.quotes[stock.code];
                if (quote) {
                    stock.price = quote.price;
                    stock.change = quote.change;
                    stock.changePercent = quote.change_percent;
                    if (quote.market === '港股') {
                        stock.priceCny = quote.price_cny;
                        stock.exchangeRate = quote.exchange_rate;
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
            showNotification('已更新实时行情', 'success');
        }
    } catch (error) {
        console.error('获取实时行情失败:', error);
    }
}

/**
 * 初始化模板下载
 */
function initTemplateDownload() {
    // 模板内容已内置在HTML中
}

/**
 * 下载示例模板
 */
function downloadTemplate(type) {
    let content = '';
    let filename = '';
    
    if (type === 'txt') {
        filename = '持仓导入模板.txt';
        content = `证券代码  证券名称  证券数量  可用数量  冻结数量  参考成本价  当前价  最新市值  浮动盈亏  盈亏比例(%)  代码
000001    平安银行  1000      1000      0         12.50       13.20   13200      700        5.60         000001
00700     腾讯控股  500       500       0         380.00      420.00  210000     20000      10.53        00700`;
    } else if (type === 'csv') {
        filename = '持仓导入模板.csv';
        content = `代码,名称,数量,成本价,现价
000001,平安银行,1000,12.50,13.20
00700,腾讯控股,500,380.00,420.00`;
    }
    
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    showNotification('模板下载成功', 'success');
}

/**
 * 切换导入标签页
 */
function switchImportTab(tabName) {
    document.querySelectorAll('.import-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.tab === tabName);
    });
    document.querySelectorAll('.import-content').forEach(content => {
        content.classList.remove('active');
    });
    const target = document.getElementById(tabName + 'Tab');
    if (target) target.classList.add('active');
}

/**
 * 启用/禁用确认按钮
 */
function enableConfirmButton(enabled) {
    const btn = document.getElementById('confirmImportBtn');
    if (btn) {
        btn.disabled = !enabled;
        // 添加视觉状态调试
        console.log('确认导入按钮状态:', enabled ? '启用' : '禁用');
    } else {
        console.error('找不到确认导入按钮');
    }
}

/**
 * 显示/隐藏弹窗
 */
let importInitialized = false;

function showDataImportModal() {
    const modal = document.getElementById('dataImportModal');
    if (modal) {
        // 延迟初始化，确保弹窗元素可见
        if (!importInitialized) {
            setTimeout(() => {
                initDataImport();
                importInitialized = true;
            }, 0);
        }
        modal.classList.add('active');
        // 重置到第一个标签
        switchImportTab('upload');
    }
}

function hideDataImportModal() {
    const modal = document.getElementById('dataImportModal');
    if (modal) {
        modal.classList.remove('active');
        // 清理状态
        clearFile();
        clearManualData();
    }
}

/**
 * 显示通知
 */
function showNotification(message, type = 'info') {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : type === 'warning' ? 'exclamation-triangle' : 'info-circle'}"></i>
        <span>${message}</span>
    `;
    
    // 样式
    notification.style.cssText = `
        position: fixed;
        top: 80px;
        right: 20px;
        padding: 12px 20px;
        background: var(--bg-card);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        display: flex;
        align-items: center;
        gap: 10px;
        z-index: 9999;
        animation: slideIn 0.3s ease;
        box-shadow: var(--shadow-lg);
    `;
    
    // 类型颜色
    if (type === 'success') {
        notification.style.borderLeft = '4px solid var(--status-success)';
    } else if (type === 'error') {
        notification.style.borderLeft = '4px solid var(--status-danger)';
    } else if (type === 'warning') {
        notification.style.borderLeft = '4px solid var(--accent-gold)';
    } else {
        notification.style.borderLeft = '4px solid var(--accent-blue)';
    }
    
    document.body.appendChild(notification);
    
    // 3秒后自动移除
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// 添加动画样式
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);

// 全局导出
window.initDataImport = initDataImport;
window.showDataImportModal = showDataImportModal;
window.hideDataImportModal = hideDataImportModal;
window.clearFile = clearFile;
window.switchImportTab = switchImportTab;
window.confirmImport = confirmImport;
window.parseManualData = parseManualData;
window.clearManualData = clearManualData;
window.downloadTemplate = downloadTemplate;
window.restoreFromHistory = restoreFromHistory;
window.showNotification = showNotification;
window.refreshStockQuotes = refreshStockQuotes;
