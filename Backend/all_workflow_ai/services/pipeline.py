import re

from resumes.models import ParseStatus
from resumes.services import (
    ENGINE_VERSION,
    ResumeEngineError,
    parse_resume_instance,
    run_ats_analysis,
)


def build_resume_text(parsed_resume):
    text_parts = [parsed_resume.get("raw_text", "")]

    contact = parsed_resume.get("contact", {})
    if contact:
        text_parts.extend([
            str(contact.get("name", "")),
            str(contact.get("email", "")),
            str(contact.get("phone", "")),
        ])

    for section in [
        "summary",
        "skills",
        "education",
        "experience",
        "projects",
        "certifications",
    ]:
        data = parsed_resume.get(section)
        if not data:
            continue

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    text_parts.append(
                        " ".join(str(value) for value in item.values())
                    )
                else:
                    text_parts.append(str(item))
        else:
            text_parts.append(str(data))

    return re.sub(r"\s+", " ", " ".join(text_parts)).strip()


def semantic_job_matching(parsed_resume, job_description):
    resume_text = build_resume_text(parsed_resume)

    if not resume_text:
        raise ResumeEngineError(
            "Resume contains no text for semantic matching."
        )

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ResumeEngineError(
            "sentence-transformers is not installed. "
            "Run: pip install sentence-transformers"
        )

    try:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = model.encode(
            [resume_text, job_description],
            normalize_embeddings=True,
        )
        similarity = float(embeddings[0] @ embeddings[1])
        semantic_score = similarity * 100
    except Exception as exc:
        raise ResumeEngineError(
            f"SBERT semantic matching failed: {exc}"
        )

    resume_skills = set()
    for skill in parsed_resume.get("skills", []):
        if isinstance(skill, dict):
            name = skill.get("name")
            if name:
                resume_skills.add(name.strip().lower())
        elif isinstance(skill, str):
            resume_skills.add(skill.strip().lower())

    jd_lower = job_description.lower()
    matched_skills = sorted(
        skill for skill in resume_skills
        if skill and skill in jd_lower
    )

    jd_terms = set(
        re.findall(r"[a-zA-Z][a-zA-Z+#.-]{2,}", jd_lower)
    )
    stop_words = {
        "the", "and", "with", "for", "that", "this", "are",
        "you", "will", "our", "your", "from", "have", "has",
        "into", "using",
    }

    resume_lower = resume_text.lower()
    missing_terms = sorted(
        term for term in jd_terms
        if term not in resume_lower and term not in stop_words
    )[:20]

    return {
        "score": round(max(0, min(100, semantic_score)), 2),
        "engine": "SBERT: all-MiniLM-L6-v2",
        "matched_skills": matched_skills,
        "missing_terms": missing_terms,
    }


def run_complete_workflow(resume, job_description):
    if (
        resume.parse_status != ParseStatus.PARSED
        or not resume.parsed_data
    ):
        parse_resume_instance(resume)
        resume.refresh_from_db()

    if (
        resume.parse_status != ParseStatus.PARSED
        or not resume.parsed_data
    ):
        raise ResumeEngineError(
            resume.parse_error or "Resume parsing failed."
        )

    parsed_resume = resume.parsed_data

    ats_result = run_ats_analysis(
        parsed_resume,
        job_description,
    )

    semantic_result = semantic_job_matching(
        parsed_resume,
        job_description,
    )

    ats_score = float(ats_result["score"])
    semantic_score = float(semantic_result["score"])

    final_job_match_score = round(
        ats_score * 0.40 + semantic_score * 0.60,
        2,
    )

    return {
        "resume_parsing": parsed_resume,
        "ats": ats_result,
        "semantic": semantic_result,
        "job_match_score": final_job_match_score,
        "engine_version": ENGINE_VERSION,
    }
