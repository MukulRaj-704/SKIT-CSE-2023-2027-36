"""
jobs/serializers.py
===================
DRF serializers for the jobs / applications endpoints (accounts + resumes
style): a write serializer validates postings, a read serializer projects
them, and the application side splits into create (resume reference), read
(projection incl. ATS fields) and a one-field status serializer for PATCH.
"""

from rest_framework import serializers

from resumes.models import Resume

from .models import Application, ApplicationStatus, Job


class JobSerializer(serializers.ModelSerializer):
    """Read-only projection of a posting (all writes go through JobWriteSerializer)."""

    company_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    applications_count = serializers.IntegerField(
        source="applications.count", read_only=True
    )

    class Meta:
        model = Job
        fields = [
            "id",
            "title",
            "company",
            "company_name",
            "location",
            "job_type",
            "salary_range",
            "description",
            "requirements",
            "is_active",
            "created_by",
            "created_by_name",
            "applications_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_company_name(self, obj) -> str | None:
        return obj.company.name if obj.company_id else None

    def get_created_by_name(self, obj) -> str:
        return obj.created_by.full_name


class JobWriteSerializer(serializers.ModelSerializer):
    """Create/update a posting; ownership and company are stamped server side."""

    class Meta:
        model = Job
        fields = [
            "title",
            "location",
            "job_type",
            "salary_range",
            "description",
            "requirements",
            "is_active",
        ]

    def validate_requirements(self, value):
        # Requirements double as the ATS scoring text - too short makes every
        # application score meaningless (mirrors the 30-char ATS endpoint rule).
        if len(value.strip()) < 30:
            raise serializers.ValidationError(
                "Requirements must be at least 30 characters; they double as "
                "the job description the ATS scorer matches resumes against."
            )
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        # Company comes from the recruiter's profile, never from the payload.
        return Job.objects.create(
            created_by=user, company=user.company, **validated_data
        )


class ApplicationCreateSerializer(serializers.Serializer):
    """POST body for ``/api/jobs/<id>/apply/`` (resume ownership checked in the view)."""

    resume = serializers.PrimaryKeyRelatedField(queryset=Resume.objects.all())
    message = serializers.CharField(
        required=False, allow_blank=True, default="", trim_whitespace=True
    )


class ApplicationSerializer(serializers.ModelSerializer):
    """Read-only projection of an application incl. its scored skills."""

    job_title = serializers.SerializerMethodField()
    job_company = serializers.SerializerMethodField()
    seeker_email = serializers.SerializerMethodField()
    matched_skills = serializers.SerializerMethodField()
    missing_skills = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id",
            "job",
            "job_title",
            "job_company",
            "resume",
            "seeker",
            "seeker_email",
            "status",
            "message",
            "ats_score",
            "ats_analysis",
            "matched_skills",
            "missing_skills",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_job_title(self, obj) -> str:
        return obj.job.title

    def get_job_company(self, obj) -> str | None:
        return obj.job.company.name if obj.job.company_id else None

    def get_seeker_email(self, obj) -> str:
        return obj.seeker.email

    def _analysis_fields(self, obj, name) -> list:
        return list(getattr(obj.ats_analysis, name) or []) if obj.ats_analysis_id else []

    def get_matched_skills(self, obj) -> list:
        return self._analysis_fields(obj, "matched_skills")

    def get_missing_skills(self, obj) -> list:
        return self._analysis_fields(obj, "missing_skills")


class ApplicationStatusSerializer(serializers.ModelSerializer):
    """PATCH/PUT body for ``/api/applications/<id>/`` (single status field)."""

    class Meta:
        model = Application
        fields = ["status"]
