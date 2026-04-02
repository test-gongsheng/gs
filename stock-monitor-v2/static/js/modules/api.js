/**
 * API Layer - 统一数据获取
 * 所有后端API调用集中管理，统一错误处理
 */

const API_BASE = '';
const DEFAULT_TIMEOUT = 15000;

// 统一的fetch封装
async function apiFetch(endpoint, options = {}) {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
    const controller = new AbortController();
    const timeout = options.timeout || DEFAULT_TIMEOUT;
    
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        return await response.json();
    } catch (error) {
        clearTimeout(timeoutId);
        
        if (error.name === 'AbortError') {
            throw new Error('请求超时');
        }
        
        console.error(`[API] ${endpoint} 失败:`, error.message);
        throw error;
    }
}

// 股票相关API
const StockAPI = {
    // 获取所有股票
    async getAll() {
        return apiFetch('/api/stocks');
    },
    
    // 获取单只股票
    async getById(id) {
        return apiFetch(`/api/stocks/${id}`);
    },
    
    // 更新股票
    async update(id, data) {
        return apiFetch(`/api/stocks/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },
    
    // 刷新中轴价格
    async refreshAxisPrice(id) {
        return apiFetch(`/api/stocks/${id}/axis`, { method: 'POST' });
    },
    
    // 刷新沽空数据
    async refreshShortSelling(id) {
        return apiFetch(`/api/stocks/${id}/short-selling`, { method: 'POST' });
    }
};

// 行情相关API
const QuoteAPI = {
    // 获取实时行情
    async getRealtime(codes) {
        const codeList = Array.isArray(codes) ? codes.join(',') : codes;
        return apiFetch(`/api/quotes?codes=${codeList}`);
    },
    
    // 批量获取行情
    async getBatch(codes, batchSize = 6) {
        const results = [];
        for (let i = 0; i < codes.length; i += batchSize) {
            const batch = codes.slice(i, i + batchSize);
            const data = await this.getRealtime(batch);
            results.push(...(Array.isArray(data) ? data : []));
        }
        return results;
    }
};

// 南向资金相关API
const SouthboundAPI = {
    // 获取个股南向资金数据
    async getStockHistory(stockCode, days = 90) {
        return apiFetch(`/api/southbound/stock/${stockCode}?days=${days}`);
    },
    
    // 获取整体南向资金流向
    async getOverall() {
        return apiFetch('/api/southbound/overall');
    }
};

// 市场情绪相关API
const SentimentAPI = {
    // 获取市场情绪
    async get() {
        return apiFetch('/api/market-sentiment');
    },
    
    // 获取热点板块
    async getHotSectors() {
        return apiFetch('/api/hot-sectors');
    }
};

// 新闻相关API
const NewsAPI = {
    // 获取新闻
    async get(limit = 20) {
        return apiFetch(`/api/news?limit=${limit}`);
    }
};

// 持仓分析相关API
const PortfolioAPI = {
    // 获取持仓分析报告
    async getAnalysis() {
        return apiFetch('/api/portfolio-analysis');
    }
};

// 港股沽空相关API
const HKShortAPI = {
    // 获取个股沽空历史
    async getStockHistory(stockCode) {
        return apiFetch(`/api/hk-stock/${stockCode}/short-selling-history`);
    },
    
    // 获取市场整体沽空数据
    async getMarketHistory() {
        return apiFetch('/api/hk-short-selling-history');
    }
};

// 导出所有API
window.API = {
    fetch: apiFetch,
    Stock: StockAPI,
    Quote: QuoteAPI,
    Southbound: SouthboundAPI,
    Sentiment: SentimentAPI,
    News: NewsAPI,
    Portfolio: PortfolioAPI,
    HKShort: HKShortAPI
};

export { apiFetch, StockAPI, QuoteAPI, SouthboundAPI, SentimentAPI, NewsAPI, PortfolioAPI, HKShortAPI };
export default window.API;
