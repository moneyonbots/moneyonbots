from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from .context import base_context
from markets.catalog import AVAILABLE_MARKETS, get_market_type, display_name
from analysis.models import MarketSignal, UserProfile


def index(request):
    ctx = base_context(active_nav="dashboard")
    # Use a working symbol as default - frxEURUSD (EUR/USD) is confirmed to work with public API
    ctx["default_symbol"] = request.GET.get("symbol", "frxEURUSD")
    return render(request, "dashboard/index.html", ctx)


@login_required
def profile_view(request):
    """User profile and personal dashboard view with favorites tracker and email alerts."""
    ctx = base_context(active_nav="profile")

    profile, _ = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={"favorites": ["frxEURUSD", "stpRNG", "cryBTCUSD", "frxXAUUSD"]}
    )

    user_favs = profile.favorites or []

    # Categorize all available markets
    categorized_markets = {
        "forex": [],
        "commodities": [],
        "crypto": [],
        "synthetic": [],
    }

    for sym, name in AVAILABLE_MARKETS.items():
        m_type = get_market_type(sym)
        if "cry" in sym.lower() or "btc" in sym.lower() or "eth" in sym.lower():
            cat = "crypto"
        elif m_type in ("synthetic", "volatility"):
            cat = "synthetic"
        elif m_type == "commodities":
            cat = "commodities"
        else:
            cat = "forex"

        categorized_markets[cat].append({
            "symbol": sym,
            "name": name,
            "is_fav": sym in user_favs,
        })

    # Get latest active signals for favorited markets
    favorite_signals = []
    if user_favs:
        for sym in user_favs:
            sig = MarketSignal.objects.filter(symbol=sym).order_by("-created_at").first()
            favorite_signals.append({
                "symbol": sym,
                "name": display_name(sym),
                "signal": sig.as_dict() if sig else None,
            })

    ctx.update({
        "profile": profile,
        "favorites": user_favs,
        "categorized_markets": categorized_markets,
        "favorite_signals": favorite_signals,
        "total_markets_count": len(AVAILABLE_MARKETS),
    })
    return render(request, "dashboard/profile.html", ctx)

