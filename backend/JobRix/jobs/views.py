"""
jobs/views.py
=============
DRF generic views for jobs and applications (accounts/resumes style).

Endpoints (all require a token; rules per role below):

* ``GET|POST /api/jobs/``                 board list / recruiter creates (POST)
* ``GET|PUT|PATCH|DELETE /api/jobs/<id>/`` detail; writes only by the owner
* ``POST /api/jobs/<id>/apply/``          seeker applies (auto-scored, 201)
* ``GET /api/jobs/<id>/applications/``    recruiter's ranked candidate list
* ``GET /api/applications/``              the seeker's own applications
* ``GET|PATCH /api/applications/<id>/``   detail; status updates

Scoring rules:
* applying to a closed job or a duplicate submission answers 409;
* an unparsed resume answers 409 (same as the ATS endpoint);
* an engine failure during scoring answers 503 - consistent with
  ``/api/resumes/<id>/ats/``.
"""

from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsJobSeeker, IsRecruiter
from resumes.exceptions import ResumeEngineUnavailable, ResumeNotParsed
from resumes.models import ATSAnalysis, ParseStatus, Resume
from resumes.services import ENGINE_VERSION, ResumeEngineError

from .exceptions import ApplicationAlreadyExists, JobClosed
from .models import Application, ApplicationStatus, Job
from .permissions import IsJobOwner
from .serializers import (
    ApplicationCreateSerializer,
    ApplicationSerializer,
    ApplicationStatusSerializer,
    JobSerializer,
    JobWriteSerializer,
)
from .services import score_application, scoring_job_description


class JobListCreateView(generics.ListCreateAPIView):
    """Board list for everyone; posting is recruiter only (admins bypass)."""

    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsRecruiter()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return JobWriteSerializer
        return JobSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            return Job.objects.all()
        if user.is_recruiter:
            # Recruiters manage their own postings (open and closed ones).
            return Job.objects.filter(created_by=user)
        # Seekers only ever see the open board.
        return Job.objects.filter(is_active=True)

    def create(self, request, *args, **kwargs):
        # Validate with the write serializer, answer with the full projection
        # (mirrors ResumeListCreateView: clients always get the id/counts).
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = serializer.save()
        output = JobSerializer(job, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)


class JobDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Public read for signed-in users; writes gated by IsJobOwner (403)."""

    permission_classes = [IsAuthenticated, IsJobOwner]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return JobWriteSerializer
        return JobSerializer

    def get_queryset(self):
        # Reads are intentionally unscoped: a job board is public to members
        # (closed postings stay reachable from application history). Writes
        # are guarded per object by IsJobOwner, so foreign edits answer 403.
        return Job.objects.all()

    def update(self, request, *args, **kwargs):
        # Same rule as create: validate with the write serializer, answer with
        # the full projection (PUT and PATCH behave identically here).
        partial = kwargs.pop("partial", False)
        job = self.get_object()
        serializer = self.get_serializer(job, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        job = serializer.save()
        output = JobSerializer(job, context=self.get_serializer_context())
        return Response(output.data)


class JobApplyView(generics.GenericAPIView):
    """Apply with one parsed resume; scores it against the posting (201)."""

    permission_classes = [IsAuthenticated, IsJobSeeker]
    serializer_class = ApplicationCreateSerializer

    @property
    def job(self) -> Job:
        if not hasattr(self, "_job"):
            self._job = get_object_or_404(Job, pk=self.kwargs["pk"])
        return self._job

    def post(self, request, *args, **kwargs):
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        job = self.job
        if not job.is_active:
            raise JobClosed()
        # Scope the resume to the caller: foreign ids404 like /api/resumes/.
        resume = get_object_or_404(
            Resume, pk=body.validated_data["resume"].pk, user=request.user
        )
        if resume.parse_status != ParseStatus.PARSED or not resume.parsed_data:
            raise ResumeNotParsed()
        if Application.objects.filter(job=job, resume=resume).exists():
            raise ApplicationAlreadyExists()

        try:
            # Reuses Resume.parsed_data - the PDF is never read again.
            fields = score_application(resume, job)
        except ResumeEngineError as exc:
            raise ResumeEngineUnavailable(detail=str(exc)) from exc

        with transaction.atomic():
            analysis = ATSAnalysis.objects.create(
                resume=resume,
                job_title=job.title,
                job_description=scoring_job_description(job),
                engine_version=ENGINE_VERSION,
                **fields,
            )
            application = Application.objects.create(
                job=job,
                resume=resume,
                seeker=resume.user,
                status=ApplicationStatus.SUBMITTED,
                message=body.validated_data.get("message", ""),
                ats_score=fields["score"],
                ats_analysis=analysis,
            )
        output = ApplicationSerializer(
            application, context=self.get_serializer_context()
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


class JobApplicationsView(generics.ListAPIView):
    """Ranked candidate list for one posting (recruiter of that job only)."""

    permission_classes = [IsAuthenticated, IsRecruiter]
    serializer_class = ApplicationSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            job = get_object_or_404(Job, pk=self.kwargs["pk"])
        else:
            # Another recruiter's posting is a 404, not an empty list.
            job = get_object_or_404(Job, pk=self.kwargs["pk"], created_by=user)
        # Scored applications first, unscored last, newest first on ties -
        # nulls_last keeps that portable across SQLite and Postgres.
        return Application.objects.filter(job=job).order_by(
            F("ats_score").desc(nulls_last=True), "-created_at"
        )


class ApplicationListView(generics.ListAPIView):
    """The caller's own applications (admins see everything)."""

    permission_classes = [IsAuthenticated, IsJobSeeker]
    serializer_class = ApplicationSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            return Application.objects.all()
        return Application.objects.filter(seeker=user)


class ApplicationDetailView(generics.RetrieveUpdateAPIView):
    """
    One application, visible to its seeker, the job's recruiter or an admin.

    Only ``status`` can be written (``ApplicationStatusSerializer``):

    * the job's recruiter (or an admin) may set any status;
    * the seeker may only move their own application to ``withdrawn``.
    """

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return ApplicationStatusSerializer
        return ApplicationSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_platform_admin:
            return Application.objects.all()
        if user.is_recruiter:
            return Application.objects.filter(job__created_by=user)
        return Application.objects.filter(seeker=user)

    def update(self, request, *args, **kwargs):
        # PUT behaves like PATCH: the resource here is a single status field.
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        user = request.user
        if user.is_platform_admin:
            pass  # admins may set any status
        elif instance.seeker_id == user.pk:
            if new_status != ApplicationStatus.WITHDRAWN:
                raise ValidationError(
                    {"status": "You may only withdraw your own application."}
                )
        # else: the job's recruiter (queryset is scoped) may set any status.

        serializer.save()
        output = ApplicationSerializer(instance, context=self.get_serializer_context())
        return Response(output.data)

