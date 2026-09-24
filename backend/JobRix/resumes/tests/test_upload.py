"""
resumes/tests/test_upload.py
============================
``POST /api/resumes/``: the parse-once contract, file validation, role gates.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role

from resumes.models import ParseStatus, Resume

from .base import TEST_MEDIA_ROOT, ResumeAPIMixin, resume_upload


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, RESUME_PARSE_SPACY=False)
class ResumeUploadTests(ResumeAPIMixin, APITestCase):
    """Upload happy path plus the rejection matrix."""

    def setUp(self):
        self.seeker = self.make_user("seeker@example.com")
        self.recruiter = self.make_user("recruiter@example.com", role=Role.RECRUITER)

    def test_upload_parses_the_pdf_once_and_persists_everything(self):
        response = self.upload_resume(self.seeker)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        resume = Resume.objects.get(pk=response.data["id"])
        self.assertEqual(resume.user, self.seeker)
        # parse-once contract: the engine output lives on the row and the response
        self.assertEqual(resume.parse_status, ParseStatus.PARSED)
        self.assertEqual(response.data["parse_status"], ParseStatus.PARSED)
        self.assertTrue(resume.parsed_data)
        self.assertTrue(resume.parsed_at)
        self.assertEqual(
            response.data["parsed_summary"]["email"], "mukul.sharma@example.com"
        )
        self.assertTrue(response.data["skills"])
        self.assertGreaterEqual(response.data["parsed_summary"]["skills_count"], 1)
        # storage: server side path under the owner, original name kept aside
        self.assertTrue(resume.file.name.startswith(f"resumes/{self.seeker.pk}/"))
        self.assertEqual(resume.original_filename, "candidate_resume.pdf")
        self.assertEqual(resume.content_type, "application/pdf")
        self.assertGreater(resume.file_size, 0)
        # the seeker's first resume becomes the default automatically
        self.assertTrue(resume.is_default)
        self.assertEqual(response.data["title"], "candidate_resume")

    def test_non_pdf_file_is_rejected(self):
        self.authenticate(self.seeker)
        response = self.client.post(
            reverse("resumes_api:resume_list"),
            {
                "file": SimpleUploadedFile(
                    "notes.txt", b"hello", content_type="text/plain"
                )
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)
        self.assertEqual(Resume.objects.count(), 0)

    def test_pdf_name_with_disallowed_content_type_is_rejected(self):
        self.authenticate(self.seeker)
        response = self.client.post(
            reverse("resumes_api:resume_list"),
            {
                "file": SimpleUploadedFile(
                    "resume.pdf", b"%PDF-1.4", content_type="text/plain"
                )
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)
        self.assertEqual(Resume.objects.count(), 0)

    @override_settings(RESUME_MAX_UPLOAD_SIZE_MB=0)
    def test_oversized_upload_is_rejected(self):
        response = self.upload_resume(self.seeker)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)
        self.assertEqual(Resume.objects.count(), 0)

    def test_unreadable_pdf_still_creates_the_row_but_marks_it_failed(self):
        # Upload must always answer 201: a broken document becomes a FAILED row
        # with parse_error, never a 500.
        response = self.upload_resume(self.seeker, content=b"not really a pdf")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        resume = Resume.objects.get(pk=response.data["id"])
        self.assertEqual(resume.parse_status, ParseStatus.FAILED)
        self.assertTrue(resume.parse_error)
        self.assertEqual(resume.parsed_data, {})
        self.assertIsNone(resume.parsed_at)

    def test_anonymous_uploads_are_unauthorized(self):
        response = self.client.post(
            reverse("resumes_api:resume_list"), {"file": resume_upload()}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Resume.objects.count(), 0)

    def test_recruiter_cannot_upload(self):
        response = self.upload_resume(self.recruiter)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Resume.objects.count(), 0)
