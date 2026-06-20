"""Per-school CSV data export tests."""
from models.enums import UserRole
from services import fees as feesvc
from models.config_tables import Term, Level
from models.fees import Invoice
from tests.factories import make_school, make_user, make_student, make_class


def _login(client, slug, email):
    return client.post('/auth/login', data={'school_slug': slug, 'email': email,
                                            'password': 'pw'})


def test_export_requires_admin(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='t@s.test', role=UserRole.teacher)
    db.session.commit()
    _login(client, 's', 't@s.test')
    assert client.get('/admin/export/students.csv').status_code == 403


def test_students_export(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    make_student(db, s, admission_no='A1', first='Ama', last='Owusu')
    db.session.commit()
    _login(client, 's', 'a@s.test')
    r = client.get('/admin/export/students.csv')
    assert r.status_code == 200
    assert r.mimetype == 'text/csv'
    assert b'admission_no' in r.data and b'A1' in r.data and b'Owusu' in r.data


def test_export_is_tenant_scoped(app, db, client):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    make_user(db, a, email='a@a.test', role=UserRole.school_admin)
    make_student(db, a, admission_no='AMINE')
    make_student(db, b, admission_no='BOTHER')
    db.session.commit()
    _login(client, 'a', 'a@a.test')
    r = client.get('/admin/export/students.csv')
    assert b'AMINE' in r.data and b'BOTHER' not in r.data   # only own school


def test_fees_export(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    klass = make_class(db, s, name='B1 A')
    level = Level.query.filter_by(school_id=s.id).first()
    term = Term(school_id=s.id, academic_year_id=klass.academic_year_id,
                name='T1', sequence=1)
    db.session.add(term); db.session.flush()
    make_student(db, s, admission_no='A1', current_class_id=klass.id)
    feesvc.create_fee_structure(s.id, name='Tuition', term_id=term.id,
                                amount=500, level_id=level.id)
    db.session.commit()
    feesvc.generate_invoices(s.id, klass.id, term.id)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    r = client.get('/admin/export/fees.csv')
    assert r.status_code == 200 and b'invoice_id' in r.data and b'500' in r.data
