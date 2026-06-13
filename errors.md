# Errors & Bug Log

Issues found during testing, with status. Newest first.

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
