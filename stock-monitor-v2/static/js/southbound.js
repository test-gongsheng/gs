/**
 * 南向资金图表模块
 */

// 前端缓存（内存中，页面刷新后清空）
const southboundCache = {
    data: new Map(),
    TTL: 5 * 60 * 1000, // 5分钟
    
    get(stockCode) {
        const cached = this.data.get(stockCode);
        if (!cached) return null;
        if (Date.now() - cached.timestamp > this.TTL) {
            this.data.delete(stockCode);
            return null;
        }
        return cached.data;
    },
    
    set(stockCode, data) {
        this.data.set(stockCode, { data, timestamp: Date.now() });
    },
    
    clear() {
        this.data.clear();
    }
};

// 渲染南向资金整体流向图表
function renderSouthboundOverallChart(data) {
    // 检查 Chart.js 是否已加载
    if (typeof Chart === 'undefined') {
        console.warn('[Southbound] Chart.js 未加载，跳过图表渲染');
        updateSouthboundStats(data);
        return;
    }
    
    const ctx = document.getElementById('southboundOverallChart');
    if (!ctx) return;
    
    // 准备数据
    const dates = data.map(d => d.date);
    const netInflows = data.map(d => d.net_inflow);
    const cumulative30d = data.map(d => d.cumulative_30d);
    
    // 销毁旧图表
    if (window.southboundOverallChartInstance) {
        window.southboundOverallChartInstance.destroy();
    }
    
    window.southboundOverallChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: dates,
            datasets: [
                {
                    label: '当日净流入（亿元）',
                    data: netInflows,
                    backgroundColor: netInflows.map(v => v >= 0 ? 'rgba(239, 68, 68, 0.7)' : 'rgba(34, 197, 94, 0.7)'),
                    borderColor: netInflows.map(v => v >= 0 ? 'rgba(239, 68, 68, 1)' : 'rgba(34, 197, 94, 1)'),
                    borderWidth: 1,
                    order: 2
                },
                {
                    label: '30日累计（亿元）',
                    data: cumulative30d,
                    type: 'line',
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    order: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#e2e8f0',
                        font: { size: 11 }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#e2e8f0',
                    bodyColor: '#e2e8f0',
                    borderColor: '#334155',
                    borderWidth: 1,
                    callbacks: {
                        label: function(context) {
                            return context.dataset.label + ': ' + (context.raw >= 0 ? '+' : '') + context.raw + '亿元';
                        }
                    }
                }
            },
            scales: {
                x: {
                    display: false
                },
                y: {
                    grid: {
                        color: 'rgba(148, 163, 184, 0.1)'
                    },
                    ticks: {
                        color: '#94a3b8',
                        callback: function(value) {
                            return value + '亿';
                        }
                    }
                }
            }
        }
    });
}

// 渲染个股南向资金图表
function renderSouthboundStockChart(data, stockCode) {
    // 检查 Chart.js 是否已加载
    if (typeof Chart === 'undefined') {
        console.warn('[Southbound] Chart.js 未加载，跳过图表渲染');
        return;
    }
    
    const ctx = document.getElementById('southboundStockChart');
    if (!ctx) return;
    
    // 准备数据
    const dates = data.map(d => d.date);
    const netInflows = data.map(d => d.net_inflow);
    const holdRatios = data.map(d => d.hold_ratio);
    
    // 销毁旧图表
    if (window.southboundStockChartInstance) {
        window.southboundStockChartInstance.destroy();
    }
    
    window.southboundStockChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: dates,
            datasets: [
                {
                    label: '净买入（亿港元）',
                    data: netInflows,
                    backgroundColor: netInflows.map(v => v >= 0 ? 'rgba(239, 68, 68, 0.7)' : 'rgba(34, 197, 94, 0.7)'),
                    borderColor: netInflows.map(v => v >= 0 ? 'rgba(239, 68, 68, 1)' : 'rgba(34, 197, 94, 1)'),
                    borderWidth: 1,
                    yAxisID: 'y',
                    order: 2
                },
                {
                    label: '持股比例（%）',
                    data: holdRatios,
                    type: 'line',
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.1)',
                    borderWidth: 2,
                    fill: false,
                    tension: 0.4,
                    pointRadius: 1,
                    yAxisID: 'y1',
                    order: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#e2e8f0',
                        font: { size: 11 }
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#e2e8f0',
                    bodyColor: '#e2e8f0',
                    borderColor: '#334155',
                    borderWidth: 1
                }
            },
            scales: {
                x: {
                    display: false
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: {
                        color: 'rgba(148, 163, 184, 0.1)'
                    },
                    ticks: {
                        color: '#94a3b8'
                    },
                    title: {
                        display: true,
                        text: '净买入（亿港元）',
                        color: '#94a3b8'
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: {
                        drawOnChartArea: false
                    },
                    ticks: {
                        color: '#f59e0b',
                        callback: function(value) {
                            return value + '%';
                        }
                    },
                    title: {
                        display: true,
                        text: '持股比例',
                        color: '#f59e0b'
                    }
                }
            }
        }
    });
    
    // 同时渲染持股市值变化图
    renderSouthboundMarketCapChart(data, stockCode);
}

// 渲染持股市值变化图（双Y轴，6个月）
function renderSouthboundMarketCapChart(data, stockCode) {
    // 检查 Chart.js 是否已加载
    if (typeof Chart === 'undefined') {
        console.warn('[Southbound] Chart.js 未加载，跳过市值图表渲染');
        return;
    }
    
    const ctx = document.getElementById('southboundMarketCapChart');
    if (!ctx) return;
    
    // 取最近6个月数据（约120个交易日）
    const sixMonthsData = data.slice(-120);
    
    // 准备数据
    const dates = sixMonthsData.map(d => d.date);
    const holdShares = sixMonthsData.map(d => d.hold_shares || 0); // 万股
    const closePrices = sixMonthsData.map(d => d.close_price || 0);
    
    // 计算持股市值（亿港元）= 持股数量(万股) × 收盘价 / 10000
    const marketCaps = sixMonthsData.map(d => {
        const shares = d.hold_shares || 0; // 万股
        const price = d.close_price || 0;  // 港元
        return (shares * price / 10000).toFixed(2); // 亿港元
    });
    
    // 销毁旧图表
    if (window.southboundMarketCapChartInstance) {
        window.southboundMarketCapChartInstance.destroy();
    }
    
    window.southboundMarketCapChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dates,
            datasets: [
                {
                    label: '持股市值（亿港元）',
                    data: marketCaps,
                    borderColor: '#3b82f6', // 蓝色
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    yAxisID: 'y',
                    order: 1
                },
                {
                    label: '收盘价（港元）',
                    data: closePrices,
                    borderColor: '#ef4444', // 红色
                    backgroundColor: 'transparent',
                    borderWidth: 2,
                    borderDash: [5, 5], // 虚线
                    fill: false,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    yAxisID: 'y1',
                    order: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#e2e8f0',
                        font: { size: 11 },
                        usePointStyle: true,
                        boxWidth: 8
                    }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#e2e8f0',
                    bodyColor: '#e2e8f0',
                    borderColor: '#334155',
                    borderWidth: 1,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (context.dataset.yAxisID === 'y') {
                                label += context.raw + '亿';
                            } else {
                                label += context.raw + '港元';
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(148, 163, 184, 0.1)',
                        drawBorder: false
                    },
                    ticks: {
                        color: '#94a3b8',
                        maxTicksLimit: 6,
                        maxRotation: 0
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: {
                        color: 'rgba(148, 163, 184, 0.1)'
                    },
                    ticks: {
                        color: '#3b82f6',
                        callback: function(value) {
                            return value + '亿';
                        }
                    },
                    title: {
                        display: false
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: {
                        drawOnChartArea: false // 不显示右Y轴的网格线
                    },
                    ticks: {
                        color: '#ef4444',
                        callback: function(value) {
                            return value + '港元';
                        }
                    },
                    title: {
                        display: false
                    }
                }
            }
        }
    });
    
    console.log(`[Southbound] 市值图表渲染完成: ${stockCode}, ${sixMonthsData.length}条数据`);
}

// 加载南向资金整体数据
async function loadSouthboundOverallData() {
    try {
        const response = await fetch('/api/southbound/overall?days=90');
        const result = await response.json();
        
        if (result.success && result.data) {
            renderSouthboundOverallChart(result.data);
            
            // 更新信号卡片
            if (result.signal) {
                updateSouthboundSignal(result.signal);
            }
            
            // 更新统计数据
            updateSouthboundStats(result.data);
        }
    } catch (error) {
        console.error('加载南向资金数据失败:', error);
    }
}

// AbortController 用于真正取消旧请求
let southboundAbortController = null;

// 显示加载状态
function showSouthboundLoading(stockCode) {
    const ratioEl = document.getElementById('stockSouthboundRatio');
    const inflowEl = document.getElementById('stockSouthbound30d');
    const signalEl = document.getElementById('stockSouthboundSignal');
    
    if (ratioEl) ratioEl.innerHTML = '<span class="loading-spinner">⟳</span>';
    if (inflowEl) inflowEl.innerHTML = '<span class="loading-text">加载中...</span>';
    if (signalEl) signalEl.textContent = '加载中';
    
    console.log(`[Southbound] 显示加载状态: ${stockCode}`);
}

// 加载个股南向资金数据 - 修复版（避免快速切换时请求被取消）
async function loadSouthboundStockData(stockCode) {
    console.log(`[Southbound] === 加载: ${stockCode} ===`);
    
    // 检查前端缓存
    const cached = southboundCache.get(stockCode);
    if (cached) {
        console.log(`[Southbound] 缓存命中，直接渲染: ${stockCode}`);
        renderSouthboundStockChart(cached, stockCode);
        renderSouthboundMarketCapChart(cached, stockCode);
        updateSouthboundStockStats(cached, stockCode);
        return;
    }
    
    // 取消之前的请求（如果存在且不是当前股票的请求）
    if (southboundAbortController && southboundAbortController.stockCode !== stockCode) {
        console.log(`[Southbound] 取消旧请求: ${southboundAbortController.stockCode}`);
        southboundAbortController.controller.abort();
    }
    
    // 创建新的 AbortController，并标记所属股票
    const controller = new AbortController();
    southboundAbortController = {
        controller: controller,
        stockCode: stockCode
    };
    const signal = controller.signal;
    
    // 显示加载状态
    showSouthboundLoading(stockCode);
    
    console.log(`[Southbound] 请求API: /api/southbound/stock/${stockCode}`);
    const startTime = Date.now();
    
    try {
        const response = await fetch(`/api/southbound/stock/${stockCode}?days=90`, {
            signal: signal
        });
        
        console.log(`[Southbound] 响应: HTTP ${response.status}`);
        
        // 关键修复：请求完成后检查是否仍然是当前选中的股票
        // 如果用户已经切换到其他股票，忽略这次响应
        if (southboundAbortController && southboundAbortController.stockCode !== stockCode) {
            console.log(`[Southbound] 请求完成但已切换股票，忽略: ${stockCode} -> ${southboundAbortController.stockCode}`);
            return;
        }
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const result = await response.json();
        const elapsed = Date.now() - startTime;
        
        console.log(`[Southbound] 数据: success=${result.success}, count=${result.data?.length || 0}, 耗时${elapsed}ms`);
        
        // 再次检查：解析完数据后，确认还是当前股票
        if (southboundAbortController && southboundAbortController.stockCode !== stockCode) {
            console.log(`[Southbound] 数据解析完成但已切换股票，忽略: ${stockCode}`);
            return;
        }
        
        if (result.success && result.data && result.data.length > 0) {
            // 保存到缓存并渲染
            southboundCache.set(stockCode, result.data);
            renderSouthboundStockChart(result.data, stockCode);
            updateSouthboundStockStats(result.data, stockCode);
            console.log(`[Southbound] 渲染完成: ${stockCode}`);
        } else {
            console.warn(`[Southbound] 无数据: ${stockCode}`);
            clearSouthboundStockDisplay();
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log(`[Southbound] 请求被主动取消: ${stockCode}`);
            return;
        }
        console.error(`[Southbound] 失败: ${stockCode}`, error.message);
        clearSouthboundStockDisplay();
    }
}

// 清空南向资金显示
function clearSouthboundStockDisplay() {
    const ratioEl = document.getElementById('stockSouthboundRatio');
    const inflowEl = document.getElementById('stockSouthbound30d');
    const signalEl = document.getElementById('stockSouthboundSignal');
    
    if (ratioEl) ratioEl.textContent = '--';
    if (inflowEl) inflowEl.textContent = '--';
    if (signalEl) signalEl.textContent = '--';
    
    // 销毁旧图表
    if (window.southboundStockChartInstance) {
        window.southboundStockChartInstance.destroy();
        window.southboundStockChartInstance = null;
    }
}

// 更新南向资金信号
function updateSouthboundSignal(signal) {
    const signalEl = document.getElementById('southboundSignal');
    const reasonEl = document.getElementById('southboundSignalReason');
    
    if (signalEl) {
        signalEl.textContent = signal.signal;
        signalEl.className = `signal-badge ${signal.score >= 60 ? 'bull' : signal.score <= 40 ? 'bear' : 'neutral'}`;
    }
    
    if (reasonEl) {
        reasonEl.textContent = signal.reason;
    }
}

// 更新统计数据
function updateSouthboundStats(data) {
    if (data.length === 0) return;
    
    // 最新数据
    const latest = data[data.length - 1];
    
    // 今日净流入
    const todayEl = document.getElementById('southboundToday');
    if (todayEl) {
        const value = latest.net_inflow;
        todayEl.textContent = (value >= 0 ? '+' : '') + value + '亿';
        todayEl.className = `metric-value ${value >= 0 ? 'up' : 'down'}`;
    }
    
    // 30日累计
    const cumulative30El = document.getElementById('southboundCumulative30');
    if (cumulative30El) {
        const value = latest.cumulative_30d;
        cumulative30El.textContent = (value >= 0 ? '+' : '') + value + '亿';
        cumulative30El.className = `metric-value ${value >= 0 ? 'up' : 'down'}`;
    }
    
    // 90日累计
    const cumulative90El = document.getElementById('southboundCumulative90');
    if (cumulative90El) {
        const value = latest.cumulative_90d;
        cumulative90El.textContent = (value >= 0 ? '+' : '') + value + '亿';
        cumulative90El.className = `metric-value ${value >= 0 ? 'up' : 'down'}`;
    }
}

// 更新个股统计数据
function updateSouthboundStockStats(data, stockCode) {
    console.log(`[Southbound] 更新统计数据: ${stockCode}, ${data.length}条数据`);
    
    if (data.length === 0) {
        console.warn(`[Southbound] 数据为空，跳过更新`);
        return;
    }
    
    const latest = data[data.length - 1];
    console.log(`[Southbound] 最新数据:`, latest);
    
    // 最新持股占比
    const ratioEl = document.getElementById('stockSouthboundRatio');
    console.log(`[Southbound] ratioEl找到: ${!!ratioEl}`);
    if (ratioEl) {
        ratioEl.textContent = latest.hold_ratio + '%';
        console.log(`[Southbound] 已更新持股比例: ${latest.hold_ratio}%`);
    }
    
    // 近30日净流入
    const recent30d = data.slice(-30);
    const netInflow30d = recent30d.reduce((sum, d) => sum + (parseFloat(d.net_inflow) || 0), 0);
    const netInflow30El = document.getElementById('stockSouthbound30d');
    console.log(`[Southbound] netInflow30El找到: ${!!netInflow30El}, 30日净流入: ${netInflow30d}`);
    if (netInflow30El) {
        netInflow30El.textContent = (netInflow30d >= 0 ? '+' : '') + netInflow30d.toFixed(2) + '亿港元';
        netInflow30El.className = `metric-value ${netInflow30d >= 0 ? 'up' : 'down'}`;
        console.log(`[Southbound] 已更新30日净流入`);
    }
    
    // 判断信号
    const signalEl = document.getElementById('stockSouthboundSignal');
    console.log(`[Southbound] signalEl找到: ${!!signalEl}`);
    if (signalEl) {
        let signal = '中性';
        if (netInflow30d > 5) signal = '增持';
        else if (netInflow30d > 10) signal = '大幅增持';
        else if (netInflow30d < -5) signal = '减持';
        else if (netInflow30d < -10) signal = '大幅减持';
        
        signalEl.textContent = signal;
        signalEl.className = `signal-badge ${netInflow30d > 0 ? 'bull' : netInflow30d < 0 ? 'bear' : 'neutral'}`;
        console.log(`[Southbound] 已更新信号: ${signal}`);
    }
}
