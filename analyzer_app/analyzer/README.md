# `analyzer` - Resume Analysis -> ATS Score -> Suggestions -> Optional Job Matching

No login. Open endpoints, UUID ids, per-IP throttle (`ANALYZER_THROTTLE_RATE`, default `60/hour`).
The uploaded file is **not stored** - only extracted text, the parse and layout signals.

## Workflow / endpoints (`/api/analyzer/`)

| Step | Request | Result |
| --- | --- | --- |
| Upload + parse (PDF/DOCX) | `POST resumes/upload/` (multipart `file`) | `resume_id`, `parsed_resume`, `warnings` |
| Stored parse | `GET resumes/<uuid>/` | same payload |
| Mode 1 - general ATS | `POST analyze/resume/` `{resume_id}` | `resume_analysis` (`ats_score`, `section_scores`, `details`) + `suggestions` |
| Mode 2 - job specific | `POST analyze/job/` `{resume_id, job_description, job_title?, company?}` | Mode 1 + `job_analysis` |
| Fetch again | `GET analysis/<uuid>/` | stored result |

Errors: `400` (`unsupported_format`, `empty_file`, `file_too_large`, `corrupted_file`, validation),
`422` (`scanned_pdf`, `no_text`), `404` unknown id, `503` engine/PyMuPDF missing. Body: `{"detail", "code"}`.

## Layout

```
analyzer/
  config.py            every weight / limit / threshold (override with ANALYZER_* settings)
  services/
    text_extractor.py    validation + PDF (PyMuPDF) / DOCX (stdlib) extraction, layout signals
    resume_parser.py     reuses resume_parser.parser.extractors; adds sections, entries, hyperlinks
    skills_taxonomy.py   skills, aliases ("RESTful APIs" == "REST API"), implications, related skills
    structure_/formatting_/experience_/education_analyzer.py   section scorers (+ JD matching for exp/edu)
    ats_scorer.py        general score = weighted section scores (weights in config.ATS_WEIGHTS)
    jd_parser.py  keyword_matcher.py  skill_matcher.py  semantic.py  job_matcher.py
    suggestion_engine.py  resume_analysis.py (facade used by views)
```

## Scoring

* **ATS score** = structure 20 / skills 20 / experience 15 / projects 15 / education 10 / contact 10 / formatting 10.
* **Job match** = skills 35 / keywords 20 / experience 15 / projects 10 / education 10 / semantic 10.
  Components the JD gives no information for are skipped and the rest re-normalised.
* **Semantic**: pure-python TF-IDF + cosine over canonicalised skill tokens. Set
  `ANALYZER_USE_SBERT = True` (and `pip install sentence-transformers`) to use SBERT; it falls back automatically.
* Related skills (Flask vs Django) earn half credit and are reported as `related_skills`, never as matches.

## Authenticity rule

Suggestions never tell the candidate to claim a skill, role, number or certification. Missing items are
phrased conditionally ("If you have genuine experience with Docker ...") and offer learning as the honest
alternative; `suggestion_engine.assert_authentic` + tests enforce it. Formatting findings are always
"Potential ATS compatibility issue", never a rejection guarantee.

## Run

```bash
cd backend/JobRix
export PYTHONPATH=../../Backend/resume_parser/resume_parser   # engine (see note in the PR)
python manage.py migrate
python manage.py test analyzer
```
