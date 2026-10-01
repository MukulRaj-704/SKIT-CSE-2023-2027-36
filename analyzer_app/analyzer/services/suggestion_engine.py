"""
analyzer/services/suggestion_engine.py
======================================
Turns analyzer findings into prioritised, *authentic* suggestions.

Hard rule: never tell the candidate to claim a skill, role, number or
certification they may not have. Every suggestion that names a missing skill is
phrased conditionally ("if you have genuine experience ...") and offers learning
as the honest alternative. ``assert_authentic`` enforces that in tests.
"""

from __future__ import annotations

import re

from .common import PRIORITY_ORDER

FORBIDDEN = re.compile(r"\b(add|include|insert|put|list)\s+(?:the\s+)?(?:missing\s+)?[A-Z][A-Za-z+#.]+\s+to\s+your\s+(?:resume|skills)", re.I)


def _sug(priority, category, message):
    return {"priority": priority, "category": category, "message": message}


def general_suggestions(issues: list) -> list:
    """Deduplicate and sort the analyzers' issues into the public suggestion list."""
    seen, out = set(), []
    for i in sorted(issues, key=lambda x: (PRIORITY_ORDER[x["priority"]], -x.get("penalty", 0))):
        if i["code"] in seen:
            continue
        seen.add(i["code"])
        out.append(_sug(i["priority"], i["category"], i["message"]))
    return out


def job_suggestions(job: dict, parsed: dict, detail: dict) -> list:
    out = []
    missing = detail["skills"]["missing_details"]
    related = {r["job_skill"]: r["resume_skill"] for r in job["related_skills"]}
    loose = {lm["keyword"]: lm["found_instead"][0] for lm in job["loosely_mentioned_keywords"]}
    for m in missing:
        name = m["skill"]
        pri = "high" if m["required"] else "low"
        if name in loose:
            msg = (f"Your resume mentions \"{loose[name]}\" but not \"{name}\" explicitly. If the work you did genuinely was "
                   f"{name}, state that clearly in the relevant bullet; if it was not, {name} is a gap to learn rather than claim.")
            pri = "medium" if m["required"] else "low"
        elif name in related:
            msg = (f"{name} was not detected in your resume, but you list {related[name]}. If you have genuinely used "
                   f"{name} as well, say so explicitly; otherwise {related[name]} is a transferable skill you can point to honestly.")
        else:
            msg = (f"{name} was not detected in your resume. If you have genuine experience with {name}, consider adding it to "
                   f"your Skills section or to a relevant project description. If you do not, consider learning it if this "
                   f"role needs it, rather than adding it to your resume.")
        out.append(_sug(pri, "skills", msg))

    skill_names = {m["skill"] for m in missing}
    for lm in job["loosely_mentioned_keywords"]:
        kw, found = lm["keyword"], lm["found_instead"][0]
        if kw in skill_names:
            continue
        out.append(_sug("medium", "keywords",
            f"Your resume mentions \"{found}\" but not \"{kw}\" explicitly. If the work you did was {kw}, state that clearly in the relevant bullet."))

    shown = {m["skill"] for m in missing}
    other_kw = [k for k in job["missing_keywords"] if k not in shown and k not in {lm["keyword"] for lm in job["loosely_mentioned_keywords"]}]
    if other_kw:
        out.append(_sug("low", "keywords", "The job description uses these terms that your resume does not contain: "
                        f"{', '.join(other_kw[:6])}. Use the exact wording only where it truthfully describes your work."))

    for item in job["experience_match"]["items"]:
        if item["verdict"] == "partial":
            out.append(_sug("medium", "experience", f"{item['note']} Present what you have accurately (dates and scope) rather than rounding it up."))
        elif item["verdict"] == "missing_information":
            out.append(_sug("medium", "experience", f"{item['note']} If you have this experience, make the dates and technologies explicit in the relevant entry."))

    edu = job["education_match"]
    if edu["verdict"] in ("partial", "missing_information"):
        out.append(_sug("medium", "education", edu["note"]))

    for gap in job["semantic"]["gaps"][:3]:
        out.append(_sug("low", "relevance", f"No clear evidence in your resume for: \"{gap['requirement'][:140]}\". If you have relevant work, describe it explicitly; if not, this is a genuine gap."))

    if not out:
        out.append(_sug("low", "match", "Your resume already covers the skills, keywords and requirements detected in this job description."))
    out.sort(key=lambda s: PRIORITY_ORDER[s["priority"]])
    return out


def assert_authentic(suggestions: list) -> None:
    """Raise AssertionError when a suggestion tells the user to claim something unconditionally."""
    for s in suggestions:
        if FORBIDDEN.search(s["message"]):
            raise AssertionError(f"Unconditional 'add X to your resume' advice: {s['message']}")
