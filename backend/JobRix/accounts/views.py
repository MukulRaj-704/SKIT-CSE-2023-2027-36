"""
accounts/views.py
=================
DRF **generic views** for authentication and for account / profile management.

The views are deliberately thin: serializers own validation and persistence
(``accounts/serializers.py``), permissions own authorization
(``accounts/permissions.py``). Everything here is wired at ``/api/accounts/``
(see ``accounts/urls.py``).

Authentication scheme
---------------------
* ``rest_framework.authentication.TokenAuthentication`` for API clients
  (``Authorization: Token <key>``).
* ``rest_framework.authentication.SessionAuthentication`` for the DRF browsable
  API (developer convenience only - the product UI is a separate React app).

Authorization is *deny by default*: ``REST_FRAMEWORK`` in ``JobRix/settings.py``
sets ``IsAuthenticated`` as the project wide default, and every open endpoint
(register / login / password reset) opts out explicitly with ``AllowAny``.
"""

from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from .models import Company, RecruiterProfile, SeekerProfile
from .permissions import (
    IsJobSeeker,
    IsOwnerOrReadOnly,
    IsPlatformAdmin,
    IsRecruiter,
    IsRecruiterOrReadOnly,
)
from .serializers import (
    AdminUserSerializer,
    CompanySerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RecruiterProfileSerializer,
    RegisterSerializer,
    SeekerProfileSerializer,
    TokenSerializer,
    UserSerializer,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
class RegisterView(generics.CreateAPIView):
    """
    ``POST /api/accounts/register/`` - open to everyone.

    Only the job seeker and recruiter roles can be requested, and the response
    already contains the API token so a new client can call the API right away.
    """

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, _ = Token.objects.get_or_create(user=user)
        headers = self.get_success_headers(serializer.data)
        return Response(
            TokenSerializer({"token": token.key, "user": user}).data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class LoginView(generics.CreateAPIView):
    """
    ``POST /api/accounts/login/`` - open to everyone.

    Exchanges email + password (checked by ``LoginSerializer``) for a DRF token.
    The response is ``{"token": "...", "user": {...}}``.
    """

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.save()
        return Response(
            TokenSerializer({"token": token.key, "user": token.user}).data,
            status=status.HTTP_200_OK,
        )


class LogoutView(generics.GenericAPIView):
    """``POST /api/accounts/logout/`` - revokes the caller's API token."""

    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "You have been logged out."}, status=status.HTTP_200_OK
        )


class MeView(generics.RetrieveUpdateAPIView):
    """
    ``GET|PUT|PATCH /api/accounts/me/`` - the caller's own account.

    ``email``, ``role`` and ``is_active`` are read only, so this endpoint can
    never be used to escalate privileges.
    """

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class PasswordChangeView(generics.GenericAPIView):
    """``POST /api/accounts/password/change/`` - for the signed in account."""

    serializer_class = PasswordChangeSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Your password has been updated."}, status=status.HTTP_200_OK
        )


class PasswordResetRequestView(generics.GenericAPIView):
    """``POST /api/accounts/password/reset/`` - emails a reset link."""

    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "detail": "If an account exists for that email address, a "
                "password reset link has been sent."
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(generics.GenericAPIView):
    """``POST /api/accounts/password/reset/confirm/`` - consumes uid + token."""

    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Your password has been reset."}, status=status.HTTP_200_OK
        )


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------
class SeekerProfileView(generics.RetrieveUpdateAPIView):
    """
    ``GET|PUT|PATCH /api/accounts/seeker-profile/`` - own candidate profile.

    Role guard: only job seeker accounts get here (administrators included).
    """

    serializer_class = SeekerProfileSerializer
    permission_classes = [IsAuthenticated, IsJobSeeker]

    def get_object(self):
        profile, _ = SeekerProfile.objects.get_or_create(user=self.request.user)
        self.check_object_permissions(self.request, profile)
        return profile


class SeekerProfileListView(generics.ListAPIView):
    """``GET /api/accounts/seekers/`` - recruiters and admins browse candidates."""

    serializer_class = SeekerProfileSerializer
    permission_classes = [IsAuthenticated, IsRecruiter | IsPlatformAdmin]
    queryset = SeekerProfile.objects.select_related("user")
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = [
        "headline",
        "location",
        "user__first_name",
        "user__last_name",
        "user__email",
    ]
    ordering_fields = ["years_of_experience", "created_at", "updated_at"]
    ordering = ["-updated_at"]


class RecruiterProfileView(generics.RetrieveUpdateAPIView):
    """
    ``GET|PUT|PATCH /api/accounts/recruiter-profile/`` - own recruiter profile.

    ``is_verified`` is read only; administrators flip it through the admin site.
    """

    serializer_class = RecruiterProfileSerializer
    permission_classes = [IsAuthenticated, IsRecruiter]

    def get_object(self):
        profile, _ = RecruiterProfile.objects.get_or_create(user=self.request.user)
        self.check_object_permissions(self.request, profile)
        return profile


class RecruiterProfileListView(generics.ListAPIView):
    """``GET /api/accounts/recruiters/`` - platform administrators only."""

    serializer_class = RecruiterProfileSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    queryset = RecruiterProfile.objects.select_related("user", "company")
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["job_title", "user__email", "company__name"]
    ordering_fields = ["created_at", "updated_at"]
    ordering = ["-updated_at"]


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------
class CompanyListCreateView(generics.ListCreateAPIView):
    """``GET|POST /api/accounts/companies/``.

    Any authenticated account may list companies; only recruiters (and
    administrators) may create them - see ``IsRecruiterOrReadOnly``.
    """

    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated, IsRecruiterOrReadOnly]
    queryset = Company.objects.select_related("owner")
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["name", "location", "description"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    def perform_create(self, serializer):
        # The owner always comes from the authenticated request and never from
        # the payload, so nobody can create a company for someone else.
        serializer.save(owner=self.request.user)


class CompanyDetailView(generics.RetrieveUpdateDestroyAPIView):
    """``GET|PUT|PATCH|DELETE /api/accounts/companies/<id>/``.

    Object level guard: readable by any authenticated account, writable by the
    owning recruiter (or an administrator) only - see ``IsOwnerOrReadOnly``.
    """

    serializer_class = CompanySerializer
    permission_classes = [IsAuthenticated, IsOwnerOrReadOnly]
    queryset = Company.objects.select_related("owner")


# ---------------------------------------------------------------------------
# Administration
# ---------------------------------------------------------------------------
class AdminUserListView(generics.ListAPIView):
    """``GET /api/accounts/users/`` - paginated account list for admins."""

    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    queryset = User.objects.all()
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["email", "first_name", "last_name", "phone"]
    ordering_fields = ["date_joined", "email", "role"]
    ordering = ["-date_joined"]


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """``GET|PUT|PATCH|DELETE /api/accounts/users/<id>/`` - administrators only.

    This is the only endpoint able to change ``role`` / ``is_active`` /
    ``is_staff``, which is what makes role changes administrator driven.
    """

    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    queryset = User.objects.all()

    def perform_destroy(self, instance):
        if instance == self.request.user:
            raise PermissionDenied("You cannot delete your own account.")
        instance.delete()