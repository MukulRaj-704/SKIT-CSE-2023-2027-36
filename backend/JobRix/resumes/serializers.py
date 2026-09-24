"""
resumes/serializers.py
======================
DRF serializers for the resume / ATS endpoints (accounts style): a write
serializer validates uploads, a read serializer projects model rows, and a
plain Serializer validates the scoring request body.
"""

from pathlib import Path

from django.conf import settings
from rest_framework import serializers

from .models import ATSAnalysis, Resume


class ResumeUploadSerializer(serializers.ModelSerializer):
    """Write side of ``Resume``: validates the PDF and stamps ownership."""

    class Meta:
        model = Resume
        fields = ["file", "title", "is_default"]

    def validate_file(self, value):
        max_bytes = settings.RESUME_MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if value.size > max_bytes:
            raise serializers.ValidationError(
                f"Resumes must be {settings.RESUME_MAX_UPLOAD_SIZE_MB} MB or smaller."
            )
        if not (value.name or "").lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF resumes are supported.")
        content_type = (getattr(value, "content_type", "") or "").lower()
        allowed = settings.RESUME_ALLOWED_CONTENT_TYPES
        if content_type and content_type not in allowed:
            raise serializers.ValidationError(
                f"Unsupported content type '{content_type}'. "
                f"Allowed: {', '.join(allowed)}."
            )
        return value

    def create(self, validated_data):
        request = self.context["request"]
        uploaded = validated_data["file"]
        user = request.user
        # A seeker's first resume becomes the default automatically; the model's
        # save() keeps "only one default per account" true for every write path.
        is_default = validated_data.get("is_default") or not Resume.objects.filter(
            user=user
        ).exists()
        return Resume.objects.create(
            user=user,
            title=validated_data.get("title") or Path(uploaded.name).stem[:150],
            file=uploaded,
            original_filename=uploaded.name or "",
            file_size=uploaded.size or 0,
            content_type=getattr(uploaded, "content_type", "") or "",
            is_default=is_default,
        )


class ResumeSerializer(serializers.ModelSerializer):
    """Read side of ``Resume``; only title/default/active are updatable."""

    file_url = serializers.SerializerMethodField()
    # No source= here: DRF rejects source == field name. Both names match the
    # Resume properties (parsed_summary / skill_names) by design.
    parsed_summary = serializers.DictField(read_only=True)
    skills = serializers.ListField(source="skill_names", read_only=True)
    ats_analyses_count = serializers.IntegerField(
        source="ats_analyses.count", read_only=True
    )

    class Meta:
        model = Resume
        fields = [
            "id",
            "title",
            "file",
            "file_url",
            "original_filename",
            "file_size",
            "content_type",
            "is_default",
            "is_active",
            "parse_status",
            "parse_error",
            "parsed_at",
            "parsed_summary",
            "skills",
            "ats_analyses_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            field
            for field in fields
            if field not in ("title", "is_default", "is_active")
        ]

    def get_file_url(self, obj) -> str | None:
        if not obj.file:
            return None
        url = obj.file.url
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class ATSAnalysisRequestSerializer(serializers.Serializer):
    """POST body for ``/api/resumes/<id>/ats/``."""

    job_description = serializers.CharField(min_length=30, trim_whitespace=True)
    job_title = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )


class ATSAnalysisSerializer(serializers.ModelSerializer):
    """Read-only projection of a stored analysis."""

    class Meta:
        model = ATSAnalysis
        fields = [
            "id",
            "resume",
            "job_title",
            "score",
            "keyword_coverage",
            "matched_skills",
            "missing_skills",
            "suggestions",
            "engine_version",
            "created_at",
        ]
        read_only_fields = fields
