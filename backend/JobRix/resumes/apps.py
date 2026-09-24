"""App configuration for ``resumes``."""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ResumesConfig(AppConfig):
    """Wires the ``resumes`` app, its signals and the engine sanity check."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "resumes"
    verbose_name = "Resumes & ATS"

    def ready(self):
        # Keep one profile-like invariant: uploaded files are removed with their
        # row (see resumes/signals.py).
        from . import signals  # noqa: F401

        # Surface a broken/missing parsing engine at boot instead of on the
        # first resume upload.
        from .services import engine_status

        available, detail = engine_status()
        if available:
            logger.info("Resume parsing engine ready (%s).", detail)
        else:
            logger.warning(
                "Resume parsing engine unavailable (%s). Resume uploads will be "
                "stored but not parsed until it is installed.",
                detail,
            )