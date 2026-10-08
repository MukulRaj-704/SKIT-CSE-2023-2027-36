"""App configuration for ``jobs``."""

from django.apps import AppConfig


class JobsConfig(AppConfig):
    """Wires the ``jobs`` app (job postings + applications)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "jobs"
    verbose_name = "Jobs & Applications"
