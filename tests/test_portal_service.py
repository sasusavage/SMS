"""Step 7 portal service tests — the security boundaries."""
import pytest

from services import portal, results_engine as re
from services.portal import PortalError
from models.enums import UserRole
from models.operational import AssessmentScore
from tests.test_results_engine import build_school
from tests.factories import make_user


def _student_login(db, ctx, student):
    """Attach a student-role login to a Student and return the user."""
    u = make_user(db, ctx['school'], email=f'stu{student.id}@s.test',
                  role=UserRole.student)
    student.user_id = u.id
    db.session.flush()
    return u


def _parent_login(db, ctx, email='par@s.test'):
    return make_user(db, ctx['school'], email=email, role=UserRole.parent)


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


# --- student_for_user -------------------------------------------------------
def test_student_for_user(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    u = _student_login(db, ctx, s0)
    db.session.commit()
    found = portal.student_for_user(ctx['school'].id, u.id)
    assert found is not None and found.id == s0.id


# --- assert_can_view --------------------------------------------------------
def test_student_can_view_only_self(app, db):
    ctx = build_school(db)
    s0, s1 = ctx['students'][0], ctx['students'][1]
    u = _student_login(db, ctx, s0)
    db.session.commit()
    # own record -> ok
    assert portal.assert_can_view(ctx['school'].id, u, s0.id).id == s0.id
    # someone else's -> blocked
    with pytest.raises(PortalError):
        portal.assert_can_view(ctx['school'].id, u, s1.id)


def test_parent_sees_only_linked_children(app, db):
    ctx = build_school(db)
    s0, s1 = ctx['students'][0], ctx['students'][1]
    parent = _parent_login(db, ctx)
    db.session.flush()
    from services import people
    people.link_parent_student(ctx['school'].id, parent.id, s0.id, 'Parent')
    db.session.commit()
    # linked child -> ok
    assert portal.assert_can_view(ctx['school'].id, parent, s0.id).id == s0.id
    # unlinked child -> blocked
    with pytest.raises(PortalError):
        portal.assert_can_view(ctx['school'].id, parent, s1.id)


def test_children_for_parent_lists_links(app, db):
    ctx = build_school(db)
    s0, s1 = ctx['students'][0], ctx['students'][1]
    parent = _parent_login(db, ctx)
    db.session.flush()
    from services import people
    people.link_parent_student(ctx['school'].id, parent.id, s0.id)
    people.link_parent_student(ctx['school'].id, parent.id, s1.id)
    db.session.commit()
    kids = portal.children_for_parent(ctx['school'].id, parent.id)
    assert {k.id for k in kids} == {s0.id, s1.id}


# --- published-only ---------------------------------------------------------
def test_published_results_only(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    # compute but DON'T publish
    for comp in ctx['comps']:
        db.session.add(AssessmentScore(
            school_id=ctx['school'].id, student_id=s0.id,
            class_id=ctx['klass'].id, subject_id=ctx['subject'].id,
            term_id=ctx['term'].id, assessment_component_id=comp.id, score=80))
    db.session.commit()
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    # nothing published -> no terms, no rows
    assert portal.published_terms(ctx['school'].id, s0.id) == []
    assert portal.published_results(ctx['school'].id, s0.id, ctx['term'].id) == []
    # now publish -> visible
    re.publish_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    assert len(portal.published_terms(ctx['school'].id, s0.id)) == 1
    assert len(portal.published_results(ctx['school'].id, s0.id, ctx['term'].id)) == 1


def test_report_card_published_excludes_drafts(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    for comp in ctx['comps']:
        db.session.add(AssessmentScore(
            school_id=ctx['school'].id, student_id=s0.id,
            class_id=ctx['klass'].id, subject_id=ctx['subject'].id,
            term_id=ctx['term'].id, assessment_component_id=comp.id, score=80))
    db.session.commit()
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    data = portal.report_card_published(ctx['school'].id, s0.id, ctx['term'].id)
    assert data['rows'] == []  # unpublished hidden from the portal view


def test_attendance_summary_counts(app, db):
    from datetime import date, timedelta
    from services import attendance
    ctx = build_school(db)
    s0 = ctx['students'][0]
    db.session.commit()
    past = (date.today().replace(day=1) - timedelta(days=1)).replace(day=10)
    attendance.save_day_attendance(ctx['school'].id, ctx['klass'].id, past,
                                   {s0.id: 'present'})
    db.session.commit()
    summary = portal.attendance_summary(ctx['school'].id, s0.id)
    assert summary['present'] == 1 and summary['total'] == 1
