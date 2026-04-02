/**
 * Utils - 工具函数
 */

// 格式化数字
function formatNumber(num, decimals = 2) {
    if (num === null || num === undefined || isNaN(num)) return '--';
    return Number(num).toFixed(decimals);
}

// 格式化金额（万/亿）
function formatMoney(num, unit = '') {
    if (num === null || num === undefined || isNaN(num)) return '--';
    
    const n = Number(num);
    if (Math.abs(n) >= 100000000) {
        return (n / 100000000).toFixed(2) + '亿' + unit;
    } else if (Math.abs(n) >= 10000) {
        return (n / 10000).toFixed(2) + '万' + unit;
    }
    return n.toFixed(2) + unit;
}

// 格式化涨跌幅
function formatChange(num) {
    if (num === null || num === undefined || isNaN(num)) return '--';
    const n = Number(num);
    const sign = n >= 0 ? '+' : '';
    return `${sign}${n.toFixed(2)}%`;
}

// 格式化日期
function formatDate(date, format = 'YYYY-MM-DD') {
    const d = new Date(date);
    if (isNaN(d.getTime())) return '--';
    
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    
    return format
        .replace('YYYY', year)
        .replace('MM', month)
        .replace('DD', day);
}

// 防抖
function debounce(fn, delay) {
    let timer = null;
    return function(...args) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

// 节流
function throttle(fn, limit) {
    let inThrottle = false;
    return function(...args) {
        if (!inThrottle) {
            fn.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// 判断是否为港股
function isHKStock(code) {
    if (!code) return false;
    // 5位数字开头是0或1-9的港股
    return /^0?\d{4,5}$/.test(code) && !code.startsWith('6') && !code.startsWith('3') && !code.startsWith('0');
}

// 判断是否为A股
function isAStock(code) {
    if (!code) return false;
    return /^[036]\d{5}$/.test(code);
}

// 深拷贝
function deepClone(obj) {
    if (obj === null || typeof obj !== 'object') return obj;
    if (obj instanceof Date) return new Date(obj);
    if (Array.isArray(obj)) return obj.map(deepClone);
    const cloned = {};
    for (const key in obj) {
        if (obj.hasOwnProperty(key)) {
            cloned[key] = deepClone(obj[key]);
        }
    }
    return cloned;
}

// 合并对象（浅合并）
function merge(target, ...sources) {
    return Object.assign({}, target, ...sources);
}

// 安全的localStorage操作
const Storage = {
    get(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : defaultValue;
        } catch (e) {
            return defaultValue;
        }
    },
    set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
            return true;
        } catch (e) {
            console.error('[Storage] 保存失败:', e);
            return false;
        }
    },
    remove(key) {
        try {
            localStorage.removeItem(key);
            return true;
        } catch (e) {
            return false;
        }
    },
    clear() {
        try {
            localStorage.clear();
            return true;
        } catch (e) {
            return false;
        }
    }
};

// 挂载到全局
window.Utils = {
    formatNumber,
    formatMoney,
    formatChange,
    formatDate,
    debounce,
    throttle,
    isHKStock,
    isAStock,
    deepClone,
    merge,
    Storage
};

console.log('[Utils] 模块加载完成');
