"""
analyzer/services/job_matcher.py
================================
Resume <-> job description matching (Mode 2). Combines the explainable component
scores with the weights in ``analyzer/config.py``. Components that cannot be
evaluated for this job (for example a JD with no education requirement) are
skipped and the remaining weights are re-normalised, so a missing JD section
never silently lowers the score.
"""

from __future__ import annotations

from .. import config
from . import education_analyzer, experience_analyzer, jd_parser, keyword_matcher, semantic, skill_matcher
from .common import experience_text, project_text


def match_job(parsed: dict, raw_text: str, jd_text: str, job_title: str = "", company: str = "") -> dict:
    jd = jd_parser.parse_job_description(jd_text, job_title, company)
    warnings = []
    if not jd["has_recognised_skills"]:
        warnings.append("No recognisable technical skills were found in the job description, so the skill match is not scored.")

    skills = skill_matcher.match_skills(parsed, jd["required_skills"], jd["preferred_skills"])
    keywords = keyword_matcher.match_keywords(jd["keywords"], raw_text)
    exp = experience_analyzer.match(parsed, jd["experience_requirements"])
    edu = education_analyzer.match(parsed, jd["education_requirement"])
    proj = skill_matcher.project_relevance(parsed, jd["required_skills"])
    sem = semantic.semantic_match(parsed, raw_text, jd_text, jd["responsibilities"] + jd["requirement_lines"])

    # Fresher-friendly JD with no explicit years: experience is not a weakness.
    if exp["score"] is None and jd["fresher_friendly"]:
        exp = {**exp, "score": None}

    components = {
        "skills": skills["skill_score"],
        "keywords": keywords["keyword_score"],
        "experience": exp["score"],
        "projects": proj,
        "education": edu["score"],
        "semantic": sem["score"],
    }
    weights = {k: w for k, w in config.JOB_MATCH_WEIGHTS.items() if components.get(k) is not None}
    total_w = sum(weights.values())
    score = round(sum(components[k] * w for k, w in weights.items()) / total_w) if total_w else 0
    if not weights:
        warnings.append("The job description did not contain enough information to score a match.")

    return {
        "job_match_score": score,
        "keyword_score": keywords["keyword_score"],
        "skill_score": skills["skill_score"],
        "experience_score": exp["score"],
        "education_score": edu["score"],
        "project_score": proj,
        "semantic_score": sem["score"],
        "weights_used": {k: round(w / total_w, 3) for k, w in weights.items()} if total_w else {},
        "matched_keywords": keywords["matched_keywords"],
        "missing_keywords": keywords["missing_keywords"],
        "loosely_mentioned_keywords": keywords["loosely_mentioned"],
        "matched_skills": skills["matched_skills"],
        "missing_skills": skills["missing_skills"],
        "related_skills": skills["related_skills"],
        "skills_by_category": skills["by_category"],
        "experience_match": exp,
        "education_match": edu,
        "semantic": {"backend": sem["backend"], "doc_similarity": sem["doc_similarity"],
                     "strong_matches": sem["strong"], "gaps": sem["gaps"]},
        "job": {k: jd[k] for k in ("job_title", "company", "required_skills", "preferred_skills", "soft_skills",
                                    "experience_requirements", "education_requirement", "responsibilities")},
        "warnings": warnings,
        "_detail": {"skills": skills, "jd": jd},  # consumed by the suggestion engine, removed before saving
    }
