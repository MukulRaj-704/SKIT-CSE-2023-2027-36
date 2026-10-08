"""
jobs/permissions.py
===================
Object-level guard for ``Job`` rows.

The platform-level role guards live in ``accounts/permissions.py`` and are
reused by the jobs views (``IsRecruiter`` for posting / candidate lists,
``IsJobSeeker`` for applying / my applications). What only this app needs is
the "who may modify this posting" rule:

* reads are open to every authenticated account (a job board is public to
  signed-in users, including closed postings behind their detail URL);
* writes are limited to the recruiter who posted the job - platform
  administrators bypass the check, everyone else is rejected with 403.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsJobOwner(BasePermission):
    """Write access to a ``Job`` limited to its creator (admins bypass)."""

    message = "Only the recruiter who posted this job can modify it."

    def has_permission(self, request, view):
        # Belt and suspenders: object checks only run for signed-in users.
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if user.is_platform_admin:
            return True
        return getattr(obj, "created_by_id", None) == user.pk
