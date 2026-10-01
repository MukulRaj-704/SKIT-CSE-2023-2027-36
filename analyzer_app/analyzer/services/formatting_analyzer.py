"""
analyzer/services/formatting_analyzer.py
========================================
Heuristic ATS-compatibility checks. Every finding is phrased as a *potential*
issue: none of these guarantees rejection by an ATS.
"""

from __future__ import annotations

import re

from .common import date_format, issue, all_experience

PREFIX = "Potential ATS compatibility issue: "
_SYMBOLS = re.compile(r"[★☆●◆◇►➢✔✓❖■□▪※→←☎✉✆♦◦▶]")


def analyze(parsed: dict, raw_text: str, layout: dict, page_count: int) -> dict:
    issues, score = [], 100
    words = len(raw_text.split())

    def hit(penalty, priority, code, msg):
        nonlocal score
        score -= penalty
        issues.append(issue(priority, "formatting", code, PREFIX + msg, penalty))

    if layout.get("multi_column"):
        hit(15, "medium", "multi_column",
            "a multi-column layout was detected; some ATS read columns out of order and mix up sections.")
    if layout.get("tables"):
        hit(10, "medium", "tables",
            f"the document contains {layout['tables']} table(s); content inside tables can be skipped or reordered by some ATS.")
    if layout.get("text_boxes"):
        hit(10, "medium", "text_boxes", "text boxes were detected; text inside them is often ignored by ATS parsers.")
    if (layout.get("images") or 0) > 3:
        hit(5, "low", "images", "the document contains several images/graphics; ATS cannot read text drawn as images.")

    if raw_text.count("\ufffd") > 3 or re.search(r"[\u0000-\u0008]", raw_text):
        hit(15, "high", "garbled_text", "text extraction produced garbled characters; the font encoding may not be readable by ATS.")

    symbols = len(_SYMBOLS.findall(raw_text))
    if symbols > 12:
        hit(8, "low", "symbols", f"many decorative symbols were found ({symbols}); stick to simple bullets (-, •).")

    long_paras = [t for t in [parsed.get("summary") or ""] + [b for e in all_experience(parsed) for b in e.get("bullets", [])]
                  + [b for p in parsed.get("projects", []) for b in p.get("bullets", [])] if len(t.split()) > 60]
    if long_paras:
        hit(8, "low", "long_paragraphs",
            f"{len(long_paras)} very long paragraph/bullet(s) (60+ words); shorter bullets are easier for ATS and recruiters to scan.")

    if parsed.get("unknown_headings"):
        names = ", ".join(f'"{h}"' for h in parsed["unknown_headings"][:3])
        hit(min(12, 4 * len(parsed["unknown_headings"])), "low", "unusual_headings",
            f"unusual section heading(s) {names}; use standard headings such as Skills, Experience, Education and Projects.")

    found = len(parsed.get("detected_sections") or [])
    if found == 0:
        hit(25, "high", "no_sections", "no standard section headings (Skills, Experience, Education, Projects) were recognised.")
    elif found < 3:
        hit(12, "medium", "few_sections", f"only {found} standard section heading(s) were recognised; use standard headings so ATS can organise your content.")

    formats = {date_format(d) for e in all_experience(parsed) for d in (e.get("start_date"), e.get("end_date"))} - {None}
    if len(formats) > 1:
        hit(5, "low", "date_formats", f"inconsistent date formats ({', '.join(sorted(formats))}); pick one format and use it everywhere.")

    if words < 150:
        hit(10, "medium", "very_short", f"the resume is very short ({words} words); ATS has little content to match against.")
    elif words > 1200 or page_count > 2:
        hit(8, "low", "very_long", f"the resume is very long ({words} words, ~{page_count} pages); most resumes work best within 1-2 pages.")

    return {"score": max(0, score), "issues": issues, "word_count": words, "page_count": page_count}
