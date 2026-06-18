"""Phase 2 fee routes: admin management + parent online payment + access."""
from unittest.mock import patch

from models.enums import UserRole
from models.fees import FeeStructure, Invoice, FeePayment
from models.config_tables import Term, Level
from services import fees as feesvc, people
from tests.factories import make_school, make_user, make_student, make_class


def _login(client, slug, email, pw='pw'):
    return client.post('/auth/login', data={'school_slug': slug, 'email': email,
                                            'password': pw})


def _school_with_class(db, slug='s'):
    s = make_school(db, slug=slug)
    klass = make_class(db, s, name='B1 A')
    level = Level.query.filter_by(school_id=s.id).first()
    term = Term(school_id=s.id, academic_year_id=klass.academic_year_id,
                name='T1', sequence=1)
    db.session.add(term)
    db.session.flush()
    return s, klass, level, term


# --- Admin management -------------------------------------------------------
def test_admin_create_fee_and_generate(app, db, client):
    s, klass, level, term = _school_with_class(db)
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    make_student(db, s, admission_no='A1', current_class_id=klass.id)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    client.post('/admin/fees/structures', data={
        'name': 'Tuition', 'term_id': term.id, 'level_id': level.id,
        'amount': '500'}, follow_redirects=True)
    assert FeeStructure.query.filter_by(school_id=s.id).count() == 1
    client.post('/admin/fees/generate', data={
        'class_id': klass.id, 'term_id': term.id}, follow_redirects=True)
    assert Invoice.query.filter_by(school_id=s.id).count() == 1


def test_admin_record_payment(app, db, client):
    s, klass, level, term = _school_with_class(db)
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    st = make_student(db, s, admission_no='A1', current_class_id=klass.id)
    feesvc.create_fee_structure(s.id, name='Tuition', term_id=term.id,
                                amount=500, level_id=level.id)
    db.session.commit()
    feesvc.generate_invoices(s.id, klass.id, term.id)
    db.session.commit()
    inv = Invoice.query.filter_by(school_id=s.id).first()
    _login(client, 's', 'a@s.test')
    client.post(f'/admin/fees/invoices/{inv.id}', data={
        'amount': '500', 'method': 'cash'}, follow_redirects=True)
    assert db.session.get(Invoice, inv.id).status == 'paid'


def test_teacher_cannot_access_fees(app, db, client):
    s, klass, level, term = _school_with_class(db)
    make_user(db, s, email='t@s.test', role=UserRole.teacher)
    db.session.commit()
    _login(client, 's', 't@s.test')
    assert client.get('/admin/fees/').status_code == 403


# --- Parent online payment --------------------------------------------------
def test_parent_can_view_and_pay(app, db, client):
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test'
    s, klass, level, term = _school_with_class(db)
    parent, _ = people.create_user(s.id, name='P', email='p@s.test', role='parent', password='parentpw1')
    st = make_student(db, s, admission_no='A1', current_class_id=klass.id)
    people.link_parent_student(s.id, parent.id, st.id, 'Parent')
    feesvc.create_fee_structure(s.id, name='Tuition', term_id=term.id,
                                amount=500, level_id=level.id)
    db.session.commit()
    feesvc.generate_invoices(s.id, klass.id, term.id)
    db.session.commit()
    inv = Invoice.query.filter_by(school_id=s.id).first()
    _login(client, 's', 'p@s.test', pw='parentpw1')
    # view
    assert client.get(f'/portal/fees/{st.id}').status_code == 200
    # pay -> redirected to (mocked) Paystack URL
    with patch('services.paystack.initialize',
               return_value={'ok': True, 'url': 'https://pay/x', 'reference': 'FEE-1'}):
        r = client.post(f'/portal/fees/{st.id}/pay/{inv.id}', follow_redirects=False)
    assert r.status_code in (302, 303) and 'pay/x' in r.headers['Location']


def test_parent_cannot_view_other_childs_fees(app, db, client):
    s, klass, level, term = _school_with_class(db)
    parent, _ = people.create_user(s.id, name='P', email='p@s.test', role='parent', password='parentpw1')
    mine = make_student(db, s, admission_no='A1', current_class_id=klass.id)
    other = make_student(db, s, admission_no='A2', current_class_id=klass.id)
    people.link_parent_student(s.id, parent.id, mine.id, 'Parent')
    db.session.commit()
    _login(client, 's', 'p@s.test', pw='parentpw1')
    assert client.get(f'/portal/fees/{other.id}').status_code == 404


def test_complete_fee_payment_records(app, db):
    """billing.complete_fee_payment verifies + records against the invoice."""
    app.config['PAYSTACK_SECRET_KEY'] = 'sk_test'
    s, klass, level, term = _school_with_class(db)
    st = make_student(db, s, admission_no='A1', current_class_id=klass.id)
    feesvc.create_fee_structure(s.id, name='Tuition', term_id=term.id,
                                amount=500, level_id=level.id)
    db.session.commit()
    feesvc.generate_invoices(s.id, klass.id, term.id)
    db.session.commit()
    inv = Invoice.query.filter_by(school_id=s.id).first()
    from services import billing
    ref = f'FEE-{s.id}-{inv.id}-abc'
    with patch('services.paystack.verify',
               return_value={'ok': True, 'status': 'success', 'amount': 50000}):
        billing.complete_fee_payment(ref)
    db.session.commit()
    assert FeePayment.query.filter_by(invoice_id=inv.id).count() == 1
    assert db.session.get(Invoice, inv.id).status == 'paid'
