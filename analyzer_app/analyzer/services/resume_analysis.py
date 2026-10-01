"""
analyzer/services/resume_analysis.py
====================================
Facade used by the views. Three entry points, matching the workflow:

    ingest_resume()   upload bytes   -> parsed resume + raw text + layout signals
    analyze_general() stored resume  -> Mode 1 (ATS score, section scores, suggestions)
    analyze_job()     stored resume + JD -> Mode 2 (Mode 1 + job analysis)
"""

from __future__ import annotations

from . import ats_scorer, job_matcher, resume_parser, suggestion_engine, text_extractor


def ingest_resume(filename: str, data: bytes) -> dict:
    doc = text_extractor.extract_document(filename, data)
    parsed = resume_parser.parse_resume_text(doc.text, doc.links)
    warnings = []
    if not parsed["skills"]:
        warnings.append("No Skills section was detected.")
    if not parsed["detected_sections"]:
        warnings.append("No standard section headings were recognised; parsing results may be incomplete.")
    return {
        "file_type": doc.file_type,
        "page_count": doc.page_count,
        "raw_text": doc.text,
        "layout": doc.layout,
        "parsed": parsed,
        "warnings": warnings,
    }


def analyze_general(parsed: dict, raw_text: str, layout: dict, page_count: int) -> dict:
    result = ats_scorer.analyze_resume(parsed, raw_text, layout, page_count)
    suggestions = suggestion_engine.general_suggestions(result.pop("issues"))
    return {"resume_analysis": result, "suggestions": suggestions}


def analyze_job(parsed: dict, raw_text: str, layout: dict, page_count: int,
                job_description: str, job_title: str = "", company: str = "") -> dict:
    general = analyze_general(parsed, raw_text, layout, page_count)
    job = job_matcher.match_job(parsed, raw_text, job_description, job_title, company)
    detail = job.pop("_detail")
    job["suggestions"] = suggestion_engine.job_suggestions(job, parsed, detail)
    return {**general, "job_analysis": job}
