"""Phase 2 tests: notification service, settings, routing, triggers."""
from unittest.mock import patch

from services import notify, secrets_box, platform_settings, school_settings
from models.notifications import (
    SchoolNotificationSettings, PlatformSetting, NotificationLog,
)
from models.enums import UserRole
from models.operational import AssessmentScore
from tests.factories import make_school, make_user, make_student
from tests.test_results_engine import build_school


# --- Encryption -------------------------------------------------------------
def test_secret_roundtrip(app):
    tok = secrets_box.encrypt('hunter2')
    assert tok and tok != 'hunter2'
    assert secrets_box.decrypt(tok) == 'hunter2'


def test_decrypt_garbage_returns_none(app):
    assert secrets_box.decrypt('not-a-token') is None
    assert secrets_box.decrypt(None) is None


# --- Platform settings ------------------------------------------------------
def test_platform_setting_secret_encrypted(app, db):
    platform_settings.set('vynfy_api_key', 'KEY123')
    db.session.commit()
    row = PlatformSetting.query.filter_by(key='vynfy_api_key').first()
    assert row.value_enc and row.value is None       # stored encrypted
    assert 'KEY123' not in (row.value_enc or '')      # not plaintext
    assert platform_settings.get('vynfy_api_key') == 'KEY123'  # decrypts


def test_platform_setting_plain(app, db):
    platform_settings.set('smtp_host', 'smtp.example.com')
    db.session.commit()
    assert platform_settings.get('smtp_host') == 'smtp.example.com'


# --- School settings encryption ---------------------------------------------
def test_school_smtp_password_encrypted(app, db):
    s = make_school(db, slug='s')
    db.session.commit()
    school_settings.update_smtp(
        s.id, enabled=True, host='smtp.x.com', port='587', use_tls=True,
        username='u', password='secretpw', from_email='a@x.com', from_name='X')
    db.session.commit()
    row = SchoolNotificationSettings.query.filter_by(school_id=s.id).first()
    assert row.smtp_password_enc and 'secretpw' not in row.smtp_password_enc
    assert secrets_box.decrypt(row.smtp_password_enc) == 'secretpw'


def test_school_smtp_password_kept_when_blank(app, db):
    s = make_school(db, slug='s')
    db.session.commit()
    school_settings.update_smtp(s.id, enabled=True, host='h', port='587',
                                use_tls=True, username='u', password='pw1',
                                from_email='a@x.com', from_name='X')
    db.session.commit()
    # Update again with blank password -> keeps the old one.
    school_settings.update_smtp(s.id, enabled=True, host='h2', port='587',
                                use_tls=True, username='u', password='',
                                from_email='a@x.com', from_name='X')
    db.session.commit()
    row = SchoolNotificationSettings.query.filter_by(school_id=s.id).first()
    assert secrets_box.decrypt(row.smtp_password_enc) == 'pw1'
    assert row.smtp_host == 'h2'


# --- Email routing / fallback / stub ----------------------------------------
def test_email_stub_when_unconfigured(app, db):
    s = make_school(db, slug='s')
    db.session.commit()
    entry = notify.send_email(s.id, 'to@x.com', 'Hi', 'Body')
    assert entry.status == 'logged' and entry.provider == 'stub'
    assert NotificationLog.query.count() == 1


def test_email_uses_school_smtp(app, db):
    s = make_school(db, slug='s')
    school_settings.update_smtp(s.id, enabled=True, host='smtp.x.com', port='587',
                                use_tls=True, username='u', password='pw',
                                from_email='a@x.com', from_name='X')
    db.session.commit()
    with patch('services.notify._smtp_send') as mock_send:
        entry = notify.send_email(s.id, 'to@x.com', 'Hi', 'Body')
    assert entry.status == 'sent' and entry.provider == 'smtp'
    mock_send.assert_called_once()


def test_email_falls_back_to_platform_smtp(app, db):
    s = make_school(db, slug='s')  # no per-school SMTP
    platform_settings.set('smtp_host', 'smtp.platform.com')
    platform_settings.set('smtp_username', 'pu')
    platform_settings.set('smtp_password', 'pp')
    db.session.commit()
    with patch('services.notify._smtp_send') as mock_send:
        entry = notify.send_email(s.id, 'to@x.com', 'Hi', 'Body')
    assert entry.status == 'sent' and entry.provider == 'platform_smtp'
    mock_send.assert_called_once()


def test_email_failure_recorded_not_raised(app, db):
    s = make_school(db, slug='s')
    school_settings.update_smtp(s.id, enabled=True, host='smtp.x.com', port='587',
                                use_tls=True, username='u', password='pw',
                                from_email='a@x.com', from_name='X')
    db.session.commit()
    with patch('services.notify._smtp_send', side_effect=Exception('boom')):
        entry = notify.send_email(s.id, 'to@x.com', 'Hi', 'Body')  # must not raise
    assert entry.status == 'failed' and 'boom' in entry.error


# --- SMS routing ------------------------------------------------------------
def test_sms_stub_when_no_vynfy_key(app, db):
    s = make_school(db, slug='s')
    db.session.commit()
    entry = notify.send_sms(s.id, '0244123456', 'hi')
    assert entry.status == 'logged' and entry.provider == 'stub'
    assert entry.recipient == '233244123456'   # normalized


def test_sms_uses_vynfy_when_configured(app, db):
    s = make_school(db, slug='s')
    platform_settings.set('vynfy_api_key', 'KEY')
    school_settings.update_sms(s.id, enabled=True, sender_id='MySchool')
    db.session.commit()
    with patch('services.notify._vynfy_send', return_value={'data': {'job_id': 'J1'}}) as m:
        entry = notify.send_sms(s.id, '0244123456', 'hi')
    assert entry.status == 'sent' and entry.provider == 'vynfy'
    assert entry.provider_message_id == 'J1'
    m.assert_called_once()


def test_sms_skipped_when_school_disabled(app, db):
    s = make_school(db, slug='s')
    platform_settings.set('vynfy_api_key', 'KEY')
    school_settings.update_sms(s.id, enabled=False, sender_id='X')
    db.session.commit()
    entry = notify.send_sms(s.id, '0244123456', 'hi')
    assert entry.status == 'logged'   # school opted out -> stub


# --- Triggers ---------------------------------------------------------------
def test_notify_results_published_dispatches(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    s0.guardian_phone = '0244000000'
    # publish a result for s0
    for comp in ctx['comps']:
        db.session.add(AssessmentScore(
            school_id=ctx['school'].id, student_id=s0.id, class_id=ctx['klass'].id,
            subject_id=ctx['subject'].id, term_id=ctx['term'].id,
            assessment_component_id=comp.id, score=80))
    db.session.commit()
    from services import results_engine as re
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    re.publish_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    count = notify.notify_results_published(ctx['school'].id, ctx['klass'].id,
                                            ctx['term'].id)
    db.session.commit()
    assert count >= 1
    # an SMS log to the guardian exists
    assert NotificationLog.query.filter_by(channel='sms',
                                           recipient='233244000000').count() == 1


def test_notify_absentees(app, db):
    s = make_school(db, slug='s')
    st = make_student(db, s, admission_no='A1', first='Ama', last='O')
    st.guardian_phone = '0244111222'
    db.session.commit()
    from datetime import date
    count = notify.notify_absentees(s.id, 1, date(2026, 6, 1),
                                    {str(st.id): 'absent'})
    db.session.commit()
    assert count == 1
    assert NotificationLog.query.filter_by(channel='sms', recipient='233244111222').count() == 1


def test_notify_absentees_skips_present(app, db):
    s = make_school(db, slug='s')
    st = make_student(db, s, admission_no='A1')
    st.guardian_phone = '0244111222'
    db.session.commit()
    from datetime import date
    count = notify.notify_absentees(s.id, 1, date(2026, 6, 1),
                                    {str(st.id): 'present'})
    assert count == 0


def test_notify_account_created(app, db):
    s = make_school(db, slug='s')
    u = make_user(db, s, email='new@s.test', role=UserRole.teacher, name='New T')
    db.session.commit()
    notify.notify_account_created(s.id, u, plaintext_password='temp1234')
    db.session.commit()
    log = NotificationLog.query.filter_by(channel='email',
                                          recipient='new@s.test').first()
    assert log is not None


# --- Routes -----------------------------------------------------------------
def test_school_notifications_page(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    client.post('/auth/login', data={'school_slug': 's', 'email': 'a@s.test',
                                     'password': 'pw'})
    assert client.get('/admin/config/notifications').status_code == 200


def test_platform_settings_page_super_admin_only(app, db, client):
    from tests.factories import make_platform_user
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    make_platform_user(db, email='super@x.test')
    db.session.commit()
    # school admin blocked
    client.post('/auth/login', data={'school_slug': 's', 'email': 'a@s.test',
                                     'password': 'pw'})
    assert client.get('/platform/settings').status_code == 403
    client.post('/auth/logout')
    # super admin ok
    client.post('/auth/login', data={'school_slug': '', 'email': 'super@x.test',
                                     'password': 'pw'})
    assert client.get('/platform/settings').status_code == 200
