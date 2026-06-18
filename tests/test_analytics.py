"""Phase 2 analytics tests."""
from datetime import date, timedelta
from decimal import Decimal

from services import analytics, fees as feesvc, attendance, results_engine as re
from models.enums import UserRole
from models.operational import AssessmentScore
from models.config_tables import Term, Level
from tests.factories import make_school, make_user, make_student, make_class
from tests.test_results_engine import build_school


PAST = (date.today().replace(day=1) - timedelta(days=1)).replace(day=10)


def test_school_overview_counts(app, db):
    s = make_school(db, slug='s')
    klass = make_class(db, s, name='B1 A')
    make_user(db, s, email='t@s.test', role=UserRole.teacher)
    make_student(db, s, admission_no='A1', current_class_id=klass.id)
    make_student(db, s, admission_no='A2', current_class_id=klass.id)
    db.session.commit()
    ov = analytics.school_overview(s.id)
    assert ov['students'] == 2 and ov['classes'] == 1 and ov['teachers'] == 1


def test_attendance_breakdown_rate(app, db):
    s = make_school(db, slug='s')
    klass = make_class(db, s, name='B1 A')
    st = make_student(db, s, admission_no='A1', current_class_id=klass.id)
    db.session.commit()
    attendance.save_day_attendance(s.id, klass.id, PAST, {st.id: 'present'})
    attendance.save_day_attendance(s.id, klass.id, PAST - timedelta(days=1),
                                   {st.id: 'absent'})
    db.session.commit()
    br = analytics.attendance_breakdown(s.id)
    assert br['total'] == 2 and br['present'] == 1 and br['present_rate'] == 50.0


def test_fees_summary(app, db):
    s = make_school(db, slug='s')
    klass = make_class(db, s, name='B1 A')
    level = Level.query.filter_by(school_id=s.id).first()
    term = Term(school_id=s.id, academic_year_id=klass.academic_year_id,
                name='T1', sequence=1)
    db.session.add(term); db.session.flush()
    st = make_student(db, s, admission_no='A1', current_class_id=klass.id)
    feesvc.create_fee_structure(s.id, name='Tuition', term_id=term.id,
                                amount=500, level_id=level.id)
    db.session.commit()
    feesvc.generate_invoices(s.id, klass.id, term.id)
    db.session.commit()
    from models.fees import Invoice
    inv = Invoice.query.filter_by(school_id=s.id).first()
    feesvc.record_payment(s.id, inv.id, 200, method='cash')
    db.session.commit()
    fz = analytics.fees_summary(s.id)
    assert fz['billed'] == Decimal('500')
    assert fz['collected'] == Decimal('200')
    assert fz['outstanding'] == Decimal('300')


def test_results_summary_pass_rate(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    for comp in ctx['comps']:
        db.session.add(AssessmentScore(
            school_id=ctx['school'].id, student_id=s0.id, class_id=ctx['klass'].id,
            subject_id=ctx['subject'].id, term_id=ctx['term'].id,
            assessment_component_id=comp.id, score=80))
    db.session.commit()
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    re.publish_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    rs = analytics.results_summary(ctx['school'].id)
    # 1 of 3 students scored (others computed as 0 -> fail), so 1 passing row.
    assert rs['published'] >= 1 and rs['passed'] == 1
    assert rs['pass_rate'] is not None


def test_dashboard_renders_with_analytics(app, db, client):
    s = make_school(db, slug='s')
    make_user(db, s, email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    client.post('/auth/login', data={'school_slug': 's', 'email': 'a@s.test',
                                     'password': 'pw'})
    r = client.get('/dashboard/')
    assert r.status_code == 200
    assert b'Attendance rate' in r.data
