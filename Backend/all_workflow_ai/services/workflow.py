from django.db import transaction

from resumes.models import Resume
from resumes.services import ResumeEngineError

from ..models import JobMatchAnalysis
from .pipeline import run_complete_workflow


@transaction.atomic
def create_complete_analysis(
    *,
    user,
    upload,
    job_title="",
    job_description="",
):
    resume = Resume.objects.create(
        user=user,
        title=(
            job_title or upload.name.rsplit(".", 1)[0]
        )[:150],
        file=upload,
        original_filename=upload.name,
        file_size=upload.size,
        content_type=(
            getattr(upload, "content_type", "")
            or "application/pdf"
        ),
        is_default=not Resume.objects.filter(user=user).exists(),
    )

    result = run_complete_workflow(
        resume,
        job_description,
    )

    analysis = JobMatchAnalysis.objects.create(
        resume=resume,
        job_title=job_title,
        job_description=job_description,
        ats_score=result["ats"]["score"],
        keyword_coverage=result["ats"]["keyword_coverage"],
        matched_skills=result["ats"]["matched_skills"],
        missing_skills=result["ats"]["missing_skills"],
        ats_suggestions=result["ats"]["suggestions"],
        semantic_score=result["semantic"]["score"],
        semantic_engine=result["semantic"]["engine"],
        job_match_score=result["job_match_score"],
    )

    return resume, analysis, result
