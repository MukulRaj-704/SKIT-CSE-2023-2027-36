# JobRix `resumes` app

Resume storage, **parse once** and persisted ATS analysis for job seekers,
wrapping the standalone engine in `Backend/resume_parser/resume_parser`.

## How the parse-once flow works

```
POST /api/resumes/           -> file stored under MEDIA_ROOT/resumes/<user id>/
                             -> services.parse_resume_instance()
                             -> Resume.parsed_data (ParsedResume as JSON)  [once]
POST /api/resumes/<id>/ats/  -> stored JSON -> pipeline.load_parsed()
                             -> pipeline.run_ats(job_description)
                             -> ATSAnalysis row (score, matched/missing, suggestions)
```

The PDF is read exactly once (at upload or manual reparse); every ATS run reuses
`Resume.parsed_data`, so scoring never touches the file again.

## Endpoints (`/api/resumes/`, token auth)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/resumes/` | Own resumes (paginated, light parse summary) |
| POST | `/api/resumes/` | Upload PDF (`file`, optional `title`, `is_default`) → parsed once → 201 |
| GET/PUT/PATCH/DELETE | `/api/resumes/<id>/` | Detail (incl. parsed data), rename, delete (+ stored file) |
| POST | `/api/resumes/<id>/reparse/` | Re-run the parse on the stored file |
| GET | `/api/resumes/<id>/ats/` | Past analyses for the resume |
| POST | `/api/resumes/<id>/ats/` | Score stored parse (`job_description`, optional `job_title`) → 201 |
| GET | `/api/resumes/<id>/ats/<pk>/` | One stored analysis |

Authorization: `IsAuthenticated` + `IsJobSeeker` (recruiters/admins: 403) +
`IsResumeOwner`; querysets are always scoped to `request.user`, so foreign rows
answer 404. The first resume of a seeker becomes the default; `is_default` stays
exclusive per account (model `save()` + a conditional unique constraint).

Status codes worth knowing: `400` invalid body (non-PDF, wrong MIME, over
`RESUME_MAX_UPLOAD_SIZE_MB`, job description shorter than 30 chars), `409`
scoring a resume without a successful parse, `503` engine unavailable during
scoring. Uploads always return `201` — a failed/absent engine is reflected in
`parse_status` (`parsed | failed | pending`) and `parse_error`.

## Engine setup

```bash
cd backend
../.venv/bin/pip install -r requirements.txt   # pulls -e ../Backend/resume_parser/resume_parser (pymupdf)
```

`pyproject.toml` at the engine root declares `pymupdf>=1.23`; spaCy is an
optional extra (`[nlp]`) that only improves name detection — without it
`services.build_pipeline()` switches to the regex fallback automatically.

## Environment (see `.env.example`)

* `RESUME_MAX_UPLOAD_SIZE_MB` (default `5`)
* `RESUME_ALLOWED_CONTENT_TYPES` (default `application/pdf`)
* `RESUME_PARSE_SPACY` (default `True`; ignored when spaCy is not installed)
* `DJANGO_MEDIA_ROOT` / `DJANGO_MEDIA_URL` / `DJANGO_DEFAULT_FILE_STORAGE`

## Tests

```bash
cd backend/JobRix
../.venv/bin/python manage.py test resumes -v 2
```