MUKUL AI - RESUME NLP + ATS + SEMANTIC JOB MATCHING

1. Copy the complete "mukul_ai" folder into:
   backend/JobRix/

2. Add this app to JobRix/settings.py:
   "mukul_ai",

3. Add this URL to JobRix/urls.py:
   path("api/mukul-ai/", include("mukul_ai.urls")))

   Make sure urls.py already has:
   from django.urls import include, path

4. Add this dependency to requirements.txt:
   sentence-transformers>=3.1.1

5. Run from backend/JobRix:
   pip install -r ..\requirements.txt
   python manage.py makemigrations mukul_ai
   python manage.py migrate
   python manage.py check
   python manage.py runserver

API:
POST /api/mukul-ai/analyze/

Use multipart/form-data:
resume = PDF file
job_title = Python Django Developer
job_description = Python Django developer required with REST API PostgreSQL Docker...

The API performs:
PDF -> existing NLP parser -> ATS -> SBERT semantic matching -> final score

Final score:
40% ATS + 60% SBERT

Important:
This folder is designed to be added as a new isolated Django app.
Do not delete or replace the existing resumes app.
