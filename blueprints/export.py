"""
/admin/export — school_admin data exports (CSV). Tenant-scoped: only ever the
current school's data. Streams in-memory CSV (no temp files).
"""
import csv
import io

from flask import Blueprint, Response, g, abort
from flask_login import login_required

from auth.security import require_role
from services.tenant import tenant_query
from services.audit import log_action
from extensions import db
from models.operational import Student
from models.fees import Invoice, FeePayment
from models.operational import TermResult
from models.config_tables import Subject, Term, Class

export_bp = Blueprint('export', __name__, url_prefix='/admin/export')


@export_bp.before_request
@login_required
@require_role('school_admin')
def _guard():
    if g.get('current_school_id') is None:
        abort(403)


def _csv_response(filename, header, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    log_action('export', entity=filename)
    db.session.commit()
    return Response(buf.getvalue(), mimetype='text/csv', headers={
        'Content-Disposition': f'attachment; filename="{filename}"'})


@export_bp.route('/students.csv')
def students():
    classes = {c.id: c.name for c in tenant_query(Class).all()}
    rows = []
    for s in (tenant_query(Student)
              .order_by(Student.last_name, Student.first_name).all()):
        rows.append([
            s.admission_no, s.first_name, s.last_name, s.other_names or '',
            s.gender or '', s.dob.isoformat() if s.dob else '',
            classes.get(s.current_class_id, ''), s.status.value,
            s.guardian_name or '', s.guardian_phone or '',
        ])
    return _csv_response(
        'students.csv',
        ['admission_no', 'first_name', 'last_name', 'other_names', 'gender',
         'dob', 'class', 'status', 'guardian_name', 'guardian_phone'],
        rows)


@export_bp.route('/fees.csv')
def fees():
    students = {s.id: s for s in tenant_query(Student).all()}
    terms = {t.id: t.name for t in tenant_query(Term).all()}
    rows = []
    for inv in tenant_query(Invoice).order_by(Invoice.id).all():
        paid = sum(float(p.amount) for p in
                   FeePayment.query.filter_by(school_id=g.current_school_id,
                                              invoice_id=inv.id).all())
        st = students.get(inv.student_id)
        rows.append([
            inv.id, (st.admission_no if st else ''),
            (f'{st.last_name}, {st.first_name}' if st else ''),
            terms.get(inv.term_id, ''), float(inv.total_amount), paid,
            float(inv.total_amount) - paid, inv.status,
        ])
    return _csv_response(
        'fees.csv',
        ['invoice_id', 'admission_no', 'student', 'term', 'total', 'paid',
         'balance', 'status'],
        rows)


@export_bp.route('/results.csv')
def results():
    students = {s.id: s for s in tenant_query(Student).all()}
    subjects = {s.id: s.name for s in tenant_query(Subject).all()}
    terms = {t.id: t.name for t in tenant_query(Term).all()}
    rows = []
    for r in tenant_query(TermResult).order_by(TermResult.id).all():
        st = students.get(r.student_id)
        rows.append([
            (st.admission_no if st else ''),
            (f'{st.last_name}, {st.first_name}' if st else ''),
            subjects.get(r.subject_id, ''), terms.get(r.term_id, ''),
            float(r.total_score) if r.total_score is not None else '',
            r.grade_label or '', r.remark or '',
            r.class_position if r.class_position is not None else '',
            'yes' if r.is_published else 'no',
        ])
    return _csv_response(
        'results.csv',
        ['admission_no', 'student', 'subject', 'term', 'total', 'grade',
         'remark', 'position', 'published'],
        rows)
