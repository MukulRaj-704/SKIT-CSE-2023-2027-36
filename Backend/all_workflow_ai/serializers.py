from rest_framework import serializers


class CompleteAnalysisRequestSerializer(serializers.Serializer):
    resume = serializers.FileField()
    job_description = serializers.CharField(
        min_length=30,
        trim_whitespace=True,
    )
    job_title = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
    )

    def validate_resume(self, value):
        if not value.name.lower().endswith(".pdf"):
            raise serializers.ValidationError(
                "Only PDF resumes are supported."
            )

        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError(
                "Resume must be smaller than 5 MB."
            )

        return value
