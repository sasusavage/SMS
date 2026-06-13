"""
Tenant isolation — the spec's NON-NEGOTIABLE requirement.

School A must never reach School B's data. Cross-tenant fetches return 404
(not 403) so existence isn't leaked.
"""
import pytest
from flask import g

from services.tenant import (
    tenant_query, get_tenant_or_404, current_school_id,
)
from models.operational import Student
from werkzeug.exceptions import NotFound

from tests.factories import make_school, make_student


def test_tenant_query_filters_by_current_school(app, db):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    make_student(db, a, admission_no='A1')
    make_student(db, b, admission_no='B1')
    db.session.commit()

    with app.test_request_context('/'):
        g.current_school_id = a.id
        rows = tenant_query(Student).all()
        assert len(rows) == 1
        assert rows[0].admission_no == 'A1'


def test_cross_tenant_fetch_returns_404_not_403(app, db):
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    b_student = make_student(db, b, admission_no='B1')
    db.session.commit()

    # Acting as school A, try to fetch school B's student by id.
    with app.test_request_context('/'):
        g.current_school_id = a.id
        with pytest.raises(NotFound):
            get_tenant_or_404(Student, b_student.id)


def test_tenant_query_requires_school_context(app, db):
    make_school(db, slug='a')
    db.session.commit()
    with app.test_request_context('/'):
        # No g.current_school_id set
        with pytest.raises(RuntimeError):
            current_school_id()


def test_tenant_query_rejects_non_tenant_model(app, db):
    from models.platform import Plan
    with app.test_request_context('/'):
        g.current_school_id = 1
        with pytest.raises(TypeError):
            tenant_query(Plan)


def test_admission_no_unique_per_school_not_global(app, db):
    """Same admission_no allowed in different schools."""
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    make_student(db, a, admission_no='SAME')
    make_student(db, b, admission_no='SAME')  # must NOT raise
    db.session.commit()
    assert Student.query.filter_by(admission_no='SAME').count() == 2
