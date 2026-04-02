/**
 * State Manager - 统一状态管理
 * 单一数据源，订阅模式，自动竞态条件处理
 */

class StateManager {
    constructor() {
        this.state = {
            stocks: [],
            selectedStock: null,
            hotSectors: [],
            news: [],
            alerts: [],
            sentiment: null,
            totalAssets: 8000000,
            marketStatus: 'closed',
            version: window.APP_VERSION || '3.0.3',
            portfolioAnalysis: null,
            exchangeRate: 0.92,
            _locks: new Map(),
            _pendingRequests: new Map()
        };
        
        this.listeners = new Map();
        this.batchUpdate = false;
        this.pendingChanges = new Set();
    }

    // 获取状态（只读）
    get(key) {
        return key ? this.state[key] : { ...this.state };
    }

    // 设置状态（触发监听）
    set(key, value) {
        const oldValue = this.state[key];
        this.state[key] = value;
        
        if (!this.batchUpdate) {
            this._notify(key, value, oldValue);
        } else {
            this.pendingChanges.add(key);
        }
    }

    // 批量更新
    batch(callback) {
        this.batchUpdate = true;
        try {
            callback(this);
        } finally {
            this.batchUpdate = false;
            this.pendingChanges.forEach(key => {
                this._notify(key, this.state[key], undefined);
            });
            this.pendingChanges.clear();
        }
    }

    // 订阅状态变化
    subscribe(key, callback) {
        if (!this.listeners.has(key)) {
            this.listeners.set(key, new Set());
        }
        this.listeners.get(key).add(callback);
        
        // 返回取消订阅函数
        return () => this.listeners.get(key).delete(callback);
    }

    // 通知监听者
    _notify(key, newValue, oldValue) {
        const callbacks = this.listeners.get(key);
        if (callbacks) {
            callbacks.forEach(cb => {
                try {
                    cb(newValue, oldValue, key);
                } catch (e) {
                    console.error(`[StateManager] 监听回调错误: ${key}`, e);
                }
            });
        }
    }

    // 获取锁（防止竞态条件）
    async withLock(key, fn) {
        if (this.state._locks.get(key)) {
            console.log(`[StateManager] 锁 ${key} 被占用，跳过`);
            return null;
        }
        
        this.state._locks.set(key, true);
        try {
            return await fn();
        } finally {
            this.state._locks.set(key, false);
        }
    }

    // 带竞态条件防护的请求
    async fetchWithRaceControl(key, fetchFn) {
        // 取消之前的请求
        const prevController = this.state._pendingRequests.get(key);
        if (prevController) {
            prevController.abort();
        }
        
        const controller = new AbortController();
        this.state._pendingRequests.set(key, controller);
        
        try {
            const result = await fetchFn(controller.signal);
            // 检查是否仍然是最新请求
            if (this.state._pendingRequests.get(key) === controller) {
                this.state._pendingRequests.delete(key);
                return result;
            }
            throw new Error('Request superseded');
        } catch (e) {
            if (e.name === 'AbortError' || e.message === 'Request superseded') {
                throw e;
            }
            this.state._pendingRequests.delete(key);
            throw e;
        }
    }

    // 清理所有 pending 请求
    abortAllRequests() {
        this.state._pendingRequests.forEach(controller => controller.abort());
        this.state._pendingRequests.clear();
    }

    // 获取选中股票（安全访问）
    getSelectedStock() {
        return this.state.selectedStock ? { ...this.state.selectedStock } : null;
    }

    // 设置选中股票
    setSelectedStock(stock) {
        this.set('selectedStock', stock ? { ...stock } : null);
    }

    // 更新股票列表中的某只股票
    updateStock(code, updates) {
        const stocks = this.state.stocks.map(s => 
            s.code === code ? { ...s, ...updates } : s
        );
        this.set('stocks', stocks);
        
        // 如果更新的是当前选中股票，同步更新
        if (this.state.selectedStock?.code === code) {
            this.setSelectedStock({ ...this.state.selectedStock, ...updates });
        }
    }

    // 重置状态
    reset() {
        this.state.stocks = [];
        this.state.selectedStock = null;
        this.state.hotSectors = [];
        this.state.news = [];
        this.state.alerts = [];
        this.state.sentiment = null;
        this.state.portfolioAnalysis = null;
        this.abortAllRequests();
    }
}

// 单例模式 - 使用V2命名避免与现有代码冲突
const stateManagerV2 = new StateManager();

// 挂载到全局供测试
window.StateManager = StateManager;
window.stateManagerV2 = stateManagerV2;

console.log('[StateManager] 模块加载完成 (V2)');
