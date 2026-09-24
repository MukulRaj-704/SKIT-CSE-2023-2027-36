"""
resumes/signals.py
==================
Removes the stored PDF when its ``Resume`` row disappears.

A ``post_delete`` receiver is used instead of overriding ``delete()`` because it
also fires for bulk deletions (``queryset.delete()``, admin bulk actions).
Connected from ``ResumesConfig.ready()``.
"""

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Resume


@receiver(post_delete, sender=Resume, dispatch_uid="resumes.delete_resume_file")
def delete_resume_file(sender, instance, **kwargs):
    """Delete the stored file after the row is gone (ignore storage errors)."""
    if not instance.file:
        return
    try:
        instance.file.delete(save=False)
    except Exception:  # pragma: no cover - storage specific
        # A missing/unreachable file must never break the delete request.
        pass