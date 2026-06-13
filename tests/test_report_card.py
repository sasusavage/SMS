"""Step 6 tests: report card data service, comments, and routes."""
from decimal import Decimal

import pytest

from services import report_card, results_engine as re
from services.report_card import ReportError
from models.config_tables import ReportSettings
from models.operational import AssessmentScore, ReportComment
from tests.test_results_engine import build_school
from tests.factories import make_user
from models.enums import UserRole


def _compute(db, ctx, score=80, publish=False):
    s0 = ctx['students'][0]
    for comp in ctx['comps']:
        db.session.add(AssessmentScore(
            school_id=ctx['school'].id, student_id=s0.id,
            class_id=ctx['klass'].id, subject_id=ctx['subject'].id,
            term_id=ctx['term'].id, assessment_component_id=comp.id, score=score))
    db.session.commit()
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    if publish:
        re.publish_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    return s0


# --- Data service -----------------------------------------------------------
def test_build_report_card_includes_results(app, db):
    ctx = build_school(db)
    s0 = _compute(db, ctx, score=80, publish=True)
    data = report_card.build_report_card(ctx['school'].id, s0.id, ctx['term'].id)
    assert data['student'].id == s0.id
    assert len(data['rows']) == 1
    assert data['rows'][0]['grade_label'] == 'A'
    assert data['summary']['average'] == 80.0
    assert data['published'] is True


def test_unpublished_excluded_by_default(app, db):
    ctx = build_school(db)
    s0 = _compute(db, ctx, score=80, publish=False)
    data = report_card.build_report_card(ctx['school'].id, s0.id, ctx['term'].id)
    assert data['rows'] == []          # nothing published
    assert data['published'] is False


def test_unpublished_included_when_requested(app, db):
    ctx = build_school(db)
    s0 = _compute(db, ctx, score=80, publish=False)
    data = report_card.build_report_card(ctx['school'].id, s0.id, ctx['term'].id,
                                         include_unpublished=True)
    assert len(data['rows']) == 1      # preview sees draft


def test_report_settings_drive_layout_flags(app, db):
    ctx = build_school(db, show_position=False)
    s0 = _compute(db, ctx, score=80, publish=True)
    data = report_card.build_report_card(ctx['school'].id, s0.id, ctx['term'].id)
    # position disabled -> stored position is None
    assert data['rows'][0]['class_position'] is None
    assert data['settings'].show_class_position is False


def test_unknown_student_rejected(app, db):
    ctx = build_school(db)
    db.session.commit()
    with pytest.raises(ReportError):
        report_card.build_report_card(ctx['school'].id, 999999, ctx['term'].id)


# --- Comments ---------------------------------------------------------------
def test_save_and_update_comment(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    db.session.commit()
    report_card.save_comment(ctx['school'].id, s0.id, ctx['term'].id,
                             teacher_comment='Good work', head_comment='Keep it up')
    db.session.commit()
    rc = ReportComment.query.filter_by(student_id=s0.id).one()
    assert rc.teacher_comment == 'Good work' and rc.head_comment == 'Keep it up'
    # update only teacher comment
    report_card.save_comment(ctx['school'].id, s0.id, ctx['term'].id,
                             teacher_comment='Excellent')
    db.session.commit()
    assert ReportComment.query.filter_by(student_id=s0.id).count() == 1
    assert ReportComment.query.filter_by(student_id=s0.id).one().teacher_comment == 'Excellent'


def test_comment_appears_in_report(app, db):
    ctx = build_school(db)
    s0 = _compute(db, ctx, score=80, publish=True)
    report_card.save_comment(ctx['school'].id, s0.id, ctx['term'].id,
                             teacher_comment='Well done')
    db.session.commit()
    data = report_card.build_report_card(ctx['school'].id, s0.id, ctx['term'].id)
    assert data['comments'].teacher_comment == 'Well done'


# --- Routes -----------------------------------------------------------------
def _login(client, slug, email, password='pw'):
    return client.post('/auth/login', data={
        'school_slug': slug, 'email': email, 'password': password})


def test_report_card_view_renders(app, db, client):
    ctx = build_school(db)
    make_user(db, ctx['school'], email='a@s.test', role=UserRole.school_admin)
    s0 = _compute(db, ctx, score=80, publish=True)
    _login(client, 's', 'a@s.test')
    r = client.get(f'/reports/report-card/{s0.id}/{ctx["term"].id}')
    assert r.status_code == 200
    assert b'TERMINAL REPORT' in r.data


def test_report_card_requires_login(app, db, client):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    db.session.commit()
    r = client.get(f'/reports/report-card/{s0.id}/{ctx["term"].id}',
                   follow_redirects=False)
    assert r.status_code in (302, 401)


def test_report_card_other_school_404(app, db, client):
    a = build_school(db)
    make_user(db, a['school'], email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    r = client.get(f'/reports/report-card/999999/{a["term"].id}')
    assert r.status_code == 404


def test_pdf_route_falls_back_when_weasyprint_missing(app, db, client):
    """Without WeasyPrint, the .pdf route should redirect (not 500)."""
    ctx = build_school(db)
    make_user(db, ctx['school'], email='a@s.test', role=UserRole.school_admin)
    s0 = _compute(db, ctx, score=80, publish=True)
    _login(client, 's', 'a@s.test')
    r = client.get(f'/reports/report-card/{s0.id}/{ctx["term"].id}.pdf',
                   follow_redirects=False)
    # Either a real PDF (if installed) or a graceful redirect — never a 500.
    assert r.status_code in (200, 302)
    if r.status_code == 200:
        assert r.mimetype == 'application/pdf'
