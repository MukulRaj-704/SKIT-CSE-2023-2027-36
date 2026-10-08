"""
jobs/services.py
================
Engine-facing helpers for the application flow.

The scoring itself belongs to the ``resume_parser`` engine and is already
wrapped by ``resumes/services.py``; this module only adds the jobs-specific
policy: *what* text a resume is scored against (the posting's requirements,
falling back to its description).

Keeping the call here means ``jobs/views.py`` never imports the engine stack
directly and a future worker can take over with a one-line change.
"""

from __future__ import annotations

from resumes.models import Resume
from resumes.services import run_ats_analysis

from .models import Job


def scoring_job_description(job: Job) -> str:
    """The text the ATS scorer matches resumes against for this posting."""
    return (job.requirements or job.description).strip()


def score_application(resume: Resume, job: Job) -> dict:
    """
    Score the *stored* parse of ``resume`` against ``job`` (PDF never re-read).

    Returns the fields needed to build a ``resumes.ATSAnalysis`` row; raises
    ``resumes.services.ResumeEngineError`` when the engine cannot score.
    """
    return run_ats_analysis(resume.parsed_data, scoring_job_description(job))
