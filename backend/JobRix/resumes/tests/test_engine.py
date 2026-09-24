"""
resumes/tests/test_engine.py
============================
The ``resumes.services`` adapter against the real engine, without HTTP or the
database: parse a generated PDF once, then score the stored structure.
"""

from django.test import SimpleTestCase, override_settings

from resumes.services import parse_pdf_bytes, run_ats_analysis

from .base import JOB_DESCRIPTION, build_resume_pdf

RESULT_KEYS = {
    "score",
    "keyword_coverage",
    "matched_skills",
    "missing_skills",
    "suggestions",
}


@override_settings(RESUME_PARSE_SPACY=False)
class EngineAdapterTests(SimpleTestCase):
    """``parse_pdf_bytes`` + ``run_ats_analysis`` (the parse-once plumbing)."""

    def test_parse_pdf_bytes_returns_the_engine_structure(self):
        parsed = parse_pdf_bytes(build_resume_pdf())

        self.assertEqual(
            parsed["contact"]["email"], "mukul.sharma@example.com", parsed["contact"]
        )
        skill_names = {skill["name"].lower() for skill in parsed["skills"]}
        self.assertTrue({"python", "django"} <= skill_names, skill_names)
        self.assertTrue(parsed["raw_text"])
        # keys match the ParsedResume dataclass the API persists as JSON
        for key in (
            "contact",
            "summary",
            "skills",
            "education",
            "experience",
            "projects",
            "certifications",
            "detected_sections",
        ):
            self.assertIn(key, parsed)

    def test_run_ats_analysis_scores_a_stored_parse(self):
        # Same shape as what Resume.parsed_data holds: parse once, then score.
        parsed = parse_pdf_bytes(build_resume_pdf())
        result = run_ats_analysis(parsed, JOB_DESCRIPTION)

        self.assertEqual(set(result), RESULT_KEYS)
        self.assertTrue(0 <= result["score"] <= 100, result["score"])
        self.assertTrue(0 <= result["keyword_coverage"] <= 1)
        matched = {item.lower() for item in result["matched_skills"]}
        missing = {item.lower() for item in result["missing_skills"]}
        self.assertTrue({"python", "django"} <= matched, matched)
        self.assertIn("kubernetes", missing, missing)

    def test_empty_parse_raises_a_domain_error(self):
        from resumes.services import ResumeEngineError

        with self.assertRaises(ResumeEngineError):
            run_ats_analysis({}, JOB_DESCRIPTION)
