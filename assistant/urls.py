from django.urls import path

from . import views

urlpatterns = [
    path("chat/", views.chat, name="ai_chat"),
    path("chat/history/", views.chat_history, name="ai_chat_history"),
    path("speak/", views.speak, name="ai_speak"),
    path("transcribe/", views.transcribe, name="ai_transcribe"),
    path("analyze/", views.analyze, name="ai_analyze"),
    path("chart-analysis/", views.chart_analysis, name="ai_chart_analysis"),
    path("news/", views.news_api, name="ai_news"),
]
