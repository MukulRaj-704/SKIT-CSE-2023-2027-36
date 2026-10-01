"""
analyzer/services/skill_matcher.py
==================================
Skill-level comparison. Three outcomes per JD skill:

* matched  - on the resume (listed, used in text, or deterministically implied)
* related  - a *different but close* skill is on the resume (half credit, never
             reported as a match)
* missing  - nothing close found
"""

from __future__ import annotations

from . import skills_taxonomy as tax
from .common import context_skills, listed_skills, project_text

REQUIRED_W, PREFERRED_W, RELATED_CREDIT = 1.0, 0.5, 0.5


def match_skills(parsed: dict, required: list, preferred: list) -> dict:
    listed, ctx = listed_skills(parsed), context_skills(parsed)
    have = set(listed) | set(ctx)
    matched, missing, related, weights = [], [], [], []
    earned = total = 0.0
    by_cat: dict = {}

    for skill, weight in [(s, REQUIRED_W) for s in required] + [(s, PREFERRED_W) for s in preferred]:
        total += weight
        cat = tax.category_of(skill)
        slot = by_cat.setdefault(cat, {"matched": 0, "total": 0})
        slot["total"] += 1
        shown = tax.display_name(skill)
        via = tax.implied_by(skill, have)
        if skill in have or via:
            earned += weight
            slot["matched"] += 1
            where = "skills section" if skill in listed else ("experience/projects" if skill in ctx else f"implied by {tax.display_name(via)}")
            matched.append({"skill": shown, "found_in": where, "required": weight == REQUIRED_W})
            continue
        close = sorted(tax.related_to(skill) & have)
        if close:
            earned += weight * RELATED_CREDIT
            related.append({"job_skill": shown, "resume_skill": tax.display_name(close[0]),
                            "note": f"{shown} was not found, but you list {tax.display_name(close[0])}, a closely related skill."})
        missing.append({"skill": shown, "required": weight == REQUIRED_W, "category": cat})

    return {
        "skill_score": round(100 * earned / total) if total else None,
        "matched_skills": [m["skill"] for m in matched],
        "matched_details": matched,
        "missing_skills": [m["skill"] for m in missing],
        "missing_details": missing,
        "related_skills": related,
        "by_category": by_cat,
    }


def project_relevance(parsed: dict, required: list) -> int | None:
    """% of the JD's required skills evidenced inside the resume's projects."""
    if not required:
        return None
    projects = parsed.get("projects") or []
    if not projects:
        return 0
    in_proj = set(tax.find_skills(project_text(parsed)))
    in_proj |= {i for s in list(in_proj) for i in tax.IMPLIES.get(s, ())}
    return round(100 * sum(1 for s in required if s in in_proj) / len(required))
