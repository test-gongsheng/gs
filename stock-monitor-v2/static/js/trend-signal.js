/**
 * 趋势信号UI模块 (Trend Signal UI Module)
 * ======================================
 * 三层展示：
 *   第一层：列表行内嵌状态条（不点就能看）
 *   第二层：详情面板顶部信号面板
 *   第三层：结论区
 * 
 * 数据来源：后端 /api/stocks 附带的 stock.trend_signal 字段
 * 由 utils/trend_signal.py 每日16:50跑批生成 → data/trend_signals.json
 * 
 * 依赖：appState（全局），在 renderStockList / renderStockDetail 中被调用
 */

(function() {
    'use strict';

    // ============ 常量 ============
    const STATE_CONFIG = {
        uptrend: {
            label: '上升趋势',
            color: '#52c41a',
            bgColor: 'rgba(82, 196, 26, 0.15)',
            icon: '🔼'
        },
        range: {
            label: '震荡',
            color: '#faad14',
            bgColor: 'rgba(250, 173, 20, 0.15)',
            icon: '↔️'
        },
        downtrend: {
            label: '单边下跌',
            color: '#ff4d4f',
            bgColor: 'rgba(255, 77, 79, 0.15)',
            icon: '🔽'
        }
    };

    const SIGNAL_STATE_ICON = {
        positive: '✅',
        negative: '⚠️',
        neutral: '➖',
        stale: '📭'
    };

    const POSITION_LIMIT_LABEL = {
        1.0: '100%',
        0.7: '70%',
        0.5: '50%'
    };

    // ============ 工具函数 ============
    function getStateConfig(state) {
        return STATE_CONFIG[state] || STATE_CONFIG.range;
    }

    function formatScore(score) {
        if (score > 0) return '+' + score;
        return String(score);
    }

    function scoreBarWidth(score) {
        // -100~+100 → 0~100%
        return Math.round((score + 100) / 2);
    }

    // ============ 第一层：列表行内嵌状态条 ============
    /**
     * 生成列表行的趋势信号状态条HTML
     * 紧凑模式：只显示色条 + 分数 + 状态标签
     */
    window.renderTrendSignalBar = function(stock) {
        const ts = stock.trend_signal;
        if (!ts) return '';

        const cfg = getStateConfig(ts.state);
        const frozen = ts.strategy_frozen;
        const width = scoreBarWidth(ts.score);

        let frozenTag = '';
        if (frozen) {
            frozenTag = '<span class="ts-frozen-tag">🚫已冻结</span>';
        }

        return `
            <div class="ts-list-bar" title="信号分${formatScore(ts.score)} · ${cfg.label}${frozen ? ' · 中轴策略已冻结' : ''}">
                <div class="ts-score-track">
                    <div class="ts-score-fill" style="width:${width}%;background:${cfg.color};"></div>
                </div>
                <div class="ts-list-info">
                    <span class="ts-state-dot" style="background:${cfg.color};"></span>
                    <span class="ts-score-num" style="color:${cfg.color};">${formatScore(ts.score)}</span>
                    <span class="ts-state-label">${cfg.label}</span>
                    ${frozenTag}
                </div>
            </div>
        `;
    };

    // ============ 第二层+第三层：详情信号面板 ============
    /**
     * 生成详情面板的趋势信号面板HTML
     * 包含：总分仪表 + 五层信号明细 + 仓位上限 + 结论
     */
    window.renderTrendSignalPanel = function(stock) {
        const ts = stock.trend_signal;
        if (!ts) return '';

        const cfg = getStateConfig(ts.state);
        const frozen = ts.strategy_frozen;
        const width = scoreBarWidth(ts.score);
        const limitPct = POSITION_LIMIT_LABEL[ts.position_limit] || (ts.position_limit * 100) + '%';

        // 面板标题
        let headerHtml = `
            <div class="ts-panel-header">
                <div class="ts-panel-title">
                    <i class="fas fa-satellite-dish"></i> 趋势信号
                    <span class="ts-panel-asof">${ts.ma_asof || ''}</span>
                </div>
                <div class="ts-panel-state" style="color:${cfg.color};background:${cfg.bgColor};">
                    ${cfg.icon} ${cfg.label} ${formatScore(ts.score)}
                </div>
            </div>
        `;

        // 冻结警告条
        let freezeHtml = '';
        if (frozen) {
            freezeHtml = `
                <div class="ts-freeze-banner">
                    🚫 <strong>中轴策略已冻结</strong> — 价格触及中轴下方不再触发加仓。持有观望，等待信号改善。
                </div>
            `;
        }

        // 分数仪表
        let gaugeHtml = `
            <div class="ts-gauge-row">
                <div class="ts-gauge-track">
                    <div class="ts-gauge-zone negative" title="单边下跌"></div>
                    <div class="ts-gauge-zone neutral" title="震荡"></div>
                    <div class="ts-gauge-zone positive" title="上升趋势"></div>
                    <div class="ts-gauge-needle" style="left:${width}%;"></div>
                </div>
                <div class="ts-gauge-labels">
                    <span class="neg">-100</span>
                    <span class="zero">0</span>
                    <span class="pos">+100</span>
                </div>
                <div class="ts-gauge-reading">
                    <span class="ts-reading-score" style="color:${cfg.color};">${formatScore(ts.score)}</span>
                    <span class="ts-reading-limit">仓位上限 ${limitPct}</span>
                    <span class="ts-reading-ma">${ts.ma_trend || ''}</span>
                </div>
            </div>
        `;

        // 信号明细
        let signalsHtml = '<div class="ts-signals-list">';
        if (ts.signals && ts.signals.length > 0) {
            ts.signals.forEach(sig => {
                if (sig.weight === 0 && sig.state === 'stale') {
                    // 数据过期，显示但标注
                    signalsHtml += `
                        <div class="ts-signal-item stale">
                            <span class="ts-sig-icon">${SIGNAL_STATE_ICON.stale}</span>
                            <span class="ts-sig-name">${sig.label}</span>
                            <span class="ts-sig-detail">${sig.detail}</span>
                        </div>
                    `;
                } else if (sig.weight === 0 && sig.score === 0) {
                    // 无数据，跳过
                    return;
                } else {
                    const sigColor = sig.score > 10 ? '#52c41a' : sig.score < -10 ? '#ff4d4f' : '#faad14';
                    signalsHtml += `
                        <div class="ts-signal-item">
                            <span class="ts-sig-icon">${SIGNAL_STATE_ICON[sig.state] || '➖'}</span>
                            <span class="ts-sig-name">${sig.label}</span>
                            <span class="ts-sig-score" style="color:${sigColor};">${formatScore(sig.score)}</span>
                            <span class="ts-sig-detail">${sig.detail}</span>
                        </div>
                    `;
                }
            });
        }
        signalsHtml += '</div>';

        // 结论（第三层）
        let conclusionHtml = '';
        if (ts.conclusion) {
            conclusionHtml = `
                <div class="ts-conclusion">
                    <div class="ts-conclusion-label"><i class="fas fa-lightbulb"></i> 策略结论</div>
                    <div class="ts-conclusion-text">${ts.conclusion}</div>
                </div>
            `;
        }

        return `
            <div class="ts-panel">
                ${headerHtml}
                ${freezeHtml}
                ${gaugeHtml}
                ${signalsHtml}
                ${conclusionHtml}
            </div>
        `;
    };

    // ============ 挂载函数 ============
    /**
     * 在详情面板中插入趋势信号面板
     * 调用时机：renderStockDetail() 内部
     */
    window.mountTrendSignalPanel = function(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const stock = window.appState ? window.appState.selectedStock : null;
        if (!stock || !stock.trend_signal) {
            container.style.display = 'none';
            return;
        }

        container.innerHTML = window.renderTrendSignalPanel(stock);
        container.style.display = 'block';
    };

    // ============ 初始化CSS ============
    function injectStyles() {
        if (document.getElementById('ts-styles')) return;

        const css = document.createElement('style');
        css.id = 'ts-styles';
        css.textContent = `
            /* ===== 趋势信号：列表状态条 ===== */
            .ts-list-bar {
                margin-top: 3px;
                width: 100%;
            }
            .ts-score-track {
                height: 3px;
                background: rgba(255,255,255,0.08);
                border-radius: 2px;
                overflow: hidden;
                margin-bottom: 2px;
            }
            .ts-score-fill {
                height: 100%;
                border-radius: 2px;
                transition: width 0.3s ease;
            }
            .ts-list-info {
                display: flex;
                align-items: center;
                gap: 4px;
                font-size: 0.65rem;
                line-height: 1;
            }
            .ts-state-dot {
                width: 6px;
                height: 6px;
                border-radius: 50%;
                flex-shrink: 0;
            }
            .ts-score-num {
                font-weight: 700;
                font-family: 'DIN Alternate', monospace;
                min-width: 24px;
            }
            .ts-state-label {
                color: var(--text-secondary, #9ca3af);
                font-size: 0.65rem;
            }
            .ts-frozen-tag {
                color: #ff4d4f;
                font-size: 0.6rem;
                font-weight: 600;
                margin-left: 2px;
            }

            /* ===== 趋势信号：详情面板 ===== */
            .ts-panel {
                background: var(--bg-card, #1a1f2e);
                border-radius: var(--border-radius, 8px);
                padding: 14px;
                margin-bottom: 12px;
                border: 1px solid rgba(255,255,255,0.06);
            }
            .ts-panel-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
            }
            .ts-panel-title {
                font-size: 0.8rem;
                font-weight: 600;
                color: var(--text-primary, #e8eaed);
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .ts-panel-asof {
                font-size: 0.65rem;
                color: var(--text-secondary, #9ca3af);
                font-weight: 400;
                margin-left: 6px;
            }
            .ts-panel-state {
                font-size: 0.75rem;
                font-weight: 700;
                padding: 3px 10px;
                border-radius: 10px;
            }

            /* 冻结警告 */
            .ts-freeze-banner {
                background: rgba(255, 77, 79, 0.1);
                border: 1px solid rgba(255, 77, 79, 0.3);
                border-radius: 6px;
                padding: 8px 12px;
                margin-bottom: 10px;
                font-size: 0.78rem;
                color: #ff7875;
                line-height: 1.4;
            }

            /* 分数仪表 */
            .ts-gauge-row {
                margin-bottom: 12px;
            }
            .ts-gauge-track {
                position: relative;
                height: 8px;
                border-radius: 4px;
                display: flex;
                overflow: visible;
            }
            .ts-gauge-zone {
                height: 100%;
            }
            .ts-gauge-zone.negative {
                flex: 42.5;
                background: rgba(255, 77, 79, 0.25);
                border-radius: 4px 0 0 4px;
            }
            .ts-gauge-zone.neutral {
                flex: 20;
                background: rgba(250, 173, 20, 0.2);
            }
            .ts-gauge-zone.positive {
                flex: 42.5;
                background: rgba(82, 196, 26, 0.2);
                border-radius: 0 4px 4px 0;
            }
            .ts-gauge-needle {
                position: absolute;
                top: -3px;
                width: 3px;
                height: 14px;
                background: #fff;
                border-radius: 2px;
                transform: translateX(-50%);
                box-shadow: 0 0 4px rgba(255,255,255,0.5);
                transition: left 0.3s ease;
            }
            .ts-gauge-labels {
                display: flex;
                justify-content: space-between;
                font-size: 0.6rem;
                color: var(--text-secondary, #6b7280);
                margin-top: 2px;
                padding: 0 2px;
            }
            .ts-gauge-reading {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-top: 6px;
            }
            .ts-reading-score {
                font-size: 1.1rem;
                font-weight: 700;
                font-family: 'DIN Alternate', monospace;
            }
            .ts-reading-limit {
                font-size: 0.7rem;
                color: var(--text-secondary, #9ca3af);
                background: rgba(255,255,255,0.06);
                padding: 2px 8px;
                border-radius: 4px;
            }
            .ts-reading-ma {
                font-size: 0.7rem;
                color: var(--text-secondary, #9ca3af);
            }

            /* 信号明细 */
            .ts-signals-list {
                display: flex;
                flex-direction: column;
                gap: 4px;
                margin-bottom: 10px;
            }
            .ts-signal-item {
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 5px 8px;
                background: rgba(255,255,255,0.03);
                border-radius: 5px;
                font-size: 0.72rem;
                line-height: 1.3;
            }
            .ts-signal-item.stale {
                opacity: 0.45;
            }
            .ts-sig-icon {
                flex-shrink: 0;
                font-size: 0.7rem;
            }
            .ts-sig-name {
                font-weight: 600;
                color: var(--text-primary, #e8eaed);
                flex-shrink: 0;
                min-width: 52px;
            }
            .ts-sig-score {
                font-weight: 700;
                font-family: monospace;
                min-width: 30px;
                text-align: right;
                flex-shrink: 0;
            }
            .ts-sig-detail {
                color: var(--text-secondary, #9ca3af);
                flex: 1;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            /* 结论 */
            .ts-conclusion {
                background: rgba(24, 144, 255, 0.08);
                border-left: 3px solid var(--accent-blue, #1890ff);
                border-radius: 0 6px 6px 0;
                padding: 8px 12px;
            }
            .ts-conclusion-label {
                font-size: 0.7rem;
                font-weight: 600;
                color: var(--accent-blue, #1890ff);
                margin-bottom: 4px;
            }
            .ts-conclusion-text {
                font-size: 0.78rem;
                color: var(--text-primary, #e8eaed);
                line-height: 1.5;
            }
        `;
        document.head.appendChild(css);
    }

    // 自动注入样式
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', injectStyles);
    } else {
        injectStyles();
    }

    console.log('[trend-signal.js] 模块已加载');
})();
