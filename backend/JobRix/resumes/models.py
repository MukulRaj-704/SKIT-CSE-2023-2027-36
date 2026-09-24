"""
resumes/models.py
=================
Resume storage plus the ATS results computed from it.

The heavy lifting belongs to the ``resume_parser`` engine
(``Backend/resume_parser``): a document is parsed **once** into a
``ParsedResume`` and that structure is stored on ``Resume.parsed_data``. Every
later feature - ATS scoring today, interview questions tomorrow - reads the
stored structure, so the PDF is never parsed twice.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _


def resume_upload_path(instance, filename):
    """Store uploads as ``resumes/<user_id>/<uuid>.pdf`` (never trust the name)."""
    suffix = Path(filename).suffix.lower() or ".pdf"
    return f"resumes/{instance.user_id}/{uuid.uuid4().hex}{suffix}"


class ParseStatus(models.TextChoices):
    """Lifecycle of the single parse attached to a resume."""

    PENDING = "pending", _("Pending")
    PARSED = "parsed", _("Parsed")
    FAILED = "failed", _("Failed")


class Resume(models.Model):
    """A job seeker's uploaded resume and the parse of that document."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="resumes",
        verbose_name=_("owner"),
    )
    title = models.CharField(_("title"), max_length=150, blank=True)
    file = models.FileField(
        _("file"),
        upload_to=resume_upload_path,
        max_length=255,
        help_text=_("PDF resume, stored under MEDIA_ROOT/resumes/<user id>/."),
    )
    original_filename = models.CharField(
        _("original filename"), max_length=255, blank=True
    )
    file_size = models.PositiveIntegerField(_("file size (bytes)"), default=0)
    content_type = models.CharField(_("content type"), max_length=100, blank=True)
    is_default = models.BooleanField(
        _("default resume"),
        default=False,
        help_text=_("At most one default resume per account."),
    )
    is_active = models.BooleanField(_("active"), default=True)

    parse_status = models.CharField(
        _("parse status"),
        max_length=16,
        choices=ParseStatus.choices,
        default=ParseStatus.PENDING,
    )
    parse_error = models.TextField(_("parse error"), blank=True)
    parsed_data = models.JSONField(
        _("parsed data"),
        default=dict,
        blank=True,
        help_text=_("The ParsedResume returned by the engine, stored as JSON."),
    )
    parsed_at = models.DateTimeField(_("parsed at"), null=True, blank=True)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("resume")
        verbose_name_plural = _("resumes")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default=True),
                name="unique_default_resume_per_user",
            )
        ]

    def __str__(self):
        return f"{self.title or self.original_filename or self.pk} ({self.user_id})"

    def save(self, *args, **kwargs):
        """Keep ``is_default`` exclusive per account, whatever the write path."""
        if self.is_default and self.user_id:
            with transaction.atomic():
                Resume.objects.filter(user_id=self.user_id, is_default=True).exclude(
                    pk=self.pk
                ).update(is_default=False)
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

    # -- convenience accessors used by the serializers ---------------------
    @property
    def parsed_contact(self) -> dict:
        return self.parsed_data.get("contact") or {}

    @property
    def skill_names(self) -> list:
        return [
            skill.get("name")
            for skill in self.parsed_data.get("skills") or []
            if skill.get("name")
        ]

    @property
    def parsed_summary(self) -> dict:
        """Small digest for list responses (the full parse stays on detail)."""
        return {
            "name": self.parsed_contact.get("name"),
            "email": self.parsed_contact.get("email"),
            "skills_count": len(self.skill_names),
            "education_count": len(self.parsed_data.get("education") or []),
            "experience_count": len(self.parsed_data.get("experience") or []),
            "projects_count": len(self.parsed_data.get("projects") or []),
            "certifications_count": len(self.parsed_data.get("certifications") or []),
        }


class ATSAnalysis(models.Model):
    """One ATS scoring run: a resume against one job description."""

    resume = models.ForeignKey(
        Resume,
        on_delete=models.CASCADE,
        related_name="ats_analyses",
        verbose_name=_("resume"),
    )
    job_title = models.CharField(_("job title"), max_length=200, blank=True)
    job_description = models.TextField(_("job description"))
    score = models.FloatField(
        _("score"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_("0-100, produced by the ATS scorer."),
    )
    keyword_coverage = models.FloatField(
        _("keyword coverage"),
        default=0.0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text=_("Fraction of the job description keywords found in the resume."),
    )
    matched_skills = models.JSONField(_("matched skills"), default=list, blank=True)
    missing_skills = models.JSONField(_("missing skills"), default=list, blank=True)
    suggestions = models.JSONField(_("suggestions"), default=list, blank=True)
    engine_version = models.CharField(_("engine version"), max_length=50, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("ATS analysis")
        verbose_name_plural = _("ATS analyses")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["resume", "-created_at"])]

    def __str__(self):
        return f"ATS {self.score} for resume {self.resume_id}"
