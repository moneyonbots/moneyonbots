from django.db.models import Avg, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from dashboard.context import base_context
from markets.catalog import all_symbols, display_name, AVAILABLE_MARKETS

from .models import MarketSignal, UserProfile
from .services.strategy_modes import generate_strategy_mode_signal


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
    """Get all currently active signals for the live signals table, adapted to strategy_mode if requested."""
    strategy_mode = request.GET.get('strategy_mode', 'default').lower()
    symbol = request.GET.get("symbol")
    timeframe = request.GET.get("timeframe")

    queryset = MarketSignal.objects.filter(status="active").order_by("-created_at")
    if symbol:
        queryset = queryset.filter(symbol=symbol)
    if timeframe:
        queryset = queryset.filter(timeframe=timeframe)

    from analysis.services.strategy_modes import adapt_signal_dict, generate_strategy_mode_signal
    from analysis.services.deriv_client import feed
    from analysis.services.indicators import add_technical_indicators

    seen = set()
    results = []

    for signal in queryset:
        if not timeframe and signal.symbol in seen:
            continue
        seen.add(signal.symbol)
        sig_dict = signal.as_dict()

        if strategy_mode and strategy_mode != 'default':
            try:
                df = feed.get_dataframe(signal.symbol)
                if df is not None and len(df) >= 30:
                    df = add_technical_indicators(df)
                    sig_dict = generate_strategy_mode_signal(
                        symbol=signal.symbol,
                        df=df,
                        model_proba_up=0.65,
                        strategy_mode=strategy_mode,
                        timeframe=signal.timeframe or "1H"
                    )
                else:
                    sig_dict = adapt_signal_dict(sig_dict, strategy_mode)
            except Exception:
                sig_dict = adapt_signal_dict(sig_dict, strategy_mode)
        else:
            sig_dict['strategy_mode'] = 'default'

        results.append(sig_dict)
        if len(results) >= 100:
            break

    return JsonResponse({"signals": results, "current_mode": strategy_mode})


@csrf_exempt
def strategy_mode_analysis(request):
    """Generate signal using specific strategy mode analysis (single or batch)."""
    import json
    from analysis.services.indicators import add_technical_indicators
    from analysis.services.deriv_client import feed
    from analysis.services.strategy_modes import generate_strategy_mode_signal, adapt_signal_dict

    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        data = json.loads(request.body)
        symbol = data.get('symbol')
        strategy_mode = data.get('strategy_mode', 'default').lower()
        timeframe = data.get('timeframe', '1H')

        if not symbol:
            return JsonResponse({'error': 'Symbol required'}, status=400)

        # 1. Try live dataframe if feed has accumulated data
        try:
            df = feed.get_dataframe(symbol)
            if df is not None and len(df) >= 30:
                df = add_technical_indicators(df)
                signal = generate_strategy_mode_signal(
                    symbol=symbol,
                    df=df,
                    model_proba_up=0.65,
                    strategy_mode=strategy_mode,
                    timeframe=timeframe
                )
                return JsonResponse({'signal': signal})
        except Exception:
            pass

        # 2. Fallback to active MarketSignal from database adapted to strategy mode
        db_sig = MarketSignal.objects.filter(symbol=symbol, status="active").order_by("-created_at").first()
        if db_sig:
            sig_dict = adapt_signal_dict(db_sig.as_dict(), strategy_mode)
            return JsonResponse({'signal': sig_dict})

        # 3. Fallback to general market catalog baseline adapted
        fallback_sig = {
            'symbol': symbol,
            'market_name': symbol,
            'market_type': 'synthetic',
            'price': 100.0,
            'direction': 'Buy',
            'rsi': 52.0,
            'atr': 1.5,
            'timeframe': timeframe
        }
        return JsonResponse({'signal': adapt_signal_dict(fallback_sig, strategy_mode)})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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


def toggle_favorite_api(request):
    """API endpoint to toggle a symbol in user's favorites."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed"}, status=405)

    try:
        import json
        data = json.loads(request.body) if request.body else request.POST
        symbol = data.get("symbol")
        if not symbol:
            return JsonResponse({"error": "Missing symbol"}, status=400)

        profile, _ = UserProfile.objects.get_or_create(
            user=request.user,
            defaults={"favorites": ["frxEURUSD", "stpRNG", "cryBTCUSD", "frxXAUUSD"]}
        )
        is_fav = profile.toggle_favorite(symbol)
        return JsonResponse({
            "success": True,
            "symbol": symbol,
            "is_favorite": is_fav,
            "favorites": profile.favorites or [],
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def update_alert_preferences_api(request):
    """API endpoint to update user alert preferences."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed"}, status=405)

    try:
        import json
        data = json.loads(request.body) if request.body else request.POST

        profile, _ = UserProfile.objects.get_or_create(
            user=request.user,
            defaults={"favorites": ["frxEURUSD", "stpRNG", "cryBTCUSD", "frxXAUUSD"]}
        )

        if "email_alerts_enabled" in data:
            profile.email_alerts_enabled = bool(data.get("email_alerts_enabled"))
        if "alert_min_quality" in data:
            try:
                profile.alert_min_quality = max(0, min(100, int(data.get("alert_min_quality", 70))))
            except (ValueError, TypeError):
                pass
        if "alert_directions" in data:
            dir_val = data.get("alert_directions")
            if dir_val in ["all", "Buy", "Sell"]:
                profile.alert_directions = dir_val
        if "alert_favorites_only" in data:
            profile.alert_favorites_only = bool(data.get("alert_favorites_only"))
        if "alert_timeframe" in data:
            tf_val = data.get("alert_timeframe")
            if tf_val in ["all", "1H", "4H", "1D"]:
                profile.alert_timeframe = tf_val

        profile.save()
        return JsonResponse({
            "success": True,
            "message": "Alert preferences updated successfully",
            "profile": profile.as_dict(),
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def send_test_alert_api(request):
    """API endpoint to trigger a sample alert email to the authenticated user."""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    if request.method != "POST":
        return JsonResponse({"error": "Only POST method allowed"}, status=405)

    try:
        from alerts.email_alerts import send_test_alert
        success, message = send_test_alert(request.user)
        return JsonResponse({
            "success": success,
            "message": message,
        })
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)