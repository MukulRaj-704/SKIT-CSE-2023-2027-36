from django.test import SimpleTestCase

from analyzer.services.resume_parser import parse_resume_text

from .base import RESUME_LINES

TEXT = "\n".join(RESUME_LINES)


class ResumeParserTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.p = parse_resume_text(TEXT)

    def test_personal_info(self):
        c = self.p["personal_info"]
        self.assertEqual(c["name"], "Aarav Mehta")
        self.assertEqual(c["email"], "aarav.mehta@example.com")
        self.assertIn("98765", c["phone"])
        self.assertIn("linkedin.com/in/aaravmehta", c["linkedin"])
        self.assertIn("github.com/aaravm", c["github"])

    def test_hyperlinks_fill_missing_urls(self):
        p = parse_resume_text("Jane Doe\njane@x.com\nSkills\nPython, Django, SQL, Git, Docker", ["https://www.linkedin.com/in/jane", "https://github.com/jane", "https://github.com/jane/repo"])
        self.assertEqual(p["personal_info"]["linkedin"], "https://www.linkedin.com/in/jane")
        self.assertEqual(p["personal_info"]["github"], "https://github.com/jane")  # profile, not repo

    def test_skills_extraction_and_categories(self):
        names = {s["name"]: s["category"] for s in self.p["skills"]}
        self.assertEqual(names["Python"], "Programming Languages")
        self.assertEqual(names["Django"], "Frameworks")
        self.assertEqual(names["PostgreSQL"], "Databases")
        self.assertTrue(self.p["skills_labeled"])

    def test_education_extraction(self):
        e = self.p["education"][0]
        self.assertIn("Swami Keshvanand", e["institution"])
        self.assertTrue(e["degree"].startswith("B.Tech"))
        self.assertEqual((e["start_date"], e["end_date"]), ("2021", "2025"))
        self.assertEqual(e["gpa"], "8.9/10")

    def test_experience_extraction(self):
        e = self.p["experience"][0]
        self.assertEqual(e["title"], "Software Engineer Intern")
        self.assertEqual(e["company"], "Acme Technologies")
        self.assertEqual((e["start_date"], e["end_date"]), ("Jan 2024", "Jun 2024"))
        self.assertEqual(len(e["bullets"]), 2)
        self.assertTrue(e["is_internship"])

    def test_project_extraction(self):
        pr = self.p["projects"][0]
        self.assertEqual(pr["name"], "TaskHub - Task management web app")
        self.assertEqual(pr["technologies"], ["Django", "PostgreSQL", "React.js"])
        self.assertEqual(len(pr["bullets"]), 2)

    def test_certifications_summary(self):
        self.assertEqual(self.p["certifications"][0]["name"], "Django Web Development")
        self.assertIn("REST APIs", self.p["summary"])

    def test_blank_lines_between_bullets_do_not_create_fake_jobs(self):
        text = "Experience\nData Intern | 05/2025 | 07/2025\nAcme\n\n - Built models with Pandas and\n   NumPy for churn.\n\n - Wrote reports.\nSkills\nPython"
        exp = parse_resume_text(text)["experience"]
        self.assertEqual(len(exp), 1)
        self.assertEqual(len(exp[0]["bullets"]), 2)
        self.assertIn("Pandas and NumPy", exp[0]["bullets"][0])

    def test_unusual_section_names(self):
        p = parse_resume_text("Name\nProfessional Experience\nDev at Foo | 2020 - 2022\n- Did things with Python\nAcademic Qualifications\nB.Sc Physics 2019\nAwards & Achievements\n- Won hackathon\nLanguages\nEnglish, Hindi")
        self.assertEqual(len(p["experience"]), 1)
        self.assertEqual(p["achievements"], ["Won hackathon"])
        self.assertEqual(p["languages"], ["English", "Hindi"])

    def test_resume_without_standard_sections_does_not_crash(self):
        p = parse_resume_text("just a blob of text without any headings at all " * 5)
        self.assertEqual(p["skills"], [])
        self.assertEqual(p["detected_sections"], [])

    def test_no_skills_no_experience_no_projects(self):
        p = parse_resume_text("Jane Doe\njane@x.com\nEducation\nB.Tech Computer Science 2025")
        self.assertEqual((p["skills"], p["experience"], p["projects"]), ([], [], []))
        self.assertEqual(len(p["education"]), 1)
