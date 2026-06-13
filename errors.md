# Errors & Bug Log

Issues found during testing, with status. Newest first.

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
