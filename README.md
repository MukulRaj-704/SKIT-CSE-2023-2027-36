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

All secrets and environment specific values live in `backend/JobRix/.env`, which
is git ignored. Start from the committed template:

```bash
cd backend/JobRix
cp .env.example .env          # then set DJANGO_SECRET_KEY (+ SMTP/DB if needed)
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py runserver
../.venv/bin/python manage.py test accounts
```