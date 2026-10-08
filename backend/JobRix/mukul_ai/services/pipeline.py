from __future__ import annotations

import re
from pathlib import Path

from resumes.models import ParseStatus
from resumes.services import ENGINE_VERSION, ResumeEngineError, parse_resume_instance, run_ats_analysis

def _resume_text(parsed):
    chunks = [parsed.get("raw_text", "")]
    contact = parsed.get("contact") or {}
    chunks.extend(str(contact.get(k, "")) for k in ("name", "email", "phone"))
    for section in ("summary", "skills", "education", "experience", "projects", "certifications"):
        value = parsed.get(section)
        if isinstance(value, list):
            for item in value:
                chunks.append(" ".join(str(v) for v in item.values()) if isinstance(item, dict) else str(item))
        elif value:
            chunks.append(str(value))
    return re.sub(r"\s+", " ", " ".join(chunks)).strip()

def semantic_match(parsed, job_description):
    resume_text = _resume_text(parsed)
    if not resume_text:
        raise ResumeEngineError("Parsed resume contains no text for semantic matching.")

    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode([resume_text, job_description], normalize_embeddings=True)
        score = float(embeddings[0] @ embeddings[1]) * 100.0
    except Exception as exc:
        raise ResumeEngineError(f"SBERT semantic matching failed: {exc}") from exc

    resume_skills = {
        str(item.get("name", "")).strip().lower()
        for item in parsed.get("skills") or []
        if isinstance(item, dict) and item.get("name")
    }
    jd_lower = job_description.lower()
    matched = sorted(skill for skill in resume_skills if skill and skill in jd_lower)

    terms = set(re.findall(r"[a-zA-Z][a-zA-Z+#.-]{2,}", jd_lower))
    stop = {"the","and","with","for","that","this","are","you","will","our","your","from","have","has","into","using"}
    missing = sorted(term for term in terms if term not in resume_text.lower() and term not in stop)[:20]

    return {
        "score": round(max(0.0, min(100.0, score)), 2),
        "engine": "SBERT: all-MiniLM-L6-v2",
        "matched_skills": matched,
        "missing_terms": missing,
    }

def run_complete_workflow(resume, job_description):
    if Path(resume.original_filename or resume.file.name).suffix.lower() != ".pdf":
        raise ResumeEngineError("Only PDF resumes are supported.")

    # TASK 1: parse the PDF once and persist the structured NLP result.
    if resume.parse_status != ParseStatus.PARSED or not resume.parsed_data:
        parse_resume_instance(resume)
        resume.refresh_from_db()

    if resume.parse_status != ParseStatus.PARSED or not resume.parsed_data:
        raise ResumeEngineError(resume.parse_error or "Resume could not be parsed.")

    # TASK 2: reuse the stored parsed resume for ATS scoring.
    ats = run_ats_analysis(resume.parsed_data, job_description)

    # TASK 3: reuse the same parsed resume for SBERT semantic matching.
    semantic = semantic_match(resume.parsed_data, job_description)

    final_score = round((float(ats["score"]) * 0.40) + (float(semantic["score"]) * 0.60), 2)

    return {
        "resume_parsing": resume.parsed_data,
        "ats": ats,
        "semantic": semantic,
        "job_match_score": final_score,
        "engine_version": ENGINE_VERSION,
    }
