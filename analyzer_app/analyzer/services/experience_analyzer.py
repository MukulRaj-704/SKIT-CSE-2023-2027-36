"""
analyzer/services/experience_analyzer.py
========================================
(1) General experience quality (Mode 1) and (2) resume-vs-JD experience matching
(Mode 2). Nothing here invents experience: unknown dates stay "unknown".
"""

from __future__ import annotations

import datetime as dt
import re

from . import skills_taxonomy as tax
from .common import all_experience, entry_interval, issue, is_action_bullet, merged_months


# ---------------------------------------------------------------------------
# Mode 1 - general quality
# ---------------------------------------------------------------------------


def analyze(parsed: dict) -> dict:
    entries = all_experience(parsed)
    if not entries:
        return {
            "score": 0,
            "entries": 0,
            "issues": [],  # the structure analyzer already reports the missing section
            "details": {"present": False},
        }
    n = len(entries)
    complete = sum(1 for e in entries if e.get("title") and e.get("company") and e.get("start_date")) / n
    bullets = [b for e in entries for b in e.get("bullets", [])]
    avg_bullets = len(bullets) / n
    action = (sum(is_action_bullet(b) for b in bullets) / len(bullets)) if bullets else 0
    with_tech = sum(1 for e in entries if tax.find_skills(e.get("raw_text", ""))) / n
    quantified = (sum(bool(re.search(r"\d", b)) for b in bullets) / len(bullets)) if bullets else 0

    score = round(
        35 + 20 * complete + 10 * min(1, avg_bullets / 2) + 15 * action + 10 * with_tech + 10 * min(1, quantified / 0.4)
    )
    issues = []
    if complete < 1:
        issues.append(issue("medium", "experience", "incomplete_entries",
            "Some experience entries are missing a title, company or start date. Each role should state "
            "the job title, employer and dates."))
    if not bullets:
        issues.append(issue("high", "experience", "no_bullets",
            "Your experience entries have no description bullets. Describe what you actually did in each role, "
            "starting each bullet with an action verb."))
    else:
        if action < 0.6:
            issues.append(issue("medium", "experience", "weak_verbs",
                "Several experience bullets do not start with an action verb (for example \"Built\", \"Automated\", "
                "\"Designed\"). Rewrite them to state what you did."))
        if with_tech < 0.7:
            issues.append(issue("medium", "experience", "no_tech_mentions",
                "Some experience entries do not name the technologies you used. Mention the tools you genuinely used in each role."))
        if quantified == 0:
            issues.append(issue("low", "experience", "no_numbers",
                "None of your experience bullets include a measurable detail. If you have real figures "
                "(data size, users, time saved), add them; do not estimate or invent numbers."))
    months = total_months(parsed)
    return {
        "score": min(100, score),
        "entries": n,
        "issues": issues,
        "details": {"present": True, "total_months": months, "action_verb_ratio": round(action, 2), "quantified_ratio": round(quantified, 2)},
    }


# ---------------------------------------------------------------------------
# Time arithmetic
# ---------------------------------------------------------------------------


def total_months(parsed: dict, today: dt.date | None = None) -> int | None:
    """Months of dated experience (None when no entry has a readable date)."""
    ivs = [iv for e in all_experience(parsed) if (iv := entry_interval(e, today))]
    return merged_months(ivs) if ivs else None


def skill_months(parsed: dict, skill: str, today: dt.date | None = None) -> int | None:
    """Months of dated entries that mention ``skill`` (None: skill not in experience)."""
    ivs, mentioned = [], False
    for e in all_experience(parsed):
        if skill in tax.find_skills(e.get("raw_text", "")):
            mentioned = True
            if iv := entry_interval(e, today):
                ivs.append(iv)
    if not mentioned:
        return None
    return merged_months(ivs) if ivs else 0


# ---------------------------------------------------------------------------
# Mode 2 - JD matching
# ---------------------------------------------------------------------------


def match(parsed: dict, requirements: list, today: dt.date | None = None) -> dict:
    """
    requirements: [{"years": 2, "skill": "django" | None, "text": "..."}]
    Verdicts: explicit | partial | missing_information | not_met
    """
    if not requirements:
        return {"score": None, "items": [], "total_experience_years": None}
    total = total_months(parsed, today)
    items, scores = [], []
    for req in requirements:
        need_m = req["years"] * 12
        skill = req.get("skill")
        have = skill_months(parsed, skill, today) if skill else total
        label = tax.display_name(skill) if skill else "relevant"
        if have is None and not skill and all_experience(parsed):
            verdict, score = "missing_information", 0
            note = "Your experience entries have no readable dates, so the duration cannot be verified."
        elif have is None:
            ctx_in_projects = skill and skill in tax.find_skills("\n".join(p.get("raw_text", "") for p in parsed.get("projects", [])))
            if ctx_in_projects:
                verdict, score = "partial", 35
                note = f"{label} appears in your projects but not in dated work experience."
            else:
                verdict, score = "missing_information", 0
                note = f"No {label} experience was detected, so this requirement cannot be confirmed from the resume."
        elif have == 0 or (total is None and not skill):
            verdict, score = "missing_information", 0
            note = "Your experience entries have no readable dates, so the duration cannot be verified."
        elif have >= need_m:
            verdict, score, note = "explicit", 100, f"About {have / 12:.1f} year(s) of {label} experience detected (needs {req['years']}+)."
        else:
            verdict = "partial"
            score = max(40, round(100 * have / need_m))
            note = f"About {have / 12:.1f} year(s) of {label} experience detected; the job asks for {req['years']}+."
        scores.append(score)
        items.append({"requirement": req["text"], "required_years": req["years"], "skill": tax.display_name(skill) if skill else None,
                      "detected_years": None if have is None else round(have / 12, 1), "verdict": verdict, "note": note})
    return {
        "score": round(sum(scores) / len(scores)),
        "items": items,
        "total_experience_years": None if total is None else round(total / 12, 1),
    }
