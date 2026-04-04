"""
Parent Portal Routes - Read-only access for parents
"""
from flask import Blueprint, render_template, g, flash, redirect, url_for
from flask_login import login_required, current_user

from models import (
    db, UserRole, Student, Parent, ClassEnrollment, Assessment, 
    TerminalReport, FeeInvoice, Attendance, Term
)
from app import parent_required

parent_bp = Blueprint('parent', __name__, url_prefix='/parent')


@parent_bp.route('/')
@parent_required
def dashboard():
    """Parent dashboard - overview of children."""
    parent = current_user.parent_profile
    if not parent:
        flash('Parent profile not found.', 'error')
        return redirect(url_for('auth.logout'))
    
    children = Student.query.filter_by(parent_id=parent.id).all()
    
    children_data = []
    from models import TerminalReportView, Notification
    
    recent_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        school_id=current_user.school_id
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    for child in children:
        data = {
            'student': child, 
            'enrollment': None, 
            'balance': 0,
            'trend': [], # Termly averages
            'last_invoice_uuid': None
        }
        
        # 1. Performance Trend
        history = TerminalReportView.query.filter_by(
            student_id=child.id,
            school_id=current_user.school_id
        ).order_by(TerminalReportView.academic_year_id.asc(), TerminalReportView.term_id.asc()).all()
        data['trend'] = [{'term': h.term_id, 'avg': float(h.average_score)} for h in history]
        
        if g.current_academic_year:
            data['enrollment'] = ClassEnrollment.query.filter_by(
                student_id=child.id,
                academic_year_id=g.current_academic_year.id
            ).first()
        
        if g.current_term:
            invoice = FeeInvoice.query.filter_by(
                student_id=child.id,
                term_id=g.current_term.id
            ).first()
            if invoice:
                data['balance'] = float(invoice.balance)
                data['last_invoice_uuid'] = invoice.uuid
        
        children_data.append(data)
    
    return render_template('parent/dashboard.html', 
        children=children_data, 
        notifications=recent_notifications
    )


@parent_bp.route('/child/<int:id>')
@parent_required
def child_profile(id):
    """View child's profile."""
    student = Student.query.get_or_404(id)
    
    # Verify parent access
    parent = current_user.parent_profile
    if not parent or student.parent_id != parent.id:
        flash('Access denied.', 'error')
        return redirect(url_for('parent.dashboard'))
    
    enrollment = None
    if g.current_academic_year:
        enrollment = ClassEnrollment.query.filter_by(
            student_id=student.id,
            academic_year_id=g.current_academic_year.id
        ).first()
    
    # Get recent assessments for current term
    recent_assessments = []
    latest_invoice = None
    if g.current_term:
        recent_assessments = Assessment.query.filter_by(
            student_id=student.id,
            term_id=g.current_term.id
        ).all()
        
        latest_invoice = FeeInvoice.query.filter_by(
            student_id=student.id,
            term_id=g.current_term.id
        ).first()
    
    return render_template('parent/child_profile.html', 
        student=student, 
        enrollment=enrollment,
        recent_assessments=recent_assessments,
        latest_invoice=latest_invoice
    )


@parent_bp.route('/child/<int:id>/results')
@parent_required
def child_results(id):
    """View child's results."""
    student = Student.query.get_or_404(id)
    
    parent = current_user.parent_profile
    if not parent or student.parent_id != parent.id:
        flash('Access denied.', 'error')
        return redirect(url_for('parent.dashboard'))
    
    # Get published terminal reports
    reports = TerminalReport.query.filter_by(
        student_id=student.id,
        is_published=True
    ).join(Term).order_by(Term.start_date.desc()).all()
    
    return render_template('parent/child_results.html', student=student, reports=reports)


@parent_bp.route('/child/<int:id>/fees')
@parent_required
def child_fees(id):
    """View child's fee status."""
    student = Student.query.get_or_404(id)
    
    parent = current_user.parent_profile
    if not parent or student.parent_id != parent.id:
        flash('Access denied.', 'error')
        return redirect(url_for('parent.dashboard'))
    
    invoices = FeeInvoice.query.filter_by(student_id=student.id).order_by(FeeInvoice.created_at.desc()).all()
    
    return render_template('parent/child_fees.html', student=student, invoices=invoices)


@parent_bp.route('/child/<int:id>/attendance')  
@parent_required
def child_attendance(id):
    """View child's attendance."""
    student = Student.query.get_or_404(id)
    
    parent = current_user.parent_profile
    if not parent or student.parent_id != parent.id:
        flash('Access denied.', 'error')
        return redirect(url_for('parent.dashboard'))
    
    records = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.date.desc()).limit(30).all()
    
    return render_template('parent/child_attendance.html', student=student, records=records)

@parent_bp.route('/notifications')
@parent_required
def notifications():
    """View all notifications for the parent."""
    from models import Notification
    notifs = Notification.query.filter_by(
        user_id=current_user.id,
        school_id=current_user.school_id
    ).order_by(Notification.created_at.desc()).all()
    
    # Mark all as read
    from models import db
    for n in notifs:
        n.is_read = True
    db.session.commit()
    
    return render_template('parent/notifications.html', notifications=notifs)
