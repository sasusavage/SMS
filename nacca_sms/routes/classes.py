"""
Classes and Subjects Management Routes
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, g
from flask_login import login_required, current_user

from models import db, Class, Subject, Department, ClassSubject, Staff, ClassEnrollment
from app import admin_required, staff_required

classes_bp = Blueprint('classes', __name__, url_prefix='/classes')


# =============================================================================
# CLASSES
# =============================================================================
@classes_bp.route('/')
@staff_required
def index():
    """List all classes."""
    school_id = current_user.school_id
    
    classes = Class.query.filter_by(
        school_id=school_id,
        is_active=True
    ).order_by(Class.level, Class.grade_number, Class.section).all()
    
    # Get student counts
    class_counts = {}
    if g.current_academic_year:
        for cls in classes:
            count = ClassEnrollment.query.filter_by(
                class_id=cls.id,
                academic_year_id=g.current_academic_year.id
            ).count()
            class_counts[cls.id] = count
    
    return render_template(
        'classes/index.html',
        classes=classes,
        class_counts=class_counts
    )


@classes_bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add():
    """Add new class."""
    if request.method == 'POST':
        cls = Class(
            school_id=current_user.school_id,
            name=request.form.get('name'),
            level=request.form.get('level'),
            grade_number=request.form.get('grade_number', type=int),
            section=request.form.get('section'),
            capacity=request.form.get('capacity', 40, type=int),
            room_number=request.form.get('room_number'),
            class_teacher_id=request.form.get('class_teacher_id', type=int) or None,
            is_active=True
        )
        db.session.add(cls)
        db.session.commit()
        
        flash(f'Class {cls.name} created successfully!', 'success')
        return redirect(url_for('classes.view', id=cls.id))
    
    teachers = Staff.query.filter_by(
        school_id=current_user.school_id,
        is_active=True
    ).filter(Staff.position.ilike('%teacher%')).all()
    
    levels = ['Creche', 'Nursery', 'Kindergarten', 'Primary', 'JHS', 'SHS']
    
    return render_template('classes/add.html', teachers=teachers, levels=levels)


@classes_bp.route('/<int:id>')
@staff_required
def view(id):
    """View class details."""
    cls = Class.query.get_or_404(id)
    
    if cls.school_id != current_user.school_id:
        flash('Access denied.', 'error')
        return redirect(url_for('classes.index'))
    
    # Get enrolled students
    students = []
    if g.current_academic_year:
        enrollments = ClassEnrollment.query.filter_by(
            class_id=cls.id,
            academic_year_id=g.current_academic_year.id
        ).all()
        students = [e.student for e in enrollments]
    
    # Get assigned subjects
    subjects = []
    if g.current_academic_year:
        class_subjects = ClassSubject.query.filter_by(
            class_id=cls.id,
            academic_year_id=g.current_academic_year.id
        ).all()
        subjects = class_subjects
    
    # Count by gender
    from models import Gender
    male_count = sum(1 for s in students if s.gender == Gender.MALE)
    female_count = sum(1 for s in students if s.gender == Gender.FEMALE)
    
    return render_template(
        'classes/view.html',
        cls=cls,
        students=students,
        subjects=subjects,
        male_count=male_count,
        female_count=female_count
    )


@classes_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(id):
    """Edit class details."""
    cls = Class.query.get_or_404(id)
    
    if cls.school_id != current_user.school_id:
        flash('Access denied.', 'error')
        return redirect(url_for('classes.index'))
    
    if request.method == 'POST':
        cls.name = request.form.get('name')
        cls.level = request.form.get('level')
        cls.grade_number = request.form.get('grade_number', type=int)
        cls.section = request.form.get('section')
        cls.capacity = request.form.get('capacity', type=int)
        cls.room_number = request.form.get('room_number')
        cls.class_teacher_id = request.form.get('class_teacher_id', type=int) or None
        
        db.session.commit()
        flash('Class updated successfully!', 'success')
        return redirect(url_for('classes.view', id=cls.id))
    
    teachers = Staff.query.filter_by(
        school_id=current_user.school_id,
        is_active=True
    ).filter(Staff.position.ilike('%teacher%')).all()
    
    levels = ['Creche', 'Nursery', 'Kindergarten', 'Primary', 'JHS', 'SHS']
    
    return render_template('classes/edit.html', cls=cls, teachers=teachers, levels=levels)


@classes_bp.route('/<int:id>/assign-subjects', methods=['GET', 'POST'])
@admin_required
def assign_subjects(id):
    """Assign subjects and teachers to a class."""
    cls = Class.query.get_or_404(id)
    
    if request.method == 'POST':
        if not g.current_academic_year:
            flash('No active academic year.', 'error')
            return redirect(url_for('classes.view', id=id))
        
        # Get form data
        subject_ids = request.form.getlist('subjects[]')
        teacher_ids = request.form.getlist('teachers[]')
        
        # Remove existing assignments for this year
        ClassSubject.query.filter_by(
            class_id=cls.id,
            academic_year_id=g.current_academic_year.id
        ).delete()
        
        # Create new assignments
        for i, subject_id in enumerate(subject_ids):
            if subject_id:
                teacher_id = teacher_ids[i] if i < len(teacher_ids) else None
                cs = ClassSubject(
                    class_id=cls.id,
                    subject_id=int(subject_id),
                    teacher_id=int(teacher_id) if teacher_id else None,
                    academic_year_id=g.current_academic_year.id
                )
                db.session.add(cs)
        
        db.session.commit()
        flash('Subjects assigned successfully!', 'success')
        return redirect(url_for('classes.view', id=id))
    
    subjects = Subject.query.filter_by(
        school_id=current_user.school_id,
        is_active=True
    ).all()
    
    teachers = Staff.query.filter_by(
        school_id=current_user.school_id,
        is_active=True
    ).filter(Staff.position.ilike('%teacher%')).all()
    
    # Current assignments
    current_assignments = []
    if g.current_academic_year:
        current_assignments = ClassSubject.query.filter_by(
            class_id=cls.id,
            academic_year_id=g.current_academic_year.id
        ).all()
    
    return render_template(
        'classes/assign_subjects.html',
        cls=cls,
        subjects=subjects,
        teachers=teachers,
        current_assignments=current_assignments
    )


# =============================================================================
# SUBJECTS
# =============================================================================
@classes_bp.route('/subjects')
@staff_required
def subjects():
    """List all subjects."""
    school_id = current_user.school_id
    
    subjects = Subject.query.filter_by(
        school_id=school_id,
        is_active=True
    ).order_by(Subject.name).all()
    
    return render_template('classes/subjects.html', subjects=subjects)


@classes_bp.route('/subjects/add', methods=['GET', 'POST'])
@admin_required
def add_subject():
    """Add new subject."""
    if request.method == 'POST':
        subject = Subject(
            school_id=current_user.school_id,
            department_id=request.form.get('department_id', type=int) or None,
            name=request.form.get('name'),
            code=request.form.get('code'),
            description=request.form.get('description'),
            is_core=request.form.get('is_core') == 'true',
            is_active=True
        )
        db.session.add(subject)
        db.session.commit()
        
        flash(f'Subject {subject.name} added successfully!', 'success')
        return redirect(url_for('classes.subjects'))
    
    departments = Department.query.filter_by(school_id=current_user.school_id).all()
    
    return render_template('classes/add_subject.html', departments=departments)


# =============================================================================
# DEPARTMENTS
# =============================================================================
@classes_bp.route('/departments')
@staff_required
def departments():
    """List all departments."""
    school_id = current_user.school_id
    
    depts = Department.query.filter_by(
        school_id=school_id,
        is_active=True
    ).order_by(Department.name).all()
    
    return render_template('classes/departments.html', departments=depts)


@classes_bp.route('/departments/add', methods=['POST'])
@admin_required
def add_department():
    """Add new department."""
    dept = Department(
        school_id=current_user.school_id,
        name=request.form.get('name'),
        code=request.form.get('code'),
        description=request.form.get('description'),
        is_active=True
    )
    db.session.add(dept)
    db.session.commit()
    
    flash(f'Department {dept.name} added successfully!', 'success')
    return redirect(url_for('classes.departments'))
