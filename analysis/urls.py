from django.urls import path

from . import views

urlpatterns = [
    path("signals/latest/", views.latest_signals, name="latest_signals"),
    path("signals/active/", views.active_signals, name="active_signals"),
    path("signals/history/", views.signal_history, name="signal_history"),
    path("signals/live/", views.live_signals_api, name="live_signals_api"),
    path("signals/update-price/", views.update_signal_price, name="update_signal_price"),
    path("signals/page/", views.live_signals_page, name="live_signals_page"),
    path("signals/strategy-mode/", views.strategy_mode_analysis, name="strategy_mode_analysis"),
    path("profile/favorite/toggle/", views.toggle_favorite_api, name="toggle_favorite_api"),
    path("profile/alerts/update/", views.update_alert_preferences_api, name="update_alert_preferences_api"),
    path("profile/alerts/test/", views.send_test_alert_api, name="send_test_alert_api"),
]

