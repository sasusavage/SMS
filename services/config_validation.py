"""
Config validation service (Step 2).

All curriculum-config invariants live here, NOT in routes (spec: service-layer
pattern). Routes call these and surface ValidationError.message to the user.

Rules enforced:
  1. Grade boundaries within a scheme must not overlap and must be well-formed.
  2. Assessment component weights must sum to 100 per level group
     (null applies_to_level_group_id = the "all levels" bucket).
  3. A term's dates must fall within its academic year's dates, and not invert.
  4. Invariants: at most one is_current academic year / term (per scope),
     at most one default grading scheme per school.

Every function is tenant-scoped: it operates on a single school_id and never
reads across schools.
"""
from decimal import Decimal

from extensions import db
from models.config_tables import (
    AcademicYear, Term, GradingScheme, GradeBoundary, AssessmentComponent,
)


class ValidationError(Exception):
    """Raised when a config invariant would be violated. .message is UI-safe."""
    def __init__(self, message):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# 1. Grade boundaries
# ---------------------------------------------------------------------------
def validate_grade_boundaries(boundaries):
    """
    `boundaries`: iterable of objects/dicts with min_score and max_score.

    Checks each band is well-formed (min <= max, within 0..100) and that no two
    bands overlap. Raises ValidationError on the first problem.
    """
    bands = []
    for b in boundaries:
        lo = _num(_get(b, 'min_score'))
        hi = _num(_get(b, 'max_score'))
        label = _get(b, 'grade_label', default='(unnamed)')
        if lo is None or hi is None:
            raise ValidationError(f'Grade "{label}" is missing a min or max score.')
        if lo > hi:
            raise ValidationError(
                f'Grade "{label}" has min ({lo}) greater than max ({hi}).')
        if lo < 0 or hi > 100:
            raise ValidationError(
                f'Grade "{label}" range {lo}–{hi} must be within 0–100.')
        bands.append((lo, hi, label))

    bands.sort(key=lambda t: t[0])
    for i in range(len(bands) - 1):
        _, hi, label = bands[i]
        next_lo, _, next_label = bands[i + 1]
        if next_lo <= hi:
            raise ValidationError(
                f'Grade ranges overlap: "{label}" (…–{hi}) and '
                f'"{next_label}" ({next_lo}–…).')
    return True


def validate_scheme_boundaries(school_id, grading_scheme_id):
    """Validate the persisted boundaries of a scheme (used after edits)."""
    rows = (GradeBoundary.query
            .filter_by(school_id=school_id, grading_scheme_id=grading_scheme_id)
            .all())
    return validate_grade_boundaries(rows)


# ---------------------------------------------------------------------------
# 2. Assessment component weights
# ---------------------------------------------------------------------------
def validate_component_weights(school_id, level_group_id=None,
                               extra_components=None):
    """
    The weights of all components in a given level-group bucket must sum to 100.

    `level_group_id=None` validates the "applies to all" bucket. Pass
    `extra_components` (list of dicts with weight_percent + applies_to_level_group_id)
    to validate a prospective set before committing.
    """
    if extra_components is not None:
        weights = [
            _num(c.get('weight_percent'))
            for c in extra_components
            if c.get('applies_to_level_group_id') == level_group_id
        ]
    else:
        rows = (AssessmentComponent.query
                .filter_by(school_id=school_id,
                           applies_to_level_group_id=level_group_id)
                .all())
        weights = [_num(r.weight_percent) for r in rows]

    if not weights:
        # No components for this bucket yet — nothing to validate against 100.
        return True
    total = sum(weights)
    if total != Decimal('100'):
        scope = 'all levels' if level_group_id is None else f'level group {level_group_id}'
        raise ValidationError(
            f'Assessment weights for {scope} sum to {total}, not 100.')
    return True


# ---------------------------------------------------------------------------
# 3. Term dates within academic year
# ---------------------------------------------------------------------------
def validate_term_dates(academic_year, start_date, end_date):
    """
    `academic_year`: an AcademicYear instance (has start_date/end_date).
    Term start must be <= end, and both must lie within the year's bounds
    (when the year defines bounds).
    """
    if start_date and end_date and start_date > end_date:
        raise ValidationError('Term start date is after its end date.')

    ay_start = academic_year.start_date
    ay_end = academic_year.end_date
    if ay_start and start_date and start_date < ay_start:
        raise ValidationError(
            f'Term starts ({start_date}) before the academic year '
            f'({ay_start}).')
    if ay_end and end_date and end_date > ay_end:
        raise ValidationError(
            f'Term ends ({end_date}) after the academic year ({ay_end}).')
    return True


# ---------------------------------------------------------------------------
# 4. Single-current / single-default invariants
# ---------------------------------------------------------------------------
def set_current_academic_year(school_id, academic_year_id):
    """Make one academic year current, clearing the flag on the others."""
    (AcademicYear.query
     .filter_by(school_id=school_id)
     .update({AcademicYear.is_current: False}))
    ay = AcademicYear.query.filter_by(
        school_id=school_id, id=academic_year_id).first()
    if ay is None:
        raise ValidationError('Academic year not found.')
    ay.is_current = True
    db.session.flush()
    return ay


def set_current_term(school_id, academic_year_id, term_id):
    """Make one term current within its academic year, clearing the others."""
    (Term.query
     .filter_by(school_id=school_id, academic_year_id=academic_year_id)
     .update({Term.is_current: False}))
    term = Term.query.filter_by(
        school_id=school_id, academic_year_id=academic_year_id,
        id=term_id).first()
    if term is None:
        raise ValidationError('Term not found.')
    term.is_current = True
    db.session.flush()
    return term


def set_default_grading_scheme(school_id, grading_scheme_id):
    """Make one grading scheme the default, clearing the flag on the others."""
    (GradingScheme.query
     .filter_by(school_id=school_id)
     .update({GradingScheme.is_default: False}))
    scheme = GradingScheme.query.filter_by(
        school_id=school_id, id=grading_scheme_id).first()
    if scheme is None:
        raise ValidationError('Grading scheme not found.')
    scheme.is_default = True
    db.session.flush()
    return scheme


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _num(value):
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
