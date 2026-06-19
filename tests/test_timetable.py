"""Phase 3 timetable service tests."""
import pytest

from services import timetable as tt
from services.timetable import TimetableError
from models.timetable import Period, TimetableSlot
from models.config_tables import Subject
from models.enums import UserRole
from tests.factories import make_school, make_user, make_class


def _ctx(db, slug='s'):
    s = make_school(db, slug=slug)
    c1 = make_class(db, s, name='B1 A')
    c2 = make_class(db, s, name='B1 B')
    subj = Subject(school_id=s.id, name='Maths', is_core=True)
    teacher = make_user(db, s, email='t@s.test', role=UserRole.teacher)
    db.session.add(subj); db.session.flush()
    p1 = tt.create_period(s.id, name='Period 1', sequence=1)
    p2 = tt.create_period(s.id, name='Period 2', sequence=2)
    db.session.flush()
    return dict(s=s, c1=c1, c2=c2, subj=subj, teacher=teacher, p1=p1, p2=p2)


# --- Periods ----------------------------------------------------------------
def test_create_period(app, db):
    ctx = _ctx(db)
    db.session.commit()
    assert len(tt.periods(ctx['s'].id)) == 2


def test_duplicate_period_rejected(app, db):
    ctx = _ctx(db)
    db.session.commit()
    with pytest.raises(TimetableError, match='already exists'):
        tt.create_period(ctx['s'].id, name='Period 1')


# --- Slots ------------------------------------------------------------------
def test_set_and_update_slot(app, db):
    ctx = _ctx(db)
    db.session.commit()
    tt.set_slot(ctx['s'].id, ctx['c1'].id, 0, ctx['p1'].id, ctx['subj'].id,
                ctx['teacher'].id)
    db.session.commit()
    assert TimetableSlot.query.filter_by(school_id=ctx['s'].id).count() == 1
    # update same cell -> still one row
    tt.set_slot(ctx['s'].id, ctx['c1'].id, 0, ctx['p1'].id, ctx['subj'].id,
                None)
    db.session.commit()
    grid = tt.class_grid(ctx['s'].id, ctx['c1'].id)
    assert grid[(0, ctx['p1'].id)].teacher_user_id is None


def test_clear_slot(app, db):
    ctx = _ctx(db)
    db.session.commit()
    tt.set_slot(ctx['s'].id, ctx['c1'].id, 0, ctx['p1'].id, ctx['subj'].id)
    db.session.commit()
    tt.clear_slot(ctx['s'].id, ctx['c1'].id, 0, ctx['p1'].id)
    db.session.commit()
    assert TimetableSlot.query.filter_by(school_id=ctx['s'].id).count() == 0


def test_teacher_double_booking_rejected(app, db):
    ctx = _ctx(db)
    db.session.commit()
    # teacher in class 1, Mon, period 1
    tt.set_slot(ctx['s'].id, ctx['c1'].id, 0, ctx['p1'].id, ctx['subj'].id,
                ctx['teacher'].id)
    db.session.commit()
    # same teacher, same day+period, different class -> conflict
    with pytest.raises(TimetableError, match='already teaching'):
        tt.set_slot(ctx['s'].id, ctx['c2'].id, 0, ctx['p1'].id, ctx['subj'].id,
                    ctx['teacher'].id)


def test_same_teacher_different_period_ok(app, db):
    ctx = _ctx(db)
    db.session.commit()
    tt.set_slot(ctx['s'].id, ctx['c1'].id, 0, ctx['p1'].id, ctx['subj'].id,
                ctx['teacher'].id)
    tt.set_slot(ctx['s'].id, ctx['c2'].id, 0, ctx['p2'].id, ctx['subj'].id,
                ctx['teacher'].id)  # different period -> fine
    db.session.commit()
    assert TimetableSlot.query.filter_by(school_id=ctx['s'].id).count() == 2


def test_non_teacher_rejected(app, db):
    ctx = _ctx(db)
    parent = make_user(db, ctx['s'], email='p@s.test', role=UserRole.parent)
    db.session.commit()
    with pytest.raises(TimetableError, match='Teacher not found'):
        tt.set_slot(ctx['s'].id, ctx['c1'].id, 0, ctx['p1'].id, ctx['subj'].id,
                    parent.id)


def test_cross_school_class_rejected(app, db):
    a = _ctx(db, slug='a')
    b = _ctx(db, slug='b')
    db.session.commit()
    with pytest.raises(TimetableError, match='Class not found'):
        tt.set_slot(a['s'].id, b['c1'].id, 0, a['p1'].id, a['subj'].id)


def test_teacher_grid(app, db):
    ctx = _ctx(db)
    db.session.commit()
    tt.set_slot(ctx['s'].id, ctx['c1'].id, 0, ctx['p1'].id, ctx['subj'].id,
                ctx['teacher'].id)
    db.session.commit()
    grid = tt.teacher_grid(ctx['s'].id, ctx['teacher'].id)
    assert (0, ctx['p1'].id) in grid
