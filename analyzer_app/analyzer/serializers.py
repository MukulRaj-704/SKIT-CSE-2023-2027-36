"""analyzer/serializers.py - request validation and response projection."""

from rest_framework import serializers

from . import config
from .models import AnalysisRun, AnalyzedResume


class ResumeUploadSerializer(serializers.Serializer):
    file = serializers.FileField(allow_empty_file=True)  # emptiness reported by the extractor


class AnalyzeResumeSerializer(serializers.Serializer):
    resume_id = serializers.UUIDField()


class AnalyzeJobSerializer(serializers.Serializer):
    resume_id = serializers.UUIDField()
    job_description = serializers.CharField(min_length=config.MIN_JD_CHARS, max_length=config.MAX_JD_CHARS, trim_whitespace=True)
    job_title = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    company = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class ResumeSerializer(serializers.ModelSerializer):
    resume_id = serializers.UUIDField(source="id", read_only=True)
    parsed_resume = serializers.JSONField(source="parsed_data", read_only=True)

    class Meta:
        model = AnalyzedResume
        fields = ["resume_id", "original_filename", "file_type", "file_size", "page_count",
                  "parsed_resume", "warnings", "created_at"]


class AnalysisSerializer(serializers.ModelSerializer):
    analysis_id = serializers.UUIDField(source="id", read_only=True)
    resume_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = AnalysisRun
        fields = ["analysis_id", "resume_id", "mode", "job_title", "company", "created_at", "result"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Flatten: the stored result already has resume_analysis / suggestions / job_analysis.
        result = data.pop("result")
        return {**data, **result}
