"""
resumes/permissions.py
======================
Role + object permissions for the resume / ATS endpoints.

Complements the project wide defaults in ``JobRix.settings.REST_FRAMEWORK``:
the defaults already deny anonymous requests and expose ``SAFE_METHODS`` to
staff/superusers, so these classes only add the resume specific rules:

* ``IsJobSeeker``          - only job seekers may touch their resumes.
* ``IsResumeOwner``        - object level guard on ``Resume`` / ``ATSAnalysis``.

Actual row scoping still happens in each view's ``get_queryset()`` (queries are
always filtered by ``request.user``), which makes cross-account access a 404
before this permission is ever consulted. This class is the belt to that
suspenders: it keeps future detail views safe even if someone forgets to scope
the queryset.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Resume


class IsJobSeeker(BasePermission):
    """Allow only authenticated job seekers (admin/staff are handled globally)."""

    message = "Only job seeker accounts can manage resumes."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_platform_admin or user.is_job_seeker)
        )


class IsResumeOwner(BasePermission):
    """Object access limited to the seeker who owns the resume (read: owner/admin)."""

    message = "You can only access your own resumes."

    @staticmethod
    def _owner(obj) -> object | None:
        if isinstance(obj, Resume):
            return obj.user
        # ATSAnalysis and anything else reached through a resume.
        return getattr(obj, "resume", None) and obj.resume.user

    def has_object_permission(self, request, view, obj) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_platform_admin:
            return True
        owner = self._owner(obj)
        if owner is None:
            return False
        if request.method in SAFE_METHODS:
            return owner.pk == user.pk
        # Writes need the job-seeker role as well (mirrors IsJobSeeker).
        return owner.pk == user.pk and user.is_job_seeker
