/*
 * Mounts Lightweight Charts against Deriv's public WebSocket feed.
 * Lightweight Charts is simpler and doesn't require complex datafeed implementation.
 */
(function () {
    const THEME = {
        background: "#ffffff",
        grid: "#eef1f4",
        border: "#dfe3e8",
        text: "#5c6470",
        up: "#26a69a",
        down: "#ef5350",
    };

    window.initDerivChart = function ({ containerId, selectId, priceId, defaultSymbol }) {
        const container = document.getElementById(containerId);
        if (!container || !window.LightweightCharts) return null;

        window.currentChartSymbol = defaultSymbol || "R_100";
        window.currentChartPrice = null;

        // Create chart
        const chart = LightweightCharts.createChart(container, {
            width: container.clientWidth,
            height: container.clientHeight,
            layout: {
                background: { color: THEME.background },
                textColor: THEME.text,
            },
            grid: {
                vertLines: { color: THEME.grid },
                horzLines: { color: THEME.grid },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: THEME.border,
            },
            timeScale: {
                borderColor: THEME.border,
                timeVisible: true,
                secondsVisible: false,
            },
        });

        // Create candlestick series
        const candlestickSeries = chart.addCandlestickSeries({
            upColor: THEME.up,
            downColor: THEME.down,
            borderDownColor: THEME.down,
            borderUpColor: THEME.up,
            wickDownColor: THEME.down,
            wickUpColor: THEME.up,
        });

        // WebSocket connection for data
        const appId = window.DERIV_APP_ID || 1089;
        const apiToken = window.DERIV_API_TOKEN || null;
        const ws = new WebSocket(`wss://ws.binaryws.com/websockets/v3?app_id=${appId}`);
        let reqId = 1;
        const pending = {};
        let currentCandle = null; // Track current candle for tick updates
        let authorized = false;
        let currentGranularity = 60; // Track current granularity

        function send(req) {
            req.req_id = reqId++;
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify(req));
            }
            return req.req_id;
        }

        function formatSymbol(sym) {
            // Internal symbol names are already in correct Deriv API format
            return sym;
        }

        // Request historical data
        function loadHistoricalData() {
            const symbol = formatSymbol(window.currentChartSymbol);
            const req = {
                ticks_history: symbol,
                style: "candles",
                granularity: currentGranularity,
                adjust_start_time: 1,
                end: "latest",
                count: 500,
            };
            const id = send(req);
            pending[id] = (data) => {
                if (data.candles) {
                    const bars = data.candles.map(c => ({
                        time: c.epoch * 1000,
                        open: parseFloat(c.open),
                        high: parseFloat(c.high),
                        low: parseFloat(c.low),
                        close: parseFloat(c.close),
                    })).sort((a, b) => a.time - b.time);
                    candlestickSeries.setData(bars);
                    if (bars.length > 0) {
                        window.currentChartPrice = bars[bars.length - 1].close;
                        currentCandle = bars[bars.length - 1]; // Set current candle for tick updates
                    }
                }
            };
        }

        // Subscribe to live updates
        function subscribeLive() {
            const symbol = formatSymbol(window.currentChartSymbol);
            
            // Subscribe to OHLC updates for candle data
            const ohlcReq = {
                ticks_history: symbol,
                style: "candles",
                granularity: currentGranularity,
                adjust_start_time: 1,
                subscribe: 1,
            };
            send(ohlcReq);
            
            // Also subscribe to ticks for per-tick chart updates
            const tickReq = {
                ticks: symbol,
                subscribe: 1,
            };
            send(tickReq);
        }

        ws.onopen = () => {
            // Only authorize if we have a valid non-empty token
            if (apiToken && apiToken.trim() !== "") {
                ws.send(JSON.stringify({ authorize: apiToken }));
            }
            // Load data regardless of authorization status
            loadHistoricalData();
            subscribeLive();
        };

        ws.onmessage = (evt) => {
            const data = JSON.parse(evt.data);
            
            if (data.req_id && pending[data.req_id]) {
                pending[data.req_id](data);
                delete pending[data.req_id];
            }

            // Handle authorization response
            if (data.msg_type === "authorize") {
                if (data.error) {
                    console.error('Chart authorization error:', data.error);
                    authorized = false;
                } else {
                    console.log('Chart authorization successful');
                    authorized = true;
                }
            }

            if (data.msg_type === "ohlc" && data.ohlc) {
                const bar = {
                    time: data.ohlc.open_time * 1000,
                    open: parseFloat(data.ohlc.open),
                    high: parseFloat(data.ohlc.high),
                    low: parseFloat(data.ohlc.low),
                    close: parseFloat(data.ohlc.close),
                };
                candlestickSeries.update(bar);
                window.currentChartPrice = bar.close;
                window.currentChartSymbol = window.currentChartSymbol;
                currentCandle = bar; // Update current candle reference
            }

            // Handle real-time tick updates for per-tick chart movement
            if (data.msg_type === "tick" && data.tick) {
                handleTickUpdate(data.tick);
            }
        };

        // Per-tick candle update function
        function handleTickUpdate(tick) {
            if (!currentCandle) return;

            const price = parseFloat(tick.quote);
            const tickTime = tick.epoch * 1000;
            const granularity = currentGranularity; // Use current granularity
            const candleTime = currentCandle.time;
            const candleEndTime = candleTime + (granularity * 1000);

            if (tickTime < candleEndTime) {
                // Update current candle with tick data
                const updatedCandle = {
                    time: currentCandle.time,
                    open: currentCandle.open,
                    high: Math.max(currentCandle.high, price),
                    low: Math.min(currentCandle.low, price),
                    close: price,
                };
                candlestickSeries.update(updatedCandle);
                window.currentChartPrice = price;
                currentCandle = updatedCandle;
            } else {
                // Create new candle when time period ends
                const newCandleTime = Math.floor(tickTime / (granularity * 1000)) * (granularity * 1000);
                const newCandle = {
                    time: newCandleTime,
                    open: price,
                    high: price,
                    low: price,
                    close: price,
                };
                candlestickSeries.update(newCandle);
                window.currentChartPrice = price;
                currentCandle = newCandle;
            }
        }

        // Enhanced symbol switching function
        function switchSymbol(newSymbol) {
            if (newSymbol === window.currentChartSymbol) return;
            
            window.currentChartSymbol = newSymbol;
            currentCandle = null; // Reset current candle
            window.currentChartPrice = null;
            
            // Resubscribe with new symbol
            loadHistoricalData();
            subscribeLive();
        }

        // Expose symbol switching function globally
        window.switchChartSymbol = switchSymbol;

        ws.onclose = () => {
            setTimeout(() => {
                const newWs = new WebSocket(`wss://ws.derivws.com/websockets/v3?app_id=${appId}`);
                Object.assign(ws, newWs);
            }, 3000);
        };

        // Handle resize
        new ResizeObserver(entries => {
            if (entries.length === 0 || entries[0].target !== container) {
                return;
            }
            const newRect = entries[0].contentRect;
            chart.applyOptions({ width: newRect.width, height: newRect.height });
        }).observe(container);

        let destroyed = false;

        return {
            chart,
            destroy() {
                if (destroyed) return;
                destroyed = true;
                chart.remove();
                ws.close();
            },
        };
    };
})();
