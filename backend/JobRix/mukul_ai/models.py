from django.db import models
from resumes.models import Resume

class JobMatchAnalysis(models.Model):
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="job_match_analyses")
    job_title = models.CharField(max_length=200, blank=True)
    job_description = models.TextField()
    ats_score = models.FloatField()
    keyword_coverage = models.FloatField(default=0.0)
    matched_skills = models.JSONField(default=list, blank=True)
    missing_skills = models.JSONField(default=list, blank=True)
    ats_suggestions = models.JSONField(default=list, blank=True)
    semantic_score = models.FloatField()
    semantic_engine = models.CharField(max_length=120, default="SBERT: all-MiniLM-L6-v2")
    semantic_warning = models.TextField(blank=True)
    job_match_score = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["resume", "-created_at"])]

    def __str__(self):
        return f"{self.resume_id}: {self.job_match_score}%"
