"""
Dashboard Routes - Role-based dashboards
"""
from flask import Blueprint, render_template, g, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import date

from models import (
    db, User, UserRole, Student, Staff, Class, FeeInvoice, Payment,
    Attendance, StudentStatus, PaymentStatus, AttendanceStatus, Expense
)
from services.payment_service import PaymentService
from services.predictive_engine import PredictiveEngine
from models import SchoolInsight

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


@dashboard_bp.route('/')
@login_required
def index():
    """Main dashboard - routes to role-specific dashboard."""
    role = current_user.role
    
    if role == UserRole.PARENT:
        return redirect(url_for('parent.dashboard'))
    elif role == UserRole.SUPER_ADMIN:
        return redirect(url_for('saas_admin.dashboard'))
    elif role == UserRole.HEADTEACHER:
        return headteacher_dashboard()
    elif role == UserRole.ADMIN:
        return admin_dashboard()
    elif role == UserRole.TEACHER:
        return teacher_dashboard()
    elif role == UserRole.ACCOUNTS_OFFICER:
        return accounts_dashboard()
    else:
        return render_template('dashboard/default.html')



def headteacher_dashboard():
    """Dashboard for Headteacher and Super Admin."""
    school_id = current_user.school_id
    
    # Statistics
    stats = {
        'total_students': Student.query.filter_by(
            school_id=school_id, 
            status=StudentStatus.ACTIVE
        ).count(),
        'total_staff': Staff.query.filter_by(
            school_id=school_id, 
            is_active=True
        ).count(),
        'staff_present': Staff.query.filter_by(
            school_id=school_id, 
            is_active=True
        ).count(),  # TODO: Implement staff attendance
        'total_classes': Class.query.filter_by(
            school_id=school_id, 
            is_active=True
        ).count(),
        'pending_reports': 0,
    }
    
    # Use PaymentService for metrics
    metrics, _ = PaymentService.get_finance_analytics(school_id)
    if metrics:
        stats.update({
            'fees_expected': float(metrics['total_income'] + metrics['outstanding_fees']),
            'fees_collected': float(metrics['total_income']),
            'fees_outstanding': float(metrics['outstanding_fees']),
            'total_expenses': float(metrics['total_expenses']),
            'net_balance': float(metrics['net_balance']),
            'collection_rate': round((float(metrics['total_income']) / float(metrics['total_income'] + metrics['outstanding_fees']) * 100), 1) if (metrics['total_income'] + metrics['outstanding_fees']) > 0 else 0
        })
    else:
        stats.update({
            'fees_expected': 0, 'fees_collected': 0, 'fees_outstanding': 0,
            'total_expenses': 0, 'net_balance': 0, 'collection_rate': 0
        })
    
    # Today's attendance
    today = date.today()
    attendance_stats = db.session.query(
        func.count(Attendance.id).label('total'),
        func.sum(func.cast(Attendance.status == AttendanceStatus.PRESENT, db.Integer)).label('present'),
        func.sum(func.cast(Attendance.status == AttendanceStatus.ABSENT, db.Integer)).label('absent'),
    ).filter(
        Attendance.school_id == school_id,
        Attendance.date == today
    ).first()
    
    if attendance_stats and attendance_stats.total:
        stats['attendance_rate'] = round(
            (attendance_stats.present / attendance_stats.total) * 100, 1
        )
    else:
        stats['attendance_rate'] = 0
    
    # Weekly attendance (Mon–Fri of the current week)
    from datetime import timedelta
    monday = today - timedelta(days=today.weekday())
    weekly_attendance = []
    day_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    for i in range(5):
        day = monday + timedelta(days=i)
        row = db.session.query(
            func.count(Attendance.id).label('total'),
            func.sum(func.cast(Attendance.status == AttendanceStatus.PRESENT, db.Integer)).label('present'),
        ).filter(
            Attendance.school_id == school_id,
            Attendance.date == day
        ).first()
        rate = round((row.present / row.total) * 100, 1) if row and row.total else 0
        weekly_attendance.append({'label': day_labels[i], 'rate': rate})

    # Recent activities
    recent_payments = Payment.query.join(FeeInvoice).join(Student).filter(
        Student.school_id == school_id
    ).order_by(Payment.created_at.desc()).limit(5).all()

    # Gender distribution
    gender_stats = db.session.query(
        Student.gender,
        func.count(Student.id)
    ).filter(
        Student.school_id == school_id,
        Student.status == StudentStatus.ACTIVE
    ).group_by(Student.gender).all()

    return render_template(
        'dashboard/headteacher.html',
        stats=stats,
        recent_payments=recent_payments,
        gender_stats=dict(gender_stats),
        weekly_attendance=weekly_attendance
    )


@dashboard_bp.route('/saas/onboard', methods=['POST'])
@login_required
def onboard_school():
    """Redirect legacy URL to new saas_admin blueprint."""
    return redirect(url_for('saas_admin.onboard_school'), 307)


@dashboard_bp.route('/saas/audit-logs')
@login_required
def saas_audit_logs():
    return redirect(url_for('saas_admin.audit_logs'))


@dashboard_bp.route('/saas/ai-conversations')
@login_required
def saas_ai_conversations():
    return redirect(url_for('saas_admin.ai_conversations'))


@dashboard_bp.route('/saas/toggle-module/<int:school_id>/<string:module_field>', methods=['POST'])
@login_required
def toggle_module(school_id, module_field):
    return redirect(url_for('saas_admin.toggle_module', school_id=school_id, module_field=module_field), 307)


@dashboard_bp.route('/predictive')
@login_required
def predictive_dashboard():
    """Elite Tier Early Warning System Dashboard."""
    if current_user.role not in [UserRole.SUPER_ADMIN, UserRole.HEADTEACHER, UserRole.ADMIN]:
        flash('Unauthorized.', 'error')
        return redirect(url_for('dashboard.index'))
        
    school_id = current_user.school_id
    # Run a quick check (in real app, this would be a background task)
    PredictiveEngine.check_dropout_risk(school_id)
    
    insights = SchoolInsight.query.filter_by(school_id=school_id, is_active=True).order_by(SchoolInsight.created_at.desc()).limit(10).all()
    forecast = PredictiveEngine.get_financial_forecast(school_id)
    
    return render_template('admin/predictive.html', insights=insights, forecast=forecast)


def admin_dashboard():
    """Dashboard for Admin users."""
    school_id = current_user.school_id
    stats = {
        'total_students': Student.query.filter_by(school_id=school_id, status=StudentStatus.ACTIVE).count(),
        'total_staff': Staff.query.filter_by(school_id=school_id, is_active=True).count(),
        'pending_tasks': 0,
    }
    return render_template('dashboard/admin.html', stats=stats)


def teacher_dashboard():
    """Dashboard for Teachers."""
    from models import ClassSubject, Assessment, ClassEnrollment
    staff = current_user.staff_profile
    if staff:
        my_classes = Class.query.filter_by(class_teacher_id=staff.id, is_active=True).all()
        my_subjects = ClassSubject.query.filter_by(teacher_id=staff.id).all()
        student_count = 0
        for cls in my_classes:
            student_count += ClassEnrollment.query.filter_by(
                class_id=cls.id,
                academic_year_id=g.current_academic_year.id if g.current_academic_year else 0
            ).count()
    else:
        my_classes = my_subjects = []
        student_count = 0
    
    return render_template('dashboard/teacher.html', my_classes=my_classes, my_subjects=my_subjects, student_count=student_count)


def accounts_dashboard():
    """Dashboard for Accounts Officers."""
    school_id = current_user.school_id
    metrics, _ = PaymentService.get_finance_analytics(school_id)
    
    if metrics:
        stats = {
            'fees_expected': float(metrics['total_income'] + metrics['outstanding_fees']),
            'fees_collected': float(metrics['total_income']),
            'fees_outstanding': float(metrics['outstanding_fees']),
            'total_expenses': float(metrics['total_expenses']),
            'net_balance': float(metrics['net_balance']),
        }
    else:
        stats = {'fees_expected': 0, 'fees_collected': 0, 'fees_outstanding': 0, 'total_expenses': 0, 'net_balance': 0}

    # Today's payments
    today_payments = Payment.query.join(FeeInvoice).join(Student).filter(
        Student.school_id == school_id,
        func.date(Payment.payment_date) == date.today()
    ).all()
    stats['today_collected'] = sum(float(p.amount) for p in today_payments)

    # Students with outstanding fees
    debtors = []
    if g.current_term:
        debtors = FeeInvoice.query.filter(
            FeeInvoice.term_id == g.current_term.id,
            FeeInvoice.balance > 0
        ).order_by(FeeInvoice.balance.desc()).limit(10).all()

    return render_template('dashboard/accounts.html', stats=stats, debtors=debtors, today_payments=today_payments)
