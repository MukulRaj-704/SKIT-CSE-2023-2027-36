"""
resumes/views.py
================
DRF generic views for resumes and ATS analyses (accounts style).

Endpoints (all scoped to ``request.user``; foreign rows answer 404):

* ``GET|POST /api/resumes/``                  list / upload + parse once
* ``GET|PUT|PATCH|DELETE /api/resumes/<id>/`` detail, rename, remove
* ``POST /api/resumes/<id>/reparse/``         re-run the parse (stored file)
* ``GET|POST /api/resumes/<id>/ats/``         score the stored parse / history
* ``GET /api/resumes/<id>/ats/<pk>/``         one stored analysis
"""

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .exceptions import ResumeNotParsed
from .models import ATSAnalysis, ParseStatus, Resume
from .permissions import IsJobSeeker, IsResumeOwner
from .serializers import (
    ATSAnalysisRequestSerializer,
    ATSAnalysisSerializer,
    ResumeSerializer,
    ResumeUploadSerializer,
)
from .services import (
    ENGINE_VERSION,
    ResumeEngineError,
    parse_resume_instance,
    run_ats_analysis,
)


class ResumeEngineUnavailable(APIException):
    """The engine could not serve this request (not installed / scoring error)."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The resume parsing engine is unavailable."
    default_code = "resume_engine_unavailable"


class ResumeListCreateView(generics.ListCreateAPIView):
    """List own resumes (GET) or upload a PDF and parse it once (POST)."""

    permission_classes = [IsAuthenticated, IsJobSeeker]

    def get_queryset(self):
        return Resume.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        return ResumeUploadSerializer if self.request.method == "POST" else ResumeSerializer

    def create(self, request, *args, **kwargs):
        upload = self.get_serializer(data=request.data)
        upload.is_valid(raise_exception=True)
        resume = upload.save()
        # Parse exactly once, right here; later flows reuse Resume.parsed_data.
        # parse_resume_instance never raises: the outcome lands in parse_status
        # (parsed | failed | pending when the engine itself is unavailable).
        parse_resume_instance(resume)
        output = ResumeSerializer(resume, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)


class ResumeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Own resume: full detail (incl. parsed data), edit flags, delete + file."""

    permission_classes = [IsAuthenticated, IsJobSeeker, IsResumeOwner]
    serializer_class = ResumeSerializer

    def get_queryset(self):
        return Resume.objects.filter(user=self.request.user)


class ResumeReparseView(generics.GenericAPIView):
    """Re-run the parse for the stored file (200 with the updated row)."""

    permission_classes = [IsAuthenticated, IsJobSeeker, IsResumeOwner]
    serializer_class = ResumeSerializer

    def get_queryset(self):
        return Resume.objects.filter(user=self.request.user)

    def post(self, request, *args, **kwargs):
        resume = self.get_object()
        parse_resume_instance(resume)
        output = ResumeSerializer(resume, context=self.get_serializer_context())
        return Response(output.data)


class ATSAnalysisListCreateView(generics.ListCreateAPIView):
    """Score a stored parse against a job description (POST) or list runs (GET)."""

    permission_classes = [IsAuthenticated, IsJobSeeker, IsResumeOwner]

    def get_queryset(self):
        # self.resume 404s for foreign/nonexistent resumes on every method, so
        # GET and POST answer consistently ("404", not "empty list" vs "404").
        return ATSAnalysis.objects.filter(resume=self.resume)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ATSAnalysisRequestSerializer
        return ATSAnalysisSerializer

    @property
    def resume(self) -> Resume:
        """The resume to score, scoped to the caller (foreign ids 404)."""
        if not hasattr(self, "_resume"):
            self._resume = get_object_or_404(
                Resume, pk=self.kwargs["resume_pk"], user=self.request.user
            )
        return self._resume

    def create(self, request, *args, **kwargs):
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        resume = self.resume

        if resume.parse_status != ParseStatus.PARSED or not resume.parsed_data:
            raise ResumeNotParsed()

        try:
            # Reuses Resume.parsed_data -> the stored JSON is fed back through
            # pipeline.load_parsed(); the PDF is never read again.
            fields = run_ats_analysis(
                resume.parsed_data, body.validated_data["job_description"]
            )
        except ResumeEngineError as exc:
            raise ResumeEngineUnavailable(detail=str(exc)) from exc

        analysis = ATSAnalysis.objects.create(
            resume=resume,
            job_title=body.validated_data.get("job_title", ""),
            job_description=body.validated_data["job_description"],
            engine_version=ENGINE_VERSION,
            **fields,
        )
        output = ATSAnalysisSerializer(analysis, context=self.get_serializer_context())
        return Response(output.data, status=status.HTTP_201_CREATED)


class ATSAnalysisDetailView(generics.RetrieveAPIView):
    """One stored analysis for one of the caller's resumes."""

    permission_classes = [IsAuthenticated, IsJobSeeker, IsResumeOwner]
    serializer_class = ATSAnalysisSerializer

    def get_queryset(self):
        return ATSAnalysis.objects.filter(
            resume_id=self.kwargs["resume_pk"],
            resume__user=self.request.user,
        )

