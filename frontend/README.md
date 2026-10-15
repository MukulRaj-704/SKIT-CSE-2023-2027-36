# JobRix frontend

Minimal React (Vite) client for the JobRix Django API — everything the backend
can do, in one demo-able UI:

| Screen | Backend features shown |
|---|---|
| Sign up / sign in | token auth, roles, recruiter `company_name` |
| Dashboard | role-aware counts, demo flow cheat-sheet |
| My resumes | PDF upload → **parse once** → skills, reparse, delete |
| Resume detail | parsed summary, ad-hoc **ATS scoring** + history (409/503 surfaced) |
| Job board | open postings, per-role visibility |
| Job detail | **apply → instant 0–100 score** (seeker) / **ranked candidates + status dropdowns** (recruiter) |
| My postings | create job (requirements = scoring text), close/reopen, delete |
| My applications | score + status badges, withdraw |

## Run it

Terminal 1 — backend:

```bash
cd backend/JobRix
../.venv/bin/python manage.py runserver        # http://127.0.0.1:8000
```

Terminal 2 — frontend:

```bash
cd frontend
npm install          # first time only
npm run dev          # http://localhost:5173
```

The backend allows CORS from `http://localhost:5173` by default
(`DJANGO_CORS_ALLOWED_ORIGINS` in `.env`). To point at another API host, create
`frontend/.env` with `VITE_API_URL=http://127.0.0.1:8000`.

## Mentor demo script (2 minutes)

1. Register a **job seeker** → upload a PDF resume → watch `parsed` badge + skills.
2. Open the resume → run an ATS analysis against a pasted job description → show score/matched/missing.
3. Sign out, register a **recruiter** (with company) → post a job (requirements list).
4. Sign back in as the seeker → apply → instant score appears → status `submitted`.
5. As the recruiter, open the posting → candidate ranked by score → advance to `interview`.
6. As the seeker, open My applications → withdraw.

## Build

`npm run build` outputs static assets to `dist/` (e.g. for hosting on any
static server behind the API).
