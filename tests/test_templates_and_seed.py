"""Template loader correctness + seed-data validation rules."""
import json
import os

import pytest

from services import template_loader
from services.template_loader import apply_template, VALID_TEMPLATES
from models.config_tables import (
    LevelGroup, Level, Subject, GradingScheme, GradeBoundary,
    AssessmentComponent, ReportSettings, AcademicYear, Term,
)
from tests.factories import make_school


TEMPLATE_KEYS = ['ghana_ges', 'cambridge', 'blank']


@pytest.mark.parametrize('key', TEMPLATE_KEYS)
def test_template_json_parses(key):
    data = template_loader.load_template_json(key)
    assert data['key'] == key


@pytest.mark.parametrize('key', ['ghana_ges', 'cambridge'])
def test_assessment_weights_sum_to_100(key):
    data = template_loader.load_template_json(key)
    total = sum(c['weight_percent'] for c in data['assessment_components'])
    assert total == 100, f'{key} weights sum to {total}, not 100'


@pytest.mark.parametrize('key', ['ghana_ges', 'cambridge'])
def test_grade_boundaries_non_overlapping(key):
    data = template_loader.load_template_json(key)
    bs = sorted(data['grading_scheme']['boundaries'],
                key=lambda b: b['min_score'])
    for i in range(len(bs) - 1):
        assert bs[i]['max_score'] < bs[i + 1]['min_score'], \
            f'{key} boundaries overlap at {bs[i]}'


@pytest.mark.parametrize('key', ['ghana_ges', 'cambridge'])
def test_grade_boundaries_cover_zero_to_100(key):
    data = template_loader.load_template_json(key)
    bs = data['grading_scheme']['boundaries']
    assert min(b['min_score'] for b in bs) == 0
    assert max(b['max_score'] for b in bs) == 100


def test_apply_ghana_template_populates_config(app, db):
    school = make_school(db, slug='ges')
    summary = apply_template(school.id, 'ghana_ges')
    db.session.commit()

    assert LevelGroup.query.filter_by(school_id=school.id).count() == 4
    assert Subject.query.filter_by(school_id=school.id).count() == 9
    assert GradingScheme.query.filter_by(school_id=school.id).count() == 1
    assert GradeBoundary.query.filter_by(school_id=school.id).count() == 9
    assert AssessmentComponent.query.filter_by(school_id=school.id).count() == 2
    assert ReportSettings.query.filter_by(school_id=school.id).count() == 1
    ay = AcademicYear.query.filter_by(school_id=school.id).one()
    assert ay.is_current is True
    assert Term.query.filter_by(school_id=school.id).count() == 3


def test_apply_template_is_tenant_scoped(app, db):
    """Applying a template to school A must not create rows for school B."""
    a = make_school(db, slug='a')
    b = make_school(db, slug='b')
    apply_template(a.id, 'ghana_ges')
    db.session.commit()
    assert Subject.query.filter_by(school_id=b.id).count() == 0
    assert Subject.query.filter_by(school_id=a.id).count() == 9


def test_blank_template_creates_minimal(app, db):
    school = make_school(db, slug='blank')
    apply_template(school.id, 'blank')
    db.session.commit()
    assert LevelGroup.query.filter_by(school_id=school.id).count() == 0
    assert Subject.query.filter_by(school_id=school.id).count() == 0
    # still gets report settings + academic year + terms
    assert ReportSettings.query.filter_by(school_id=school.id).count() == 1
    assert Term.query.filter_by(school_id=school.id).count() == 3


def test_unknown_template_rejected():
    with pytest.raises(ValueError):
        template_loader.load_template_json('does_not_exist')


def test_only_three_templates_exist():
    assert VALID_TEMPLATES == {'ghana_ges', 'cambridge', 'blank'}
