"""
jobs/exceptions.py
==================
API level errors raised by the jobs / applications endpoints, so "the job is
closed" and "you already applied" reach the client as 409 instead of a 500.

Engine and parse problems reuse the ``resumes`` exceptions (409 not-parsed,
503 engine unavailable) because they are the same conditions on the same data.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class JobClosed(APIException):
    """Apply was attempted on a posting that no longer accepts applications."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This job is not accepting applications (it is closed)."
    default_code = "job_closed"


class ApplicationAlreadyExists(APIException):
    """The same resume was already submitted to the same job."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "You have already applied to this job with this resume."
    default_code = "application_already_exists"
