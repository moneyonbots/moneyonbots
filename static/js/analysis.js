/*
 * Keeps the nav bar's "analysis feed" connection indicator live. The
 * signal table and positions table used to live in a side panel here;
 * that panel was removed in favour of a full-page chart, and the same
 * signal data now feeds the AI insight tab in the brain panel instead
 * (see brain.js). This file just owns the websocket connection status.
 */
(function () {
    const connDot = document.getElementById("analysis-conn-dot");
    const connLabel = document.getElementById("analysis-conn-label");
    if (!connDot || !connLabel) return;

    // Check if we're on Vercel (WebSockets not supported)
    if (window.location.hostname.includes('vercel.app')) {
        console.log('WebSockets not supported on Vercel, analysis feed disabled');
        connDot.classList.add("down");
        connLabel.textContent = "analysis feed: unavailable";
        return;
    }

    function connectWebSocket() {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(`${proto}://${window.location.host}/ws/analysis/`);

        ws.onopen = () => {
            connDot.classList.add("live");
            connDot.classList.remove("down");
            connLabel.textContent = "analysis feed: live";
        };
        ws.onclose = () => {
            connDot.classList.remove("live");
            connDot.classList.add("down");
            connLabel.textContent = "analysis feed: reconnecting…";
            setTimeout(connectWebSocket, 3000);
        };
        ws.onerror = () => ws.close();
    }

    connectWebSocket();
})();
