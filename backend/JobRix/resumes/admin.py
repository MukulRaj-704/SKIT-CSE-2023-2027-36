"""
resumes/admin.py
================
Read-mostly admin for resumes and ATS analyses.

Results are produced by the API (upload -> parse -> score), so admin mainly
browses them; the one write action is re-parsing a broken document.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import ATSAnalysis, Resume


class ATSAnalysisInline(admin.TabularInline):
    """Read-only history of ATS runs for a resume."""

    model = ATSAnalysis
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("job_title", "score", "keyword_coverage", "engine_version", "created_at")
    readonly_fields = fields
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    """Resume list with parse state and a bulk re-parse action."""

    list_display = (
        "id",
        "title",
        "user",
        "parse_status",
        "skills_count",
        "is_default",
        "created_at",
    )
    list_filter = ("parse_status", "is_default", "is_active", "created_at")
    search_fields = ("user__email", "user__full_name", "title", "original_filename")
    ordering = ("-created_at",)
    inlines = [ATSAnalysisInline]
    actions = ["reparse_selected"]
    readonly_fields = (
        "user",
        "file",
        "original_filename",
        "file_size",
        "content_type",
        "parse_status",
        "parse_error",
        "parsed_data",
        "parsed_at",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            _("Resume"),
            {"fields": (("title", "is_default", "is_active"), "file")},
        ),
        (
            _("Parse"),
            {"fields": (("parse_status", "parsed_at"), "parsed_data", "parse_error")},
        ),
        (
            _("Metadata"),
            {
                "fields": (
                    "user",
                    "original_filename",
                    "file_size",
                    "content_type",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description=_("Skills"))
    def skills_count(self, obj: Resume) -> int:
        return len(obj.skill_names)

    @admin.action(description=_("Re-parse selected resumes"))
    def reparse_selected(self, request, queryset):
        from .services import ResumeEngineError, parse_resume_instance

        parsed = failed = 0
        for resume in queryset:
            try:
                parse_resume_instance(resume)
                parsed += 1
            except ResumeEngineError:
                failed += 1
        self.message_user(
            request,
            f"Re-parsed {parsed} resume(s); {failed} failed (see parse_error).",
        )


@admin.register(ATSAnalysis)
class ATSAnalysisAdmin(admin.ModelAdmin):
    """Immutable results of ATS runs - browse/search only."""

    list_display = (
        "id",
        "resume",
        "job_title",
        "score",
        "keyword_coverage",
        "engine_version",
        "created_at",
    )
    list_filter = ("engine_version", "created_at")
    search_fields = (
        "job_title",
        "job_description",
        "resume__title",
        "resume__user__email",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "resume",
        "job_title",
        "job_description",
        "score",
        "keyword_coverage",
        "matched_skills",
        "missing_skills",
        "suggestions",
        "engine_version",
        "created_at",
    )

    def has_add_permission(self, request):
        return False
