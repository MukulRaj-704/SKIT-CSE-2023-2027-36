from django.urls import path

from .views import (
    CompleteResumeJobAnalysisView,
    JobMatchAnalysisDetailView,
)

app_name = "mukul_ai"

urlpatterns = [
    path(
        "analyze/",
        CompleteResumeJobAnalysisView.as_view(),
        name="analyze",
    ),
    path(
        "results/<int:pk>/",
        JobMatchAnalysisDetailView.as_view(),
        name="result",
    ),
]
