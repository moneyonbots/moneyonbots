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

    function validateChartPayload(payload) {
        if (!payload.symbol) {
            return { valid: false, error: "No symbol selected" };
        }
        if (!payload.candles || payload.candles.length === 0) {
            return { valid: false, error: "No candle data available" };
        }
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
                    }
                } else {
                    el.hidden = true;
                    el.style.display = 'none';
                }
            }
        });
        if (name === "chat" && input) input.focus();
    }

    function updateSymbolLabel() {
        const symbol = currentSymbol();
        let label = symbol || "—";
        if (window.AVAILABLE_MARKETS && symbol) {
            const market = window.AVAILABLE_MARKETS.find((m) => m.symbol === symbol);
            if (market) label = market.name;
        }
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
            const signal = (data.signals || [])[0];
            marketName.textContent = (signal && signal.market_name) || marketLabel;
            paintPrice();

            if (!signal) {
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
            console.warn("AI insight refresh failed", e);
        }
    }

    window.addEventListener("chart-symbol-changed", (event) => {
        window.currentChartSymbol = event.detail.symbol;
        updateSymbolLabel();
        if (open) refreshInsight();
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

    // Voice cache & JARVIS speech synthesis engine
    let availableVoices = [];
    function refreshVoices() {
        if (typeof window !== "undefined" && window.speechSynthesis) {
            availableVoices = window.speechSynthesis.getVoices() || [];
        }
    }
    if (typeof window !== "undefined" && window.speechSynthesis) {
        refreshVoices();
        window.speechSynthesis.onvoiceschanged = refreshVoices;
    }

    function getJarvisVoice() {
        const voices = (availableVoices && availableVoices.length) 
            ? availableVoices 
            : (window.speechSynthesis ? window.speechSynthesis.getVoices() : []);
        if (!voices || voices.length === 0) return null;

        function scoreVoice(v) {
            const name = (v.name || "").toLowerCase();
            const lang = (v.lang || "").toLowerCase().replace("_", "-");
            let score = 0;

            const isUK = lang.startsWith("en-gb") || name.includes("united kingdom") || name.includes("uk") || name.includes("british") || name.includes("english (united kingdom)");
            const isEnglish = lang.startsWith("en");
            if (!isEnglish) return -200;

            const isNeural = name.includes("natural") || name.includes("neural") || name.includes("online") || name.includes("premium") || name.includes("enhanced");
            const ukMaleNames = ["ryan", "george", "daniel", "oliver", "arthur", "brian", "guy", "charles", "alfred", "edward", "james", "william", "uk english male"];
            const usMaleNames = ["guy", "christopher", "davis", "eric", "roger", "andrew", "brian", "david", "mark", "alex", "fred", "us english male"];
            const femaleNames = ["zira", "susan", "hazel", "jenny", "aria", "sonia", "libby", "mia", "victoria", "karen", "samantha", "stephanie", "catherine", "heera", "female"];
            const isFemale = femaleNames.some(f => name.includes(f));

            if (isFemale) score -= 60;

            if (isUK && ukMaleNames.some(n => name.includes(n)) && isNeural) {
                score += 200;
            } else if (isUK && ukMaleNames.some(n => name.includes(n))) {
                score += 150;
            } else if (isUK && isNeural && !isFemale) {
                score += 120;
            } else if (isUK && !isFemale) {
                score += 90;
            } else if (usMaleNames.some(n => name.includes(n)) && isNeural) {
                score += 80;
            } else if (usMaleNames.some(n => name.includes(n))) {
                score += 60;
            } else if (isNeural && !isFemale) {
                score += 50;
            } else if (isUK) {
                score += 40;
            } else if (!isFemale) {
                score += 20;
            }

            if (name.includes("google uk english male")) score += 40;
            if (name.includes("microsoft ryan")) score += 40;
            if (name.includes("microsoft george")) score += 35;
            if (name.includes("daniel")) score += 30;

            return score;
        }

        let bestVoice = voices[0];
        let bestScore = -999;
        for (const v of voices) {
            const s = scoreVoice(v);
            if (s > bestScore) {
                bestScore = s;
                bestVoice = v;
            }
        }
        return bestVoice;
    }

    function cleanTextForJarvisSpeech(rawText) {
        if (!rawText) return "";
        let text = String(rawText);

        // Strip action blocks and markdown code blocks
        text = text.replace(/```actions[\s\S]*?```/gi, "");
        text = text.replace(/```[\s\S]*?```/g, "");
        text = text.replace(/`([^`]+)`/g, "$1");

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
            const size = rect.width || 220;
            this.canvas.width = size * dpr;
            this.canvas.height = size * dpr;
            this.width = size;
            this.height = size;
        }

        initParticles() {
            this.particles = [];
            for (let i = 0; i < 30; i++) {
                const angle = Math.random() * Math.PI * 2;
                const dist = 75 + Math.random() * 35;
                this.particles.push({
                    angle: angle,
                    dist: dist,
                    speed: 0.015 + Math.random() * 0.02,
                    size: 1.2 + Math.random() * 2.2,
                    z: (Math.random() - 0.5) * 60,
                    opacity: 0.35 + Math.random() * 0.65,
                    hue: Math.random() > 0.4 ? 185 : (Math.random() > 0.5 ? 260 : 45)
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
                this.analyser = this.audioCtx.createAnalyser();
                this.analyser.fftSize = 256;
                this.analyser.smoothingTimeConstant = 0.75;
                this.dataArray = new Uint8Array(this.analyser.frequencyBinCount);
                this.sourceNode = this.audioCtx.createMediaStreamSource(stream);
                this.sourceNode.connect(this.analyser);
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
            if (this.analyser && this.dataArray) {
                this.analyser.getByteFrequencyData(this.dataArray);
                let sum = 0;
                const count = Math.min(this.dataArray.length, 32);
                for (let i = 0; i < count; i++) {
                    sum += this.dataArray[i];
                }
                const avg = sum / (count * 255);
                this.targetAudioLevel = avg;
            } else {
                this.targetAudioLevel = 0;
            }
            this.audioLevel += (this.targetAudioLevel - this.audioLevel) * 0.28;

            let speed = 0.025;
            if (this.state === "thinking") speed = 0.075;
            else if (this.state === "speaking") speed = 0.045;
            else if (this.state === "listening") speed = 0.040;
            this.t += speed;

            const baseRadius = (w * 0.32) * dpr;

            // 1. Outer Volumetric Corona Bloom
            const coronaGrad = ctx.createRadialGradient(cx, cy, baseRadius * 0.3, cx, cy, baseRadius * 1.55);
            if (this.state === "listening") {
                coronaGrad.addColorStop(0, "rgba(16, 185, 129, 0.55)");
                coronaGrad.addColorStop(0.5, "rgba(52, 211, 153, 0.25)");
                coronaGrad.addColorStop(1, "rgba(16, 185, 129, 0)");
            } else if (this.state === "thinking") {
                coronaGrad.addColorStop(0, "rgba(59, 130, 246, 0.5)");
                coronaGrad.addColorStop(0.5, "rgba(99, 102, 241, 0.25)");
                coronaGrad.addColorStop(1, "rgba(59, 130, 246, 0)");
            } else if (this.state === "speaking") {
                coronaGrad.addColorStop(0, "rgba(0, 242, 255, 0.65)");
                coronaGrad.addColorStop(0.45, "rgba(0, 119, 255, 0.35)");
                coronaGrad.addColorStop(1, "rgba(0, 242, 255, 0)");
            } else {
                coronaGrad.addColorStop(0, "rgba(0, 242, 255, 0.4)");
                coronaGrad.addColorStop(0.5, "rgba(0, 119, 255, 0.18)");
                coronaGrad.addColorStop(1, "rgba(0, 242, 255, 0)");
            }
            ctx.fillStyle = coronaGrad;
            ctx.beginPath();
            ctx.arc(cx, cy, baseRadius * 1.55, 0, Math.PI * 2);
            ctx.fill();

            // 2. Background Orbital Particles (z < 0)
            this.drawParticles(ctx, cx, cy, dpr, true);

            // 3. Swirling Internal Plasma Vortices (JARVIS Core)
            ctx.save();
            ctx.globalCompositeOperation = "screen";
            for (let p = 0; p < 3; p++) {
                const rot = this.t * (p % 2 === 0 ? 1 : -1.2) + (p * Math.PI / 1.5);
                const scaleX = 0.85 + Math.sin(this.t * 2 + p) * 0.15;
                const scaleY = 0.7 + Math.cos(this.t * 1.5 + p) * 0.15;
                ctx.save();
                ctx.translate(cx, cy);
                ctx.rotate(rot);
                ctx.scale(scaleX, scaleY);
                const plasmaGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, baseRadius * 0.9);
                if (this.state === "listening") {
                    plasmaGrad.addColorStop(0, "rgba(255, 255, 255, 0.95)");
                    plasmaGrad.addColorStop(0.35, "rgba(16, 185, 129, 0.85)");
                    plasmaGrad.addColorStop(0.7, "rgba(5, 150, 105, 0.45)");
                    plasmaGrad.addColorStop(1, "rgba(16, 185, 129, 0)");
                } else if (this.state === "thinking") {
                    plasmaGrad.addColorStop(0, "rgba(255, 255, 255, 0.9)");
                    plasmaGrad.addColorStop(0.3, "rgba(59, 130, 246, 0.8)");
                    plasmaGrad.addColorStop(0.7, "rgba(99, 102, 241, 0.4)");
                    plasmaGrad.addColorStop(1, "rgba(59, 130, 246, 0)");
                } else if (this.state === "speaking") {
                    plasmaGrad.addColorStop(0, "rgba(255, 255, 255, 0.95)");
                    plasmaGrad.addColorStop(0.25, "rgba(0, 242, 255, 0.9)");
                    plasmaGrad.addColorStop(0.65, "rgba(0, 119, 255, 0.55)");
                    plasmaGrad.addColorStop(1, "rgba(0, 242, 255, 0)");
                } else {
                    plasmaGrad.addColorStop(0, "rgba(255, 255, 255, 0.85)");
                    plasmaGrad.addColorStop(0.3, "rgba(0, 242, 255, 0.7)");
                    plasmaGrad.addColorStop(0.65, "rgba(0, 119, 255, 0.45)");
                    plasmaGrad.addColorStop(1, "rgba(0, 242, 255, 0)");
                }
                ctx.fillStyle = plasmaGrad;
                ctx.beginPath();
                ctx.arc(0, 0, baseRadius * 0.9, 0, Math.PI * 2);
                ctx.fill();
                ctx.restore();
            }
            ctx.restore();

            // 4. Main 3D Liquid Morphing Blob
            const numPoints = 120;
            const points = [];
            const morphAmp = (this.state === "listening" ? (6 + this.audioLevel * 38) :
                              this.state === "thinking" ? 14 :
                              this.state === "speaking" ? (9 + Math.sin(this.t * 7) * 7) : 5) * dpr;

            for (let i = 0; i < numPoints; i++) {
                const angle = (i / numPoints) * Math.PI * 2;
                const w1 = Math.sin(angle * 2 + this.t * 2.2);
                const w2 = Math.cos(angle * 3 - this.t * 1.8);
                const w3 = Math.sin(angle * 5 + this.t * 3.1) * 0.5;
                const w4 = Math.cos(angle * 7 - this.t * 4.0) * 0.25;
                const distortion = (w1 + w2 + w3 + w4) * morphAmp;
                const r = baseRadius + distortion;
                points.push({
                    x: cx + Math.cos(angle) * r,
                    y: cy + Math.sin(angle) * r
                });
            }

            // Render Blob Path with smooth curves
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

            // Membrane gradient fill
            const blobGrad = ctx.createLinearGradient(
                cx + Math.cos(this.t) * baseRadius,
                cy + Math.sin(this.t) * baseRadius,
                cx - Math.cos(this.t) * baseRadius,
                cy - Math.sin(this.t) * baseRadius
            );
            if (this.state === "listening") {
                blobGrad.addColorStop(0, "rgba(52, 211, 153, 0.94)");
                blobGrad.addColorStop(0.45, "rgba(16, 185, 129, 0.88)");
                blobGrad.addColorStop(1, "rgba(5, 150, 105, 0.92)");
            } else if (this.state === "thinking") {
                blobGrad.addColorStop(0, "rgba(96, 165, 250, 0.9)");
                blobGrad.addColorStop(0.5, "rgba(59, 130, 246, 0.85)");
                blobGrad.addColorStop(1, "rgba(37, 99, 235, 0.9)");
            } else if (this.state === "speaking") {
                blobGrad.addColorStop(0, "rgba(103, 232, 249, 0.95)");
                blobGrad.addColorStop(0.45, "rgba(0, 242, 255, 0.9)");
                blobGrad.addColorStop(0.85, "rgba(0, 119, 255, 0.85)");
                blobGrad.addColorStop(1, "rgba(29, 78, 216, 0.9)");
            } else {
                blobGrad.addColorStop(0, "rgba(34, 211, 238, 0.9)");
                blobGrad.addColorStop(0.5, "rgba(0, 150, 255, 0.85)");
                blobGrad.addColorStop(1, "rgba(30, 64, 175, 0.88)");
            }
            ctx.fillStyle = blobGrad;
            ctx.fill();

            // 5. Inner Glass Reflection & Highlights
            ctx.save();
            ctx.clip();

            // Specular highlight bubble
            const specX = cx - baseRadius * 0.32;
            const specY = cy - baseRadius * 0.32;
            const specGrad = ctx.createRadialGradient(specX, specY, 0, specX, specY, baseRadius * 0.7);
            specGrad.addColorStop(0, "rgba(255, 255, 255, 0.85)");
            specGrad.addColorStop(0.25, "rgba(255, 255, 255, 0.35)");
            specGrad.addColorStop(0.7, "rgba(255, 255, 255, 0)");
            ctx.fillStyle = specGrad;
            ctx.beginPath();
            ctx.arc(specX, specY, baseRadius * 0.7, 0, Math.PI * 2);
            ctx.fill();

            // Inner shadow rim
            const innerShadowGrad = ctx.createRadialGradient(cx, cy, baseRadius * 0.4, cx, cy, baseRadius * 1.05);
            innerShadowGrad.addColorStop(0, "rgba(0, 0, 0, 0)");
            innerShadowGrad.addColorStop(0.75, "rgba(0, 0, 0, 0.15)");
            innerShadowGrad.addColorStop(1, "rgba(0, 0, 0, 0.65)");
            ctx.fillStyle = innerShadowGrad;
            ctx.beginPath();
            ctx.arc(cx, cy, baseRadius * 1.1, 0, Math.PI * 2);
            ctx.fill();

            ctx.restore();

            // Glowing perimeter rim stroke
            ctx.lineWidth = 2.5 * dpr;
            ctx.strokeStyle = (this.state === "listening") ? "rgba(209, 250, 229, 0.9)" :
                              (this.state === "speaking") ? "rgba(217, 249, 255, 0.95)" :
                              (this.state === "thinking") ? "rgba(219, 234, 254, 0.85)" : "rgba(255, 255, 255, 0.7)";
            ctx.stroke();
            ctx.restore();

            // 6. Foreground Orbital Particles (z >= 0)
            this.drawParticles(ctx, cx, cy, dpr, false);
        }

        drawParticles(ctx, cx, cy, dpr, isBack) {
            ctx.save();
            const baseHue = (this.state === "listening") ? 155 :
                            (this.state === "thinking") ? 225 :
                            (this.state === "speaking") ? 190 : 195;
            for (const p of this.particles) {
                p.angle += p.speed * (this.state === "thinking" ? 3.0 : (this.state === "speaking" ? 1.8 : 1.0));
                const x3d = Math.cos(p.angle) * p.dist * dpr;
                const y3d = Math.sin(p.angle) * p.dist * 0.38 * dpr;
                const z3d = Math.sin(p.angle) * p.dist * dpr;

                const isCurrentBack = z3d < 0;
                if (isCurrentBack !== isBack) continue;

                const alpha = isBack ? p.opacity * 0.35 : p.opacity;
                const size = (isBack ? p.size * 0.75 : p.size * 1.25) * dpr;

                const px = cx + x3d;
                const py = cy + y3d + (Math.sin(this.t + p.angle) * 6 * dpr);

                ctx.beginPath();
                ctx.arc(px, py, size, 0, Math.PI * 2);
                ctx.fillStyle = `hsla(${baseHue}, 90%, 65%, ${alpha})`;
                ctx.shadowColor = `hsla(${baseHue}, 100%, 70%, 1)`;
                ctx.shadowBlur = (isBack ? 4 : 10) * dpr;
                ctx.fill();
            }
            ctx.restore();
        }
    }

    const jarvisSphere = voiceCanvas ? new JarvisSphere(voiceCanvas, voiceOrbContainer) : null;

    let currentSpeechSession = 0;

    function speakReply(text) {
        if (!text || !window.speechSynthesis || !window.SpeechSynthesisUtterance) {
            return Promise.resolve();
        }

        const sessionId = ++currentSpeechSession;
        const cleaned = cleanTextForJarvisSpeech(text);
        if (!cleaned) return Promise.resolve();

        const rawChunks = cleaned.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [cleaned];
        const chunks = rawChunks.map(c => c.trim()).filter(Boolean);
        if (!chunks.length) return Promise.resolve();

        if (jarvisSphere) jarvisSphere.setState("speaking");

        return new Promise((resolve) => {
            // Cancel previous speech safely
            try {
                window.speechSynthesis.cancel();
            } catch (e) {}

            let chunkIndex = 0;
            let keepAliveTimer = null;
            let finished = false;

            function finish() {
                if (finished) return;
                finished = true;
                if (keepAliveTimer) clearInterval(keepAliveTimer);
                if (jarvisSphere && jarvisSphere.state === "speaking") {
                    jarvisSphere.setState("idle");
                }
                resolve();
            }

            keepAliveTimer = setInterval(() => {
                if (sessionId !== currentSpeechSession) {
                    finish();
                    return;
                }
                if (window.speechSynthesis && window.speechSynthesis.speaking) {
                    window.speechSynthesis.pause();
                    window.speechSynthesis.resume();
                }
            }, 5000);

            function speakChunk(chunkText, isRetry = false) {
                if (sessionId !== currentSpeechSession) {
                    finish();
                    return;
                }

                const utterance = new SpeechSynthesisUtterance(chunkText);
                utterance.rate = 1.0;
                utterance.pitch = 0.95;
                utterance.volume = 1.0;

                const jarvisVoice = getJarvisVoice();
                if (!isRetry && jarvisVoice) {
                    utterance.voice = jarvisVoice;
                }

                utterance.onstart = () => {
                    if (jarvisSphere) jarvisSphere.setState("speaking");
                };

                utterance.onend = () => {
                    if (sessionId === currentSpeechSession) {
                        if (chunkIndex < chunks.length) {
                            speakChunk(chunks[chunkIndex++]);
                        } else {
                            finish();
                        }
                    } else {
                        finish();
                    }
                };

                utterance.onerror = (evt) => {
                    console.warn("JARVIS speech utterance error", evt);
                    // If failed with custom voice, retry once with default voice
                    if (!isRetry && jarvisVoice) {
                        speakChunk(chunkText, true);
                    } else {
                        if (chunkIndex < chunks.length) {
                            speakChunk(chunks[chunkIndex++]);
                        } else {
                            finish();
                        }
                    }
                };

                try {
                    if (window.speechSynthesis.paused) {
                        window.speechSynthesis.resume();
                    }
                    window.speechSynthesis.speak(utterance);
                    if (window.speechSynthesis.paused) {
                        window.speechSynthesis.resume();
                    }
                } catch (e) {
                    console.error("SpeechSynthesis speak error:", e);
                    finish();
                }
            }

            // Small delay so cancel state settles cleanly in Chromium
            setTimeout(() => {
                if (sessionId !== currentSpeechSession) return;
                speakChunk(chunks[chunkIndex++]);
            }, 60);
        });
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
                speakBtn.title = "Speak with JARVIS voice";
                speakBtn.setAttribute("aria-label", "Speak with JARVIS voice");
                speakBtn.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>';
                speakBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    if (window.speechSynthesis && window.speechSynthesis.speaking) {
                        window.speechSynthesis.cancel();
                        if (jarvisSphere) jarvisSphere.setState("idle");
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
        
        const payload = chartPayload();
        const validation = validateChartPayload(payload);
        
        if (!validation.valid) {
            addMessage("ai", "⚠ " + validation.error + " Please select a market on the chart first.");
            return;
        }
        
        addMessage("user", message);
        history.push({ role: "user", content: message });
        const thinking = addMessage("ai", "thinking");
        payload.message = message;
        payload.history = history.slice(0, -1);

        if (voiceReply && jarvisSphere) {
            jarvisSphere.setState("thinking");
        }

        try {
            const res = await fetch("/api/ai/chat/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            
            if (!res.ok) {
                throw new Error(`HTTP error! status: ${res.status}`);
            }
            
            const data = await res.json();
            thinking.remove();
            if (data.error) {
                addMessage("ai", "⚠ " + data.error);
                if (voiceReply && jarvisSphere) jarvisSphere.setState("idle");
            } else {
                addMessage("ai", data.reply);
                history.push({ role: "assistant", content: data.reply });
                window.aiChartActions.applyActions(data.actions || []);
                if (voiceReply) {
                    await speakReply(data.reply);
                }
            }
        } catch (e) {
            console.error("Chat error:", e);
            thinking.remove();
            addMessage("ai", "⚠ Couldn't reach the AI backend — check the server is running and your internet connection.");
            if (voiceReply) exitVoiceMode();
        }
    }

    form.addEventListener("submit", (e) => {
        e.preventDefault();
        const value = input.value.trim();
        if (!value) return;
        input.value = "";
        send(value);
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

    function enterVoiceMode() {
        voiceModeActive = true;
        panel.classList.add("voice-mode-open");
        voiceMode.hidden = false;
        if (jarvisSphere) {
            jarvisSphere.start();
            jarvisSphere.setState("idle");
        }
        setVoiceModeStatus("");
    }

    function exitVoiceMode() {
        currentSpeechSession++;
        voiceModeActive = false;
        panel.classList.remove("voice-mode-open");
        voiceMode.hidden = true;
        if (jarvisSphere) {
            jarvisSphere.setState("idle");
            jarvisSphere.stop();
        }
        if (window.speechSynthesis) window.speechSynthesis.cancel();
        if (recorder && recorder.state === "recording") recorder.stop();
        setVoiceModeStatus("");
    }

    async function startRecording() {
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            setVoiceModeStatus("Voice recording is not supported by this browser.", true);
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            recordingChunks = [];
            recordingStartTime = Date.now();
            recorder = new MediaRecorder(stream);
            
            if (jarvisSphere) {
                jarvisSphere.setState("listening");
                jarvisSphere.setStream(stream);
            }

            // Recording timer for button tooltip
            recordingTimer = setInterval(() => {
                const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
                const minutes = Math.floor(elapsed / 60);
                const seconds = elapsed % 60;
                if (voiceBtn) voiceBtn.title = `Listening… ${minutes}:${seconds.toString().padStart(2, '0')}`;
            }, 1000);
            
            recorder.ondataavailable = (event) => {
                if (event.data.size) recordingChunks.push(event.data);
            };
            recorder.onstop = async () => {
                clearInterval(recordingTimer);
                stream.getTracks().forEach((track) => track.stop());
                if (jarvisSphere) {
                    jarvisSphere.stopStream();
                    jarvisSphere.setState("thinking");
                }
                voiceBtn.classList.remove("is-recording");
                voiceBtn.disabled = true;
                try {
                    const blob = new Blob(recordingChunks, { type: recorder.mimeType || "audio/webm" });
                    const formData = new FormData();
                    formData.append("audio", blob, "voice-question.webm");
                    const response = await fetch("/api/ai/transcribe/", { method: "POST", body: formData });
                    const data = await response.json();
                    if (!response.ok || data.error) throw new Error(data.error || "Transcription failed.");
                    await send(data.text, true);
                } catch (error) {
                    if (jarvisSphere) jarvisSphere.setState("idle");
                    setVoiceModeStatus(error.message || "Could not transcribe the recording.", true);
                } finally {
                    voiceBtn.disabled = false;
                }
            };
            recorder.start();
            voiceBtn.classList.add("is-recording");
        } catch (error) {
            if (jarvisSphere) jarvisSphere.setState("idle");
            setVoiceModeStatus("Microphone access was denied or unavailable.", true);
        }
    }

    if (voiceBtn) voiceBtn.addEventListener("click", () => {
        enterVoiceMode();
        if (!recorder || recorder.state !== "recording") startRecording();
    });

    if (voiceOrbContainer) {
        voiceOrbContainer.addEventListener("click", () => {
            if (recorder && recorder.state === "recording") {
                recorder.stop();
            } else {
                if (window.speechSynthesis && window.speechSynthesis.speaking) {
                    window.speechSynthesis.cancel();
                }
                startRecording();
            }
        });
        voiceOrbContainer.addEventListener("keydown", (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                voiceOrbContainer.click();
            }
        });
    }

    if (voiceModeClose) voiceModeClose.addEventListener("click", exitVoiceMode);

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && open) setOpen(false);
    });
})();
