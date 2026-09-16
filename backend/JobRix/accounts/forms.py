"""
accounts/forms.py
=================
Forms used by the Django admin for the email based user model.

The product UI is a separate React application that talks to the JSON API
(``accounts/serializers.py``), so there are no public HTML forms here - only the
admin ones, which Django's stock ``UserCreationForm`` / ``UserChangeForm``
cannot provide because they assume a ``username`` field.
"""

from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from .models import User


class AdminUserCreationForm(forms.ModelForm):
    """
    Admin "add user" form.

    Django's stock ``UserCreationForm`` is hard wired to a ``username`` field,
    which this user model does not have, so the admin needs this replacement.
    """

    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(
        label="Password confirmation", widget=forms.PasswordInput
    )

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone", "role"]

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The two password fields did not match.")

        if password1:
            try:
                password_validation.validate_password(password1)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class AdminUserChangeForm(forms.ModelForm):
    """Admin "change user" form with a read only password hash field."""

    password = ReadOnlyPasswordHashField(
        label="Password",
        help_text="Raw passwords are not stored, use the 'change password' form instead.",
    )

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        ]