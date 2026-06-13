# Errors & Bug Log

Issues found during testing, with status. Newest first.

---

## Step 4 — Attendance testing (2026-06-13)

Built the daily attendance grid (upsert per student per day) + monthly summary
per class, with teacher/admin access control. Added 22 tests (14 service + 8
route). **Full suite now 125/125 passing.** No schema change
(attendance_records shipped in Step 1) — confirmed by empty autogenerate diff.

### No functional bugs found
Cross-tenant/unassigned-class access returns 404; the save path ignores any
student id not on the class roster (blocks tampered-form writes to other
classes); future-date marking is rejected; per-day uniqueness is upheld by
upsert (re-marking updates, never duplicates).

### TEST-002 — time-fragile tests (fixed-future dates)
- **Severity:** Medium (would cause false failures over time, not a prod bug)
- **Found by:** a monthly-summary test used `date(2026, 6, 15)`, which is in the
  future relative to today (2026-06-13) and tripped the real future-date guard.
  Several other tests hardcoded June 2026 dates that would also "become future"
  if the suite ran later.
- **Fix:** derive marking dates relative to `date.today()` — use the 10th/11th
  of the previous calendar month (always safely past, same month). Summary
  queries derive year/month from those dates too.
- **Lesson:** never hardcode dates near "now" in tests when the code has a
  now-relative guard.
- **Status:** ✅ Fixed.

---

## Step 3 — People testing (2026-06-13)

Built users CRUD, students CRUD + CSV import (validate→preview→commit),
parent-student linking, and teacher assignments. Added 30 tests (21 service +
9 route). **Full suite now 103/103 passing.**

### No functional bugs found
Service-layer-first again paid off — routes wired correctly on first run.
Verified: cross-tenant access returns 404 (reset password / student detail /
toggle-active on another school's row), CSV detects in-file AND in-DB duplicate
admission numbers, only valid CSV rows commit, role checks (can't link a
non-parent, can't assign a non-teacher), and per-school uniqueness of email and
admission_no.

### Note — CSV import uses the session to carry data between preview and commit
The uploaded CSV text is stashed in the Flask session between the preview and
commit steps, and the commit RE-validates before writing (never trusts the
preview). Re-validation means a row that became a duplicate between preview and
commit is still skipped. Acceptable for Phase 1; if files get large, switch to
a temp-file/staging-table approach.

### Cleanup — replaced legacy Query.get() in a test
- `User.query.get()` → `db.session.get(User, ...)`. No deprecation warnings.
- **Status:** ✅ Done.

---

## UI redesign (2026-06-13)

Full restyle to a clean modern SaaS look (single static/css/app.css, app shell
with sidebar/topbar). Added 17 page-render smoke tests; **full suite 73/73
passing.**

### BUG-003 — missing `db` import after switching to `db.session.get()`
- **Severity:** HIGH (would crash auth on every request in production)
- **Found by:** noticing `db.session.get()` was added to `auth/security.py`
  (the Flask-Login user loader) without importing `db`. The test suite did NOT
  catch it at first — the in-memory client reused the session identity, so the
  loader's NameError path wasn't always exercised. A direct `load_user()` probe
  reproduced it.
- **Cause:** modernised `User.query.get()` → `db.session.get(User, ...)` to
  clear a SQLAlchemy 2.0 deprecation, but `db` wasn't in the import list.
- **Fix:** `from extensions import login_manager, bcrypt, db`. Verified
  `load_user()` loads users, platform identities, and returns None for missing.
- **Lesson:** a green suite isn't proof a hot path ran — probe security-critical
  functions directly.
- **Status:** ✅ Fixed.

### Cleanup — replaced legacy Query.get() in app code
- `onboarding.py`, `auth/security.py` now use `db.session.get(...)`. No behavior
  change; removes SQLAlchemy 2.0 deprecation warnings from real code.
- **Status:** ✅ Done.

---

## Step 2 — Config module testing (2026-06-13)

Added 27 tests (17 validation-service + 10 route/wizard). **Full suite now
56/56 passing.** Covered: grade-boundary overlap, weights=100 per bucket, term
dates within academic year, single-current/single-default invariants, config
CRUD tenant-scoping (cross-tenant delete = 404 not 403), validation surfaced
through routes, and the /signup → template-applied → wizard flow.

### Note — no functional bugs found
The validation-service-first approach paid off: building and testing the rules
before the UI meant the routes wired up correctly on the first run. No defects.

### TEST-001 — deprecated Query.get() in a test assertion
- **Severity:** Cosmetic (test-only warning)
- **Fix:** switched `Subject.query.get(id)` → `db.session.get(Subject, id)`.
- **Status:** ✅ Fixed.

---

## Step 1 — Testing (2026-06-13)

Ran a 29-test suite (tenant isolation, auth/decorators, template loader, seed
validation) on in-memory/file SQLite. **Final result: 29/29 passing.** Issues
found and fixed during the run:

### BUG-001 — `audit_logs.meta` used Postgres-only JSONB, breaking portability
- **Severity:** Low (prod fine; blocked SQLite-based tests/local dev)
- **Found by:** test setup — schema failed to create on SQLite.
- **Cause:** `models/operational.py` declared `meta = mapped_column(JSONB)`
  (Postgres-only type).
- **Fix:** `meta = mapped_column(JSON().with_variant(JSONB, 'postgresql'))` —
  JSONB on Postgres (prod), portable JSON elsewhere. No prod behavior change.
- **Status:** ✅ Fixed.

### BUG-002 — Test config pulled Postgres pool options, crashing on SQLite
- **Severity:** Low (test-only)
- **Found by:** test run — `OperationalError` connecting to localhost:5432.
- **Cause:** `TestingConfig` inherited `SQLALCHEMY_ENGINE_OPTIONS`
  (`pool_pre_ping`, `pool_recycle`) from base `Config`; these are
  Postgres-oriented and the default test URL pointed at a real Postgres.
- **Fix:** `TestingConfig.SQLALCHEMY_ENGINE_OPTIONS = {}` and conftest sets
  `TEST_DATABASE_URL`/`DATABASE_URL` to a SQLite temp file BEFORE app import.
- **Status:** ✅ Fixed.

### ENV-001 — pytest cache cannot be written inside OneDrive folder
- **Severity:** Cosmetic (warning only; tests still run)
- **Found by:** test run — `WinError 5 Access is denied` creating
  `.pytest_cache` (project lives under OneDrive, which locks the dir).
- **Fix:** `pytest.ini` with `addopts = -p no:cacheprovider` to disable the
  cache. Not a code bug — environment quirk of running under OneDrive.
- **Status:** ✅ Worked around.

### Notes / non-bugs
- The production DB (217.182.64.6:5436) is reachable ONLY from inside Coolify,
  so integration tests against the live DB cannot run locally. The suite uses
  SQLite to stay runnable anywhere. Models are portable as of BUG-001.
- No defects found in tenant isolation, auth, decorators, or the results of
  applying curriculum templates — all behave per spec.
