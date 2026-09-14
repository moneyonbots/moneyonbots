"""
python manage.py run_analysis

The core loop: keeps one Deriv WebSocket feed alive for every market,
periodically runs the ML + signal engine on each, saves a MarketSignal,
broadcasts it to any connected analysis-window websockets, opens/closes
paper positions, and (optionally) emails an alert on strong signals.

Run this as a long-lived process (systemd service), separate from the
Django web/ASGI server — same pattern as the original bot.py's
`while True: await main(...)` loop.
"""
import asyncio
import logging
import random
import time

from channels.db import database_sync_to_async
from django.core.management.base import BaseCommand
from django.utils import timezone

from alerts.email_alerts import send_trade_alert
from analysis.models import MarketSignal
from analysis.services.broadcaster import broadcast
from analysis.services.deriv_client import feed
from analysis.services.indicators import add_technical_indicators
from analysis.services.ml_engine import registry
from analysis.services.price_monitor import price_monitor
from analysis.services.signal_engine import generate_signal, passes_trade_filters
from analysis.services.profitable_signal_generator import generate_profitable_signal
from analysis.services.news_sentiment import news_analyzer
from markets.catalog import all_symbols, is_market_open
from positions.services.position_manager import check_and_close_positions, maybe_open_position

logger = logging.getLogger(__name__)

# Configuration: Use profitable signal generator or original
USE_PROFITABLE_SIGNALS = True  # Set to False to use original signal engine


@database_sync_to_async
def _save_signal(signal: dict, model_confidence: float) -> dict:
    now = timezone.now()
    timeframe = signal.get("timeframe", "1H")
    MarketSignal.objects.filter(symbol=signal["symbol"], status="active", timeframe=timeframe).update(
        status="completed",
        completed_at=now,
    )
    obj = MarketSignal.objects.create(
        symbol=signal["symbol"],
        market_name=signal["market_name"],
        market_type=signal["market_type"],
        timeframe=signal.get("timeframe", "1H"),
        direction=signal["direction"],
        signal_strength=signal["signal_strength"],
        setup_quality=signal["setup_quality"],
        opportunity_score=signal["opportunity_score"],
        entry_type=signal["entry_type"],
        risk_level=signal["risk_level"],
        structure=signal.get("structure", "Neutral"),
        price=signal["price"],
        rsi=signal["rsi"],
        atr=signal["atr"],
        stop_loss=signal["stop_loss"],
        take_profit=signal["take_profit"],
        risk_reward=signal["risk_reward"],
        model_confidence=model_confidence,
        confirmation_count=signal.get("confirmation_count", 0),
        pattern=signal.get("pattern", ""),
        patterns_identified=signal.get("patterns_identified", []),
        support_resistance=signal.get("support_resistance", {}),
        technical_notes=signal.get("technical_notes", []),
        news_sentiment=signal.get("news_sentiment"),
        news_count=signal.get("news_count", 0),
        status="active",  # New signals start as active
        htf_advice=signal.get("htf_advice", ""),
    )
    return obj.as_dict()


@database_sync_to_async
def _update_signal_strength(symbol: str, new_strength: float, new_rsi: float, new_price: float, timeframe: str = "1H") -> dict:
    """Update strength of existing active signal for live updates."""
    signal = MarketSignal.objects.filter(symbol=symbol, status="active", timeframe=timeframe).first()
    if signal:
        signal.signal_strength = new_strength
        signal.rsi = new_rsi
        signal.price = new_price
        signal.save()
        return signal.as_dict()
    return None


@database_sync_to_async
def _get_existing_signal(symbol: str, timeframe: str = "1H") -> dict:
    """Get existing active signal for a symbol and timeframe."""
    signal = MarketSignal.objects.filter(symbol=symbol, status="active", timeframe=timeframe).first()
    if signal:
        return signal.as_dict()
    return None


_maybe_open_position = database_sync_to_async(maybe_open_position)
_check_and_close_positions = database_sync_to_async(check_and_close_positions)
_check_signal_tp_sl = database_sync_to_async(price_monitor.check_symbol)
_broadcast_price_update = database_sync_to_async(price_monitor.broadcast_price_update)
_get_active_signals = database_sync_to_async(
    lambda symbol: list(MarketSignal.objects.filter(symbol=symbol, status="active"))
)


async def analyze_symbol(symbol: str):
    # Check if market is open
    is_open, market_status = is_market_open(symbol)
    if not is_open:
        logger.info(f"Skipping {symbol} - market closed: {market_status}")
        return
        
    df = feed.get_dataframe(symbol)
    
    # Only proceed if we have real data
    # For daily timeframe, we need fewer candles but still need sufficient data
    if df is None or len(df) < 30:
        logger.debug(f"No data available for {symbol}, skipping analysis")
        return
    
    # Log data source for debugging
    from django.core.cache import cache
    chart_data = cache.get(f"chart_data_{symbol}")
    if chart_data:
        logger.info(f"Using chart data for {symbol} (from browser)")
    else:
        logger.info(f"Using WebSocket data for {symbol} (from server)")

    current_price = float(df.iloc[-1]["close"])
    logger.debug("Current price for %s: %s", symbol, current_price)

    # Broadcast live price updates for active signals
    await _broadcast_price_update(symbol, current_price)

    # Close paper positions and check active signals for TP/SL hits
    await _check_and_close_positions(symbol, current_price)
    await _check_signal_tp_sl(symbol, current_price)

    df_ind = add_technical_indicators(df)
    # For daily timeframe, we can work with fewer candles
    min_candles = 20  
    if len(df_ind) < min_candles:
        return

    model = registry.get_or_train(symbol, df)
    proba_up = model.predict_proba_up(df_ind)

    # Fetch news sentiment for market context
    try:
        news = await news_analyzer.fetch_market_news(symbol)
        overall_sentiment = news_analyzer.get_overall_sentiment(news)
        logger.info(f"News sentiment for {symbol}: {overall_sentiment:.2f}")
    except Exception as news_exc:
        logger.warning("News sentiment analysis failed: %s", news_exc)
        overall_sentiment = 0.0
        news = []

    # Support all timeframes for scalping, day trading, and swing trading
    timeframes = ["1M", "5M", "15M", "30M", "1H", "4H", "1D"]
    for timeframe in timeframes:
        try:
            logger.debug(f"Generating signal for {symbol} with timeframe {timeframe}")
            
            # Use profitable signal generator if enabled, otherwise use original
            if USE_PROFITABLE_SIGNALS:
                logger.debug(f"Using profitable signal generator for {symbol}")
                signal = generate_profitable_signal(symbol, df_ind, proba_up, timeframe=timeframe)
            else:
                logger.debug(f"Using original signal engine for {symbol}")
                signal = generate_signal(symbol, df_ind, proba_up, timeframe=timeframe)
            
            # Add news sentiment to signal
            signal['news_sentiment'] = overall_sentiment
            signal['news_count'] = len(news)
            
            # Check if there's an existing active signal for this symbol and timeframe
            existing_signal = await _get_existing_signal(symbol, timeframe)
            
            if signal["direction"] in ("Buy", "Sell"):
                # Calculate direction-aware confidence
                if signal["direction"] == "Buy":
                    direction_confidence = proba_up
                elif signal["direction"] == "Sell":
                    direction_confidence = 1.0 - proba_up
                else:
                    direction_confidence = proba_up
                
                if existing_signal and existing_signal["direction"] == signal["direction"]:
                    # Update existing signal strength for live updates
                    updated_signal = await _update_signal_strength(
                        symbol, 
                        signal["signal_strength"],
                        signal["rsi"],
                        current_price,
                        timeframe=timeframe
                    )
                    if updated_signal:
                        await broadcast({"type": "signal_update", "signal": updated_signal})
                        logger.info(f"Updated signal strength for {symbol} ({timeframe}): {signal['signal_strength']:.2f}")
                else:
                    # Create new signal
                    signal_dict = await _save_signal(signal, direction_confidence)
                    await broadcast({"type": "signal", "signal": signal_dict})
                    
                    # Check if signal passes trade filters for position opening
                    if passes_trade_filters(signal):
                        # Paper trading only
                        position = await _maybe_open_position(signal)
                        if position:
                            await broadcast({"type": "position_opened", "symbol": symbol})
                            try:
                                send_trade_alert(
                                    signal,
                                    {
                                        "entry": signal["price"],
                                        "stop_loss": signal["stop_loss"],
                                        "take_profit": signal["take_profit"],
                                        "market_name": signal["market_name"],
                                    },
                                    f"Paper position opened: {position.volume} lots, risk ~{position.risk_pct:.2f}%",
                                )
                            except Exception as exc:
                                logger.warning("Email alert failed: %s", exc)
        except Exception as exc:
            logger.error("Signal generation failed for %s timeframe %s: %s", symbol, timeframe, exc)


async def analysis_loop(interval_seconds: int):
    from django.core.cache import cache
    
    while True:
        start = time.time()
        
        # Prioritize current chart symbol if available
        current_chart_symbol = cache.get('current_chart_symbol')
        symbols_to_analyze = []
        
        if current_chart_symbol and current_chart_symbol in feed.symbols:
            # Analyze current chart symbol first
            symbols_to_analyze.append(current_chart_symbol)
            logger.info(f"Prioritizing current chart symbol: {current_chart_symbol}")
        
        # Add remaining symbols
        for symbol in feed.symbols:
            if symbol not in symbols_to_analyze:
                symbols_to_analyze.append(symbol)
        
        # The feed provides a validated, live catalogue from active_symbols.
        for symbol in symbols_to_analyze:
            try:
                await analyze_symbol(symbol)
            except Exception as exc:
                logger.error("Analysis error for %s: %s", symbol, exc)
        elapsed = time.time() - start
        await asyncio.sleep(max(1.0, interval_seconds - elapsed))


async def main(interval_seconds: int):
    from django.core.cache import cache
    
    # Always run WebSocket feed as fallback and for non-chart symbols
    feed_task = asyncio.create_task(feed.run_forever())
    
    # Give the feed a moment to pull initial candle history before scoring.
    await asyncio.sleep(10)
    
    # Check if we have chart data available (browser integration)
    has_chart_data = cache.get('current_chart_symbol') is not None
    if has_chart_data:
        logger.info("Chart data integration active - analysis will prioritize browser data")
    else:
        logger.info("No chart data available - analysis will use WebSocket feed data")
    
    loop_task = asyncio.create_task(analysis_loop(interval_seconds))
    await asyncio.gather(feed_task, loop_task)


class Command(BaseCommand):
    help = "Run the live Deriv analysis + paper-trading loop."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=None, help="Seconds between full market scans")

    def handle(self, *args, **options):
        from django.conf import settings

        interval = options["interval"] or settings.ANALYSIS_INTERVAL_SECONDS
        self.stdout.write(self.style.SUCCESS(f"Starting analysis loop (interval={interval}s)..."))
        try:
            asyncio.run(main(interval))
        except KeyboardInterrupt:
            self.stdout.write("Stopped.")
