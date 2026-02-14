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
