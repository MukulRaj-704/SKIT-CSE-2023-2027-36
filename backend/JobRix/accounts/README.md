# accounts — authentication & authorization

JSON API for identity, roles and profiles on the JobRix platform, built with
Django and Django REST Framework **generic views**. There is no server rendered
UI here: the product frontend is a separate React application that consumes
these endpoints.

## Layout

| File | Purpose |
| --- | --- |
| `models.py` | `User` (email login + `role`), `UserManager`, `SeekerProfile`, `RecruiterProfile`, `Company`, `Role` |
| `signals.py` | Creates the role profile as soon as an account is created |
| `permissions.py` | Reusable role guards (`HasRole`, `IsJobSeeker`, `IsRecruiter`, `IsPlatformAdmin`) and object level guards (`IsOwnerOrReadOnly`, `IsRecruiterOrReadOnly`) |
| `serializers.py` | Validation + persistence for every endpoint |
| `views.py` | DRF **generic views** for the API |
| `urls.py` | API URLConf mounted at `/api/accounts/` |
| `forms.py`, `admin.py` | Admin-only forms + admin wiring for the email based user model |
| `templates/emails/` | Transactional email bodies (password reset), plain text |
| `tests.py` | Test suite: auth, authorization, reset link, admin |
| `migrations/0001_initial.py` | Initial schema |

## Roles

| Role | Allowed |
| --- | --- |
| `job_seeker` | own account, own candidate profile, browse companies |
| `recruiter` | own account, own recruiter profile, browse candidates, create/own companies |
| `admin` | everything, plus account administration (roles, verification) |

`Role.ADMIN` can never be self assigned: it is granted by an existing
administrator through `PATCH /api/accounts/users/<id>/` or the Django admin.

## Authentication

* `rest_framework.authtoken` tokens (`Authorization: Token <key>`) for the React
  client and any other API consumer.
* Django session authentication is enabled for the DRF browsable API only
  (`/api-auth/login/`, developer convenience).
* Passwords go through Django's `AUTH_PASSWORD_VALIDATORS`.
* `register/`, `login/` and the password reset endpoints are rate limited with
  the `auth` throttle scope.
* `IsAuthenticated` is the project wide DRF default; the open endpoints opt out
  explicitly with `AllowAny`.

## API — mounted at `/api/accounts/`

| Method | URL | Access | Notes |
| --- | --- | --- | --- |
| POST | `register/` | anyone | job seeker or recruiter, returns `{token, user}` |
| POST | `login/` | anyone | email + password, returns `{token, user}` |
| POST | `logout/` | authenticated | revokes the caller's token |
| POST | `password/reset/` | anyone | emails a reset link pointing at the React app |
| POST | `password/reset/confirm/` | anyone | `uid`, `token`, `new_password`, `new_password_confirm` |
| POST | `password/change/` | authenticated | `old_password`, `new_password`, `new_password_confirm` |
| GET, PUT, PATCH | `me/` | authenticated | own account; `email`, `role`, `is_active` are read only |
| GET, PUT, PATCH | `seeker-profile/` | job seeker | own candidate profile |
| GET, PUT, PATCH | `recruiter-profile/` | recruiter | own profile; `is_verified` is read only |
| GET | `seekers/` | recruiter, admin | supports `?search=` and `?ordering=` |
| GET | `recruiters/` | admin | |
| GET, POST | `companies/` | read: authenticated / write: recruiter, admin | `owner` always comes from the request |
| GET, PUT, PATCH, DELETE | `companies/<id>/` | read: authenticated / write: owner, admin | |
| GET | `users/` | admin | paginated account list |
| GET, PUT, PATCH, DELETE | `users/<id>/` | admin | only place where `role`, `is_active`, `is_staff` change; self lockout is blocked |

```bash
# register a job seeker and use the returned token
curl -X POST http://127.0.0.1:8000/api/accounts/register/ \
  -H "Content-Type: application/json" \
  -d '{"email":"seeker@example.com","first_name":"Seera","last_name":"Nair",
       "password":"JobRix-Auth-Pass-2026","password_confirm":"JobRix-Auth-Pass-2026",
       "role":"job_seeker"}'

curl http://127.0.0.1:8000/api/accounts/me/ -H "Authorization: Token <key>"
```

## Password reset contract (for the React app)

1. Frontend posts the email to `POST /api/accounts/password/reset/`.
2. The backend emails a link built from `FRONTEND_URL`:

   `{FRONTEND_URL}/reset-password?uid=<uid>&token=<token>`

3. The React screen reads `uid` + `token` from the query string and posts them
   to `POST /api/accounts/password/reset/confirm/` together with the new
   password. A successful reset also revokes every API token of that account.

## Configuration (secrets stay out of git)

All environment specific values live in `backend/JobRix/.env`, which is listed
in `.gitignore` and therefore never committed. `.env.example` documents every
supported variable (Django secret key, debug flag, allowed hosts, CSRF trusted
origins, `FRONTEND_URL`, database engine + credentials, mailer backend + SMTP
credentials).

```bash
cd JobRix/backend/JobRix
cp .env.example .env          # then fill in DJANGO_SECRET_KEY etc.
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py createsuperuser   # email + first/last name + password
../.venv/bin/python manage.py runserver
../.venv/bin/python manage.py test accounts -v 2
```

Notes:

* Without `DJANGO_SECRET_KEY` the process refuses to start unless
  `DJANGO_DEBUG=True` (local development only).
* Password reset emails are printed to the console while
  `DJANGO_MAILER_BACKEND` is the console backend; switch it to the SMTP backend
  and provide `DJANGO_EMAIL_HOST*` credentials for real delivery.
* The console mailer prints the MIME *encoded* message, so the link appears
  quoted-printable escaped there (`=` shows up as `=3D`). Mail clients decode
  that transparently, but any tool that scrapes the link from the console (or a
  log file) must MIME-decode the body first - see
  `email.message_from_string(...)` + `part.get_payload(decode=True)`.
* Serving the React dev server from a different origin requires that origin in
  `DJANGO_CSRF_TRUSTED_ORIGINS` (and a CORS policy on the API; token auth needs
  no cookies, so CSRF only applies to the browsable API).