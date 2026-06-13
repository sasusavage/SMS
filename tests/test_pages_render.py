"""
Smoke test: every user-facing page renders (HTTP 200) without template errors.
Catches Jinja breakage introduced by the UI redesign.
"""
import pytest

from models.enums import UserRole
from services.template_loader import apply_template
from tests.factories import make_school, make_user, make_platform_user


def _login(client, slug, email, password='pw'):
    return client.post('/auth/login', data={
        'school_slug': slug, 'email': email, 'password': password})


ADMIN_PAGES = [
    '/dashboard/',
    '/onboarding',
    '/admin/config/',
    '/admin/config/academic-years',
    '/admin/config/terms',
    '/admin/config/level-groups',
    '/admin/config/levels',
    '/admin/config/classes',
    '/admin/config/subjects',
    '/admin/config/level-subjects',
    '/admin/config/grading-schemes',
    '/admin/config/components',
    '/admin/config/report-settings',
]


@pytest.fixture()
def admin_client(app, db, client):
    school = make_school(db, slug='render')
    make_user(db, school, email='admin@render.test', role=UserRole.school_admin)
    apply_template(school.id, 'ghana_ges')  # gives a scheme to view bands
    db.session.commit()
    _login(client, 'render', 'admin@render.test')
    return client, school


@pytest.mark.parametrize('path', ADMIN_PAGES)
def test_admin_page_renders(admin_client, path):
    client, _ = admin_client
    resp = client.get(path)
    assert resp.status_code == 200, f'{path} -> {resp.status_code}'


def test_scheme_boundaries_page_renders(admin_client, db):
    from models.config_tables import GradingScheme
    client, school = admin_client
    scheme = GradingScheme.query.filter_by(school_id=school.id).first()
    resp = client.get(f'/admin/config/grading-schemes/{scheme.id}')
    assert resp.status_code == 200


def test_public_pages_render(client):
    assert client.get('/auth/login').status_code == 200
    assert client.get('/auth/password-reset').status_code == 200
    assert client.get('/signup').status_code == 200


def test_error_page_renders(client):
    resp = client.get('/admin/config/')  # not logged in -> redirect to login
    assert resp.status_code in (302, 401)
    # 404 page
    resp = client.get('/no-such-route')
    assert resp.status_code == 404


def test_platform_page_renders(app, db, client):
    make_platform_user(db, email='super@x.test')
    db.session.commit()
    client.post('/auth/login', data={
        'school_slug': '', 'email': 'super@x.test', 'password': 'pw'})
    resp = client.get('/platform/')
    assert resp.status_code == 200
