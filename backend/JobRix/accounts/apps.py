"""App configuration for ``accounts``."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Wires the ``accounts`` app, including its signal receivers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
    verbose_name = "Accounts & Authentication"

    def ready(self):
        # Importing the module registers the receivers that keep one profile per
        # account in sync (see accounts/signals.py).
        from . import signals  # noqa: F401