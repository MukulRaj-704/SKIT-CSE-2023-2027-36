"""
jobs/urls.py
============
API URLConf for the ``jobs`` app. It is mounted at ``/api/`` by
``JobRix/urls.py`` (not ``/api/jobs/``) because the app serves two prefixes:

* ``/api/jobs/...``          postings, applying, candidate lists
* ``/api/applications/...``  the seeker's own applications + status updates

View classes live in ``jobs/views.py``.
"""

from django.urls import path

from . import views

app_name = "jobs_api"

urlpatterns = [
    path("jobs/", views.JobListCreateView.as_view(), name="job_list"),
    path("jobs/<int:pk>/", views.JobDetailView.as_view(), name="job_detail"),
    path(
        "jobs/<int:pk>/apply/",
        views.JobApplyView.as_view(),
        name="job_apply",
    ),
    path(
        "jobs/<int:pk>/applications/",
        views.JobApplicationsView.as_view(),
        name="job_applications",
    ),
    path(
        "applications/",
        views.ApplicationListView.as_view(),
        name="application_list",
    ),
    path(
        "applications/<int:pk>/",
        views.ApplicationDetailView.as_view(),
        name="application_detail",
    ),
]
