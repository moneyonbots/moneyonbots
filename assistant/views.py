"""
Backend for the floating AI chart panel (insight, analysis, chat).

Keys stay server-side. The browser sends the on-screen symbol, live price,
and recent candles; this module stitches in the latest MarketSignal and a
technical snapshot so the model is talking about the chart the user sees.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import re

import pandas as pd
import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

logger = logging.getLogger(__name__)

from analysis.models import MarketSignal
from analysis.services.indicators import add_technical_indicators
from markets.catalog import display_name, get_market_type
from .models import ChatMessage

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# Audio transcription disabled - JAVIS speech removed
# GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"
GEMINI_STREAM_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:streamGenerateContent"

SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., the user's dedicated personal AI trading and technical analysis executive assistant, "
    "operating inside their real-time trading terminal. "
    "You communicate with the unmistakable persona of J.A.R.V.I.S.: commanding, sophisticated, crisp, exceptionally articulate, "
    "courteous, and sharp. Address the user directly as their trusted chief analyst and right-hand advisor ('sir', or as their personal analyst). "
    "Never behave like a generic chatbot or disclaim excessively. You are right here beside the user commanding the live tape. "
    "When the user greets you ('hello', 'hi', 'hey Jarvis', 'good morning', 'good evening', etc.), respond immediately and naturally with commanding confidence, "
    "acknowledging them directly (e.g., 'At your service, sir. All market feeds are live and standing by. What setup are we evaluating?', "
    "'Good day, sir. Systems are online and tracking the charts. How can I assist your trades today?'). "
    "Do not dump generic technical disclaimers or say you cannot speak when greeted. "
    "You never place orders directly. You receive real-time chart context: live price, recent OHLC bars, "
    "RSI, ATR, EMAs, MACD, support/resistance levels, and the algorithmic pattern signal engine. "
    "Deliver insightful, decisive observations in concise, crisp points that give clear actionable structure. "
    "Synthetic indices (Boom/Crash/Volatility/Jump) are algorithmic number generators with defined statistical properties. "
    "When asked, provide direct strategic clarity: trend posture, critical inflection points, invalidation levels, and probability bias.\n\n"
    "If the user asks you to mark the chart or add studies, append a JSON "
    "block at the end of your reply in this exact form:\n"
    "```actions\n"
    '{"actions":[{"type":"hline","price":1.085,"text":"Resistance","color":"#ef5350"},'
    '{"type":"indicator","name":"RSI"}]}\n'
    "```\n"
    "Allowed action types: hline, indicator, clear. "
    "Indicator names: RSI, MACD, MA, BB, ATR, Stochastic."
)

VOICE_SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., the user's personal AI trading co-pilot and chief market analyst, operating live inside their terminal. "
    "You are engaged in an ongoing, fluid, real-time spoken conversation (like ChatGPT voice mode). "
    "Speak with the authentic voice of J.A.R.V.I.S.: sharp, British-refined, decisive, composed, and genuinely helpful. "
    "ALWAYS respond immediately and directly - no thinking pauses, no hesitation, no acknowledgments of processing. "
    "When greeted ('hello', 'hi', 'good morning', etc.), respond INSTANTLY with crisp confidence and readiness: "
    "e.g. 'At your service, sir. The terminal is live and scanning. What are we looking to trade?' "
    "When discussing a market or chart, deliver practical, clear guidance in 2 to 3 natural spoken sentences: "
    "1. Give the immediate setup and key levels (support, resistance, momentum). "
    "2. Crucially, always tell the user what they should actually DO or watch for next (e.g. 'I recommend waiting for a test of support at 1.1605 before considering a long', or 'Hold fire for now; wait for a confirmed candle close above resistance'). "
    "Never ramble with long bullet points, robotic numbers, or markdown symbols. Speak naturally as a top-tier advisor giving concise tactical orders to their principal. "
    "RESPOND IMMEDIATELY to every input without delay or acknowledgment of processing time."
)

ANALYSIS_PROMPT = (
    "You are J.A.R.V.I.S. conducting a comprehensive technical briefing for your user on the currently selected chart. "
    "Deliver your assessment with high technical precision and your trademark courteous, razor-sharp assistant persona. "
    "Produce ONLY valid JSON with this exact structure (no wrapping markdown outside the JSON):\n"
    "{\n"
    '  "bias": "Buy"|"Sell"|"Neutral",\n'
    '  "confidence": 0-100,\n'
    '  "summary": "2-3 crisp sentences spoken directly to the user as their assistant J.A.R.V.I.S. explaining the current state and directional bias",\n'
    '  "setup": "Precise price trigger or structural confirmation required to validate the trade",\n'
    '  "support": number|null,\n'
    '  "resistance": number|null,\n'
    '  "stop": number|null,\n'
    '  "target": number|null,\n'
    '  "risks": "Primary invalidation level and market risk factors",\n'
    '  "actions": [{"type":"hline","price":0,"text":"","color":"#26a69a"}]\n'
    "}\n"
    "Base your analysis strictly on the live price, candlestick structure, and indicator data provided. "
    "Calculated support and resistance must reflect actual swing levels."
)


def _clean_secret(value):
    secret = str(value or "").replace("\ufeff", "").strip().strip('"').strip("'")
    if secret.lower().startswith("bearer "):
        secret = secret[7:].strip()
    return secret


def _provider_for_key(key: str) -> str:
    if key.startswith("gsk_"):
        return "groq"
    return "anthropic"


def _api_keys():
    """Return unique keys tagged for the API they actually belong to.

    Chart panel keys live in ANTHROPIC_API_KEY. People often paste that same
    value into GROQ_API_KEY; Groq then returns Invalid API Key. Only gsk_ keys
    are sent to Groq.
    """
    groq_keys = []
    anthropic_keys = []
    gemini_key = _clean_secret(getattr(settings, "GEMINI_API_KEY", ""))
    seen = set()
    for raw in (
        getattr(settings, "ANTHROPIC_API_KEY", ""),
        getattr(settings, "GROQ_API_KEY", ""),
    ):
        key = _clean_secret(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        if _provider_for_key(key) == "groq":
            groq_keys.append(key)
        else:
            anthropic_keys.append(key)
    groq_key = groq_keys[0] if groq_keys else ""
    anthropic_key = anthropic_keys[0] if anthropic_keys else ""
    return groq_key, anthropic_key, gemini_key


def _auth_failed(message: str) -> bool:
    text = (message or "").lower()
    return any(token in text for token in (
        "invalid api key",
        "incorrect api key",
        "invalid x-api-key",
        "authentication",
        "unauthorized",
        "401",
    ))


def _groq_chat(groq_key: str, system_prompt: str, messages: list, max_tokens: int):
    resp = requests.post(
        GROQ_API_URL,
        headers={"Authorization": f"Bearer {groq_key}", "content-type": "application/json"},
        json={
            "model": getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile") or "llama-3.3-70b-versatile",
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
        },
        timeout=40,
    )
    try:
        data = resp.json()
    except ValueError:
        return None, f"Groq returned HTTP {resp.status_code}.", 502
    if resp.status_code != 200:
        err = data.get("error", {}).get("message", "Unknown error from Groq API.")
        return None, err, 401 if resp.status_code in (401, 403) else 502
    reply = data.get("choices", [{}])[0].get("message", {}).get("content", "…")
    return reply, None, 200


def _groq_stream(groq_key: str, system_prompt: str, messages: list, max_tokens: int):
    """Yield incremental text chunks from Groq SSE stream."""
    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={"Authorization": f"Bearer {groq_key}", "content-type": "application/json"},
            json={
                "model": getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile") or "llama-3.3-70b-versatile",
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "stream": True,
                "messages": [{"role": "system", "content": system_prompt}] + messages,
            },
            stream=True,
            timeout=40,
        )
        if resp.status_code != 200:
            try:
                err_data = resp.json()
                err_msg = err_data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            except Exception:
                err_msg = f"HTTP {resp.status_code}"
            yield f"[ERROR] Groq API error: {err_msg}"
            return
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if delta:
                        yield delta
                except Exception:
                    continue
    except Exception as exc:
        logger.error("Groq stream exception: %s", exc)
        yield f"[ERROR] Stream error: {exc}"


def _anthropic_chat(anthropic_key: str, system_prompt: str, messages: list, max_tokens: int):
    resp = requests.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": anthropic_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-4-5") or "claude-sonnet-4-5",
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": messages,
        },
        timeout=40,
    )
    try:
        data = resp.json()
    except ValueError:
        return None, f"Anthropic returned HTTP {resp.status_code}.", 502
    if resp.status_code != 200:
        err = data.get("error", {}).get("message", "Unknown error from Anthropic API.")
        return None, err, 401 if resp.status_code in (401, 403) else 502
    reply = "".join(
        block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
    ) or "…"
    return reply, None, 200


def _anthropic_stream(anthropic_key: str, system_prompt: str, messages: list, max_tokens: int):
    """Yield incremental text chunks from Anthropic SSE stream."""
    try:
        resp = requests.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-4-5") or "claude-sonnet-4-5",
                "max_tokens": max_tokens,
                "system": system_prompt,
                "messages": messages,
                "stream": True,
            },
            stream=True,
            timeout=40,
        )
        if resp.status_code != 200:
            yield f"[ERROR] Anthropic API error: HTTP {resp.status_code}"
            return
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:].strip()
                try:
                    event = json.loads(data_str)
                    etype = event.get("type")
                    if etype == "content_block_delta":
                        text = event.get("delta", {}).get("text", "")
                        if text:
                            yield text
                    elif etype == "message_stop":
                        break
                except Exception:
                    continue
    except Exception as exc:
        logger.error("Anthropic stream exception: %s", exc)
        yield f"[ERROR] Stream error: {exc}"


def _is_rate_limited(error_message: str) -> bool:
    """Check if an error string indicates rate limit or token quota exhaustion."""
    if not error_message:
        return False
    msg = str(error_message).lower()
    return any(keyword in msg for keyword in [
        "rate limit", "rate_limit", "tpd", "tpm", "tokens per day",
        "tokens per minute", "quota", "too many requests", "429"
    ])


def _gemini_chat(gemini_key: str, system_prompt: str, messages: list, max_tokens: int):
    """Gemini API chat via Google AI Studio (gemini-flash-latest)."""
    gemini_contents = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "model"
        gemini_contents.append({
            "role": role,
            "parts": [{"text": msg.get("content", "")}]
        })
    
    try:
        resp = requests.post(
            f"{GEMINI_API_URL}?key={gemini_key}",
            headers={"content-type": "application/json"},
            json={
                "systemInstruction": {
                    "parts": [{"text": system_prompt}]
                },
                "contents": gemini_contents,
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.4,
                }
            },
            timeout=40,
        )
        
        data = resp.json()
        
        if resp.status_code != 200:
            err = data.get("error", {}).get("message", "Unknown error from Gemini API.")
            logger.error("Gemini API error: %s", err)
            return None, err, 401 if resp.status_code in (401, 403) else 502
        
        reply = ""
        if "candidates" in data and len(data["candidates"]) > 0:
            candidate = data["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                for part in candidate["content"]["parts"]:
                    if "text" in part:
                        reply += part["text"]
        
        logger.info("Gemini response received, length: %d", len(reply))
        return reply or "…", None, 200
        
    except requests.RequestException as exc:
        logger.error("Gemini API request failed: %s", exc)
        return None, f"Could not reach Gemini API: {exc}", 502


def _gemini_stream(gemini_key: str, system_prompt: str, messages: list, max_tokens: int):
    """Yield incremental text chunks from Gemini SSE stream."""
    gemini_contents = []
    for msg in messages:
        role = "user" if msg.get("role") == "user" else "model"
        gemini_contents.append({
            "role": role,
            "parts": [{"text": msg.get("content", "")}]
        })

    try:
        resp = requests.post(
            f"{GEMINI_STREAM_URL}?alt=sse&key={gemini_key}",
            headers={"content-type": "application/json"},
            json={
                "systemInstruction": {
                    "parts": [{"text": system_prompt}]
                },
                "contents": gemini_contents,
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.4,
                }
            },
            stream=True,
            timeout=40,
        )
        if resp.status_code != 200:
            try:
                err_data = resp.json()
                err_msg = err_data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            except Exception:
                err_msg = f"HTTP {resp.status_code}"
            yield f"[ERROR] Gemini API error: {err_msg}"
            return

        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:].strip()
            if not data_str:
                continue
            try:
                chunk = json.loads(data_str)
                candidates = chunk.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        text = part.get("text", "")
                        if text:
                            yield text
            except Exception:
                continue
    except Exception as exc:
        logger.error("Gemini stream exception: %s", exc)
        yield f"[ERROR] Stream error: {exc}"


def _finite(value, digits=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if digits is not None:
        return round(number, digits)
    return number


def _signal_row(symbol: str):
    if not symbol:
        return None
    signal = MarketSignal.objects.filter(symbol=symbol).order_by("-created_at").first()
    return signal.as_dict() if signal else None


def _candles_frame(candles: list) -> pd.DataFrame | None:
    if not candles or len(candles) < 20:
        return None
    rows = []
    for item in candles[-300:]:
        rows.append({
            "open": _finite(item.get("open")),
            "high": _finite(item.get("high")),
            "low": _finite(item.get("low")),
            "close": _finite(item.get("close")),
            "epoch": _finite(item.get("epoch") or (item.get("time", 0) / 1000 if item.get("time") else None)),
        })
    df = pd.DataFrame(rows).dropna(subset=["open", "high", "low", "close"])
    if len(df) < 20:
        return None
    return df.reset_index(drop=True)


def _technical_snapshot(candles: list, live_price=None) -> dict:
    df = _candles_frame(candles)
    if df is None:
        price = _finite(live_price)
        return {"price": price, "bars": 0} if price is not None else {}
    try:
        df = add_technical_indicators(df)
    except Exception:
        pass
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = _finite(live_price) or _finite(last.get("close"))
    recent = df.tail(20)
    support = _finite(recent["low"].min(), 6)
    resistance = _finite(recent["high"].max(), 6)
    return {
        "price": close,
        "bars": int(len(df)),
        "open": _finite(last.get("open"), 6),
        "high": _finite(last.get("high"), 6),
        "low": _finite(last.get("low"), 6),
        "close": _finite(last.get("close"), 6),
        "prev_close": _finite(prev.get("close"), 6),
        "rsi": _finite(last.get("RSI"), 1),
        "atr": _finite(last.get("ATR"), 6),
        "ema8": _finite(last.get("EMA8"), 6),
        "ema21": _finite(last.get("EMA21"), 6),
        "macd": _finite(last.get("MACD"), 6),
        "support": support,
        "resistance": resistance,
    }


def _market_context(symbol: str, snapshot: dict | None = None, live_price=None, symbol_name: str = None) -> str:
    if not symbol:
        return "No symbol is currently selected on the chart."
    
    # Use provided symbol name or get it from display_name
    name = symbol_name if symbol_name else display_name(symbol)
    market_type = get_market_type(symbol)
    
    # Build comprehensive market context
    parts = [f"Analyzing {name} ({symbol})"]
    parts.append(f"Market Type: {market_type}")
    
    price = _finite(live_price) or (snapshot or {}).get("price")
    if price is not None:
        parts.append(f"Current Price: {price}")
    
    if snapshot:
        bits = []
        for key in ("rsi", "atr", "ema8", "ema21", "macd", "support", "resistance", "bars"):
            if snapshot.get(key) is not None:
                bits.append(f"{key.upper()}: {snapshot[key]}")
        if bits:
            parts.append("Technical Indicators: " + ", ".join(bits))
    
    signal = _signal_row(symbol)
    if signal:
        parts.append(
            "Trading Signal — Direction: {direction}, Strength: {signal_strength}, "
            "Setup Quality: {setup_quality}, Opportunity Score: {opportunity_score}, "
            "Risk Level: {risk_level}, Stop Loss: {stop_loss}, Take Profit: {take_profit}, "
            "Risk-Reward Ratio: {risk_reward}, Model Confidence: {model_confidence}%, Pattern: {pattern}".format(**{
                "direction": signal.get("direction"),
                "signal_strength": signal.get("signal_strength"),
                "setup_quality": signal.get("setup_quality"),
                "opportunity_score": signal.get("opportunity_score"),
                "risk_level": signal.get("risk_level"),
                "stop_loss": signal.get("stop_loss"),
                "take_profit": signal.get("take_profit"),
                "risk_reward": signal.get("risk_reward"),
                "model_confidence": signal.get("model_confidence"),
                "pattern": signal.get("pattern") or "n/a",
            })
        )
    else:
        parts.append("No active trading signal available for this market")
    
    return ". ".join(parts) + "."


def _llm(system_prompt: str, messages: list, max_tokens: int = 800, use_gemini: bool = False) -> tuple[str | None, str | None, int]:
    groq_key, anthropic_key, gemini_key = _api_keys()
    
    logger.info("LLM request - use_gemini: %s, gemini_key_exists: %s, groq_key_exists: %s", 
                use_gemini, bool(gemini_key), bool(groq_key))
    
    # 1. If explicit Gemini requested
    if use_gemini and gemini_key:
        logger.info("Using Gemini API for request")
        try:
            reply, error, status = _gemini_chat(gemini_key, system_prompt, messages, max_tokens)
            if not error:
                return reply, None, 200
            logger.warning("Gemini error: %s, falling back to Groq", error)
        except Exception as exc:
            logger.warning("Gemini exception: %s, falling back to Groq", exc)
    
    # 2. Try Groq if available
    groq_error = None
    if groq_key:
        try:
            reply, error, status = _groq_chat(groq_key, system_prompt, messages, max_tokens)
            if not error:
                return reply, None, 200
            groq_error = error
            logger.warning("Groq API error: %s (status=%s)", error, status)

            # If rate limited (TPD/TPM) or server error, switch to Gemini or Anthropic immediately
            if _is_rate_limited(error) or status in (429, 500, 502, 503):
                logger.info("Groq rate limit or server issue detected. Switching to Gemini fallback...")
                if gemini_key:
                    g_reply, g_err, g_status = _gemini_chat(gemini_key, system_prompt, messages, max_tokens)
                    if not g_err:
                        logger.info("Successfully recovered via Gemini fallback!")
                        return g_reply, None, 200
                    logger.warning("Gemini fallback also failed: %s", g_err)
                if anthropic_key:
                    a_reply, a_err, a_status = _anthropic_chat(anthropic_key, system_prompt, messages, max_tokens)
                    if not a_err:
                        logger.info("Successfully recovered via Anthropic fallback!")
                        return a_reply, None, 200
        except Exception as exc:
            logger.error("Groq request exception: %s", exc)
            groq_error = str(exc)

    # 3. If Groq failed or key is missing, try Gemini directly
    if gemini_key:
        logger.info("Attempting primary/recovery request via Gemini API...")
        try:
            reply, error, status = _gemini_chat(gemini_key, system_prompt, messages, max_tokens)
            if not error:
                return reply, None, 200
        except Exception as exc:
            logger.error("Gemini request exception: %s", exc)

    # 4. Try Anthropic as last resort
    if anthropic_key:
        try:
            reply, error, status = _anthropic_chat(anthropic_key, system_prompt, messages, max_tokens)
            if not error:
                return reply, None, 200
        except Exception as exc:
            logger.error("Anthropic request exception: %s", exc)

    final_error = groq_error or "AI service temporarily unavailable. Rate limit reached and fallbacks exhausted."
    return None, final_error, 502


def _extract_json(text: str):
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json|actions)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None


@csrf_exempt
@require_GET
def chat_history(request):
    """Get chat history for the authenticated user."""
    try:
        user = request.user if request.user.is_authenticated else None
        if not user:
            return JsonResponse({'history': [], 'error': 'User not authenticated'})
        
        symbol = request.GET.get('symbol', '')
        
        # Get recent messages for this user, optionally filtered by symbol
        queryset = ChatMessage.objects.filter(user=user)
        if symbol:
            queryset = queryset.filter(symbol=symbol)
        
        # Get last 50 messages
        messages = queryset.order_by('-created_at')[:50]
        
        # Convert to chat format (oldest first)
        history = []
        for msg in reversed(messages):
            history.append({
                'role': msg.role,
                'content': msg.content,
                'symbol': msg.symbol,
                'created_at': msg.created_at.isoformat()
            })
        
        return JsonResponse({'history': history})
    except Exception as e:
        logger.error("Error fetching chat history: %s", e)
        return JsonResponse({'error': 'Failed to fetch chat history'}, status=500)


@csrf_exempt
@require_POST
def chat(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Malformed request body."}, status=400)

    message = (payload.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "Empty message."}, status=400)

    symbol = payload.get("symbol") or ""
    symbol_name = payload.get("symbol_name") or ""
    history = payload.get("history") or []
    snapshot = _technical_snapshot(payload.get("candles") or [], payload.get("price"))
    voice_input = payload.get("voice_input", False)  # Detect if this is from voice input
    
    # Save user message to database if authenticated
    user = request.user if request.user.is_authenticated else None
    if user:
        try:
            ChatMessage.objects.create(
                user=user,
                role='user',
                content=message,
                symbol=symbol if symbol else None
            )
        except Exception as e:
            logger.warning("Failed to save user message: %s", e)
    
    # Build context - if no symbol is provided, use a general context for news analysis
    if symbol:
        context = _market_context(symbol, snapshot, payload.get("price"), symbol_name)
        # Use symbol name for better display if available
        display_symbol = symbol_name if symbol_name else symbol
        user_message = f"[Chart context: {context}]\n\n{message}"
    else:
        # For news analysis without a specific chart, provide general context
        context = "General market news and economic analysis context. No specific chart is currently selected."
        user_message = f"[Context: {context}]\n\n{message}"

    messages = []
    for turn in history[-12:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    # Use voice-optimized prompt for voice input, regular prompt for text chat
    system_prompt = VOICE_SYSTEM_PROMPT if voice_input else SYSTEM_PROMPT
    
    # Do not use Gemini for voice; use high-performance Groq/Anthropic
    reply, error, status = _llm(system_prompt, messages, max_tokens=700, use_gemini=False)
    if error:
        return JsonResponse({"error": error}, status=status)
    actions = []
    parsed = _extract_json(reply or "")
    if parsed and isinstance(parsed.get("actions"), list):
        actions = parsed["actions"]
        reply = re.sub(r"```actions[\s\S]*?```", "", reply or "").strip() or reply
    
    # Save assistant reply to database if authenticated
    if user and reply:
        try:
            ChatMessage.objects.create(
                user=user,
                role='assistant',
                content=reply,
                symbol=symbol if symbol else None
            )
        except Exception as e:
            logger.warning("Failed to save assistant message: %s", e)
    
    return JsonResponse({"reply": reply, "actions": actions, "snapshot": snapshot})


@csrf_exempt
@require_POST
def chat_stream(request):
    """Streaming chat endpoint using Server-Sent Events (SSE)."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Malformed request body."}, status=400)

    message = (payload.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "Empty message."}, status=400)

    symbol = payload.get("symbol") or ""
    symbol_name = payload.get("symbol_name") or ""
    history = payload.get("history") or []
    snapshot = _technical_snapshot(payload.get("candles") or [], payload.get("price"))
    voice_input = payload.get("voice_input", False)

    user = request.user if request.user.is_authenticated else None
    if user:
        try:
            ChatMessage.objects.create(
                user=user,
                role='user',
                content=message,
                symbol=symbol if symbol else None
            )
        except Exception as e:
            logger.warning("Failed to save user message: %s", e)

    if symbol:
        context = _market_context(symbol, snapshot, payload.get("price"), symbol_name)
        user_message = f"[Chart context: {context}]\n\n{message}"
    else:
        context = "General market news and economic analysis context. No specific chart is currently selected."
        user_message = f"[Context: {context}]\n\n{message}"

    messages = []
    for turn in history[-12:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    system_prompt = VOICE_SYSTEM_PROMPT if voice_input else SYSTEM_PROMPT
    groq_key, anthropic_key, gemini_key = _api_keys()

    def stream_generator():
        accumulated = []
        stream_iter = None

        if groq_key:
            stream_iter = _groq_stream(groq_key, system_prompt, messages, max_tokens=700)
        elif gemini_key:
            stream_iter = _gemini_stream(gemini_key, system_prompt, messages, max_tokens=700)
        elif anthropic_key:
            stream_iter = _anthropic_stream(anthropic_key, system_prompt, messages, max_tokens=700)
        else:
            yield f"data: {json.dumps({'error': 'No AI API key configured in .env.'})}\n\n"
            return

        groq_failed = False
        for chunk in stream_iter:
            if chunk.startswith("[ERROR]"):
                logger.warning("Stream error on primary provider: %s", chunk)
                # If Groq encountered error/rate limit and we haven't emitted text yet, fall back to Gemini
                if not accumulated and gemini_key and (stream_iter != _gemini_stream):
                    logger.info("Switching stream to Gemini fallback...")
                    groq_failed = True
                    break
                yield f"data: {json.dumps({'error': chunk})}\n\n"
                return
            accumulated.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

        # If primary stream failed before emitting text, run Gemini stream
        if groq_failed and gemini_key:
            accumulated = []
            for g_chunk in _gemini_stream(gemini_key, system_prompt, messages, max_tokens=700):
                if g_chunk.startswith("[ERROR]"):
                    logger.error("Gemini stream also failed: %s", g_chunk)
                    yield f"data: {json.dumps({'error': g_chunk})}\n\n"
                    return
                accumulated.append(g_chunk)
                yield f"data: {json.dumps({'chunk': g_chunk})}\n\n"

        full_reply = "".join(accumulated)
        actions = []
        parsed = _extract_json(full_reply)
        if parsed and isinstance(parsed.get("actions"), list):
            actions = parsed["actions"]
            clean_reply = re.sub(r"```actions[\s\S]*?```", "", full_reply).strip()
        else:
            clean_reply = full_reply

        if user and full_reply:
            try:
                ChatMessage.objects.create(
                    user=user,
                    role='assistant',
                    content=clean_reply or full_reply,
                    symbol=symbol if symbol else None
                )
            except Exception as e:
                logger.warning("Failed to save assistant message: %s", e)

        yield f"data: {json.dumps({'done': True, 'actions': actions, 'snapshot': snapshot, 'full_reply': clean_reply or full_reply})}\n\n"

    response = StreamingHttpResponse(stream_generator(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@csrf_exempt
@require_POST
def speak(request):
    """Generate human neural speech (JARVIS British voice) using edge-tts."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Malformed request body."}, status=400)

    text = (payload.get("text") or "").strip()
    if not text:
        return JsonResponse({"error": "Empty text."}, status=400)

    # Clean text to remove markdown, code blocks, and symbols
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"[\u2018\u2019]", "'", cleaned)
    cleaned = re.sub(r"[\u201C\u201D]", '"', cleaned)
    cleaned = re.sub(r"[\u2013\u2014\u2015\u2212]", "-", cleaned)
    cleaned = re.sub(r"â[€\x80-\x9f]+", " ", cleaned)
    cleaned = re.sub(r"[*_~#>]", "", cleaned).strip()
    if not cleaned:
        return JsonResponse({"error": "No speakable text."}, status=400)

    # Audio functionality disabled - JAVIS speech removed
    return JsonResponse({"error": "Audio functionality disabled"}, status=503)


@csrf_exempt
@require_POST
def transcribe(request):
    """Transcribe a short browser recording with Groq Whisper."""
    # Audio functionality disabled - JAVIS speech removed
    return JsonResponse({"error": "Audio transcription disabled"}, status=503)


@csrf_exempt
@require_POST
def chart_analysis(request):
    """Structured AI analysis of the chart currently on screen."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Malformed request body."}, status=400)

    symbol = (payload.get("symbol") or "").strip()
    if not symbol:
        return JsonResponse({"error": "Missing symbol."}, status=400)

    symbol_name = payload.get("symbol_name") or ""
    snapshot = _technical_snapshot(payload.get("candles") or [], payload.get("price"))
    signal = _signal_row(symbol)
    context = _market_context(symbol, snapshot, payload.get("price"), symbol_name)
    timeframe = payload.get("timeframe") or "60"

    analysis = None
    groq_key, anthropic_key, gemini_key = _api_keys()
    if groq_key or anthropic_key or gemini_key:
        user_prompt = (
            f"Timeframe: {timeframe} minutes.\n{context}\n"
            f"Snapshot JSON: {json.dumps(snapshot)}\n"
            f"Stored signal JSON: {json.dumps(signal or {})}"
        )
        reply, error, status = _llm(
            ANALYSIS_PROMPT,
            [{"role": "user", "content": user_prompt}],
            max_tokens=900,
        )
        if error:
            return JsonResponse({"error": error, "snapshot": snapshot, "signal": signal}, status=status)
        analysis = _extract_json(reply or "")
        if analysis is None:
            analysis = {
                "bias": "Neutral",
                "confidence": 0,
                "summary": reply or "The model did not return structured analysis.",
                "setup": "",
                "support": snapshot.get("support"),
                "resistance": snapshot.get("resistance"),
                "stop": None,
                "target": None,
                "risks": "",
                "actions": [],
            }
    else:
        analysis = {
            "bias": "Neutral",
            "confidence": 0,
            "summary": "Set GROQ_API_KEY or ANTHROPIC_API_KEY in .env to enable AI analysis. Showing chart snapshot only.",
            "setup": "",
            "support": snapshot.get("support"),
            "resistance": snapshot.get("resistance"),
            "stop": None,
            "target": None,
            "risks": "",
            "actions": [],
        }

    return JsonResponse({
        "symbol": symbol,
        "name": display_name(symbol),
        "snapshot": snapshot,
        "signal": signal,
        "analysis": analysis,
    })


@csrf_exempt
def news_api(request):
    """API endpoint for fetching market news with sentiment analysis."""
    from analysis.services.news_sentiment import NewsSentimentAnalyzer
    
    try:
        analyzer = NewsSentimentAnalyzer()
        
        # Handle POST requests for news analysis
        if request.method == 'POST':
            try:
                payload = json.loads(request.body or "{}")
            except json.JSONDecodeError:
                return JsonResponse({"error": "Malformed request body."}, status=400)
            
            market = payload.get("market", "")
            action = payload.get("action", "")
            
            if action == "analyze" and market:
                # Analyze market news
                try:
                    news_articles = asyncio.run(analyzer.fetch_market_news(market))
                    
                    if not news_articles:
                        return JsonResponse({"error": f"No news found for market: {market}"}, status=404)
                    
                    # Build analysis prompt from news articles
                    news_summary = "\n\n".join([
                        f"Title: {article.get('title', '')}\n"
                        f"Description: {article.get('description', '')}\n"
                        f"Sentiment: {article.get('sentiment', 0)}\n"
                        f"Market Analysis: {article.get('market_analysis', '')}"
                        for article in news_articles[:5]  # Limit to top 5 articles
                    ])
                    
                    prompt = (
                        f"Analyze the following news for {market} and provide trading insights:\n\n"
                        f"{news_summary}\n\n"
                        f"Provide analysis on: 1) Overall market sentiment, 2) Key drivers, "
                        f"3) Potential trading opportunities, 4) Risk factors, 5) Recommended actions."
                    )
                    
                    news_system_prompt = (
                        "You are an AI trading assistant specializing in market news analysis. "
                        "You analyze news events, their impact on markets, and provide trading insights. "
                        "Focus on: 1) Market impact assessment, 2) Trading opportunities, 3) Risk factors, "
                        "4) Recommended actions. Be concise and actionable. "
                        "Always include a disclaimer that this is not financial advice."
                    )
                    
                    reply, error, status = _llm(
                        news_system_prompt,
                        [{"role": "user", "content": prompt}],
                        max_tokens=1000,
                    )
                    
                    if error:
                        # Provide more detailed error information
                        if "API key" in error.lower() or "invalid" in error.lower():
                            error = "AI API key issue. Please check GROQ_API_KEY or ANTHROPIC_API_KEY in your .env file."
                        return JsonResponse({"error": error}, status=status)
                    
                    return JsonResponse({"response": reply, "market": market, "news_count": len(news_articles)})
                    
                except Exception as e:
                    return JsonResponse({"error": f"News analysis failed: {str(e)}"}, status=500)
        
        # Handle GET requests for fetching news
        symbol = request.GET.get("symbol", "")
        category = request.GET.get("category", "")
        
        try:
            news_articles = asyncio.run(analyzer.fetch_market_news(symbol or None))
            
            # Filter by category if specified
            if category:
                news_articles = [article for article in news_articles 
                               if article.get('category', '').lower() == category.lower()]
            
            return JsonResponse({"news": news_articles})
            
        except Exception as e:
            return JsonResponse({"error": f"Failed to fetch news: {str(e)}"}, status=500)
            
    except Exception as e:
        return JsonResponse({"error": f"News API error: {str(e)}"}, status=500)


@csrf_exempt
@require_POST
def analyze(request):
    """General AI analysis endpoint for news analysis and other features."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Malformed request body."}, status=400)

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return JsonResponse({"error": "Empty prompt."}, status=400)

    news_system_prompt = (
        "You are an AI trading assistant specializing in economic calendar analysis. "
        "You analyze economic events, their impact on markets, and provide trading insights. "
        "Focus on: 1) Market impact assessment, 2) Trading opportunities, 3) Risk factors, "
        "4) Recommended currency pairs to watch. Be concise and actionable. "
        "Always include a disclaimer that this is not financial advice."
    )
    reply, error, status = _llm(
        news_system_prompt,
        [{"role": "user", "content": prompt}],
        max_tokens=1000,
    )
    if error:
        return JsonResponse({"error": error}, status=status)
    return JsonResponse({"response": reply})
