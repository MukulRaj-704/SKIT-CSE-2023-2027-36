"""App configuration for ``analyzer`` (resume analysis -> ATS score -> job matching)."""

from django.apps import AppConfig


class AnalyzerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analyzer"
    verbose_name = "Resume Analyzer"
