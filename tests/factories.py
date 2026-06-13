"""Small helpers to create test rows."""
from models.platform import School, PlatformUser
from models.enums import SchoolStatus, UserRole
from models.operational import User, Student
from models.config_tables import LevelGroup, Level, AcademicYear, Class
from auth.security import hash_password


def make_school(db, slug='school-a', name='School A'):
    s = School(name=name, slug=slug, status=SchoolStatus.trial)
    db.session.add(s)
    db.session.flush()
    return s


def make_user(db, school, email='admin@a.test', role=UserRole.school_admin,
              password='pw', name='Admin', is_active=True):
    u = User(school_id=school.id, email=email, name=name, role=role,
             password_hash=hash_password(password), is_active=is_active)
    db.session.add(u)
    db.session.flush()
    return u


def make_student(db, school, admission_no='ADM001', first='Ama', last='Owusu',
                 current_class_id=None):
    st = Student(school_id=school.id, admission_no=admission_no,
                 first_name=first, last_name=last,
                 current_class_id=current_class_id)
    db.session.add(st)
    db.session.flush()
    return st


def make_class(db, school, name='Class A', class_teacher_id=None):
    lg = LevelGroup(school_id=school.id, name=f'G-{name}', sequence=1)
    db.session.add(lg)
    db.session.flush()
    lvl = Level(school_id=school.id, level_group_id=lg.id, name=f'L-{name}',
                sequence=1)
    ay = AcademicYear(school_id=school.id, name='2025/2026', is_current=True)
    db.session.add_all([lvl, ay])
    db.session.flush()
    c = Class(school_id=school.id, level_id=lvl.id, academic_year_id=ay.id,
              name=name, class_teacher_id=class_teacher_id)
    db.session.add(c)
    db.session.flush()
    return c


def make_platform_user(db, email='super@x.test', password='pw'):
    pu = PlatformUser(email=email, name='Super', is_active=True,
                      password_hash=hash_password(password))
    db.session.add(pu)
    db.session.flush()
    return pu
