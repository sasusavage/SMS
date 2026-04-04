"""
API Routes for AJAX operations
"""
from flask import Blueprint, jsonify, request, g
from flask_login import login_required, current_user

from models import db, Student, Class, Subject, Staff

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/students/search')
@login_required
def search_students():
    q = request.args.get('q', '')
    if len(q) < 2:
        return jsonify([])
    
    students = Student.query.filter(
        Student.school_id == current_user.school_id,
        db.or_(
            Student.first_name.ilike(f'%{q}%'),
            Student.last_name.ilike(f'%{q}%'),
            Student.student_id.ilike(f'%{q}%')
        )
    ).limit(10).all()
    
    return jsonify([{'id': s.id, 'name': s.full_name, 'student_id': s.student_id} for s in students])


@api_bp.route('/classes')
@login_required
def get_classes():
    classes = Class.query.filter_by(school_id=current_user.school_id, is_active=True).all()
    return jsonify([{'id': c.id, 'name': c.name} for c in classes])


@api_bp.route('/subjects')
@login_required
def get_subjects():
    subjects = Subject.query.filter_by(school_id=current_user.school_id, is_active=True).all()
    return jsonify([{'id': s.id, 'name': s.name} for s in subjects])


@api_bp.route('/attendance/scan', methods=['POST'])
@login_required
def scan_attendance():
    """Process a QR code scan for attendance."""
    from models import Attendance, AttendanceStatus, ClassEnrollment
    import datetime
    
    data = request.get_json()
    student_uuid = data.get('student_uuid')
    
    if not student_uuid:
        return jsonify({"success": False, "message": "Missing student UUID"}), 400
        
    student = Student.query.filter_by(
        uuid=student_uuid, 
        school_id=current_user.school_id
    ).first()
    
    if not student:
        return jsonify({"success": False, "message": "Student not recognized or belongs to another school"}), 404
        
    if not g.current_academic_year:
        return jsonify({"success": False, "message": "No active academic year found"}), 400
        
    enrollment = ClassEnrollment.query.filter_by(
        student_id=student.id,
        academic_year_id=g.current_academic_year.id
    ).first()
    
    if not enrollment:
        return jsonify({"success": False, "message": "Student found but not enrolled in current academic year"}), 400
        
    today = datetime.date.today()
    
    existing = Attendance.query.filter_by(student_id=student.id, date=today).first()
    if existing:
        if existing.status == AttendanceStatus.PRESENT:
            return jsonify({
                "success": True, 
                "message": f"{student.full_name} is already marked Present.", 
                "already_done": True, 
                "student": student.full_name, 
                "class": enrollment.class_.name
            }), 200
        else:
            existing.status = AttendanceStatus.PRESENT
            existing.recorded_by_id = current_user.id
            db.session.commit()
            msg = f"{student.full_name} arrival updated to Present."
    else:
        new_attendance = Attendance(
            school_id=current_user.school_id,
            student_id=student.id,
            class_id=enrollment.class_id,
            date=today,
            status=AttendanceStatus.PRESENT,
            recorded_by_id=current_user.id
        )
        db.session.add(new_attendance)
        db.session.commit()
        msg = f"{student.full_name} arrival recorded."
        
    from services.notification_service import NotificationService
    try:
        NotificationService.send_attendance_alert(
            student_id=student.id,
            status=AttendanceStatus.PRESENT,
            school_id=current_user.school_id
        )
    except Exception as e:
        print(f"Notice: SMS alert failed: {e}")

    return jsonify({
        "success": True, 
        "message": msg,
        "student": student.full_name,
        "class": enrollment.class_.name,
        "photo": student.photo_url or ""
    })
