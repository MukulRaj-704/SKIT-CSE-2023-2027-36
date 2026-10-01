"""
analyzer/views.py
=================
Thin DRF views: validate -> call the service layer -> persist -> respond.
No authentication (the module is open by design); a per-IP throttle protects
the CPU-heavy parse/score endpoints instead.

POST /api/analyzer/resumes/upload/     upload PDF/DOCX, parse once  -> resume_id
GET  /api/analyzer/resumes/<id>/       stored parsed resume
POST /api/analyzer/analyze/resume/     Mode 1: general ATS result
POST /api/analyzer/analyze/job/        Mode 2: ATS + job match
GET  /api/analyzer/analysis/<id>/      a stored analysis
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from . import config
from .models import AnalysisRun, AnalyzedResume
from .serializers import (AnalysisSerializer, AnalyzeJobSerializer, AnalyzeResumeSerializer,
                          ResumeSerializer, ResumeUploadSerializer)
from .services import resume_analysis


class AnalyzerThrottle(AnonRateThrottle):
    scope = "analyzer"

    def get_rate(self):
        return config.THROTTLE_RATE


class AnalyzerBaseView(APIView):
    authentication_classes = []  # no login in this module (and so no CSRF surface)
    permission_classes = [AllowAny]
    throttle_classes = [AnalyzerThrottle]


class ResumeUploadView(AnalyzerBaseView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        body = ResumeUploadSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        upload = body.validated_data["file"]
        result = resume_analysis.ingest_resume(upload.name, upload.read())  # raises ExtractionError (400/422)
        resume = AnalyzedResume.objects.create(
            original_filename=upload.name[:255],
            file_type=result["file_type"],
            file_size=upload.size,
            page_count=result["page_count"],
            raw_text=result["raw_text"],
            parsed_data=result["parsed"],
            layout=result["layout"],
            warnings=result["warnings"],
        )
        return Response(ResumeSerializer(resume).data, status=status.HTTP_201_CREATED)


class ResumeDetailView(AnalyzerBaseView):
    def get(self, request, pk):
        return Response(ResumeSerializer(get_object_or_404(AnalyzedResume, pk=pk)).data)


class AnalyzeResumeView(AnalyzerBaseView):
    """Mode 1 - general ATS check (no job description needed)."""

    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def post(self, request):
        body = AnalyzeResumeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        resume = get_object_or_404(AnalyzedResume, pk=body.validated_data["resume_id"])
        result = resume_analysis.analyze_general(resume.parsed_data, resume.raw_text, resume.layout, resume.page_count)
        run = AnalysisRun.objects.create(
            resume=resume, mode=AnalysisRun.Mode.GENERAL,
            ats_score=result["resume_analysis"]["ats_score"], result=result,
        )
        return Response(AnalysisSerializer(run).data, status=status.HTTP_201_CREATED)


class AnalyzeJobView(AnalyzerBaseView):
    """Mode 2 - resume against a pasted job description."""

    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def post(self, request):
        body = AnalyzeJobSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        d = body.validated_data
        resume = get_object_or_404(AnalyzedResume, pk=d["resume_id"])
        result = resume_analysis.analyze_job(
            resume.parsed_data, resume.raw_text, resume.layout, resume.page_count,
            d["job_description"], d["job_title"], d["company"],
        )
        run = AnalysisRun.objects.create(
            resume=resume, mode=AnalysisRun.Mode.JOB, job_title=d["job_title"], company=d["company"],
            job_description=d["job_description"],
            ats_score=result["resume_analysis"]["ats_score"],
            job_match_score=result["job_analysis"]["job_match_score"], result=result,
        )
        return Response(AnalysisSerializer(run).data, status=status.HTTP_201_CREATED)


class AnalysisDetailView(AnalyzerBaseView):
    def get(self, request, pk):
        return Response(AnalysisSerializer(get_object_or_404(AnalysisRun, pk=pk)).data)
