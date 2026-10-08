"""
jobs/admin.py
=============
Read-mostly admin for postings and applications. Rows are produced by the API
(recruiter posts a job, seeker applies and the engine scores), so admin mainly
browses them; the one write action is moving an application through its
statuses (``status`` is the only editable field on ``Application``).
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Application, Job


class ApplicationInline(admin.TabularInline):
    """Applications of one posting, ranked by score like the API does."""

    model = Application
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("seeker", "resume", "status", "ats_score", "created_at")
    readonly_fields = ("seeker", "resume", "ats_score", "created_at")
    ordering = ("-ats_score", "-created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """Job postings with a count and the applications inline."""

    list_display = (
        "id",
        "title",
        "company",
        "created_by",
        "job_type",
        "is_active",
        "applications_count",
        "created_at",
    )
    list_filter = ("job_type", "is_active", "created_at")
    search_fields = (
        "title",
        "description",
        "requirements",
        "location",
        "company__name",
        "created_by__email",
    )
    ordering = ("-created_at",)
    inlines = [ApplicationInline]
    readonly_fields = ("created_by", "company", "created_at", "updated_at")
    fieldsets = (
        (
            _("Posting"),
            {
                "fields": (
                    ("title", "job_type"),
                    ("location", "salary_range"),
                    "description",
                    "requirements",
                    "is_active",
                )
            },
        ),
        (
            _("Ownership"),
            {"fields": (("created_by", "company"),), "classes": ("collapse",)},
        ),
        (
            _("Timestamps"),
            {
                "fields": (("created_at", "updated_at"),),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description=_("Applications"))
    def applications_count(self, obj) -> int:
        return obj.applications.count()


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    """Applications - status editable, everything else produced by the API."""

    list_display = (
        "id",
        "job",
        "seeker",
        "status",
        "ats_score",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("seeker__email", "job__title", "job__company__name")
    ordering = ("-created_at",)
    readonly_fields = (
        "job",
        "resume",
        "seeker",
        "message",
        "ats_score",
        "ats_analysis",
        "created_at",
        "updated_at",
    )
