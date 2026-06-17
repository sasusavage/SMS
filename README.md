# SchoolBrain — Multi-Tenant School Management SaaS

Phase 1 implementation. **Step 1 (Foundation) is complete.**

> Core principle: **Configuration over Code.** Nothing curriculum-specific is
> hardcoded — no grade scales, term names, or level names live in Python.
> Every school defines its own structure, loaded from JSON seed templates.

## Stack
Python 3.11+ / Flask 3 / SQLAlchemy 2 / PostgreSQL / Flask-Login / Alembic.

## What's in Step 1
- **App factory** (`app.py`) + config (`config.py`) + extension singletons (`extensions.py`)
- **All 24 Phase-1 models** (`models/`): platform, tenant-config, tenant-operational
- **Multi-tenancy:** `school_id` discriminator on every tenant table; tenant query
  helper (`services/tenant.py`) — `tenant_query(Model)` and `Model.tenant`
  auto-filter by `g.current_school_id` (resolved from the logged-in user, never the URL)
- **Auth** (`auth/`): Flask-Login + bcrypt, login (school slug + email + password),
  logout, password-reset stub, role decorators (`@require_role`, `@platform_only`,
  `@require_same_school`). Super admins are a separate `platform_users` table.
- **Audit log helper** (`services/audit.py`)
- **Alembic migrations** (`migrations/`) — initial schema migration
- **Seed templates** (`seeds/templates/`): `ghana_ges`, `cambridge`, `blank`
- **Template loader** (`services/template_loader.py`) — applies a template's
  structure into a school's config tables
- **Seed script** (`seed.py`): plans, super admin, one demo school per template

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env          # set DATABASE_URL + SECRET_KEY
```

## Database
```bash
# Create all tables
python -m flask --app app db upgrade

# Seed plans, super admin, and two demo schools (Ghana GES + Cambridge)
python seed.py
```

## Run
```bash
python -m flask --app app run        # or: python app.py
```

## Demo logins (after seeding — change passwords in production)
| Who | School code | Email | Password |
|---|---|---|---|
| Super admin | *(blank)* | sasuisaac332@gmail.com | ChangeMe!Super1 |
| GES admin | `demo-ges` | admin@demoges.test | ChangeMe!Ges1 |
| Cambridge admin | `demo-cambridge` | admin@democam.test | ChangeMe!Cam1 |

## Multi-tenancy rules (enforced)
- Every tenant table has `school_id` (FK, indexed, NOT NULL)
- Query tenant models **only** via `tenant_query(Model)` / `Model.tenant` —
  bare `Model.query` on tenant models is a code-review failure
- Unique constraints are school-scoped (e.g. `admission_no` unique per school)
- Cross-tenant access belongs to super admins via `/platform` only

## Deploying on Coolify (Nixpacks)

This repo is Coolify-ready via Nixpacks — no Dockerfile needed.

**1. Create the app in Coolify**
- New Resource → Application → your Git repo (`sasusavage/SMS`), branch `main`
- Build pack: **Nixpacks** (auto-detected). Coolify reads `nixpacks.toml` /
  `Procfile`, which run `start.sh`.

**2. Attach a database**
- Add a PostgreSQL service in Coolify (or use an existing one), then copy its
  connection string.

**3. Set environment variables** (Coolify → your app → Environment Variables):

| Variable | Value |
|---|---|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/dbname` (from your Coolify Postgres) |
| `SECRET_KEY` | a long random string (required in production — app won't start without it) |
| `FLASK_CONFIG` | `production` |
| `PORT` | usually set by Coolify automatically; `start.sh` defaults to 8000 |
| `WEB_CONCURRENCY` | optional, gunicorn workers (default 3) |

**4. Deploy.** On each deploy `start.sh`:
1. runs `flask db upgrade` (creates/updates tables — idempotent),
2. runs `seed_if_empty.py` (seeds demo data only on an empty DB),
3. starts gunicorn on `0.0.0.0:$PORT`.

**5. Health check:** set the Coolify health-check path to **`/health`**
(returns `{"status":"ok"}` 200, or 503 if the DB is unreachable). No auth needed.

**6. First login:** use the seeded super admin (blank school code,
`sasuisaac332@gmail.com`) or a demo school admin. **Change all seeded
passwords immediately.**

> Note: never commit `.env` — set real secrets in Coolify's env var UI.

## Phase 1 — COMPLETE ✅
All 8 steps shipped and tested:
1. Foundation (models, migrations, auth, tenant isolation)
2. Config module (onboarding wizard + `/admin/config` CRUD with validation)
3. People (users, students + CSV import, parent links, teacher assignments)
4. Attendance (daily grid + monthly summary)
5. Scores & Results (score entry, results engine, publish flow, class ranking)
6. Report cards (HTML driven by report_settings + optional WeasyPrint PDF)
7. Portals (student + parent, published data only)
8. Platform panel (super admin: schools, suspend/activate, plans, subscriptions, metrics)

**Out of scope for Phase 1 (Phase 2+):** fees/Paystack billing, SMS/email
notifications, timetabling, React frontend, mobile app, AI features.
