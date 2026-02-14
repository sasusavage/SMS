"""
Student Management Routes
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, g
from flask_login import login_required, current_user
from datetime import date
import uuid

from models import (
    db, Student, Parent, Class, ClassEnrollment, AcademicYear,
    StudentStatus, Gender, User, UserRole
)
from app import admin_required, staff_required

students_bp = Blueprint('students', __name__, url_prefix='/students')


@students_bp.route('/')
@staff_required
def index():
    """List all students."""
    school_id = current_user.school_id
    page = request.args.get('page', 1, type=int)
    per_page = 25
    
    # Search and filters
    search = request.args.get('search', '')
    class_filter = request.args.get('class_id', type=int)
    status_filter = request.args.get('status', 'active')
    
    query = Student.query.filter_by(school_id=school_id)
    
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            db.or_(
                Student.first_name.ilike(search_term),
                Student.last_name.ilike(search_term),
                Student.student_id.ilike(search_term)
            )
        )
    
    if status_filter and status_filter != 'all':
        query = query.filter_by(status=StudentStatus(status_filter))
    
    if class_filter and g.current_academic_year:
        query = query.join(ClassEnrollment).filter(
            ClassEnrollment.class_id == class_filter,
            ClassEnrollment.academic_year_id == g.current_academic_year.id
        )
    
    students = query.order_by(Student.last_name, Student.first_name).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    classes = Class.query.filter_by(school_id=school_id, is_active=True).all()
    
    return render_template(
        'students/index.html',
        students=students,
        classes=classes,
        search=search,
        class_filter=class_filter,
        status_filter=status_filter
    )


@students_bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add():
    """Add new student."""
    if request.method == 'POST':
        # Generate student ID
        school_id = current_user.school_id
        count = Student.query.filter_by(school_id=school_id).count()
        student_id = f"STU{school_id:03d}{count + 1:04d}"
        
        # Create parent record
        parent = Parent(
            school_id=school_id,
            father_name=request.form.get('father_name'),
            father_phone=request.form.get('father_phone'),
            father_occupation=request.form.get('father_occupation'),
            mother_name=request.form.get('mother_name'),
            mother_phone=request.form.get('mother_phone'),
            mother_occupation=request.form.get('mother_occupation'),
            guardian_name=request.form.get('guardian_name'),
            guardian_phone=request.form.get('guardian_phone'),
            guardian_relationship=request.form.get('guardian_relationship'),
            address=request.form.get('address'),
            city=request.form.get('city'),
            region=request.form.get('region'),
            primary_contact_phone=request.form.get('guardian_phone') or request.form.get('father_phone')
        )
        db.session.add(parent)
        db.session.flush()
        
        # Parse date of birth
        dob_str = request.form.get('date_of_birth')
        dob = date.fromisoformat(dob_str) if dob_str else None
        
        # Create student record
        student = Student(
            school_id=school_id,
            parent_id=parent.id,
            student_id=student_id,
            first_name=request.form.get('first_name'),
            last_name=request.form.get('last_name'),
            other_names=request.form.get('other_names'),
            gender=Gender(request.form.get('gender')),
            date_of_birth=dob,
            nationality=request.form.get('nationality', 'Ghanaian'),
            place_of_birth=request.form.get('place_of_birth'),
            hometown=request.form.get('hometown'),
            religion=request.form.get('religion'),
            blood_group=request.form.get('blood_group'),
            allergies=request.form.get('allergies'),
            medical_conditions=request.form.get('medical_conditions'),
            admission_date=date.today(),
            previous_school=request.form.get('previous_school'),
            status=StudentStatus.ACTIVE
        )
        db.session.add(student)
        db.session.flush()
        
        # Enroll in class if selected
        class_id = request.form.get('class_id', type=int)
        if class_id and g.current_academic_year:
            enrollment = ClassEnrollment(
                student_id=student.id,
                class_id=class_id,
                academic_year_id=g.current_academic_year.id,
                enrollment_date=date.today()
            )
            db.session.add(enrollment)
        
        db.session.commit()
        flash(f'Student {student.full_name} added successfully!', 'success')
        return redirect(url_for('students.view', id=student.id))
    
    classes = Class.query.filter_by(
        school_id=current_user.school_id,
        is_active=True
    ).order_by(Class.name).all()
    
    return render_template('students/add.html', classes=classes)


@students_bp.route('/<int:id>')
@login_required
def view(id):
    """View student profile."""
    student = Student.query.get_or_404(id)
    
    # Verify access
    if student.school_id != current_user.school_id:
        flash('Access denied.', 'error')
        return redirect(url_for('students.index'))
    
    # Restrict parent access
    if current_user.role == UserRole.PARENT:
        if not current_user.parent_profile or student.parent_id != current_user.parent_profile.id:
            flash('Access denied. You can only view your own children.', 'error')
            return redirect(url_for('parent.dashboard'))
        # If parent is viewing their child, redirect to parent portal view instead
        # This keeps them in the parent portal context
        return redirect(url_for('parent.child_profile', id=id))
    
    # Get current enrollment
    current_enrollment = None
    if g.current_academic_year:
        current_enrollment = ClassEnrollment.query.filter_by(
            student_id=student.id,
            academic_year_id=g.current_academic_year.id
        ).first()
    
    # Get enrollment history
    enrollment_history = ClassEnrollment.query.filter_by(
        student_id=student.id
    ).join(AcademicYear).order_by(AcademicYear.start_date.desc()).all()
    
    return render_template(
        'students/view.html',
        student=student,
        current_enrollment=current_enrollment,
        enrollment_history=enrollment_history
    )


@students_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(id):
    """Edit student information."""
    student = Student.query.get_or_404(id)
    
    if student.school_id != current_user.school_id:
        flash('Access denied.', 'error')
        return redirect(url_for('students.index'))
    
    if request.method == 'POST':
        student.first_name = request.form.get('first_name')
        student.last_name = request.form.get('last_name')
        student.other_names = request.form.get('other_names')
        student.gender = Gender(request.form.get('gender'))
        
        dob_str = request.form.get('date_of_birth')
        if dob_str:
            student.date_of_birth = date.fromisoformat(dob_str)
        
        student.nationality = request.form.get('nationality')
        student.place_of_birth = request.form.get('place_of_birth')
        student.hometown = request.form.get('hometown')
        student.religion = request.form.get('religion')
        student.blood_group = request.form.get('blood_group')
        student.allergies = request.form.get('allergies')
        student.medical_conditions = request.form.get('medical_conditions')
        
        # Update parent info
        if student.parent:
            student.parent.father_name = request.form.get('father_name')
            student.parent.father_phone = request.form.get('father_phone')
            student.parent.mother_name = request.form.get('mother_name')
            student.parent.mother_phone = request.form.get('mother_phone')
            student.parent.guardian_name = request.form.get('guardian_name')
            student.parent.guardian_phone = request.form.get('guardian_phone')
            student.parent.address = request.form.get('address')
        
        db.session.commit()
        flash('Student updated successfully!', 'success')
        return redirect(url_for('students.view', id=student.id))
    
    classes = Class.query.filter_by(
        school_id=current_user.school_id,
        is_active=True
    ).order_by(Class.name).all()
    
    return render_template('students/edit.html', student=student, classes=classes)


@students_bp.route('/<int:id>/enroll', methods=['POST'])
@admin_required
def enroll(id):
    """Enroll student in a class."""
    student = Student.query.get_or_404(id)
    
    class_id = request.form.get('class_id', type=int)
    
    if not class_id or not g.current_academic_year:
        flash('Invalid enrollment request.', 'error')
        return redirect(url_for('students.view', id=id))
    
    # Check if already enrolled
    existing = ClassEnrollment.query.filter_by(
        student_id=id,
        academic_year_id=g.current_academic_year.id
    ).first()
    
    if existing:
        existing.class_id = class_id
        flash('Class enrollment updated.', 'success')
    else:
        enrollment = ClassEnrollment(
            student_id=id,
            class_id=class_id,
            academic_year_id=g.current_academic_year.id,
            enrollment_date=date.today()
        )
        db.session.add(enrollment)
        flash('Student enrolled in class.', 'success')
    
    db.session.commit()
    return redirect(url_for('students.view', id=id))


@students_bp.route('/<int:id>/status', methods=['POST'])
@admin_required
def update_status(id):
    """Update student status."""
    student = Student.query.get_or_404(id)
    
    new_status = request.form.get('status')
    if new_status:
        student.status = StudentStatus(new_status)
        db.session.commit()
        flash(f'Student status updated to {new_status}.', 'success')
    
    return redirect(url_for('students.view', id=id))


@students_bp.route('/api/search')
@login_required
def api_search():
    """Search students API."""
    q = request.args.get('q', '')
    limit = request.args.get('limit', 10, type=int)
    
    if len(q) < 2:
        return jsonify([])
    
    students = Student.query.filter(
        Student.school_id == current_user.school_id,
        db.or_(
            Student.first_name.ilike(f'%{q}%'),
            Student.last_name.ilike(f'%{q}%'),
            Student.student_id.ilike(f'%{q}%')
        )
    ).limit(limit).all()
    
    return jsonify([
        {
            'id': s.id,
            'student_id': s.student_id,
            'name': s.full_name,
            'class': s.current_class.name if s.current_class else 'Not Enrolled'
        }
        for s in students
    ])


# =============================================================================
# PARENT ACCOUNT MANAGEMENT
# =============================================================================
@students_bp.route('/<int:id>/parent-account', methods=['GET', 'POST'])
@admin_required
def parent_account(id):
    """View/manage parent account for a student."""
    student = Student.query.get_or_404(id)
    
    if student.school_id != current_user.school_id:
        flash('Access denied.', 'error')
        return redirect(url_for('students.index'))
    
    if not student.parent:
        flash('No parent information for this student.', 'error')
        return redirect(url_for('students.view', id=id))
    
    parent = student.parent
    parent_user = parent.user
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create_account':
            # Create new parent user account
            password = request.form.get('password', '').strip()
            
            if len(password) < 6:
                flash('Password must be at least 6 characters.', 'error')
                return redirect(url_for('students.parent_account', id=id))
            
            if parent_user:
                flash('Parent already has an account.', 'error')
                return redirect(url_for('students.parent_account', id=id))
            
            # Generate email from parent info or use phone
            email = parent.father_email or parent.mother_email or parent.guardian_email
            if not email:
                # Generate email from phone
                phone = parent.primary_contact_phone or parent.father_phone or parent.mother_phone
                email = f"parent_{phone}@school.local"
            
            # Check if email already exists
            if User.query.filter_by(email=email).first():
                email = f"parent_{parent.id}@school.local"
            
            new_user = User(
                school_id=student.school_id,
                email=email,
                role=UserRole.PARENT,
                parent_id=parent.id
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            flash(f'Parent account created! They can login with any phone number and password.', 'success')
        
        elif action == 'reset_password':
            # Reset existing parent password
            password = request.form.get('password', '').strip()
            
            if len(password) < 6:
                flash('Password must be at least 6 characters.', 'error')
                return redirect(url_for('students.parent_account', id=id))
            
            if not parent_user:
                flash('Parent does not have an account yet.', 'error')
                return redirect(url_for('students.parent_account', id=id))
            
            parent_user.set_password(password)
            db.session.commit()
            
            flash('Parent password has been reset.', 'success')
        
        elif action == 'toggle_active':
            # Activate/deactivate account
            if parent_user:
                parent_user.is_active = not parent_user.is_active
                db.session.commit()
                status = 'activated' if parent_user.is_active else 'deactivated'
                flash(f'Parent account has been {status}.', 'success')
        
        return redirect(url_for('students.parent_account', id=id))
    
    return render_template('students/parent_account.html', 
        student=student, 
        parent=parent,
        parent_user=parent_user
    )
