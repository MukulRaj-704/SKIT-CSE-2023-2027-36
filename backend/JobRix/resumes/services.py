"""
resumes/services.py
===================
The only module that talks to the ``resume_parser`` engine
(``Backend/resume_parser``).

Isolating it means: Django never imports the heavy PDF/NLP stack at module
import time, a missing engine degrades into a clear domain error instead of a
500, and the scoring flow can later move to a worker without touching models,
serializers or views.

Flow (parse once):
    Resume row + file --parse_resume_instance()--> Resume.parsed_data (JSON)
Flow (reuse, never re-read the PDF):
    stored JSON --parsed_resume_from_dict()--> ParsedResume --load_parsed()-->
    pipeline.run_ats(job_description) --> score / matched / missing / suggestions
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from .models import ParseStatus, Resume

logger = logging.getLogger(__name__)

# The engine does not expose a version number; stamp analyses with the component
# we call so score changes can be traced back to engine upgrades.
ENGINE_VERSION = "resume_parser.ats/1.0"


class ResumeEngineError(RuntimeError):
    """The engine ran but could not produce a result (e.g. unreadable PDF)."""


class ResumeEngineUnavailableError(ResumeEngineError):
    """The engine itself cannot be used on this server (not installed)."""


def engine_status() -> tuple[bool, str]:
    """Cheap import probe used by ``ResumesConfig.ready()`` to log readiness."""
    try:
        import resume_parser  # noqa: F401
    except Exception as exc:
        return False, str(exc)
    return True, ENGINE_VERSION


def build_pipeline():
    """Return a ``ResumePipeline`` honouring ``settings.RESUME_PARSE_SPACY``."""
    try:
        from resume_parser import ResumePipeline
    except Exception as exc:  # pragma: no cover - environment dependent
        raise ResumeEngineUnavailableError(
            "The resume parsing engine is not importable. Install it with "
            "`pip install -e Backend/resume_parser/resume_parser` (needs pymupdf)."
        ) from exc

    try:
        from resume_parser.parser.common_parser import CommonResumeParser
        import importlib.util

        # Prefer spaCy when the operator asked for it *and* it is installed;
        # otherwise stay on the regex fallback without spamming a warning.
        load_spacy = bool(settings.RESUME_PARSE_SPACY) and (
            importlib.util.find_spec("spacy") is not None
        )
        parser = CommonResumeParser(load_spacy=load_spacy)
        return ResumePipeline(parser=parser)
    except Exception:  # pragma: no cover - fall back to engine defaults
        logger.debug("Using ResumePipeline defaults (custom parser unavailable).")
        return ResumePipeline()


def parsed_resume_from_dict(parsed_data: dict):
    """Rebuild the engine dataclasses from stored JSON (never re-reads the PDF)."""
    import dataclasses

    if not parsed_data:
        raise ResumeEngineError("This resume has no parsed data to score against.")
    try:
        from resume_parser import models as engine_models
    except Exception as exc:
        raise ResumeEngineUnavailableError(
            "The resume parsing engine is not importable."
        ) from exc

    def build(model_cls, data):
        known = {field.name for field in dataclasses.fields(model_cls)}
        return {k: v for k, v in (data or {}).items() if k in known}

    d = parsed_data
    return engine_models.ParsedResume(
        contact=engine_models.ContactInfo(
            **build(engine_models.ContactInfo, d.get("contact"))
        ),
        summary=d.get("summary"),
        skills=[
            engine_models.Skill(**build(engine_models.Skill, item))
            for item in d.get("skills") or []
        ],
        education=[
            engine_models.Education(**build(engine_models.Education, item))
            for item in d.get("education") or []
        ],
        experience=[
            engine_models.Experience(**build(engine_models.Experience, item))
            for item in d.get("experience") or []
        ],
        projects=[
            engine_models.Project(**build(engine_models.Project, item))
            for item in d.get("projects") or []
        ],
        certifications=[
            engine_models.Certification(**build(engine_models.Certification, item))
            for item in d.get("certifications") or []
        ],
        raw_text=d.get("raw_text") or "",
        detected_sections=d.get("detected_sections") or {},
    )


def parse_pdf_bytes(pdf_bytes: bytes) -> dict:
    """Parse a PDF exactly once and return its ``ParsedResume`` as a plain dict."""
    import dataclasses

    if not pdf_bytes:
        raise ResumeEngineError("The uploaded document is empty.")
    pipeline = build_pipeline()
    try:
        parsed = pipeline.load(pdf_bytes=pdf_bytes)
    except Exception as exc:
        raise ResumeEngineError(f"Could not parse the PDF: {exc}") from exc
    return dataclasses.asdict(parsed)


def _persist(resume: Resume, status: str, error: str, data: dict) -> None:
    resume.parse_status = status
    resume.parse_error = error[:2000]
    resume.parsed_data = data
    resume.parsed_at = timezone.now() if status == ParseStatus.PARSED else None
    resume.save(
        update_fields=[
            "parse_status",
            "parse_error",
            "parsed_data",
            "parsed_at",
            "updated_at",
        ]
    )


def parse_resume_instance(resume: Resume) -> Resume:
    """
    Parse ``resume.file`` once and persist the outcome on the row.

    The upload endpoint must always be able to answer 201 with the stored row,
    so *no* engine problem raises here:

    * engine unavailable -> row stays ``pending`` with an explanatory
      ``parse_error`` (retry later with POST .../reparse/)
    * engine ran but the PDF is unusable -> row becomes ``failed``
    * success -> ``parsed`` + the engine result in ``parsed_data``
    """
    try:
        with resume.file.open("rb") as handle:
            parsed_data = parse_pdf_bytes(handle.read())
    except ResumeEngineUnavailableError as exc:
        logger.warning("Resume %s not parsed: %s", resume.pk, exc)
        _persist(resume, ParseStatus.PENDING, f"engine unavailable: {exc}", {})
        return resume
    except ResumeEngineError as exc:
        logger.warning("Resume %s failed to parse: %s", resume.pk, exc)
        _persist(resume, ParseStatus.FAILED, str(exc), {})
        return resume

    _persist(resume, ParseStatus.PARSED, "", parsed_data)
    logger.info("Resume %s parsed: %s skill(s).", resume.pk, len(resume.skill_names))
    return resume


def run_ats_analysis(parsed_data: dict, job_description: str) -> dict:
    """
    Score a stored parse against a job description; the PDF is never touched.

    Returns the fields needed to build an ``ATSAnalysis`` row.
    """
    pipeline = build_pipeline()
    pipeline.load_parsed(parsed_resume_from_dict(parsed_data))
    try:
        result = pipeline.run_ats(job_description=job_description)
    except Exception as exc:
        raise ResumeEngineError(f"ATS scoring failed: {exc}") from exc

    score_result = result.score_result
    return {
        "score": round(float(score_result.score), 2),
        "keyword_coverage": round(float(score_result.keyword_coverage), 4),
        "matched_skills": list(score_result.matched_skills),
        "missing_skills": list(score_result.missing_skills),
        "suggestions": list(score_result.suggestions),
    }

