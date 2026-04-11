"""
NaCCA Terminal Report Services
Handles generation of PDF reports with subject positioning and performance trends.
"""
from flask import render_template
import os
from models import db, Student, Term, School, Attendance, AttendanceStatus
from sqlalchemy import text
from decimal import Decimal
from datetime import datetime

# Choose best available PDF engine
PDF_ENGINE = None
try:
    from weasyprint import HTML
    test_html = HTML(string="<p></p>") # Test if libraries are actually loadable
    PDF_ENGINE = 'weasyprint'
except (ImportError, OSError):
    try:
        from xhtml2pdf import pisa
        PDF_ENGINE = 'xhtml2pdf'
    except (ImportError, Exception):
        PDF_ENGINE = None

class ReportService:
    
    @staticmethod
    def get_student_performance(student_id, term_id):
        """Fetches detailed performance data from PostgreSQL views."""
        # 1. Terminal Summary (Class Position, average)
        sql_summary = text("SELECT * FROM v_student_terminal_reports WHERE student_id = :sid AND term_id = :tid")
        summary = db.session.execute(sql_summary, {"sid": student_id, "tid": term_id}).fetchone()
        
        # 2. Subject Breakdown
        sql_subjects = text("SELECT * FROM v_student_subject_performance WHERE student_id = :sid AND term_id = :tid")
        subjects = db.session.execute(sql_subjects, {"sid": student_id, "tid": term_id}).fetchall()
        
        return summary, subjects

    @staticmethod
    def get_performance_trend(student_id, current_term_id):
        """Retrieves average scores over the last 3 terms for trending."""
        sql_trend = text("""
            SELECT t.name, r.average_score 
            FROM v_student_terminal_reports r
            JOIN terms t ON r.term_id = t.id
            WHERE r.student_id = :sid
            ORDER BY t.start_date DESC
            LIMIT 3
        """)
        results = db.session.execute(sql_trend, {"sid": student_id}).fetchall()
        # Return in forward chronological order for the chart
        return sorted(results, key=lambda x: x[0])

    @staticmethod
    def generate_terminal_pdf(student_id, term_id):
        """Generates a NaCCA-compliant PDF report."""
        student = Student.query.get(student_id)
        term = Term.query.get(term_id)
        school = School.query.get(student.school_id)
        
        summary, subjects = ReportService.get_student_performance(student_id, term_id)
        trend = ReportService.get_performance_trend(student_id, term_id)
        
        # Attendance stats — scoped to the term's date range
        total_days = (
            Attendance.query
            .filter_by(school_id=school.id, student_id=student_id)
            .filter(Attendance.date >= term.start_date, Attendance.date <= term.end_date)
            .count()
        )
        present_days = (
            Attendance.query
            .filter_by(school_id=school.id, student_id=student_id,
                       status=AttendanceStatus.PRESENT)
            .filter(Attendance.date >= term.start_date, Attendance.date <= term.end_date)
            .count()
        )
        
        html_content = render_template(
            'reports/terminal_report.html',
            student=student,
            term=term,
            school=school,
            summary=summary,
            subjects=subjects,
            trend=trend,
            attendance={'total': total_days, 'present': present_days},
            now=datetime.now()
        )
        
        # Generate PDF
        output_path = f"/tmp/report_{student_id}_{term_id}.pdf"
        if PDF_ENGINE == 'weasyprint':
            HTML(string=html_content).write_pdf(output_path)
        elif PDF_ENGINE == 'xhtml2pdf':
            with open(output_path, "wb") as f:
                pisa.CreatePDF(html_content, dest=f)
        else:
            raise Exception("No PDF engine found. Please install WeasyPrint or xhtml2pdf.")

        return output_path


# =============================================================================
# WEEKLY VITALS — Friday 4 PM scheduled briefing
# =============================================================================

def send_weekly_vitals():
    """
    Called by APScheduler every Friday 16:00.
    Builds a plain-text summary for each active school and sends it
    to the headteacher's phone via WhatsApp / SMS.
    """
    from datetime import date, timedelta
    from models import School, User, UserRole, Payment, FeeInvoice, Student
    from sqlalchemy import func

    schools = School.query.filter_by(is_account_suspended=False).all()

    for school in schools:
        try:
            _send_vitals_for_school(school)
        except Exception as exc:
            # Never let one bad school kill the whole job
            print(f"[WeeklyVitals] Error for school {school.id}: {exc}")


def _send_vitals_for_school(school):
    from datetime import date, timedelta
    from models import (
        User, UserRole, Payment, FeeInvoice, Student,
        Attendance, AttendanceStatus, Term, AcademicYear,
        ClassSubject, Assessment
    )
    from sqlalchemy import func

    today  = date.today()
    monday = today - timedelta(days=today.weekday())   # Mon of current week

    # ── Headteacher phone ────────────────────────────────────────────────────
    ht_user = User.query.filter_by(
        school_id=school.id,
        role=UserRole.HEADTEACHER,
        is_active=True
    ).first()
    if not ht_user:
        return

    from models import Staff
    staff = Staff.query.filter_by(id=ht_user.staff_id).first() if ht_user.staff_id else None
    ht_phone = staff.phone if staff else None
    if not ht_phone:
        return

    # ── Fees collected this week ─────────────────────────────────────────────
    week_fees = db.session.query(func.coalesce(func.sum(Payment.amount), 0)).join(
        FeeInvoice, Payment.invoice_id == FeeInvoice.id
    ).filter(
        FeeInvoice.school_id == school.id,
        func.date(Payment.payment_date) >= monday,
        func.date(Payment.payment_date) <= today
    ).scalar()

    # ── Zero-attendance students (absent every day this week so far) ─────────
    active_students = Student.query.filter_by(
        school_id=school.id, status='active'
    ).count()

    zero_attendance = db.session.query(func.count(Student.id)).filter(
        Student.school_id == school.id,
        ~Student.id.in_(
            db.session.query(Attendance.student_id).filter(
                Attendance.school_id == school.id,
                Attendance.date >= monday,
                Attendance.date <= today,
                Attendance.status == AttendanceStatus.PRESENT
            )
        )
    ).scalar()

    # ── Teachers who haven't uploaded marks this term ────────────────────────
    current_year = AcademicYear.query.filter_by(
        school_id=school.id, is_current=True
    ).first()
    current_term = Term.query.filter_by(
        academic_year_id=current_year.id, is_current=True
    ).first() if current_year else None

    missing_marks = 0
    if current_term:
        from models import ClassSubject
        all_class_subjects = ClassSubject.query.filter_by(
            academic_year_id=current_year.id
        ).join(
            __import__('models').Class,
            ClassSubject.class_id == __import__('models').Class.id
        ).filter_by(school_id=school.id).count()

        subjects_with_marks = db.session.query(
            func.count(func.distinct(Assessment.class_subject_id))
        ).filter(
            Assessment.school_id == school.id,
            Assessment.term_id == current_term.id
        ).scalar()

        missing_marks = max(0, all_class_subjects - (subjects_with_marks or 0))

    # ── Build message ────────────────────────────────────────────────────────
    message = (
        f"📊 *Weekly Vitals — {school.name}*\n"
        f"Week: {monday.strftime('%d %b')} – {today.strftime('%d %b %Y')}\n\n"
        f"💰 Fees collected this week: GH₵ {float(week_fees):,.2f}\n"
        f"🏫 Active students: {active_students}\n"
        f"⚠️  Zero attendance this week: {zero_attendance}\n"
        f"📝 Class subjects missing marks: {missing_marks}\n\n"
        f"_Powered by SmartSchool AI_"
    )

    # ── Send via NotificationService ─────────────────────────────────────────
    from services.notification_service import NotificationService
    NotificationService.send_sms(school_id=school.id, phone=ht_phone, message=message)
