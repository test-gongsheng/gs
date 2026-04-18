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
    initTradeImport();  // 初始化交易记录导入
    
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
                // 对于港股，使用券商提供的最新市值（人民币）
                // 对于A股，用当前价计算
                let marketValue;
                if (stock.market === '港股' && stock.marketValue > 0) {
                    marketValue = stock.marketValue;  // 券商提供的市值（人民币）
                } else {
                    marketValue = stock.currentPrice * stock.shares;  // 实时计算
                }
                
                const costValue = stock.costPrice * stock.shares;
                const pnl = marketValue - costValue;
                
                stock.marketValue = marketValue;
                stock.pnl = pnl;
                stock.pnlPercent = costValue > 0 ? (pnl / costValue * 100) : 0;
                
                // 计算中轴价格和触发价
                // 注意：这里先不设置中轴价格，等导入后通过API动态获取
                // 中轴价格应该基于历史K线计算，而不是持仓成本
                stock.pivotPrice = 0;  // 标记为未计算，后续通过API获取
                stock.triggerBuy = 0;
                stock.triggerSell = 0;
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
        
        // 尝试解析扩展字段（交易记录、高波动标记、优先级）
        let lastTradePrice = 0;
        let lastTradeType = '';
        let lastTradeTime = '';
        let stockType = 'normal';
        let priority = 'P2';
        
        // 如果字段数量足够，尝试解析扩展字段
        if (parts.length >= 12) {
            lastTradePrice = parseFloat(parts[8]) || 0;
            lastTradeType = parts[9] || '';
            lastTradeTime = parts[10] || '';
            stockType = parts[11] || 'normal';
            priority = parts[12] || 'P2';
        }
        
        return {
            code,
            name,
            market,
            shares,
            costPrice,
            currentPrice,
            marketValue,  // 券商提供的最新市值
            // 扩展字段
            lastTradePrice,
            lastTradeType,
            lastTradeTime,
            stockType,
            priority
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
 * 确认导入 - 新版：支持自动检测交易并记录冷却期
 */
async function confirmImport() {
    console.log('确认导入被调用', pendingImportData);

    try {
        if (!pendingImportData || !pendingImportData.stocks.length) {
            showNotification('没有待导入的数据', 'warning');
            return;
        }

        // 获取现有的持仓数据（用于对比变化）
        let oldStocks = [];
        try {
            const response = await fetch('/api/stocks');
            const data = await response.json();
            if (Array.isArray(data)) {
                oldStocks = data;
            }
        } catch (e) {
            console.warn('获取现有持仓失败，将视为空持仓', e);
        }

        const stocks = pendingImportData.stocks;
        console.log('旧持仓数据:', oldStocks.map(s => ({ code: s.code, shares: s.shares || s.holdQuantity || 0 })));
        console.log('新持仓数据:', stocks.map(s => ({ code: s.code, shares: s.shares })));

        // 【新增】对比持仓变化，自动检测交易
        const trades = detectTrades(oldStocks, stocks);
        console.log('[confirmImport] 检测到的交易:', trades);

        // 清除旧缓存
        localStorage.removeItem('import_data_last');

        // 显示加载提示
        showNotification('正在导入数据，请稍候...', 'info');

        // 先清空所有现有股票
        console.log('[confirmImport] 清空现有持仓...');
        try {
            await fetch('/api/stocks/clear', { method: 'POST' });
            console.log('[confirmImport] 清空完成');
        } catch (e) {
            console.warn('[confirmImport] 清空失败，继续导入', e);
        }

        // 获取汇率
        let exchangeRate = 1.1339;
        try {
            const rateResponse = await fetch('/api/exchange-rate');
            const rateData = await rateResponse.json();
            if (rateData.success && rateData.yesterday_rate) {
                exchangeRate = rateData.yesterday_rate;
            }
        } catch (e) {
            console.warn('获取汇率失败，使用默认值', e);
        }

        // 构建批量导入数据
        const stocksToAdd = stocks.map(newStock => ({
            code: newStock.code,
            name: newStock.name,
            market: newStock.market,
            avg_cost: newStock.costPrice,
            shares: newStock.shares,
            current_price: newStock.currentPrice,
            axis_price: 0,  // 导入完成后统一刷新
            base_position_pct: 50,
            float_position_pct: 50,
            trigger_pct: 8,
            stop_loss: 0,
            priority: newStock.priority || 'P2',
            strategy_mode: '基础策略',
            notes: '',
            // 【新增】交易记录和股票类型
            stock_type: newStock.stockType || 'normal',
            last_trade_price: newStock.lastTradePrice || 0,
            last_trade_type: newStock.lastTradeType || '',
            last_trade_time: newStock.lastTradeTime || ''
        }));

        console.log(`[confirmImport] 批量导入 ${stocksToAdd.length} 只股票`);
        
        // 调用批量导入 API（传递交易记录）
        console.log('[confirmImport] 发送批量导入请求...', stocksToAdd.length, '只股票');
        const batchResponse = await fetch('/api/stocks/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                stocks: stocksToAdd,
                trades: trades  // 【新增】传递检测到的交易记录
            })
        });

        let added = 0;
        console.log('[confirmImport] 批量导入响应状态:', batchResponse.status);
        if (batchResponse.ok) {
            const result = await batchResponse.json();
            console.log('[confirmImport] 批量导入响应:', result);
            if (result.success) {
                added = result.count;
                console.log(`[confirmImport] 批量导入成功: ${added} 只`);
                
                // 显示交易记录提示
                if (trades.length > 0) {
                    const buyCount = trades.filter(t => t.trade_type === 'buy').length;
                    const sellCount = trades.filter(t => t.trade_type === 'sell').length;
                    showNotification(`自动记录: ${buyCount} 笔买入, ${sellCount} 笔卖出`, 'info');
                }
                
                // 立即验证后端数据
                const verifyResp = await fetch('/api/stocks');
                const verifyData = await verifyResp.json();
                console.log('[confirmImport] 验证后端数据:', verifyData.length, '只股票');
            } else {
                console.error('[confirmImport] 批量导入失败:', result.error);
            }
        } else {
            const errorText = await batchResponse.text();
            console.error('[confirmImport] 批量导入失败:', batchResponse.status, errorText);
        }

        // 添加到导入历史
        const totalValue = stocks.reduce((sum, s) => sum + (s.currentPrice * s.shares), 0);
        addImportHistory({
            timestamp: new Date().toISOString(),
            fileName: pendingImportData.fileName || '手动导入',
            stockCount: added,
            totalValue: totalValue,
            stats: {
                totalMarketValue: totalValue,
                totalCost: stocks.reduce((sum, s) => sum + (s.costPrice * s.shares), 0),
                profitCount: stocks.filter(s => s.pnl >= 0).length,
                lossCount: stocks.filter(s => s.pnl < 0).length
            },
            stocks: stocks.map(s => ({ code: s.code, name: s.name, shares: s.shares })),
            trades: trades  // 【新增】保存交易记录到历史
        });

        // 清空待导入数据
        pendingImportData = null;
        hideDataImportModal();

        showNotification(`导入完成！共 ${added} 只股票`, 'success');

        // 导入完成，立即刷新页面（行情将在后台异步刷新）
        setTimeout(() => {
            console.log('[导入完成] 刷新页面...');
            window.location.reload();
        }, 1500);

    } catch (error) {
        console.error('导入失败:', error);
        showNotification('导入失败: ' + error.message, 'error');
    }
}

/**
 * 【新增】检测持仓变化，生成交易记录
 * @param {Array} oldStocks - 旧持仓
 * @param {Array} newStocks - 新持仓
 * @returns {Array} 交易记录数组
 */
function detectTrades(oldStocks, newStocks) {
    const trades = [];
    const now = new Date().toISOString();
    
    // 创建旧持仓映射（按代码）
    const oldMap = {};
    oldStocks.forEach(s => {
        const code = s.code || s.stock_code;
        if (code) {
            oldMap[code] = {
                shares: parseFloat(s.shares || s.holdQuantity || 0),
                avg_cost: parseFloat(s.avg_cost || s.costPrice || s.cost || 0),
                name: s.name || s.stock_name || ''
            };
        }
    });
    
    // 创建新持仓映射
    const newMap = {};
    newStocks.forEach(s => {
        if (s.code) {
            newMap[s.code] = {
                shares: parseFloat(s.shares || 0),
                costPrice: parseFloat(s.costPrice || s.avg_cost || 0),
                name: s.name || '',
                currentPrice: parseFloat(s.currentPrice || 0)
            };
        }
    });
    
    // 1. 检测买入（新股票或股数增加）
    Object.keys(newMap).forEach(code => {
        const newStock = newMap[code];
        const oldStock = oldMap[code];
        
        if (!oldStock) {
            // 全新买入
            trades.push({
                stock_code: code,
                stock_name: newStock.name,
                trade_type: 'buy',
                price: newStock.costPrice,
                shares: newStock.shares,
                time: now,
                note: '导入时检测：新增持仓'
            });
        } else if (newStock.shares > oldStock.shares) {
            // 加仓
            const addedShares = newStock.shares - oldStock.shares;
            trades.push({
                stock_code: code,
                stock_name: newStock.name,
                trade_type: 'buy',
                price: newStock.costPrice,
                shares: addedShares,
                time: now,
                note: '导入时检测：加仓'
            });
        }
    });
    
    // 2. 检测卖出（股票消失或股数减少）
    Object.keys(oldMap).forEach(code => {
        const oldStock = oldMap[code];
        const newStock = newMap[code];
        
        if (!newStock) {
            // 完全清仓
            trades.push({
                stock_code: code,
                stock_name: oldStock.name,
                trade_type: 'sell',
                price: oldStock.avg_cost, // 使用成本价作为卖出参考
                shares: oldStock.shares,
                time: now,
                note: '导入时检测：清仓卖出'
            });
        } else if (oldStock.shares > newStock.shares) {
            // 减仓卖出
            const soldShares = oldStock.shares - newStock.shares;
            trades.push({
                stock_code: code,
                stock_name: newStock.name,
                trade_type: 'sell',
                price: newStock.currentPrice || oldStock.avg_cost,
                shares: soldShares,
                time: now,
                note: '导入时检测：减仓卖出'
            });
        }
    });
    
    console.log(`[detectTrades] 检测到 ${trades.length} 笔交易:`, trades.map(t => 
        `${t.stock_code} ${t.trade_type} ${t.shares}股 @ ¥${t.price}`
    ));
    
    return trades;
}

/**
 * 导入完成后刷新股票行情（带超时控制，失败时使用导入价格）
 * 注意：此函数现在由页面加载后自动调用，不在导入时阻塞
 */
async function refreshStockQuotesAfterImport() {
    const appState = window.appState;
    if (!appState || !appState.stocks || appState.stocks.length === 0) return;
    
    console.log('[refreshStockQuotesAfterImport] 开始后台刷新行情...');
    
    // 使用 AbortController 设置 8 秒超时
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);
    
    try {
        const response = await fetch('/api/quotes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                stocks: appState.stocks.map(s => ({ code: s.code, market: s.market }))
            }),
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        
        const data = await response.json();
        
        if (data.success && data.quotes) {
            if (data.exchange_rate) appState.exchangeRate = data.exchange_rate;
            
            // 更新前端价格
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
            
            // 同步到后端（不等待）
            appState.stocks.forEach(stock => {
                fetch(`/api/stocks/${stock.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current_price: stock.price })
                }).catch(() => {});
            });
            
            renderStockList();
            if (appState.selectedStock) renderStockDetail();
            updateAssetOverview();
            console.log('[refreshStockQuotesAfterImport] 行情刷新成功');
        }
    } catch (error) {
        console.warn('[refreshStockQuotesAfterImport] 获取行情失败，使用导入价格:', error.name || error.message);
        // 失败时不阻塞，使用导入时保存的价格
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
window.refreshStockQuotes = refreshStockQuotesAfterImport;

// ========== 交易记录导入功能 ==========

let pendingTradeData = null;

/**
 * 初始化交易记录导入功能
 */
function initTradeImport() {
    const tradeUploadArea = document.getElementById('tradeUploadArea');
    const tradeFileInput = document.getElementById('tradeFileInput');
    
    if (!tradeUploadArea || !tradeFileInput) {
        console.log('[TradeImport] 找不到交易上传元素，可能页面未加载');
        return;
    }
    
    // 点击上传
    tradeUploadArea.onclick = function(e) {
        if (e.target.tagName !== 'INPUT') {
            tradeFileInput.click();
        }
    };
    
    // 文件选择
    tradeFileInput.onchange = function(e) {
        const file = e.target.files[0];
        if (file) processTradeFile(file);
    };
    
    console.log('[TradeImport] 交易记录导入初始化完成');
}

/**
 * 处理交易记录文件
 */
function processTradeFile(file) {
    console.log('[TradeImport] 处理交易文件:', file.name);
    
    const validTypes = ['.txt', '.csv', '.xls', '.xlsx'];
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    
    if (!validTypes.includes(ext)) {
        showNotification('不支持的文件格式，请上传 .txt、.csv 或 Excel 文件', 'error');
        return;
    }
    
    const reader = new FileReader();
    
    reader.onload = function(e) {
        const content = e.target.result;
        try {
            const result = parseTradeData(content, file.name);
            if (result.success && result.trades.length > 0) {
                pendingTradeData = {
                    fileName: file.name,
                    trades: result.trades,
                    stats: result.stats,
                    timestamp: new Date().toISOString()
                };
                showTradePreview(pendingTradeData);
                showNotification(`成功解析 ${result.trades.length} 笔交易`, 'success');
            } else {
                showNotification(result.error || '未能解析到交易记录', 'error');
            }
        } catch (err) {
            console.error('解析交易文件出错:', err);
            showNotification('文件解析失败，请检查格式是否正确', 'error');
        }
    };
    
    reader.onerror = function() {
        showNotification('文件读取失败', 'error');
    };
    
    // 交易文件通常用GBK编码
    if (ext === '.txt') {
        reader.readAsText(file, 'GBK');
    } else {
        reader.readAsText(file, 'UTF-8');
    }
}

/**
 * 解析交易记录数据 - 支持同花顺/通达信格式
 */
function parseTradeData(content, fileName) {
    const lines = content.split('\n').filter(line => line.trim());
    const trades = [];
    let stats = {
        totalCount: 0,
        buyCount: 0,
        sellCount: 0,
        stockTrades: 0,
        filteredCount: 0
    };
    
    // 检测表头行
    let headerFound = false;
    let headerIndex = -1;
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (line.includes('成交日期') || line.includes('成交时间') || line.includes('证券代码')) {
            headerFound = true;
            headerIndex = i;
            break;
        }
    }
    
    // 开始解析数据行
    const startIndex = headerFound ? headerIndex + 1 : 0;
    
    for (let i = startIndex; i < lines.length; i++) {
        const line = lines[i].trim();
        
        // 跳过空行和分隔线
        if (!line || line.match(/^[-=]+$/) || line.includes('合计') || line.includes('总计')) continue;
        
        const trade = parseTradeLine(line);
        if (trade) {
            // 过滤逆回购等非股票交易
            if (isStockTrade(trade)) {
                trades.push(trade);
                stats.stockTrades++;
                stats.totalCount++;
                if (trade.tradeType === 'buy') {
                    stats.buyCount++;
                } else {
                    stats.sellCount++;
                }
            } else {
                stats.filteredCount++;
            }
        }
    }
    
    if (trades.length === 0) {
        return { success: false, error: '未能解析到有效交易记录，请检查文件格式' };
    }
    
    return { success: true, trades, stats };
}

/**
 * 解析单行交易数据
 */
function parseTradeLine(line) {
    try {
        // 清理行内容
        line = line.replace(/"/g, '').trim();
        
        // 按空格或制表符分割
        const parts = line.split(/\s+|\t+/).filter(p => p.trim());
        
        if (parts.length < 6) return null;
        
        // 同花顺格式:
        // 成交日期 成交时间 证券代码 证券名称 买卖标志 成交价格 成交数量 成交金额
        // 20260410 09:55:58 000559 万向钱潮 证券卖出 16.840 3000 50520.00
        
        // 尝试识别各字段位置
        let date = '';
        let time = '';
        let code = '';
        let name = '';
        let tradeType = '';
        let price = 0;
        let shares = 0;
        
        // 遍历字段，根据特征识别
        for (let i = 0; i < parts.length; i++) {
            const part = parts[i].trim();
            
            // 日期格式: 20260410 或 2026-04-10
            if (!date && part.match(/^\d{8}$/) || part.match(/^\d{4}[-/]\d{2}[-/]\d{2}$/)) {
                date = part.replace(/[-/]/g, '');
                continue;
            }
            
            // 时间格式: 09:55:58 或 09:55
            if (!time && part.match(/^\d{2}:\d{2}(:\d{2})?$/)) {
                time = part;
                continue;
            }
            
            // 证券代码: 6位数字
            if (!code && part.match(/^\d{5,6}$/)) {
                code = part;
                continue;
            }
            
            // 买卖标志
            if (!tradeType && (part.includes('买入') || part.includes('卖出') || part.includes('买') || part.includes('卖'))) {
                tradeType = part.includes('买入') || part.includes('买') ? 'buy' : 'sell';
                continue;
            }
            
            // 成交价格: 带小数点的数字
            if (price === 0 && part.match(/^\d+\.\d+$/)) {
                price = parseFloat(part);
                continue;
            }
            
            // 成交数量: 整数
            if (shares === 0 && part.match(/^\d+$/) && parseInt(part) > 100) {
                shares = parseInt(part);
                continue;
            }
            
            // 证券名称: 中文，不是数字
            if (!name && !part.match(/^\d/) && part.length >= 2 && part.length <= 6) {
                name = part;
                continue;
            }
        }
        
        // 如果没有识别出名称，尝试用代码附近的字段
        if (!name) {
            const codeIndex = parts.findIndex(p => p === code);
            if (codeIndex >= 0 && codeIndex + 1 < parts.length) {
                const nextPart = parts[codeIndex + 1];
                if (!nextPart.match(/^\d/) && !nextPart.includes('买入') && !nextPart.includes('卖出')) {
                    name = nextPart;
                }
            }
        }
        
        // 验证必填字段
        if (!code || !tradeType || price === 0 || shares === 0) {
            return null;
        }
        
        // 构建交易记录
        const tradeTime = date && time ? `${date.slice(0,4)}-${date.slice(4,6)}-${date.slice(6,8)} ${time}` : 
                         date ? `${date.slice(0,4)}-${date.slice(4,6)}-${date.slice(6,8)}` :
                         new Date().toISOString();
        
        return {
            code,
            name: name || code,
            tradeType,
            price,
            shares,
            time: tradeTime,
            amount: price * shares
        };
    } catch (e) {
        console.error('解析交易行失败:', line, e);
        return null;
    }
}

/**
 * 判断是否为股票交易（排除逆回购等）
 */
function isStockTrade(trade) {
    // 排除国债逆回购
    const nonStockCodes = ['GC001', 'GC007', 'GC028', 'R001', 'R007', 'R028'];
    if (nonStockCodes.includes(trade.code)) return false;
    
    // 排除基金
    if (trade.code.startsWith('5') || trade.code.startsWith('1')) {
        // 检查名称是否包含基金相关字样
        const fundKeywords = ['ETF', 'LOF', '基金', '国债', '转债'];
        if (fundKeywords.some(k => trade.name.includes(k))) return false;
    }
    
    // 确保代码是6位（A股）或5位（港股）
    if (trade.code.length !== 6 && trade.code.length !== 5) return false;
    
    return true;
}

/**
 * 显示交易记录预览
 */
function showTradePreview(data) {
    const uploadArea = document.getElementById('tradeUploadArea');
    const preview = document.getElementById('tradePreview');
    const fileName = document.getElementById('tradePreviewFileName');
    const table = document.getElementById('tradePreviewTable');
    const stats = document.getElementById('tradePreviewStats');
    const actions = document.getElementById('tradeImportActions');
    
    if (!uploadArea || !preview) return;
    
    // 隐藏上传区域，显示预览
    uploadArea.style.display = 'none';
    preview.style.display = 'block';
    if (actions) actions.style.display = 'block';
    
    // 显示文件名
    if (fileName) fileName.textContent = data.fileName;
    
    // 生成预览表格
    if (table) {
        const trades = data.trades.slice(0, 10); // 最多显示10条
        const hasMore = data.trades.length > 10;
        
        let html = `
            <thead>
                <tr>
                    <th>日期时间</th>
                    <th>代码</th>
                    <th>名称</th>
                    <th>类型</th>
                    <th>价格</th>
                    <th>数量</th>
                    <th>金额</th>
                </tr>
            </thead>
            <tbody>
        `;
        
        trades.forEach(t => {
            const typeClass = t.tradeType === 'buy' ? 'up' : 'down';
            const typeText = t.tradeType === 'buy' ? '买入' : '卖出';
            html += `
                <tr>
                    <td>${t.time.slice(0,16)}</td>
                    <td>${t.code}</td>
                    <td>${t.name}</td>
                    <td class="${typeClass}">${typeText}</td>
                    <td>${t.price.toFixed(2)}</td>
                    <td>${t.shares}</td>
                    <td>${(t.amount/10000).toFixed(2)}万</td>
                </tr>
            `;
        });
        
        if (hasMore) {
            html += `<tr><td colspan="7" style="text-align:center;color:var(--text-muted)">...还有 ${data.trades.length - 10} 笔交易...</td></tr>`;
        }
        
        html += '</tbody>';
        table.innerHTML = html;
    }
    
    // 显示统计
    if (stats) {
        stats.innerHTML = `
            <div style="display:flex;gap:16px;justify-content:center;padding:12px;">
                <span>总计: <strong>${data.stats.totalCount}</strong> 笔</span>
                <span style="color:#10b981;">买入: <strong>${data.stats.buyCount}</strong></span>
                <span style="color:#ef4444;">卖出: <strong>${data.stats.sellCount}</strong></span>
                ${data.stats.filteredCount > 0 ? `<span style="color:#999;">已过滤: ${data.stats.filteredCount}</span>` : ''}
            </div>
        `;
    }
}

/**
 * 清除交易文件
 */
function clearTradeFile() {
    pendingTradeData = null;
    const uploadArea = document.getElementById('tradeUploadArea');
    const preview = document.getElementById('tradePreview');
    const fileInput = document.getElementById('tradeFileInput');
    const actions = document.getElementById('tradeImportActions');
    
    if (uploadArea) uploadArea.style.display = 'flex';
    if (preview) preview.style.display = 'none';
    if (actions) actions.style.display = 'none';
    if (fileInput) fileInput.value = '';
}

/**
 * 确认导入交易记录
 */
async function confirmTradeImport() {
    console.log('[TradeImport] 确认导入交易记录', pendingTradeData);
    
    if (!pendingTradeData || !pendingTradeData.trades.length) {
        showNotification('没有待导入的交易记录', 'warning');
        return;
    }
    
    try {
        showNotification('正在导入交易记录...', 'info');
        
        const response = await fetch('/api/trades/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                trades: pendingTradeData.trades
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const result = await response.json();
        console.log('[TradeImport] 导入结果:', result);
        
        if (result.success) {
            showNotification(`导入成功！更新 ${result.updated} 只股票交易记录`, 'success');
            
            // 清除状态
            clearTradeFile();
            
            // 延迟刷新页面
            setTimeout(() => {
                window.location.reload();
            }, 1500);
        } else {
            showNotification(result.error || '导入失败', 'error');
        }
    } catch (error) {
        console.error('[TradeImport] 导入失败:', error);
        showNotification('导入失败: ' + error.message, 'error');
    }
}

// 导出到全局
window.initTradeImport = initTradeImport;
window.confirmTradeImport = confirmTradeImport;
window.clearTradeFile = clearTradeFile;
