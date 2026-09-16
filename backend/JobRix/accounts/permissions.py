"""
accounts/permissions.py
=======================
Every authorization rule of the accounts API lives here, so the views only ever
declare *which* guard they use (``permission_classes = [...]``).

Two families of guards exist:

* ``has_permission`` guards (role / platform level) - May this kind of account
  call this endpoint at all?
* ``has_object_permission`` guards (object level) - May this account touch this
  particular row?
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Role


class HasRole(BasePermission):
    """
    Base guard: allow the request when the account holds one of ``allowed_roles``.

    Platform administrators bypass the role check on purpose - they can inspect
    every resource - and unauthenticated requests are always rejected, even when
    the view is decorated with ``AllowAny`` elsewhere.
    """

    message = "Your account role is not allowed to perform this action."
    allowed_roles = ()

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        if user.is_platform_admin:
            return True
        return user.role in self.allowed_roles


class IsJobSeeker(HasRole):
    """Job seeker (candidate) accounts only."""

    message = "Only job seeker accounts can perform this action."
    allowed_roles = (Role.JOB_SEEKER,)


class IsRecruiter(HasRole):
    """Recruiter accounts only."""

    message = "Only recruiter accounts can perform this action."
    allowed_roles = (Role.RECRUITER,)


class IsPlatformAdmin(BasePermission):
    """Django staff / superuser accounts, or accounts carrying ``Role.ADMIN``."""

    message = "Only platform administrators can perform this action."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_platform_admin)


class IsOwnerOrReadOnly(BasePermission):
    """
    Object level guard: authenticated accounts may read, only the owner (or an
    administrator) may write. The owner attribute is configurable so the guard
    can be reused by future apps (jobs, applications, ...).
    """

    message = "Only the owner of this object can modify it."
    owner_field = "owner"

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_platform_admin:
            return True
        owner = getattr(obj, self.owner_field, None)
        return owner is not None and owner == user


class IsRecruiterOrReadOnly(BasePermission):
    """Authenticated read for everyone, create/update for recruiters and admins."""

    message = "Only recruiter accounts can create or update companies."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        return user.is_platform_admin or user.role == Role.RECRUITER