"""
accounts/signals.py
===================
Keeps exactly one profile per account.

Creating an account and creating its role specific profile must never be two
separate steps for the caller, otherwise the profile endpoints would randomly
404. The receiver is connected from ``AccountsConfig.ready()``.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import RecruiterProfile, Role, SeekerProfile, User


@receiver(post_save, sender=User, dispatch_uid="accounts.create_role_profile")
def create_role_profile(sender, instance, created, **kwargs):
    """Give every new job seeker / recruiter the matching profile row."""
    if not created:
        return
    if instance.role == Role.RECRUITER:
        RecruiterProfile.objects.get_or_create(user=instance)
    elif instance.role == Role.JOB_SEEKER:
        SeekerProfile.objects.get_or_create(user=instance)