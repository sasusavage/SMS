"""Step 5 route tests: score entry grid + results compute/review/publish."""
from decimal import Decimal

from models.enums import UserRole
from models.operational import AssessmentScore, TermResult
from tests.test_results_engine import build_school
from tests.factories import make_user


def _login(client, slug, email, password='pw'):
    return client.post('/auth/login', data={
        'school_slug': slug, 'email': email, 'password': password})


def _admin(db, ctx, email='admin@s.test'):
    make_user(db, ctx['school'], email=email, role=UserRole.school_admin)


# --- Score entry ------------------------------------------------------------
def test_scores_requires_teacher_or_admin(app, db, client):
    ctx = build_school(db)
    make_user(db, ctx['school'], email='p@s.test', role=UserRole.parent)
    db.session.commit()
    _login(client, 's', 'p@s.test')
    assert client.get('/teacher/scores').status_code == 403


def test_save_scores_via_route(app, db, client):
    ctx = build_school(db)
    _admin(db, ctx)
    db.session.commit()
    _login(client, 's', 'admin@s.test')
    s0 = ctx['students'][0]
    c1, c2 = ctx['comps']
    client.post(
        f'/teacher/scores?class_id={ctx["klass"].id}'
        f'&subject_id={ctx["subject"].id}&term_id={ctx["term"].id}',
        data={f'score_{s0.id}_{c1.id}': '80', f'score_{s0.id}_{c2.id}': '60'},
        follow_redirects=True)
    assert AssessmentScore.query.filter_by(student_id=s0.id).count() == 2


# --- Compute / review / publish flow ----------------------------------------
def _enter_scores(db, ctx):
    s0 = ctx['students'][0]
    for comp in ctx['comps']:
        db.session.add(AssessmentScore(
            school_id=ctx['school'].id, student_id=s0.id,
            class_id=ctx['klass'].id, subject_id=ctx['subject'].id,
            term_id=ctx['term'].id, assessment_component_id=comp.id, score=80))
    db.session.commit()


def test_compute_then_publish_flow(app, db, client):
    ctx = build_school(db)
    _admin(db, ctx)
    _enter_scores(db, ctx)
    _login(client, 's', 'admin@s.test')
    cid, tid = ctx['klass'].id, ctx['term'].id

    # Compute
    client.post(f'/admin/results/compute?class_id={cid}&term_id={tid}',
                follow_redirects=True)
    assert TermResult.query.filter_by(school_id=ctx['school'].id).count() >= 1
    assert TermResult.query.filter_by(is_published=True).count() == 0

    # Publish
    client.post(f'/admin/results/publish?class_id={cid}&term_id={tid}',
                follow_redirects=True)
    assert TermResult.query.filter_by(is_published=True).count() >= 1

    # Unpublish
    client.post(f'/admin/results/unpublish?class_id={cid}&term_id={tid}',
                follow_redirects=True)
    assert TermResult.query.filter_by(is_published=True).count() == 0


def test_results_page_renders(app, db, client):
    ctx = build_school(db)
    _admin(db, ctx)
    db.session.commit()
    _login(client, 's', 'admin@s.test')
    r = client.get(f'/admin/results/?class_id={ctx["klass"].id}&term_id={ctx["term"].id}')
    assert r.status_code == 200


def test_teacher_cannot_access_results(app, db, client):
    ctx = build_school(db)
    make_user(db, ctx['school'], email='t@s.test', role=UserRole.teacher)
    db.session.commit()
    _login(client, 's', 't@s.test')
    assert client.get('/admin/results/').status_code == 403


def test_compute_bad_weights_flashes_error(app, db, client):
    ctx = build_school(db, weights=(40, 50))  # 90 != 100
    _admin(db, ctx)
    db.session.commit()
    _login(client, 's', 'admin@s.test')
    r = client.post(
        f'/admin/results/compute?class_id={ctx["klass"].id}&term_id={ctx["term"].id}',
        follow_redirects=True)
    assert b'not 100' in r.data
    assert TermResult.query.count() == 0
