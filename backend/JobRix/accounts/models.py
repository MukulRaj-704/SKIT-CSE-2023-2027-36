"""
accounts/models.py
==================
Identity, roles and profiles for the JobRix platform.

Authentication is email based (``USERNAME_FIELD = "email"``): an account is an
email + password pair plus exactly one *role*, and that role drives every
authorization decision on the platform:

* ``Role.JOB_SEEKER`` - candidate running the resume / ATS / interview flows
* ``Role.RECRUITER``  - recruiter publishing jobs and evaluating candidates
* ``Role.ADMIN``      - platform administrator (never self assignable)

``role`` is read only on the self service API (see ``accounts/serializers.py``)
so a signed in user can never escalate their own privileges.
"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    """Every account holds exactly one role; the guards live in permissions.py."""

    JOB_SEEKER = "job_seeker", _("Job Seeker")
    RECRUITER = "recruiter", _("Recruiter")
    ADMIN = "admin", _("Administrator")

    @classmethod
    def self_assignable_choices(cls):
        """The (value, label) pairs a visitor may pick when signing up."""
        return [
            (value, label)
            for value, label in cls.choices
            if value in (cls.JOB_SEEKER, cls.RECRUITER)
        ]


class UserManager(BaseUserManager):
    """
    Custom manager required because ``email`` replaces ``username`` as the
    login identifier (``AbstractUser`` still ships the username based manager).
    """

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """Create a regular account (defaults to the job seeker role)."""
        extra_fields.setdefault("role", Role.JOB_SEEKER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        """Create a platform administrator (used by ``createsuperuser``)."""
        extra_fields.setdefault("role", Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)

    def create_job_seeker(self, email, password=None, **extra_fields):
        """Explicit intent version of ``create_user`` for candidates."""
        extra_fields["role"] = Role.JOB_SEEKER
        return self.create_user(email, password, **extra_fields)

    def create_recruiter(self, email, password=None, **extra_fields):
        """Explicit intent version of ``create_user`` for recruiters."""
        extra_fields["role"] = Role.RECRUITER
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    JobRix account. ``username`` is removed, ``email`` is the login identifier
    and ``role`` is the single source of truth for authorization.
    """

    username = None

    email = models.EmailField(_("email address"), unique=True)
    phone = models.CharField(_("phone number"), max_length=20, blank=True)
    role = models.CharField(
        _("role"),
        max_length=20,
        choices=Role.choices,
        default=Role.JOB_SEEKER,
        help_text=_("Drives every permission check in the platform."),
    )

    objects = UserManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        # Emails are stored lower case so ``email`` lookups never have to be
        # case aware (registration, login and password reset all match on it).
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        """Display name, falling back to the email address."""
        return self.get_full_name() or self.email

    @property
    def is_job_seeker(self):
        return self.role == Role.JOB_SEEKER

    @property
    def is_recruiter(self):
        return self.role == Role.RECRUITER

    @property
    def is_platform_admin(self):
        """``True`` for the admin role and for Django staff/superusers."""
        return bool(self.is_staff or self.is_superuser or self.role == Role.ADMIN)

    @property
    def company(self):
        """Company attached to a recruiter account, ``None`` for everyone else."""
        profile = getattr(self, "recruiter_profile", None)
        return profile.company if profile else None


class Company(models.Model):
    """A company owned by the recruiter who created it."""

    name = models.CharField(_("name"), max_length=200, unique=True)
    website = models.URLField(_("website"), blank=True)
    location = models.CharField(_("location"), max_length=120, blank=True)
    description = models.TextField(_("description"), blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_companies",
        verbose_name=_("owner"),
        help_text=_("Recruiter who created the company."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("company")
        verbose_name_plural = _("companies")
        ordering = ["name"]

    def __str__(self):
        return self.name


class SeekerProfile(models.Model):
    """
    Candidate profile. The resume / ATS / interview features hang off this
    object, which mirrors the contact information extracted by the resume
    parser (see Backend/resume_parser).
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seeker_profile",
        verbose_name=_("user"),
    )
    headline = models.CharField(_("headline"), max_length=150, blank=True)
    bio = models.TextField(_("bio"), blank=True)
    location = models.CharField(_("location"), max_length=120, blank=True)
    phone = models.CharField(_("phone number"), max_length=20, blank=True)
    years_of_experience = models.PositiveSmallIntegerField(
        _("years of experience"), default=0
    )
    linkedin_url = models.URLField(_("LinkedIn URL"), blank=True)
    github_url = models.URLField(_("GitHub URL"), blank=True)
    portfolio_url = models.URLField(_("portfolio URL"), blank=True)
    is_open_to_work = models.BooleanField(_("open to work"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("job seeker profile")
        verbose_name_plural = _("job seeker profiles")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.full_name} ({self.headline or 'no headline'})"


class RecruiterProfile(models.Model):
    """Recruiter profile, optionally attached to a company."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recruiter_profile",
        verbose_name=_("user"),
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recruiters",
        verbose_name=_("company"),
    )
    job_title = models.CharField(_("job title"), max_length=150, blank=True)
    phone = models.CharField(_("phone number"), max_length=20, blank=True)
    is_verified = models.BooleanField(
        _("verified"),
        default=False,
        help_text=_("Only platform administrators can change this flag."),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("recruiter profile")
        verbose_name_plural = _("recruiter profiles")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.full_name} @ {self.company or 'no company'}"