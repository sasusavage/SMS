"""Step 7 portal route tests — access boundaries + published gating."""
from models.enums import UserRole
from models.operational import AssessmentScore
from services import results_engine as re, people
from tests.test_results_engine import build_school
from tests.factories import make_user
from auth.security import hash_password


def _login(client, slug, email, password='pw'):
    return client.post('/auth/login', data={
        'school_slug': slug, 'email': email, 'password': password})


def _student_user(db, ctx, student, email='stu@s.test'):
    u = make_user(db, ctx['school'], email=email, role=UserRole.student)
    student.user_id = u.id
    db.session.flush()
    return u


def _publish(db, ctx, student, score=80):
    for comp in ctx['comps']:
        db.session.add(AssessmentScore(
            school_id=ctx['school'].id, student_id=student.id,
            class_id=ctx['klass'].id, subject_id=ctx['subject'].id,
            term_id=ctx['term'].id, assessment_component_id=comp.id, score=score))
    db.session.commit()
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    re.publish_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()


# --- Access control ---------------------------------------------------------
def test_admin_cannot_access_portal(app, db, client):
    ctx = build_school(db)
    make_user(db, ctx['school'], email='a@s.test', role=UserRole.school_admin)
    db.session.commit()
    _login(client, 's', 'a@s.test')
    assert client.get('/portal/student').status_code == 403


def test_student_home_renders(app, db, client):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    _student_user(db, ctx, s0)
    _publish(db, ctx, s0)
    _login(client, 's', 'stu@s.test')
    r = client.get('/portal/student')
    assert r.status_code == 200
    assert ctx['students'][0].first_name.encode() in r.data


def test_dashboard_redirects_student_to_portal(app, db, client):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    _student_user(db, ctx, s0)
    db.session.commit()
    _login(client, 's', 'stu@s.test')
    r = client.get('/dashboard/', follow_redirects=False)
    assert r.status_code in (302, 303)
    assert '/portal/student' in r.headers['Location']


# --- Published gating -------------------------------------------------------
def test_student_report_published_only(app, db, client):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    _student_user(db, ctx, s0)
    # compute but DON'T publish
    for comp in ctx['comps']:
        db.session.add(AssessmentScore(
            school_id=ctx['school'].id, student_id=s0.id,
            class_id=ctx['klass'].id, subject_id=ctx['subject'].id,
            term_id=ctx['term'].id, assessment_component_id=comp.id, score=80))
    db.session.commit()
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    _login(client, 's', 'stu@s.test')
    # unpublished term report -> 404 (nothing to show)
    assert client.get(f'/portal/student/report/{ctx["term"].id}').status_code == 404


def test_student_report_visible_when_published(app, db, client):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    _student_user(db, ctx, s0)
    _publish(db, ctx, s0)
    _login(client, 's', 'stu@s.test')
    r = client.get(f'/portal/student/report/{ctx["term"].id}')
    assert r.status_code == 200
    assert b'TERMINAL REPORT' in r.data


# --- Parent portal ----------------------------------------------------------
def test_parent_sees_only_linked_child(app, db, client):
    ctx = build_school(db)
    s0, s1 = ctx['students'][0], ctx['students'][1]
    parent = make_user(db, ctx['school'], email='par@s.test', role=UserRole.parent)
    db.session.flush()
    people.link_parent_student(ctx['school'].id, parent.id, s0.id, 'Parent')
    _publish(db, ctx, s0)
    _login(client, 's', 'par@s.test')
    # linked child report -> ok
    assert client.get(
        f'/portal/parent/report/{s0.id}/{ctx["term"].id}').status_code == 200
    # unlinked child report -> 404
    assert client.get(
        f'/portal/parent/report/{s1.id}/{ctx["term"].id}').status_code == 404


def test_parent_home_renders_with_switcher(app, db, client):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    parent = make_user(db, ctx['school'], email='par@s.test', role=UserRole.parent)
    db.session.flush()
    people.link_parent_student(ctx['school'].id, parent.id, s0.id)
    db.session.commit()
    _login(client, 's', 'par@s.test')
    r = client.get('/portal/parent')
    assert r.status_code == 200
    assert s0.first_name.encode() in r.data


def test_student_cannot_view_other_via_parent_route(app, db, client):
    """A student hitting the parent report route for someone else -> 404."""
    ctx = build_school(db)
    s0, s1 = ctx['students'][0], ctx['students'][1]
    _student_user(db, ctx, s0)
    _publish(db, ctx, s1)
    _login(client, 's', 'stu@s.test')
    # student role on parent route, other student -> blocked
    assert client.get(
        f'/portal/parent/report/{s1.id}/{ctx["term"].id}').status_code == 404
