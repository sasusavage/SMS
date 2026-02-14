"""
Assessments & Grading Routes - NaCCA Standards Implementation
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, g, current_app
from flask_login import login_required, current_user
from sqlalchemy import func

from models import (
    db, Assessment, ClassSubject, Student, Class, Subject, Term,
    ClassEnrollment, TerminalReport, UserRole
)
from app import teacher_required, admin_required, staff_required

assessments_bp = Blueprint('assessments', __name__, url_prefix='/assessments')


# =============================================================================
# ASSESSMENT ENTRY
# =============================================================================
@assessments_bp.route('/')
@teacher_required
def index():
    """Assessment management dashboard."""
    school_id = current_user.school_id
    
    # Get classes and subjects based on role
    if current_user.is_admin():
        classes = Class.query.filter_by(school_id=school_id, is_active=True).all()
        class_subjects = ClassSubject.query.filter_by(
            academic_year_id=g.current_academic_year.id if g.current_academic_year else 0
        ).all()
    else:
        # Teachers only see their assigned classes/subjects
        staff = current_user.staff_profile
        if staff:
            class_subjects = ClassSubject.query.filter_by(
                teacher_id=staff.id,
                academic_year_id=g.current_academic_year.id if g.current_academic_year else 0
            ).all()
            class_ids = [cs.class_id for cs in class_subjects]
            classes = Class.query.filter(Class.id.in_(class_ids)).all()
        else:
            classes = []
            class_subjects = []
    
    return render_template(
        'assessments/index.html',
        classes=classes,
        class_subjects=class_subjects
    )


@assessments_bp.route('/entry/<int:class_subject_id>')
@teacher_required
def entry(class_subject_id):
    """Score entry page for a specific class subject."""
    class_subject = ClassSubject.query.get_or_404(class_subject_id)
    
    # Verify access
    if not current_user.is_admin():
        staff = current_user.staff_profile
        if staff and class_subject.teacher_id != staff.id:
            flash('You are not authorized to enter scores for this subject.', 'error')
            return redirect(url_for('assessments.index'))
    
    # Get students enrolled in this class
    enrollments = ClassEnrollment.query.filter_by(
        class_id=class_subject.class_id,
        academic_year_id=class_subject.academic_year_id
    ).join(Student).order_by(Student.last_name, Student.first_name).all()
    
    # Get existing assessments
    if g.current_term:
        existing_assessments = {
            a.student_id: a for a in Assessment.query.filter_by(
                class_subject_id=class_subject_id,
                term_id=g.current_term.id
            ).all()
        }
    else:
        existing_assessments = {}
    
    return render_template(
        'assessments/entry.html',
        class_subject=class_subject,
        enrollments=enrollments,
        assessments=existing_assessments
    )


@assessments_bp.route('/save', methods=['POST'])
@teacher_required
def save_scores():
    """Save assessment scores with automatic grading."""
    data = request.get_json()
    
    class_subject_id = data.get('class_subject_id')
    scores = data.get('scores', [])
    
    if not class_subject_id or not g.current_term:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400
    
    class_subject = ClassSubject.query.get(class_subject_id)
    if not class_subject:
        return jsonify({'success': False, 'message': 'Subject not found'}), 404
    
    # Determine grading level from class
    class_obj = Class.query.get(class_subject.class_id)
    grading_level = class_obj.level.upper() if class_obj else 'PRIMARY'
    if grading_level not in ['PRIMARY', 'JHS', 'SHS']:
        grading_level = 'PRIMARY'
    
    saved_count = 0
    
    for score_data in scores:
        student_id = score_data.get('student_id')
        
        # Find or create assessment record
        assessment = Assessment.query.filter_by(
            student_id=student_id,
            class_subject_id=class_subject_id,
            term_id=g.current_term.id
        ).first()
        
        if not assessment:
            assessment = Assessment(
                student_id=student_id,
                class_subject_id=class_subject_id,
                term_id=g.current_term.id,
                recorded_by_id=current_user.id
            )
            db.session.add(assessment)
        
        # Update scores with validation
        assessment.classwork_score = min(max(float(score_data.get('classwork', 0) or 0), 0), 30)
        assessment.homework_score = min(max(float(score_data.get('homework', 0) or 0), 0), 10)
        assessment.project_score = min(max(float(score_data.get('project', 0) or 0), 0), 10)
        assessment.exam_score = min(max(float(score_data.get('exam', 0) or 0), 0), 50)
        
        # Calculate total and grade
        assessment.calculate_total()
        calculate_grade_for_assessment(assessment, grading_level)
        
        saved_count += 1
    
    # Calculate class positions
    calculate_class_positions(class_subject_id, g.current_term.id)
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Saved {saved_count} assessment records',
        'saved_count': saved_count
    })


def calculate_grade_for_assessment(assessment, level='PRIMARY'):
    """Calculate grade based on NaCCA standards."""
    grading_scale = current_app.config.get('NACCA_GRADING_SCALE', {}).get(level, {})
    
    if assessment.total_score is None:
        assessment.calculate_total()
    
    for (min_score, max_score), (grade, remark) in grading_scale.items():
        if min_score <= assessment.total_score <= max_score:
            assessment.grade = grade
            assessment.grade_remark = remark
            return
    
    assessment.grade = None
    assessment.grade_remark = None


def calculate_class_positions(class_subject_id, term_id):
    """Calculate and update class positions for a subject."""
    assessments = Assessment.query.filter_by(
        class_subject_id=class_subject_id,
        term_id=term_id
    ).order_by(Assessment.total_score.desc()).all()
    
    position = 1
    prev_score = None
    
    for i, assessment in enumerate(assessments):
        if prev_score is not None and assessment.total_score != prev_score:
            position = i + 1
        assessment.class_position = position
        prev_score = assessment.total_score


# =============================================================================
# GRADE CALCULATION API
# =============================================================================
@assessments_bp.route('/api/calculate-grade', methods=['POST'])
@teacher_required
def api_calculate_grade():
    """API endpoint to calculate grade from scores."""
    data = request.get_json()
    
    classwork = float(data.get('classwork', 0) or 0)
    homework = float(data.get('homework', 0) or 0)
    project = float(data.get('project', 0) or 0)
    exam = float(data.get('exam', 0) or 0)
    level = data.get('level', 'PRIMARY').upper()
    
    # Validate ranges
    classwork = min(max(classwork, 0), 30)
    homework = min(max(homework, 0), 10)
    project = min(max(project, 0), 10)
    exam = min(max(exam, 0), 50)
    
    total = classwork + homework + project + exam
    
    # Calculate grade
    grading_scale = current_app.config.get('NACCA_GRADING_SCALE', {}).get(level, {})
    grade = None
    remark = None
    
    for (min_score, max_score), (g, r) in grading_scale.items():
        if min_score <= total <= max_score:
            grade = g
            remark = r
            break
    
    return jsonify({
        'total': total,
        'grade': grade,
        'remark': remark
    })


# =============================================================================
# VIEWING ASSESSMENTS
# =============================================================================
@assessments_bp.route('/view/<int:class_id>')
@teacher_required
def view_class(class_id):
    """View all assessments for a class."""
    class_obj = Class.query.get_or_404(class_id)
    
    if not g.current_term:
        flash('No active term found.', 'warning')
        return redirect(url_for('assessments.index'))
    
    # Get all subjects for this class
    class_subjects = ClassSubject.query.filter_by(
        class_id=class_id,
        academic_year_id=g.current_academic_year.id
    ).all()
    
    # Get all students in this class
    enrollments = ClassEnrollment.query.filter_by(
        class_id=class_id,
        academic_year_id=g.current_academic_year.id
    ).join(Student).order_by(Student.last_name, Student.first_name).all()
    
    # Build assessment matrix
    assessment_data = {}
    for enrollment in enrollments:
        student = enrollment.student
        assessment_data[student.id] = {
            'student': student,
            'subjects': {}
        }
        
        for cs in class_subjects:
            assessment = Assessment.query.filter_by(
                student_id=student.id,
                class_subject_id=cs.id,
                term_id=g.current_term.id
            ).first()
            
            assessment_data[student.id]['subjects'][cs.subject_id] = assessment
    
    return render_template(
        'assessments/view_class.html',
        class_obj=class_obj,
        class_subjects=class_subjects,
        assessment_data=assessment_data
    )


@assessments_bp.route('/student/<int:student_id>')
@teacher_required
def view_student(student_id):
    """View all assessments for a specific student."""
    student = Student.query.get_or_404(student_id)
    
    if not g.current_term or not g.current_academic_year:
        flash('No active academic term.', 'warning')
        return redirect(url_for('assessments.index'))
    
    # Get current enrollment
    enrollment = ClassEnrollment.query.filter_by(
        student_id=student_id,
        academic_year_id=g.current_academic_year.id
    ).first()
    
    if not enrollment:
        flash('Student not enrolled in current academic year.', 'warning')
        return redirect(url_for('assessments.index'))
    
    # Get all assessments for this student in current term
    assessments = Assessment.query.filter_by(
        student_id=student_id,
        term_id=g.current_term.id
    ).join(ClassSubject).join(Subject).all()
    
    # Calculate aggregates
    total_subjects = len(assessments)
    if assessments:
        total_marks = sum(a.total_score or 0 for a in assessments)
        average_score = round(total_marks / len(assessments), 1)
        
        # Calculate overall grade based on average
        grading_scale = current_app.config.get('NACCA_GRADING_SCALE', {}).get('PRIMARY', {})
        overall_grade = '-'
        for (min_score, max_score), (grade, remark) in grading_scale.items():
            if min_score <= average_score <= max_score:
                overall_grade = grade
                break
    else:
        total_marks = 0
        average_score = 0
        overall_grade = '-'
    
    # Get class position (from terminal report if exists)
    position = '-'
    terminal_report = TerminalReport.query.filter_by(
        student_id=student_id,
        term_id=g.current_term.id
    ).first()
    if terminal_report and terminal_report.class_position:
        position = terminal_report.class_position
    
    return render_template(
        'assessments/view_student.html',
        student=student,
        enrollment=enrollment,
        assessments=assessments,
        total_subjects=total_subjects,
        total_marks=total_marks,
        average_score=average_score,
        overall_grade=overall_grade,
        position=position
    )


# =============================================================================
# TERMINAL REPORTS
# =============================================================================
@assessments_bp.route('/reports')
@teacher_required
def terminal_reports():
    """Terminal report management."""
    if not g.current_term:
        flash('No active academic term.', 'warning')
        return redirect(url_for('dashboard.index'))
    
    classes = Class.query.filter_by(
        school_id=current_user.school_id,
        is_active=True
    ).order_by(Class.name).all()
    
    # Compute counts for each class
    class_data = []
    for cls in classes:
        # Count enrolled students
        student_count = ClassEnrollment.query.filter_by(
            class_id=cls.id,
            academic_year_id=g.current_academic_year.id if g.current_academic_year else 0
        ).count()
        
        # Count generated reports
        reports_generated = TerminalReport.query.join(ClassEnrollment).filter(
            ClassEnrollment.class_id == cls.id,
            TerminalReport.term_id == g.current_term.id
        ).count()
        
        class_data.append({
            'id': cls.id,
            'name': cls.name,
            'level': cls.level,
            'student_count': student_count,
            'reports_generated': reports_generated
        })
    
    return render_template(
        'assessments/terminal_reports.html',
        classes=class_data
    )


@assessments_bp.route('/reports/generate/<int:class_id>', methods=['POST'])
@teacher_required
def generate_reports(class_id):
    """Generate terminal reports for all students in a class."""
    class_obj = Class.query.get_or_404(class_id)
    
    # Verify access: must be admin or the class teacher
    if not current_user.is_admin():
        staff = current_user.staff_profile
        if not staff or class_obj.class_teacher_id != staff.id:
            flash('You can only generate reports for your own class.', 'error')
            return redirect(url_for('assessments.terminal_reports'))
    
    if not g.current_term:
        flash('No active term.', 'error')
        return redirect(url_for('assessments.terminal_reports'))
    
    # Get all enrolled students
    enrollments = ClassEnrollment.query.filter_by(
        class_id=class_id,
        academic_year_id=g.current_academic_year.id
    ).all()
    
    generated_count = 0
    
    for enrollment in enrollments:
        # Check if report already exists
        report = TerminalReport.query.filter_by(
            student_id=enrollment.student_id,
            term_id=g.current_term.id
        ).first()
        
        if not report:
            report = TerminalReport(
                student_id=enrollment.student_id,
                term_id=g.current_term.id,
                class_enrollment_id=enrollment.id
            )
            db.session.add(report)
        
        # Calculate aggregates from assessments
        assessments = Assessment.query.join(ClassSubject).filter(
            Assessment.student_id == enrollment.student_id,
            Assessment.term_id == g.current_term.id,
            ClassSubject.class_id == class_id
        ).all()
        
        if assessments:
            report.total_marks = sum(a.total_score or 0 for a in assessments)
            report.average_score = report.total_marks / len(assessments)
            report.class_size = len(enrollments)
        
        # Calculate attendance
        from models import Attendance, AttendanceStatus
        from datetime import date
        
        attendance_records = Attendance.query.filter(
            Attendance.student_id == enrollment.student_id,
            Attendance.class_id == class_id,
            Attendance.date >= g.current_term.start_date,
            Attendance.date <= min(g.current_term.end_date, date.today())
        ).all()
        
        report.total_days = len(attendance_records)
        report.days_present = sum(1 for a in attendance_records 
                                   if a.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE])
        report.days_absent = sum(1 for a in attendance_records 
                                  if a.status == AttendanceStatus.ABSENT)
        
        generated_count += 1
    
    # Calculate class positions based on average score
    calculate_terminal_positions(class_id, g.current_term.id)
    
    db.session.commit()
    
    flash(f'Successfully generated {generated_count} terminal reports!', 'success')
    return redirect(url_for('assessments.terminal_reports'))


def calculate_terminal_positions(class_id, term_id):
    """Calculate overall class positions for terminal reports."""
    from models import ClassEnrollment
    
    reports = TerminalReport.query.join(ClassEnrollment).filter(
        ClassEnrollment.class_id == class_id,
        TerminalReport.term_id == term_id
    ).order_by(TerminalReport.average_score.desc()).all()
    
    position = 1
    prev_score = None
    
    for i, report in enumerate(reports):
        if prev_score is not None and report.average_score != prev_score:
            position = i + 1
        report.class_position = position
        prev_score = report.average_score


@assessments_bp.route('/reports/publish/<int:class_id>', methods=['POST'])
@teacher_required
def publish_reports(class_id):
    """Publish terminal reports for parent viewing."""
    if not g.current_term:
        flash('No active term.', 'error')
        return redirect(url_for('assessments.terminal_reports'))
    
    from datetime import datetime
    from models import ClassEnrollment, Class
    
    # Verify access: must be admin or the class teacher
    cls = Class.query.get_or_404(class_id)
    if not current_user.is_admin():
        staff = current_user.staff_profile
        if not staff or cls.class_teacher_id != staff.id:
            flash('You can only publish reports for your own class.', 'error')
            return redirect(url_for('assessments.terminal_reports'))
    
    reports = TerminalReport.query.join(ClassEnrollment).filter(
        ClassEnrollment.class_id == class_id,
        TerminalReport.term_id == g.current_term.id
    ).all()
    
    if not reports:
        flash('No reports found to publish.', 'warning')
        return redirect(url_for('assessments.terminal_reports'))
    
    for report in reports:
        report.is_published = True
        report.published_at = datetime.utcnow()
    
    db.session.commit()
    
    flash(f'Successfully published {len(reports)} terminal reports!', 'success')
    return redirect(url_for('assessments.terminal_reports'))
