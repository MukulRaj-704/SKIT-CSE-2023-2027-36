"""
analyzer/services/keyword_matcher.py
====================================
Keyword coverage: which job-description terms appear *anywhere* in the resume
(skills list, experience, projects), after normalising spelling variants.
"""

from __future__ import annotations

import re

from . import skills_taxonomy as tax


def _phrase_present(phrase: str, text: str) -> bool:
    words = [re.escape(w) for w in phrase.split()]
    return bool(re.search(r"(?<![A-Za-z0-9])" + r"[\s\-]+".join(words) + r"s?(?![A-Za-z0-9])", text, re.I))


def match_keywords(jd_keywords: list, resume_text: str) -> dict:
    resume_skills = set(tax.find_skills(resume_text))
    implied = {i for s in list(resume_skills) for i in tax.IMPLIES.get(s, ())}
    matched, missing, partial = [], [], []
    for kw in dict.fromkeys(jd_keywords):  # dedupe, keep order
        if kw in tax.SKILLS:
            ok = kw in resume_skills or kw in implied
        else:
            ok = _phrase_present(kw, resume_text)
        shown = tax.display_name(kw) if kw in tax.SKILLS else kw
        if ok:
            matched.append(shown)
        else:
            missing.append(shown)
            hints = [h for h in tax.HINTS.get(kw, ()) if _phrase_present(h, resume_text)]
            if hints:
                partial.append({"keyword": shown, "found_instead": hints[:2]})
    total = len(matched) + len(missing)
    return {
        "keyword_score": round(100 * len(matched) / total) if total else None,
        "matched_keywords": matched,
        "missing_keywords": missing,
        "loosely_mentioned": partial,
    }
