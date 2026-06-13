"""
Seed script.

Creates:
  - SaaS plans (Free Trial, Basic, Pro)
  - One platform super admin (Sasu)
  - One demo school per template (Ghana GES + Cambridge), each with a
    school_admin user, fully configured from its template JSON
  - Step 3 test data on the GES demo school: teachers, parents, a class,
    students, parent-student links, and teacher assignments — so you can log
    in and exercise the People features immediately.

Idempotent: re-running will not duplicate rows (it checks before inserting).

Run:
    python seed.py
"""
from datetime import date, timedelta

from app import create_app
from extensions import db
from models.platform import School, Plan, Subscription, PlatformUser
from models.enums import SchoolStatus, UserRole
from models.operational import User
from models.config_tables import Class, Level, AcademicYear, Term
from auth.security import hash_password
from services.template_loader import apply_template
from services import people, attendance, results_engine, report_card


# --- Credentials (demo only — change in production) ------------------------
SUPER_ADMIN = {
    'name': 'Sasu (Platform Owner)',
    'email': 'sasuisaac332@gmail.com',
    'password': 'ChangeMe!Super1',
}

DEMO_SCHOOLS = [
    {
        'name': 'Demo GES Academy',
        'slug': 'demo-ges',
        'country': 'Ghana',
        'template': 'ghana_ges',
        'admin': {'name': 'GES Admin', 'email': 'admin@demoges.test',
                  'password': 'ChangeMe!Ges1'},
    },
    {
        'name': 'Demo Cambridge International',
        'slug': 'demo-cambridge',
        'country': 'United Kingdom',
        'template': 'cambridge',
        'admin': {'name': 'Cambridge Admin', 'email': 'admin@democam.test',
                  'password': 'ChangeMe!Cam1'},
    },
]

PLANS = [
    {'name': 'Free Trial', 'price_ghs': 0, 'max_students': 50, 'billing_cycle': 'trial'},
    {'name': 'Basic', 'price_ghs': 150, 'max_students': 300, 'billing_cycle': 'monthly'},
    {'name': 'Pro', 'price_ghs': 400, 'max_students': None, 'billing_cycle': 'monthly'},
]


def seed_plans():
    created = {}
    for p in PLANS:
        plan = Plan.query.filter_by(name=p['name']).first()
        if not plan:
            plan = Plan(**p)
            db.session.add(plan)
            db.session.flush()
            print(f'  + plan: {p["name"]}')
        created[p['name']] = plan
    return created


def seed_super_admin():
    pu = PlatformUser.query.filter_by(email=SUPER_ADMIN['email']).first()
    if pu:
        print(f'  = super admin exists: {pu.email}')
        return pu
    pu = PlatformUser(
        name=SUPER_ADMIN['name'],
        email=SUPER_ADMIN['email'],
        password_hash=hash_password(SUPER_ADMIN['password']),
        is_active=True,
    )
    db.session.add(pu)
    db.session.flush()
    print(f'  + super admin: {pu.email}')
    return pu


def seed_school(spec, trial_plan):
    existing = School.query.filter_by(slug=spec['slug']).first()
    if existing:
        print(f'  = school exists: {spec["slug"]} (skipping)')
        return existing

    school = School(
        name=spec['name'],
        slug=spec['slug'],
        country=spec['country'],
        curriculum_template_used=spec['template'],
        status=SchoolStatus.trial,
    )
    db.session.add(school)
    db.session.flush()
    print(f'  + school: {school.slug} (id={school.id})')

    # School admin user
    admin = User(
        school_id=school.id,
        email=spec['admin']['email'],
        password_hash=hash_password(spec['admin']['password']),
        name=spec['admin']['name'],
        role=UserRole.school_admin,
        is_active=True,
    )
    db.session.add(admin)

    # Trial subscription
    db.session.add(Subscription(
        school_id=school.id,
        plan_id=trial_plan.id,
        starts_on=date.today(),
        ends_on=date.today() + timedelta(days=30),
        status='active',
    ))

    # Apply curriculum template -> config tables
    summary = apply_template(school.id, spec['template'])
    print(f'    template "{spec["template"]}" applied: {summary}')

    return school


# --- Minimal test data (People) --------------------------------------------
# Kept deliberately small so testing is simple: per school, exactly ONE
# teacher, ONE parent and ONE student, in ONE class, with attendance +
# published results + a report card pre-filled. All use TEST_PASSWORD.
TEST_PASSWORD = 'Test1234'


def seed_people(school):
    """One teacher + one parent + one student, fully set up for testing."""
    sid = school.id
    slug = school.slug  # e.g. 'demo-ges'
    handle = slug.replace('demo-', '')          # 'ges' / 'cambridge'
    domain = f'{slug}.test'
    teacher_email = f'teacher@{domain}'

    # Idempotent: skip if this school's teacher already exists.
    if User.query.filter_by(school_id=sid, email=teacher_email).first():
        print(f'  = people test data already exists for {slug} (skipping)')
        return

    # One teacher, one parent.
    teacher, _ = people.create_user(sid, name='Test Teacher',
                                    email=teacher_email, role='teacher',
                                    password=TEST_PASSWORD)
    parent, _ = people.create_user(sid, name='Test Parent',
                                   email=f'parent@{domain}', role='parent',
                                   password=TEST_PASSWORD)
    print('  + 1 teacher, 1 parent')

    # One class on the school's first level of the current academic year.
    level = (Level.query.filter_by(school_id=sid)
             .order_by(Level.sequence).first())
    ay = AcademicYear.query.filter_by(school_id=sid, is_current=True).first()
    klass = None
    if level and ay:
        class_name = f'{level.name} A'
        klass = Class.query.filter_by(school_id=sid, name=class_name).first()
        if not klass:
            klass = Class(school_id=sid, level_id=level.id,
                          academic_year_id=ay.id, name=class_name,
                          class_teacher_id=teacher.id)
            db.session.add(klass)
            db.session.flush()
            print(f'  + class: {klass.name}')

    # One student, in the class, linked to the parent. Give the student a login
    # (student-role user) so the student portal is testable.
    student = people.create_student(
        sid, admission_no=f'{handle.upper()}001', first_name='Test',
        last_name='Student', gender='F', guardian_name='Test Parent',
        current_class_id=klass.id if klass else None)
    student_user, _ = people.create_user(
        sid, name='Test Student', email=f'student@{domain}', role='student',
        password=TEST_PASSWORD)
    student.user_id = student_user.id
    db.session.flush()
    people.link_parent_student(sid, parent.id, student.id, 'Parent')
    print('  + 1 student (with login), linked to parent')

    term = Term.query.filter_by(school_id=sid, is_current=True).first()
    if not (klass and term):
        return

    # Assign the teacher to every subject offered at the class's level.
    subjects = results_engine.subjects_for_class(sid, klass)
    for subj in subjects:
        people.assign_teacher(sid, teacher.id, klass.id, subj.id, term.id)
    print(f'  + teacher assigned to {len(subjects)} subject(s)')

    # Attendance: last 5 weekdays.
    statuses = ['present', 'present', 'absent', 'late', 'present']
    marked = 0
    d = date.today()
    while marked < 5:
        d -= timedelta(days=1)
        if d.weekday() >= 5:
            continue
        attendance.save_day_attendance(sid, klass.id, d,
                                       {student.id: statuses[marked]},
                                       marked_by=teacher.id)
        marked += 1
    print(f'  + attendance for {marked} weekdays')

    # Scores for every subject -> compute -> publish -> report card ready.
    lg_id = results_engine._class_level_group_id(sid, klass)
    components = results_engine.components_for(sid, lg_id)
    for subj in subjects:
        entries = [{'student_id': student.id, 'component_id': comp.id,
                    'score': 78} for comp in components]
        results_engine.save_scores(sid, klass.id, subj.id, term.id, entries,
                                   entered_by=teacher.id)
    out = results_engine.compute_term_results(sid, klass.id, term.id)
    results_engine.publish_results(sid, klass.id, term.id)
    report_card.save_comment(sid, student.id, term.id,
                             teacher_comment='A solid, consistent performance.',
                             head_comment='Well done. Keep it up.')
    print(f'  + scores + results ({out["computed"]}) published + report comment')


def main():
    app = create_app()
    with app.app_context():
        print('Seeding plans...')
        plans = seed_plans()

        print('Seeding super admin...')
        seed_super_admin()

        print('Seeding demo schools...')
        trial = plans['Free Trial']
        for spec in DEMO_SCHOOLS:
            school = seed_school(spec, trial)
            print(f'Seeding minimal People data for {spec["slug"]}...')
            seed_people(school)

        db.session.commit()

        # --- Summary -------------------------------------------------------
        print('\nSeed complete.\n')
        print('LOGINS (all demo passwords — change in production):')
        print('  Super admin | school code: (blank) | '
              f'{SUPER_ADMIN["email"]} / {SUPER_ADMIN["password"]}')
        print()
        for s in DEMO_SCHOOLS:
            slug = s['slug']
            print(f'  {s["name"]}  (school code: {slug})')
            print(f'    admin   | {s["admin"]["email"]} / {s["admin"]["password"]}')
            print(f'    teacher | teacher@{slug}.test / {TEST_PASSWORD}')
            print(f'    parent  | parent@{slug}.test  / {TEST_PASSWORD}')
            print(f'    student | student@{slug}.test / {TEST_PASSWORD}')
            print(f'    (1 class, attendance + published results + report card; '
                  'student & parent portals ready)')
            print()


if __name__ == '__main__':
    main()
