"""
accounts/serializers.py
=======================
The serializers behind the DRF generic views (``accounts/views.py``).

Validation, persistence and response shaping live here; authorization lives in
``accounts/permissions.py``. Notes on the security model:

* ``role`` (and ``is_staff`` / ``is_superuser`` / ``is_active``) are read only on
  the self service endpoints, so ``PATCH /api/accounts/me/`` can never be used to
  escalate privileges.
* ``Role.ADMIN`` cannot be picked at registration and can only be granted by an
  existing administrator through ``AdminUserSerializer``.
* Passwords go through Django's configured ``AUTH_PASSWORD_VALIDATORS`` via
  ``django.contrib.auth.password_validation.validate_password``.
"""

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, password_validation
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers
from rest_framework.authtoken.models import Token

from .models import Company, RecruiterProfile, Role, SeekerProfile

User = get_user_model()


# ---------------------------------------------------------------------------
# Account and profile serializers
# ---------------------------------------------------------------------------
class UserSerializer(serializers.ModelSerializer):
    """Public representation of an account (never exposes the password hash)."""

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "role",
            "is_active",
            "date_joined",
        ]
        read_only_fields = [
            "id",
            "email",
            "full_name",
            "role",
            "is_active",
            "date_joined",
        ]


class AdminUserSerializer(UserSerializer):
    """
    Administrator only view of an account: adds ``is_active`` / ``is_staff`` /
    ``is_superuser`` so roles can be granted and accounts disabled through
    ``/api/accounts/users/<id>/``.
    """

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["is_staff", "is_superuser", "last_login"]
        read_only_fields = ["id", "email", "full_name", "date_joined", "last_login"]

    def validate(self, attrs):
        """An administrator may not lock themselves out of their own account."""
        request = self.context.get("request")
        if request is None or self.instance is None or request.user != self.instance:
            return attrs

        if attrs.get("is_active") is False:
            raise serializers.ValidationError(
                {"is_active": "You cannot deactivate your own account."}
            )

        new_role = attrs.get("role")
        if new_role is not None and new_role != self.instance.role:
            raise serializers.ValidationError(
                {"role": "You cannot change your own role."}
            )
        return attrs


class CompanySerializer(serializers.ModelSerializer):
    """Company resource. ``owner`` comes from the request, it is never sent."""

    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    recruiter_count = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "website",
            "location",
            "description",
            "owner_email",
            "recruiter_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner_email",
            "recruiter_count",
            "created_at",
            "updated_at",
        ]

    def get_recruiter_count(self, obj):
        return obj.recruiters.count()


class SeekerProfileSerializer(serializers.ModelSerializer):
    """Candidate profile. The account itself is read only (see ``MeView``)."""

    user = UserSerializer(read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.full_name", read_only=True)

    class Meta:
        model = SeekerProfile
        fields = [
            "id",
            "user",
            "email",
            "full_name",
            "headline",
            "bio",
            "location",
            "phone",
            "years_of_experience",
            "linkedin_url",
            "github_url",
            "portfolio_url",
            "is_open_to_work",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "email", "full_name", "created_at", "updated_at"]


class RecruiterProfileSerializer(serializers.ModelSerializer):
    """Recruiter profile. ``is_verified`` is administrator managed."""

    user = UserSerializer(read_only=True)
    company = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(), required=False, allow_null=True
    )
    company_detail = CompanySerializer(source="company", read_only=True)

    class Meta:
        model = RecruiterProfile
        fields = [
            "id",
            "user",
            "company",
            "company_detail",
            "job_title",
            "phone",
            "is_verified",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "is_verified", "created_at", "updated_at"]

    def validate_company(self, company):
        """A recruiter may only attach themselves to a company they own."""
        if company is None:
            return company
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and (user.is_platform_admin or company.owner_id == user.id):
            return company
        raise serializers.ValidationError(
            "You can only join a company that you created."
        )


# ---------------------------------------------------------------------------
# Authentication serializers
# ---------------------------------------------------------------------------
class TokenSerializer(serializers.Serializer):
    """
    Read only payload returned by register / login.

    ``Token`` is DRF's ``rest_framework.authtoken`` token: clients send it back
    as ``Authorization: Token <key>``.
    """

    token = serializers.CharField(read_only=True)
    user = UserSerializer(read_only=True)


class RegisterSerializer(serializers.ModelSerializer):
    """
    ``POST /api/accounts/register/``.

    Creates a job seeker or a recruiter (nothing else) and, for recruiters,
    creates the company they own and attaches it to their profile.
    """

    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )
    password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )
    role = serializers.ChoiceField(
        choices=Role.self_assignable_choices(), default=Role.JOB_SEEKER
    )
    company_name = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Required when registering as a recruiter.",
    )

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "company_name",
            "password",
            "password_confirm",
        ]

    def validate_email(self, value):
        """Normalise the address and reject duplicates case insensitively."""
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "An account with this email address already exists."
            )
        return email

    def validate_password(self, value):
        """Run Django's configured ``AUTH_PASSWORD_VALIDATORS``."""
        password_validation.validate_password(value)
        return value

    def validate(self, attrs):
        password_confirm = attrs.pop("password_confirm")

        if attrs["password"] != password_confirm:
            raise serializers.ValidationError(
                {"password_confirm": "The two password fields did not match."}
            )

        if attrs.get("role") == Role.RECRUITER and not attrs.get("company_name"):
            raise serializers.ValidationError(
                {"company_name": "Recruiters must provide the name of their company."}
            )

        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        role = validated_data.pop("role", Role.JOB_SEEKER)
        company_name = validated_data.pop("company_name", "")

        user = User.objects.create_user(password=password, role=role, **validated_data)

        if role == Role.RECRUITER and company_name:
            company, _ = Company.objects.get_or_create(
                name=company_name, defaults={"owner": user}
            )
            profile, _ = RecruiterProfile.objects.get_or_create(user=user)
            profile.company = company
            profile.save(update_fields=["company", "updated_at"])

        return user


class LoginSerializer(serializers.Serializer):
    """
    ``POST /api/accounts/login/``.

    Credentials are checked with ``django.contrib.auth.authenticate`` so the
    configured authentication backends stay in charge. ``save()`` returns the
    DRF token that must be sent back in the ``Authorization`` header.
    """

    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )

    def validate(self, attrs):
        # ``username`` is the credential identifier for ModelBackend; our
        # USERNAME_FIELD is ``email``, hence ``username=<email>``.
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"].strip().lower(),
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError(
                {"detail": "No active account found with the given credentials."},
                code="authorization",
            )
        attrs["user"] = user
        return attrs

    def create(self, validated_data):
        token, _ = Token.objects.get_or_create(user=validated_data["user"])
        return token


class LogoutSerializer(serializers.Serializer):
    """
    ``POST /api/accounts/logout/``.

    Revokes the token of the authenticated account (the request itself is
    already authenticated, so there is nothing to validate).
    """

    def save(self, **kwargs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            Token.objects.filter(user=user).delete()
        return None


class PasswordChangeSerializer(serializers.Serializer):
    """``POST /api/accounts/password/change/`` for a signed in account."""

    old_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )
    new_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )
    new_password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Your current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "The two password fields did not match."}
            )
        password_validation.validate_password(
            attrs["new_password"], self.context["request"].user
        )
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    ``POST /api/accounts/password/reset/``.

    Emails a reset link that points at the React frontend
    (``FRONTEND_URL`` + ``/reset-password?uid=...&token=...``); the frontend then
    posts the ``uid`` / ``token`` pair to ``password/reset/confirm/``.

    The endpoint always answers 200, even for unknown emails, so it cannot be
    used to enumerate which accounts exist.
    """

    email = serializers.EmailField()

    def validate_email(self, value):
        return value.strip().lower()

    def save(self, **kwargs):
        request = self.context.get("request")
        form = PasswordResetForm(data={"email": self.validated_data["email"]})
        if form.is_valid():
            form.save(
                request=request,
                use_https=request.is_secure() if request else False,
                email_template_name="emails/password_reset_email.txt",
                subject_template_name="emails/password_reset_subject.txt",
                from_email=None,
                extra_email_context={"frontend_url": settings.FRONTEND_URL},
            )
        return None


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    ``POST /api/accounts/password/reset/confirm/``.

    Consumes the ``uid`` / ``token`` pair produced by Django's reset token
    generator, sets the new password and revokes every existing API token.
    """

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )
    new_password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "The two password fields did not match."}
            )

        try:
            user_id = urlsafe_base64_decode(attrs["uid"]).decode()
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError(
                {"uid": "This password reset link is invalid."}
            )

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError(
                {"token": "This password reset link is invalid or has expired."}
            )

        password_validation.validate_password(attrs["new_password"], user)
        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        # Old API clients must stop working once the password is reset.
        Token.objects.filter(user=user).delete()
        return user

    @staticmethod
    def build_uid_and_token(user):
        """Build the ``(uid, token)`` pair that is emailed to the user."""
        return (
            urlsafe_base64_encode(force_bytes(user.pk)),
            default_token_generator.make_token(user),
        )