"""
analyzer/exceptions.py
======================
Domain errors that reach the client as meaningful status codes instead of 500s.
Body shape: ``{"detail": "<message>", "code": "<machine readable code>"}``.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class ExtractionError(APIException):
    """The uploaded file cannot be used (400) or has no readable text (422)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The uploaded file could not be processed."
    default_code = "invalid_file"

    def __init__(self, code: str, message: str, status: int = 400):
        self.status_code = status
        self.detail = {"detail": message, "code": code}


class EngineUnavailable(APIException):
    """A required library (the ``resume_parser`` engine / PyMuPDF) is missing."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The resume parsing engine is unavailable on this server."
    default_code = "engine_unavailable"

    def __init__(self, message: str = None):
        self.detail = {"detail": message or self.default_detail, "code": self.default_code}


class ResumeNotReady(APIException):
    """The stored resume has no usable parse (should not normally happen)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This resume has no parsed data. Upload it again."
    default_code = "resume_not_parsed"
