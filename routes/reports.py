"""
Reports and PDF Generation Routes
"""
from flask import Blueprint, render_template, make_response, g, flash, redirect, url_for
from flask_login import login_required, current_user

from models import db, Student, TerminalReport, FeeInvoice, UserRole, School
from app import teacher_required

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.route('/')
@teacher_required
def index():
    """Reports dashboard."""
    return render_template('reports/index.html')


@reports_bp.route('/terminal/<int:student_id>/<int:term_id>')
@login_required
def terminal_report(student_id, term_id):
    """Generate terminal report PDF."""
    student = Student.query.get_or_404(student_id)
    
    # Access Control
    if current_user.role == UserRole.PARENT:
        if not current_user.parent_profile or student.parent_id != current_user.parent_profile.id:
            flash('Access denied.', 'error')
            return redirect(url_for('parent.dashboard'))
    elif student.school_id != current_user.school_id:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
        
    report = TerminalReport.query.filter_by(
        student_id=student_id,
        term_id=term_id
    ).first_or_404()
    
    # Ensure report is published for parents
    if current_user.role == UserRole.PARENT and not report.is_published:
        flash('Report not yet published.', 'warning')
        return redirect(url_for('parent.dashboard'))
    
    # For now, return HTML view (PDF generation to be added)
    school = School.query.get(student.school_id)
    
    # Get assessments for this student/term
    from models import Assessment, ClassSubject, ClassEnrollment
    from datetime import datetime
    
    enrollment = report.class_enrollment
    class_name = enrollment.class_.name if enrollment else '-'
    level = enrollment.class_.level if enrollment else 'PRIMARY'
    
    assessments = Assessment.query.join(ClassSubject).filter(
        Assessment.student_id == student.id,
        Assessment.term_id == term_id,
        ClassSubject.class_id == enrollment.class_id
    ).all() if enrollment else []
    
    # Calculate totals
    total_score = report.total_marks or 0
    average_score = round(report.average_score or 0, 1)
    
    # Attendance data
    attendance = {
        'present': report.days_present or 0,
        'absent': report.days_absent or 0,
        'total': report.total_days or 0
    }
    
    # Term and academic year info
    term_obj = report.term
    term_name = term_obj.name if term_obj else '-'
    academic_year_name = term_obj.academic_year.name if term_obj and term_obj.academic_year else '-'
    
    return render_template('reports/terminal_report.html', 
        report=report, 
        student=student, 
        school=school,
        class_name=class_name,
        academic_year=academic_year_name,
        term=term_name,
        position=report.class_position or '-',
        class_size=report.class_size or '-',
        assessments=assessments,
        total_score=total_score,
        average_score=average_score,
        attendance=attendance,
        level=level,
        teacher_remark=report.class_teacher_remarks,
        head_remark=report.headteacher_remarks,
        generated_date=datetime.now().strftime('%B %d, %Y'),
        next_term_date=report.next_term_begins.strftime('%B %d, %Y') if report.next_term_begins else None
    )


@reports_bp.route('/invoice/<int:invoice_id>')
@login_required
def invoice_pdf(invoice_id):
    """Generate invoice PDF."""
    invoice = FeeInvoice.query.get_or_404(invoice_id)
    
    # Access Control
    if current_user.role == UserRole.PARENT:
        if not current_user.parent_profile or invoice.student.parent_id != current_user.parent_profile.id:
            flash('Access denied.', 'error')
            return redirect(url_for('parent.dashboard'))
    elif invoice.student.school_id != current_user.school_id:
        flash('Access denied.', 'error')
        return redirect(url_for('dashboard.index'))
        
    return render_template('reports/invoice.html', invoice=invoice)
