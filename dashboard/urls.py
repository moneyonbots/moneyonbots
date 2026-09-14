from django.urls import path
from django.shortcuts import redirect

from . import views
from analysis.views import live_signals_page, performance_page

urlpatterns = [
    path("", views.index, name="dashboard_index"),
    path("signals/", live_signals_page, name="live_signals"),
    path("performance/", performance_page, name="performance_page"),
    path("profile/", views.profile_view, name="user_profile"),
]
