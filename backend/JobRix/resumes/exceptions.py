"""
resumes/exceptions.py
=====================
API level errors raised by the resume / ATS endpoints.

They exist so the engine's failures (missing dependency, unreadable PDF) and the
"not parsed yet" state reach the client as meaningful status codes instead of a
500 traceback.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class ResumeEngineUnavailable(APIException):
    """The ``resume_parser`` engine cannot be used on this server."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "The resume parsing engine is unavailable on this server. Install it with "
        "`pip install -e Backend/resume_parser/resume_parser` (it needs pymupdf)."
    )
    default_code = "resume_engine_unavailable"


class ResumeNotParsed(APIException):
    """ATS scoring was requested for a resume without a successful parse."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        "This resume has no parsed data yet. Fix the parse (POST "
        "/api/resumes/<id>/reparse/) before running an ATS analysis."
    )
    default_code = "resume_not_parsed"