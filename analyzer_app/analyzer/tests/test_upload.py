from unittest import mock

from django.urls import reverse

from analyzer import config
from analyzer.models import AnalyzedResume

from .base import AnalyzerAPITestCase, build_docx, build_pdf, upload


class ResumeUploadTests(AnalyzerAPITestCase):
    url = property(lambda self: reverse("analyzer_api:resume_upload"))

    def post(self, data, name="resume.pdf"):
        return self.client.post(self.url, {"file": upload(data, name)}, format="multipart")

    def test_valid_pdf_without_login(self):
        r = self.post(build_pdf())
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["file_type"], "pdf")
        self.assertEqual(r.data["parsed_resume"]["personal_info"]["email"], "aarav.mehta@example.com")
        self.assertTrue(AnalyzedResume.objects.filter(pk=r.data["resume_id"]).exists())

    def test_valid_docx(self):
        r = self.post(build_docx(), "resume.docx")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["file_type"], "docx")
        self.assertIn("Python", [s["name"] for s in r.data["parsed_resume"]["skills"]])

    def test_unsupported_format(self):
        r = self.post(b"plain text resume " * 10, "resume.txt")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "unsupported_format")

    def test_empty_file(self):
        r = self.post(b"")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "empty_file")

    def test_missing_file_field(self):
        self.assertEqual(self.client.post(self.url, {}, format="multipart").status_code, 400)

    def test_corrupted_pdf(self):
        r = self.post(b"%PDF-1.7 this is not really a pdf at all" * 3)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "corrupted_file")

    def test_renamed_file_is_not_a_pdf(self):
        r = self.post(b"just some text pretending to be a resume", "resume.pdf")
        self.assertEqual(r.data["code"], "corrupted_file")

    def test_corrupted_docx(self):
        r = self.post(b"PK\x03\x04 broken zip content", "resume.docx")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "corrupted_file")

    def test_file_too_large(self):
        with mock.patch.object(config, "MAX_UPLOAD_SIZE_MB", 0.0001):
            r = self.post(build_pdf())
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "file_too_large")

    def test_scanned_image_only_pdf(self):
        r = self.post(build_pdf(text=False, image=True))
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data["code"], "scanned_pdf")

    def test_pdf_without_text(self):
        r = self.post(build_pdf(lines=["hi"]))
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.data["code"], "no_text")

    def test_docx_table_is_detected_for_formatting(self):
        r = self.post(build_docx(tables=1), "resume.docx")
        self.assertEqual(AnalyzedResume.objects.get(pk=r.data["resume_id"]).layout["tables"], 1)

    def test_get_stored_resume(self):
        rid = self.post(build_pdf()).data["resume_id"]
        r = self.client.get(reverse("analyzer_api:resume_detail", args=[rid]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["resume_id"], rid)
