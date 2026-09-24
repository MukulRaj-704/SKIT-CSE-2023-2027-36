"""
accounts/urls.py
================
API URLConf for the ``accounts`` app, mounted at ``/api/accounts/`` by
``JobRix/urls.py``. View classes live in ``accounts/views.py``.
"""

from django.urls import path

from . import views

app_name = "accounts_api"

urlpatterns = [
    # -- authentication ----------------------------------------------------
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path(
        "password/change/",
        views.PasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "password/reset/",
        views.PasswordResetRequestView.as_view(),
        name="password_reset",
    ),
    path(
        "password/reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    # -- the signed in account ---------------------------------------------
    path("me/", views.MeView.as_view(), name="me"),
    # -- profiles ----------------------------------------------------------
    path(
        "seeker-profile/",
        views.SeekerProfileView.as_view(),
        name="seeker_profile",
    ),
    path(
        "recruiter-profile/",
        views.RecruiterProfileView.as_view(),
        name="recruiter_profile",
    ),
    path("seekers/", views.SeekerProfileListView.as_view(), name="seeker_list"),
    path(
        "recruiters/",
        views.RecruiterProfileListView.as_view(),
        name="recruiter_list",
    ),
    # -- companies ---------------------------------------------------------
    path("companies/", views.CompanyListCreateView.as_view(), name="company_list"),
    path(
        "companies/<int:pk>/",
        views.CompanyDetailView.as_view(),
        name="company_detail",
    ),
    # -- administration ----------------------------------------------------
    path("users/", views.AdminUserListView.as_view(), name="user_list"),
    path("users/<int:pk>/", views.AdminUserDetailView.as_view(), name="user_detail"),
]