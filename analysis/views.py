from django.db.models import Avg, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from dashboard.context import base_context
from markets.catalog import all_symbols, display_name, AVAILABLE_MARKETS

from .models import MarketSignal


def _completed_signals_queryset():
    return MarketSignal.objects.filter(
        status="completed",
        pnl_hit__in=["tp", "sl"],
    )


def latest_signals(request):
    """Latest MarketSignal per symbol, for the analysis window's first paint
    (live updates after that arrive over the ws/analysis/ websocket)."""
    results = []
    for symbol in all_symbols():
        signal = MarketSignal.objects.filter(symbol=symbol).order_by("-created_at").first()
        if signal:
            results.append(signal.as_dict())
    return JsonResponse({"signals": results})


def active_signals(request):
    """Return active signals — one per symbol to avoid duplicate live rows."""
    seen = set()
    signals = []
    queryset = MarketSignal.objects.filter(status="active")
    symbol = request.GET.get("symbol")
    if symbol:
        queryset = queryset.filter(symbol=symbol)
    timeframe = request.GET.get("timeframe")
    if timeframe:
        queryset = queryset.filter(timeframe=timeframe)
    
    # When timeframe is specified, allow multiple signals per symbol for different timeframes
    # When no timeframe specified, show one signal per symbol (prefer 1H over 1D)
    if timeframe:
        # When timeframe is specified, return all signals for that timeframe
        signals = [signal.as_dict() for signal in queryset.order_by("-created_at")[:100]]
    else:
        # When no timeframe, ensure one signal per symbol (prefer 1H over 1D)
        for signal in queryset.order_by("-created_at"):
            if signal.symbol in seen:
                continue
            seen.add(signal.symbol)
            signals.append(signal.as_dict())
            if len(signals) >= 100:
                break
    
    return JsonResponse({"signals": signals})


def signal_history(request):
    """Completed TP/SL signals — used by Performance page and chart scanner."""
    qs = _completed_signals_queryset().order_by("-completed_at", "-created_at")
    symbol = request.GET.get("symbol")
    if symbol:
        qs = qs.filter(symbol=symbol)
    timeframe = request.GET.get("timeframe")
    if timeframe:
        qs = qs.filter(timeframe=timeframe)
    limit = min(int(request.GET.get("limit", 200)), 500)
    signals = [signal.as_dict() for signal in qs[:limit]]
    return JsonResponse({"signals": signals})


def performance_stats(request):
    """Aggregate win/loss stats for the Performance dashboard."""
    qs = _completed_signals_queryset()
    tp_count = qs.filter(pnl_hit="tp").count()
    sl_count = qs.filter(pnl_hit="sl").count()
    total = tp_count + sl_count
    aggregates = qs.aggregate(
        avg_pnl=Avg("actual_pnl"),
        avg_win=Avg("actual_pnl", filter=Q(pnl_hit="tp")),
        avg_loss=Avg("actual_pnl", filter=Q(pnl_hit="sl")),
    )
    return JsonResponse({
        "total_trades": total,
        "wins": tp_count,
        "losses": sl_count,
        "win_rate": round(tp_count / total * 100, 1) if total else 0,
        "avg_pnl": round(aggregates["avg_pnl"] or 0, 2),
        "avg_win": round(aggregates["avg_win"] or 0, 2),
        "avg_loss": round(aggregates["avg_loss"] or 0, 2),
    })


@csrf_exempt
def performance_page(request):
    """Performance page: signal history for completed TP/SL trades."""
    ctx = base_context(active_nav="performance")
    return render(request, "dashboard/performance.html", ctx)


@ensure_csrf_cookie
def live_signals_page(request):
    """Live signals page. The browser fills the table from chart-market candles."""
    ctx = base_context(active_nav="signals")
    ctx.update({
        'signals': [],
        'market_types': {},
        'total_markets': len(AVAILABLE_MARKETS),
        'active_signals': 0,
        'active_signals_db': [],
    })
    return render(request, "dashboard/live_signals.html", ctx)


def live_signals_api(request):
    """API endpoint for live signals - returns active signals from database that move with price."""
    market_type = request.GET.get('market_type')
    
    # Get active signals from database (these are the ones that move with price)
    queryset = MarketSignal.objects.filter(status="active")
    
    if market_type:
        queryset = queryset.filter(market_type=market_type)
    
    # Get one signal per symbol (the most recent active one)
    seen_symbols = set()
    signals = []
    for signal in queryset.order_by("-created_at"):
        if signal.symbol not in seen_symbols:
            seen_symbols.add(signal.symbol)
            signals.append(signal.as_dict())
            if len(signals) >= 100:  # Limit to 100 signals
                break
    
    return JsonResponse({"signals": signals})


def update_signal_price(request):
    """API endpoint to update current price for active signals (called from frontend)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        symbol = data.get('symbol')
        current_price = data.get('current_price')
        
        if not symbol or current_price is None:
            return JsonResponse({'error': 'Missing symbol or current_price'}, status=400)
        
        # Update current_price for all active signals for this symbol
        updated_count = MarketSignal.objects.filter(
            symbol=symbol,
            status='active'
        ).update(current_price=current_price)
        
        # Trigger price monitoring check for this symbol
        from analysis.services.price_monitor import price_monitor
        hit_signals = price_monitor.check_symbol(symbol, current_price)
        
        return JsonResponse({
            'success': True,
            'updated_count': updated_count,
            'hit_signals': len(hit_signals)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)