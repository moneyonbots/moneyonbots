/*
 * Live Signals panel: displays active trading signals with real-time updates.
 * Loads initial signals from API and updates via WebSocket.
 * Also handles Signal History section for completed TP/SL signals.
 * Prices update per tick via Deriv WebSocket.
 */
(function () {
    const container = document.getElementById("live-signals-body");
    const historyContainer = document.getElementById("signal-history-body");
    if (!container) return;

    const markets = window.AVAILABLE_MARKETS || {};
    const lastPrices = {};

    function fmt(n, digits = 2) {
        return n === null || n === undefined ? "—" : Number(n).toFixed(digits);
    }

    function renderSignalRow(signal) {
        const direction = signal.direction;
        const directionClass = direction.toLowerCase();
        const strengthPct = (signal.signal_strength * 100).toFixed(0);
        const priceColor = direction === 'Buy' ? 'price-up' : 'price-down';
        const htfAdvice = signal.htf_advice || '';
        const htfClass = htfAdvice.includes('Caution') ? 'htf-warning' : 'htf-good';
        
        return `
            <tr data-symbol="${signal.symbol}" class="signal-row ${directionClass}">
                <td class="signal-market">${signal.market_name}</td>
                <td class="signal-direction ${directionClass}">${direction}</td>
                <td class="signal-price ${priceColor}">${fmt(signal.price, 5)}</td>
                <td class="signal-entry">${fmt(signal.entry || signal.price, 5)}</td>
                <td class="signal-sl">${fmt(signal.stop_loss, 5)}</td>
                <td class="signal-tp">${fmt(signal.take_profit, 5)}</td>
                <td class="signal-strength">${strengthPct}%</td>
                <td class="signal-rr">${fmt(signal.risk_reward, 2)}</td>
                <td class="signal-htf ${htfClass}">${htfAdvice || '—'}</td>
            </tr>
        `;
    }

    function renderHistoryRow(signal) {
        const direction = signal.direction;
        const directionClass = direction.toLowerCase();
        const resultClass = signal.pnl_hit === 'tp' ? 'result-win' : 'result-loss';
        const pnlClass = signal.actual_pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
        
        return `
            <tr data-symbol="${signal.symbol}" class="history-row ${directionClass}">
                <td class="signal-market">${signal.market_name}</td>
                <td class="signal-direction ${directionClass}">${direction}</td>
                <td class="signal-entry">${fmt(signal.price, 5)}</td>
                <td class="signal-exit">${fmt(signal.exit_price, 5)}</td>
                <td class="signal-sl">${fmt(signal.stop_loss, 5)}</td>
                <td class="signal-tp">${fmt(signal.take_profit, 5)}</td>
                <td class="signal-result ${resultClass}">${signal.pnl_hit.toUpperCase()}</td>
                <td class="signal-pnl ${pnlClass}">${fmt(signal.actual_pnl, 1)} pips</td>
                <td class="signal-rr">${fmt(signal.risk_reward, 2)}</td>
            </tr>
        `;
    }

    function updateSignalTable(signals) {
        if (!signals || signals.length === 0) {
            container.innerHTML = `
                <tr class="signal-history-empty">
                    <td colspan="9">
                        <div class="loading-container">
                            <span class="loading-spinner"></span>
                            <span class="loading-text">Waiting for live signals…</span>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        const rows = signals.map(renderSignalRow).join("");
        container.innerHTML = rows;
    }

    function removeSignal(symbol) {
        const row = container.querySelector(`tr[data-symbol="${symbol}"]`);
        if (row) row.remove();
        const count = container.querySelectorAll(".signal-row").length;
        if (count === 0) {
            container.innerHTML = `
                <tr class="signal-history-empty">
                    <td colspan="9">
                        <div class="loading-container">
                            <span class="loading-spinner"></span>
                            <span class="loading-text">Waiting for live signals…</span>
                        </div>
                    </td>
                </tr>
            `;
        }
        updateCount(count);
    }

    function addSignal(signal) {
        const existing = container.querySelector(`tr[data-symbol="${signal.symbol}"]`);
        if (existing) existing.remove();

        const emptyRow = container.querySelector(".signal-history-empty");
        if (emptyRow) emptyRow.remove();

        container.insertAdjacentHTML("afterbegin", renderSignalRow(signal));
        updateCount(container.querySelectorAll(".signal-row").length);
        
        // Subscribe to this symbol for price updates
        if (derivWs && derivWs.readyState === WebSocket.OPEN) {
            const formatted = formatSymbol(signal.symbol);
            derivWs.send(JSON.stringify({ ticks: formatted, subscribe: 1, req_id: reqId++ }));
        }
    }

    function addToHistory(signal) {
        if (!historyContainer) return;
        
        const emptyRow = historyContainer.querySelector(".signal-history-empty");
        if (emptyRow) emptyRow.remove();

        historyContainer.insertAdjacentHTML("afterbegin", renderHistoryRow(signal));
        
        // Limit history to 50 entries
        const rows = historyContainer.querySelectorAll(".history-row");
        if (rows.length > 50) {
            rows[rows.length - 1].remove();
        }
        
        updateHistoryCount(historyContainer.querySelectorAll(".history-row").length);
    }

    // Load initial signals
    async function loadInitialSignals() {
        try {
            const response = await fetch("/api/signals/active/");
            const data = await response.json();
            if (data.signals) {
                updateSignalTable(data.signals);
                updateCount(data.signals.length);
            }
        } catch (error) {
            console.error("Failed to load initial signals:", error);
        }
    }

    // Load signal history
    async function loadSignalHistory() {
        if (!historyContainer) return;
        try {
            const response = await fetch("/api/signals/history/");
            const data = await response.json();
            if (data.signals) {
                updateHistoryTable(data.signals);
                updateHistoryCount(data.signals.length);
            }
        } catch (error) {
            console.error("Failed to load signal history:", error);
        }
    }

    function updateHistoryTable(signals) {
        if (!historyContainer) return;
        if (!signals || signals.length === 0) {
            historyContainer.innerHTML = `
                <tr class="signal-history-empty">
                    <td colspan="9">No completed signals yet</td>
                </tr>
            `;
            return;
        }

        const rows = signals.map(renderHistoryRow).join("");
        historyContainer.innerHTML = rows;
    }

    function updateHistoryCount(count) {
        const countEl = document.getElementById("history-count");
        if (countEl) {
            countEl.textContent = count;
        }
    }

    function updateCount(count) {
        const countEl = document.getElementById("live-signals-count");
        if (countEl) {
            countEl.textContent = count;
        }
    }

    function updateSignalPrice(symbol, price) {
        const row = container.querySelector(`tr[data-symbol="${symbol}"]`);
        if (!row) return;

        const priceEl = row.querySelector(".signal-price");
        const prev = lastPrices[symbol];
        const digits = price < 10 ? 5 : 2;
        
        priceEl.textContent = fmt(price, digits);
        priceEl.classList.remove("price-up", "price-down");
        
        if (prev !== undefined) {
            priceEl.classList.add(price >= prev ? "price-up" : "price-down");
        }
        
        lastPrices[symbol] = price;
    }

    // WebSocket connection for real-time updates
    function connectWebSocket() {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(`${proto}://${window.location.host}/ws/analysis/`);

        ws.onopen = () => {
            console.log("Live signals WebSocket connected");
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                if (data.type === "signal" && data.signal) {
                    addSignal(data.signal);
                } else if (data.type === "signal_completed" && data.signal) {
                    removeSignal(data.signal.symbol);
                    addToHistory(data.signal);
                }
            } catch (error) {
                console.error("Error parsing WebSocket message:", error);
            }
        };

        ws.onclose = () => {
            console.log("Live signals WebSocket disconnected, reconnecting...");
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = (error) => {
            console.error("Live signals WebSocket error:", error);
            ws.close();
        };
    }

    // Deriv WebSocket for real-time price updates
    // Internal symbol names are already in correct Deriv API format
    function formatSymbol(sym) {
        // No conversion needed - internal names match API format
        return sym;
    }

    let derivWs = null;
    let reqId = 1;

    function connectDerivWebSocket() {
        derivWs = new WebSocket(`wss://ws.binaryws.com/websockets/v3?app_id=${window.DERIV_APP_ID}`);
        
        derivWs.onopen = () => {
            console.log("Deriv WebSocket connected for live signals");
            
            // Only authorize if we have a valid non-empty token
            if (window.DERIV_API_TOKEN && window.DERIV_API_TOKEN.trim() !== "") {
                derivWs.send(JSON.stringify({ authorize: window.DERIV_API_TOKEN }));
            }
            
            // Subscribe to all active signal symbols
            subscribeToActiveSignals();
        };

        derivWs.onmessage = (evt) => {
            const data = JSON.parse(evt.data);
            
            // Handle authorization response
            if (data.msg_type === "authorize") {
                if (data.error) {
                    console.error('Live signals authorization error:', data.error);
                } else {
                    console.log('Live signals authorization successful');
                }
                return;
            }
            
            if (data.error || !data.tick) return;
            
            const symbol = data.tick.symbol;
            // Map back to our internal symbol
            const internalSymbol = Object.keys(SYMBOL_MAP).find(key => SYMBOL_MAP[key] === symbol) || symbol;
            
            // Update price if this symbol has an active signal
            updateSignalPrice(internalSymbol, data.tick.quote);
        };

        derivWs.onclose = () => {
            console.log("Deriv WebSocket disconnected, reconnecting...");
            setTimeout(connectDerivWebSocket, 4000);
        };

        derivWs.onerror = () => derivWs.close();
    }

    function subscribeToActiveSignals() {
        if (!derivWs || derivWs.readyState !== WebSocket.OPEN) return;
        
        // Get all symbols with active signals
        const activeSymbols = Array.from(container.querySelectorAll(".signal-row"))
            .map(row => row.dataset.symbol);
        
        // Subscribe to each symbol
        activeSymbols.forEach(symbol => {
            const formatted = formatSymbol(symbol);
            derivWs.send(JSON.stringify({ ticks: formatted, subscribe: 1, req_id: reqId++ }));
        });
    }

    // Initialize
    loadInitialSignals();
    loadSignalHistory();
    connectWebSocket();
    connectDerivWebSocket();

    // Filter functionality
    const searchFilter = document.getElementById("live-search-filter");
    const symbolFilter = document.getElementById("live-symbol-filter");
    const categoryFilter = document.getElementById("live-category-filter");
    const timeframeFilter = document.getElementById("live-timeframe-filter");

    function applyFilters() {
        const search = searchFilter?.value.toLowerCase();
        const symbol = symbolFilter?.value;
        const category = categoryFilter?.value;
        const timeframe = timeframeFilter?.value;

        const rows = container.querySelectorAll(".signal-row");
        rows.forEach(row => {
            const rowSymbol = row.dataset.symbol;
            const rowMarketName = row.querySelector(".signal-market")?.textContent.toLowerCase();
            
            let visible = true;
            
            if (search && !rowMarketName.includes(search)) {
                visible = false;
            }
            
            if (symbol && rowSymbol !== symbol) {
                visible = false;
            }
            
            if (category && !rowMarketName.includes(category.toLowerCase())) {
                visible = false;
            }
            
            if (timeframe) {
                // Add timeframe filtering if signals have timeframe data
            }
            
            row.style.display = visible ? "" : "none";
        });
    }

    if (searchFilter) searchFilter.addEventListener("input", applyFilters);
    if (symbolFilter) symbolFilter.addEventListener("change", applyFilters);
    if (categoryFilter) categoryFilter.addEventListener("change", applyFilters);
    if (timeframeFilter) timeframeFilter.addEventListener("change", applyFilters);
})();
