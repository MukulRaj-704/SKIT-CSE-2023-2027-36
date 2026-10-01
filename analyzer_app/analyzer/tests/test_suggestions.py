from django.test import SimpleTestCase

from analyzer.services import resume_analysis, suggestion_engine
from analyzer.services import skills_taxonomy as tax
from analyzer.services.resume_parser import parse_resume_text

from .base import JOB_DESCRIPTION, RESUME_LINES

TEXT = "\n".join(RESUME_LINES)
LAYOUT = {"multi_column": False, "images": 0, "tables": 0}


def general(text):
    p = parse_resume_text(text)
    return resume_analysis.analyze_general(p, text, LAYOUT, 1)["suggestions"]


class GeneralSuggestionTests(SimpleTestCase):
    def test_suggestions_have_priority_category_message_and_are_sorted(self):
        s = general("Jane Doe\nSkills\nPython, SQL\nEducation\nB.Tech Computer Science 2025")
        self.assertTrue(s)
        order = {"high": 0, "medium": 1, "low": 2}
        self.assertEqual([order[x["priority"]] for x in s], sorted(order[x["priority"]] for x in s))
        self.assertTrue(all({"priority", "category", "message"} == set(x) for x in s))

    def test_suggestions_follow_what_was_detected(self):
        codes = lambda t: {x["category"] + ":" + x["message"][:25] for x in general(t)}
        no_summary = general("\n".join(l for l in RESUME_LINES if l not in ("Professional Summary",) and not l.startswith("Backend developer")))
        self.assertTrue(any("professional summary" in x["message"] for x in no_summary))
        self.assertFalse(any("professional summary" in x["message"] for x in general(TEXT)))

    def test_ungrouped_skills_are_flagged(self):
        t = TEXT.replace("Languages: ", "").replace("Frameworks: ", "").replace("Databases: ", "").replace("Tools: ", "")
        self.assertTrue(any("separate programming languages" in x["message"] for x in general(t)))

    def test_missing_sections_are_reported_with_conditional_wording(self):
        s = general("Jane Doe\njane@example.com\nSkills\nPython, Django, SQL, Git, Docker, React.js, Flask")
        text = " ".join(x["message"] for x in s)
        self.assertIn("No work experience", text)
        self.assertIn("do not invent", text)

    def test_general_suggestions_never_name_a_skill_the_resume_lacks(self):
        for x in general("Jane Doe\nSkills\nPython"):
            self.assertNotRegex(x["message"], r"\b(Docker|Kubernetes|AWS|Redis)\b")


class JobSuggestionTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        p = parse_resume_text(TEXT)
        cls.result = resume_analysis.analyze_job(p, TEXT, LAYOUT, 1, JOB_DESCRIPTION, "Backend Engineer", "Acme")["job_analysis"]

    def test_missing_skill_advice_is_conditional_and_offers_learning(self):
        docker = next(s for s in self.result["suggestions"] if s["message"].startswith("Docker"))
        self.assertIn("If you have genuine experience with Docker", docker["message"])
        self.assertIn("rather than adding it to your resume", docker["message"])

    def test_no_unconditional_add_x_advice(self):
        suggestion_engine.assert_authentic(self.result["suggestions"])
        with self.assertRaises(AssertionError):
            suggestion_engine.assert_authentic([{"message": "Add Docker to your resume."}])

    def test_skills_in_suggestions_come_from_the_job_description_only(self):
        jd_skills = set(tax.find_skills(JOB_DESCRIPTION))
        for s in self.result["suggestions"]:
            for name in tax.find_skills(s["message"]):
                self.assertIn(name, jd_skills | set(tax.find_skills(TEXT)), s["message"])

    def test_suggestions_never_invent_experience_or_numbers(self):
        text = " ".join(s["message"] for s in self.result["suggestions"])
        self.assertNotRegex(text, r"\b(claim|pretend|fake)\b.*\byears\b")
        self.assertNotRegex(text, r"\d+\+? years of \w+ experience to your resume")

    def test_loose_mention_suggestion(self):
        text = "Experience\nDev | 2023 - 2024\nAcme\n- Developed APIs for the billing backend using Python\nSkills\nPython, Git, SQL"
        p = parse_resume_text(text)
        out = resume_analysis.analyze_job(p, text, LAYOUT, 1, "Requirements: Python, REST API, Git, SQL, Docker")["job_analysis"]
        msg = next(s["message"] for s in out["suggestions"] if s["message"].startswith("Your resume mentions"))
        self.assertIn('"api" but not "REST API"', msg)
        self.assertIn("if it was not", msg)

    def test_related_skill_suggestion_is_honest(self):
        text = "Skills\nPython, Django, SQL, Git, PostgreSQL"
        p = parse_resume_text(text)
        out = resume_analysis.analyze_job(p, text, LAYOUT, 1, "Requirements: Python, Flask, Git")["job_analysis"]
        msg = next(s["message"] for s in out["suggestions"] if s["message"].startswith("Flask"))
        self.assertIn("Django", msg)
        self.assertIn("If you have genuinely used", msg)
