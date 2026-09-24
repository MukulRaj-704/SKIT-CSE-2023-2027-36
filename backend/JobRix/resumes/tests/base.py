"""
resumes/tests/base.py
=====================
Shared fixtures for the ``resumes`` suites: accounts-style users + token auth,
a real PDF built with pymupdf (the engine's own dependency) and a throwaway
MEDIA_ROOT so test uploads never touch the developer's media directory.
"""

import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.authtoken.models import Token

from accounts.models import Role

User = get_user_model()

PASSWORD = "JobRix-Resume-Pass-2026"
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="jobrix_test_media_")

# Section headings the engine recognises; rendered into a real one-page PDF.
RESUME_LINES = [
    "Mukul Sharma",
    "mukul.sharma@example.com | +91 98765 43210",
    "Bengaluru, India | linkedin.com/in/mukulsharma",
    "SUMMARY",
    "Backend developer with 4 years of experience building REST APIs in Django.",
    "SKILLS",
    "Python, Django, Django REST Framework, PostgreSQL, Redis, Docker, Git, AWS, Celery",
    "EXPERIENCE",
    "Software Engineer - Acme Pvt Ltd, Bengaluru (Jan 2022 - Present)",
    "Built Django REST APIs serving 2M requests per day; cut p95 latency by 40%.",
    "EDUCATION",
    "B.Tech Computer Science - Visvesvaraya Technological University, 2021",
    "PROJECTS",
    "JobRix - job application tracker with resume ATS scoring (Django, React).",
    "CERTIFICATIONS",
    "AWS Certified Solutions Architect - Associate, 2023",
]

# What the seeker would paste into the "analyze against a job" form. The second
# line is a "Requirements:" list, which the engine's scorer treats as its
# primary skill signal; Kubernetes and Terraform are deliberately absent from
# the resume -> they must show up as missing skills.
JOB_DESCRIPTION = (
    "We are hiring a Backend Engineer to build REST APIs with Python, Django "
    "and Django REST Framework, work with PostgreSQL and Redis, ship services "
    "in Docker on AWS, and run background jobs with Celery.\n"
    "Requirements: Kubernetes, Terraform, Docker, AWS, Python, Django, Redis."
)

# Minimal stored parse for tests where the engine must not run (the API only
# reads contact + skills here; engine-facing tests parse a real PDF instead).
PARSED_DATA = {
    "contact": {
        "name": "Mukul Sharma",
        "email": "mukul.sharma@example.com",
        "location": "Bengaluru, India",
    },
    "summary": "Backend developer with 4 years of experience building REST APIs.",
    "skills": [
        {"name": "Python", "category": "Languages"},
        {"name": "Django", "category": "Frameworks"},
        {"name": "PostgreSQL", "category": "Databases"},
        {"name": "Docker", "category": "Tools"},
    ],
    "raw_text": "Mukul Sharma mukul.sharma@example.com",
}


def build_resume_pdf(lines=None) -> bytes:
    """Render ``lines`` into a one-page PDF with pymupdf."""
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 72
    for line in lines or RESUME_LINES:
        page.insert_text((72, y), line, fontsize=11)
        y += 16
    payload = doc.tobytes()
    doc.close()
    return payload


def resume_upload(content=None, name="candidate_resume.pdf") -> SimpleUploadedFile:
    """A multipart PDF upload (real PDF unless ``content`` overrides the bytes)."""
    return SimpleUploadedFile(
        name,
        build_resume_pdf() if content is None else content,
        content_type="application/pdf",
    )


class ResumeAPIMixin:
    """Accounts-style helpers: users, token auth, resume endpoints."""

    def make_user(self, email, role=Role.JOB_SEEKER):
        return User.objects.create_user(email=email, password=PASSWORD, role=role)

    def authenticate(self, user):
        """Send ``Authorization: Token <key>`` for ``user`` (like real clients)."""
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return token

    def upload_resume(self, user, **upload_kwargs):
        """POST a real PDF as ``user`` to the list endpoint."""
        self.authenticate(user)
        return self.client.post(
            reverse("resumes_api:resume_list"),
            {"file": resume_upload(**upload_kwargs)},
        )
