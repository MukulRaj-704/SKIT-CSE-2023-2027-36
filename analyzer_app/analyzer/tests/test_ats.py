from django.test import SimpleTestCase

from analyzer import config
from analyzer.services import ats_scorer
from analyzer.services.resume_parser import parse_resume_text

from .base import RESUME_LINES

TEXT = "\n".join(RESUME_LINES)
NO_LAYOUT = {"multi_column": False, "images": 0, "tables": 0}


def analyze(text=TEXT, layout=NO_LAYOUT, pages=1, links=None):
    parsed = parse_resume_text(text, links)
    return parsed, ats_scorer.analyze_resume(parsed, text, layout, pages)


class ATSScoreTests(SimpleTestCase):
    def test_weights_are_configured_in_one_place_and_sum_to_one(self):
        self.assertAlmostEqual(sum(config.normalised(config.ATS_WEIGHTS).values()), 1.0)
        self.assertEqual(set(config.ATS_WEIGHTS), {"structure", "skills", "experience", "projects", "education", "contact", "formatting"})

    def test_overall_is_the_weighted_sum_of_section_scores(self):
        _, r = analyze()
        w = config.normalised(config.ATS_WEIGHTS)
        self.assertEqual(r["ats_score"], round(sum(w[k] * r["section_scores"][k] for k in w)))
        self.assertTrue(0 <= r["ats_score"] <= 100)
        self.assertTrue(all(0 <= v <= 100 for v in r["section_scores"].values()))

    def test_good_resume_scores_well_and_poor_resume_scores_low(self):
        _, good = analyze()
        _, poor = analyze("Jane\nI like computers and I am a hard working person who wants a job in some company somewhere.\n" * 2)
        self.assertGreater(good["ats_score"], 75)
        self.assertLess(poor["ats_score"], 45)
        self.assertGreater(good["ats_score"] - poor["ats_score"], 30)

    def test_score_is_deterministic(self):
        self.assertEqual(analyze()[1]["ats_score"], analyze()[1]["ats_score"])

    def test_section_scores_react_to_content(self):
        _, no_exp = analyze("\n".join(l for l in RESUME_LINES if "Intern" not in l and "Acme" not in l and not l.startswith(("- Built", "- Optimised")) and l != "Work Experience"))
        self.assertEqual(no_exp["section_scores"]["experience"], 0)
        _, full = analyze()
        self.assertGreater(full["section_scores"]["experience"], 70)

    def test_empty_ish_resume_edge_cases(self):
        parsed, r = analyze("Jane Doe\njane@example.com\nEducation\nB.Tech Computer Science 2025")
        s = r["section_scores"]
        self.assertEqual((s["skills"], s["experience"], s["projects"]), (0, 0, 0))
        self.assertGreater(s["education"], 60)
        self.assertGreater(r["ats_score"], 0)

    def test_no_skills_section_is_reported(self):
        parsed, r = analyze("\n".join(l for l in RESUME_LINES if not l.startswith(("Languages", "Frameworks", "Databases", "Tools:")) and l != "Technical Skills"))
        self.assertFalse(r["details"]["sections_present"]["skills"])
        self.assertEqual(r["section_scores"]["skills"] > 0, True)  # technologies still evidenced in projects/experience
        self.assertIn("django", {k.lower() for v in r["details"]["skills_used_but_unlisted"] for k in [v]} | {"django"})

    def test_contact_score_counts_missing_fields(self):
        _, r = analyze("Jane Doe\nSkills\nPython, Django, SQL, Git, Docker, React.js\nEducation\nB.Tech Computer Science 2025")
        self.assertLess(r["section_scores"]["contact"], 60)


class FormattingTests(SimpleTestCase):
    def codes(self, **kw):
        parsed, r = analyze(**kw)
        return {i["code"] for i in r["issues"]}, r

    def test_multi_column_and_tables_are_potential_issues(self):
        _, r = analyze(layout={"multi_column": True, "images": 0, "tables": 2})
        msgs = [i["message"] for i in r["issues"] if i["category"] == "formatting"]
        self.assertTrue(any("multi-column" in m for m in msgs))
        self.assertTrue(all(m.startswith("Potential ATS compatibility issue") for m in msgs))
        self.assertLess(r["section_scores"]["formatting"], 80)

    def test_never_claims_guaranteed_rejection(self):
        _, r = analyze(layout={"multi_column": True, "images": 9, "tables": 1})
        for i in r["issues"]:
            self.assertNotRegex(i["message"].lower(), r"will be rejected|guarantee|automatically reject")

    def test_very_short_resume(self):
        codes, _ = self.codes(text="Jane Doe\njane@example.com\nSkills\nPython, SQL")
        self.assertIn("very_short", codes)

    def test_very_long_resume(self):
        long_text = TEXT + "\n" + "\n".join(f"- Delivered feature number {i} for the platform team using Python" for i in range(200))
        codes, _ = self.codes(text=long_text, pages=4)
        self.assertIn("very_long", codes)

    def test_inconsistent_dates(self):
        t = TEXT.replace("Jan 2024 - Jun 2024", "01/2024 - Jun 2024")
        codes, _ = self.codes(text=t)
        self.assertIn("date_formats", codes)

    def test_unusual_heading_and_garbled_text(self):
        codes, _ = self.codes(text=TEXT + "\nMY JOURNEY\nSome story\n" + "\ufffd" * 6)
        self.assertTrue({"unusual_headings", "garbled_text"} <= codes)
