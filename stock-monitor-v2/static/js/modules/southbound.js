/**
 * Southbound Capital Module - 南向资金模块
 * 完全独立，内部处理竞态条件，外部零耦合
 */

class SouthboundModule {
    constructor() {
        this.cache = new Map();
        this.currentRequest = null;
        this.listeners = new Set();
    }

    // 订阅数据更新
    onUpdate(callback) {
        this.listeners.add(callback);
        return () => this.listeners.delete(callback);
    }

    // 通知监听者
    _notify(data, stockCode) {
        this.listeners.forEach(cb => {
            try {
                cb(data, stockCode);
            } catch (e) {
                console.error('[Southbound] 监听回调错误:', e);
            }
        });
    }

    // 获取缓存键
    _getCacheKey(stockCode) {
        return `southbound_${stockCode}`;
    }

    // 检查缓存是否有效
    _isCacheValid(stockCode) {
        const cached = this.cache.get(this._getCacheKey(stockCode));
        if (!cached) return false;
        
        // 缓存5分钟
        const CACHE_TTL = 5 * 60 * 1000;
        return Date.now() - cached.timestamp < CACHE_TTL;
    }

    // 获取缓存数据
    _getCache(stockCode) {
        return this.cache.get(this._getCacheKey(stockCode))?.data;
    }

    // 设置缓存
    _setCache(stockCode, data) {
        this.cache.set(this._getCacheKey(stockCode), {
            data,
            timestamp: Date.now()
        });
    }

    // 加载南向资金数据（核心方法）
    async load(stockCode, options = {}) {
        const { forceRefresh = false, days = 90 } = options;
        
        // 取消之前的请求
        if (this.currentRequest) {
            this.currentRequest.abort();
        }
        
        // 检查缓存
        if (!forceRefresh && this._isCacheValid(stockCode)) {
            console.log(`[Southbound] 使用缓存: ${stockCode}`);
            const cached = this._getCache(stockCode);
            this._notify(cached, stockCode);
            return { success: true, data: cached, fromCache: true };
        }
        
        console.log(`[Southbound] 开始加载: ${stockCode}`);
        
        const controller = new AbortController();
        this.currentRequest = controller;
        
        try {
            const response = await fetch(`/api/southbound/stock/${stockCode}?days=${days}`, {
                signal: controller.signal
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const result = await response.json();
            
            // 检查请求是否被取消或已被新的请求替代
            if (this.currentRequest !== controller) {
                console.log(`[Southbound] 请求 ${stockCode} 已过期，忽略响应`);
                throw new Error('Request superseded');
            }
            
            this.currentRequest = null;
            
            if (!result.success || !result.data) {
                throw new Error(result.message || '数据获取失败');
            }
            
            // 处理数据
            const processed = this._processData(result.data);
            
            // 缓存
            this._setCache(stockCode, processed);
            
            console.log(`[Southbound] 加载完成: ${stockCode}, ${processed.history?.length || 0}条数据`);
            
            // 通知监听者
            this._notify(processed, stockCode);
            
            return { success: true, data: processed, fromCache: false };
            
        } catch (error) {
            this.currentRequest = null;
            
            if (error.name === 'AbortError' || error.message === 'Request superseded') {
                console.log(`[Southbound] 请求 ${stockCode} 被取消`);
                throw error;
            }
            
            console.error(`[Southbound] 加载 ${stockCode} 失败:`, error.message);
            
            // 如果有缓存，返回缓存作为降级
            const cached = this._getCache(stockCode);
            if (cached) {
                console.log(`[Southbound] 返回过期缓存: ${stockCode}`);
                this._notify(cached, stockCode);
                return { success: true, data: cached, fromCache: true, error: error.message };
            }
            
            return { success: false, error: error.message };
        }
    }

    // 处理原始数据
    _processData(rawData) {
        // 后端返回的是数组，直接使用
        const history = Array.isArray(rawData) ? rawData : (rawData.history || []);
        const stockName = history.length > 0 ? history[0].stock_name : '';
        
        // 按日期排序
        const sorted = [...history].sort((a, b) => 
            new Date(a.date) - new Date(b.date)
        );
        
        // 计算统计数据
        const stats = this._calculateStats(sorted);
        
        return {
            history: sorted,
            stockName: stockName,
            stats,
            updateTime: new Date().toISOString()
        };
    }

    // 计算统计数据
    _calculateStats(history) {
        if (!history.length) return null;
        
        const netInflows = history.map(d => parseFloat(d.net_inflow) || 0);
        const recent30d = netInflows.slice(-30);
        const recent60d = netInflows.slice(-60);
        
        const avg = arr => arr.reduce((a, b) => a + b, 0) / (arr.length || 1);
        
        return {
            total30d: recent30d.reduce((a, b) => a + b, 0),
            avg30d: avg(recent30d),
            avg60d: avg(recent60d),
            avg90d: avg(netInflows),
            max90d: Math.max(...netInflows),
            min90d: Math.min(...netInflows),
            count: history.length
        };
    }

    // 清空缓存
    clearCache(stockCode = null) {
        if (stockCode) {
            this.cache.delete(this._getCacheKey(stockCode));
        } else {
            this.cache.clear();
        }
    }

    // 销毁模块
    destroy() {
        if (this.currentRequest) {
            this.currentRequest.abort();
        }
        this.listeners.clear();
        this.cache.clear();
    }
}

// 单例
const southboundModule = new SouthboundModule();

// 兼容旧代码的全局函数
window.SouthboundModule = SouthboundModule;
window.southboundModule = southboundModule;

// 保持与原 southbound.js 相同的接口
window.loadSouthboundStockData = (stockCode) => southboundModule.load(stockCode);

export default southboundModule;
