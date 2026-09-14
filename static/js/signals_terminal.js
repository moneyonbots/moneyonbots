/*
 * Signals Terminal page (/terminal/) — a dedicated, full-screen view of
 * nothing but the live signal feed. Self-contained: doesn't share state
 * with analysis_history.js (that file also drives the Analysis page's
 * Market Watch + Signal History tables, which don't exist here).
 *
 * Data flow: GET /api/signals/active/ for first paint, then ws/analysis/
 * "signal" / "signal_completed" events keep it live — same backend the
 * Analysis page's Live Signals panel uses.
 */
(function () {
    console.log('[Signals Terminal] Initializing...');
    const body = document.getElementById("term-signals-body");
    if (!body) {
        console.log('[Signals Terminal] Body element not found, exiting');
        return;
    }
    console.log('[Signals Terminal] Body element found, proceeding');

    const searchInput = document.getElementById("term-search");
    const categoryFilter = document.getElementById("term-category-filter");
    const directionFilter = document.getElementById("term-direction-filter");
    const sortSelect = document.getElementById("term-sort");
    const countEl = document.getElementById("term-count");

    // MIN_DIRECTION_CONFIDENCE mirrors the Analysis page's Live Signals
    // filter: model_confidence is direction-aware (0.5 = coin flip on the
    // direction being shown, 1.0 = fully confident), so anything at or
    // below a coin flip isn't a signal worth surfacing here.
    const MIN_DIRECTION_CONFIDENCE = 0.55;

    let signalsBySymbol = new Map();

    function getMarketType(symbol) {
        if (symbol.startsWith("frx")) {
            if (symbol.includes("XAU") || symbol.includes("GOLD")) return "commodities";
            return "forex";
        } else if (symbol.includes("CRASH") || symbol.includes("BOOM") || symbol.includes("Jump") || symbol.includes("STPRD") || symbol.includes("JD") || symbol.includes("STP")) {
            return "synthetic";
        } else if (symbol.includes("R_") || symbol.includes("1HZ")) {
            return "volatility";
        } else if (symbol.includes("RD") || symbol.includes("BEAR") || symbol.includes("BULL")) {
            return "synthetic";
        }
        return "general";
    }

    function fmt(n, digits = 2) {
        return n === null || n === undefined ? "—" : Number(n).toFixed(digits);
    }

    function dirClass(dir) {
        return dir === "Buy" ? "buy" : dir === "Sell" ? "sell" : "neutral";
    }

    function timeAgo(iso) {
        const secs = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
        if (secs < 60) return `${secs}s`;
        const mins = Math.floor(secs / 60);
        if (mins < 60) return `${mins}m`;
        const hrs = Math.floor(mins / 60);
        return `${hrs}h${mins % 60}m`;
    }

    // Audio alert functionality removed - JAVIS sound disabled

    function qualifies(signal) {
        if (signal.direction !== "Buy" && signal.direction !== "Sell") return false;
        const conf = signal.model_confidence;
        return conf !== null && conf !== undefined && conf >= MIN_DIRECTION_CONFIDENCE;
    }

    function upsert(signal, { announce = false } = {}) {
        if (!qualifies(signal)) {
            signalsBySymbol.delete(signal.symbol);
            renderAll();
            return;
        }
        signal._receivedAt = signal._receivedAt || Date.now();
        if (announce) {
            signal._isNew = true;
            setTimeout(() => {
                signal._isNew = false;
                renderAll();
            }, 4000);
            // Audio alert removed - JAVIS sound disabled
        }
        signalsBySymbol.set(signal.symbol, signal);
        renderAll();
    }

    function remove(symbol) {
        signalsBySymbol.delete(symbol);
        renderAll();
    }

    function rowHtml(signal) {
        const priceDigits = signal.price < 10 ? 5 : 2;
        return `
            <tr data-symbol="${signal.symbol}" class="signal-row-clickable${signal._isNew ? " new-signal" : ""}" onclick="TerminalShowDetails('${signal.symbol}')">
                <td>
                    <div class="market-name">${signal.market_name || signal.symbol}${signal._isNew ? ' <span class="new-badge">NEW</span>' : ""}</div>
                    <div class="market-analysis">${signal.pattern || signal.entry_type || "—"}</div>
                </td>
                <td><span class="dir-badge ${dirClass(signal.direction)}">${signal.direction}</span></td>
                <td class="live-price">${fmt(signal.price, priceDigits)}</td>
                <td class="${signal.direction === "Buy" ? "sl-red" : "sl-green"}">${signal.stop_loss != null ? fmt(signal.stop_loss, 4) : "—"}</td>
                <td class="${signal.direction === "Buy" ? "tp-green" : "tp-red"}">${signal.take_profit != null ? fmt(signal.take_profit, 4) : "—"}</td>
                <td>${signal.risk_reward ? `1:${fmt(signal.risk_reward, 1)}` : "—"}</td>
                <td>${fmt(signal.signal_strength, 2)}</td>
                <td>${fmt(signal.model_confidence * 100, 0)}%</td>
                <td>${timeAgo(signal.updated_at)}</td>
            </tr>`;
    }

    function renderAll() {
        let list = Array.from(signalsBySymbol.values());

        const q = (searchInput?.value || "").trim().toLowerCase();
        if (q) {
            list = list.filter(
                (s) => s.symbol.toLowerCase().includes(q) || (s.market_name || "").toLowerCase().includes(q)
            );
        }

        const category = categoryFilter?.value || "";
        if (category) list = list.filter((s) => getMarketType(s.symbol) === category);

        const direction = directionFilter?.value || "";
        if (direction) list = list.filter((s) => s.direction === direction);

        const sort = sortSelect?.value || "new";
        if (sort === "strength") {
            list.sort((a, b) => (b.signal_strength || 0) - (a.signal_strength || 0));
        } else if (sort === "confidence") {
            list.sort((a, b) => (b.model_confidence || 0) - (a.model_confidence || 0));
        } else {
            list.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
        }

        body.innerHTML = list.length
            ? list.map(rowHtml).join("")
            : `<tr class="signal-history-empty"><td colspan="9"><span class="loading-spinner"></span> Waiting for live signals…</td></tr>`;

        if (countEl) countEl.textContent = `${list.length}`;
    }

    // Age column keeps ticking even with no new signals.
    setInterval(renderAll, 15000);

    window.TerminalShowDetails = function (symbol) {
        const signal = signalsBySymbol.get(symbol);
        if (!signal) return;
        const modal = document.getElementById("signal-modal");
        const modalTitle = document.getElementById("modal-title");
        const modalBody = document.getElementById("modal-body");
        if (!modal || !modalTitle || !modalBody) return;

        modalTitle.textContent = `${signal.market_name || signal.symbol} — ${signal.direction} Signal`;
        const rows = [
            ["Symbol", signal.symbol],
            ["Direction", signal.direction],
            ["Timeframe", signal.timeframe || "—"],
            ["Entry Price", fmt(signal.price, signal.price < 10 ? 5 : 2)],
            ["Stop Loss", signal.stop_loss != null ? fmt(signal.stop_loss, 4) : "—"],
            ["Take Profit", signal.take_profit != null ? fmt(signal.take_profit, 4) : "—"],
            ["Risk/Reward", signal.risk_reward ? `1:${fmt(signal.risk_reward, 1)}` : "—"],
            ["Signal Strength", fmt(signal.signal_strength, 2)],
            ["Model Confidence", signal.model_confidence != null ? `${fmt(signal.model_confidence * 100, 0)}%` : "—"],
            ["RSI", signal.rsi != null ? fmt(signal.rsi, 1) : "—"],
            ["ATR", signal.atr != null ? fmt(signal.atr, 5) : "—"],
            ["Pattern", signal.pattern || "—"],
            ["Structure", signal.structure || "—"],
            ["Entry Type", signal.entry_type || "—"],
            ["Risk Level", signal.risk_level || "—"],
            ["Updated", new Date(signal.updated_at).toLocaleString()],
        ];
        modalBody.innerHTML = rows
            .map(
                ([label, value]) =>
                    `<div class="signal-detail-row"><span class="signal-detail-label">${label}</span><span class="signal-detail-value">${value}</span></div>`
            )
            .join("");
        modal.style.display = "block";
    };

    const modalCloseBtn = document.querySelector("#signal-modal .modal-close");
    if (modalCloseBtn) {
        modalCloseBtn.addEventListener("click", () => {
            document.getElementById("signal-modal").style.display = "none";
        });
    }
    window.addEventListener("click", (e) => {
        const modal = document.getElementById("signal-modal");
        if (modal && e.target === modal) modal.style.display = "none";
    });

    async function loadInitial() {
        try {
            console.log('[Signals Terminal] Loading initial signals...');
            const res = await fetch("/api/signals/active/");
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            console.log('[Signals Terminal] Received data:', data);
            (data.signals || []).forEach((s) => {
                if (qualifies(s)) signalsBySymbol.set(s.symbol, s);
            });
            console.log('[Signals Terminal] Qualified signals:', signalsBySymbol.size);
            renderAll();
        } catch (e) {
            console.error('[Signals Terminal] Error loading signals:', e);
            body.innerHTML = `<tr class="signal-history-empty"><td colspan="9">Couldn't load live signals: ${e.message}</td></tr>`;
        }
    }

    function connectWebSocket() {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(`${proto}://${window.location.host}/ws/analysis/`);

        ws.onmessage = (evt) => {
            let data;
            try {
                data = JSON.parse(evt.data);
            } catch (e) {
                return;
            }
            if (data.type === "signal" && data.signal) {
                upsert(data.signal, { announce: true });
            } else if (data.type === "signal_completed" && data.signal) {
                remove(data.signal.symbol);
            }
        };
        ws.onclose = () => setTimeout(connectWebSocket, 3000);
        ws.onerror = () => ws.close();
    }

    if (searchInput) searchInput.addEventListener("input", renderAll);
    if (categoryFilter) categoryFilter.addEventListener("change", renderAll);
    if (directionFilter) directionFilter.addEventListener("change", renderAll);
    if (sortSelect) sortSelect.addEventListener("change", renderAll);
    // Sound toggle functionality removed - JAVIS sound disabled

    loadInitial();
    connectWebSocket();
})();
