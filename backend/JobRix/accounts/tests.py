"""
accounts/tests.py
=================
Authentication / authorization test suite for the ``accounts`` app.

Coverage:

* registration, login, logout, token handling and password flows of the DRF API
* role and object level authorization (job seeker vs recruiter vs admin)
* the password reset link that is emailed to (and consumed by) the React frontend
* the Django admin, which uses the custom email based user model

Run with::

    cd backend/JobRix
    ../.venv/bin/python manage.py test accounts -v 2
"""

import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Company, RecruiterProfile, Role, SeekerProfile
from .serializers import PasswordResetConfirmSerializer

User = get_user_model()

# Passwords used by the suite (they must satisfy AUTH_PASSWORD_VALIDATORS).
PASSWORD = "JobRix-Auth-Pass-2026"
NEW_PASSWORD = "JobRix-Auth-New-2026"
WEAK_PASSWORD = "12345"


class AccountApiMixin:
    """Helpers shared by the API test cases."""

    def register(
        self,
        email,
        password=PASSWORD,
        role=Role.JOB_SEEKER,
        first_name="Test",
        last_name="User",
        **extra,
    ):
        payload = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "password": password,
            "password_confirm": password,
            "role": role,
        }
        payload.update(extra)
        return self.client.post(
            reverse("accounts_api:register"), payload, format="json"
        )

    def login(self, email, password=PASSWORD):
        return self.client.post(
            reverse("accounts_api:login"),
            {"email": email, "password": password},
            format="json",
        )

    def authenticate(self, user):
        """Send ``Authorization: Token <key>`` for ``user``."""
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return token

    def make_user(self, email, role=Role.JOB_SEEKER, password=PASSWORD, **extra):
        return User.objects.create_user(
            email=email, password=password, role=role, **extra
        )


class RegistrationTests(AccountApiMixin, APITestCase):
    """``POST /api/accounts/register/``."""

    def test_job_seeker_registration_returns_token_and_user(self):
        response = self.register("seeker@example.com")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["role"], Role.JOB_SEEKER)
        self.assertEqual(response.data["user"]["email"], "seeker@example.com")
        self.assertTrue(Token.objects.filter(user__email="seeker@example.com").exists())
        # The role profile must exist right away (post_save receiver).
        self.assertTrue(
            SeekerProfile.objects.filter(user__email="seeker@example.com").exists()
        )

    def test_recruiter_registration_creates_owned_company_and_profile(self):
        response = self.register(
            "recruiter@example.com",
            role=Role.RECRUITER,
            company_name="JobRix Labs",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="recruiter@example.com")
        self.assertEqual(user.role, Role.RECRUITER)

        profile = RecruiterProfile.objects.get(user=user)
        self.assertEqual(profile.company.name, "JobRix Labs")
        self.assertEqual(profile.company.owner, user)

    def test_admin_role_cannot_be_self_assigned(self):
        response = self.register("sneaky@example.com", role=Role.ADMIN)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)
        self.assertFalse(User.objects.filter(email="sneaky@example.com").exists())

    def test_recruiter_registration_requires_company_name(self):
        response = self.register("recruiter@example.com", role=Role.RECRUITER)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("company_name", response.data)

    def test_password_confirmation_must_match(self):
        response = self.client.post(
            reverse("accounts_api:register"),
            {
                "email": "seeker@example.com",
                "password": PASSWORD,
                "password_confirm": PASSWORD + "-different",
                "role": Role.JOB_SEEKER,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    def test_weak_password_is_rejected(self):
        response = self.register("seeker@example.com", password=WEAK_PASSWORD)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_duplicate_email_is_rejected(self):
        self.register("seeker@example.com")
        response = self.register("SEEKER@example.com")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertEqual(User.objects.filter(email="seeker@example.com").count(), 1)


class LoginLogoutTests(AccountApiMixin, APITestCase):
    """``POST /api/accounts/login/`` and ``POST /api/accounts/logout/``."""

    def setUp(self):
        self.user = self.make_user("seeker@example.com")

    def test_login_returns_token_and_user(self):
        response = self.login("seeker@example.com")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["email"], "seeker@example.com")
        self.assertEqual(response.data["token"], Token.objects.get(user=self.user).key)

    def test_login_is_case_insensitive_on_email(self):
        response = self.login("SEEKER@example.com")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_with_wrong_password_is_rejected(self):
        response = self.login("seeker@example.com", password="wrong-password-123")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_with_inactive_account_is_rejected(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.login("seeker@example.com")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_revokes_the_token(self):
        token = self.authenticate(self.user)

        response = self.client.post(reverse("accounts_api:logout"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

        # The revoked token no longer authenticates.
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(
            self.client.get(reverse("accounts_api:me")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_logout_requires_authentication(self):
        response = self.client.post(reverse("accounts_api:logout"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class MeEndpointTests(AccountApiMixin, APITestCase):
    """``GET|PATCH /api/accounts/me/``."""

    def setUp(self):
        self.user = self.make_user(
            "seeker@example.com", first_name="Meera", last_name="Nair"
        )

    def test_me_requires_authentication(self):
        response = self.client.get(reverse("accounts_api:me"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_the_authenticated_account(self):
        self.authenticate(self.user)

        response = self.client.get(reverse("accounts_api:me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "seeker@example.com")
        self.assertEqual(response.data["full_name"], "Meera Nair")
        self.assertNotIn("password", response.data)

    def test_me_can_update_own_profile_fields(self):
        self.authenticate(self.user)

        response = self.client.patch(
            reverse("accounts_api:me"), {"first_name": "Meera R"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Meera R")

    def test_me_cannot_escalate_role_or_reactivate_a_disabled_account(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.authenticate(self.user)

        # TokenAuthentication refuses to authenticate an inactive account.
        self.assertEqual(
            self.client.get(reverse("accounts_api:me")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        response = self.client.patch(
            reverse("accounts_api:me"),
            {"role": Role.ADMIN, "is_staff": True, "email": "root@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, Role.JOB_SEEKER)
        self.assertFalse(self.user.is_staff)
        self.assertEqual(self.user.email, "seeker@example.com")


class PasswordFlowTests(AccountApiMixin, APITestCase):
    """``password/change/`` and ``password/reset/`` endpoints."""

    def setUp(self):
        self.user = self.make_user("seeker@example.com")

    def test_password_change_updates_the_password(self):
        self.authenticate(self.user)

        response = self.client.post(
            reverse("accounts_api:password_change"),
            {
                "old_password": PASSWORD,
                "new_password": NEW_PASSWORD,
                "new_password_confirm": NEW_PASSWORD,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

        # The new credentials work against the login endpoint.
        self.client.credentials()
        self.assertEqual(
            self.login("seeker@example.com", NEW_PASSWORD).status_code,
            status.HTTP_200_OK,
        )

    def test_password_change_rejects_a_wrong_current_password(self):
        self.authenticate(self.user)

        response = self.client.post(
            reverse("accounts_api:password_change"),
            {
                "old_password": "not-my-password",
                "new_password": NEW_PASSWORD,
                "new_password_confirm": NEW_PASSWORD,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("old_password", response.data)

    def test_password_change_requires_authentication(self):
        response = self.client.post(
            reverse("accounts_api:password_change"),
            {
                "old_password": PASSWORD,
                "new_password": NEW_PASSWORD,
                "new_password_confirm": NEW_PASSWORD,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_reset_request_emails_a_link_to_the_frontend(self):
        response = self.client.post(
            reverse("accounts_api:password_reset"),
            {"email": "seeker@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("JobRix password", mail.outbox[0].subject)

        # The email links to the React app with a ready to use uid/token pair.
        body = mail.outbox[0].body
        self.assertIn(settings.FRONTEND_URL, body)

        match = re.search(r"uid=(?P<uid>[^&\s]+)&token=(?P<token>[^&\s]+)", body)
        self.assertIsNotNone(match, msg=body)

        # ... and that pair is exactly what the confirm endpoint expects.
        confirm = self.client.post(
            reverse("accounts_api:password_reset_confirm"),
            {
                "uid": match.group("uid"),
                "token": match.group("token"),
                "new_password": NEW_PASSWORD,
                "new_password_confirm": NEW_PASSWORD,
            },
            format="json",
        )

        self.assertEqual(confirm.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_password_reset_request_does_not_reveal_unknown_accounts(self):
        response = self.client.post(
            reverse("accounts_api:password_reset"),
            {"email": "nobody@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_confirm_sets_password_and_revokes_tokens(self):
        token = self.authenticate(self.user)
        uid, reset_token = PasswordResetConfirmSerializer.build_uid_and_token(self.user)
        self.client.credentials()

        response = self.client.post(
            reverse("accounts_api:password_reset_confirm"),
            {
                "uid": uid,
                "token": reset_token,
                "new_password": NEW_PASSWORD,
                "new_password_confirm": NEW_PASSWORD,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        # Every previously issued token is revoked by the reset.
        self.assertFalse(Token.objects.filter(user=self.user).exists())

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(
            self.client.get(reverse("accounts_api:me")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_password_reset_confirm_rejects_an_invalid_token(self):
        uid, _ = PasswordResetConfirmSerializer.build_uid_and_token(self.user)

        response = self.client.post(
            reverse("accounts_api:password_reset_confirm"),
            {
                "uid": uid,
                "token": "not-a-real-token",
                "new_password": NEW_PASSWORD,
                "new_password_confirm": NEW_PASSWORD,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token", response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))


class ProfileAuthorizationTests(AccountApiMixin, APITestCase):
    """Role guards on the profile and candidate browsing endpoints."""

    def setUp(self):
        self.seeker = self.make_user("seeker@example.com", role=Role.JOB_SEEKER)
        self.recruiter = self.make_user("recruiter@example.com", role=Role.RECRUITER)
        self.admin = self.make_user("admin@example.com", role=Role.ADMIN)

    def test_seeker_profile_is_created_automatically(self):
        self.assertTrue(SeekerProfile.objects.filter(user=self.seeker).exists())
        self.assertTrue(RecruiterProfile.objects.filter(user=self.recruiter).exists())

    def test_job_seeker_reads_and_updates_own_candidate_profile(self):
        self.authenticate(self.seeker)

        response = self.client.patch(
            reverse("accounts_api:seeker_profile"),
            {"headline": "Backend Engineer", "years_of_experience": 3},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # The endpoint only ever exposes the caller's own profile.
        self.assertEqual(response.data["email"], "seeker@example.com")
        profile = SeekerProfile.objects.get(user=self.seeker)
        self.assertEqual(profile.headline, "Backend Engineer")

    def test_recruiter_cannot_use_the_seeker_profile_endpoint(self):
        self.authenticate(self.recruiter)

        response = self.client.get(reverse("accounts_api:seeker_profile"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_job_seeker_cannot_use_the_recruiter_profile_endpoint(self):
        self.authenticate(self.seeker)

        response = self.client.get(reverse("accounts_api:recruiter_profile"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_recruiter_updates_own_profile_but_not_the_verified_flag(self):
        self.authenticate(self.recruiter)

        response = self.client.patch(
            reverse("accounts_api:recruiter_profile"),
            {"job_title": "Talent Lead", "is_verified": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        profile = RecruiterProfile.objects.get(user=self.recruiter)
        self.assertEqual(profile.job_title, "Talent Lead")
        # is_verified is administrator managed, it must be ignored here.
        self.assertFalse(profile.is_verified)

    def test_recruiter_can_browse_candidates(self):
        self.authenticate(self.recruiter)

        response = self.client.get(reverse("accounts_api:seeker_list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["email"], "seeker@example.com")

    def test_job_seeker_cannot_browse_candidates(self):
        self.authenticate(self.seeker)

        response = self.client.get(reverse("accounts_api:seeker_list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_recruiter_listing_is_administrator_only(self):
        self.authenticate(self.recruiter)
        self.assertEqual(
            self.client.get(reverse("accounts_api:recruiter_list")).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.authenticate(self.admin)
        self.assertEqual(
            self.client.get(reverse("accounts_api:recruiter_list")).status_code,
            status.HTTP_200_OK,
        )


class CompanyAuthorizationTests(AccountApiMixin, APITestCase):
    """Role and object level guards on the company endpoints."""

    def setUp(self):
        self.recruiter = self.make_user("recruiter@example.com", role=Role.RECRUITER)
        self.other_recruiter = self.make_user("other@example.com", role=Role.RECRUITER)
        self.seeker = self.make_user("seeker@example.com", role=Role.JOB_SEEKER)
        self.admin = self.make_user("admin@example.com", role=Role.ADMIN)
        self.company = Company.objects.create(name="JobRix Labs", owner=self.recruiter)

    def company_url(self, company=None):
        return reverse(
            "accounts_api:company_detail", args=[(company or self.company).pk]
        )

    def test_company_creation_uses_the_authenticated_account_as_owner(self):
        self.authenticate(self.other_recruiter)

        response = self.client.post(
            reverse("accounts_api:company_list"),
            {"name": "Acme Hiring", "owner": self.seeker.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Company.objects.get(name="Acme Hiring").owner, self.other_recruiter
        )

    def test_job_seeker_cannot_create_a_company(self):
        self.authenticate(self.seeker)

        response = self.client.post(
            reverse("accounts_api:company_list"), {"name": "Nope"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Company.objects.filter(name="Nope").exists())

    def test_authenticated_accounts_can_list_companies(self):
        self.authenticate(self.seeker)

        response = self.client.get(reverse("accounts_api:company_list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_unauthenticated_access_to_companies_is_rejected(self):
        self.assertEqual(
            self.client.get(reverse("accounts_api:company_list")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            self.client.get(self.company_url()).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_only_the_owner_can_update_a_company(self):
        self.authenticate(self.other_recruiter)
        response = self.client.patch(
            self.company_url(), {"location": "Remote"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.recruiter)
        response = self.client.patch(
            self.company_url(), {"location": "Bengaluru"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.company.refresh_from_db()
        self.assertEqual(self.company.location, "Bengaluru")

    def test_administrator_can_update_any_company(self):
        self.authenticate(self.admin)

        response = self.client.patch(
            self.company_url(), {"description": "Hiring platform"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Company.objects.get(pk=self.company.pk).description, "Hiring platform"
        )

    def test_recruiter_count_reports_attached_recruiters(self):
        profile = self.recruiter.recruiter_profile
        profile.company = self.company
        profile.save(update_fields=["company", "updated_at"])

        self.authenticate(self.seeker)
        response = self.client.get(self.company_url())

        self.assertEqual(response.data["recruiter_count"], 1)


class AdministrationTests(AccountApiMixin, APITestCase):
    """Administrator only account management endpoints."""

    def setUp(self):
        self.admin = self.make_user("admin@example.com", role=Role.ADMIN, is_staff=True)
        self.seeker = self.make_user("seeker@example.com", role=Role.JOB_SEEKER)
        self.recruiter = self.make_user("recruiter@example.com", role=Role.RECRUITER)

    def user_url(self, user=None):
        return reverse("accounts_api:user_detail", args=[(user or self.seeker).pk])

    def test_user_listing_requires_an_administrator(self):
        self.assertEqual(
            self.client.get(reverse("accounts_api:user_list")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        for account in (self.seeker, self.recruiter):
            self.authenticate(account)
            self.assertEqual(
                self.client.get(reverse("accounts_api:user_list")).status_code,
                status.HTTP_403_FORBIDDEN,
            )

        self.authenticate(self.admin)
        response = self.client.get(reverse("accounts_api:user_list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)

    def test_administrator_can_change_a_role_and_deactivate_an_account(self):
        self.authenticate(self.admin)

        response = self.client.patch(
            self.user_url(),
            {"role": Role.RECRUITER, "is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.seeker.refresh_from_db()
        self.assertEqual(self.seeker.role, Role.RECRUITER)
        self.assertFalse(self.seeker.is_active)

    def test_administrator_cannot_deactivate_or_demote_their_own_account(self):
        self.authenticate(self.admin)

        response = self.client.patch(
            self.user_url(self.admin), {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_active", response.data)

        response = self.client.patch(
            self.user_url(self.admin), {"role": Role.JOB_SEEKER}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("role", response.data)

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.role, Role.ADMIN)

    def test_administrator_cannot_delete_their_own_account(self):
        self.authenticate(self.admin)

        response = self.client.delete(self.user_url(self.admin))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_administrator_can_delete_another_account(self):
        self.authenticate(self.admin)

        response = self.client.delete(self.user_url())

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(pk=self.seeker.pk).exists())

    def test_a_deactivated_account_loses_api_access(self):
        token = self.authenticate(self.seeker)
        self.authenticate(self.admin)
        self.client.patch(self.user_url(), {"is_active": False}, format="json")

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(
            self.client.get(reverse("accounts_api:me")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class AdminSiteTests(AccountApiMixin, APITestCase):
    """The Django admin must work with the email based user model."""

    def setUp(self):
        self.admin = self.make_user(
            "admin@example.com",
            role=Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_add_user_page_renders_without_a_username_field(self):
        response = self.client.get(reverse("admin:accounts_user_add"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'name="email"')
        self.assertNotContains(response, 'name="username"')

    def test_administrator_creates_an_account_through_the_admin(self):
        response = self.client.post(
            reverse("admin:accounts_user_add"),
            {
                "email": "recruiter@example.com",
                "first_name": "Rhea",
                "last_name": "Kapoor",
                "phone": "",
                "role": Role.RECRUITER,
                "password1": PASSWORD,
                "password2": PASSWORD,
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        user = User.objects.get(email="recruiter@example.com")
        self.assertEqual(user.role, Role.RECRUITER)
        self.assertTrue(user.check_password(PASSWORD))

    def test_change_user_page_renders_the_role_fieldset(self):
        response = self.client.get(
            reverse("admin:accounts_user_change", args=[self.admin.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, "Role &amp; permissions")

    def test_recruiter_can_be_verified_through_the_admin(self):
        recruiter = self.make_user("recruiter@example.com", role=Role.RECRUITER)

        response = self.client.post(
            reverse(
                "admin:accounts_recruiterprofile_change",
                args=[recruiter.recruiter_profile.pk],
            ),
            {
                "user": recruiter.pk,
                "company": "",
                "job_title": "Hiring Manager",
                "phone": "",
                "is_verified": "on",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        recruiter.recruiter_profile.refresh_from_db()
        self.assertTrue(recruiter.recruiter_profile.is_verified)