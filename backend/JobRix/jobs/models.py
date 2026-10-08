"""
jobs/models.py
==============
Job postings and the applications they receive.

The two rows close the product loop opened by ``accounts`` (roles) and
``resumes`` (parse-once + ATS scoring):

* a recruiter publishes a ``Job``;
* a job seeker applies with one of their parsed ``Resume`` rows;
* applying scores the *stored* parse against ``Job.requirements`` with the same
  engine behind ``/api/resumes/<id>/ats/`` - the PDF is never re-read - the
  score is snapshotted on the ``Application`` and the full run is kept as a
  ``resumes.ATSAnalysis`` row (linked, so the resume's analysis history shows
  it too).

Applications are unique per (job, resume); the ranked candidate list of a job
is simply its applications ordered by ``ats_score`` descending.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class JobType(models.TextChoices):
    """Employment type of a posting (free-form enough for v1)."""

    FULL_TIME = "full_time", _("Full time")
    PART_TIME = "part_time", _("Part time")
    CONTRACT = "contract", _("Contract")
    INTERNSHIP = "internship", _("Internship")


class ApplicationStatus(models.TextChoices):
    """Lifecycle of an application, from submit to the final decision."""

    SUBMITTED = "submitted", _("Submitted")
    SCREENING = "screening", _("Screening")
    INTERVIEW = "interview", _("Interview")
    OFFER = "offer", _("Offer")
    REJECTED = "rejected", _("Rejected")
    WITHDRAWN = "withdrawn", _("Withdrawn")


class Job(models.Model):
    """One job posting created by a recruiter."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="jobs_posted",
        verbose_name=_("created by"),
        help_text=_("Recruiter who published the job."),
    )
    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs",
        verbose_name=_("company"),
        help_text=_("Stamped from the recruiter's profile on creation."),
    )
    title = models.CharField(_("title"), max_length=200)
    location = models.CharField(_("location"), max_length=120, blank=True)
    job_type = models.CharField(
        _("job type"),
        max_length=20,
        choices=JobType.choices,
        default=JobType.FULL_TIME,
    )
    salary_range = models.CharField(
        _("salary range"),
        max_length=50,
        blank=True,
        help_text=_("Free-form, e.g. 'INR 12-18 LPA'."),
    )
    description = models.TextField(_("description"))
    requirements = models.TextField(
        _("requirements"),
        help_text=_(
            "The pasted job description; doubles as the text the ATS scorer "
            "matches candidate resumes against."
        ),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Closed (inactive) jobs stop accepting applications."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("job")
        verbose_name_plural = _("jobs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "-created_at"]),
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.company or self.created_by})"



class Application(models.Model):
    """A seeker applying to a job with one specific resume, plus its ATS score."""

    job = models.ForeignKey(
        Job,
        on_delete=models.CASCADE,
        related_name="applications",
        verbose_name=_("job"),
    )
    resume = models.ForeignKey(
        "resumes.Resume",
        on_delete=models.CASCADE,
        related_name="applications",
        verbose_name=_("resume"),
        help_text=_("The parsed resume the applicant submitted."),
    )
    seeker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="applications",
        verbose_name=_("applicant"),
        help_text=_("Denormalised copy of ``resume.user`` (always the caller)."),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.SUBMITTED,
    )
    message = models.TextField(
        _("message"), blank=True, help_text=_("Optional cover note from the seeker.")
    )
    ats_score = models.FloatField(
        _("ATS score"),
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text=_(
            "Snapshot of the engine score for this resume against the job's "
            "requirements (0-100)."
        ),
    )
    ats_analysis = models.ForeignKey(
        "resumes.ATSAnalysis",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applications",
        verbose_name=_("ATS analysis"),
        help_text=_("The full scoring run behind ``ats_score``."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("application")
        verbose_name_plural = _("applications")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "resume"],
                name="unique_application_per_job_resume",
            )
        ]
        indexes = [
            models.Index(fields=["seeker", "-created_at"]),
            models.Index(fields=["job", "-ats_score"]),
        ]

    def __str__(self):
        return f"{self.seeker} -> {self.job}"
