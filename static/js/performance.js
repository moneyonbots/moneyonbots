/*
 * Performance page — completed TP/SL signal history with aggregate stats.
 */
(function () {
    const container = document.getElementById("performance-history-body");
    if (!container) return;

    let allSignals = [];

    function fmt(n, digits = 2) {
        return n === null || n === undefined ? "—" : Number(n).toFixed(digits);
    }

    function fmtDate(iso) {
        if (!iso) return "—";
        const d = new Date(iso);
        return d.toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function resultBadge(hit) {
        if (hit === "tp") return '<span class="result-badge result-tp">TP</span>';
        if (hit === "sl") return '<span class="result-badge result-sl">SL</span>';
        return "—";
    }

    function pnlClass(pnl) {
        if (pnl === null || pnl === undefined) return "";
        return pnl >= 0 ? "pnl-positive" : "pnl-negative";
    }

    function renderRow(signal) {
        const directionClass = (signal.direction || "").toLowerCase();
        const priceDigits = signal.price < 10 ? 5 : 2;
        return `
            <tr data-symbol="${signal.symbol}" data-result="${signal.pnl_hit || ""}" class="signal-row ${directionClass}">
                <td class="signal-market">${signal.market_name}</td>
                <td class="signal-direction ${directionClass}">${signal.direction}</td>
                <td>${fmt(signal.price, priceDigits)}</td>
                <td>${fmt(signal.exit_price, priceDigits)}</td>
                <td>${fmt(signal.stop_loss, priceDigits)}</td>
                <td>${fmt(signal.take_profit, priceDigits)}</td>
                <td>${resultBadge(signal.pnl_hit)}</td>
                <td class="${pnlClass(signal.actual_pnl)}">${signal.actual_pnl != null ? fmt(signal.actual_pnl) + "%" : "—"}</td>
                <td>${fmt(signal.risk_reward, 2)}</td>
                <td class="perf-closed-at">${fmtDate(signal.completed_at)}</td>
            </tr>
        `;
    }

    function updateStats(stats) {
        const set = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        set("stat-total", stats.total_trades ?? "0");
        set("stat-win-rate", stats.total_trades ? `${stats.win_rate}%` : "—");
        set("stat-wl", stats.total_trades ? `${stats.wins} / ${stats.losses}` : "—");
        set("stat-avg-pnl", stats.total_trades ? `${fmt(stats.avg_pnl)}%` : "—");
        set("stat-avg-win", stats.wins ? `+${fmt(stats.avg_win)}%` : "—");
        set("stat-avg-loss", stats.losses ? `${fmt(stats.avg_loss)}%` : "—");
        
        // Update symbol filter dropdown with available symbols
        const symbolFilter = document.getElementById("perf-symbol-filter");
        if (symbolFilter && allSignals.length > 0) {
            const symbols = [...new Set(allSignals.map(s => s.symbol))].sort();
            const currentValue = symbolFilter.value;
            symbolFilter.innerHTML = '<option value="">All Symbols</option>' +
                symbols.map(s => `<option value="${s}" ${s === currentValue ? 'selected' : ''}>${s}</option>`).join('');
        }
    }

    function updateCount(count) {
        const el = document.getElementById("perf-history-count");
        if (el) el.textContent = count;
    }

    function renderTable(signals) {
        if (!signals.length) {
            container.innerHTML = `
                <tr class="signal-history-empty">
                    <td colspan="10">No completed signals yet. Trades appear here when TP or SL is hit.</td>
                </tr>
            `;
            updateCount(0);
            return;
        }
        container.innerHTML = signals.map(renderRow).join("");
        updateCount(signals.length);
    }

    function applyFilters() {
        const search = (document.getElementById("perf-search-filter")?.value || "").toLowerCase();
        const symbol = document.getElementById("perf-symbol-filter")?.value || "";
        const result = document.getElementById("perf-result-filter")?.value || "";

        const filtered = allSignals.filter((s) => {
            if (search && !(s.market_name || "").toLowerCase().includes(search)) return false;
            if (symbol && s.symbol !== symbol) return false;
            if (result && s.pnl_hit !== result) return false;
            return true;
        });
        renderTable(filtered);
    }

    async function loadStats() {
        try {
            const res = await fetch("/api/performance/stats/");
            const stats = await res.json();
            updateStats(stats);
        } catch (err) {
            console.error("Failed to load performance stats:", err);
        }
    }

    async function loadHistory() {
        try {
            const res = await fetch("/api/signals/history/");
            const data = await res.json();
            allSignals = data.signals || [];
            applyFilters();
        } catch (err) {
            console.error("Failed to load signal history:", err);
            container.innerHTML = `
                <tr class="signal-history-empty">
                    <td colspan="10">Failed to load signal history.</td>
                </tr>
            `;
        }
    }

    function prependSignal(signal) {
        if (!signal || !signal.pnl_hit) return;
        allSignals = allSignals.filter((s) => s.id !== signal.id);
        allSignals.unshift(signal);
        applyFilters();
        loadStats();
    }

    function connectWebSocket() {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(`${proto}://${window.location.host}/ws/analysis/`);

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "signal_completed" && data.signal) {
                    prependSignal(data.signal);
                }
            } catch (err) {
                console.error("Performance WS parse error:", err);
            }
        };

        ws.onclose = () => setTimeout(connectWebSocket, 3000);
        ws.onerror = () => ws.close();
    }

    document.getElementById("perf-search-filter")?.addEventListener("input", applyFilters);
    document.getElementById("perf-symbol-filter")?.addEventListener("change", applyFilters);
    document.getElementById("perf-result-filter")?.addEventListener("change", applyFilters);

    loadStats();
    loadHistory();
    connectWebSocket();
})();
