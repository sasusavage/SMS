"""
Seed script — Step 1.

Creates:
  - SaaS plans (Free Trial, Basic, Pro)
  - One platform super admin (Sasu)
  - One demo school per template (Ghana GES + Cambridge), each with a
    school_admin user, fully configured from its template JSON

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
from auth.security import hash_password
from services.template_loader import apply_template


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
            seed_school(spec, trial)

        db.session.commit()
        print('\nSeed complete.')
        print('  Super admin login: leave school code BLANK, email '
              f'{SUPER_ADMIN["email"]}')
        for s in DEMO_SCHOOLS:
            print(f'  {s["name"]}: school code "{s["slug"]}", '
                  f'admin {s["admin"]["email"]}')


if __name__ == '__main__':
    main()
