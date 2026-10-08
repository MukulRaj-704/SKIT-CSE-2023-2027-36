from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [("resumes", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="JobMatchAnalysis",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("job_title", models.CharField(blank=True, max_length=200)),
                ("job_description", models.TextField()),
                ("ats_score", models.FloatField()),
                ("keyword_coverage", models.FloatField(default=0.0)),
                ("matched_skills", models.JSONField(blank=True, default=list)),
                ("missing_skills", models.JSONField(blank=True, default=list)),
                ("ats_suggestions", models.JSONField(blank=True, default=list)),
                ("semantic_score", models.FloatField()),
                ("semantic_engine", models.CharField(default="SBERT: all-MiniLM-L6-v2", max_length=120)),
                ("semantic_warning", models.TextField(blank=True)),
                ("job_match_score", models.FloatField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resume", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="job_match_analyses", to="resumes.resume")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
