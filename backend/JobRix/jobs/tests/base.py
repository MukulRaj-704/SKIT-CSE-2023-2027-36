"""
jobs/tests/base.py
==================
Shared fixtures for the ``jobs`` suites: recruiters, parsed resumes and the
``apply`` helper.

The resume side reuses the fixtures of the ``resumes`` suite (its user/token
mixin, the engine-valid job description and the minimal stored parse). Rows
created through ``make_parsed_resume`` carry a stub ``parsed_data`` - the
engine still runs for real during ``POST /api/jobs/<id>/apply/`` (it scores
the stored JSON), only PDF parsing is skipped: that contract is covered by
the resumes tests.
"""

from django.urls import reverse
from django.utils import timezone

from resumes.models import ParseStatus, Resume
from resumes.tests.base import JOB_DESCRIPTION, PARSED_DATA, ResumeAPIMixin

from ..models import Job

JOB_PAYLOAD = {
    "title": "Backend Engineer",
    "location": "Bengaluru, India",
    "job_type": "full_time",
    "salary_range": "INR 12-18 LPA",
    "description": "Build and scale the JobRix API surface for job seekers.",
    "requirements": JOB_DESCRIPTION,
}


def make_parsed_resume(user, title="Stub resume") -> Resume:
    """A resume row whose parse already succeeded (no PDF, no engine call)."""
    return Resume.objects.create(
        user=user,
        title=title,
        parse_status=ParseStatus.PARSED,
        parsed_data=PARSED_DATA,
        parsed_at=timezone.now(),
    )


class JobsAPIMixin(ResumeAPIMixin):
    """
    Accounts-style helpers: users, token auth (inherited from the resumes
    mixin) plus job posting and applying helpers for this suite.
    """

    def make_recruiter(self, email):
        return self.make_user(email, role="recruiter")

    def make_job(self, recruiter, **overrides) -> Job:
        """Create a posting through the API (asserts the happy path, 201)."""
        self.authenticate(recruiter)
        response = self.client.post(
            reverse("jobs_api:job_list"),
            {**JOB_PAYLOAD, **overrides},
            format="json",
        )
        assert response.status_code == 201, getattr(response, "data", response)
        return Job.objects.get(pk=response.data["id"])

    def apply(self, seeker, job_id, resume=None, **extra):
        """``POST /api/jobs/<id>/apply/`` with an own parsed resume."""
        resume = resume or make_parsed_resume(seeker)
        self.authenticate(seeker)
        return self.client.post(
            reverse("jobs_api:job_apply", args=[job_id]),
            {"resume": resume.pk, **extra},
            format="json",
        )


def list_rows(response) -> list:
    """Rows of a (possibly paginated) list response - the project pages at 20."""
    data = response.data
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data
