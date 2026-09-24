"""
resumes/tests/test_resume_api.py
================================
Detail/update/delete scoping, manual reparse, one-default-per-account.
"""

import os

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Role

from resumes.models import ParseStatus, Resume

from .base import PARSED_DATA, TEST_MEDIA_ROOT, ResumeAPIMixin, resume_upload


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, RESUME_PARSE_SPACY=False)
class ResumeDetailPermissionTests(ResumeAPIMixin, APITestCase):
    """``/api/resumes/<id>/`` - owner only: others 404, recruiters 403."""

    def setUp(self):
        self.seeker = self.make_user("seeker@example.com")
        self.other = self.make_user("other@example.com")
        self.recruiter = self.make_user("recruiter@example.com", role=Role.RECRUITER)
        self.resume = Resume.objects.create(
            user=self.seeker,
            title="My resume",
            file=resume_upload(),
            parse_status=ParseStatus.PARSED,
            parsed_data=PARSED_DATA,
            original_filename="candidate_resume.pdf",
        )
        self.detail_url = reverse("resumes_api:resume_detail", args=[self.resume.pk])

    def test_owner_gets_the_full_detail(self):
        self.authenticate(self.seeker)
        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["parsed_summary"]["skills_count"], 4)
        self.assertEqual(response.data["skills"][0], "Python")
        self.assertEqual(response.data["ats_analyses_count"], 0)

    def test_other_seeker_cannot_see_or_touch_it(self):
        self.authenticate(self.other)
        self.assertEqual(self.client.get(self.detail_url).status_code, 404)
        rename = self.client.patch(self.detail_url, {"title": "hijacked"})
        self.assertEqual(rename.status_code, 404)
        self.assertEqual(self.client.delete(self.detail_url).status_code, 404)
        self.assertTrue(Resume.objects.filter(pk=self.resume.pk).exists())

    def test_recruiter_is_forbidden(self):
        self.authenticate(self.recruiter)
        self.assertEqual(self.client.get(self.detail_url).status_code, 403)
        self.assertEqual(
            self.client.patch(self.detail_url, {"title": "x"}).status_code, 403
        )

    def test_owner_can_rename_and_delete_removes_the_stored_file_too(self):
        stored_path = self.resume.file.path
        self.assertTrue(os.path.exists(stored_path))

        self.authenticate(self.seeker)
        rename = self.client.patch(self.detail_url, {"title": "Renamed"})
        self.assertEqual(rename.status_code, status.HTTP_200_OK)
        self.assertEqual(rename.data["title"], "Renamed")

        delete = self.client.delete(self.detail_url)
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Resume.objects.filter(pk=self.resume.pk).exists())
        self.assertFalse(os.path.exists(stored_path), "stored PDF must be removed")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, RESUME_PARSE_SPACY=False)
class ResumeReparseAndDefaultTests(ResumeAPIMixin, APITestCase):
    """Manual reparse + the one-default-per-account invariant."""

    def setUp(self):
        self.seeker = self.make_user("seeker@example.com")

    def test_reparse_reruns_the_engine_on_the_stored_file(self):
        upload = self.upload_resume(self.seeker)
        resume = Resume.objects.get(pk=upload.data["id"])
        self.assertEqual(resume.parse_status, ParseStatus.PARSED)

        self.authenticate(self.seeker)
        reparsed = self.client.post(
            reverse("resumes_api:resume_reparse", args=[resume.pk])
        )
        self.assertEqual(reparsed.status_code, status.HTTP_200_OK)
        self.assertEqual(reparsed.data["parse_status"], ParseStatus.PARSED)
        resume.refresh_from_db()
        self.assertTrue(resume.parsed_data)
        self.assertTrue(resume.parsed_at)

    def test_second_resume_can_become_the_only_default(self):
        first = self.upload_resume(self.seeker)
        self.assertTrue(Resume.objects.get(pk=first.data["id"]).is_default)

        self.authenticate(self.seeker)
        second = self.client.post(
            reverse("resumes_api:resume_list"),
            {"file": resume_upload(name="second.pdf"), "is_default": True},
        )
        self.assertEqual(second.status_code, status.HTTP_201_CREATED, second.data)

        defaults = Resume.objects.filter(user=self.seeker, is_default=True)
        self.assertEqual(defaults.count(), 1)
        self.assertEqual(defaults.first().pk, second.data["id"])
        self.assertEqual(Resume.objects.filter(user=self.seeker).count(), 2)
