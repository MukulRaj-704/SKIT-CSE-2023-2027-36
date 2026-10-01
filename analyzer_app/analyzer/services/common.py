"""
analyzer/services/common.py
===========================
Small helpers shared by the analyzers: the issue record, resume text views and
date arithmetic.
"""

from __future__ import annotations

import datetime as dt
import re

from . import skills_taxonomy as tax

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

ACTION_VERBS = set(
    """achieved analyzed analysed architected automated built collaborated configured created
    delivered deployed designed developed devised engineered enhanced established evaluated
    executed implemented improved integrated launched led managed migrated modeled modelled
    optimized optimised orchestrated organized organised owned planned processed produced
    refactored reduced researched resolved reviewed scaled shipped simplified streamlined
    strengthened tested trained transformed validated wrote coordinated mentored maintained
    monitored supported drove initiated spearheaded fine-tuned tuned debugged documented
    published presented contributed leveraged applied conducted performed prepared""".split()
)


def issue(priority: str, category: str, code: str, message: str, penalty: int = 0) -> dict:
    return {"priority": priority, "category": category, "code": code, "message": message, "penalty": penalty}


def all_experience(parsed: dict) -> list:
    """Work experience and internships together (both are real experience)."""
    return list(parsed.get("experience") or []) + list(parsed.get("internships") or [])


def experience_text(parsed: dict) -> str:
    return "\n".join(e.get("raw_text", "") for e in all_experience(parsed))


def project_text(parsed: dict) -> str:
    return "\n".join(p.get("raw_text", "") for p in parsed.get("projects") or [])


def listed_skills(parsed: dict) -> dict:
    """canonical name -> display name, from the Skills section."""
    out = {}
    for s in parsed.get("skills") or []:
        canon = tax.canonical(s["name"])
        if canon:
            out[canon] = s["name"]
    return out


def context_skills(parsed: dict) -> dict:
    """canonical skill -> mentions in experience/projects/summary prose."""
    text = "\n".join([experience_text(parsed), project_text(parsed), parsed.get("summary") or ""])
    return dict(tax.find_skills(text))


def is_action_bullet(bullet: str) -> bool:
    words = re.findall(r"[A-Za-z\-]+", bullet or "")
    if not words:
        return False
    first = words[0].lower()
    return first in ACTION_VERBS or (first.endswith("ed") and len(first) > 4)


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_PRESENT = re.compile(r"present|current|ongoing|now|till date", re.I)


def parse_date(token: str | None, *, end: bool = False, today: dt.date | None = None) -> dt.date | None:
    """'05/2026', 'Jan 2022', '2021', 'Present' -> date (year-only: Jan for start, Dec for end)."""
    if not token:
        return None
    today = today or dt.date.today()
    t = token.strip()
    if _PRESENT.search(t):
        return today
    m = re.search(r"(\d{1,2})\s*[/.-]\s*((?:19|20)\d{2})", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return dt.date(int(m.group(2)), int(m.group(1)), 1)
    m = re.search(r"([A-Za-z]{3})[a-z]*\.?\s*,?\s*((?:19|20)\d{2})", t)
    if m and m.group(1).lower() in _MONTHS:
        return dt.date(int(m.group(2)), _MONTHS[m.group(1).lower()], 1)
    m = re.search(r"((?:19|20)\d{2})", t)
    if m:
        return dt.date(int(m.group(1)), 12 if end else 1, 1)
    return None


def date_format(token: str | None) -> str | None:
    if not token or _PRESENT.search(token):
        return None
    if re.search(r"\d{1,2}\s*[/.-]\s*(19|20)\d{2}", token):
        return "MM/YYYY"
    if re.search(r"[A-Za-z]{3}", token):
        return "Mon YYYY"
    if re.fullmatch(r"\s*(19|20)\d{2}\s*", token):
        return "YYYY"
    return None


def entry_interval(entry: dict, today: dt.date | None = None):
    today = today or dt.date.today()
    start = parse_date(entry.get("start_date"), today=today)
    end = parse_date(entry.get("end_date"), end=True, today=today)
    if not start:
        return None
    end = min(end or today, today)
    if end < start:
        return None
    return start, end


def months_between(start: dt.date, end: dt.date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month) + 1  # inclusive


def merged_months(intervals: list) -> int:
    """Total months covered by (start, end) intervals without double counting."""
    if not intervals:
        return 0
    intervals = sorted(intervals)
    total, (cs, ce) = 0, intervals[0]
    for s, e in intervals[1:]:
        if s <= ce:
            ce = max(ce, e)
        else:
            total += months_between(cs, ce)
            cs, ce = s, e
    return total + months_between(cs, ce)
