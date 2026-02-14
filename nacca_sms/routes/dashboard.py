"""
Dashboard Routes - Role-based dashboards
"""
from flask import Blueprint, render_template, g
from flask_login import login_required, current_user
from sqlalchemy import func

from models import (
    db, User, UserRole, Student, Staff, Class, FeeInvoice, Payment,
    Attendance, StudentStatus, PaymentStatus, AttendanceStatus
)

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')


@dashboard_bp.route('/')
@login_required
def index():
    """Main dashboard - routes to role-specific dashboard."""
    role = current_user.role
    
    if role == UserRole.PARENT:
        return redirect(url_for('parent.dashboard'))
    elif role in [UserRole.SUPER_ADMIN, UserRole.HEADTEACHER]:
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
        'pending_reports': 0,  # TODO: Count unpublished reports
    }
    
    # Fee statistics for current term
    if g.current_term:
        fee_stats = db.session.query(
            func.coalesce(func.sum(FeeInvoice.total_amount), 0).label('total_expected'),
            func.coalesce(func.sum(FeeInvoice.amount_paid), 0).label('total_collected'),
            func.coalesce(func.sum(FeeInvoice.balance), 0).label('total_outstanding')
        ).filter(
            FeeInvoice.term_id == g.current_term.id
        ).first()
        
        stats['fees_expected'] = float(fee_stats.total_expected)
        stats['fees_collected'] = float(fee_stats.total_collected)
        stats['fees_outstanding'] = float(fee_stats.total_outstanding)
        
        # Collection rate
        if stats['fees_expected'] > 0:
            stats['collection_rate'] = round(
                (stats['fees_collected'] / stats['fees_expected']) * 100, 1
            )
        else:
            stats['collection_rate'] = 0
    else:
        stats['fees_expected'] = 0
        stats['fees_collected'] = 0
        stats['fees_outstanding'] = 0
        stats['collection_rate'] = 0
    
    # Today's attendance
    from datetime import date
    today = date.today()
    
    attendance_stats = db.session.query(
        func.count(Attendance.id).label('total'),
        func.sum(func.cast(Attendance.status == AttendanceStatus.PRESENT, db.Integer)).label('present'),
        func.sum(func.cast(Attendance.status == AttendanceStatus.ABSENT, db.Integer)).label('absent'),
    ).filter(
        Attendance.date == today
    ).first()
    
    if attendance_stats.total:
        stats['attendance_rate'] = round(
            (attendance_stats.present / attendance_stats.total) * 100, 1
        )
    else:
        stats['attendance_rate'] = 0
    
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
        gender_stats=dict(gender_stats)
    )


def admin_dashboard():
    """Dashboard for Admin users."""
    school_id = current_user.school_id
    
    stats = {
        'total_students': Student.query.filter_by(
            school_id=school_id, 
            status=StudentStatus.ACTIVE
        ).count(),
        'total_staff': Staff.query.filter_by(
            school_id=school_id, 
            is_active=True
        ).count(),
        'pending_tasks': 0,  # TODO: Implement task system
    }
    
    return render_template('dashboard/admin.html', stats=stats)


def teacher_dashboard():
    """Dashboard for Teachers."""
    from models import ClassSubject, Assessment
    
    staff = current_user.staff_profile
    
    if staff:
        # Classes where user is class teacher
        my_classes = Class.query.filter_by(class_teacher_id=staff.id, is_active=True).all()
        
        # Subjects taught by this teacher
        my_subjects = ClassSubject.query.filter_by(teacher_id=staff.id).all()
        
        # Students in my classes
        from models import ClassEnrollment
        student_count = 0
        for cls in my_classes:
            student_count += ClassEnrollment.query.filter_by(
                class_id=cls.id,
                academic_year_id=g.current_academic_year.id if g.current_academic_year else 0
            ).count()
    else:
        my_classes = []
        my_subjects = []
        student_count = 0
    
    return render_template(
        'dashboard/teacher.html',
        my_classes=my_classes,
        my_subjects=my_subjects,
        student_count=student_count
    )


def accounts_dashboard():
    """Dashboard for Accounts Officers."""
    school_id = current_user.school_id
    
    if g.current_term:
        # Fee statistics
        fee_stats = db.session.query(
            func.coalesce(func.sum(FeeInvoice.total_amount), 0).label('total_expected'),
            func.coalesce(func.sum(FeeInvoice.amount_paid), 0).label('total_collected'),
            func.coalesce(func.sum(FeeInvoice.balance), 0).label('total_outstanding')
        ).filter(
            FeeInvoice.term_id == g.current_term.id
        ).first()
        
        stats = {
            'fees_expected': float(fee_stats.total_expected),
            'fees_collected': float(fee_stats.total_collected),
            'fees_outstanding': float(fee_stats.total_outstanding),
        }
        
        # Students with outstanding fees
        debtors = FeeInvoice.query.filter(
            FeeInvoice.term_id == g.current_term.id,
            FeeInvoice.balance > 0
        ).order_by(FeeInvoice.balance.desc()).limit(10).all()
        
        # Today's payments
        from datetime import date
        today_payments = Payment.query.join(FeeInvoice).join(Student).filter(
            Student.school_id == school_id,
            func.date(Payment.payment_date) == date.today()
        ).all()
        
        stats['today_collected'] = sum(float(p.amount) for p in today_payments)
    else:
        stats = {
            'fees_expected': 0,
            'fees_collected': 0,
            'fees_outstanding': 0,
            'today_collected': 0
        }
        debtors = []
        today_payments = []
    
    return render_template(
        'dashboard/accounts.html',
        stats=stats,
        debtors=debtors,
        today_payments=today_payments
    )
