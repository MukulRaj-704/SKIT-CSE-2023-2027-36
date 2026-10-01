import uuid

from django.urls import reverse

from .base import JOB_DESCRIPTION, AnalyzerAPITestCase, build_docx


class AnalyzerFlowTests(AnalyzerAPITestCase):
    def test_full_workflow_without_login(self):
        rid = self.upload_resume().data["resume_id"]

        # Mode 1: general ATS check, no job description.
        g = self.client.post(reverse("analyzer_api:analyze_resume"), {"resume_id": rid}, format="json")
        self.assertEqual(g.status_code, 201, g.content)
        self.assertEqual(g.data["mode"], "general")
        self.assertNotIn("job_analysis", g.data)
        ra = g.data["resume_analysis"]
        self.assertEqual(set(ra["section_scores"]), {"structure", "skills", "experience", "projects", "education", "contact", "formatting"})
        self.assertTrue(0 <= ra["ats_score"] <= 100)
        self.assertTrue(g.data["suggestions"] is not None)

        # Mode 2: job specific.
        j = self.client.post(reverse("analyzer_api:analyze_job"),
                             {"resume_id": rid, "job_description": JOB_DESCRIPTION, "job_title": "Backend Engineer", "company": "Acme"}, format="json")
        self.assertEqual(j.status_code, 201, j.content)
        job = j.data["job_analysis"]
        for key in ("job_match_score", "keyword_score", "skill_score", "experience_score", "education_score",
                    "matched_keywords", "missing_keywords", "matched_skills", "missing_skills", "suggestions"):
            self.assertIn(key, job)
        self.assertIn("Docker", job["missing_skills"])
        self.assertIn("Python", job["matched_skills"])
        self.assertEqual(j.data["resume_analysis"]["ats_score"], ra["ats_score"])

        # Stored analyses can be fetched again.
        got = self.client.get(reverse("analyzer_api:analysis_detail", args=[j.data["analysis_id"]]))
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.data["job_analysis"]["job_match_score"], job["job_match_score"])

    def test_docx_flow(self):
        rid = self.upload_resume(build_docx(), "resume.docx").data["resume_id"]
        r = self.client.post(reverse("analyzer_api:analyze_resume"), {"resume_id": rid}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertGreater(r.data["resume_analysis"]["ats_score"], 60)

    def test_reanalysis_after_improving_resume_scores_higher(self):
        from .base import RESUME_LINES
        weak = [l for l in RESUME_LINES if not l.startswith(("Languages", "Frameworks", "Databases", "Tools")) and not l.startswith("Backend developer") and l != "Professional Summary"]
        score = lambda lines: self.client.post(reverse("analyzer_api:analyze_resume"),
            {"resume_id": self.upload_resume(__import__("analyzer.tests.base", fromlist=["build_pdf"]).build_pdf(lines)).data["resume_id"]}, format="json").data["resume_analysis"]["ats_score"]
        self.assertGreater(score(RESUME_LINES), score(weak))

    def test_validation_errors(self):
        rid = self.upload_resume().data["resume_id"]
        url = reverse("analyzer_api:analyze_job")
        self.assertEqual(self.client.post(url, {"resume_id": rid, "job_description": ""}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"resume_id": rid, "job_description": "too short"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"job_description": JOB_DESCRIPTION}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"resume_id": "not-a-uuid", "job_description": JOB_DESCRIPTION}, format="json").status_code, 400)

    def test_unknown_ids_are_404(self):
        ghost = str(uuid.uuid4())
        self.assertEqual(self.client.post(reverse("analyzer_api:analyze_resume"), {"resume_id": ghost}, format="json").status_code, 404)
        self.assertEqual(self.client.post(reverse("analyzer_api:analyze_job"), {"resume_id": ghost, "job_description": JOB_DESCRIPTION}, format="json").status_code, 404)
        self.assertEqual(self.client.get(reverse("analyzer_api:analysis_detail", args=[ghost])).status_code, 404)

    def test_job_description_with_no_skills_still_answers(self):
        rid = self.upload_resume().data["resume_id"]
        r = self.client.post(reverse("analyzer_api:analyze_job"),
                             {"resume_id": rid, "job_description": "Looking for a friendly person to greet customers at the front desk."}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data["job_analysis"]["warnings"])

    def test_existing_modules_are_untouched(self):
        # The legacy, login based endpoint still demands authentication.
        self.assertEqual(self.client.get("/api/resumes/").status_code, 401)
