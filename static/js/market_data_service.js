/**
 * Centralized Market Data Service
 * Provides shared market data access between charts and analysis components
 * to avoid redundant WebSocket connections to Deriv API.
 */
(function() {
    'use strict';

    class MarketDataService {
        constructor() {
            this.ws = null;
            this.connected = false;
            this.reqId = 1;
            this.pending = {}; // Expose this for external use
            this.subscribers = new Map();
            this.currentSymbol = null;
            this.currentPrice = null;
            this.currentCandle = null;
            this.historicalData = [];
            this.candlesBySymbol = {};
            this.pricesBySymbol = {};
            this.chartMarkets = [];
            this.subscribedTicks = new Set();
            this.connectionPromise = null;
            this.reconnectAttempts = 0;
            this.maxReconnectAttempts = 5;
            this.reconnectDelay = 3000;
            
            // Configuration
            this.appId = window.DERIV_APP_ID || 1089;
            this.apiToken = window.DERIV_API_TOKEN || null;
            this.wsUrl = `wss://ws.derivws.com/websockets/v3?app_id=${this.appId}`;
        }

        /**
         * Initialize the service and connect to Deriv WebSocket
         */
        connect() {
            if (this.ws && this.connected && this.ws.readyState === WebSocket.OPEN) {
                return Promise.resolve();
            }
            if (this.connectionPromise) {
                return this.connectionPromise;
            }

            this.connectionPromise = new Promise((resolve, reject) => {
                try {
                    this.ws = new WebSocket(this.wsUrl);
                    
                    this.ws.onopen = () => {
                        console.log('Market Data Service: WebSocket connected');
                        this.connected = true;
                        this.reconnectAttempts = 0;
                        
                        if (this.apiToken && this.apiToken.trim() !== '') {
                            this.authorize();
                        }
                        
                        resolve();
                    };

                    this.ws.onmessage = (event) => {
                        this.handleMessage(event);
                    };

                    this.ws.onerror = (error) => {
                        console.error('Market Data Service: WebSocket error', error);
                        this.connected = false;
                        this.connectionPromise = null;
                        reject(error);
                    };

                    this.ws.onclose = () => {
                        console.log('Market Data Service: WebSocket closed');
                        this.connected = false;
                        this.connectionPromise = null;
                        this.subscribedTicks.clear();
                        this.handleReconnect();
                    };
                } catch (error) {
                    this.connectionPromise = null;
                    reject(error);
                }
            });
            return this.connectionPromise;
        }

        /**
         * Handle WebSocket reconnection
         */
        handleReconnect() {
            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                console.log(`Market Data Service: Reconnecting (attempt ${this.reconnectAttempts})`);
                setTimeout(() => {
                    this.connect().catch(err => {
                        console.error('Market Data Service: Reconnection failed', err);
                    });
                }, this.reconnectDelay);
            } else {
                console.error('Market Data Service: Max reconnection attempts reached');
            }
        }

        /**
         * Authorize with Deriv API
         */
        authorize() {
            this.send({ authorize: this.apiToken });
        }

        /**
         * Send a request to Deriv API
         */
        send(payload) {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
                console.warn('Market Data Service: WebSocket not connected');
                return null;
            }

            payload.req_id = this.reqId++;
            this.ws.send(JSON.stringify(payload));
            return payload.req_id;
        }

        /**
         * Handle incoming WebSocket messages
         */
        handleMessage(event) {
            try {
                const data = JSON.parse(event.data);
                
                // Handle pending requests
                if (data.req_id && this.pending[data.req_id]) {
                    this.pending[data.req_id](data);
                    delete this.pending[data.req_id];
                }

                // Handle authorization response
                if (data.msg_type === 'authorize') {
                    if (data.error) {
                        console.error('Market Data Service: Authorization failed', data.error);
                    } else {
                        console.log('Market Data Service: Authorization successful');
                    }
                }

                // Handle active symbols response
                if (data.msg_type === 'active_symbols') {
                    this.notifySubscribers('active_symbols', data);
                }

                if (data.msg_type === 'ohlc' && data.ohlc) {
                    this.handleOHLC(data.ohlc);
                }

                if (data.msg_type === 'tick' && data.tick) {
                    this.handleTick(data.tick);
                }

                if ((data.msg_type === 'history' || data.msg_type === 'candles') && (data.history || data.candles)) {
                    const symbol = (data.echo_req && data.echo_req.ticks_history) || this.currentSymbol;
                    this.handleHistory(data.history || data.candles, symbol);
                }

            } catch (error) {
                console.error('Market Data Service: Error handling message', error);
            }
        }

        /**
         * Handle OHLC candle updates
         */
        handleOHLC(ohlc) {
            const candle = {
                time: ohlc.open_time * 1000,
                open: parseFloat(ohlc.open),
                high: parseFloat(ohlc.high),
                low: parseFloat(ohlc.low),
                close: parseFloat(ohlc.close),
            };

            if (ohlc.symbol) {
                this.pricesBySymbol[ohlc.symbol] = candle.close;
            }
            this.currentCandle = candle;
            this.currentPrice = candle.close;
            
            // Update historical data
            const lastIndex = this.historicalData.length - 1;
            if (lastIndex >= 0 && this.historicalData[lastIndex].time === candle.time) {
                this.historicalData[lastIndex] = candle;
            } else {
                this.historicalData.push(candle);
            }

            // Notify subscribers
            this.notifySubscribers('candle', candle);
            this.notifySubscribers('price', this.currentPrice);
        }

        /**
         * Handle tick updates
         */
        handleTick(tick) {
            if (!tick || !tick.quote) return;
            const price = parseFloat(tick.quote);
            if (isNaN(price)) return;
            const symbol = tick.symbol;

            if (symbol) {
                this.pricesBySymbol[symbol] = price;
                const candles = this.candlesBySymbol[symbol];
                if (candles && candles.length) {
                    const last = candles[candles.length - 1];
                    last.close = price;
                    last.high = Math.max(last.high, price);
                    last.low = Math.min(last.low, price);
                }
            }
            if (!symbol || symbol === this.currentSymbol) {
                this.currentPrice = price;
            }
            
            if (this.currentCandle && (!symbol || symbol === this.currentSymbol)) {
                const tickTime = (tick.epoch ? Number(tick.epoch) : Math.floor(Date.now() / 1000)) * 1000;
                const granularity = 60;
                const candleTime = this.currentCandle.time;
                const candleEndTime = candleTime + (granularity * 1000);

                if (tickTime < candleEndTime) {
                    const updatedCandle = {
                        time: this.currentCandle.time,
                        open: this.currentCandle.open,
                        high: Math.max(this.currentCandle.high, price),
                        low: Math.min(this.currentCandle.low, price),
                        close: price,
                    };
                    this.currentCandle = updatedCandle;
                    
                    const lastIndex = this.historicalData.length - 1;
                    if (lastIndex >= 0) {
                        this.historicalData[lastIndex] = updatedCandle;
                    }
                } else {
                    const newCandleStartTime = Math.floor(tickTime / (granularity * 1000)) * (granularity * 1000);
                    const newCandle = {
                        time: newCandleStartTime,
                        open: price,
                        high: price,
                        low: price,
                        close: price,
                    };
                    this.currentCandle = newCandle;
                    this.historicalData.push(newCandle);
                    if (this.historicalData.length > 1000) {
                        this.historicalData.shift();
                    }
                }
                this.notifySubscribers('candle', this.currentCandle);
            }

            this.notifySubscribers('tick', {
                symbol: tick.symbol || this.currentSymbol,
                quote: tick.quote,
                price,
                epoch: tick.epoch,
                tick,
            });
            this.notifySubscribers('price', price);
        }

        /**
         * Ingest tick directly from TradingView chart datafeed for instant synchronization
         */
        handleChartTick(symbol, price, tickTime, candle) {
            if (!symbol || isNaN(price)) return;
            this.pricesBySymbol[symbol] = price;
            if (symbol === this.currentSymbol || !this.currentSymbol) {
                this.currentPrice = price;
                if (candle) {
                    this.currentCandle = { ...candle };
                    const lastIndex = this.historicalData.length - 1;
                    if (lastIndex >= 0 && this.historicalData[lastIndex].time === candle.time) {
                        this.historicalData[lastIndex] = this.currentCandle;
                    } else if (lastIndex < 0 || this.historicalData[lastIndex].time < candle.time) {
                        this.historicalData.push(this.currentCandle);
                        if (this.historicalData.length > 1000) {
                            this.historicalData.shift();
                        }
                    }
                    this.notifySubscribers('candle', this.currentCandle);
                }
                this.notifySubscribers('price', price);
            }
            this.notifySubscribers('tick', { symbol, price, time: tickTime, candle });
        }

        /**
         * Handle historical data response
         */
        handleHistory(candles, symbol) {
            const mapped = (candles || []).map(c => ({
                time: c.epoch * 1000,
                open: parseFloat(c.open),
                high: parseFloat(c.high),
                low: parseFloat(c.low),
                close: parseFloat(c.close),
                epoch: c.epoch,
            })).sort((a, b) => a.time - b.time);

            if (symbol) {
                this.candlesBySymbol[symbol] = mapped;
                if (mapped.length) {
                    this.pricesBySymbol[symbol] = mapped[mapped.length - 1].close;
                }
            }

            this.historicalData = mapped;
            if (mapped.length > 0) {
                this.currentCandle = mapped[mapped.length - 1];
                this.currentPrice = this.currentCandle.close;
                if (symbol) this.currentSymbol = symbol;
            }

            this.notifySubscribers('history', mapped);
            this.notifySubscribers('market_history', { symbol: symbol || this.currentSymbol, candles: mapped });
        }

        /**
         * Subscribe to market data updates
         */
        subscribe(event, callback) {
            if (!this.subscribers.has(event)) {
                this.subscribers.set(event, new Set());
            }
            this.subscribers.get(event).add(callback);
            
            // Return unsubscribe function
            return () => {
                const callbacks = this.subscribers.get(event);
                if (callbacks) {
                    callbacks.delete(callback);
                }
            };
        }

        /**
         * Notify all subscribers of an event
         */
        notifySubscribers(event, data) {
            const callbacks = this.subscribers.get(event);
            if (callbacks) {
                callbacks.forEach(callback => {
                    try {
                        callback(data);
                    } catch (error) {
                        console.error('Market Data Service: Error in subscriber callback', error);
                    }
                });
            }
        }

        /**
         * Load historical data for a symbol
         */
        loadHistoricalData(symbol, options = {}) {
            const {
                granularity = 60,
                count = 500,
                end = 'latest'
            } = options;

            this.currentSymbol = symbol;

            return new Promise((resolve, reject) => {
                const id = this.send({
                    ticks_history: symbol,
                    style: 'candles',
                    granularity: granularity,
                    adjust_start_time: 1,
                    end: end,
                    count: count,
                });

                if (id) {
                    const timeout = setTimeout(() => {
                        delete this.pending[id];
                        reject(new Error('Timeout loading historical data'));
                    }, 15000);

                    this.pending[id] = (data) => {
                        clearTimeout(timeout);
                        if (data.error) {
                            reject(data.error);
                        } else {
                            // Convert to standard candle format
                            const candles = data.history || data.candles;
                            if (candles) {
                                resolve(candles);
                            } else {
                                reject(new Error('No candle data received'));
                            }
                        }
                    };
                } else {
                    reject(new Error('WebSocket not connected'));
                }
            });
        }

        /**
         * Subscribe to live updates for a symbol
         */
        subscribeTicks(symbol) {
            if (!symbol || this.subscribedTicks.has(symbol)) return;
            this.subscribedTicks.add(symbol);
            this.send({
                ticks: symbol,
                subscribe: 1,
            });
        }

        subscribeToSymbol(symbol, granularity = 60) {
            if (!symbol) return;
            this.currentSymbol = symbol;
            this.subscribedTicks.forEach((prevSym) => {
                if (prevSym !== symbol) {
                    this.send({ forget_all: 'ticks' });
                    this.subscribedTicks.delete(prevSym);
                }
            });
            this.send({
                ticks_history: symbol,
                style: 'candles',
                granularity: granularity,
                adjust_start_time: 1,
                count: 1,
                end: 'latest',
            });
            this.subscribeTicks(symbol);
        }

        /**
         * Get current market data
         */
        getCurrentData() {
            // If TradingView chart has data, use that
            if (window.currentChartSymbol && window.currentChartPrice) {
                return {
                    symbol: window.currentChartSymbol,
                    price: window.currentChartPrice,
                    candle: this.currentCandle,
                    historical: this.historicalData,
                    source: 'chart'
                };
            }
            
            // Otherwise use service data
            return {
                symbol: this.currentSymbol,
                price: this.currentPrice,
                candle: this.currentCandle,
                historical: this.historicalData,
                source: 'service'
            };
        }

        /**
         * Set current symbol from external source (e.g., TradingView chart)
         */
        setCurrentSymbol(symbol) {
            if (symbol && symbol !== this.currentSymbol) {
                this.currentSymbol = symbol;
                console.log('Market data service symbol updated:', symbol);
                
                // Load data for the new symbol
                this.loadHistoricalData(symbol);
                this.subscribeToSymbol(symbol);
            }
        }

        /**
         * Set current price from external source (e.g., TradingView chart)
         */
        setCurrentPrice(price) {
            this.currentPrice = price;
        }

        /**
         * Change the current symbol
         */
        changeSymbol(symbol) {
            if (this.currentSymbol === symbol) return;
            
            this.currentSymbol = symbol;
            this.currentPrice = null;
            this.currentCandle = null;
            this.historicalData = [];
            
            // Load new data
            this.loadHistoricalData(symbol);
            this.subscribeToSymbol(symbol);
        }

        request(payload, timeoutMs) {
            return new Promise((resolve, reject) => {
                const id = this.send(payload);
                if (!id) {
                    reject(new Error('WebSocket not connected'));
                    return;
                }
                const timeout = setTimeout(() => {
                    delete this.pending[id];
                    reject(new Error('Timeout'));
                }, timeoutMs || 15000);
                this.pending[id] = (data) => {
                    clearTimeout(timeout);
                    resolve(data);
                };
            });
        }

        classifyMarket(symbol, typeHint, market, submarket) {
            const hint = `${typeHint || ''} ${market || ''} ${submarket || ''}`.toLowerCase();
            if (hint.includes('forex') && !hint.includes('basket')) return 'forex';
            if (hint.includes('commodit')) return 'commodities';
            if (hint.includes('crypto')) return 'cryptocurrencies';
            if (hint.includes('volatility')) return 'volatility';
            if (hint.includes('indice') && !hint.includes('volatility')) return 'indices';
            if (hint.includes('derived') || hint.includes('synthetic') || hint.includes('crash') || hint.includes('boom')) return 'synthetic';
            if (symbol.startsWith('frxXAU') || symbol.startsWith('frxXAG')) return 'commodities';
            if (symbol.startsWith('frx')) return 'forex';
            if (symbol.startsWith('cry')) return 'cryptocurrencies';
            if (symbol.startsWith('R_') || symbol.startsWith('1HZ')) return 'volatility';
            if (symbol.startsWith('OTC_')) return 'indices';
            return 'synthetic';
        }

        defaultChartMarkets() {
            const rows = [
                ['R_10', 'Volatility 10 Index', 'volatility'],
                ['R_25', 'Volatility 25 Index', 'volatility'],
                ['R_50', 'Volatility 50 Index', 'volatility'],
                ['R_75', 'Volatility 75 Index', 'volatility'],
                ['R_100', 'Volatility 100 Index', 'volatility'],
                ['1HZ10V', 'Volatility 10 (1s) Index', 'volatility'],
                ['1HZ15V', 'Volatility 15 (1s) Index', 'volatility'],
                ['1HZ25V', 'Volatility 25 (1s) Index', 'volatility'],
                ['1HZ30V', 'Volatility 30 (1s) Index', 'volatility'],
                ['1HZ50V', 'Volatility 50 (1s) Index', 'volatility'],
                ['1HZ75V', 'Volatility 75 (1s) Index', 'volatility'],
                ['1HZ90V', 'Volatility 90 (1s) Index', 'volatility'],
                ['1HZ100V', 'Volatility 100 (1s) Index', 'volatility'],
                ['BOOM1000', 'Boom 1000 Index', 'synthetic'],
                ['BOOM500', 'Boom 500 Index', 'synthetic'],
                ['BOOM600', 'Boom 600 Index', 'synthetic'],
                ['BOOM900', 'Boom 900 Index', 'synthetic'],
                ['BOOM50', 'Boom 50 Index', 'synthetic'],
                ['BOOM150N', 'Boom 150 Index', 'synthetic'],
                ['BOOM300N', 'Boom 300 Index', 'synthetic'],
                ['CRASH1000', 'Crash 1000 Index', 'synthetic'],
                ['CRASH500', 'Crash 500 Index', 'synthetic'],
                ['CRASH600', 'Crash 600 Index', 'synthetic'],
                ['CRASH900', 'Crash 900 Index', 'synthetic'],
                ['CRASH50', 'Crash 50 Index', 'synthetic'],
                ['CRASH150N', 'Crash 150 Index', 'synthetic'],
                ['CRASH300N', 'Crash 300 Index', 'synthetic'],
                ['JD10', 'Jump 10 Index', 'synthetic'],
                ['JD25', 'Jump 25 Index', 'synthetic'],
                ['JD50', 'Jump 50 Index', 'synthetic'],
                ['JD75', 'Jump 75 Index', 'synthetic'],
                ['JD100', 'Jump 100 Index', 'synthetic'],
                ['RDBEAR', 'Bear Market Index', 'synthetic'],
                ['RDBULL', 'Bull Market Index', 'synthetic'],
                ['stpRNG', 'Step Index 100', 'synthetic'],
                ['stpRNG2', 'Step Index 200', 'synthetic'],
                ['stpRNG3', 'Step Index 300', 'synthetic'],
                ['stpRNG4', 'Step Index 400', 'synthetic'],
                ['stpRNG5', 'Step Index 500', 'synthetic'],
                ['RB100', 'Range Break 100 Index', 'synthetic'],
                ['RB200', 'Range Break 200 Index', 'synthetic'],
                ['WLDAUD', 'AUD Basket', 'forex'],
                ['WLDEUR', 'EUR Basket', 'forex'],
                ['WLDGBP', 'GBP Basket', 'forex'],
                ['WLDUSD', 'USD Basket', 'forex'],
                ['WLDXAU', 'Gold Basket', 'commodities'],
                ['cryBTCUSD', 'BTC/USD', 'cryptocurrencies'],
                ['cryETHUSD', 'ETH/USD', 'cryptocurrencies'],
                ['frxEURUSD', 'EUR/USD', 'forex'],
                ['frxGBPUSD', 'GBP/USD', 'forex'],
                ['frxUSDJPY', 'USD/JPY', 'forex'],
                ['frxAUDUSD', 'AUD/USD', 'forex'],
                ['frxUSDCAD', 'USD/CAD', 'forex'],
                ['frxUSDCHF', 'USD/CHF', 'forex'],
                ['frxNZDUSD', 'NZD/USD', 'forex'],
                ['frxEURGBP', 'EUR/GBP', 'forex'],
                ['frxEURJPY', 'EUR/JPY', 'forex'],
                ['frxEURCHF', 'EUR/CHF', 'forex'],
                ['frxGBPJPY', 'GBP/JPY', 'forex'],
                ['frxAUDJPY', 'AUD/JPY', 'forex'],
                ['frxEURAUD', 'EUR/AUD', 'forex'],
                ['frxEURCAD', 'EUR/CAD', 'forex'],
                ['frxGBPAUD', 'GBP/AUD', 'forex'],
                ['frxGBPCAD', 'GBP/CAD', 'forex'],
                ['frxXAUUSD', 'Gold/USD', 'commodities'],
                ['frxXAGUSD', 'Silver/USD', 'commodities'],
                ['OTC_DJI', 'Wall Street 30', 'indices'],
                ['OTC_NDX', 'US Tech 100', 'indices'],
                ['OTC_SPC', 'US 500', 'indices'],
                ['OTC_FTSE', 'UK 100', 'indices'],
                ['OTC_GDAXI', 'Germany 40', 'indices'],
                ['OTC_N225', 'Japan 225', 'indices'],
            ];
            return rows.map(([symbol, name, type]) => ({ symbol, name, type }));
        }

        mergeMarkets(lists) {
            const bySymbol = new Map();
            lists.flat().forEach((item) => {
                if (!item || !item.symbol) return;
                bySymbol.set(item.symbol, {
                    symbol: item.symbol,
                    name: item.name || item.description || item.symbol,
                    type: item.type || this.classifyMarket(item.symbol, item.type, item.market, item.submarket),
                });
            });
            return Array.from(bySymbol.values());
        }

        setChartSymbols(symbols) {
            const mapped = (symbols || []).map((item) => ({
                symbol: item.symbol || item.ticker,
                name: item.description || item.display_name || item.name || item.symbol,
                type: this.classifyMarket(item.symbol || item.ticker, item.type, item.market, item.submarket),
            })).filter((item) => item.symbol);
            this.chartMarkets = this.mergeMarkets([this.defaultChartMarkets(), this.chartMarkets, mapped]);
            this.notifySubscribers('markets', this.chartMarkets);
            return this.chartMarkets;
        }

        ingestChartBars(symbol, bars) {
            if (!symbol || !bars || !bars.length) return;
            const candles = bars.map((bar) => ({
                time: bar.time,
                open: parseFloat(bar.open),
                high: parseFloat(bar.high),
                low: parseFloat(bar.low),
                close: parseFloat(bar.close),
                epoch: bar.time > 1e12 ? Math.floor(bar.time / 1000) : bar.time,
            }));
            this.candlesBySymbol[symbol] = candles;
            const last = candles[candles.length - 1];
            this.pricesBySymbol[symbol] = last.close;
            this.currentSymbol = symbol;
            this.historicalData = candles;
            this.currentCandle = last;
            this.currentPrice = last.close;
            this.notifySubscribers('market_history', { symbol, candles });
        }

        async fetchChartMarkets() {
            const catalog = this.defaultChartMarkets();
            this.chartMarkets = this.mergeMarkets([catalog, this.chartMarkets]);

            if (!this.connected) {
                await this.connect().catch(() => {});
            }

            try {
                const date = new Date().toISOString().slice(0, 10);
                const times = await this.request({ trading_times: date });
                if (!times.error && times.trading_times && times.trading_times.markets) {
                    const fromTimes = times.trading_times.markets.flatMap((market) =>
                        (market.submarkets || []).flatMap((submarket) =>
                            (submarket.symbols || []).map((item) => ({
                                symbol: item.symbol,
                                name: item.display_name || item.name || item.symbol,
                                type: this.classifyMarket(item.symbol, market.name, market.name, submarket.name),
                            }))
                        )
                    );
                    this.chartMarkets = this.mergeMarkets([this.chartMarkets, fromTimes]);
                }
            } catch (error) {
                console.warn('Market Data Service: trading_times unavailable', error);
            }

            try {
                const active = await this.request({ active_symbols: 'brief', product_type: 'basic' });
                if (!active.error && active.active_symbols) {
                    const fromActive = active.active_symbols.map((item) => {
                        const symbol = item.underlying_symbol || item.symbol;
                        return {
                            symbol,
                            name: item.display_name || item.underlying_symbol_name || symbol,
                            type: this.classifyMarket(symbol, item.market, item.market, item.submarket),
                        };
                    });
                    this.chartMarkets = this.mergeMarkets([this.chartMarkets, fromActive]);
                }
            } catch (error) {
                console.warn('Market Data Service: active_symbols unavailable', error);
            }

            console.log('Market Data Service: chart markets loaded', this.chartMarkets.length);
            this.notifySubscribers('markets', this.chartMarkets);
            return this.chartMarkets;
        }

        getMarkets() {
            return this.chartMarkets.length ? this.chartMarkets : this.defaultChartMarkets();
        }

        getPrice(symbol) {
            return this.pricesBySymbol[symbol];
        }

        getCandles(symbol) {
            return this.candlesBySymbol[symbol] || [];
        }

        getAllMarketData() {
            const data = {};
            Object.keys(this.candlesBySymbol).forEach((symbol) => {
                const candles = this.candlesBySymbol[symbol] || [];
                data[symbol] = {
                    price: this.pricesBySymbol[symbol] || (candles.length ? candles[candles.length - 1].close : null),
                    historical: candles,
                    candle: candles.length ? candles[candles.length - 1] : null,
                    source: 'chart',
                };
            });
            return data;
        }

        /**
         * Disconnect from the WebSocket
         */
        disconnect() {
            if (this.ws) {
                this.ws.close();
                this.ws = null;
            }
            this.connected = false;
            this.subscribers.clear();
        }
    }

    // Create singleton instance
    window.marketDataService = new MarketDataService();

    // Auto-connect on page load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            window.marketDataService.connect().catch(err => {
                console.error('Failed to initialize Market Data Service:', err);
            });
        });
    } else {
        window.marketDataService.connect().catch(err => {
            console.error('Failed to initialize Market Data Service:', err);
        });
    }

})();
