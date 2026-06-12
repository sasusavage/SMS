"""
Tenant isolation helper — the single chokepoint for all tenant-scoped queries.

NON-NEGOTIABLE rule from the spec:
  - g.current_school_id is resolved per-request from the logged-in user's
    school_id, NEVER from URL params (never trust client-supplied school IDs).
  - Route code must query tenant models through tenant_query(Model) / the
    TenantQueryMixin, never via bare Model.query. A bare Model.query on a
    tenant model is a code-review failure.

Usage:
    from services.tenant import tenant_query
    students = tenant_query(Student).all()          # auto-filtered by school
    student = tenant_query(Student).filter_by(id=sid).first()  # 404 if other school

Or, since tenant models mix in TenantQueryMixin:
    Student.tenant.all()
    Student.tenant.filter_by(id=sid).first_or_404()
"""
from flask import g, abort

from extensions import db
from models.mixins import TenantMixin


def current_school_id():
    """
    The active tenant for this request. Resolved in the request lifecycle
    (see app factory's before_request) from the logged-in user — NOT from the
    URL. Raises if called outside a tenant context to fail loud rather than
    leak across tenants.
    """
    sid = getattr(g, 'current_school_id', None)
    if sid is None:
        raise RuntimeError(
            'current_school_id is not set. tenant_query() must run inside a '
            'request where a school-scoped user is logged in.'
        )
    return sid


def tenant_query(model):
    """
    Return a query for `model` automatically filtered to the current school.

    Refuses non-tenant models (those without school_id) so platform tables are
    never accidentally routed through tenant filtering.
    """
    if not _is_tenant_model(model):
        raise TypeError(
            f'{model.__name__} is not a tenant model (no school_id). '
            f'Query it directly, not via tenant_query().'
        )
    return model.query.filter(model.school_id == current_school_id())


def _is_tenant_model(model):
    return isinstance(model, type) and issubclass(model, TenantMixin)


class _TenantQueryDescriptor:
    """
    Descriptor exposing `Model.tenant` -> a query pre-filtered by school_id.
    Attached to tenant models via TenantQueryMixin.
    """
    def __get__(self, obj, model):
        return tenant_query(model)


class TenantQueryMixin:
    """
    Mix into tenant models to get `Model.tenant`.

    Example:
        class Student(db.Model, TenantMixin, TenantQueryMixin):
            ...
        Student.tenant.filter_by(id=sid).first()
    """
    tenant = _TenantQueryDescriptor()


def install_tenant_query_descriptor():
    """
    Attach the `.tenant` descriptor to every TenantMixin subclass so route code
    can use Model.tenant without each model explicitly inheriting
    TenantQueryMixin. Called once at app startup after models are imported.
    """
    for model in _iter_tenant_models():
        if 'tenant' not in model.__dict__:
            setattr(model, 'tenant', _TenantQueryDescriptor())


def _iter_tenant_models():
    seen = set()
    stack = list(TenantMixin.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        stack.extend(cls.__subclasses__())
        # Only concrete mapped models have __tablename__
        if getattr(cls, '__tablename__', None):
            yield cls


def get_tenant_or_404(model, obj_id):
    """
    Fetch a tenant-owned object by id, scoped to the current school.

    Returns 404 (not 403) when the object belongs to another school, so we do
    not leak the existence of other tenants' resources — per the spec's
    isolation-test requirement.
    """
    obj = tenant_query(model).filter(model.id == obj_id).first()
    if obj is None:
        abort(404)
    return obj
