"""
jobs/tests/test_jobs.py
=======================
``/api/jobs/`` - who may post, what each role sees, and the edit rules.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Company

from ..models import Job
from .base import JOB_PAYLOAD, JobsAPIMixin, list_rows


class JobPostingTests(JobsAPIMixin, APITestCase):
    """Posting lifecycle + the role/object matrix around it."""

    def setUp(self):
        self.seeker = self.make_user("seeker@example.com")
        self.recruiter = self.make_recruiter("recruiter@example.com")
        self.other_recruiter = self.make_recruiter("other@example.com")

    def test_recruiter_creates_a_job_and_company_is_stamped(self):
        company = Company.objects.create(name="Acme Corp", owner=self.recruiter)
        profile = self.recruiter.recruiter_profile
        profile.company = company
        profile.save(update_fields=["company", "updated_at"])

        self.authenticate(self.recruiter)
        response = self.client.post(
            reverse("jobs_api:job_list"), JOB_PAYLOAD, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        job = Job.objects.get(pk=response.data["id"])
        self.assertEqual(job.created_by, self.recruiter)
        self.assertEqual(job.company, company)
        self.assertTrue(job.is_active)
        self.assertEqual(response.data["company_name"], "Acme Corp")
        self.assertEqual(response.data["created_by_name"], self.recruiter.full_name)
        self.assertEqual(response.data["applications_count"], 0)

    def test_seeker_cannot_create_a_job(self):
        self.authenticate(self.seeker)
        response = self.client.post(
            reverse("jobs_api:job_list"), JOB_PAYLOAD, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Job.objects.count(), 0)

    def test_anonymous_cannot_list_or_create_jobs(self):
        self.assertEqual(
            self.client.get(reverse("jobs_api:job_list")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            self.client.post(
                reverse("jobs_api:job_list"), JOB_PAYLOAD, format="json"
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(Job.objects.count(), 0)

    def test_short_requirements_are_rejected(self):
        # Requirements double as the ATS scoring text - same 30-char floor.
        self.authenticate(self.recruiter)
        response = self.client.post(
            reverse("jobs_api:job_list"),
            {**JOB_PAYLOAD, "requirements": "Python"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("requirements", response.data)
        self.assertEqual(Job.objects.count(), 0)

    def test_seeker_list_shows_only_active_jobs(self):
        active = self.make_job(self.recruiter)
        self.make_job(self.recruiter, is_active=False)
        other = self.make_job(self.other_recruiter, title="Data Engineer")

        self.authenticate(self.seeker)
        response = self.client.get(reverse("jobs_api:job_list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in list_rows(response)]
        self.assertIn(active.pk, ids)
        self.assertIn(other.pk, ids)
        self.assertEqual(len(ids), 2)  # the closed posting stays hidden

    def test_recruiter_list_shows_own_jobs_including_closed(self):
        own_open = self.make_job(self.recruiter)
        own_closed = self.make_job(self.recruiter, is_active=False)
        self.make_job(self.other_recruiter)

        self.authenticate(self.recruiter)
        response = self.client.get(reverse("jobs_api:job_list"))
        ids = [row["id"] for row in list_rows(response)]

        self.assertEqual(sorted(ids), sorted([own_open.pk, own_closed.pk]))

    def test_seeker_reads_any_job_but_cannot_edit_it(self):
        job = self.make_job(self.recruiter)
        self.authenticate(self.seeker)
        detail = reverse("jobs_api:job_detail", args=[job.pk])

        # Board reads are open to members...
        self.assertEqual(self.client.get(detail).status_code, status.HTTP_200_OK)
        # ...writes are owner only.
        self.assertEqual(
            self.client.patch(detail, {"title": "Hacked"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.delete(detail).status_code, status.HTTP_403_FORBIDDEN
        )
        job.refresh_from_db()
        self.assertNotEqual(job.title, "Hacked")

    def test_other_recruiter_cannot_edit_foreign_job(self):
        job = self.make_job(self.recruiter)
        self.authenticate(self.other_recruiter)
        detail = reverse("jobs_api:job_detail", args=[job.pk])

        self.assertEqual(
            self.client.get(detail).status_code, status.HTTP_200_OK
        )  # reads stay open
        self.assertEqual(
            self.client.patch(detail, {"title": "Mine now"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.delete(detail).status_code, status.HTTP_403_FORBIDDEN
        )
        job.refresh_from_db()
        self.assertEqual(job.title, JOB_PAYLOAD["title"])

    def test_owner_can_update_and_close_then_reopen(self):
        job = self.make_job(self.recruiter)
        self.authenticate(self.recruiter)
        detail = reverse("jobs_api:job_detail", args=[job.pk])

        response = self.client.patch(
            detail, {"title": "Senior Backend Engineer"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["title"], "Senior Backend Engineer")
        self.assertEqual(response.data["company"], job.company_id)

        self.assertEqual(
            self.client.patch(detail, {"is_active": False}, format="json").status_code,
            status.HTTP_200_OK,
        )
        job.refresh_from_db()
        self.assertFalse(job.is_active)

        # Closed postings drop off the seeker board again.
        self.authenticate(self.seeker)
        board = self.client.get(reverse("jobs_api:job_list"))
        self.assertEqual([row["id"] for row in list_rows(board)], [])

    def test_owner_can_delete_a_job(self):
        job = self.make_job(self.recruiter)
        self.authenticate(self.recruiter)
        detail = reverse("jobs_api:job_detail", args=[job.pk])

        self.assertEqual(
            self.client.delete(detail).status_code, status.HTTP_204_NO_CONTENT
        )
        self.assertEqual(
            self.client.get(detail).status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertEqual(Job.objects.count(), 0)

    def test_anonymous_detail_is_unauthorized(self):
        job = self.make_job(self.recruiter)
        self.client.credentials()  # drop the recruiter token set by make_job
        response = self.client.get(reverse("jobs_api:job_detail", args=[job.pk]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

