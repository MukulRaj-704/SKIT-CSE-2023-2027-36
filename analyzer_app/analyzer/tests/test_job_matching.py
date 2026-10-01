from django.test import SimpleTestCase

from analyzer.services import (education_analyzer, experience_analyzer, jd_parser, job_matcher,
                               keyword_matcher, semantic, skill_matcher)
from analyzer.services import skills_taxonomy as tax
from analyzer.services.resume_parser import parse_resume_text

from .base import JOB_DESCRIPTION, RESUME_LINES

TEXT = "\n".join(RESUME_LINES)
PARSED = parse_resume_text(TEXT)


class TaxonomyTests(SimpleTestCase):
    def test_rest_api_variants_normalise_to_one_term(self):
        for v in ["REST API", "REST APIs", "RESTful API", "RESTful APIs", "REST API Development"]:
            self.assertEqual(tax.canonical(v), "rest api", v)
        self.assertEqual(list(tax.find_skills("Built RESTful APIs and a REST API")), ["rest api"])

    def test_other_aliases_and_ambiguous_names(self):
        self.assertEqual(tax.canonical("Postgres"), "postgresql")
        self.assertEqual(tax.canonical("sklearn"), "scikit-learn")
        self.assertEqual(tax.canonical("React.js"), "react")
        self.assertNotIn("java", tax.find_skills("JavaScript developer"))
        self.assertNotIn("git", tax.find_skills("GitHub profile"))
        self.assertIn("c", tax.find_skills("Languages: C, C++, Python"))
        self.assertNotIn("c", tax.find_skills("Plan C was a good idea"))


class JDParserTests(SimpleTestCase):
    def setUp(self):
        self.jd = jd_parser.parse_job_description(JOB_DESCRIPTION, "Backend Engineer", "Acme")

    def test_required_vs_preferred_skills(self):
        self.assertTrue({"python", "django", "rest api", "postgresql", "docker", "redis", "git"} <= set(self.jd["required_skills"]))
        self.assertEqual(set(self.jd["preferred_skills"]), {"ci/cd", "kubernetes"})

    def test_experience_education_and_responsibilities(self):
        self.assertEqual(self.jd["experience_requirements"][0]["years"], 2)
        self.assertEqual(self.jd["experience_requirements"][0]["skill"], "django")
        self.assertEqual(self.jd["education_requirement"]["level"], 2)
        self.assertEqual(len(self.jd["responsibilities"]), 2)

    def test_multiple_experience_requirements(self):
        r = jd_parser.parse_experience("2+ years of Django experience and 3-5 years of professional experience overall")
        self.assertEqual([(x["years"], x["skill"]) for x in r], [(2, "django"), (3, None)])

    def test_soft_skills_and_fresher_flag(self):
        jd = jd_parser.parse_job_description("Fresher role. Strong communication and teamwork. Python required.")
        self.assertEqual(set(jd["soft_skills"]), {"communication", "teamwork"})
        self.assertTrue(jd["fresher_friendly"])

    def test_jd_without_recognisable_skills(self):
        out = job_matcher.match_job(PARSED, TEXT, "We need a friendly person to greet customers at the front desk every morning.")
        self.assertFalse(out["warnings"] == [])
        self.assertIsNone(out["skill_score"])
        self.assertTrue(0 <= out["job_match_score"] <= 100)


class KeywordMatcherTests(SimpleTestCase):
    def test_spec_example(self):
        text = "Skills: Python, Django, PostgreSQL, Git"
        r = keyword_matcher.match_keywords(["python", "django", "rest api", "postgresql", "docker", "git"], text)
        self.assertEqual(r["matched_keywords"], ["Python", "Django", "PostgreSQL", "Git"])
        self.assertEqual(r["missing_keywords"], ["REST API", "Docker"])
        self.assertEqual(r["keyword_score"], 67)

    def test_duplicates_and_variants(self):
        r = keyword_matcher.match_keywords(["rest api", "rest api", "python"], "Built RESTful APIs in Python")
        self.assertEqual(r["matched_keywords"], ["REST API", "Python"])

    def test_loose_mention_is_reported_not_matched(self):
        r = keyword_matcher.match_keywords(["rest api"], "Developed APIs for the billing backend")
        self.assertEqual(r["matched_keywords"], [])
        self.assertEqual(r["loosely_mentioned"][0]["found_instead"][0], "api")


class SkillMatcherTests(SimpleTestCase):
    def test_matched_missing_and_related(self):
        r = skill_matcher.match_skills(PARSED, ["python", "django", "docker", "mongodb", "flask"], ["kubernetes"])
        self.assertEqual(r["matched_skills"], ["Python", "Django"])
        self.assertEqual(r["missing_skills"], ["Docker", "MongoDB", "Flask", "Kubernetes"])
        self.assertEqual({x["job_skill"]: x["resume_skill"] for x in r["related_skills"]}["Flask"], "Django")
        self.assertNotIn("Flask", r["matched_skills"])  # related is never a match

    def test_implied_skill_counts_but_says_why(self):
        r = skill_matcher.match_skills(PARSED, ["sql", "rest api"], [])  # PostgreSQL implies SQL, DRF implies REST API
        self.assertEqual(r["matched_skills"], ["SQL", "REST API"])

    def test_score_gives_related_half_credit(self):
        r = skill_matcher.match_skills(PARSED, ["python", "flask"], [])
        self.assertEqual(r["skill_score"], 75)

    def test_no_required_skills_gives_no_score(self):
        self.assertIsNone(skill_matcher.match_skills(PARSED, [], [])["skill_score"])


class ExperienceMatchTests(SimpleTestCase):
    def parsed(self, start, end, bullet="Built Django APIs"):
        return parse_resume_text(f"Experience\nBackend Developer | {start} - {end}\nAcme\n- {bullet}\nSkills\nDjango")

    def test_explicit_match(self):
        r = experience_analyzer.match(self.parsed("Jan 2020", "Dec 2023"), [{"years": 2, "skill": "django", "text": "2+ years of Django"}])
        self.assertEqual(r["items"][0]["verdict"], "explicit")
        self.assertEqual(r["score"], 100)

    def test_partial_match_one_year_of_two(self):
        r = experience_analyzer.match(self.parsed("Jan 2023", "Dec 2023"), [{"years": 2, "skill": "django", "text": "2+ years of Django"}])
        self.assertEqual(r["items"][0]["verdict"], "partial")
        self.assertEqual(r["items"][0]["detected_years"], 1.0)
        self.assertTrue(40 <= r["score"] < 100)

    def test_missing_information_is_not_invented(self):
        r = experience_analyzer.match(self.parsed("Jan 2023", "Dec 2023", "Wrote reports"), [{"years": 2, "skill": "docker", "text": "2+ years of Docker"}])
        self.assertEqual(r["items"][0]["verdict"], "missing_information")
        self.assertEqual(r["score"], 0)

    def test_no_requirement_means_no_score(self):
        self.assertIsNone(experience_analyzer.match(PARSED, [])["score"])

    def test_overlapping_roles_are_not_double_counted(self):
        p = parse_resume_text("Experience\nDev | Jan 2022 - Dec 2022\nA\n- Used Django\nDev 2 | Jun 2022 - Dec 2022\nB\n- Used Django\nSkills\nDjango")
        self.assertEqual(experience_analyzer.total_months(p), 12)


class EducationMatchTests(SimpleTestCase):
    def test_btech_cs_meets_bachelor_cs(self):
        r = education_analyzer.match(PARSED, {"level": 2, "fields": ["computer science"], "text": "Bachelor's degree in Computer Science"})
        self.assertEqual((r["verdict"], r["score"]), ("strong", 100))

    def test_level_too_low(self):
        r = education_analyzer.match(PARSED, {"level": 3, "fields": [], "text": "Master's degree"})
        self.assertEqual(r["verdict"], "partial")
        self.assertLess(r["score"], 50)

    def test_missing_education_and_not_specified(self):
        p = parse_resume_text("Skills\nPython")
        self.assertEqual(education_analyzer.match(p, {"level": 2, "fields": [], "text": "Bachelor's"})["verdict"], "missing_information")
        self.assertEqual(education_analyzer.match(p, {"level": 0})["verdict"], "not_specified")


class SemanticTests(SimpleTestCase):
    def test_relevant_requirement_beats_irrelevant_one(self):
        rel = semantic.semantic_match(PARSED, TEXT, "x", ["Design REST APIs and database schemas for web applications"])
        irr = semantic.semantic_match(PARSED, TEXT, "x", ["Negotiate enterprise sales contracts with retail clients"])
        self.assertGreater(rel["score"], irr["score"])
        self.assertTrue(irr["gaps"])

    def test_synonyms_are_recognised_through_the_taxonomy(self):
        a = semantic.similarity_matrix(["Build RESTful web services"], ["Developed REST API endpoints", "Cooked pasta for dinner"])[0][0]
        self.assertGreater(a[0], a[1])

    def test_identical_text_is_close_to_one(self):
        m, backend = semantic.similarity_matrix(["python django postgresql"], ["python django postgresql"])
        self.assertEqual(backend, "tfidf")
        self.assertAlmostEqual(m[0][0], 1.0, places=5)


class JobMatchScoreTests(SimpleTestCase):
    def test_relevant_job_beats_unrelated_job(self):
        good = job_matcher.match_job(PARSED, TEXT, JOB_DESCRIPTION)["job_match_score"]
        bad = job_matcher.match_job(PARSED, TEXT, "Hiring a Data Scientist: TensorFlow, PyTorch, Spark, Hadoop, Tableau, R and AWS. 5+ years of experience. Master's degree required.")["job_match_score"]
        self.assertGreater(good, bad + 20)

    def test_components_without_data_are_skipped_not_zeroed(self):
        out = job_matcher.match_job(PARSED, TEXT, "Python and Django developer. Requirements: Python, Django.")
        self.assertNotIn("education", out["weights_used"])
        self.assertAlmostEqual(sum(out["weights_used"].values()), 1.0, places=2)
        self.assertGreater(out["job_match_score"], 70)
