"""
analyzer/urls.py - mounted at ``/api/analyzer/`` by ``JobRix/urls.py``.

The prefix keeps this module clear of the existing ``/api/resumes/`` routes
(login-based, owned by another module).
"""

from django.urls import path

from . import views

app_name = "analyzer_api"

urlpatterns = [
    path("resumes/upload/", views.ResumeUploadView.as_view(), name="resume_upload"),
    path("resumes/<uuid:pk>/", views.ResumeDetailView.as_view(), name="resume_detail"),
    path("analyze/resume/", views.AnalyzeResumeView.as_view(), name="analyze_resume"),
    path("analyze/job/", views.AnalyzeJobView.as_view(), name="analyze_job"),
    path("analysis/<uuid:pk>/", views.AnalysisDetailView.as_view(), name="analysis_detail"),
]
