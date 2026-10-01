"""
analyzer/services/jd_parser.py
==============================
Job description text -> structured requirements.

Skills are found with the shared taxonomy, so "REST APIs", "RESTful API" and
"REST API development" all normalise to the same ``rest api`` term.
"""

from __future__ import annotations

import re
from collections import Counter

from . import skills_taxonomy as tax
from .education_analyzer import _LEVELS, level_of

_PREFERRED_HEAD = re.compile(r"preferred|nice to have|good to have|bonus|plus\b|desirable|added advantage|optional", re.I)
_REQUIRED_HEAD = re.compile(r"requirements?|must have|required|qualifications?|what you.?ll need|you have|skills|who you are|mandatory|key skills", re.I)
_RESP_HEAD = re.compile(r"responsibilit|what you.?ll do|your role|duties|you will|day[- ]to[- ]day|the role|about the role", re.I)
_BULLET = re.compile(r"^\s*(?:[-•*\u2022▪►➢✓]|\d+[.)])\s*")

_YEARS_RE = re.compile(
    r"(?P<lo>\d{1,2})\s*(?:\+|-\s*(?P<hi>\d{1,2})|to\s*(?P<hi2>\d{1,2}))?\s*(?:\+\s*)?(?:years?|yrs?)(?:\s+of)?"
    r"(?:\s+(?:relevant|professional|hands[- ]on|industry|work|working|proven|practical|total|overall))*"
    r"(?:\s+experience)?(?:\s+(?:in|with|of|on|using))?\s*(?P<tail>[^.;\n\d]{0,60})",
    re.I,
)
_FRESHER = re.compile(r"\b(fresher|freshers|entry[- ]level|new grad(?:uate)?s?|graduate engineer|0\s*-\s*1\s*years?|no experience required|internship)\b", re.I)
_EDU_RE = re.compile(r"(?:bachelor|master|ph\.?d|b\.?\s?tech|m\.?\s?tech|b\.?\s?e\b|m\.?\s?sc|b\.?\s?sc|\bmca\b|\bbca\b|\bmba\b|diploma|degree|graduate)[^.\n;]{0,90}", re.I)
_FIELDS = re.compile(r"computer science|information technology|software engineering|engineering|data science|mathematics|statistics|related field|\bcse\b|\bit\b", re.I)
_STOP = set("""a an the and or of to in for with on at as by is are be we you our your will can this that from
 who what job role team work years experience strong ability including such etc must should have has more
 looking join company candidate responsibilities requirements preferred plus skills using use used
 good great new help build make across within into other their they them about able both also any all""".split())


def _split_lines(jd: str) -> list:
    return [ln.strip() for ln in re.split(r"\n+", jd) if ln.strip()]


def _classify_lines(lines: list) -> list:
    """[(line, bucket)] where bucket in required|preferred|responsibility|other."""
    out, mode = [], "other"
    for ln in lines:
        stripped = _BULLET.sub("", ln)
        is_heading = len(stripped) < 60 and (stripped.endswith(":") or stripped.isupper() or len(stripped.split()) <= 5) and not _BULLET.match(ln)
        if is_heading:
            if _PREFERRED_HEAD.search(stripped):
                mode = "preferred"
            elif _RESP_HEAD.search(stripped):
                mode = "responsibility"
            elif _REQUIRED_HEAD.search(stripped):
                mode = "required"
            else:
                mode = "other"
            if stripped.endswith(":") and len(stripped.split()) <= 5:
                continue
        bucket = mode
        # Inline cues inside a normal sentence/bullet override the section mode.
        if _PREFERRED_HEAD.search(stripped) and not stripped.lower().startswith(("requirements", "required")):
            bucket = "preferred"
        elif re.match(r"^\s*(?:required\s*)?(?:skills?|requirements?|stack|technologies)\s*[:\-]", stripped, re.I):
            bucket = "required"
        out.append((stripped, bucket))
    return out


def parse_education(jd: str) -> dict:
    m = _EDU_RE.search(jd)
    if not m:
        return {"level": 0, "fields": [], "text": ""}
    text = m.group(0).strip()
    level = level_of(text)
    if not level and re.search(r"degree|graduate", text, re.I):
        level = 2
    fields = sorted({f.group(0).lower() for f in _FIELDS.finditer(m.group(0) + " " + jd[m.end():m.end() + 80])})
    return {"level": level, "fields": [f for f in fields if f not in ("related field",)], "text": text}


def parse_experience(jd: str) -> list:
    reqs = []
    for m in _YEARS_RE.finditer(jd):
        years = int(m.group("lo"))
        if not 0 < years <= 20:
            continue
        # Stop the skill window at "and"/","/digits so "2+ years of Django and 3-5 years ..." stays two requirements.
        tail = re.split(r"\band\b|,|\d|\bor\b", m.group("tail") or "")[0]
        skills = list(tax.find_skills(tail))
        phrase = m.group(0).replace(m.group("tail") or "", tail).strip()
        reqs.append({"years": years, "skill": skills[0] if skills else None, "text": re.sub(r"\s+", " ", phrase).strip(" ,.")})
    seen, out = set(), []
    for r in reqs:
        key = (r["years"], r["skill"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _top_phrases(jd: str, limit: int = 10) -> list:
    """Frequent two-word phrases (>=2 mentions) that are not already taxonomy skills."""
    words = [w for w in re.findall(r"[a-z][a-z0-9+#.\-]{2,}", jd.lower())]
    freq = Counter()
    for a, b in zip(words, words[1:]):
        if a not in _STOP and b not in _STOP:
            freq[f"{a} {b}"] += 1
    known = set()
    for s in tax.find_skills(jd):
        known.update(s.split())
    return [p for p, c in freq.most_common() if c >= 2 and not (set(p.split()) <= known)][:limit]


def parse_job_description(jd: str, title: str = "", company: str = "") -> dict:
    lines = _classify_lines(_split_lines(jd))
    required, preferred, resp, other = {}, {}, [], {}
    req_lines = []
    for text, bucket in lines:
        found = tax.find_skills(text)
        if bucket == "preferred":
            target = preferred
        elif bucket in ("required", "responsibility"):
            target = required
        else:
            target = other
        for sk, n in found.items():
            target[sk] = target.get(sk, 0) + n
        if bucket == "responsibility" and len(text.split()) >= 4:
            resp.append(text)
        if bucket == "required" and len(text.split()) >= 3:
            req_lines.append(text)
    # Skills mentioned only in untitled prose count as required; a skill that is
    # both required and preferred stays required.
    for sk, n in other.items():
        required.setdefault(sk, n)
    for sk in list(preferred):
        if sk in required:
            preferred.pop(sk)

    all_skills = {**required, **preferred}
    tech = [s for s in all_skills if tax.is_technical(s)]
    soft = [s for s in all_skills if not tax.is_technical(s)]
    technical_required = [s for s in required if tax.is_technical(s)]
    technical_preferred = [s for s in preferred if tax.is_technical(s)]

    if not resp:  # no explicit responsibilities heading: use action-like sentences
        resp = [t for t, _ in lines if re.match(r"^(?:build|develop|design|implement|work|collaborate|deploy|maintain|create|manage|write|own|lead|analy[sz]e|optimi[sz]e|integrate|ensure|support|participate|contribute)", t, re.I)]

    return {
        "job_title": title or None,
        "company": company or None,
        "required_skills": technical_required,
        "preferred_skills": technical_preferred,
        "technologies": tech,
        "soft_skills": soft,
        "keywords": list(dict.fromkeys([*all_skills, *_top_phrases(jd)])),
        "experience_requirements": parse_experience(jd),
        "fresher_friendly": bool(_FRESHER.search(jd)),
        "education_requirement": parse_education(jd),
        "responsibilities": resp[:15],
        "requirement_lines": req_lines[:15],
        "has_recognised_skills": bool(tech),
    }
