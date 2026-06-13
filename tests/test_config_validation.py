"""Tests for the Step 2 config validation service."""
from datetime import date

import pytest

from services.config_validation import (
    ValidationError,
    validate_grade_boundaries, validate_scheme_boundaries,
    validate_component_weights, validate_term_dates,
    set_current_academic_year, set_current_term, set_default_grading_scheme,
)
from models.config_tables import (
    AcademicYear, Term, GradingScheme, GradeBoundary, AssessmentComponent,
)
from tests.factories import make_school


# --- Grade boundaries -------------------------------------------------------
def test_boundaries_valid_non_overlapping():
    bs = [
        {'min_score': 80, 'max_score': 100, 'grade_label': 'A'},
        {'min_score': 60, 'max_score': 79, 'grade_label': 'B'},
        {'min_score': 0, 'max_score': 59, 'grade_label': 'C'},
    ]
    assert validate_grade_boundaries(bs) is True


def test_boundaries_overlap_rejected():
    bs = [
        {'min_score': 70, 'max_score': 100, 'grade_label': 'A'},
        {'min_score': 60, 'max_score': 75, 'grade_label': 'B'},  # overlaps A
    ]
    with pytest.raises(ValidationError, match='overlap'):
        validate_grade_boundaries(bs)


def test_boundaries_min_gt_max_rejected():
    bs = [{'min_score': 90, 'max_score': 80, 'grade_label': 'A'}]
    with pytest.raises(ValidationError, match='greater than max'):
        validate_grade_boundaries(bs)


def test_boundaries_out_of_range_rejected():
    bs = [{'min_score': 0, 'max_score': 120, 'grade_label': 'A'}]
    with pytest.raises(ValidationError, match='within 0'):
        validate_grade_boundaries(bs)


def test_boundaries_adjacent_touching_rejected():
    # max of one equals min of next => overlap at the boundary value
    bs = [
        {'min_score': 50, 'max_score': 80, 'grade_label': 'B'},
        {'min_score': 80, 'max_score': 100, 'grade_label': 'A'},
    ]
    with pytest.raises(ValidationError, match='overlap'):
        validate_grade_boundaries(bs)


def test_validate_scheme_boundaries_from_db(app, db):
    school = make_school(db, slug='s')
    scheme = GradingScheme(school_id=school.id, name='X', is_default=True)
    db.session.add(scheme)
    db.session.flush()
    for lo, hi, lbl in [(0, 49, 'F'), (50, 100, 'P')]:
        db.session.add(GradeBoundary(school_id=school.id,
                                     grading_scheme_id=scheme.id,
                                     min_score=lo, max_score=hi,
                                     grade_label=lbl))
    db.session.commit()
    assert validate_scheme_boundaries(school.id, scheme.id) is True


# --- Component weights ------------------------------------------------------
def test_weights_sum_100_ok():
    comps = [
        {'weight_percent': 40, 'applies_to_level_group_id': None},
        {'weight_percent': 60, 'applies_to_level_group_id': None},
    ]
    assert validate_component_weights(1, None, extra_components=comps) is True


def test_weights_not_100_rejected():
    comps = [
        {'weight_percent': 40, 'applies_to_level_group_id': None},
        {'weight_percent': 50, 'applies_to_level_group_id': None},
    ]
    with pytest.raises(ValidationError, match='sum to 90'):
        validate_component_weights(1, None, extra_components=comps)


def test_weights_per_level_group_isolated():
    comps = [
        {'weight_percent': 100, 'applies_to_level_group_id': None},
        {'weight_percent': 30, 'applies_to_level_group_id': 5},  # bucket 5 = 30
    ]
    # 'all' bucket is fine (100)...
    assert validate_component_weights(1, None, extra_components=comps) is True
    # ...but bucket 5 is only 30
    with pytest.raises(ValidationError, match='sum to 30'):
        validate_component_weights(1, 5, extra_components=comps)


def test_weights_empty_bucket_passes():
    assert validate_component_weights(1, None, extra_components=[]) is True


def test_weights_from_db(app, db):
    school = make_school(db, slug='s')
    db.session.add_all([
        AssessmentComponent(school_id=school.id, name='Class', weight_percent=50),
        AssessmentComponent(school_id=school.id, name='Exam', weight_percent=50),
    ])
    db.session.commit()
    assert validate_component_weights(school.id, None) is True


# --- Term dates -------------------------------------------------------------
def _year(db, school, start, end):
    ay = AcademicYear(school_id=school.id, name='2025/2026',
                      start_date=start, end_date=end)
    db.session.add(ay)
    db.session.flush()
    return ay


def test_term_dates_within_year_ok(app, db):
    school = make_school(db, slug='s')
    ay = _year(db, school, date(2025, 9, 1), date(2026, 7, 31))
    assert validate_term_dates(ay, date(2025, 9, 10), date(2025, 12, 20)) is True


def test_term_start_before_year_rejected(app, db):
    school = make_school(db, slug='s')
    ay = _year(db, school, date(2025, 9, 1), date(2026, 7, 31))
    with pytest.raises(ValidationError, match='before the academic year'):
        validate_term_dates(ay, date(2025, 8, 1), date(2025, 12, 20))


def test_term_end_after_year_rejected(app, db):
    school = make_school(db, slug='s')
    ay = _year(db, school, date(2025, 9, 1), date(2026, 7, 31))
    with pytest.raises(ValidationError, match='after the academic year'):
        validate_term_dates(ay, date(2025, 9, 10), date(2026, 8, 15))


def test_term_start_after_end_rejected(app, db):
    school = make_school(db, slug='s')
    ay = _year(db, school, date(2025, 9, 1), date(2026, 7, 31))
    with pytest.raises(ValidationError, match='after its end'):
        validate_term_dates(ay, date(2025, 12, 20), date(2025, 9, 10))


# --- Single-current / single-default invariants -----------------------------
def test_set_current_year_clears_others(app, db):
    school = make_school(db, slug='s')
    y1 = AcademicYear(school_id=school.id, name='2024/2025', is_current=True)
    y2 = AcademicYear(school_id=school.id, name='2025/2026', is_current=False)
    db.session.add_all([y1, y2])
    db.session.flush()
    set_current_academic_year(school.id, y2.id)
    db.session.commit()
    assert y2.is_current is True
    assert y1.is_current is False
    assert AcademicYear.query.filter_by(school_id=school.id,
                                        is_current=True).count() == 1


def test_set_default_scheme_clears_others(app, db):
    school = make_school(db, slug='s')
    s1 = GradingScheme(school_id=school.id, name='A', is_default=True)
    s2 = GradingScheme(school_id=school.id, name='B', is_default=False)
    db.session.add_all([s1, s2])
    db.session.flush()
    set_default_grading_scheme(school.id, s2.id)
    db.session.commit()
    assert GradingScheme.query.filter_by(school_id=school.id,
                                         is_default=True).count() == 1
    assert s2.is_default is True
