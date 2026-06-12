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

## Not built yet (later steps)
Config CRUD/wizard (Step 2), people (Step 3), attendance (Step 4),
scores & results engine (Step 5), report cards (Step 6), portals (Step 7),
platform panel (Step 8). Out of scope for Phase 1: fees/Paystack, SMS/email,
timetabling, React, mobile, AI.
