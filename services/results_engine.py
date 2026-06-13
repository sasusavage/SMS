"""
Results engine + score entry (Step 5) — the heart of the configurability.

Nothing curriculum-specific is hardcoded: components, weights, grade bands and
report options all come from the school's config tables. Every function is
tenant-scoped via an explicit school_id.

Pipeline (compute_term_results), per spec §4:
  1. Load assessment_components for the school (level_group override wins).
  2. Validate weights sum to 100 — abort with a clear error if not.
  3. For each student in the class, each subject offered at the class's level:
     weighted_total = Σ (component_score × weight / 100); missing score => 0
     but flagged in warnings.
  4. Map weighted_total -> grade via the school's default grading_scheme.
  5. If report_settings.show_class_position: rank per subject and overall
     (average of totals) with standard competition ranking (1,2,2,4).
  6. Upsert into term_results with a snapshot of grade_label/remark/is_pass.
  7. Return a summary {computed, warnings, errors}.

Publishing: results are computed, reviewed, then published. Students/parents
only ever see published results. Re-compute is allowed until published; after
publishing, an admin must explicitly unpublish (audited by the caller).
"""
from decimal import Decimal

from extensions import db
from models.enums import AttendanceStatus  # noqa: F401 (kept for parity)
from models.operational import Student, AssessmentScore, TermResult
from models.config_tables import (
    Class, Level, LevelSubject, Subject, AssessmentComponent, GradingScheme,
    GradeBoundary, ReportSettings, Term,
)

ZERO = Decimal('0')
HUNDRED = Decimal('100')


class ResultsError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------
def _get_class(school_id, class_id):
    c = Class.query.filter_by(school_id=school_id, id=class_id).first()
    if c is None:
        raise ResultsError('Class not found.')
    return c


def _get_term(school_id, term_id):
    t = Term.query.filter_by(school_id=school_id, id=term_id).first()
    if t is None:
        raise ResultsError('Term not found.')
    return t


def _class_level_group_id(school_id, klass):
    level = Level.query.filter_by(school_id=school_id, id=klass.level_id).first()
    return level.level_group_id if level else None


def components_for(school_id, level_group_id):
    """
    Components that apply to a level group: those scoped to it, else the
    'all levels' bucket (applies_to_level_group_id is NULL). A level-group
    override fully replaces the global set.
    """
    scoped = AssessmentComponent.query.filter_by(
        school_id=school_id, applies_to_level_group_id=level_group_id).all()
    if scoped:
        return scoped
    return AssessmentComponent.query.filter_by(
        school_id=school_id, applies_to_level_group_id=None).all()


def validate_weights(components):
    total = sum((Decimal(str(c.weight_percent or 0)) for c in components), ZERO)
    if not components:
        raise ResultsError('No assessment components are configured.')
    if total != HUNDRED:
        raise ResultsError(
            f'Assessment weights sum to {total}, not 100. Fix them under '
            f'Configuration → Assessment components before computing results.')
    return True


def default_scheme(school_id):
    scheme = GradingScheme.query.filter_by(
        school_id=school_id, is_default=True).first()
    if scheme is None:
        raise ResultsError('No default grading scheme is set.')
    boundaries = GradeBoundary.query.filter_by(
        school_id=school_id, grading_scheme_id=scheme.id).all()
    if not boundaries:
        raise ResultsError('The default grading scheme has no grade bands.')
    return scheme, boundaries


def grade_for(score, boundaries):
    """Return (grade_label, remark, is_pass) for a score, or (None, None, None)."""
    s = Decimal(str(score))
    for b in boundaries:
        if Decimal(str(b.min_score)) <= s <= Decimal(str(b.max_score)):
            return b.grade_label, b.remark, b.is_pass
    return None, None, None


def subjects_for_class(school_id, klass):
    """Subjects offered at the class's level (via level_subjects)."""
    rows = (db.session.query(Subject)
            .join(LevelSubject, LevelSubject.subject_id == Subject.id)
            .filter(LevelSubject.school_id == school_id,
                    LevelSubject.level_id == klass.level_id)
            .order_by(Subject.name).all())
    return rows


# ---------------------------------------------------------------------------
# Score entry (assessment_scores upsert)
# ---------------------------------------------------------------------------
def get_score_grid(school_id, class_id, subject_id, term_id):
    """
    Existing scores for a class+subject+term as
    {student_id: {component_id: Decimal(score)}}.
    """
    rows = AssessmentScore.query.filter_by(
        school_id=school_id, class_id=class_id, subject_id=subject_id,
        term_id=term_id).all()
    grid = {}
    for r in rows:
        grid.setdefault(r.student_id, {})[r.assessment_component_id] = r.score
    return grid


def save_scores(school_id, class_id, subject_id, term_id, entries,
                entered_by=None):
    """
    Upsert raw component scores. `entries` is a list of dicts:
      {'student_id': int, 'component_id': int, 'score': number|None}
    Only students currently in the class and components valid for the class's
    level group are accepted (others ignored). Scores must be 0–100.
    Returns count saved.
    """
    klass = _get_class(school_id, class_id)
    _get_term(school_id, term_id)
    if Subject.query.filter_by(school_id=school_id, id=subject_id).first() is None:
        raise ResultsError('Subject not found.')

    roster_ids = {s.id for s in _roster(school_id, class_id)}
    lg_id = _class_level_group_id(school_id, klass)
    comp_ids = {c.id for c in components_for(school_id, lg_id)}

    existing = {
        (r.student_id, r.assessment_component_id): r
        for r in AssessmentScore.query.filter_by(
            school_id=school_id, class_id=class_id, subject_id=subject_id,
            term_id=term_id).all()
    }

    saved = 0
    for e in entries:
        try:
            sid_ = int(e['student_id'])
            cid_ = int(e['component_id'])
        except (KeyError, TypeError, ValueError):
            continue
        if sid_ not in roster_ids or cid_ not in comp_ids:
            continue
        raw = e.get('score')
        if raw in (None, ''):
            # Blank clears any existing score for this cell.
            rec = existing.get((sid_, cid_))
            if rec is not None:
                db.session.delete(rec)
                saved += 1
            continue
        try:
            score = Decimal(str(raw))
        except Exception:
            raise ResultsError(f'Invalid score: {raw!r}.')
        if score < ZERO or score > HUNDRED:
            raise ResultsError(f'Score {score} must be between 0 and 100.')

        rec = existing.get((sid_, cid_))
        if rec is None:
            rec = AssessmentScore(
                school_id=school_id, student_id=sid_, class_id=class_id,
                subject_id=subject_id, term_id=term_id,
                assessment_component_id=cid_, score=score, entered_by=entered_by)
            db.session.add(rec)
        else:
            rec.score = score
            rec.entered_by = entered_by
        saved += 1

    db.session.flush()
    return saved


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------
def _roster(school_id, class_id):
    return (Student.query
            .filter_by(school_id=school_id, current_class_id=class_id)
            .order_by(Student.last_name, Student.first_name).all())


def compute_term_results(school_id, class_id, term_id):
    """
    Compute (and upsert) term_results for a class+term. Refuses to recompute
    any subject that is already published (caller must unpublish first).
    Returns {'computed': int, 'warnings': [...], 'errors': [...]}.
    """
    klass = _get_class(school_id, class_id)
    _get_term(school_id, term_id)

    lg_id = _class_level_group_id(school_id, klass)
    components = components_for(school_id, lg_id)
    validate_weights(components)
    scheme, boundaries = default_scheme(school_id)

    students = _roster(school_id, class_id)
    subjects = subjects_for_class(school_id, klass)
    if not students:
        return {'computed': 0, 'warnings': [], 'errors': ['Class has no students.']}
    if not subjects:
        return {'computed': 0, 'warnings': [],
                'errors': ['No subjects are offered at this class\'s level.']}

    rs = ReportSettings.query.filter_by(school_id=school_id).first()
    show_position = bool(rs.show_class_position) if rs else False

    # Pre-load all scores for this class+term.
    score_rows = AssessmentScore.query.filter_by(
        school_id=school_id, class_id=class_id, term_id=term_id).all()
    scores = {}  # (student_id, subject_id, component_id) -> Decimal
    for r in score_rows:
        scores[(r.student_id, r.subject_id, r.assessment_component_id)] = \
            Decimal(str(r.score))

    # Block recompute of already-published rows.
    published = {
        (r.student_id, r.subject_id)
        for r in TermResult.query.filter_by(
            school_id=school_id, class_id=class_id, term_id=term_id,
            is_published=True).all()
    }

    warnings = []
    # totals[(student_id, subject_id)] = Decimal weighted total
    totals = {}
    computed = 0

    for student in students:
        for subject in subjects:
            if (student.id, subject.id) in published:
                continue  # don't touch published results
            total = ZERO
            for comp in components:
                key = (student.id, subject.id, comp.id)
                val = scores.get(key)
                if val is None:
                    warnings.append(
                        f'Missing {comp.name} for {student.first_name} '
                        f'{student.last_name} in {subject.name} (treated as 0).')
                    val = ZERO
                total += val * Decimal(str(comp.weight_percent)) / HUNDRED
            total = total.quantize(Decimal('0.01'))
            totals[(student.id, subject.id)] = total

    # Class position per subject (competition ranking 1,2,2,4).
    positions = {}
    if show_position:
        for subject in subjects:
            ranked = sorted(
                ((sid_sub, t) for (sid_sub, subj_id), t in totals.items()
                 if subj_id == subject.id),
                key=lambda kv: kv[1], reverse=True)
            _assign_positions(ranked, positions, subject.id)

    # Upsert term_results.
    existing = {
        (r.student_id, r.subject_id): r
        for r in TermResult.query.filter_by(
            school_id=school_id, class_id=class_id, term_id=term_id).all()
    }
    for (student_id, subject_id), total in totals.items():
        label, remark, is_pass = grade_for(total, boundaries)
        rec = existing.get((student_id, subject_id))
        pos = positions.get((subject_id, student_id)) if show_position else None
        if rec is None:
            rec = TermResult(
                school_id=school_id, student_id=student_id, class_id=class_id,
                subject_id=subject_id, term_id=term_id, total_score=total,
                grade_label=label, remark=remark, is_pass=is_pass,
                class_position=pos, is_published=False)
            db.session.add(rec)
        else:
            rec.total_score = total
            rec.grade_label = label
            rec.remark = remark
            rec.is_pass = is_pass
            rec.class_position = pos
        computed += 1

    db.session.flush()
    return {'computed': computed, 'warnings': warnings, 'errors': []}


def _assign_positions(ranked, positions, subject_id):
    """Standard competition ranking (1,2,2,4) into positions[(subject_id, sid)]."""
    last_total = None
    last_rank = 0
    for idx, (student_id, total) in enumerate(ranked, start=1):
        if total == last_total:
            rank = last_rank
        else:
            rank = idx
            last_rank = rank
            last_total = total
        positions[(subject_id, student_id)] = rank


# ---------------------------------------------------------------------------
# Publish / unpublish
# ---------------------------------------------------------------------------
def publish_results(school_id, class_id, term_id):
    rows = TermResult.query.filter_by(
        school_id=school_id, class_id=class_id, term_id=term_id).all()
    if not rows:
        raise ResultsError('Nothing to publish — compute results first.')
    n = 0
    for r in rows:
        if not r.is_published:
            r.is_published = True
            n += 1
    db.session.flush()
    return n


def unpublish_results(school_id, class_id, term_id):
    rows = TermResult.query.filter_by(
        school_id=school_id, class_id=class_id, term_id=term_id,
        is_published=True).all()
    n = 0
    for r in rows:
        r.is_published = False
        n += 1
    db.session.flush()
    return n


def results_overview(school_id, class_id, term_id):
    """Computed results for review (all rows, joined-friendly ordering)."""
    return (TermResult.query
            .filter_by(school_id=school_id, class_id=class_id, term_id=term_id)
            .all())
