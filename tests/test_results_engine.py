"""Tests for the Step 5 results engine + score entry service."""
from decimal import Decimal

import pytest

from services import results_engine as re
from services.results_engine import ResultsError
from models.config_tables import (
    LevelGroup, Level, AcademicYear, Class, Subject, LevelSubject,
    GradingScheme, GradeBoundary, AssessmentComponent, ReportSettings, Term,
)
from models.operational import AssessmentScore, TermResult, Student
from tests.factories import make_school, make_student


def build_school(db, *, show_position=True, weights=(50, 50)):
    """A fully-configured school: class, 3 students, 1 subject, 2 components,
    a default grading scheme, and report settings."""
    s = make_school(db, slug='s')
    lg = LevelGroup(school_id=s.id, name='Primary', sequence=1)
    db.session.add(lg); db.session.flush()
    lvl = Level(school_id=s.id, level_group_id=lg.id, name='B1', sequence=1)
    ay = AcademicYear(school_id=s.id, name='2025/2026', is_current=True)
    db.session.add_all([lvl, ay]); db.session.flush()
    klass = Class(school_id=s.id, level_id=lvl.id, academic_year_id=ay.id, name='B1 Gold')
    term = Term(school_id=s.id, academic_year_id=ay.id, name='T1', sequence=1)
    subj = Subject(school_id=s.id, name='Maths', code='M', is_core=True)
    db.session.add_all([klass, term, subj]); db.session.flush()
    db.session.add(LevelSubject(school_id=s.id, level_id=lvl.id, subject_id=subj.id))
    # Components
    c1 = AssessmentComponent(school_id=s.id, name='Class', weight_percent=weights[0])
    c2 = AssessmentComponent(school_id=s.id, name='Exam', weight_percent=weights[1])
    db.session.add_all([c1, c2])
    # Grading scheme (simple)
    scheme = GradingScheme(school_id=s.id, name='Std', is_default=True)
    db.session.add(scheme); db.session.flush()
    for lo, hi, lbl, pas in [(70, 100, 'A', True), (50, 69, 'B', True),
                             (0, 49, 'F', False)]:
        db.session.add(GradeBoundary(school_id=s.id, grading_scheme_id=scheme.id,
                                     min_score=lo, max_score=hi, grade_label=lbl,
                                     remark=lbl, is_pass=pas))
    db.session.add(ReportSettings(school_id=s.id, show_class_position=show_position))
    # Students
    students = [make_student(db, s, admission_no=f'A{i}', first=f'F{i}',
                             last=f'L{i}', current_class_id=klass.id)
                for i in range(3)]
    db.session.flush()
    return dict(school=s, klass=klass, term=term, subject=subj,
                comps=[c1, c2], students=students)


def _set(db, ctx, student, comp, score):
    db.session.add(AssessmentScore(
        school_id=ctx['school'].id, student_id=student.id,
        class_id=ctx['klass'].id, subject_id=ctx['subject'].id,
        term_id=ctx['term'].id, assessment_component_id=comp.id, score=score))


# --- Weights validation -----------------------------------------------------
def test_weights_must_sum_100(app, db):
    ctx = build_school(db, weights=(40, 50))  # = 90
    db.session.commit()
    with pytest.raises(ResultsError, match='sum to 90'):
        re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)


# --- Weighted total + grade -------------------------------------------------
def test_weighted_total_and_grade(app, db):
    ctx = build_school(db)  # 50/50
    s0 = ctx['students'][0]
    _set(db, ctx, s0, ctx['comps'][0], 80)   # class
    _set(db, ctx, s0, ctx['comps'][1], 60)   # exam
    db.session.commit()
    out = re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    tr = TermResult.query.filter_by(student_id=s0.id, subject_id=ctx['subject'].id).one()
    assert tr.total_score == Decimal('70.00')   # 80*.5 + 60*.5
    assert tr.grade_label == 'A' and tr.is_pass is True


def test_missing_score_treated_as_zero_with_warning(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    _set(db, ctx, s0, ctx['comps'][0], 100)   # class only; exam missing
    db.session.commit()
    out = re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    tr = TermResult.query.filter_by(student_id=s0.id, subject_id=ctx['subject'].id).one()
    assert tr.total_score == Decimal('50.00')  # 100*.5 + 0*.5
    assert any('Missing Exam' in w for w in out['warnings'])


# --- Class position (competition ranking 1,2,2,4) ---------------------------
def test_class_position_with_tie(app, db):
    ctx = build_school(db, show_position=True)
    s0, s1, s2 = ctx['students']
    # totals: s0=90, s1=90 (tie), s2=50
    for s, val in [(s0, 90), (s1, 90), (s2, 50)]:
        _set(db, ctx, s, ctx['comps'][0], val)
        _set(db, ctx, s, ctx['comps'][1], val)
    db.session.commit()
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    pos = {tr.student_id: tr.class_position
           for tr in TermResult.query.filter_by(subject_id=ctx['subject'].id).all()}
    assert pos[s0.id] == 1 and pos[s1.id] == 1   # tie at rank 1
    assert pos[s2.id] == 3                         # next is 3, not 2


def test_no_position_when_disabled(app, db):
    ctx = build_school(db, show_position=False)
    s0 = ctx['students'][0]
    _set(db, ctx, s0, ctx['comps'][0], 80); _set(db, ctx, s0, ctx['comps'][1], 80)
    db.session.commit()
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    tr = TermResult.query.filter_by(student_id=s0.id).first()
    assert tr.class_position is None


# --- Publish gating ---------------------------------------------------------
def test_publish_and_unpublish(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    _set(db, ctx, s0, ctx['comps'][0], 80); _set(db, ctx, s0, ctx['comps'][1], 80)
    db.session.commit()
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    n = re.publish_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    assert n >= 1
    assert TermResult.query.filter_by(is_published=True).count() >= 1
    re.unpublish_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    assert TermResult.query.filter_by(is_published=True).count() == 0


def test_recompute_skips_published(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    _set(db, ctx, s0, ctx['comps'][0], 80); _set(db, ctx, s0, ctx['comps'][1], 80)
    db.session.commit()
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    re.publish_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    published_total = TermResult.query.filter_by(student_id=s0.id).first().total_score
    # Change the score and recompute — published row must NOT change.
    AssessmentScore.query.filter_by(student_id=s0.id,
        assessment_component_id=ctx['comps'][0].id).one().score = Decimal('10')
    db.session.commit()
    re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
    db.session.commit()
    assert TermResult.query.filter_by(student_id=s0.id).first().total_score == published_total


def test_publish_nothing_raises(app, db):
    ctx = build_school(db)
    db.session.commit()
    with pytest.raises(ResultsError, match='compute results first'):
        re.publish_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)


# --- Score entry (upsert) ---------------------------------------------------
def test_save_scores_upsert(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    entries = [{'student_id': s0.id, 'component_id': ctx['comps'][0].id, 'score': 70}]
    re.save_scores(ctx['school'].id, ctx['klass'].id, ctx['subject'].id,
                   ctx['term'].id, entries)
    db.session.commit()
    # update same cell
    entries[0]['score'] = 90
    re.save_scores(ctx['school'].id, ctx['klass'].id, ctx['subject'].id,
                   ctx['term'].id, entries)
    db.session.commit()
    rows = AssessmentScore.query.filter_by(student_id=s0.id,
        assessment_component_id=ctx['comps'][0].id).all()
    assert len(rows) == 1 and rows[0].score == Decimal('90')


def test_save_scores_rejects_out_of_range(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    with pytest.raises(ResultsError, match='between 0 and 100'):
        re.save_scores(ctx['school'].id, ctx['klass'].id, ctx['subject'].id,
                       ctx['term'].id,
                       [{'student_id': s0.id, 'component_id': ctx['comps'][0].id,
                         'score': 150}])


def test_save_scores_blank_clears(app, db):
    ctx = build_school(db)
    s0 = ctx['students'][0]
    re.save_scores(ctx['school'].id, ctx['klass'].id, ctx['subject'].id, ctx['term'].id,
                   [{'student_id': s0.id, 'component_id': ctx['comps'][0].id, 'score': 70}])
    db.session.commit()
    re.save_scores(ctx['school'].id, ctx['klass'].id, ctx['subject'].id, ctx['term'].id,
                   [{'student_id': s0.id, 'component_id': ctx['comps'][0].id, 'score': ''}])
    db.session.commit()
    assert AssessmentScore.query.filter_by(student_id=s0.id).count() == 0


def test_save_scores_ignores_students_not_in_class(app, db):
    ctx = build_school(db)
    outsider = make_student(db, ctx['school'], admission_no='OUT', current_class_id=None)
    db.session.commit()
    saved = re.save_scores(ctx['school'].id, ctx['klass'].id, ctx['subject'].id,
                           ctx['term'].id,
                           [{'student_id': outsider.id,
                             'component_id': ctx['comps'][0].id, 'score': 50}])
    db.session.commit()
    assert saved == 0
    assert AssessmentScore.query.filter_by(student_id=outsider.id).count() == 0


# --- Grade mapping edge -----------------------------------------------------
def test_no_default_scheme_raises(app, db):
    ctx = build_school(db)
    GradingScheme.query.filter_by(school_id=ctx['school'].id).update({'is_default': False})
    db.session.commit()
    with pytest.raises(ResultsError, match='default grading scheme'):
        re.compute_term_results(ctx['school'].id, ctx['klass'].id, ctx['term'].id)
