"""Phase 3 polish: fee receipt, CLI fee reminders, dashboard charts."""
from unittest.mock import patch

from models.enums import UserRole, SchoolStatus
from models.fees import Invoice
from models.notifications import NotificationLog
from services import fees as feesvc, platform_settings, school_settings
from models.config_tables import Term, Level
from tests.factories import make_school, make_user, make_student, make_class


def _login(client, slug, email):
    return client.post('/auth/login', data={'school_slug': slug, 'email': email,
                                            'password': 'pw'})


def _school_with_invoice(db, slug='s'):
    s = make_school(db, slug=slug)
    klass = make_class(db, s, name='B1 A')
    level = Level.query.filter_by(school_id=s.id).first()
    term = Term(school_id=s.id, academic_year_id=klass.academic_year_id,
                name='T1', sequence=1)
    db.session.add(term); db.session.flush()
    st = make_student(db, s, admission_no='A1', current_class_id=klass.id)
    st.guardian_phone = '0244000000'
    feesvc.create_fee_structure(s.id, name='Tuition', term_id=term.id,
                                amount=500, level_id=level.id)
    db.session.commit()
    feesvc.generate_invoices(s.id, klass.id, term.id)
    db.session.commit()
    return s, Invoice.query.filter_by(school_id=s.id).first()


# --- Receipt ----------------------------------------------------------------
def test_receipt_renders_html(app, db, client):
    s, inv = _school_with_invoice(db)
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    feesvc.record_payment(s.id, inv.id, 200, method='cash')
    db.session.commit()
    _login(client, 's', 'a@s.test')
    r = client.get(f'/admin/fees/invoices/{inv.id}/receipt')
    assert r.status_code == 200
    assert b'FEE RECEIPT' in r.data
    assert b'200' in r.data  # the payment shows


def test_receipt_other_school_404(app, db, client):
    a, a_inv = _school_with_invoice(db, slug='a')
    b, b_inv = _school_with_invoice(db, slug='b')
    make_user(db, a, email='a@a.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 'a', 'a@a.test')
    assert client.get(f'/admin/fees/invoices/{b_inv.id}/receipt').status_code == 404


# --- CLI fee reminders ------------------------------------------------------
def test_cli_send_fee_reminders(app, db):
    s, inv = _school_with_invoice(db)   # unpaid invoice, guardian phone set
    platform_settings.set('vynfy_api_key', 'KEY')
    school_settings.update_sms(s.id, enabled=True, sender_id='X')
    db.session.commit()
    runner = app.test_cli_runner()
    with patch('services.notify._vynfy_send', return_value={'data': {}}):
        result = runner.invoke(args=['send-fee-reminders'])
    assert result.exit_code == 0
    assert 'Sent' in result.output
    # a reminder SMS was logged for the outstanding invoice
    assert NotificationLog.query.filter_by(school_id=s.id, channel='sms').count() >= 1


def test_cli_skips_suspended_school(app, db):
    s, inv = _school_with_invoice(db)
    s.status = SchoolStatus.suspended
    platform_settings.set('vynfy_api_key', 'KEY')
    school_settings.update_sms(s.id, enabled=True, sender_id='X')
    db.session.commit()
    runner = app.test_cli_runner()
    with patch('services.notify._vynfy_send', return_value={'data': {}}) as m:
        runner.invoke(args=['send-fee-reminders'])
    m.assert_not_called()   # suspended school skipped


# --- Dashboard charts -------------------------------------------------------
def test_dashboard_shows_charts(app, db, client):
    s, inv = _school_with_invoice(db)
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    r = client.get('/dashboard/')
    assert r.status_code == 200
    assert b'Attendance breakdown' in r.data and b'Fees collection' in r.data
    assert b'bar-track' in r.data   # the chart component rendered
