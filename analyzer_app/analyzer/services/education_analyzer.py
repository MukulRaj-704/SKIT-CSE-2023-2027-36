"""analyzer/services/education_analyzer.py - education quality and JD education matching."""

from __future__ import annotations

import re

from .common import issue

_LEVELS = [
    (4, r"ph\.?\s?d|doctorate"),
    (3, r"m\.?\s?tech|m\.?\s?e\b|m\.?\s?sc|\bmba\b|\bmca\b|m\.?\s?s\b|master"),
    (2, r"b\.?\s?tech|b\.?\s?e\b|b\.?\s?sc|\bbca\b|\bbba\b|b\.?\s?s\b|bachelor|b\.?\s?com|undergraduate|\bbs\b"),
    (1, r"diploma"),
]
LEVEL_NAMES = {4: "doctorate", 3: "master's", 2: "bachelor's", 1: "diploma"}
CS_FIELD = re.compile(r"computer|information technology|\bit\b|software|data science|artificial intelligence|\bcse\b|\bece\b|electronics|informatics|computing", re.I)
STEM_FIELD = re.compile(r"engineering|technology|science|mathematics|statistics|physics", re.I)


def level_of(text: str | None) -> int:
    t = (text or "").lower()
    for level, pat in _LEVELS:
        if re.search(pat, t):
            return level
    return 0


def analyze(parsed: dict) -> dict:
    edu = parsed.get("education") or []
    if not edu:
        return {"score": 0, "issues": [], "details": {"present": False}}
    best = max(edu, key=lambda e: level_of(e.get("degree") or e.get("raw_text")))
    score = 40
    score += 25 if best.get("degree") else 0
    score += 20 if best.get("institution") else 0
    score += 15 if (best.get("end_date") or best.get("start_date")) else 0
    issues = []
    if not best.get("degree"):
        issues.append(issue("medium", "education", "no_degree", "Your Education section does not clearly state a degree (for example \"B.Tech in Computer Science\")."))
    if not (best.get("end_date") or best.get("start_date")):
        issues.append(issue("medium", "education", "no_grad_year", "No graduation year or study dates were detected in Education; add them."))
    return {"score": score, "issues": issues, "details": {"present": True, "highest_level": LEVEL_NAMES.get(level_of(best.get("degree") or best.get("raw_text")))}}


def match(parsed: dict, requirement: dict) -> dict:
    """requirement: {"level": int|0, "fields": [str], "text": str} from the JD parser."""
    if not requirement or not requirement.get("level"):
        return {"score": None, "verdict": "not_specified", "note": "The job description has no explicit education requirement."}
    edu = parsed.get("education") or []
    need = requirement["level"]
    if not edu:
        return {"score": 0, "verdict": "missing_information",
                "note": "No education was detected in the resume, so the requirement cannot be confirmed."}
    best = max(edu, key=lambda e: level_of(e.get("degree") or e.get("raw_text")))
    have = level_of(best.get("degree") or best.get("raw_text"))
    blob = " ".join(filter(None, [best.get("degree"), best.get("field_of_study"), best.get("raw_text")]))
    field_ok = (not requirement.get("fields")) or bool(CS_FIELD.search(blob)) or bool(STEM_FIELD.search(blob) and "engineering" in requirement.get("text", "").lower())
    if have == 0:
        return {"score": 0, "verdict": "missing_information",
                "note": "A degree level could not be detected in your Education section."}
    if have >= need and field_ok:
        return {"score": 100, "verdict": "strong", "note": f"Your {LEVEL_NAMES[have]} degree meets the requirement ({requirement['text'].strip()})."}
    if have >= need:
        return {"score": 70, "verdict": "partial", "note": "Your degree level meets the requirement, but the field of study could not be matched."}
    return {"score": 30, "verdict": "partial", "note": f"The job asks for a {LEVEL_NAMES[need]} degree; the highest detected is {LEVEL_NAMES[have]}."}
