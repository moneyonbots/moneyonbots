/*
 * Floating AI chart panel: Insight, Analysis, Chat.
 * Sends the open chart's symbol, live price, and candles to /api/ai/.
 * 
 * Features:
 * - Multi-tab interface (Insight, Analysis, Gap Analysis, Chat)
 * - Voice recording for questions and news analysis
 * - Real-time chart data integration
 * - AI-powered market analysis and recommendations
 */
(function () {
    // DOM Elements
    const fab = document.getElementById("brain-fab");
    if (!fab) return;

    if (!window.AI_ENABLED) {
        fab.addEventListener("click", () => {
            alert("To enable the AI chart panel, set GROQ_API_KEY or ANTHROPIC_API_KEY in .env and restart the server.");
        });
        return;
    }

    const panel = document.getElementById("brain-panel");
    if (!panel) return;

    const closeBtn = document.getElementById("brain-close");
    const messages = document.getElementById("brain-messages");
    const form = document.getElementById("brain-form");
    const input = document.getElementById("brain-input");
    const voiceBtn = document.getElementById("brain-voice");
    const voiceStatus = document.getElementById("brain-voice-status");
    const voiceMode = document.getElementById("brain-voice-mode");
    const voiceModeMic = document.getElementById("brain-voice-mode-mic");
    const voiceModeClose = document.getElementById("brain-voice-mode-close");
    const voiceModeStatus = document.getElementById("brain-voice-mode-status");
    const voiceOrbContainer = document.getElementById("brain-voice-orb-container");
    const voiceCanvas = document.getElementById("brain-voice-canvas");
    const voiceModeToggle = document.getElementById("brain-voice-mode-toggle");
    const symbolLabel = document.getElementById("brain-current-symbol");

    const tabs = panel.querySelectorAll(".brain-tab");
    const tabPanels = {
        insight: document.getElementById("brain-panel-insight"),
        analysis: document.getElementById("brain-panel-analysis"),
        chat: document.getElementById("brain-panel-chat"),
    };

    // State management
    const history = [];
    let open = false;
    let recorder = null;
    let recordingChunks = [];
    let recordingStartTime = null;
    let recordingTimer = null;
    let voiceModeActive = false;
    let chatHistoryLoaded = false;
    
    // Technical indicator mapping for TradingView
    const STUDY_MAP = {
        RSI: "Relative Strength Index",
        MACD: "MACD",
        MA: "Moving Average",
        MASIMPLE: "Moving Average",
        BB: "Bollinger Bands",
        ATR: "Average True Range",
        STOCHASTIC: "Stochastic",
    };

    // Chart data functions
    function currentSymbol() {
        return window.currentChartSymbol || "";
    }

    function livePrice(symbol) {
        if (window.currentChartPrice != null && (!symbol || symbol === window.currentChartSymbol)) {
            return Number(window.currentChartPrice);
        }
        if (window.marketDataService && symbol) {
            const quoted = window.marketDataService.getPrice(symbol);
            if (quoted != null) return Number(quoted);
        }
        return null;
    }

    function chartCandles(symbol) {
        if (window.marketDataService && symbol) {
            const bars = window.marketDataService.getCandles(symbol);
            if (bars && bars.length) return bars.slice(-240);
        }
        if (window.currentCandleData && symbol === window.currentChartSymbol) {
            return [window.currentCandleData];
        }
        return [];
    }

    function chartPayload() {
        const symbol = currentSymbol();
        return {
            symbol: symbol,
            price: livePrice(symbol),
            candles: chartCandles(symbol),
            timeframe: "60",
        };
    }

    async function loadChatHistory() {
        if (chatHistoryLoaded) return;
        
        try {
            const symbol = currentSymbol();
            const url = symbol ? `/api/ai/chat/history/?symbol=${encodeURIComponent(symbol)}` : '/api/ai/chat/history/';
            const res = await fetch(url);
            const data = await res.json();
            
            if (data.history && Array.isArray(data.history)) {
                // Clear existing history and load from server
                history.length = 0;
                messages.innerHTML = '';
                
                // Load messages from server
                data.history.forEach(msg => {
                    if (msg.role === 'user' || msg.role === 'assistant') {
                        history.push({ role: msg.role, content: msg.content });
                        addMessage(msg.role, msg.content);
                    }
                });
                
                chatHistoryLoaded = true;
            }
        } catch (e) {
            console.warn("Failed to load chat history:", e);
            // Continue with empty history if loading fails
        }
    }

    function validateChartPayload(payload) {
        // The assistant backend handles general queries and news analysis even when no chart or candles are loaded
        return { valid: true };
    }

    // TradingView chart interaction functions
    function withChart(fn) {
        const widget = window.tradingViewWidget;
        if (!widget || typeof widget.activeChart !== "function") {
            return { error: "Chart not ready" };
        }
        const run = function () {
            try {
                fn(widget.activeChart());
            } catch (err) {
                console.warn("AI chart action failed", err);
            }
        };
        if (typeof widget.onChartReady === "function") {
            widget.onChartReady(run);
        } else {
            run();
        }
        return { success: true };
    }

    // AI chart actions for TradingView integration
    window.aiChartActions = {
        addIndicator: function (name) {
            const mapped = STUDY_MAP[String(name || "").toUpperCase()] || name;
            return withChart(function (chart) {
                chart.createStudy(mapped, false, false);
            });
        },
        addHorizontalLine: function (price, color, text) {
            return withChart(function (chart) {
                chart.createShape(
                    { price: Number(price) },
                    {
                        shape: "horizontal_line",
                        lock: false,
                        disableSelection: false,
                        overrides: {
                            linecolor: color || "#26a69a",
                            linewidth: 2,
                            showLabel: Boolean(text),
                            text: text || "",
                        },
                    }
                );
            });
        },
        clearShapes: function () {
            return withChart(function (chart) {
                chart.removeAllShapes();
            });
        },
        applyActions: function (actions) {
            if (!Array.isArray(actions)) return;
            actions.forEach(function (action) {
                const type = (action && action.type) || "";
                if (type === "clear") window.aiChartActions.clearShapes();
                else if (type === "indicator") window.aiChartActions.addIndicator(action.name);
                else if (type === "hline") {
                    window.aiChartActions.addHorizontalLine(action.price, action.color, action.text);
                }
            });
        },
    };

    // UI state management functions
    function setOpen(next) {
        open = next;
        panel.classList.toggle("open", open);
        panel.setAttribute("aria-hidden", open ? "false" : "true");
        fab.classList.toggle("active", open);
        if (open) {
            updateSymbolLabel();
            refreshInsight();
            renderMarketsWithNews();
            // Load chat history when panel opens
            loadChatHistory();
            
            // If entering voice mode, show sphere
            if (voiceModeActive && jarvisSphere) {
                jarvisSphere.start();
            }
        } else {
            // Close voice mode when panel closes
            if (voiceModeActive) {
                exitVoiceMode();
            }
        }
    }

    function setTab(name) {
        tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
        Object.entries(tabPanels).forEach(([key, el]) => {
            if (el) {
                if (key === name) {
                    el.hidden = false;
                    el.style.display = 'flex';
                    // Force reflow to ensure proper rendering
                    void el.offsetHeight;
                    // Ensure chat messages are visible when switching to chat tab
                    if (key === "chat" && messages) {
                        messages.scrollTop = messages.scrollHeight;
                        // Load chat history when switching to chat tab
                        loadChatHistory();
                    }
                } else {
                    el.hidden = true;
                    el.style.display = 'none';
                }
            }
        });
        if (name === "chat" && input) input.focus();
    }

    function getSymbolName(symbol) {
        if (!symbol) return "—";
        if (window.AVAILABLE_MARKETS) {
            const market = window.AVAILABLE_MARKETS.find((m) => m.symbol === symbol);
            if (market) return market.name;
        }
        return symbol;
    }

    function updateSymbolLabel() {
        const symbol = currentSymbol();
        const label = getSymbolName(symbol);
        if (symbolLabel) symbolLabel.textContent = label;
    }

    // Event listeners for UI interactions
    fab.addEventListener("click", () => setOpen(!open));
    closeBtn.addEventListener("click", () => setOpen(false));
    tabs.forEach((tab) => tab.addEventListener("click", () => setTab(tab.dataset.tab)));

    // Insight panel elements and functions
    const dirBadge = document.getElementById("ai-dir-badge");
    const marketName = document.getElementById("ai-market-name");
    const updatedEl = document.getElementById("ai-updated");
    const emptyEl = document.getElementById("ai-insight-empty");
    const fields = {
        price: document.getElementById("m-price"),
        strength: document.getElementById("m-strength"),
        opportunity: document.getElementById("m-opportunity"),
        rsi: document.getElementById("m-rsi"),
        atr: document.getElementById("m-atr"),
        risk: document.getElementById("m-risk"),
        sl: document.getElementById("m-sl"),
        tp: document.getElementById("m-tp"),
        rr: document.getElementById("m-rr"),
        conf: document.getElementById("m-conf"),
    };

    // Utility functions for formatting
    function fmt(n, digits) {
        const value = Number(n);
        if (!Number.isFinite(value)) return "—";
        return value.toFixed(digits == null ? 2 : digits);
    }

    function dirClass(dir) {
        return dir === "Buy" ? "buy" : dir === "Sell" ? "sell" : "neutral";
    }

    function paintPrice() {
        const symbol = currentSymbol();
        const price = livePrice(symbol);
        if (fields.price && price != null) {
            fields.price.textContent = fmt(price, price < 10 ? 5 : 2);
        }
    }

    const newsList = document.getElementById("ai-news-list");
    const newsDot = document.getElementById("ai-news-dot");
    const newsMarkets = document.getElementById("ai-news-markets");
    const analyzeNewsBtn = document.getElementById("analyze-news-btn");
    const newsBackBtn = document.getElementById("ai-news-back-btn");
    const voiceNewsBtn = document.getElementById("brain-voice-news");
    const newsForm = document.getElementById("news-form");
    const newsInput = document.getElementById("news-input");
    const attachBtn = document.querySelector(".brain-attach");
    let selectedNewsMarket = null;
    let newsRecorder = null;
    let newsRecordingChunks = [];

    async function fetchMarketsWithNews() {
        try {
            const res = await fetch("/api/ai/news/");
            const data = await res.json();
            
            if (data.error) {
                console.error("News API error:", data.error);
                if (newsMarkets) {
                    newsMarkets.innerHTML = `<div class="ai-news-empty">News error: ${data.error}</div>`;
                }
                return {};
            }
            
            const news = data.news || [];
            
            // Group news by markets
            const marketNewsMap = {};
            news.forEach(article => {
                const markets = article.markets || [article.category || 'general'];
                markets.forEach(market => {
                    if (!marketNewsMap[market]) {
                        marketNewsMap[market] = [];
                    }
                    marketNewsMap[market].push(article);
                });
            });

            return marketNewsMap;
        } catch (e) {
            console.error("Failed to fetch markets with news:", e);
            if (newsMarkets) {
                newsMarkets.innerHTML = `<div class="ai-news-empty">Failed to load news. Please try again later.</div>`;
            }
            return {};
        }
    }

    async function renderMarketsWithNews() {
        if (!newsMarkets) return;
        
        const marketNewsMap = await fetchMarketsWithNews();
        const markets = Object.keys(marketNewsMap);
        
        if (markets.length === 0) {
            newsMarkets.innerHTML = '<div class="ai-news-empty">No markets with recent news.</div>';
            return;
        }

        const marketButtons = markets.map(market => {
            const count = marketNewsMap[market].length;
            return `<button class="ai-news-market-btn" data-market="${market}">${market} (${count})</button>`;
        }).join('');

        newsMarkets.innerHTML = `<div class="ai-news-markets-grid">${marketButtons}</div>`;

        // Add click handlers
        document.querySelectorAll('.ai-news-market-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const market = this.dataset.market;
                selectMarketForNews(market, marketNewsMap[market]);
            });
        });
    }

    function selectMarketForNews(market, newsArticles) {
        selectedNewsMarket = market;
        
        // Update UI to show selected market news
        newsMarkets.style.display = 'none';
        newsList.style.display = 'block';
        analyzeNewsBtn.style.display = 'block';
        if (newsForm) {
            newsForm.style.display = 'flex';
            // Clear any previous input
            if (newsInput) newsInput.value = '';
        }

        // Render news articles
        const newsHtml = newsArticles.map(article => {
            const title = (article.title || '').replace(/[&<>"']/g, function(c) {
                return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
            });
            const sentiment = article.sentiment ? article.sentiment.toFixed(2) : 'N/A';
            return `
            <div class="ai-news-item">
                <div class="ai-news-body">
                    <div class="ai-news-title-row">
                        <span class="ai-news-headline">${title}</span>
                    </div>
                    <div class="ai-news-sentiment">Sentiment: ${sentiment}</div>
                </div>
            </div>`;
        }).join('');

        newsList.innerHTML = newsHtml || '<div class="ai-news-empty">No news articles for this market.</div>';
    }

    function backToMarkets() {
        selectedNewsMarket = null;
        newsMarkets.style.display = 'block';
        newsList.style.display = 'none';
        analyzeNewsBtn.style.display = 'none';
        if (newsForm) newsForm.style.display = 'none';
    }

    // Add click handler for back button
    if (newsBackBtn) {
        newsBackBtn.addEventListener("click", backToMarkets);
    }

    async function analyzeMarketNews() {
        if (!selectedNewsMarket) {
            alert("Please select a market first.");
            return;
        }
        
        analyzeNewsBtn.textContent = "Analyzing...";
        analyzeNewsBtn.disabled = true;

        try {
            const res = await fetch("/api/ai/news/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    market: selectedNewsMarket,
                    action: "analyze"
                }),
            });
            
            if (!res.ok) {
                throw new Error(`HTTP error! status: ${res.status}`);
            }
            
            const data = await res.json();
            
            if (data.error) {
                // Provide user-friendly error message
                let errorMsg = data.error;
                if (errorMsg.includes("API key") || errorMsg.includes("Invalid")) {
                    errorMsg = "AI API key issue. Please check your .env file has GROQ_API_KEY or ANTHROPIC_API_KEY set.";
                }
                alert("Analysis failed: " + errorMsg);
            } else {
                // Show analysis results in the chat tab
                setTab("chat");
                addMessage("ai", data.response || "Analysis completed for " + selectedNewsMarket);
            }
        } catch (e) {
            console.error("News analysis error:", e);
            alert("Could not reach the analysis API. Please check your internet connection and try again.");
        } finally {
            analyzeNewsBtn.textContent = "Analyze Market News";
            analyzeNewsBtn.disabled = false;
        }
    }

    // Add click handler for analyze news button
    if (analyzeNewsBtn) {
        analyzeNewsBtn.addEventListener("click", analyzeMarketNews);
    }

    // Voice recording for news analysis
    let newsRecordingStartTime = null;
    let newsRecordingTimer = null;

    async function startNewsRecording() {
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            alert("Voice recording is not supported by this browser.");
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            newsRecordingChunks = [];
            newsRecordingStartTime = Date.now();
            newsRecorder = new MediaRecorder(stream);
            
            // Start recording timer
            newsRecordingTimer = setInterval(() => {
                const elapsed = Math.floor((Date.now() - newsRecordingStartTime) / 1000);
                const minutes = Math.floor(elapsed / 60);
                const seconds = elapsed % 60;
                voiceNewsBtn.title = `Recording… ${minutes}:${seconds.toString().padStart(2, '0')} — Click to stop`;
            }, 1000);
            
            newsRecorder.ondataavailable = (event) => {
                if (event.data.size) newsRecordingChunks.push(event.data);
            };
            
            newsRecorder.onstop = async () => {
                clearInterval(newsRecordingTimer);
                stream.getTracks().forEach((track) => track.stop());
                voiceNewsBtn.classList.remove("is-recording");
                voiceNewsBtn.disabled = true;
                voiceNewsBtn.title = "Record voice for news analysis";
                
                try {
                    const blob = new Blob(newsRecordingChunks, { type: newsRecorder.mimeType || "audio/webm" });
                    const formData = new FormData();
                    formData.append("audio", blob, "voice-news.webm");
                    const response = await fetch("/api/ai/transcribe/", { method: "POST", body: formData });
                    const data = await response.json();
                    
                    if (!response.ok || data.error) throw new Error(data.error || "Transcription failed.");
                    
                    // Put the transcribed text in the input field
                    newsInput.value = data.text;
                    newsInput.focus();
                } catch (error) {
                    alert(error.message || "Could not transcribe the recording.");
                } finally {
                    voiceNewsBtn.disabled = false;
                }
            };
            
            newsRecorder.start();
            voiceNewsBtn.classList.add("is-recording");
            voiceNewsBtn.title = "Recording… 0:00 — Click to stop";
        } catch (error) {
            alert("Microphone access was denied or unavailable.");
        }
    }

    if (voiceNewsBtn) {
        voiceNewsBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (newsRecorder && newsRecorder.state === "recording") {
                newsRecorder.stop();
            } else {
                startNewsRecording();
            }
        });
    }

    // Prevent attach button from submitting form
    if (attachBtn) {
        attachBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            // File attachment functionality can be added here
            alert("File attachment feature coming soon!");
        });
    }

    // News form submission handler
    if (newsForm) {
        newsForm.addEventListener("submit", (e) => {
            e.preventDefault();
            const value = newsInput.value.trim();
            if (!value || !selectedNewsMarket) return;
            
            // Switch to chat tab and send the news-related question
            setTab("chat");
            addMessage("user", `Analyze the news for ${selectedNewsMarket}: ${value}`);
            
            // Add thinking indicator
            const thinking = addMessage("ai", "thinking");
            
            // Trigger the news analysis with the text input
            fetch("/api/ai/news/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    market: selectedNewsMarket,
                    action: "analyze",
                    question: value
                }),
            })
            .then(res => res.json())
            .then(analysisData => {
                thinking.remove();
                
                if (analysisData.error) {
                    addMessage("ai", "Analysis failed: " + analysisData.error);
                } else {
                    addMessage("ai", analysisData.response || "Analysis completed for " + selectedNewsMarket);
                }
            })
            .catch(e => {
                thinking.remove();
                addMessage("ai", "Could not reach the analysis API. Please check your internet connection.");
            });
            
            // Clear the input
            newsInput.value = "";
        });
    }

    async function refreshInsight() {
        const symbol = currentSymbol();
        if (!symbol || !dirBadge) return;

        console.log("Refreshing insight for symbol:", symbol);

        let marketLabel = symbol;
        if (window.AVAILABLE_MARKETS) {
            const market = window.AVAILABLE_MARKETS.find((m) => m.symbol === symbol);
            if (market) marketLabel = market.name;
        }

        if (window.SignalNews && newsList) {
            window.SignalNews.refresh(symbol, marketLabel, newsList, { compact: true }).then(() => {
                if (newsDot) newsDot.classList.add("live");
            });
        }

        try {
            const res = await fetch("/api/signals/active/?symbol=" + encodeURIComponent(symbol));
            const data = await res.json();
            console.log("Signals data received:", data);
            const signal = (data.signals || [])[0];
            console.log("Signal for symbol:", signal);
            
            marketName.textContent = (signal && signal.market_name) || marketLabel;
            paintPrice();

            if (!signal) {
                console.log("No signal found for symbol:", symbol);
                // Try to generate real-time analysis using chart analysis API
                try {
                    console.log("Attempting real-time analysis for:", symbol);
                    const payload = chartPayload();
                    const analysisRes = await fetch("/api/ai/chart-analysis/", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload),
                    });
                    const analysisData = await analysisRes.json();
                    console.log("Real-time analysis data:", analysisData);
                    
                    if (analysisData.snapshot) {
                        emptyEl.style.display = "none";
                        const snapshot = analysisData.snapshot;
                        
                        // Generate basic direction from RSI
                        let direction = "Neutral";
                        if (snapshot.rsi !== null && snapshot.rsi !== undefined) {
                            if (snapshot.rsi < 30) direction = "Buy";
                            else if (snapshot.rsi > 70) direction = "Sell";
                        }
                        
                        dirBadge.textContent = direction;
                        dirBadge.className = "dir-badge " + dirClass(direction);
                        updatedEl.textContent = "live";
                        
                        const price = livePrice(symbol);
                        const shown = price != null ? price : snapshot.price;
                        fields.price.textContent = fmt(shown, shown < 10 ? 5 : 2);
                        fields.strength.textContent = "50.00"; // Default strength
                        fields.opportunity.textContent = "5.0"; // Default opportunity
                        fields.rsi.textContent = snapshot.rsi !== null ? fmt(snapshot.rsi, 1) : "—";
                        fields.atr.textContent = snapshot.atr !== null ? fmt(snapshot.atr, 4) : "—";
                        fields.risk.textContent = "Medium";
                        fields.sl.textContent = snapshot.support !== null ? fmt(snapshot.support, 4) : "—";
                        fields.tp.textContent = snapshot.resistance !== null ? fmt(snapshot.resistance, 4) : "—";
                        fields.rr.textContent = "1:2.0"; // Default risk-reward
                        fields.conf.textContent = "65%"; // Default confidence
                        
                        console.log("Real-time analysis displayed");
                        return;
                    }
                } catch (analysisError) {
                    console.error("Real-time analysis failed:", analysisError);
                }
                
                // Fallback to empty state
                emptyEl.style.display = "block";
                emptyEl.textContent = "No stored signal yet. Open Analysis to run AI on this chart's candles.";
                dirBadge.textContent = "—";
                dirBadge.className = "dir-badge neutral";
                updatedEl.textContent = "live";
                ["strength", "opportunity", "rsi", "atr", "risk", "sl", "tp", "rr", "conf"].forEach((key) => {
                    if (fields[key]) fields[key].textContent = "—";
                });
                return;
            }

            console.log("Displaying signal data:", signal);
            emptyEl.style.display = "none";
            dirBadge.textContent = signal.direction;
            dirBadge.className = "dir-badge " + dirClass(signal.direction);
            updatedEl.textContent = new Date(signal.updated_at || Date.now()).toLocaleTimeString();
            const price = livePrice(symbol);
            const shown = price != null ? price : signal.current_price != null ? signal.current_price : signal.price;
            fields.price.textContent = fmt(shown, shown < 10 ? 5 : 2);
            fields.strength.textContent = fmt(signal.signal_strength, 2);
            fields.opportunity.textContent = fmt(signal.opportunity_score, 1);
            fields.rsi.textContent = signal.rsi !== null && signal.rsi !== undefined ? fmt(signal.rsi, 1) : "—";
            fields.atr.textContent = signal.atr !== null && signal.atr !== undefined ? fmt(signal.atr, 4) : "—";
            fields.risk.textContent = signal.risk_level || "—";
            fields.sl.textContent = signal.stop_loss != null ? fmt(signal.stop_loss, 4) : "—";
            fields.tp.textContent = signal.take_profit != null ? fmt(signal.take_profit, 4) : "—";
            fields.rr.textContent = signal.risk_reward ? "1:" + fmt(signal.risk_reward, 1) : "—";
            fields.conf.textContent = signal.model_confidence != null ? fmt(signal.model_confidence * 100, 0) + "%" : "—";
        } catch (e) {
            console.error("AI insight refresh failed", e);
            emptyEl.style.display = "block";
            emptyEl.textContent = "Error loading signals: " + e.message;
        }
    }

    window.addEventListener("chart-symbol-changed", (event) => {
        window.currentChartSymbol = event.detail.symbol;
        updateSymbolLabel();
        if (open) refreshInsight();
        // Reload chat history when symbol changes
        chatHistoryLoaded = false;
        if (open) loadChatHistory();
    });

    window.addEventListener("tick-update", (event) => {
        if (!open) return;
        const symbol = event.detail && event.detail.symbol;
        if (symbol && symbol === currentSymbol()) paintPrice();
    });

    setInterval(() => {
        if (open) {
            updateSymbolLabel();
            paintPrice();
        }
    }, 1000);
    
    setInterval(() => {
        if (open) refreshInsight();
    }, 10000);

    const askBtn = document.getElementById("ask-ai-btn");
    if (askBtn) {
        askBtn.addEventListener("click", () => {
            setTab("chat");
            let name = currentSymbol() || "this market";
            if (window.AVAILABLE_MARKETS && currentSymbol()) {
                const market = window.AVAILABLE_MARKETS.find((m) => m.symbol === currentSymbol());
                if (market) name = market.name;
            }
            input.value = "What's your read on " + name + " right now?";
            input.focus();
        });
    }

    const runBtn = document.getElementById("run-ai-analysis");
    const analysisStatus = document.getElementById("ai-analysis-status");
    const analysisCard = document.getElementById("ai-analysis-card");

    function paintAnalysis(data) {
        const analysis = data.analysis || {};
        const snapshot = data.snapshot || {};
        analysisCard.hidden = false;
        const bias = document.getElementById("ai-analysis-bias");
        const conf = document.getElementById("ai-analysis-conf");
        bias.textContent = analysis.bias || "Neutral";
        bias.className = "dir-badge " + dirClass(analysis.bias);
        conf.textContent = analysis.confidence != null ? analysis.confidence + "% confidence" : "";
        document.getElementById("ai-analysis-summary").textContent = analysis.summary || "";
        document.getElementById("ai-analysis-setup").textContent = analysis.setup ? "Setup: " + analysis.setup : "";
        document.getElementById("ai-analysis-risks").textContent = analysis.risks ? "Risk: " + analysis.risks : "";
        const digits = (snapshot.price || 0) < 10 ? 5 : 2;
        document.getElementById("ai-an-support").textContent = fmt(analysis.support, digits);
        document.getElementById("ai-an-resist").textContent = fmt(analysis.resistance, digits);
        document.getElementById("ai-an-stop").textContent = fmt(analysis.stop, digits);
        document.getElementById("ai-an-target").textContent = fmt(analysis.target, digits);
        if (analysis.rsi == null && snapshot.rsi != null && fields.rsi) {
            fields.rsi.textContent = fmt(snapshot.rsi, 1);
        }
        window.aiChartActions.applyActions(analysis.actions || []);

        const analysisSpeakBtn = document.getElementById("ai-analysis-speak-btn");
        if (analysisSpeakBtn) {
            analysisSpeakBtn.onclick = (e) => {
                e.stopPropagation();
                if (currentSpeechAudio || (window.speechSynthesis && window.speechSynthesis.speaking)) {
                    stopCurrentSpeech();
                } else {
                    const speechBriefing = [
                        analysis.summary || "",
                        analysis.setup ? ("Setup trigger: " + analysis.setup) : "",
                        analysis.risks ? ("Risk factor: " + analysis.risks) : ""
                    ].filter(Boolean).join(". ");
                    if (speechBriefing) speakReply(speechBriefing);
                }
            };
        }
    }

    async function runChartAnalysis() {
        const payload = chartPayload();
        const validation = validateChartPayload(payload);
        
        if (!validation.valid) {
            analysisStatus.textContent = validation.error;
            analysisStatus.style.color = "var(--warn)";
            return;
        }
        
        analysisStatus.textContent = "Analyzing " + payload.symbol + "…";
        analysisStatus.style.color = "var(--text-dim)";
        runBtn.disabled = true;
        try {
            if ((!payload.candles || payload.candles.length < 20) && window.marketDataService) {
                try {
                    const raw = await window.marketDataService.loadHistoricalData(payload.symbol, {
                        granularity: 60,
                        count: 240,
                        end: "latest",
                    });
                    payload.candles = (raw || []).map(function (c) {
                        return {
                            time: c.epoch ? c.epoch * 1000 : c.time,
                            open: c.open,
                            high: c.high,
                            low: c.low,
                            close: c.close,
                            epoch: c.epoch,
                        };
                    });
                } catch (loadErr) {
                    console.warn("Could not prefetch candles for AI analysis", loadErr);
                }
            }
            const res = await fetch("/api/ai/chart-analysis/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (data.error) {
                analysisStatus.textContent = "Error: " + data.error;
                analysisStatus.style.color = "var(--sell)";
                if (data.snapshot) {
                    paintAnalysis(data);
                }
                return;
            }
            analysisStatus.textContent = data.name || payload.symbol;
            analysisStatus.style.color = "var(--buy)";
            paintAnalysis(data);
        } catch (err) {
            console.error("Chart analysis error:", err);
            analysisStatus.textContent = "Could not reach the analysis API. Please check your connection.";
            analysisStatus.style.color = "var(--sell)";
        } finally {
            runBtn.disabled = false;
        }
    }

    if (runBtn) runBtn.addEventListener("click", runChartAnalysis);

    // Stock analysis functions removed - gap analysis tab removed from deriv chart panel
    // Stock analysis should be implemented separately for stock charts

    // Audio functionality removed - JAVIS speech disabled
    // No-op function for audio context initialization (functionality removed)
    function initializeAudioContext() {
        // Audio functionality removed - no-op for compatibility
    }
    
    // Initialize audio context on first user interaction
    document.addEventListener('click', () => {
        initializeAudioContext();
    }, { once: true });
    
    // Also initialize on touch for mobile
    document.addEventListener('touchstart', () => {
        initializeAudioContext();
    }, { once: true });

    function getJarvisVoice() {
        const voices = (window.speechSynthesis ? window.speechSynthesis.getVoices() : []) || availableVoices;
        if (!voices || voices.length === 0) return null;

        console.log("Available voices for selection:", voices.length);
        voices.forEach((v, i) => console.log(`${i}: ${v.name} (${v.lang}) - local: ${v.localService}`));

        function scoreVoice(v) {
            const name = (v.name || "").toLowerCase();
            const lang = (v.lang || "").toLowerCase().replace("_", "-");
            let score = 0;

            const isEnglish = lang.startsWith("en");
            if (!isEnglish) return -500;

            // TOP PRIORITY: Premium Neural / Natural voices (non-robotic)
            if (name.includes("ryan")) score += 600;
            if (name.includes("natural")) score += 300;
            if (name.includes("neural")) score += 300;
            if (name.includes("online")) score += 150;

            // British English priority for the commanding Jarvis tone
            if (lang.includes("en-gb")) score += 200;
            if (name.includes("uk") || name.includes("british") || name.includes("great britain")) score += 150;

            // Authoritative commanding male names
            const bossyMaleNames = [
                "ryan", "george", "guy", "christopher", "arthur", "oliver",
                "daniel", "brian", "alfred", "charles", "edward", "david"
            ];
            for (const n of bossyMaleNames) {
                if (name.includes(n)) {
                    score += 120;
                    break;
                }
            }

            // High-grade system voices
            if (name.includes("google uk english male")) score += 350;
            if (name.includes("microsoft ryan")) score += 400;
            if (name.includes("microsoft george")) score += 250;

            // Penalize female voices and robotic voices
            const femaleNames = ["zira", "susan", "hazel", "jenny", "aria", "sonia", "libby", "mia", "victoria", "karen", "samantha", "stephanie", "catherine", "heera", "female", "woman", "lady"];
            if (femaleNames.some(f => name.includes(f))) score -= 400;
            if (name.includes("desktop") && !name.includes("natural") && !name.includes("neural")) score -= 50;

            return score;
        }

        let bestVoice = null;
        let bestScore = -999;
        for (const v of voices) {
            const s = scoreVoice(v);
            console.log(`Voice: ${v.name} (${v.lang}) - Score: ${s}`);
            if (s > bestScore) {
                bestScore = s;
                bestVoice = v;
            }
        }
        
        console.log("Best voice selected:", bestVoice ? bestVoice.name : "None", "Score:", bestScore);
        return bestVoice;
    }

    function cleanTextForJarvisSpeech(rawText) {
        if (!rawText) return "";
        let text = String(rawText);

        // Strip action blocks and markdown code blocks
        text = text.replace(/```actions[\s\S]*?```/gi, "");
        text = text.replace(/```[\s\S]*?```/g, "");
        text = text.replace(/`([^`]+)`/g, "$1");

        // Normalize non-ASCII quotes, dashes, and garbled symbols
        text = text.replace(/[\u2018\u2019]/g, "'");
        text = text.replace(/[\u201C\u201D]/g, '"');
        text = text.replace(/[\u2013\u2014\u2015\u2212]/g, "-");
        text = text.replace(/â[€\u0080-\u009F]+/g, " ");

        // Strip markdown links [label](url) -> label
        text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");

        // Strip headers, bold, italics, strikethrough, blockquotes
        text = text.replace(/^#+\s+/gm, "");
        text = text.replace(/(\*\*|__)(.*?)\1/g, "$2");
        text = text.replace(/(\*|_)(.*?)\1/g, "$2");
        text = text.replace(/~~(.*?)~~/g, "$1");
        text = text.replace(/^\s*>\s+/gm, "");
        text = text.replace(/^\s*[-*+•]\s+/gm, ". ");
        text = text.replace(/^\s*\d+\.\s+/gm, ". ");

        // Remove emojis and symbols
        text = text.replace(/[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}\u{1F100}-\u{1F1FF}\u{1F200}-\u{1F2FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}]/gu, "");
        text = text.replace(/[⚠✓✔✕✖★☆⚡📈📉🎯💡🚀💰🛡🤖]/g, "");

        // Expand financial symbols and acronyms for natural spoken English
        text = text.replace(/\bEUR\/USD\b/gi, "Euro to U.S. Dollar");
        text = text.replace(/\bGBP\/USD\b/gi, "Pound to U.S. Dollar");
        text = text.replace(/\bUSD\/JPY\b/gi, "U.S. Dollar to Japanese Yen");
        text = text.replace(/\bAUD\/USD\b/gi, "Australian Dollar to U.S. Dollar");
        text = text.replace(/\bUSD\/CAD\b/gi, "U.S. Dollar to Canadian Dollar");
        text = text.replace(/\bUSD\/CHF\b/gi, "U.S. Dollar to Swiss Franc");
        text = text.replace(/\bNZD\/USD\b/gi, "New Zealand Dollar to U.S. Dollar");
        text = text.replace(/\b([A-Z]{3})\/([A-Z]{3})\b/g, "$1 to $2");

        text = text.replace(/\bRSI\b/g, "R.S.I.");
        text = text.replace(/\bMACD\b/g, "M.A.C.D.");
        text = text.replace(/\bEMA\b/g, "E.M.A.");
        text = text.replace(/\bSMA\b/g, "S.M.A.");
        text = text.replace(/\bATR\b/g, "A.T.R.");
        text = text.replace(/\bBB\b/g, "Bollinger Bands");
        text = text.replace(/\bSL\b/g, "Stop Loss");
        text = text.replace(/\bTP\b/g, "Take Profit");
        text = text.replace(/\bR:R\b/gi, "risk to reward");
        text = text.replace(/\b1:(\d+(\.\d+)?)\b/g, "1 to $1");
        text = text.replace(/\bapprox\./gi, "approximately");
        text = text.replace(/\bvs\.?\b/gi, "versus");
        text = text.replace(/\bw\//gi, "with");
        text = text.replace(/\bw\/o\b/gi, "without");
        text = text.replace(/\bpts\b/gi, "points");
        text = text.replace(/\bpt\b/gi, "point");
        text = text.replace(/\bpips\b/gi, "pips");
        text = text.replace(/\bpip\b/gi, "pip");
        text = text.replace(/\bvol\b/gi, "volatility");
        text = text.replace(/%/g, " percent");
        text = text.replace(/\+/g, " plus ");
        text = text.replace(/\$/g, " dollars ");

        // Clean up punctuation and whitespace
        text = text.replace(/[\r\n]+/g, ". ");
        text = text.replace(/\s+/g, " ");
        text = text.replace(/\.{2,}/g, ".");
        text = text.replace(/\s+([.,!?;:])/g, "$1");
        return text.trim();
    }

    // -------------------------------------------------------------------------
    // Advanced 3D Liquid Morphing JARVIS Voice Sphere (Next-Gen Procedural Engine)
    // -------------------------------------------------------------------------
    class JarvisSphere {
        constructor(canvas, container) {
            this.canvas = canvas;
            this.container = container;
            this.ctx = canvas ? canvas.getContext("2d") : null;
            this.state = "idle"; // "idle" | "listening" | "thinking" | "speaking"
            this.animId = null;
            this.t = 0;
            this.audioLevel = 0;
            this.targetAudioLevel = 0;
            this.audioCtx = null;
            this.micAnalyser = null;
            this.outputAnalyser = null;
            this.analyser = null;
            this.dataArray = null;
            this.sourceNode = null;
            this.particles = [];
            this.initParticles();
            this.setupDpr();
        }

        setupDpr() {
            if (!this.canvas) return;
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            this.dpr = dpr;
            const rect = this.canvas.getBoundingClientRect();
            const size = rect.width || 180;
            this.canvas.width = size * dpr;
            this.canvas.height = size * dpr;
            this.width = size;
            this.height = size;
        }

        initParticles() {
            // ChatGPT voice orb has subtle ethereal floating dust/stars
            this.particles = [];
            for (let i = 0; i < 24; i++) {
                const angle = Math.random() * Math.PI * 2;
                const dist = 60 + Math.random() * 32;
                this.particles.push({
                    angle: angle,
                    dist: dist,
                    baseDist: dist,
                    speed: (0.008 + Math.random() * 0.012) * (Math.random() > 0.5 ? 1 : -1),
                    size: 1.0 + Math.random() * 1.8,
                    z: (Math.random() - 0.5) * 40,
                    opacity: 0.2 + Math.random() * 0.5,
                    hue: Math.random() > 0.5 ? 190 : 270
                });
            }
        }

        setStream(stream) {
            if (!stream) return;
            try {
                const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
                if (!AudioCtxClass) return;
                if (!this.audioCtx) this.audioCtx = new AudioCtxClass();
                if (this.audioCtx.state === "suspended") this.audioCtx.resume();
                if (this.sourceNode) {
                    try { this.sourceNode.disconnect(); } catch (e) {}
                    this.sourceNode = null;
                }
                this.micAnalyser = this.audioCtx.createAnalyser();
                this.micAnalyser.fftSize = 256;
                this.micAnalyser.smoothingTimeConstant = 0.8;
                this.dataArray = new Uint8Array(this.micAnalyser.frequencyBinCount);
                this.sourceNode = this.audioCtx.createMediaStreamSource(stream);
                this.sourceNode.connect(this.micAnalyser);
            } catch (err) {
                console.warn("JarvisSphere WebAudio init failed", err);
            }
        }

        stopStream() {
            if (this.sourceNode) {
                try { this.sourceNode.disconnect(); } catch (e) {}
                this.sourceNode = null;
            }
        }

        setState(state) {
            this.state = state;
            if (this.container) {
                this.container.classList.remove("is-speaking", "is-listening", "is-thinking", "is-idle");
                this.container.classList.add("is-" + state);
            }
            if (voiceMode) {
                voiceMode.classList.remove("is-speaking", "is-listening", "is-thinking", "is-idle");
                voiceMode.classList.add("is-" + state);
            }
            
            // Handle thinking state
            if (state === "thinking") {
                // Audio removed
            }
        }

        start() {
            if (!this.canvas) return;
            if (this.animId) return;
            this.setupDpr();
            const loop = () => {
                this.draw();
                this.animId = requestAnimationFrame(loop);
            };
            this.animId = requestAnimationFrame(loop);
        }

        stop() {
            if (this.animId) {
                cancelAnimationFrame(this.animId);
                this.animId = null;
            }
            this.stopStream();
            if (this.ctx && this.canvas) {
                this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            }
        }

        draw() {
            if (!this.ctx || !this.canvas) return;
            const ctx = this.ctx;
            const w = this.width;
            const h = this.height;
            const dpr = this.dpr || 1;
            const cx = (w / 2) * dpr;
            const cy = (h / 2) * dpr;

            ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

            // Audio amplitude evaluation
            let activeAnalyser = null;
            if (this.state === "speaking" && this.outputAnalyser) {
                activeAnalyser = this.outputAnalyser;
            } else if (this.state === "listening" && this.micAnalyser) {
                activeAnalyser = this.micAnalyser;
            } else if (this.analyser) {
                activeAnalyser = this.analyser;
            }

            if (activeAnalyser) {
                if (!this.dataArray || this.dataArray.length !== activeAnalyser.frequencyBinCount) {
                    this.dataArray = new Uint8Array(activeAnalyser.frequencyBinCount);
                }
                activeAnalyser.getByteFrequencyData(this.dataArray);
                let sum = 0;
                const count = Math.min(this.dataArray.length, 36);
                for (let i = 0; i < count; i++) {
                    sum += this.dataArray[i];
                }
                const avg = sum / (count * 255);
                this.targetAudioLevel = avg;
            } else if (this.state === "speaking") {
                // Natural speech rhythm wave simulation
                const speechWave = (Math.sin(this.t * 7.2) * 0.32 + Math.sin(this.t * 12.5) * 0.22 + 0.42);
                this.targetAudioLevel = Math.max(0.15, Math.min(0.85, speechWave));
            } else {
                this.targetAudioLevel = 0;
            }

            // Smooth audio damping
            this.audioLevel += (this.targetAudioLevel - this.audioLevel) * 0.22;

            // Speed based on ChatGPT states
            let speed = 0.022;
            if (this.state === "thinking") speed = 0.065; // Swift orbital swirl
            else if (this.state === "speaking") speed = 0.048; // Expressive pulsation
            else if (this.state === "listening") speed = 0.035; // Sensitive rippling
            this.t += speed;

            const baseRadius = (w * 0.29) * dpr;
            const pulseAmp = (this.audioLevel * 18 * dpr);
            const r = baseRadius + pulseAmp;

            // -------------------------------------------------------------
            // A. ChatGPT Outer Atmospheric Diffuse Glow
            // -------------------------------------------------------------
            const outerGlow = ctx.createRadialGradient(cx, cy, r * 0.35, cx, cy, r * 1.7);
            if (this.state === "listening") {
                outerGlow.addColorStop(0, "rgba(20, 184, 166, 0.45)");
                outerGlow.addColorStop(0.5, "rgba(56, 189, 248, 0.2)");
                outerGlow.addColorStop(1, "rgba(20, 184, 166, 0)");
            } else if (this.state === "thinking") {
                outerGlow.addColorStop(0, "rgba(99, 102, 241, 0.45)");
                outerGlow.addColorStop(0.5, "rgba(168, 85, 247, 0.25)");
                outerGlow.addColorStop(1, "rgba(99, 102, 241, 0)");
            } else if (this.state === "speaking") {
                outerGlow.addColorStop(0, "rgba(14, 165, 233, 0.55)");
                outerGlow.addColorStop(0.45, "rgba(59, 130, 246, 0.28)");
                outerGlow.addColorStop(0.8, "rgba(244, 63, 94, 0.15)");
                outerGlow.addColorStop(1, "rgba(14, 165, 233, 0)");
            } else {
                // Idle: Pure iconic ChatGPT cyan-blue-purple soft glow
                outerGlow.addColorStop(0, "rgba(56, 189, 248, 0.35)");
                outerGlow.addColorStop(0.5, "rgba(129, 140, 248, 0.18)");
                outerGlow.addColorStop(1, "rgba(56, 189, 248, 0)");
            }
            ctx.fillStyle = outerGlow;
            ctx.beginPath();
            ctx.arc(cx, cy, r * 1.7, 0, Math.PI * 2);
            ctx.fill();

            // -------------------------------------------------------------
            // B. ChatGPT Smooth Organic Morphing Sphere (Harmonic Fourier Waves)
            // -------------------------------------------------------------
            const numPoints = 140;
            const points = [];
            const morphIntensity = (this.state === "listening" ? (3 + this.audioLevel * 24) :
                                    this.state === "thinking" ? 10 :
                                    this.state === "speaking" ? (7 + Math.sin(this.t * 5) * 6 + this.audioLevel * 16) : 3.5) * dpr;

            for (let i = 0; i < numPoints; i++) {
                const angle = (i / numPoints) * Math.PI * 2;
                // Complex organic harmonics resembling 3D fluid membrane
                const h1 = Math.sin(angle * 2 + this.t * 1.8);
                const h2 = Math.cos(angle * 3 - this.t * 1.4);
                const h3 = Math.sin(angle * 4 + this.t * 2.6) * 0.45;
                const h4 = Math.cos(angle * 6 - this.t * 3.2) * 0.22;
                
                const distortion = (h1 + h2 + h3 + h4) * morphIntensity;
                const currentRadius = Math.max(r * 0.6, r + distortion);
                points.push({
                    x: cx + Math.cos(angle) * currentRadius,
                    y: cy + Math.sin(angle) * currentRadius
                });
            }

            // Draw smooth curve perimeter
            ctx.save();
            ctx.beginPath();
            ctx.moveTo((points[0].x + points[numPoints - 1].x) / 2, (points[0].y + points[numPoints - 1].y) / 2);
            for (let i = 0; i < numPoints; i++) {
                const next = points[(i + 1) % numPoints];
                const midX = (points[i].x + next.x) / 2;
                const midY = (points[i].y + next.y) / 2;
                ctx.quadraticCurveTo(points[i].x, points[i].y, midX, midY);
            }
            ctx.closePath();

            // Base spherical dark obsidian depth (ChatGPT voice canvas base)
            ctx.fillStyle = "#0c1222";
            ctx.fill();

            // Clip all internal fluid gradient layers inside the morphing sphere
            ctx.save();
            ctx.clip();

            // -------------------------------------------------------------
            // C. ChatGPT 4o Iconic Fluid Gradients (Cyan, Indigo, Magenta, Coral)
            // -------------------------------------------------------------
            // Layer 1: Swirling Deep Azure / Violet Bed
            const deepGrad = ctx.createLinearGradient(
                cx + Math.cos(this.t * 0.7) * r,
                cy + Math.sin(this.t * 0.7) * r,
                cx - Math.cos(this.t * 0.7) * r,
                cy - Math.sin(this.t * 0.7) * r
            );
            deepGrad.addColorStop(0, "#0ea5e9");
            deepGrad.addColorStop(0.35, "#3b82f6");
            deepGrad.addColorStop(0.7, "#6366f1");
            deepGrad.addColorStop(1, "#8b5cf6");
            ctx.fillStyle = deepGrad;
            ctx.fillRect(cx - r * 1.5, cy - r * 1.5, r * 3, r * 3);

            // Layer 2: Swirling Cyan/Teal Fluid Blobs (Additive Blend)
            ctx.globalCompositeOperation = "screen";
            const b1X = cx + Math.cos(this.t * 1.2) * (r * 0.45);
            const b1Y = cy + Math.sin(this.t * 0.9) * (r * 0.45);
            const blob1 = ctx.createRadialGradient(b1X, b1Y, 0, b1X, b1Y, r * 0.95);
            blob1.addColorStop(0, "rgba(34, 211, 238, 0.95)");
            blob1.addColorStop(0.4, "rgba(6, 182, 212, 0.7)");
            blob1.addColorStop(0.8, "rgba(14, 165, 233, 0.25)");
            blob1.addColorStop(1, "rgba(14, 165, 233, 0)");
            ctx.fillStyle = blob1;
            ctx.beginPath();
            ctx.arc(b1X, b1Y, r * 0.95, 0, Math.PI * 2);
            ctx.fill();

            // Layer 3: Vibrant Coral / Rose Accent Fluid Blob (Iconic ChatGPT warm highlight)
            const b2X = cx + Math.cos(-this.t * 1.4 + Math.PI) * (r * 0.4);
            const b2Y = cy + Math.sin(this.t * 1.1 + Math.PI * 0.5) * (r * 0.4);
            const blob2 = ctx.createRadialGradient(b2X, b2Y, 0, b2X, b2Y, r * 0.85);
            blob2.addColorStop(0, "rgba(251, 113, 133, 0.95)");
            blob2.addColorStop(0.4, "rgba(244, 63, 94, 0.65)");
            blob2.addColorStop(0.75, "rgba(217, 70, 239, 0.25)");
            blob2.addColorStop(1, "rgba(244, 63, 94, 0)");
            ctx.fillStyle = blob2;
            ctx.beginPath();
            ctx.arc(b2X, b2Y, r * 0.85, 0, Math.PI * 2);
            ctx.fill();

            // Layer 4: Floating White/Sky Core Luminescence
            const coreX = cx + Math.sin(this.t * 1.5) * (r * 0.2);
            const coreY = cy + Math.cos(this.t * 1.3) * (r * 0.2);
            const coreGlow = ctx.createRadialGradient(coreX, coreY, 0, coreX, coreY, r * 0.65);
            coreGlow.addColorStop(0, "rgba(255, 255, 255, 0.85)");
            coreGlow.addColorStop(0.35, "rgba(224, 242, 254, 0.55)");
            coreGlow.addColorStop(0.7, "rgba(186, 230, 253, 0.15)");
            coreGlow.addColorStop(1, "rgba(255, 255, 255, 0)");
            ctx.fillStyle = coreGlow;
            ctx.beginPath();
            ctx.arc(coreX, coreY, r * 0.65, 0, Math.PI * 2);
            ctx.fill();

            // Layer 5: State-Specific Color Infusion
            if (this.state === "listening") {
                // Emerald/Mint reactive pulse for user listening
                const listenBlob = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 0.9);
                listenBlob.addColorStop(0, `rgba(52, 211, 153, ${0.45 + this.audioLevel * 0.45})`);
                listenBlob.addColorStop(0.6, "rgba(16, 185, 129, 0.3)");
                listenBlob.addColorStop(1, "rgba(5, 150, 105, 0)");
                ctx.fillStyle = listenBlob;
                ctx.beginPath();
                ctx.arc(cx, cy, r * 0.9, 0, Math.PI * 2);
                ctx.fill();
            } else if (this.state === "thinking") {
                // Violet/Indigo deep processing swirl
                const thinkBlob = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 0.9);
                thinkBlob.addColorStop(0, "rgba(192, 132, 252, 0.65)");
                thinkBlob.addColorStop(0.5, "rgba(147, 51, 234, 0.35)");
                thinkBlob.addColorStop(1, "rgba(126, 34, 206, 0)");
                ctx.fillStyle = thinkBlob;
                ctx.beginPath();
                ctx.arc(cx, cy, r * 0.9, 0, Math.PI * 2);
                ctx.fill();
            }

            // Layer 6: Soft 3D Fresnel Edge & Inner Shadow (Glassy physical realism)
            ctx.globalCompositeOperation = "source-over";
            const fresnel = ctx.createRadialGradient(cx, cy, r * 0.65, cx, cy, r);
            fresnel.addColorStop(0, "rgba(0, 0, 0, 0)");
            fresnel.addColorStop(0.7, "rgba(10, 15, 30, 0.15)");
            fresnel.addColorStop(0.95, "rgba(15, 23, 42, 0.65)");
            fresnel.addColorStop(1, "rgba(2, 6, 23, 0.85)");
            ctx.fillStyle = fresnel;
            ctx.beginPath();
            ctx.arc(cx, cy, r * 1.1, 0, Math.PI * 2);
            ctx.fill();

            // Specular Glass Reflection Sheen (Top Left)
            const specX = cx - r * 0.32;
            const specY = cy - r * 0.32;
            const specGrad = ctx.createRadialGradient(specX, specY, 0, specX, specY, r * 0.7);
            specGrad.addColorStop(0, "rgba(255, 255, 255, 0.65)");
            specGrad.addColorStop(0.25, "rgba(255, 255, 255, 0.2)");
            specGrad.addColorStop(0.65, "rgba(255, 255, 255, 0)");
            ctx.fillStyle = specGrad;
            ctx.beginPath();
            ctx.arc(specX, specY, r * 0.7, 0, Math.PI * 2);
            ctx.fill();

            ctx.restore(); // End clipping

            // -------------------------------------------------------------
            // D. Ultra-Thin Ethereal Rim Light
            // -------------------------------------------------------------
            ctx.save();
            ctx.lineWidth = 1.6 * dpr;
            let rimColor = "rgba(255, 255, 255, 0.45)";
            if (this.state === "listening") rimColor = "rgba(167, 243, 208, 0.7)";
            else if (this.state === "speaking") rimColor = "rgba(224, 242, 254, 0.8)";
            else if (this.state === "thinking") rimColor = "rgba(233, 213, 255, 0.7)";
            ctx.strokeStyle = rimColor;
            ctx.stroke();
            ctx.restore();

            // -------------------------------------------------------------
            // E. Ambient Ethereal Micro-Sparks
            // -------------------------------------------------------------
            this.drawDust(ctx, cx, cy, dpr);
        }

        drawDust(ctx, cx, cy, dpr) {
            ctx.save();
            for (const p of this.particles) {
                p.angle += p.speed * (this.state === "thinking" ? 2.2 : (this.state === "speaking" ? 1.4 : 1.0));
                const rad = (p.baseDist + Math.sin(this.t + p.angle * 2) * 6) * dpr;
                const px = cx + Math.cos(p.angle) * rad;
                const py = cy + Math.sin(p.angle) * rad * 0.85;

                ctx.beginPath();
                ctx.arc(px, py, p.size * dpr, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(255, 255, 255, ${p.opacity * 0.65})`;
                ctx.shadowColor = "rgba(255, 255, 255, 0.8)";
                ctx.shadowBlur = 4 * dpr;
                ctx.fill();
            }
            ctx.restore();
        }
    }

    const jarvisSphere = voiceCanvas ? new JarvisSphere(voiceCanvas, voiceOrbContainer) : null;

    let currentSpeechSession = 0;
    let currentSpeechAudio = null;
    let currentSpeechAudioUrl = null;
    let activeUtterance = null;

    function playVoiceChime(type) {
        try {
            const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtxClass) return;
            const ctx = (jarvisSphere && jarvisSphere.audioCtx) ? jarvisSphere.audioCtx : new AudioCtxClass();
            if (ctx.state === "suspended") ctx.resume();
            
            const now = ctx.currentTime;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);

            if (type === "start") {
                // Soft musical upward chime (ChatGPT style)
                osc.type = "sine";
                osc.frequency.setValueAtTime(523.25, now);
                osc.frequency.exponentialRampToValueAtTime(783.99, now + 0.12);
                gain.gain.setValueAtTime(0.001, now);
                gain.gain.linearRampToValueAtTime(0.06, now + 0.025);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.16);
                osc.start(now);
                osc.stop(now + 0.17);
            } else if (type === "done") {
                // Soft musical acknowledgment chime (ChatGPT style)
                osc.type = "sine";
                osc.frequency.setValueAtTime(783.99, now);
                osc.frequency.exponentialRampToValueAtTime(659.25, now + 0.12);
                gain.gain.setValueAtTime(0.001, now);
                gain.gain.linearRampToValueAtTime(0.05, now + 0.025);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.16);
                osc.start(now);
                osc.stop(now + 0.17);
            }
        } catch (e) {
            // WebAudio autoplay or permission restriction
        }
    }

    function stopCurrentSpeech() {
        const wasSpeaking = (currentSpeechAudio != null) || 
                            (typeof window !== "undefined" && window.speechSynthesis && window.speechSynthesis.speaking) || 
                            (jarvisSphere && jarvisSphere.state === "speaking");
        currentSpeechSession++;
        if (currentSpeechAudio) {
            try {
                currentSpeechAudio.pause();
                currentSpeechAudio.currentTime = 0;
            } catch (e) {}
            currentSpeechAudio = null;
        }
        if (currentSpeechAudioUrl) {
            try { URL.revokeObjectURL(currentSpeechAudioUrl); } catch (e) {}
            currentSpeechAudioUrl = null;
        }
        if (typeof window !== "undefined" && window.speechSynthesis) {
            try { window.speechSynthesis.cancel(); } catch (e) {}
        }
        activeUtterance = null;
        window.__jarvisActiveUtterance = null;
        if (jarvisSphere && jarvisSphere.state === "speaking") {
            jarvisSphere.setState("idle");
        }
        return wasSpeaking;
    }

    async function speakReply(text) {
        // Audio functionality removed - JAVIS speech disabled
        return Promise.resolve();
    }

            return new Promise((resolve) => {
                let finished = false;
                function finish() {
                    if (finished) return;
                    finished = true;
                    if (currentSpeechAudioUrl) {
                        try { URL.revokeObjectURL(currentSpeechAudioUrl); } catch (e) {}
                        currentSpeechAudioUrl = null;
                    }
                    currentSpeechAudio = null;
                    if (sessionId === currentSpeechSession && jarvisSphere) {
                        jarvisSphere.setState("idle");
                    }
                    if (sessionId === currentSpeechSession && voiceModeStatus && voiceModeActive) {
                        voiceModeStatus.textContent = "Listening...";
                    }
                    resolve();
                }

                audio.onplay = () => {
                    console.log("Neural TTS audio started playing with volume:", audio.volume);
                    if (sessionId === currentSpeechSession) {
                        if (jarvisSphere) jarvisSphere.setState("speaking");
                        if (voiceModeStatus) voiceModeStatus.textContent = "Speaking... Tap to interrupt";
                    }
                };
                audio.onended = finish;
                audio.onerror = (e) => {
                    console.warn("Human neural audio playback error, fallback to browser voice:", e);
                    finish();
                };

                // Connect audio to sphere output analyser for real-time visual wave reaction
                try {
                    const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
                    if (AudioCtxClass && jarvisSphere) {
                        if (!jarvisSphere.audioCtx) jarvisSphere.audioCtx = new AudioCtxClass();
                        if (jarvisSphere.audioCtx.state === "suspended") jarvisSphere.audioCtx.resume();
                        if (!jarvisSphere.outputAnalyser) {
                            jarvisSphere.outputAnalyser = jarvisSphere.audioCtx.createAnalyser();
                            jarvisSphere.outputAnalyser.fftSize = 256;
                            jarvisSphere.outputAnalyser.smoothingTimeConstant = 0.75;
                            jarvisSphere.outputAnalyser.connect(jarvisSphere.audioCtx.destination);
                        }
                        const source = jarvisSphere.audioCtx.createMediaElementSource(audio);
                        source.connect(jarvisSphere.outputAnalyser);
                    }
                } catch (audioCtxErr) {}

                // Ensure audio plays immediately without user interaction
                console.log("Attempting to play neural TTS audio with volume:", audio.volume);
                audio.play().then(() => {
                    console.log("Neural TTS audio started successfully");
                }).catch((playErr) => {
                    console.warn("Audio play() blocked, attempting autoplay workaround:", playErr);
                    // Try to resume audio context and play again
                    try {
                        if (jarvisSphere && jarvisSphere.audioCtx && jarvisSphere.audioCtx.state === "suspended") {
                            jarvisSphere.audioCtx.resume().then(() => {
                                console.log("Audio context resumed, retrying play");
                                audio.play().catch(() => {
                                    console.warn("Audio play failed after context resume");
                                    finish();
                                });
                            }).catch(() => finish());
                        } else {
                            console.warn("No audio context available, finishing");
                            finish();
                        }
                    } catch (e) {
                        console.warn("Audio context resume failed:", e);
                        finish();
                    }
                });
            });
        } catch (err) {
            console.warn("Human neural TTS fetch error:", err);
        }
    }

    // Audio functions removed - JAVIS speech disabled
            utterance.onend = finish;
            utterance.onerror = (evt) => {
                console.warn("Browser speech fallback error:", evt);
                finish();
            };

            try {
                // Ensure speech synthesis is ready and play immediately
                console.log("Starting speech synthesis with volume:", utterance.volume);
                
                // Cancel any existing speech to prevent conflicts
                window.speechSynthesis.cancel();
                
                // Resume if paused
                if (window.speechSynthesis.paused) {
                    console.log("Resuming paused speech synthesis");
                    window.speechSynthesis.resume();
                }
                
                // Speak the utterance
                window.speechSynthesis.speak(utterance);
                
                // Multiple checks to ensure speech is playing
                setTimeout(() => {
                    if (window.speechSynthesis.paused) {
                        console.log("Speech was paused, resuming...");
                        window.speechSynthesis.resume();
                    }
                    // Force another check
                    setTimeout(() => {
                        if (window.speechSynthesis.paused) {
                            console.log("Speech still paused, forcing resume...");
                            window.speechSynthesis.resume();
                        }
                    }, 200);
                }, 100);
                
                // Final check to ensure audio is playing
                setTimeout(() => {
                    if (window.speechSynthesis.speaking) {
                        console.log("JARVIS is speaking successfully");
                    } else {
                        console.warn("JARVIS speech may not be playing");
                    }
                }, 300);
                
            } catch (err) {
                console.warn("Browser speech synthesis error:", err);
                finish();
            }
        });
    }

    // Audio functions removed - JAVIS speech disabled

    async function loadChatHistory() {
        if (!messages) return;
        try {
            const res = await fetch("/api/ai/chat/history/");
            if (!res.ok) return;
            const data = await res.json();
            if (data.history && data.history.length > 0) {
                messages.innerHTML = "";
                history.length = 0;
                for (const item of data.history) {
                    history.push({ role: item.role, content: item.content });
                    addMessage(item.role, item.content);
                }
                messages.scrollTop = messages.scrollHeight;
                chatHistoryLoaded = true;
            }
        } catch (e) {
            console.warn("Could not load user chat history:", e);
        }
    }

    function addMessage(role, text) {
        const div = document.createElement("div");
        div.className = "brain-msg brain-msg-" + (role === "user" ? "user" : "ai");
        
        if (role === "ai" && text === "thinking") {
            div.classList.add("brain-msg-thinking");
            div.innerHTML = '<span class="thinking-indicator"><span></span><span></span><span></span></span>';
        } else {
            div.textContent = text;
            if (role === "ai" && text && text.trim() && text !== "thinking") {
                const speakBtn = document.createElement("button");
                speakBtn.type = "button";
                speakBtn.className = "brain-msg-speak";
                speakBtn.title = "Listen to JARVIS human voice";
                speakBtn.setAttribute("aria-label", "Listen to JARVIS human voice");
                speakBtn.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>';
                speakBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    if (currentSpeechAudio || (window.speechSynthesis && window.speechSynthesis.speaking)) {
                        stopCurrentSpeech();
                    } else {
                        speakReply(text);
                    }
                });
                div.appendChild(speakBtn);
            }
        }
        
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
        return div;
    }

    // Prevent voice button from triggering form submission
    if (voiceBtn) {
        voiceBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
    }

    async function send(message, voiceReply = false) {
        if (!message || message.trim() === "") {
            return;
        }
        
        // Auto-enable voice reply if in voice mode
        if (voiceModeActive) {
            voiceReply = true;
        }
        
        const payload = chartPayload();
        const validation = validateChartPayload(payload);
        
        if (!validation.valid) {
            addMessage("ai", "⚠ " + validation.error + " Please select a market on the chart first.");
            return;
        }
        
        // Replace symbol code with symbol name for better display
        if (payload.symbol) {
            payload.symbol_name = getSymbolName(payload.symbol);
        }
        
        addMessage("user", message);
        history.push({ role: "user", content: message });
        const thinking = addMessage("ai", "thinking");
        payload.message = message;
        payload.history = history.slice(0, -1);
        payload.voice_input = voiceReply; // Flag to use Gemini for voice input

        if (voiceReply && jarvisSphere) {
            jarvisSphere.setState("thinking");
            console.log("Set sphere to thinking state");
        }

        try {
            const res = await fetch("/api/ai/chat/stream/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            if (!res.ok || !res.body) {
                throw new Error(`HTTP ${res.status}`);
            }

            thinking.remove();

            // Create streaming AI message bubble
            const aiMsg = document.createElement("div");
            aiMsg.className = "brain-msg brain-msg-ai";
            const textSpan = document.createElement("span");
            aiMsg.appendChild(textSpan);
            messages.appendChild(aiMsg);
            messages.scrollTop = messages.scrollHeight;

            const reader = res.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let accumulatedText = "";
            let buffer = "";
            let finalActions = [];
            let streamSuccess = false;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop(); // keep partial line

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed.startsWith("data:")) continue;
                    const jsonStr = trimmed.replace(/^data:\s*/, "");
                    if (!jsonStr) continue;

                    try {
                        const parsed = JSON.parse(jsonStr);
                        if (parsed.error) {
                            textSpan.textContent = "⚠ " + parsed.error;
                            streamSuccess = false;
                            break;
                        }
                        if (parsed.chunk) {
                            streamSuccess = true;
                            accumulatedText += parsed.chunk;
                            // Clean out any raw actions blocks from view while streaming
                            const displayText = accumulatedText.replace(/```actions[\s\S]*?```/g, "").replace(/```actions[\s\S]*$/, "");
                            textSpan.textContent = displayText;
                            messages.scrollTop = messages.scrollHeight;
                        }
                        if (parsed.done) {
                            if (parsed.actions) finalActions = parsed.actions;
                            if (parsed.full_reply) accumulatedText = parsed.full_reply;
                        }
                    } catch (e) {
                        // ignore malformed JSON chunk
                    }
                }
            }

            const cleanFinal = accumulatedText.replace(/```actions[\s\S]*?```/g, "").trim() || accumulatedText;
            textSpan.textContent = cleanFinal;

            if (cleanFinal) {
                history.push({ role: "assistant", content: cleanFinal });

                // Attach speak button to message bubble
                const speakBtn = document.createElement("button");
                speakBtn.type = "button";
                speakBtn.className = "brain-msg-speak";
                speakBtn.title = "Listen to JARVIS human voice";
                speakBtn.setAttribute("aria-label", "Listen to JARVIS human voice");
                speakBtn.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>';
                speakBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    if (currentSpeechAudio || (window.speechSynthesis && window.speechSynthesis.speaking)) {
                        stopCurrentSpeech();
                    } else {
                        speakReply(cleanFinal);
                    }
                });
                aiMsg.appendChild(speakBtn);
            }

            if (finalActions && finalActions.length > 0) {
                window.aiChartActions.applyActions(finalActions);
            }

            // Voice response if requested - immediate response
            if (voiceReply && cleanFinal) {
                const turnSession = currentSpeechSession;
                console.log("Voice reply requested, speaking:", cleanFinal);
                await speakReply(cleanFinal);
                if (turnSession === currentSpeechSession && voiceModeActive && !isProcessingSpeech) {
                    // Minimal delay for natural conversation flow
                    setTimeout(() => {
                        if (turnSession === currentSpeechSession && voiceModeActive && !isProcessingSpeech && (!recorder || recorder.state !== "recording")) {
                            startVoiceListening();
                        }
                    }, 100);
                }
            } else if (voiceReply && jarvisSphere) {
                jarvisSphere.setState("idle");
            }
        } catch (e) {
            console.error("Streaming chat error, attempting standard fallback:", e);
            thinking.remove();
            try {
                const fallbackRes = await fetch("/api/ai/chat/", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload),
                });
                const data = await fallbackRes.json();
                if (data.error) {
                    addMessage("ai", "⚠ " + data.error);
                } else {
                    addMessage("ai", data.reply);
                    history.push({ role: "assistant", content: data.reply });
                    window.aiChartActions.applyActions(data.actions || []);
                    if (voiceReply) {
                        const turnSession = currentSpeechSession;
                        console.log("Fallback voice reply requested, speaking:", data.reply);
                        await speakReply(data.reply);
                        if (turnSession === currentSpeechSession && voiceModeActive && !isProcessingSpeech) {
                            // Minimal delay for immediate conversation flow
                            setTimeout(() => {
                                if (turnSession === currentSpeechSession && voiceModeActive && !isProcessingSpeech && (!recorder || recorder.state !== "recording")) {
                                    startVoiceListening();
                                }
                            }, 100);
                        }
                    }
                }
            } catch (err) {
                addMessage("ai", "⚠ Couldn't reach Jarvis backend — please verify your connection.");
            }
            if (voiceReply && jarvisSphere && (!voiceModeActive || !voiceReply)) jarvisSphere.setState("idle");
        }
    }

    form.addEventListener("submit", (e) => {
        e.preventDefault();
        const value = input.value.trim();
        if (!value) return;
        input.value = "";
        send(value, false); // Voice disabled - automatic speech disabled
    });

    function setVoiceStatus(message) {
        if (!voiceStatus) return;
        voiceStatus.hidden = !message;
        voiceStatus.textContent = message;
    }

    function setVoiceModeStatus(message, isError = false) {
        if (!voiceModeStatus) return;
        if (isError && message) {
            voiceModeStatus.hidden = false;
            voiceModeStatus.textContent = message;
        } else {
            voiceModeStatus.hidden = true;
            voiceModeStatus.textContent = "";
        }
        setVoiceStatus(message);
    }

    function cleanupVoiceRecording() {
        if (vadTimer) {
            clearInterval(vadTimer);
            vadTimer = null;
        }
        if (recordingTimer) {
            clearInterval(recordingTimer);
            recordingTimer = null;
        }
        if (recorder) {
            try {
                if (recorder.state === "recording") {
                    recorder.onstop = null;
                    recorder.stop();
                }
            } catch (e) {}
            recorder = null;
        }
        recordingChunks = [];
        hasDetectedSpeech = false;
        speechConsecutiveFrames = 0;
        if (voiceBtn) {
            voiceBtn.classList.remove("is-recording");
            voiceBtn.title = "Record a voice question";
        }
        if (jarvisSphere) {
            jarvisSphere.stopStream();
        }
    }

    function setupVAD(stream) {
        try {
            const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtxClass) return;
            if (!jarvisSphere.audioCtx) jarvisSphere.audioCtx = new AudioCtxClass();
            const ctx = jarvisSphere.audioCtx;
            if (ctx.state === "suspended") ctx.resume();

            if (vadSource) {
                try { vadSource.disconnect(); } catch (e) {}
                vadSource = null;
            }

            vadAnalyser = ctx.createAnalyser();
            vadAnalyser.fftSize = 256;
            vadAnalyser.smoothingTimeConstant = 0.5;
            vadDataArray = new Uint8Array(vadAnalyser.frequencyBinCount);

            vadSource = ctx.createMediaStreamSource(stream);
            vadSource.connect(vadAnalyser);
            // DO NOT connect to destination to prevent mic feedback!
        } catch (e) {
            console.warn("VAD setup error:", e);
        }
    }

    function startVADLoop() {
        if (vadTimer) clearInterval(vadTimer);
        hasDetectedSpeech = false;
        speechConsecutiveFrames = 0;
        lastSpeechTimestamp = Date.now();
        const startTimestamp = Date.now();

        vadTimer = setInterval(() => {
            if (!recorder || recorder.state !== "recording") {
                clearInterval(vadTimer);
                vadTimer = null;
                return;
            }

            if (vadAnalyser && vadDataArray) {
                vadAnalyser.getByteFrequencyData(vadDataArray);
                // Vocal frequency bins: ~250 Hz to ~3800 Hz - focused on human speech range
                let sum = 0;
                let count = 0;
                const minBin = 3;
                const maxBin = 45;
                for (let i = minBin; i <= maxBin && i < vadDataArray.length; i++) {
                    sum += vadDataArray[i];
                    count++;
                }
                const avg = count > 0 ? sum / count : 0;
                // Increased threshold to filter out background noise more aggressively
                const SPEECH_THRESHOLD = 25;
                // Require more consecutive frames to confirm speech (reduces false positives)
                const SPEECH_FRAME_THRESHOLD = 4;

                if (avg > SPEECH_THRESHOLD) {
                    speechConsecutiveFrames++;
                    if (speechConsecutiveFrames >= SPEECH_FRAME_THRESHOLD) {
                        hasDetectedSpeech = true;
                        lastSpeechTimestamp = Date.now();
                        if (voiceModeStatus) {
                            voiceModeStatus.textContent = "Listening... I'm hearing you";
                        }
                    }
                } else {
                    speechConsecutiveFrames = 0;
                    if (hasDetectedSpeech) {
                        const silenceDuration = Date.now() - lastSpeechTimestamp;
                        const totalDuration = Date.now() - startTimestamp;
                        // Minimum speech duration 500ms, faster pause detection 800ms for quicker responses
                        if (totalDuration > 500 && silenceDuration >= 800) {
                            console.log("VAD: Natural pause detected (" + silenceDuration + "ms). Sending prompt...");
                            clearInterval(vadTimer);
                            vadTimer = null;
                            finishRecordingAndSubmit();
                            return;
                        }
                    }
                }
            }

            // Safety limit: if continuous talking exceeds 32 seconds, submit
            if (Date.now() - startTimestamp > 32000) {
                console.log("VAD: Max recording length reached. Submitting...");
                clearInterval(vadTimer);
                vadTimer = null;
                finishRecordingAndSubmit();
            }
        }, 60);
    }

    function finishRecordingAndSubmit() {
        if (!recorder || recorder.state !== "recording") return;
        if (vadTimer) {
            clearInterval(vadTimer);
            vadTimer = null;
        }
        playVoiceChime("done");
        isProcessingSpeech = true;
        if (jarvisSphere) jarvisSphere.setState("thinking");
        if (voiceModeStatus) voiceModeStatus.textContent = "Thinking...";
        try {
            recorder.stop();
        } catch (e) {
            console.warn("finishRecordingAndSubmit stop error:", e);
        }
    }

    async function startVoiceListening() {
        if (!voiceModeActive) return;
        if (isProcessingSpeech) return;
        if (recorder && recorder.state === "recording") return;

        cleanupVoiceRecording();

        if (!navigator.mediaDevices || !window.MediaRecorder) {
            setVoiceModeStatus("Voice recording is not supported by this browser.", true);
            return;
        }

        try {
            // Reuse active stream if tracks are live for low-latency hands-free looping
            let stream = vadStream;
            const isStreamValid = stream && stream.getTracks().some(t => t.readyState === "live");
            if (!isStreamValid) {
                stream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: true
                    }
                });
                vadStream = stream;
            }

            recordingChunks = [];
            recordingStartTime = Date.now();

            setupVAD(stream);

            if (jarvisSphere) {
                jarvisSphere.setState("listening");
                jarvisSphere.setStream(stream);
            }

            playVoiceChime("start");

            if (voiceModeStatus) {
                voiceModeStatus.textContent = "Listening... Speak naturally";
                voiceModeStatus.hidden = false;
            }

            let mimeType = "audio/webm;codecs=opus";
            if (!MediaRecorder.isTypeSupported(mimeType)) {
                mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
            }

            recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

            recordingTimer = setInterval(() => {
                const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
                const minutes = Math.floor(elapsed / 60);
                const seconds = elapsed % 60;
                const timeStr = `${minutes}:${seconds.toString().padStart(2, '0')}`;
                if (voiceBtn) voiceBtn.title = `Listening… ${timeStr}`;
                if (voiceModeStatus && !hasDetectedSpeech) {
                    voiceModeStatus.textContent = `Listening... ${timeStr}`;
                }
            }, 1000);

            recorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    recordingChunks.push(event.data);
                }
            };

            recorder.onstop = async () => {
                if (recordingTimer) {
                    clearInterval(recordingTimer);
                    recordingTimer = null;
                }
                if (jarvisSphere) {
                    jarvisSphere.stopStream();
                    jarvisSphere.setState("thinking");
                }
                if (voiceModeStatus) {
                    voiceModeStatus.textContent = "Thinking...";
                }
                if (voiceBtn) {
                    voiceBtn.classList.remove("is-recording");
                    voiceBtn.disabled = true;
                }

                try {
                    const blob = new Blob(recordingChunks, { type: recorder ? recorder.mimeType : "audio/webm" });
                    
                    // If user tapped immediately without saying anything or silence
                    if (blob.size < 250 || !hasDetectedSpeech) {
                        console.log("No speech detected. Re-arming listening loop...");
                        isProcessingSpeech = false;
                        if (voiceModeActive) {
                            if (voiceModeStatus) voiceModeStatus.textContent = "Listening... Speak naturally";
                            if (jarvisSphere) jarvisSphere.setState("listening");
                            // Immediate re-listening for faster response
                            setTimeout(() => {
                                if (voiceModeActive && !isProcessingSpeech && (!recorder || recorder.state !== "recording")) {
                                    startVoiceListening();
                                }
                            }, 100);
                        } else {
                            if (jarvisSphere) jarvisSphere.setState("idle");
                        }
                        return;
                    }

                    const formData = new FormData();
                    formData.append("audio", blob, "voice-question.webm");
                    const response = await fetch("/api/ai/transcribe/", { method: "POST", body: formData });
                    const data = await response.json();

                    if (!response.ok || data.error) {
                        throw new Error(data.error || "Transcription failed.");
                    }

                    const transcribedText = (data.text || "").trim();
                    console.log("Transcription result:", transcribedText);

                    if (!transcribedText || transcribedText.length < 2) {
                        console.log("Transcription was blank. Resuming listening...");
                        isProcessingSpeech = false;
                        if (voiceModeActive) {
                            if (voiceModeStatus) voiceModeStatus.textContent = "Didn't catch that. Listening...";
                            // Faster retry for immediate response
                            setTimeout(() => {
                                if (voiceModeActive && !isProcessingSpeech && (!recorder || recorder.state !== "recording")) {
                                    startVoiceListening();
                                }
                            }, 150);
                        }
                        return;
                    }

                    // Keep voice screen clean like ChatGPT voice chat (no text display)
                    const transcriptEl = document.getElementById("brain-voice-transcript");
                    if (transcriptEl) {
                        transcriptEl.hidden = true;
                    }

                    await send(transcribedText, true);

                } catch (error) {
                    console.error("Voice processing error:", error);
                    isProcessingSpeech = false;
                    if (jarvisSphere) jarvisSphere.setState("idle");
                    setVoiceModeStatus(error.message || "Could not transcribe audio.", true);
                    if (voiceModeActive) {
                        // Faster error recovery
                        setTimeout(() => {
                            if (voiceModeActive && !isProcessingSpeech && (!recorder || recorder.state !== "recording")) {
                                startVoiceListening();
                            }
                        }, 500);
                    }
                } finally {
                    if (voiceBtn) voiceBtn.disabled = false;
                    isProcessingSpeech = false;
                }
            };

            recorder.start(250);
            if (voiceBtn) voiceBtn.classList.add("is-recording");
            startVADLoop();

        } catch (error) {
            console.error("Voice listening initialization error:", error);
            if (jarvisSphere) jarvisSphere.setState("idle");
            setVoiceModeStatus("Microphone access was denied or unavailable.", true);
        }
    }

    function enterVoiceMode() {
        voiceModeActive = true;
        isProcessingSpeech = false;
        panel.classList.add("voice-mode-open");
        voiceMode.hidden = false;
        
        if (typeof window !== "undefined" && window.speechSynthesis) {
            try { window.speechSynthesis.resume(); } catch (e) {}
        }
        if (jarvisSphere) {
            jarvisSphere.start();
            jarvisSphere.setState("listening");
        }
        if (voiceModeStatus) {
            voiceModeStatus.textContent = "Connecting microphone...";
            voiceModeStatus.hidden = false;
        }

        // Immediate start for instant response
        setTimeout(() => {
            if (voiceModeActive) {
                startVoiceListening();
            }
        }, 50);
    }

    function exitVoiceMode() {
        currentSpeechSession++;
        stopCurrentSpeech();
        cleanupVoiceRecording();
        if (vadStream) {
            try {
                vadStream.getTracks().forEach(track => track.stop());
            } catch (e) {}
            vadStream = null;
        }
        if (vadSource) {
            try { vadSource.disconnect(); } catch (e) {}
            vadSource = null;
        }
        voiceModeActive = false;
        isProcessingSpeech = false;
        panel.classList.remove("voice-mode-open");
        voiceMode.hidden = true;
        if (voiceModeToggle) voiceModeToggle.classList.remove("is-active");
        const transcriptEl = document.getElementById("brain-voice-transcript");
        if (transcriptEl) transcriptEl.hidden = true;
        if (jarvisSphere) {
            jarvisSphere.setState("idle");
            jarvisSphere.stop();
        }
        setVoiceModeStatus("");
    }

    if (voiceBtn) {
        voiceBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!voiceModeActive) {
                enterVoiceMode();
            } else {
                // If AI is speaking -> Barge-in interruption
                if (currentSpeechAudio || (window.speechSynthesis && window.speechSynthesis.speaking) || (jarvisSphere && jarvisSphere.state === "speaking")) {
                    stopCurrentSpeech();
                    startVoiceListening();
                } else if (recorder && recorder.state === "recording") {
                    finishRecordingAndSubmit();
                } else {
                    startVoiceListening();
                }
            }
        });
    }

    // Voice mode toggle button for ChatGPT-like voice conversation
    if (voiceModeToggle) {
        voiceModeToggle.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!voiceModeActive) {
                enterVoiceMode();
                voiceModeToggle.classList.add("is-active");
            } else {
                exitVoiceMode();
                voiceModeToggle.classList.remove("is-active");
            }
        });
    }

    if (voiceOrbContainer) {
        voiceOrbContainer.addEventListener("click", () => {
            if (!voiceModeActive) {
                enterVoiceMode();
                return;
            }

            // 1. Barge-in / Interrupt AI speech immediately
            if (currentSpeechAudio || (window.speechSynthesis && window.speechSynthesis.speaking) || (jarvisSphere && jarvisSphere.state === "speaking")) {
                console.log("Barge-in: Interrupting AI speech...");
                stopCurrentSpeech();
                setTimeout(() => {
                    startVoiceListening();
                }, 100);
                return;
            }

            // 2. While listening/speaking: tap to submit immediately
            if (recorder && recorder.state === "recording") {
                if (hasDetectedSpeech) {
                    console.log("Tap to send immediately without waiting for silence timer...");
                    finishRecordingAndSubmit();
                } else {
                    console.log("Tap to reset listening...");
                    cleanupVoiceRecording();
                    startVoiceListening();
                }
                return;
            }

            // 3. If currently processing / thinking, ignore tap
            if (isProcessingSpeech) {
                return;
            }

            // 4. Otherwise start listening
            startVoiceListening();
        });
        
        voiceOrbContainer.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                voiceOrbContainer.click();
            }
        });
    }

    const voiceModeHistoryBtn = document.getElementById("brain-voice-history-btn");
    if (voiceModeHistoryBtn) {
        voiceModeHistoryBtn.addEventListener("click", () => {
            exitVoiceMode();
            setTab("chat");
        });
    }

    if (voiceModeClose) {
        voiceModeClose.addEventListener("click", () => {
            exitVoiceMode();
            setTab("chat");
        });
    }

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && open) setOpen(false);
    });

    // Initial load of account chat history
    loadChatHistory();
})();
