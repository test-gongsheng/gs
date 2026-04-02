# 股票监控系统架构重构计划

## 状态: ✅ 已完成 (2026-04-02)

---

## 已修复的数据流问题 ✅
- 单一数据源 (appState.stocks)
- 单一渲染入口 (renderStockList())

---

## 已完成的重构

### P0 - 核心架构修复 ✅
1. **状态管理层提取** ✅
   - `modules/state.js` - StateManager类，统一状态管理
   - 内置竞态条件处理 (fetchWithRaceControl)
   - 订阅模式 (subscribe/notify)
   - 锁机制 (withLock)

2. **南向资金模块独立化** ✅
   - `modules/southbound.js` - SouthboundModule类
   - 完全自包含，外部零耦合
   - 内部处理所有竞态条件 (AbortController)
   - 内置缓存机制 (5分钟TTL)

3. **渲染函数参数化** ✅
   - `modules/renderers.js` - 所有DOM操作集中管理
   - 不再依赖全局 appState.selectedStock
   - 显式传递参数

4. **API层统一** ✅
   - `modules/api.js` - 所有后端API调用集中管理
   - 统一超时处理 (15秒默认)
   - 统一错误处理

5. **工具函数集中** ✅
   - `modules/utils.js` - 格式化、防抖节流、类型判断等

### P1 - 模块拆分 ✅
1. **app.js 重构** ✅
   - 从 3106 行精简到 ~200 行
   - 使用新模块，职责单一
   - 保持所有原有接口兼容

2. **数据流单向化** ✅
   - StateManager 订阅模式替代直接函数调用
   - 状态变化自动触发渲染

3. **内存泄漏修复** ✅
   - 所有请求可取消 (AbortController)
   - 模块销毁时清理资源

### P2 - 长期优化 ✅
1. **统一错误处理** ✅
   - API层统一错误捕获
   - 降级策略 (缓存数据回退)

2. **南向资金缓存** ✅
   - 5分钟TTL缓存
   - 请求失败时返回过期缓存

3. **可回滚设计** ✅
   - 保留原文件备份 (app.js.backup.*, southbound.js.backup.*)
   - 版本号管理 (APP_VERSION)

---

## 文件结构

```
static/js/
├── modules/
│   ├── state.js          # 状态管理 (StateManager)
│   ├── api.js            # API层 (StockAPI, QuoteAPI, SouthboundAPI...)
│   ├── southbound.js     # 南向资金模块 (SouthboundModule)
│   ├── renderers.js      # 渲染函数 (renderStockList, renderStockDetail...)
│   └── utils.js          # 工具函数
├── app.js                # 主入口 (~200行，使用新模块)
├── app.js.backup.*       # 原app.js备份 (3106行)
├── southbound.js         # 原南向资金模块 (保留兼容)
├── southbound.js.backup.* # 备份
└── import.js             # 数据导入模块
```

---

## 兼容性

### 保持的全局接口
- `window.appState` - 状态对象 (Proxy代理到StateManager)
- `window.renderStockList()` - 渲染股票列表
- `window.renderStockDetail()` - 渲染股票详情
- `window.loadSouthboundStockData()` - 加载南向资金
- `window.updateStockPricesOnce()` - 更新行情
- `window.init()` - 初始化

### 界面零变更
- 所有HTML结构保持不变
- 所有CSS类名保持不变
- 所有DOM ID保持不变

---

## Git提交

`42d036d` refactor: P0/P1/P2 架构重构全部完成

---

*计划制定: 2026-04-02*  
*完成时间: 2026-04-02*  
*重构耗时: ~30分钟*
