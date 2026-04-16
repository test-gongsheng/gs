# 股票监控系统数据流梳理与彻底修复方案

## 当前问题总结

1. **个股分析弹窗显示错误数据**
   - 当前价格显示为持仓成本（7.20）而非实际股价（16.44）
   - 中轴价格显示错误（16.70 vs 16.82）
   - 偏离度计算错误

2. **数据不一致的根本原因**
   - 多个数据源：后端API、前端缓存、localStorage、内存状态
   - 没有统一的数据同步机制
   - 缓存污染后无法自动恢复

## 数据流全链路分析

```
[数据源层]
  ├── 实时行情 API (腾讯/东方财富)
  ├── 历史行情数据 (akshare)
  └── 用户持仓数据 (stocks.json)

[后端服务层]
  ├── /api/stocks - 返回持仓列表
  ├── /api/quotes - 返回实时行情
  ├── /api/axis-price - 计算中轴价格
  └── /api/portfolio-analysis - 返回分析报告

[前端状态层]
  ├── appState.stocks - 内存中的股票列表
  ├── appState.portfolioAnalysis - 分析报告缓存
  ├── localStorage.import_data_last - 本地备份
  └── localStorage.app_version - 版本标记

[UI展示层]
  ├── 股票列表 (stockList)
  ├── 个股详情弹窗 (stockAnalysisDetailModal)
  └── 持仓健康度面板 (portfolioAnalysisSection)
```

## 问题定位

### 问题1: stocks.json 中的 current_price 字段
- 后端 `/api/stocks` 返回的 `current_price` 可能是旧的
- 前端 `loadStocks()` 用这个值初始化 `appState.stocks`
- 但实时行情应该来自 `/api/quotes`

### 问题2: 分析报告数据流
- `update_portfolio_analysis.py` 生成报告时是正确的
- 但 `showStockAnalysisDetail()` 可能使用了旧的缓存
- 或者 `stockAnalysis.current_price` 被错误赋值

### 问题3: 多个缓存层级
- localStorage 缓存
- appState 内存缓存
- 浏览器 HTTP 缓存
- 没有统一的失效策略

## 彻底修复方案

### 1. 数据源唯一化
- 实时价格只能从 `/api/quotes` 获取
- 中轴价格只能从 `/api/axis-price` 获取
- 分析报告只能从 `/api/portfolio-analysis` 获取
- 禁止从 `appState.stocks` 获取价格数据

### 2. 强制实时加载
- 所有弹窗/详情页面，每次都从 API 重新加载
- 不使用任何前端缓存
- 添加数据新鲜度验证（超过5分钟强制刷新）

### 3. 数据校验机制
- 价格合理性检查（不能等于持仓成本）
- 偏离度计算验证
- 异常数据自动标记并重新获取

### 4. 缓存清理策略
- 版本号变化时清除所有缓存
- 每日开盘前自动清除
- 数据异常时自动清除并重载

## 具体修复清单

### 后端修复
- [ ] 确保 `/api/stocks` 返回的 current_price 是最新的
- [ ] `/api/portfolio-analysis` 添加数据生成时间戳
- [ ] 添加数据一致性校验接口

### 前端修复
- [ ] 删除所有从 appState.stocks 读取价格的代码
- [ ] showStockAnalysisDetail 强制实时 API 调用
- [ ] 添加价格数据校验（price != avg_cost）
- [ ] 版本号 3.3.0，彻底清除所有缓存

### 监控与调试
- [ ] 添加详细的数据流日志
- [ ] 异常数据自动上报
- [ ] 数据新鲜度显示

## 验证步骤
1. 清除所有缓存，重新加载页面
2. 检查股票列表显示的价格是否正确
3. 点击个股，检查弹窗显示的价格
4. 对比后端 API 返回的数据
5. 检查控制台是否有数据不一致警告
