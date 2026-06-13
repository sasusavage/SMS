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
from models.operational import User, Student
from models.config_tables import Class, Level, AcademicYear, Subject, Term
from auth.security import hash_password
from services.template_loader import apply_template
from services import people, attendance


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


# --- Step 3 test data (People) ---------------------------------------------
# Simple, predictable credentials for the GES demo school so you can log in and
# test users/students/parents/assignments right away.
TEST_PASSWORD = 'Test1234'

TEST_TEACHERS = [
    {'name': 'Akua Boateng', 'email': 'teacher1@demoges.test'},
    {'name': 'Yaw Darko', 'email': 'teacher2@demoges.test'},
]
TEST_PARENTS = [
    {'name': 'Mary Owusu', 'email': 'parent1@demoges.test'},
    {'name': 'John Mensah', 'email': 'parent2@demoges.test'},
]
TEST_STUDENTS = [
    {'admission_no': 'GES001', 'first_name': 'Ama', 'last_name': 'Owusu',
     'gender': 'F', 'guardian_name': 'Mary Owusu'},
    {'admission_no': 'GES002', 'first_name': 'Kofi', 'last_name': 'Mensah',
     'gender': 'M', 'guardian_name': 'John Mensah'},
    {'admission_no': 'GES003', 'first_name': 'Esi', 'last_name': 'Asante',
     'gender': 'F', 'guardian_name': 'Grace Asante'},
    {'admission_no': 'GES004', 'first_name': 'Yaw', 'last_name': 'Boateng',
     'gender': 'M', 'guardian_name': 'Peter Boateng'},
]


def seed_people(school):
    """Seed teachers, parents, students, a class, links and assignments."""
    # Skip if already seeded (idempotent).
    if User.query.filter_by(school_id=school.id,
                            email='teacher1@demoges.test').first():
        print('  = people test data already exists (skipping)')
        return

    sid = school.id

    # Teachers + parents (create_user gives a known password)
    teachers = []
    for t in TEST_TEACHERS:
        u, _ = people.create_user(sid, name=t['name'], email=t['email'],
                                  role='teacher', password=TEST_PASSWORD)
        teachers.append(u)
    parents = []
    for p in TEST_PARENTS:
        u, _ = people.create_user(sid, name=p['name'], email=p['email'],
                                  role='parent', password=TEST_PASSWORD)
        parents.append(u)
    print(f'  + {len(teachers)} teachers, {len(parents)} parents')

    # A class on the first level of the current academic year.
    level = (Level.query.filter_by(school_id=sid)
             .order_by(Level.sequence).first())
    ay = AcademicYear.query.filter_by(school_id=sid, is_current=True).first()
    klass = None
    if level and ay:
        klass = Class.query.filter_by(school_id=sid, name='Basic 1 Gold').first()
        if not klass:
            klass = Class(school_id=sid, level_id=level.id,
                          academic_year_id=ay.id, name='Basic 1 Gold')
            db.session.add(klass)
            db.session.flush()
            print(f'  + class: {klass.name}')

    # Students (placed in the class)
    students = []
    for s in TEST_STUDENTS:
        st = people.create_student(
            sid, admission_no=s['admission_no'], first_name=s['first_name'],
            last_name=s['last_name'], gender=s['gender'],
            guardian_name=s['guardian_name'],
            current_class_id=klass.id if klass else None)
        students.append(st)
    print(f'  + {len(students)} students')

    # Link each parent to two students.
    people.link_parent_student(sid, parents[0].id, students[0].id, 'Mother')
    people.link_parent_student(sid, parents[0].id, students[1].id, 'Mother')
    people.link_parent_student(sid, parents[1].id, students[2].id, 'Father')
    print('  + parent-student links')

    # Assign teacher1 to a couple of subjects in the class for the current term.
    term = Term.query.filter_by(school_id=sid, is_current=True).first()
    if klass and term:
        subjects = (Subject.query.filter_by(school_id=sid)
                    .order_by(Subject.name).limit(2).all())
        for subj in subjects:
            people.assign_teacher(sid, teachers[0].id, klass.id, subj.id, term.id)
        print(f'  + teacher assignments ({len(subjects)})')

    # Attendance: mark the last 5 weekdays with a realistic mix of statuses, so
    # the daily grid AND the monthly summary have something to show.
    if klass and students:
        # Rotating pattern per student so totals aren't all identical.
        pattern = ['present', 'present', 'present', 'absent', 'late',
                   'present', 'excused']
        marked_days = 0
        d = date.today()
        while marked_days < 5:
            d -= timedelta(days=1)
            if d.weekday() >= 5:   # skip Sat/Sun
                continue
            marks = {}
            for i, st in enumerate(students):
                marks[st.id] = pattern[(i + marked_days) % len(pattern)]
            attendance.save_day_attendance(sid, klass.id, d, marks,
                                           marked_by=teachers[0].id)
            marked_days += 1
        print(f'  + attendance marked for {marked_days} recent weekdays')


def main():
    app = create_app()
    with app.app_context():
        print('Seeding plans...')
        plans = seed_plans()

        print('Seeding super admin...')
        seed_super_admin()

        print('Seeding demo schools...')
        trial = plans['Free Trial']
        schools_by_slug = {}
        for spec in DEMO_SCHOOLS:
            schools_by_slug[spec['slug']] = seed_school(spec, trial)

        print('Seeding People test data (GES demo school)...')
        seed_people(schools_by_slug['demo-ges'])

        db.session.commit()

        # --- Summary -------------------------------------------------------
        print('\nSeed complete.\n')
        print('LOGINS (all demo passwords — change in production):')
        print('  Super admin   | school code: (blank) | '
              f'{SUPER_ADMIN["email"]} / {SUPER_ADMIN["password"]}')
        for s in DEMO_SCHOOLS:
            print(f'  School admin  | school code: {s["slug"]:<14} | '
                  f'{s["admin"]["email"]} / {s["admin"]["password"]}')
        print('\n  GES test users (school code: demo-ges, password: '
              f'{TEST_PASSWORD}):')
        for t in TEST_TEACHERS:
            print(f'    teacher | {t["email"]}')
        for p in TEST_PARENTS:
            print(f'    parent  | {p["email"]}')
        print(f'\n  GES has {len(TEST_STUDENTS)} students in class "Basic 1 Gold", '
              'parent links, and teacher assignments.')


if __name__ == '__main__':
    main()
