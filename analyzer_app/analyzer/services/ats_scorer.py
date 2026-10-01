"""
analyzer/services/ats_scorer.py
===============================
General (job-independent) ATS score. Section scorers are small and explainable;
the weights live in ``analyzer/config.py`` (one place).
"""

from __future__ import annotations

import re

from .. import config
from . import (education_analyzer, experience_analyzer, formatting_analyzer,
               skills_taxonomy as tax, structure_analyzer)
from .common import all_experience, context_skills, is_action_bullet, issue, listed_skills, project_text, experience_text

TECH_CATEGORIES = {tax.LANG, tax.FRAMEWORK, tax.DB, tax.CLOUD, tax.DEVOPS, tax.ML, tax.DATA, tax.WEB, tax.TOOLS}


def analyze_contact(parsed: dict) -> dict:
    c = parsed.get("personal_info") or {}
    technical = bool(listed_skills(parsed) or context_skills(parsed))
    parts = {"name": 25, "email": 25, "phone": 20, "linkedin": 15}
    score = sum(pts for k, pts in parts.items() if c.get(k))
    score += 15 if (c.get("github") or c.get("portfolio") or not technical) else 0
    labels = {"name": "your full name", "email": "an email address", "phone": "a phone number", "linkedin": "a LinkedIn profile URL"}
    issues = []
    for k, label in labels.items():
        if not c.get(k):
            pr = "high" if k in ("name", "email", "phone") else "low"
            issues.append(issue(pr, "contact", f"no_{k}", f"No {k} was detected in the contact block. Make sure {label} is written as plain text near the top of the resume."))
    if technical and not (c.get("github") or c.get("portfolio")):
        issues.append(issue("low", "contact", "no_github", "No GitHub or portfolio link was detected. If you have public work, link it (as plain text, not only as an icon)."))
    return {"score": score, "issues": issues}


def analyze_skills(parsed: dict) -> dict:
    listed = listed_skills(parsed)
    ctx = context_skills(parsed)
    tech_listed = {k: v for k, v in listed.items() if tax.category_of(k) in TECH_CATEGORIES}
    categories = {tax.category_of(k) for k in tech_listed}
    by_cat: dict = {}
    for canon, shown in listed.items():
        by_cat.setdefault(tax.category_of(canon), []).append(shown)
    unlisted = [tax.display_name(k) for k in ctx if k not in listed and tax.is_technical(k)]

    if not listed and not ctx:
        score = 0
    else:
        base = tech_listed if listed else {k: k for k in ctx if tax.is_technical(k)}
        volume = min(1, len(base) / 12) * (40 if listed else 20)
        diversity = min(1, len({tax.category_of(k) for k in base}) / 4) * (25 if listed else 12)
        organised = 15 if parsed.get("skills_labeled") else 0
        evidence = (sum(1 for k in tech_listed if k in ctx) / len(tech_listed) * 20) if tech_listed else 0
        score = round(volume + diversity + organised + evidence)

    issues = []
    if listed and not parsed.get("skills_labeled"):
        issues.append(issue("high", "skills", "skills_not_grouped",
            "Your skills section does not clearly separate programming languages, frameworks, databases and tools. "
            "Group them under labels such as \"Languages:\", \"Frameworks:\", \"Databases:\" and \"Tools:\"."))
    if listed and len(tech_listed) < 6:
        issues.append(issue("medium", "skills", "few_skills", f"Only {len(tech_listed)} recognised technical skill(s) are listed. List the technologies you genuinely use, including ones only shown in your projects."))
    if listed and len(categories) < 3 and len(tech_listed) >= 3:
        issues.append(issue("low", "skills", "narrow_skills", "Your listed skills cover few technology areas. If you also work with databases, tools or cloud/DevOps, list them separately."))
    if unlisted:
        issues.append(issue("medium", "skills", "unlisted_skills",
            f"These technologies appear in your experience/projects but not in your Skills section: {', '.join(unlisted[:8])}. Listing them there makes them easier for ATS to find."))
    return {"score": min(100, score), "issues": issues, "by_category": by_cat, "unlisted_but_used": unlisted}


def analyze_projects(parsed: dict) -> dict:
    projects = parsed.get("projects") or []
    if not projects:
        return {"score": 0, "issues": [], "count": 0}
    n = len(projects)
    with_stack = sum(1 for p in projects if p.get("technologies") or tax.find_skills(p.get("raw_text", ""))) / n
    described = sum(1 for p in projects if len(p.get("bullets", [])) >= 2 or len((p.get("description") or "").split()) >= 15) / n
    bullets = [b for p in projects for b in p.get("bullets", [])]
    contribution = (sum(is_action_bullet(b) for b in bullets) / len(bullets)) if bullets else 0
    linked = sum(1 for p in projects if p.get("has_link_hint")) / n
    score = round(30 + 25 * with_stack + 20 * described + 15 * contribution + 10 * linked)
    issues = []
    if with_stack < 1:
        issues.append(issue("medium", "projects", "no_stack", "Some projects do not state the technology stack. Name the languages, frameworks and tools you actually used in each project."))
    if described < 0.7:
        issues.append(issue("medium", "projects", "thin_descriptions", "Some project descriptions are too short to judge. Add 2-3 bullets covering what the project does and what you built."))
    if bullets and contribution < 0.6:
        issues.append(issue("medium", "projects", "unclear_contribution",
            "Some project descriptions describe the technology but do not clearly explain your contribution. "
            "Start bullets with what YOU built or decided (for example \"Designed...\", \"Implemented...\"); for team projects, say which part was yours."))
    if linked < 0.5:
        issues.append(issue("low", "projects", "no_links", "Few projects link to code or a live demo. If the work is public, add the link."))
    return {"score": min(100, score), "issues": issues, "count": n}


def analyze_resume(parsed: dict, raw_text: str, layout: dict, page_count: int) -> dict:
    """Run every section analyzer and combine them with the configured weights."""
    structure = structure_analyzer.analyze(parsed)
    skills = analyze_skills(parsed)
    experience = experience_analyzer.analyze(parsed)
    projects = analyze_projects(parsed)
    education = education_analyzer.analyze(parsed)
    contact = analyze_contact(parsed)
    formatting = formatting_analyzer.analyze(parsed, raw_text, layout, page_count)

    parts = {"structure": structure, "skills": skills, "experience": experience, "projects": projects,
             "education": education, "contact": contact, "formatting": formatting}
    section_scores = {k: int(round(v["score"])) for k, v in parts.items()}
    weights = config.normalised(config.ATS_WEIGHTS)
    overall = round(sum(weights[k] * section_scores[k] for k in weights))
    issues = [i for v in parts.values() for i in v["issues"]]
    return {
        "ats_score": overall,
        "section_scores": section_scores,
        "weights": {k: round(w, 3) for k, w in weights.items()},
        "details": {
            "sections_present": structure["present"],
            "skills_by_category": skills["by_category"],
            "skills_used_but_unlisted": skills["unlisted_but_used"],
            "experience": experience["details"],
            "education": education["details"],
            "word_count": formatting["word_count"],
            "page_count": formatting["page_count"],
        },
        "issues": issues,
    }
