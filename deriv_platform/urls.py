from django.contrib import admin
from django.http import HttpResponse, FileResponse
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static
from pathlib import Path

def google_login_redirect(request):
    """Redirect to the correct allauth Google login URL."""
    process = request.GET.get('process', 'login')
    return redirect(f'/accounts/social/google/login/?process={process}')

def healthz(_request):
    return HttpResponse("ok", content_type="text/plain")

def favicon(request):
    """Serve favicon.ico to prevent 404/500 errors."""
    try:
        favicon_path = Path(settings.STATIC_ROOT) / "favicon.ico"
        if not favicon_path.exists():
            favicon_path = Path(settings.BASE_DIR) / "static" / "favicon.ico"
        
        if favicon_path.exists():
            return FileResponse(favicon_path.open('rb'), content_type="image/x-icon")
    except Exception:
        pass
    return HttpResponse("", status=204)  # Return empty response if favicon not found

def robots_txt(request):
    """Serve robots.txt to prevent 404 errors."""
    return HttpResponse(
        "User-agent: *\nDisallow: /admin/\n",
        content_type="text/plain"
    )

urlpatterns = [
    path("favicon.ico", favicon),
    path("robots.txt", robots_txt),
    path("healthz", healthz),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("accounts/google/login/", google_login_redirect, name="google_login"),
    path("", include("dashboard.urls")),
    path("news/", include("news.urls")),
    path("api/", include("analysis.urls")),
    path("analysis/", include("analysis.urls")),
    path("api/", include("positions.urls")),
    path("api/ai/", include("assistant.urls")),
    path("signals/", include("analysis.urls")),  # Add direct /signals/ route for live signals page
    path("stocks/", include("stocks.urls")),  # Add stocks page with TradingView integration
    # WebSocket routes are handled in ASGI, not here
]

# Serve static files in development (not needed in production with WhiteNoise)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
