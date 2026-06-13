"""Small helpers to create test rows."""
from models.platform import School, PlatformUser
from models.enums import SchoolStatus, UserRole
from models.operational import User, Student
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


def make_student(db, school, admission_no='ADM001', first='Ama', last='Owusu'):
    st = Student(school_id=school.id, admission_no=admission_no,
                 first_name=first, last_name=last)
    db.session.add(st)
    db.session.flush()
    return st


def make_platform_user(db, email='super@x.test', password='pw'):
    pu = PlatformUser(email=email, name='Super', is_active=True,
                      password_hash=hash_password(password))
    db.session.add(pu)
    db.session.flush()
    return pu
