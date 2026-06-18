"""
Analytics — aggregations for the school admin dashboard. Tenant-scoped.
Read-only; cheap COUNT/SUM queries over existing data.
"""
from decimal import Decimal

from extensions import db
from models.enums import StudentStatus, AttendanceStatus
from models.operational import Student, AttendanceRecord, TermResult, User
from models.config_tables import Class, Subject
from models.fees import Invoice, FeePayment

ZERO = Decimal('0')


def school_overview(school_id):
    """Headline counts for a school."""
    return {
        'students': Student.query.filter_by(
            school_id=school_id, status=StudentStatus.active).count(),
        'students_total': Student.query.filter_by(school_id=school_id).count(),
        'classes': Class.query.filter_by(school_id=school_id).count(),
        'subjects': Subject.query.filter_by(school_id=school_id).count(),
        'teachers': User.query.filter_by(
            school_id=school_id, role='teacher').count(),
    }


def attendance_breakdown(school_id):
    """Counts of each attendance status across all records (overall health)."""
    out = {s.value: 0 for s in AttendanceStatus}
    total = 0
    for r in AttendanceRecord.query.filter_by(school_id=school_id).all():
        out[r.status.value] = out.get(r.status.value, 0) + 1
        total += 1
    present_like = out.get('present', 0) + out.get('late', 0)
    out['total'] = total
    out['present_rate'] = round(present_like / total * 100, 1) if total else None
    return out


def results_summary(school_id):
    """Pass rate across published results."""
    rows = TermResult.query.filter_by(
        school_id=school_id, is_published=True).all()
    total = len(rows)
    passed = sum(1 for r in rows if r.is_pass)
    return {
        'published': total,
        'passed': passed,
        'pass_rate': round(passed / total * 100, 1) if total else None,
    }


def fees_summary(school_id):
    """Total billed, collected, and outstanding across all invoices."""
    invoices = Invoice.query.filter_by(school_id=school_id).all()
    billed = sum((Decimal(str(i.total_amount)) for i in invoices), ZERO)
    collected = sum(
        (Decimal(str(p.amount)) for p in
         FeePayment.query.filter_by(school_id=school_id).all()), ZERO)
    outstanding = billed - collected
    return {
        'invoices': len(invoices),
        'billed': billed,
        'collected': collected,
        'outstanding': outstanding if outstanding > ZERO else ZERO,
    }


def school_dashboard(school_id):
    return {
        'overview': school_overview(school_id),
        'attendance': attendance_breakdown(school_id),
        'results': results_summary(school_id),
        'fees': fees_summary(school_id),
    }
