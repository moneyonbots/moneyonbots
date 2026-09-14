/* Intraday scanner. It only visualises validated AI signal records. */
(function () {
    const MODES = {
        '1m': { timeframe: '1M', resolution: '1', seconds: 60, interval: 15 * 1000, label: '1-minute chart · Ultra Scalp', desc: 'every 15 seconds' },
        '5m': { timeframe: '5M', resolution: '5', seconds: 300, interval: 30 * 1000, label: '5-minute chart · Scalping', desc: 'every 30 seconds' },
        '15m': { timeframe: '15M', resolution: '15', seconds: 900, interval: 45 * 1000, label: '15-minute chart · Momentum', desc: 'every 45 seconds' },
        '30m': { timeframe: '30M', resolution: '30', seconds: 1800, interval: 60 * 1000, label: '30-minute chart · Intraday', desc: 'every minute' },
        '1h': { timeframe: '1H', resolution: '60', seconds: 3600, interval: 60 * 1000, label: '1-hour chart · Day Trading', desc: 'every minute' },
        '4h': { timeframe: '4H', resolution: '240', seconds: 14400, interval: 2 * 60 * 1000, label: '4-hour chart · Swing Entry', desc: 'every 2 minutes' },
        '1d': { timeframe: '1D', resolution: 'D', seconds: 86400, interval: 5 * 60 * 1000, label: 'Daily chart · Swing Trading', desc: 'every 5 minutes' },
        // Legacy aliases
        'scalp': { timeframe: '5M', resolution: '5', seconds: 300, interval: 30 * 1000, label: '5-minute chart · Scalping', desc: 'every 30 seconds' },
        'day': { timeframe: '1H', resolution: '60', seconds: 3600, interval: 60 * 1000, label: '1-hour chart · Day Trading', desc: 'every minute' },
        'swing': { timeframe: '1D', resolution: 'D', seconds: 86400, interval: 5 * 60 * 1000, label: 'Daily chart · Swing Trading', desc: 'every 5 minutes' },
    };
    // Internal symbol names are already in correct Deriv API format
    function formatSymbol(sym) {
        return sym || '';
    }
    const TRADE_ARROW_COLORS = { Buy: '#16a34a', Sell: '#dc2626' };

    function init() {
        const fab = document.getElementById('scanner-fab');
        const modal = document.getElementById('scanner-modal');
        const close = document.getElementById('scanner-close');
        const scanButton = document.getElementById('scan-chart-btn');
        const autoButton = document.getElementById('auto-scan-btn');
        const status = document.getElementById('scanner-status');
        const summary = document.getElementById('scanner-summary');
        const entries = document.getElementById('scanner-entries');
        const modeLabel = document.getElementById('scanner-mode-label');
        const modeNote = document.getElementById('scanner-note');
        const activeSymbolEl = document.getElementById('scanner-active-symbol');
        const modeButtons = Array.from(document.querySelectorAll('[data-scanner-mode]'));
        if (!fab || !modal || !scanButton || !autoButton) return;

        let scanning = false;
        let shapes = [];
        let timer = null;
        let autoEnabled = localStorage.getItem('aiScannerAutoScan') === 'true';
        let rawMode = localStorage.getItem('aiScannerMode') || '1h';
        if (rawMode === 'day') rawMode = '1h';
        else if (rawMode === 'scalp') rawMode = '5m';
        else if (rawMode === 'swing') rawMode = '1d';
        let mode = MODES[rawMode] ? rawMode : '1h';

        const scannerSymbol = symbol => formatSymbol(symbol);
        const format = value => Number(value).toFixed(Number(value) < 10 ? 5 : 2);
        const escape = value => String(value || '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
        const cleanName = value => String(value || 'AI Signal').replace(/^\s*QATraders:\s*/i, '').trim() || 'AI Signal';

        function updateSymbolBadge() {
            if (!activeSymbolEl) return;
            const currentSym = window.currentChartSymbol;
            if (currentSym) {
                activeSymbolEl.textContent = formatSymbol(currentSym);
                activeSymbolEl.title = `Current Chart Market: ${currentSym}`;
            } else {
                activeSymbolEl.textContent = 'Active Market';
            }
        }

        function setModal(open) {
            modal.classList.toggle('open', open);
            modal.setAttribute('aria-hidden', String(!open));
            if (open) {
                updateSymbolBadge();
                setModeResolution();
            }
        }

        function setModeResolution() {
            if (!window.tradingViewWidget) return;
            window.tradingViewWidget.onChartReady(() => {
                try { window.tradingViewWidget.activeChart().setResolution(MODES[mode].resolution); } catch (_) { /* chart still loading */ }
            });
        }

        function removeShapes(chart) {
            shapes.forEach(id => { try { chart.removeEntity(id); } catch (_) { /* already removed */ } });
            shapes = [];
        }

        function clearPlots() {
            if (!window.tradingViewWidget || !shapes.length) return;
            window.tradingViewWidget.onChartReady(() => removeShapes(window.tradingViewWidget.activeChart()));
        }

        function validPlan(signal) {
            const entry = Number(signal.price), sl = Number(signal.stop_loss), tp = Number(signal.take_profit);
            if (!Number.isFinite(entry) || !Number.isFinite(sl) || !Number.isFinite(tp)) return false;
            return signal.direction === 'Buy' ? sl < entry && tp > entry : signal.direction === 'Sell' && sl > entry && tp < entry;
        }

        function markerPrice(signal) {
            const entry = Number(signal.price), risk = Math.abs(entry - Number(signal.stop_loss));
            const offset = Math.max(risk * 0.6, Math.abs(entry) * 0.00001, 0.000001);
            return signal.direction === 'Buy' ? entry - offset : entry + offset;
        }

        function barSeconds() {
            return (MODES[mode] && MODES[mode].seconds) ? MODES[mode].seconds : 3600;
        }

        function uniqueHistory(history, active) {
            const usedBars = new Set();
            const activeTime = active ? Math.floor(new Date(active.created_at || active.updated_at).getTime() / 1000) : null;
            const activeBar = Number.isFinite(activeTime) ? Math.floor(activeTime / barSeconds()) : null;
            return history.filter(signal => {
                const time = Math.floor(new Date(signal.created_at || signal.updated_at).getTime() / 1000);
                const bar = Math.floor(time / barSeconds());
                if (!Number.isFinite(time) || bar === activeBar || usedBars.has(bar)) return false;
                usedBars.add(bar);
                return true;
            }).slice(0, 6);
        }

        function addShape(chart, point, options) {
            shapes.push(chart.createShape(point, options));
        }

        function addTradeArrow(chart, signal, time) {
            addShape(chart, { time, price: markerPrice(signal) }, {
                shape: signal.direction === 'Buy' ? 'arrow_up' : 'arrow_down',
                lock: true,
                disableSelection: false,
                disableUndo: false,
                showInObjectsTree: true,
                overrides: {
                    color: TRADE_ARROW_COLORS[signal.direction] || '#ffffff',
                    fontsize: 9,
                    linewidth: 2,
                }
            });
        }

        function plotActive(signal, expectedSymbol) {
            if (!window.tradingViewWidget) return;
            window.tradingViewWidget.onChartReady(() => {
                const chart = window.tradingViewWidget.activeChart();
                if (scannerSymbol(chart.symbol()) !== expectedSymbol) return;
                removeShapes(chart);
                const time = Math.floor(new Date(signal.created_at || signal.updated_at || Date.now()).getTime() / 1000);
                const digits = Number(signal.price) < 10 ? 5 : 2;
                const level = (price, label, color) => addShape(chart, { time, price: Number(price) }, {
                    shape: 'horizontal_line', lock: true, disableSelection: false, disableUndo: false,
                    showInObjectsTree: true, text: `${label} ${Number(price).toFixed(digits)}`,
                    overrides: { linecolor: color, linewidth: 2, textcolor: color }
                });
                level(signal.price, 'Entry', '#2563eb');
                level(signal.take_profit, 'Take Profit', '#16a34a');
                level(signal.stop_loss, 'Stop Loss', '#dc2626');
                addTradeArrow(chart, signal, time);
            });
        }

        function plotHistory(history, expectedSymbol) {
            if (!window.tradingViewWidget) return;
            window.tradingViewWidget.onChartReady(() => {
                const chart = window.tradingViewWidget.activeChart();
                if (scannerSymbol(chart.symbol()) !== expectedSymbol) return;
                history.forEach(signal => {
                    const time = Math.floor(new Date(signal.created_at || signal.updated_at).getTime() / 1000);
                    if (!Number.isFinite(time)) return;
                    addTradeArrow(chart, signal, time);
                });
            });
        }

        function render(active, history, symbol) {
            if (!entries) return;
            entries.innerHTML = '';
            if (!active && !history.length) {
                if (summary) {
                    summary.style.display = 'block';
                    summary.className = 'scanner-summary scanner-summary-empty';
                    summary.innerHTML = `
                        <div class="scanner-empty-box">
                            <div class="scanner-empty-icon">
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                                    <circle cx="12" cy="12" r="9"></circle>
                                    <path d="M12 7v5l3 3"></path>
                                </svg>
                            </div>
                            <div class="scanner-empty-title">No Validated Setup</div>
                            <div class="scanner-empty-desc">No confirmed ${MODES[mode] ? MODES[mode].timeframe : mode} setup for <strong>${escape(symbol)}</strong> right now. Auto Scan will monitor incoming candles.</div>
                        </div>`;
                }
                return;
            }

            if (active) {
                const entry = Number(active.price), sl = Number(active.stop_loss), tp = Number(active.take_profit);
                const risk = Math.abs(entry - sl);
                const rr = risk > 0 ? Math.abs(tp - entry) / risk : 0;
                const isBuy = active.direction === 'Buy';
                const dirClass = isBuy ? 'buy' : 'sell';
                const dirArrow = isBuy ? '▲ BUY' : '▼ SELL';

                if (summary) {
                    summary.style.display = 'block';
                    summary.className = `scanner-summary scanner-summary-${dirClass}`;
                    summary.innerHTML = `
                        <div class="scanner-hud-card ${dirClass}">
                            <div class="scanner-hud-header">
                                <div class="scanner-hud-left">
                                    <span class="scanner-dir-chip ${dirClass}">${dirArrow}</span>
                                    <span class="scanner-pattern-name">${escape(cleanName(active.pattern || active.entry_type))}</span>
                                </div>
                                <span class="scanner-hud-symbol">${escape(symbol)}</span>
                            </div>
                            <div class="scanner-hud-grid">
                                <div class="scanner-hud-metric entry">
                                    <span class="hud-lbl">ENTRY</span>
                                    <span class="hud-val">${format(entry)}</span>
                                </div>
                                <div class="scanner-hud-metric tp">
                                    <span class="hud-lbl">TAKE PROFIT</span>
                                    <span class="hud-val">${format(tp)}</span>
                                </div>
                                <div class="scanner-hud-metric sl">
                                    <span class="hud-lbl">STOP LOSS</span>
                                    <span class="hud-val">${format(sl)}</span>
                                </div>
                                <div class="scanner-hud-metric rr">
                                    <span class="hud-lbl">R : R</span>
                                    <span class="hud-val">1 : ${rr.toFixed(2)}</span>
                                </div>
                            </div>
                        </div>
                    `;
                }

                const card = document.createElement('button');
                card.type = 'button';
                card.className = `scanner-entry scanner-active-card ${dirClass}`;
                card.innerHTML = `
                    <div class="scanner-entry-header">
                        <div class="scanner-entry-left">
                            <span class="scanner-live-badge"><span class="scanner-live-dot"></span>ACTIVE SETUP</span>
                            <span class="scanner-entry-type ${dirClass}">${escape(cleanName(active.pattern || active.entry_type))}</span>
                        </div>
                        <span class="scanner-plot-pill">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
                            Plotted
                        </span>
                    </div>
                    <div class="scanner-entry-details">
                        <span>Entry: <strong class="price-blue">${format(entry)}</strong> · TP: <strong class="price-green">${format(tp)}</strong> · SL: <strong class="price-red">${format(sl)}</strong></span>
                        <span class="scanner-entry-hint">Tap to focus & replot on TradingView chart</span>
                    </div>
                `;
                card.addEventListener('click', () => plotActive(active, symbol));
                entries.appendChild(card);
            } else if (summary) {
                summary.style.display = 'none';
            }

            if (history.length) {
                const histHeader = document.createElement('div');
                histHeader.className = 'scanner-history-heading';
                histHeader.textContent = 'RECENT HISTORICAL SETUPS';
                entries.appendChild(histHeader);

                history.slice(0, 8).forEach(signal => {
                    const card = document.createElement('div');
                    const isBuy = signal.direction === 'Buy';
                    const dirClass = isBuy ? 'buy' : 'sell';
                    const pnlHit = String(signal.pnl_hit || 'closed').toLowerCase();
                    let outcomeBadge = 'CLOSED';
                    let outcomeClass = 'neutral';
                    if (pnlHit.includes('tp')) { outcomeBadge = 'TP HIT'; outcomeClass = 'tp'; }
                    else if (pnlHit.includes('sl')) { outcomeBadge = 'SL HIT'; outcomeClass = 'sl'; }

                    card.className = `scanner-entry scanner-history-entry ${dirClass}`;
                    card.innerHTML = `
                        <div class="scanner-entry-header">
                            <div class="scanner-entry-left">
                                <span class="scanner-hist-dir ${dirClass}">${escape(signal.direction)}</span>
                                <span class="scanner-entry-type">${escape(cleanName(signal.pattern || signal.entry_type))}</span>
                            </div>
                            <span class="scanner-outcome-badge ${outcomeClass}">${outcomeBadge}</span>
                        </div>
                        <div class="scanner-history-details">
                            <span>Entry: <strong class="price-blue">${format(signal.price)}</strong></span>
                            <span>TP: <strong class="price-green">${format(signal.take_profit)}</strong></span>
                            <span>SL: <strong class="price-red">${format(signal.stop_loss)}</strong></span>
                        </div>
                    `;
                    entries.appendChild(card);
                });
            }
        }

        async function scan() {
            if (scanning) return;
            const rawSymbol = window.currentChartSymbol;
            updateSymbolBadge();
            if (!rawSymbol) {
                if (status) {
                    status.innerHTML = `<span class="scanner-status-icon">▲</span><span class="scanner-status-text">Wait for chart market to finish loading, then scan again.</span>`;
                }
                return;
            }
            const symbol = scannerSymbol(rawSymbol);
            scanning = true;
            scanButton.disabled = true;
            scanButton.classList.add('is-scanning');
            modal.classList.add('is-scanning');
            clearPlots();
            setModeResolution();

            const scanBtnText = scanButton.querySelector('.scan-btn-text');
            if (scanBtnText) scanBtnText.textContent = 'Scanning…';

            if (status) {
                status.innerHTML = `<span class="scanner-status-icon"><span class="scanner-mini-spin"></span></span><span class="scanner-status-text">Scanning <strong>${escape(symbol)}</strong> for ${MODES[mode] ? MODES[mode].timeframe : mode} patterns…</span>`;
            }

            try {
                const query = `symbol=${encodeURIComponent(symbol)}&timeframe=${MODES[mode].timeframe}`;
                const [activeResponse, historyResponse] = await Promise.all([
                    fetch(`/api/signals/active/?${query}`),
                    fetch(`/api/signals/history/?${query}&limit=200`)
                ]);
                if (!activeResponse.ok || !historyResponse.ok) throw new Error('Signal service unavailable');
                const activeData = await activeResponse.json();
                const historyData = await historyResponse.json();
                const active = (activeData.signals || []).find(validPlan) || null;
                const rawHistory = (historyData.signals || []).filter(signal => ['Buy', 'Sell'].includes(signal.direction) && validPlan(signal));
                const history = uniqueHistory(rawHistory, active);
                if (active) plotActive(active, symbol);
                plotHistory(history, symbol);
                render(active, history, symbol);

                if (status) {
                    if (active) {
                        status.innerHTML = `<span class="scanner-status-icon">◈</span><span class="scanner-status-text">${MODES[mode].label} setup plotted on chart.</span>`;
                    } else {
                        status.innerHTML = `<span class="scanner-status-icon">◇</span><span class="scanner-status-text">No validated ${MODES[mode] ? MODES[mode].timeframe : mode} setup right now on ${escape(symbol)}.</span>`;
                    }
                }
            } catch (error) {
                console.error('Scanner error:', error);
                if (status) {
                    status.innerHTML = `<span class="scanner-status-icon">▲</span><span class="scanner-status-text">${MODES[mode].label} signal data unavailable. Try again shortly.</span>`;
                }
                if (summary) {
                    summary.innerHTML = `<div class="scanner-empty-box"><div class="scanner-empty-title">Service Reconnecting</div><div class="scanner-empty-desc">Signal engine is synchronizing. Please retry in a few moments.</div></div>`;
                }
                if (entries) entries.innerHTML = '';
            } finally {
                scanning = false;
                scanButton.disabled = false;
                scanButton.classList.remove('is-scanning');
                modal.classList.remove('is-scanning');
                if (scanBtnText) scanBtnText.textContent = 'Scan Chart';
            }
        }

        function updateAuto() {
            autoButton.classList.toggle('active', autoEnabled);
            autoButton.setAttribute('aria-pressed', String(autoEnabled));
            const autoText = autoButton.querySelector('.auto-btn-text');
            if (autoText) {
                autoText.textContent = autoEnabled ? 'Auto: On' : 'Auto: Off';
            } else {
                autoButton.textContent = autoEnabled ? 'Auto: On' : 'Auto: Off';
            }
        }

        function setAuto(enabled) {
            autoEnabled = enabled;
            localStorage.setItem('aiScannerAutoScan', String(enabled));
            updateAuto();
            if (timer) clearInterval(timer);
            timer = null;
            if (enabled) {
                scan();
                timer = setInterval(scan, MODES[mode].interval);
            }
        }

        function setMode(nextMode) {
            let targetMode = nextMode;
            if (targetMode === 'day') targetMode = '1h';
            else if (targetMode === 'scalp') targetMode = '5m';
            else if (targetMode === 'swing') targetMode = '1d';
            mode = MODES[targetMode] ? targetMode : '1h';
            localStorage.setItem('aiScannerMode', mode);
            modeButtons.forEach(button => button.classList.toggle('active', button.dataset.scannerMode === mode));
            const activeMode = MODES[mode] || MODES['1h'];
            if (modeLabel) modeLabel.textContent = `${activeMode.label} · validated Entry / TP / SL`;
            if (modeNote) modeNote.textContent = `Auto Scan checks the current market ${activeMode.desc}. It does not place trades.`;
            clearPlots();
            setModeResolution();
            if (autoEnabled) setAuto(true);
        }

        fab.addEventListener('click', () => setModal(!modal.classList.contains('open')));
        close.addEventListener('click', () => setModal(false));
        const backdrop = modal.querySelector('.scanner-modal-backdrop');
        if (backdrop) backdrop.addEventListener('click', () => setModal(false));
        scanButton.addEventListener('click', scan);
        autoButton.addEventListener('click', () => setAuto(!autoEnabled));
        modeButtons.forEach(button => button.addEventListener('click', () => setMode(button.dataset.scannerMode)));
        window.addEventListener('chart-symbol-changed', () => {
            updateSymbolBadge();
            clearPlots();
            if (autoEnabled) setTimeout(scan, 350);
        });
        document.addEventListener('keydown', event => { if (event.key === 'Escape') setModal(false); });

        updateSymbolBadge();
        setMode(mode);
        updateAuto();
        if (autoEnabled) setAuto(true);
        window.aiScannerActions = { scan, setAuto, setMode, clearPlots };
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();

