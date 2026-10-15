# JobRix
MUKUL RAJ<br>
MEHUL<br>
RAJVEER<br>
PRAMEY<br>

## Backend

Django (6.1) + Django REST Framework backend lives in `backend/JobRix`. It is a
JSON API only — the user interface is a separate React application.

Authentication and authorization (email based login, roles, token auth, DRF
generic views) is implemented by the `accounts` app:
see [`backend/JobRix/accounts/README.md`](backend/JobRix/accounts/README.md).

Resume processing is implemented by the `resumes` app: PDF uploads are parsed
**once** by the `resume_parser` engine (packaged in `Backend/resume_parser`,
installed editable — needs `pymupdf`, spaCy optional), the structured result is
stored as JSON on the resume row, and ATS analyses score that stored parse
against a job description without ever re-reading the PDF:
see [`backend/JobRix/resumes/README.md`](backend/JobRix/resumes/README.md).

Job postings and applications are implemented by the `jobs` app: recruiters post
jobs (company stamped from their profile), seekers apply with a parsed resume -
the stored parse is scored **once** against the posting's requirements, the score
is snapshotted on the application, and recruiters get a candidate list ranked by
score plus a submitted → screening → interview → offer/rejected status flow.

The React frontend lives in `frontend/` (Vite + react-router, token auth, no UI
framework) and covers all three apps: sign up/in, resume upload with the
parse-once badge, ad-hoc ATS scoring, the job board, apply-with-instant-score,
ranked candidate lists and the application pipeline:
see [`frontend/README.md`](frontend/README.md) for setup and a 2-minute mentor
demo script.

```bash
# terminal 1 - API
cd backend/JobRix && ../.venv/bin/python manage.py runserver
# terminal 2 - UI (CORS is preconfigured for localhost:5173)
cd frontend && npm install && npm run dev        # http://localhost:5173
```

All secrets and environment specific values live in `backend/JobRix/.env`, which
is git ignored. Start from the committed template:

```bash
cd backend/JobRix
cp .env.example .env          # then set DJANGO_SECRET_KEY (+ SMTP/DB if needed)
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py runserver
../.venv/bin/python manage.py test                # accounts + resumes + jobs suites
```