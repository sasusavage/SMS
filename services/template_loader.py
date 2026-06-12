"""
Curriculum template loader.

Reads a seed template JSON and writes its structure into a school's tenant
config tables (level groups, levels, subjects, level-subjects, grading scheme +
boundaries, assessment components, report settings, and a default academic year
with its terms). This is the mechanism that makes templates DATA, not code:
the same loader applies Ghana GES, Cambridge, or anything else.

Used by the seed script now and by the onboarding wizard in Step 2.
"""
import json
import os
from datetime import date

from extensions import db
from models.config_tables import (
    LevelGroup, Level, Subject, LevelSubject, GradingScheme, GradeBoundary,
    AssessmentComponent, ReportSettings, AcademicYear, Term,
)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), '..', 'seeds', 'templates')

VALID_TEMPLATES = {'ghana_ges', 'cambridge', 'blank'}


def load_template_json(key):
    if key not in VALID_TEMPLATES:
        raise ValueError(f'Unknown template: {key!r}')
    path = os.path.join(TEMPLATES_DIR, f'{key}.json')
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def apply_template(school_id, template_key, academic_year_name=None,
                   flush=True):
    """
    Apply a template's structure to a school. Idempotency is NOT assumed —
    intended to run once on a freshly created school (onboarding / seed).

    Returns a dict summary of what was created.
    """
    data = load_template_json(template_key)
    summary = {'template': template_key}

    # --- Level groups + levels ---
    levels_by_name = {}
    for lg in data.get('level_groups', []):
        group = LevelGroup(school_id=school_id, name=lg['name'],
                           sequence=lg.get('sequence', 0))
        db.session.add(group)
        db.session.flush()  # need group.id for levels
        for seq, level_name in enumerate(lg.get('levels', []), start=1):
            lvl = Level(school_id=school_id, level_group_id=group.id,
                        name=level_name, sequence=seq)
            db.session.add(lvl)
            db.session.flush()
            levels_by_name[level_name] = lvl
    summary['levels'] = len(levels_by_name)

    # --- Subjects ---
    subjects = []
    for s in data.get('subjects', []):
        subj = Subject(school_id=school_id, name=s['name'], code=s.get('code'),
                       is_core=s.get('is_core', True))
        db.session.add(subj)
        subjects.append(subj)
    db.session.flush()
    summary['subjects'] = len(subjects)

    # --- Level-subjects: offer every subject at every level by default ---
    ls_count = 0
    for lvl in levels_by_name.values():
        for subj in subjects:
            db.session.add(LevelSubject(school_id=school_id, level_id=lvl.id,
                                        subject_id=subj.id))
            ls_count += 1
    summary['level_subjects'] = ls_count

    # --- Grading scheme + boundaries ---
    scheme_data = data.get('grading_scheme')
    if scheme_data:
        scheme = GradingScheme(school_id=school_id, name=scheme_data['name'],
                               is_default=scheme_data.get('is_default', True))
        db.session.add(scheme)
        db.session.flush()
        for b in scheme_data.get('boundaries', []):
            db.session.add(GradeBoundary(
                school_id=school_id, grading_scheme_id=scheme.id,
                min_score=b['min_score'], max_score=b['max_score'],
                grade_label=b['grade_label'], remark=b.get('remark'),
                grade_point=b.get('grade_point'), is_pass=b.get('is_pass', True),
            ))
        summary['grading_scheme'] = scheme_data['name']

    # --- Assessment components ---
    comp_count = 0
    for c in data.get('assessment_components', []):
        db.session.add(AssessmentComponent(
            school_id=school_id, name=c['name'],
            weight_percent=c['weight_percent'],
            applies_to_level_group_id=None,  # resolved by name in Step 2 if needed
        ))
        comp_count += 1
    summary['components'] = comp_count

    # --- Report settings (one row per school) ---
    rs = data.get('report_settings', {})
    db.session.add(ReportSettings(
        school_id=school_id,
        show_class_position=rs.get('show_class_position', True),
        show_grade_point=rs.get('show_grade_point', False),
        show_skills_ratings=rs.get('show_skills_ratings', False),
        teacher_comment_required=rs.get('teacher_comment_required', True),
        head_comment_required=rs.get('head_comment_required', True),
        next_term_begins_label=rs.get('next_term_begins_label'),
    ))

    # --- Default academic year + terms ---
    year_name = academic_year_name or _default_year_name()
    ay = AcademicYear(school_id=school_id, name=year_name, is_current=True)
    db.session.add(ay)
    db.session.flush()
    for seq, term_name in enumerate(data.get('term_names', []), start=1):
        db.session.add(Term(
            school_id=school_id, academic_year_id=ay.id, name=term_name,
            sequence=seq, is_current=(seq == 1),
        ))
    summary['academic_year'] = year_name
    summary['terms'] = len(data.get('term_names', []))

    if flush:
        db.session.flush()
    return summary


def _default_year_name():
    today = date.today()
    # Academic year typically spans Sep–Aug; pick the span containing today.
    if today.month >= 9:
        return f'{today.year}/{today.year + 1}'
    return f'{today.year - 1}/{today.year}'
