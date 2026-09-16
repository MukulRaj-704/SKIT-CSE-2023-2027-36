"""
accounts/admin.py
=================
Django admin for the email based account model and the profile models.

``UserAdmin`` is subclassed because Django's stock admin assumes a ``username``
field (see ``accounts/forms.py``). Role, ``is_active``, ``is_staff`` and
``RecruiterProfile.is_verified`` are all editable here, which makes the admin
site the second place - next to ``/api/accounts/users/`` - where privileges and
verification flags can be granted.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .forms import AdminUserChangeForm, AdminUserCreationForm
from .models import Company, RecruiterProfile, SeekerProfile, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for the email based JobRix account."""

    form = AdminUserChangeForm
    add_form = AdminUserCreationForm

    ordering = ("email",)
    list_display = ("email", "full_name", "role", "is_active", "is_staff", "date_joined")
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    search_fields = ("email", "first_name", "last_name", "phone")
    readonly_fields = ("last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal information", {"fields": ("first_name", "last_name", "phone")}),
        (
            "Role & permissions",
            {
                "fields": (
                    "role",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "phone",
                    "role",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "location", "created_at")
    search_fields = ("name", "owner__email", "location")
    list_select_related = ("owner",)
    ordering = ("name",)


@admin.register(SeekerProfile)
class SeekerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "headline",
        "location",
        "years_of_experience",
        "is_open_to_work",
        "updated_at",
    )
    list_filter = ("is_open_to_work",)
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "headline",
        "location",
    )
    list_select_related = ("user",)


@admin.register(RecruiterProfile)
class RecruiterProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "job_title", "is_verified", "updated_at")
    list_filter = ("is_verified", "company")
    search_fields = ("user__email", "job_title", "company__name")
    list_select_related = ("user", "company")