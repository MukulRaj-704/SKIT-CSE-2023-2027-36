"""
resumes/urls.py
===============
API URLConf for the ``resumes`` app, mounted at ``/api/resumes/`` by
``JobRix/urls.py``. View classes live in ``resumes/views.py``.
"""

from django.urls import path

from . import views

app_name = "resumes_api"

urlpatterns = [
    path("", views.ResumeListCreateView.as_view(), name="resume_list"),
    path("<int:pk>/", views.ResumeDetailView.as_view(), name="resume_detail"),
    path(
        "<int:pk>/reparse/",
        views.ResumeReparseView.as_view(),
        name="resume_reparse",
    ),
    path(
        "<int:resume_pk>/ats/",
        views.ATSAnalysisListCreateView.as_view(),
        name="ats_list",
    ),
    path(
        "<int:resume_pk>/ats/<int:pk>/",
        views.ATSAnalysisDetailView.as_view(),
        name="ats_detail",
    ),
]
