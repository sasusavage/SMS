# School Management SaaS — Phase 1 Implementation Spec
**Project codename:** SchoolBrain (rename as you like)
**Stack:** Python 3.11+ / Flask / SQLAlchemy / PostgreSQL / Jinja2 + modern CSS
**Style:** Spec 2 / Barns style — backend and database first, frontend styling after

---

## 0. Core Principle: CONFIGURATION OVER CODE

Nothing curriculum-specific is hardcoded. No "JHS", no "IGCSE", no "Term 1", no "A1 = 80-100" anywhere in Python code. Every school defines its own:

- Academic structure (levels, classes, streams)
- Academic calendar (years, terms/semesters, configurable count)
- Grading schemes (grade boundaries, labels, pass marks)
- Assessment structure (components and weights, e.g. Class Score 40% + Exam 60%)
- Report card layout options (show class position or not, comment fields, skills ratings)
- Subjects (core/elective, per level)

The app ships with **seed templates** a school can pick during onboarding, then customize:
1. `ghana_ges` template (Creche → KG1-2 → B1-B6 → B7-B9/JHS → SHS, 3 terms, BECE/WASSCE-style grading)
2. `cambridge` template (Early Years → Primary → Lower Secondary → IGCSE → A-Level, 3 terms, A*-G grading)
3. `blank` template (school builds from scratch)

Templates are just JSON seed data, NOT code branches.

---

## 1. Multi-Tenancy Rules (NON-NEGOTIABLE)

- Strategy: **shared database, shared schema, `school_id` discriminator column**
- EVERY tenant-owned table has `school_id` (FK → `schools.id`, indexed, NOT NULL)
- A global SQLAlchemy query pattern enforces tenant isolation:
  - Implement a `TenantQueryMixin` / helper `tenant_query(Model)` that automatically filters by `g.current_school_id`
  - Direct `Model.query` on tenant models in route code is a code-review failure — always go through the tenant helper
- `g.current_school_id` is resolved per-request from the logged-in user's `school_id` (NOT from URL params — never trust client-supplied school IDs)
- Super admin (platform owner = Sasu) is the ONLY role with cross-tenant access, via separate `/platform` blueprint
- Unique constraints must be scoped: e.g. student admission number unique **per school**, not globally → `UniqueConstraint('school_id', 'admission_no')`
- File uploads (logos, student photos) stored under `uploads/<school_id>/...`

---

## 2. Roles & Permissions

| Role | Scope | Can do |
|---|---|---|
| `super_admin` | Platform | Manage schools, subscriptions, suspend tenants, view platform metrics. No access to grades/students by default. |
| `school_admin` | One school | Everything in their school: config, users, students, fees, results approval |
| `teacher` | One school | Mark attendance, enter scores for assigned class-subjects, write report comments |
| `student` | One school | View own profile, attendance, results (when published), fee balance |
| `parent` | One school | View linked children's data (one parent → many students) |

- Implement as `users.role` enum + decorator `@require_role('school_admin', 'teacher')`
- All school-scoped routes also pass through `@require_same_school` (verifies the resource being accessed belongs to `g.current_school_id`)
- Passwords: bcrypt. Sessions: Flask-Login. CSRF on all forms.

---

## 3. Database Schema (Phase 1)

### 3.1 Platform tables (no school_id)
```
schools
- id (PK)
- name, slug (unique, for subdomain/school code login)
- country, address, phone, email
- logo_path
- curriculum_template_used (string, informational only)
- status: enum(trial, active, suspended)
- created_at

plans                      -- SaaS pricing plans (seed: Free Trial, Basic, Pro)
- id, name, price_ghs, max_students, billing_cycle

subscriptions
- id, school_id, plan_id, starts_on, ends_on, status, paystack_ref

platform_users             -- super admins only
- id, email, password_hash, name
```

### 3.2 Tenant configuration tables (ALL have school_id)
```
academic_years
- id, school_id, name ("2025/2026"), start_date, end_date, is_current (bool)

terms                      -- configurable count: 2 semesters, 3 terms, whatever
- id, school_id, academic_year_id, name ("Term 1" / "Michaelmas"), sequence,
  start_date, end_date, is_current

level_groups               -- e.g. "Primary", "JHS", "Lower Secondary", "Sixth Form"
- id, school_id, name, sequence

levels                     -- e.g. "Basic 4", "Year 7", "IGCSE Year 1"
- id, school_id, level_group_id, name, sequence

classes                    -- actual class/stream, e.g. "Basic 4 Gold", "Year 7B"
- id, school_id, level_id, academic_year_id, name, class_teacher_id (FK users)

subjects
- id, school_id, name, code, is_core (bool)

level_subjects             -- which subjects are offered at which level
- id, school_id, level_id, subject_id

grading_schemes
- id, school_id, name ("BECE Style", "IGCSE A*-G"), is_default (bool)

grade_boundaries
- id, school_id, grading_scheme_id,
  min_score, max_score (decimal, e.g. 80.00–100.00),
  grade_label ("A1", "A*", "Distinction"),
  remark ("Excellent"), grade_point (decimal, nullable), is_pass (bool)
- CHECK: no overlapping ranges within a scheme (validate in service layer)

assessment_components      -- per school: how a final score is composed
- id, school_id, name ("Class Score", "Exam Score", "Coursework"),
  weight_percent (decimal), applies_to_level_group_id (nullable FK; null = all)
- VALIDATION: weights per level_group must sum to 100

report_settings            -- per school report card options
- id, school_id,
  show_class_position (bool), show_grade_point (bool),
  show_skills_ratings (bool), teacher_comment_required (bool),
  head_comment_required (bool), next_term_begins_label (string)
```

### 3.3 Tenant operational tables (ALL have school_id)
```
users
- id, school_id (nullable ONLY for platform_users if you merge tables — prefer
  separate platform_users table), email (unique per school), password_hash,
  name, role enum(school_admin, teacher, student, parent), phone, is_active

students
- id, school_id, user_id (nullable — young students may have no login),
  admission_no (unique per school), first_name, last_name, other_names,
  gender, dob, photo_path, current_class_id, date_admitted,
  guardian_name, guardian_phone, status enum(active, graduated, withdrawn)

parent_students            -- many-to-many
- id, school_id, parent_user_id, student_id, relationship ("Mother")

teacher_assignments        -- which teacher teaches which subject in which class
- id, school_id, teacher_user_id, class_id, subject_id, term_id

attendance_records
- id, school_id, student_id, class_id, date,
  status enum(present, absent, late, excused), marked_by (FK users)
- UniqueConstraint(school_id, student_id, date)

assessment_scores          -- raw component scores entered by teachers
- id, school_id, student_id, class_id, subject_id, term_id,
  assessment_component_id, score (decimal 0–100), entered_by, entered_at
- UniqueConstraint(school_id, student_id, subject_id, term_id, assessment_component_id)

term_results               -- computed: weighted total + grade snapshot
- id, school_id, student_id, class_id, subject_id, term_id,
  total_score (decimal), grade_label, remark, is_pass,
  class_position (nullable int), computed_at
- Snapshot grade_label at computation time (don't re-derive later — boundaries may change)

report_comments
- id, school_id, student_id, term_id, teacher_comment, head_comment,
  attendance_present, attendance_total

audit_logs
- id, school_id (nullable for platform actions), user_id, action,
  entity, entity_id, meta (JSONB), created_at
```

---

## 4. The Results Engine (heart of the configurability)

Service: `services/results_engine.py`

```
compute_term_results(school_id, class_id, term_id):
  1. Load assessment_components for the school (respect level_group override)
  2. Validate weights sum to 100 — abort with clear error if not
  3. For each student in class, each subject offered:
     weighted_total = Σ (component_score × weight / 100)
     - Missing component score => treat as 0 BUT flag in a warnings list
  4. Map weighted_total → grade via the school's default grading_scheme
  5. If report_settings.show_class_position: rank students per subject
     and overall (average of totals), standard competition ranking (1,2,2,4)
  6. Upsert into term_results with snapshot of grade_label/remark
  7. Return summary: computed count, warnings (missing scores), errors
```

Rules:
- Results are computed, reviewed by school_admin, then **published** (add `is_published` bool on a `result_batches` table or on term_results) — students/parents only see published results
- Re-computation allowed until published; after publishing requires admin "unpublish" with audit log entry

---

## 5. Onboarding Flow (tenant setup wizard)

`/signup` → creates school + first school_admin user → wizard:

1. **School profile** — name, country, logo, contact
2. **Pick template** — Ghana GES / Cambridge / Blank (loads seed JSON into config tables)
3. **Academic year + terms** — confirm/edit dates, set current term
4. **Levels & classes** — review seeded levels, add streams ("Gold", "B")
5. **Subjects** — review seeded subjects per level, edit
6. **Grading scheme** — review seeded boundaries, edit inline
7. **Assessment weights** — review (e.g. 40/60), edit, validate sum = 100
8. **Done** → dashboard with checklist (add teachers, add students, take attendance)

Seed templates live in `seeds/templates/ghana_ges.json` and `seeds/templates/cambridge.json`. Structure: levels, level_groups, subjects, grading scheme + boundaries, components, terms-per-year count, report settings defaults.

---

## 6. Routes / Blueprints (Phase 1)

```
/auth          login (school slug + email + password), logout, password reset
/onboarding    signup + wizard steps (school_admin only, pre-completion)
/dashboard     role-aware landing

/admin/config  academic years, terms, level groups, levels, classes,
               subjects, level-subjects, grading schemes + boundaries,
               assessment components, report settings   (school_admin)
/admin/users   CRUD teachers/parents, reset passwords, deactivate
/admin/students CRUD + CSV bulk import (you've built CSV import before —
               same pattern: validate, preview, commit) + promote/transfer class

/teacher/attendance   pick class → mark daily attendance grid
/teacher/scores       pick class+subject+term → score entry grid
                      (one row per student, one column per assessment component)
/teacher/comments     report comments for class teacher's students

/admin/results        compute, review warnings, publish/unpublish per class+term
/reports/report-card/<student_id>/<term_id>   HTML view + PDF (WeasyPrint)

/portal/student       own results (published only), attendance, profile
/portal/parent        children switcher → same views

/platform/*           super_admin: schools list, suspend/activate,
                      subscriptions, plans, metrics
```

API style: server-rendered Jinja pages + JSON endpoints where grids need them (score entry grid posts JSON). All POST/PUT/DELETE CSRF-protected.

---

## 7. Phase Plan for Claude Code (strict order)

**Step 1 — Foundation**
- Flask app factory, config, SQLAlchemy models for ALL tables above, Alembic migrations, tenant query helper, auth (Flask-Login, bcrypt), role decorators, audit log helper
- Seed script: one demo school per template + super admin

**Step 2 — Config module**
- Onboarding wizard + all /admin/config CRUD with validation (no overlapping grade boundaries, weights sum to 100, term dates inside academic year)

**Step 3 — People**
- Users CRUD, students CRUD + CSV import, parent-student linking, teacher assignments

**Step 4 — Attendance**
- Daily attendance grid + monthly summary per class

**Step 5 — Scores & Results**
- Score entry grid, results engine, review/publish flow, class position ranking

**Step 6 — Report cards**
- HTML report card template driven entirely by report_settings + PDF export

**Step 7 — Portals**
- Student + parent portals (published data only)

**Step 8 — Platform**
- Super admin panel, plans, manual subscription marking (Paystack subscription billing = Phase 2)

Each step: write tests for tenant isolation (e.g., school A admin cannot fetch school B student by ID — expect 404, not 403, to avoid leaking existence).

**Out of scope for Phase 1 (do NOT build yet):** fees/Paystack, SMS/email notifications, timetabling, React frontend, mobile app, AI features.

---

## 8. Definition of Done (Phase 1)

- A Ghanaian demo school and a Cambridge demo school both run on the SAME deployed instance with completely different structures, grading and report cards — zero code changes between them
- Tenant isolation tests pass
- A teacher can go from login → mark attendance → enter scores → admin computes + publishes → parent sees report card PDF
