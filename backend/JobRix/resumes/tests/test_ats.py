"""
resumes/tests/test_ats.py
=========================
``/api/resumes/<id>/ats/``: scoring persistence, guards and permissions.
"""

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role

from resumes.models import ATSAnalysis, ParseStatus, Resume

from .base import JOB_DESCRIPTION, TEST_MEDIA_ROOT, ResumeAPIMixin, resume_upload


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, RESUME_PARSE_SPACY=False)
class ATSAnalysisTests(ResumeAPIMixin, APITestCase):
    """Score a stored parse; the PDF must never be read again."""

    def setUp(self):
        self.seeker = self.make_user("seeker@example.com")
        self.other = self.make_user("other@example.com")
        self.recruiter = self.make_user("recruiter@example.com", role=Role.RECRUITER)
        upload = self.upload_resume(self.seeker)
        self.resume = Resume.objects.get(pk=upload.data["id"])
        self.assertEqual(self.resume.parse_status, ParseStatus.PARSED)
        self.ats_url = reverse("resumes_api:ats_list", args=[self.resume.pk])

    def score(self, **extra):
        payload = {"job_description": JOB_DESCRIPTION}
        payload.update(extra)
        return self.client.post(self.ats_url, payload, format="json")

    def test_scoring_persists_score_matched_missing_and_suggestions(self):
        self.authenticate(self.seeker)
        response = self.score(job_title="Backend Engineer")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(0 <= response.data["score"] <= 100, response.data["score"])
        self.assertEqual(response.data["job_title"], "Backend Engineer")
        self.assertTrue(response.data["engine_version"])
        self.assertTrue(0 <= response.data["keyword_coverage"] <= 1)
        self.assertIsInstance(response.data["suggestions"], list)

        matched = {item.lower() for item in response.data["matched_skills"]}
        missing = {item.lower() for item in response.data["missing_skills"]}
        self.assertTrue({"python", "django"} <= matched, matched)
        self.assertIn("kubernetes", missing, missing)

        analysis = ATSAnalysis.objects.get(pk=response.data["id"])
        self.assertEqual(analysis.resume, self.resume)
        self.assertEqual(analysis.job_description, JOB_DESCRIPTION)
        self.assertEqual(analysis.score, response.data["score"])
        self.assertEqual(analysis.engine_version, response.data["engine_version"])

        # analyses are listed back for the owner, and readable in detail
        listing = self.client.get(self.ats_url)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data["count"], 1)
        detail = self.client.get(
            reverse("resumes_api:ats_detail", args=[self.resume.pk, analysis.pk])
        )
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["score"], analysis.score)

    def test_scoring_never_re_reads_the_pdf(self):
        """Remove the stored file: scoring still works from Resume.parsed_data."""
        self.resume.file.delete(save=False)

        self.authenticate(self.seeker)
        response = self.score()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertGreater(
            len(response.data["matched_skills"]) + len(response.data["missing_skills"]),
            0,
        )

    def test_unparsed_resume_answers_409(self):
        pending = Resume.objects.create(
            user=self.seeker,
            title="Not parsed",
            file=resume_upload(),
            parse_status=ParseStatus.PENDING,
        )
        self.authenticate(self.seeker)
        response = self.client.post(
            reverse("resumes_api:ats_list", args=[pending.pk]),
            {"job_description": JOB_DESCRIPTION},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("detail", response.data)
        self.assertEqual(ATSAnalysis.objects.count(), 0)

    def test_short_or_missing_job_description_is_rejected(self):
        self.authenticate(self.seeker)
        short = self.score(job_description="too short")
        self.assertEqual(short.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("job_description", short.data)

        missing = self.client.post(self.ats_url, {}, format="json")
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ATSAnalysis.objects.count(), 0)

    def test_recruiter_is_forbidden_and_other_seeker_gets_404(self):
        self.authenticate(self.recruiter)
        self.assertEqual(self.score().status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.other)
        self.assertEqual(self.score().status_code, status.HTTP_404_NOT_FOUND)
        listing = self.client.get(self.ats_url)
        self.assertEqual(listing.status_code, status.HTTP_404_NOT_FOUND)

        self.assertEqual(ATSAnalysis.objects.count(), 0)
