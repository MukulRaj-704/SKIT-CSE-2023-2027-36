"""
analyzer/models.py
==================
No-login storage for the analyzer workflow. Ids are UUIDs so a result cannot be
guessed by counting. The uploaded file itself is NOT kept: only the extracted
text, the parse and the layout signals are stored (the analyzers never need the
file again).
"""

import uuid

from django.db import models


class AnalyzedResume(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=8)  # pdf | docx
    file_size = models.PositiveIntegerField(default=0)
    page_count = models.PositiveSmallIntegerField(default=1)
    raw_text = models.TextField()
    parsed_data = models.JSONField(default=dict)
    layout = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.id})"


class AnalysisRun(models.Model):
    class Mode(models.TextChoices):
        GENERAL = "general", "General resume ATS check"
        JOB = "job", "Job-specific analysis"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resume = models.ForeignKey(AnalyzedResume, on_delete=models.CASCADE, related_name="analyses")
    mode = models.CharField(max_length=10, choices=Mode.choices)
    job_title = models.CharField(max_length=200, blank=True)
    company = models.CharField(max_length=200, blank=True)
    job_description = models.TextField(blank=True)
    ats_score = models.PositiveSmallIntegerField()
    job_match_score = models.PositiveSmallIntegerField(null=True, blank=True)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["resume", "-created_at"])]

    def __str__(self):
        return f"{self.mode} analysis {self.id}"
