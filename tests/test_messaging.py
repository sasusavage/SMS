"""Phase 2 messaging: log viewer, retry, bulk SMS, fee reminders."""
from unittest.mock import patch

from models.enums import UserRole
from models.notifications import NotificationLog
from services import notify, fees as feesvc, platform_settings, school_settings
from models.config_tables import Term, Level
from tests.factories import make_school, make_user, make_student, make_class


def _login(client, slug, email):
    return client.post('/auth/login', data={'school_slug': slug, 'email': email,
                                            'password': 'pw'})


def _sms_ready(db, s):
    platform_settings.set('vynfy_api_key', 'KEY')
    school_settings.update_sms(s.id, enabled=True, sender_id='X')


# --- Bulk SMS ---------------------------------------------------------------
def test_bulk_sms_to_class(app, db):
    s = make_school(db, slug='s')
    klass = make_class(db, s, name='B1 A')
    _sms_ready(db, s)
    for i in range(3):
        st = make_student(db, s, admission_no=f'A{i}', current_class_id=klass.id)
        st.guardian_phone = f'024400000{i}'
    make_student(db, s, admission_no='NOPHONE', current_class_id=klass.id)  # no phone
    db.session.commit()
    with patch('services.notify._vynfy_send', return_value={'data': {}}):
        n = notify.bulk_sms_to_class(s.id, klass.id, 'Hello')
    db.session.commit()
    assert n == 3   # only the 3 with phones
    assert NotificationLog.query.filter_by(channel='sms').count() == 3


def test_bulk_sms_all_guardians(app, db):
    s = make_school(db, slug='s')
    _sms_ready(db, s)
    for i in range(2):
        st = make_student(db, s, admission_no=f'A{i}')
        st.guardian_phone = f'024411111{i}'
    db.session.commit()
    with patch('services.notify._vynfy_send', return_value={'data': {}}):
        n = notify.bulk_sms_all_guardians(s.id, 'Hi')
    assert n == 2


# --- Fee reminders ----------------------------------------------------------
def test_fee_reminders_only_outstanding(app, db):
    s = make_school(db, slug='s')
    klass = make_class(db, s, name='B1 A')
    level = Level.query.filter_by(school_id=s.id).first()
    term = Term(school_id=s.id, academic_year_id=klass.academic_year_id,
                name='T1', sequence=1)
    db.session.add(term); db.session.flush()
    _sms_ready(db, s)
    st1 = make_student(db, s, admission_no='A1', current_class_id=klass.id)
    st1.guardian_phone = '0244000001'
    st2 = make_student(db, s, admission_no='A2', current_class_id=klass.id)
    st2.guardian_phone = '0244000002'
    feesvc.create_fee_structure(s.id, name='Tuition', term_id=term.id,
                                amount=500, level_id=level.id)
    db.session.commit()
    feesvc.generate_invoices(s.id, klass.id, term.id)
    db.session.commit()
    # pay st1's invoice fully -> only st2 should get a reminder
    from models.fees import Invoice
    inv1 = Invoice.query.filter_by(student_id=st1.id).first()
    feesvc.record_payment(s.id, inv1.id, 500, method='cash')
    db.session.commit()
    with patch('services.notify._vynfy_send', return_value={'data': {}}):
        n = notify.send_fee_reminders(s.id, term_id=term.id)
    db.session.commit()
    assert n == 1   # only st2 outstanding


# --- Retry ------------------------------------------------------------------
def test_retry_failed_log(app, db):
    s = make_school(db, slug='s')
    _sms_ready(db, s)
    db.session.commit()
    # a failed log
    failed = NotificationLog(school_id=s.id, channel='sms',
                             recipient='233244123456', message='hi',
                             status='failed', error='boom')
    db.session.add(failed); db.session.commit()
    with patch('services.notify._vynfy_send', return_value={'data': {}}):
        new = notify.retry_log(s.id, failed.id)
    db.session.commit()
    assert new is not None and new.status == 'sent'


# --- Routes -----------------------------------------------------------------
def test_messaging_admin_only(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    make_user(db, s, email='t@s.test', role=UserRole.teacher)
    db.session.commit()
    _login(client, 's', 't@s.test')
    assert client.get('/admin/messaging/').status_code == 403
    client.post('/auth/logout')
    _login(client, 's', 'a@s.test')
    assert client.get('/admin/messaging/').status_code == 200


def test_bulk_route_sends(app, db, client):
    s = make_school(db, slug='s')
    klass = make_class(db, s, name='B1 A')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    _sms_ready(db, s)
    st = make_student(db, s, admission_no='A1', current_class_id=klass.id)
    st.guardian_phone = '0244000000'
    db.session.commit()
    _login(client, 's', 'a@s.test')
    with patch('services.notify._vynfy_send', return_value={'data': {}}):
        client.post('/admin/messaging/bulk', data={
            'target': f'class:{klass.id}', 'message': 'Hi all'},
            follow_redirects=True)
    assert NotificationLog.query.filter_by(school_id=s.id, channel='sms').count() == 1
