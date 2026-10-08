from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from resumes.services import ResumeEngineError
from .models import JobMatchAnalysis
from .serializers import CompleteAnalysisRequestSerializer
from .services.workflow import create_complete_analysis

class CompleteResumeJobAnalysisView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = CompleteAnalysisRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            resume, analysis, result = create_complete_analysis(
                user=request.user,
                upload=serializer.validated_data["resume"],
                job_title=serializer.validated_data.get("job_title", ""),
                job_description=serializer.validated_data["job_description"],
            )
        except ResumeEngineError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except Exception as exc:
            return Response({"detail": "Complete resume analysis failed.", "error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        parsed = result["resume_parsing"]
        contact = parsed.get("contact") or {}
        return Response({
            "workflow": {
                "1_resume_parsing": "completed",
                "2_ats_score": "completed",
                "3_semantic_job_matching": "completed",
            },
            "resume": {
                "id": resume.id,
                "filename": resume.original_filename,
                "name": contact.get("name"),
                "email": contact.get("email"),
                "skills": parsed.get("skills") or [],
                "education": parsed.get("education") or [],
                "experience": parsed.get("experience") or [],
                "projects": parsed.get("projects") or [],
                "certifications": parsed.get("certifications") or [],
            },
            "ats": result["ats"],
            "semantic_job_matching": result["semantic"],
            "job_match_score": result["job_match_score"],
            "analysis_id": analysis.id,
            "score_formula": "40% ATS + 60% SBERT semantic similarity",
        }, status=status.HTTP_201_CREATED)

class JobMatchAnalysisDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        analysis = JobMatchAnalysis.objects.select_related("resume").filter(pk=pk, resume__user=request.user).first()
        if not analysis:
            return Response({"detail": "Analysis not found."}, status=404)
        return Response({
            "analysis_id": analysis.id,
            "resume_id": analysis.resume_id,
            "job_title": analysis.job_title,
            "ats_score": analysis.ats_score,
            "semantic_score": analysis.semantic_score,
            "job_match_score": analysis.job_match_score,
            "matched_skills": analysis.matched_skills,
            "missing_skills": analysis.missing_skills,
            "ats_suggestions": analysis.ats_suggestions,
            "semantic_engine": analysis.semantic_engine,
            "created_at": analysis.created_at,
        })
