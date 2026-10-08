"""
jobs/tests/test_applications.py
===============================
``POST /api/jobs/<id>/apply/`` (the score-once flow) plus the application
lists and the status machine.
"""

from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from resumes.models import ATSAnalysis, ParseStatus, Resume
from resumes.services import ResumeEngineError

from ..models import Application, ApplicationStatus
from .base import JobsAPIMixin, list_rows, make_parsed_resume


class ApplyTests(JobsAPIMixin, APITestCase):
    """Apply: role gates, conflict rules and the persisted score."""

    def setUp(self):
        self.recruiter = self.make_recruiter("recruiter@example.com")
        self.job = self.make_job(self.recruiter)
        self.seeker = self.make_user("seeker@example.com")
        self.resume = make_parsed_resume(self.seeker)

    def test_apply_scores_and_persists_everything(self):
        response = self.apply(self.seeker, self.job.pk, self.resume, message="Hi!")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        application = Application.objects.get(pk=response.data["id"])
        self.assertEqual(application.job, self.job)
        self.assertEqual(application.resume, self.resume)
        self.assertEqual(application.seeker, self.seeker)
        self.assertEqual(application.status, ApplicationStatus.SUBMITTED)
        self.assertEqual(application.message, "Hi!")
        # Score snapshot + the full run kept on the resume's analysis history.
        self.assertIsNotNone(application.ats_score)
        self.assertGreaterEqual(application.ats_score, 0)
        self.assertLessEqual(application.ats_score, 100)
        analysis = application.ats_analysis
        self.assertEqual(analysis.resume, self.resume)
        self.assertEqual(analysis.job_title, self.job.title)
        self.assertEqual(analysis.job_description, self.job.requirements)
        self.assertEqual(analysis.score, application.ats_score)
        self.assertTrue(response.data["matched_skills"])
        self.assertEqual(response.data["job_title"], "Backend Engineer")
        self.assertEqual(response.data["seeker_email"], self.seeker.email)
        self.assertEqual(Application.objects.filter(job=self.job).count(), 1)

    def test_duplicate_application_is_409(self):
        first = self.apply(self.seeker, self.job.pk, self.resume)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.apply(self.seeker, self.job.pk, self.resume)

        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Application.objects.count(), 1)

    def test_closed_job_answers_409(self):
        closed = self.make_job(self.recruiter, title="Closed role", is_active=False)

        response = self.apply(self.seeker, closed.pk, self.resume)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Application.objects.count(), 0)

    def test_missing_job_answers_404(self):
        response = self.apply(self.seeker, 999999, self.resume)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_foreign_resume_answers_404(self):
        other = self.make_user("other-seeker@example.com")
        their_resume = make_parsed_resume(other)

        response = self.apply(self.seeker, self.job.pk, their_resume)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Application.objects.count(), 0)

    def test_unknown_resume_pk_answers_400(self):
        self.authenticate(self.seeker)
        response = self.client.post(
            reverse("jobs_api:job_apply", args=[self.job.pk]),
            {"resume": 999999},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unparsed_resume_answers_409(self):
        raw = Resume.objects.create(
            user=self.seeker, title="Raw upload", parse_status=ParseStatus.PENDING
        )

        response = self.apply(self.seeker, self.job.pk, raw)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Application.objects.count(), 0)

    def test_recruiter_cannot_apply(self):
        self.authenticate(self.recruiter)
        response = self.client.post(
            reverse("jobs_api:job_apply", args=[self.job.pk]),
            {"resume": self.resume.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Application.objects.count(), 0)

    def test_anonymous_apply_is_unauthorized(self):
        self.client.credentials()  # drop the recruiter token set by make_job
        response = self.client.post(
            reverse("jobs_api:job_apply", args=[self.job.pk]),
            {"resume": self.resume.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_engine_failure_answers_503_and_creates_nothing(self):
        with patch(
            "jobs.views.score_application",
            side_effect=ResumeEngineError("scorer exploded"),
        ):
            response = self.apply(self.seeker, self.job.pk, self.resume)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(Application.objects.count(), 0)
        self.assertEqual(ATSAnalysis.objects.count(), 0)

    def test_apply_accepts_an_optional_cover_note_only(self):
        response = self.apply(
            self.seeker, self.job.pk, self.resume, message="Pick me", status="offer"
        )
        # Extra payload keys beyond (resume, message) are ignored - the status
        # can never be chosen by the applicant.
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        application = Application.objects.get(pk=response.data["id"])
        self.assertEqual(application.status, ApplicationStatus.SUBMITTED)


class ApplicationListAndStatusTests(JobsAPIMixin, APITestCase):
    """Ranked candidate list, my-applications scoping, the status machine."""

    def setUp(self):
        self.recruiter = self.make_recruiter("recruiter@example.com")
        self.other_recruiter = self.make_recruiter("other@example.com")
        self.job = self.make_job(self.recruiter)
        self.seeker1 = self.make_user("one@example.com")
        self.seeker2 = self.make_user("two@example.com")
        resume1 = make_parsed_resume(self.seeker1)
        resume2 = make_parsed_resume(self.seeker1, title="Resume two")
        resume3 = make_parsed_resume(self.seeker2)
        self.app1 = Application.objects.create(
            job=self.job, resume=resume1, seeker=self.seeker1, ats_score=80.0
        )
        self.app2 = Application.objects.create(
            job=self.job, resume=resume2, seeker=self.seeker1, ats_score=45.0
        )
        self.app3 = Application.objects.create(
            job=self.job, resume=resume3, seeker=self.seeker2
        )  # unscored row: must sort last

    def test_candidate_list_is_ranked_by_score(self):
        self.authenticate(self.recruiter)
        response = self.client.get(
            reverse("jobs_api:job_applications", args=[self.job.pk])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in list_rows(response)]
        self.assertEqual(ids, [self.app1.pk, self.app2.pk, self.app3.pk])

    def test_candidate_list_is_forbidden_or_hidden_from_others(self):
        url = reverse("jobs_api:job_applications", args=[self.job.pk])

        self.authenticate(self.seeker1)  # wrong role for the candidate list
        self.assertEqual(
            self.client.get(url).status_code, status.HTTP_403_FORBIDDEN
        )

        self.authenticate(self.other_recruiter)  # right role, someone else's job
        self.assertEqual(
            self.client.get(url).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_my_applications_is_scoped_to_each_seeker(self):
        self.authenticate(self.seeker1)
        response = self.client.get(reverse("jobs_api:application_list"))
        self.assertEqual(
            {row["id"] for row in list_rows(response)},
            {self.app1.pk, self.app2.pk},
        )

        self.authenticate(self.seeker2)
        response = self.client.get(reverse("jobs_api:application_list"))
        self.assertEqual(
            [row["id"] for row in list_rows(response)], [self.app3.pk]
        )

    def test_application_detail_visibility_matrix(self):
        def detail(app):
            return reverse("jobs_api:application_detail", args=[app.pk])

        self.authenticate(self.seeker1)
        self.assertEqual(
            self.client.get(detail(self.app1)).status_code, status.HTTP_200_OK
        )
        self.assertEqual(
            self.client.get(detail(self.app3)).status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.authenticate(self.recruiter)
        self.assertEqual(
            self.client.get(detail(self.app1)).status_code, status.HTTP_200_OK
        )

        self.authenticate(self.other_recruiter)
        self.assertEqual(
            self.client.get(detail(self.app1)).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_recruiter_moves_application_through_statuses(self):
        self.authenticate(self.recruiter)
        url = reverse("jobs_api:application_detail", args=[self.app1.pk])

        response = self.client.patch(
            url, {"status": ApplicationStatus.INTERVIEW}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.app1.refresh_from_db()
        self.assertEqual(self.app1.status, ApplicationStatus.INTERVIEW)
        # PATCH answers with the full projection, not the single-field one.
        self.assertEqual(response.data["job_title"], self.job.title)
        self.assertIn("ats_score", response.data)

        bad = self.client.patch(url, {"status": "bogus"}, format="json")
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_recruiter_of_another_job_cannot_update(self):
        self.authenticate(self.other_recruiter)
        response = self.client.patch(
            reverse("jobs_api:application_detail", args=[self.app1.pk]),
            {"status": ApplicationStatus.OFFER},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.app1.refresh_from_db()
        self.assertEqual(self.app1.status, ApplicationStatus.SUBMITTED)

    def test_seeker_may_only_withdraw_their_own_application(self):
        url = reverse("jobs_api:application_detail", args=[self.app1.pk])
        self.authenticate(self.seeker1)

        advanced = self.client.patch(
            url, {"status": ApplicationStatus.INTERVIEW}, format="json"
        )
        self.assertEqual(advanced.status_code, status.HTTP_400_BAD_REQUEST)

        withdrawn = self.client.patch(
            url, {"status": ApplicationStatus.WITHDRAWN}, format="json"
        )
        self.assertEqual(withdrawn.status_code, status.HTTP_200_OK, withdrawn.data)
        self.app1.refresh_from_db()
        self.assertEqual(self.app1.status, ApplicationStatus.WITHDRAWN)

    def test_seeker_cannot_touch_someone_elses_application(self):
        self.authenticate(self.seeker2)
        response = self.client.patch(
            reverse("jobs_api:application_detail", args=[self.app1.pk]),
            {"status": ApplicationStatus.WITHDRAWN},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_application_endpoints_require_auth(self):
        self.client.credentials()  # drop the recruiter token set by make_job
        self.assertEqual(
            self.client.get(reverse("jobs_api:application_list")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            self.client.get(
                reverse("jobs_api:application_detail", args=[self.app1.pk])
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


