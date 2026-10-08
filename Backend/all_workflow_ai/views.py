from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated

from resumes.services import ResumeEngineError

from .serializers import CompleteAnalysisRequestSerializer
from .models import JobMatchAnalysis
from .services.workflow import create_complete_analysis


class CompleteResumeJobAnalysisView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = CompleteAnalysisRequestSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        try:
            resume, analysis, result = create_complete_analysis(
                user=request.user,
                upload=serializer.validated_data["resume"],
                job_title=serializer.validated_data.get("job_title", ""),
                job_description=serializer.validated_data["job_description"],
            )
        except ResumeEngineError as exc:
            return Response(
                {"success": False, "detail": str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "detail": "Resume analysis failed.",
                    "error": str(exc),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        parsed = result["resume_parsing"]
        contact = parsed.get("contact", {})

        return Response(
            {
                "success": True,
                "workflow": {
                    "resume_parsing": "completed",
                    "ats_score": "completed",
                    "semantic_job_matching": "completed",
                    "final_job_match": "completed",
                },
                "resume": {
                    "id": resume.id,
                    "filename": resume.original_filename,
                    "name": contact.get("name"),
                    "email": contact.get("email"),
                    "phone": contact.get("phone"),
                    "skills": parsed.get("skills", []),
                    "education": parsed.get("education", []),
                    "experience": parsed.get("experience", []),
                    "projects": parsed.get("projects", []),
                    "certifications": parsed.get("certifications", []),
                },
                "ats": {
                    "score": result["ats"]["score"],
                    "keyword_coverage": result["ats"]["keyword_coverage"],
                    "matched_skills": result["ats"]["matched_skills"],
                    "missing_skills": result["ats"]["missing_skills"],
                    "suggestions": result["ats"]["suggestions"],
                },
                "semantic_job_matching": {
                    "score": result["semantic"]["score"],
                    "engine": result["semantic"]["engine"],
                    "matched_skills": result["semantic"]["matched_skills"],
                    "missing_terms": result["semantic"]["missing_terms"],
                },
                "job_match_score": result["job_match_score"],
                "score_formula": "40% ATS + 60% SBERT",
                "analysis_id": analysis.id,
            },
            status=status.HTTP_201_CREATED,
        )


class JobMatchAnalysisDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        analysis = (
            JobMatchAnalysis.objects
            .select_related("resume")
            .filter(
                pk=pk,
                resume__user=request.user,
            )
            .first()
        )

        if not analysis:
            return Response(
                {
                    "success": False,
                    "detail": "Analysis not found.",
                },
                status=404,
            )

        return Response({
            "success": True,
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
