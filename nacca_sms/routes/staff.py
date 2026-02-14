"""
Staff Management Routes
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import date

from models import db, Staff, User, UserRole, Department, Gender
from app import admin_required

staff_bp = Blueprint('staff', __name__, url_prefix='/staff')


@staff_bp.route('/')
@login_required
def index():
    """List all staff members."""
    school_id = current_user.school_id
    page = request.args.get('page', 1, type=int)
    per_page = 25
    
    search = request.args.get('search', '')
    dept_filter = request.args.get('department_id', type=int)
    
    query = Staff.query.filter_by(school_id=school_id)
    
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            db.or_(
                Staff.first_name.ilike(search_term),
                Staff.last_name.ilike(search_term),
                Staff.staff_id.ilike(search_term)
            )
        )
    
    if dept_filter:
        query = query.filter_by(department_id=dept_filter)
    
    staff = query.order_by(Staff.last_name, Staff.first_name).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    departments = Department.query.filter_by(school_id=school_id).all()
    
    return render_template(
        'staff/index.html',
        staff=staff,
        departments=departments,
        search=search,
        dept_filter=dept_filter
    )


@staff_bp.route('/add', methods=['GET', 'POST'])
@admin_required
def add():
    """Add new staff member."""
    if request.method == 'POST':
        school_id = current_user.school_id
        
        # Generate staff ID
        count = Staff.query.filter_by(school_id=school_id).count()
        staff_id = f"STF{school_id:03d}{count + 1:04d}"
        
        # Parse date of birth
        dob_str = request.form.get('date_of_birth')
        dob = date.fromisoformat(dob_str) if dob_str else None
        
        # Parse employment date
        emp_date_str = request.form.get('date_employed')
        emp_date = date.fromisoformat(emp_date_str) if emp_date_str else date.today()
        
        staff = Staff(
            school_id=school_id,
            staff_id=staff_id,
            first_name=request.form.get('first_name'),
            last_name=request.form.get('last_name'),
            other_names=request.form.get('other_names'),
            gender=Gender(request.form.get('gender')),
            date_of_birth=dob,
            nationality=request.form.get('nationality', 'Ghanaian'),
            phone=request.form.get('phone'),
            email=request.form.get('email'),
            address=request.form.get('address'),
            city=request.form.get('city'),
            region=request.form.get('region'),
            position=request.form.get('position'),
            department_id=request.form.get('department_id', type=int) or None,
            qualification=request.form.get('qualification'),
            date_employed=emp_date,
            ghana_card_number=request.form.get('ghana_card'),
            ssnit_number=request.form.get('ssnit'),
            is_active=True
        )
        db.session.add(staff)
        db.session.flush()
        
        # Create user account if role provided
        role = request.form.get('role')
        email = request.form.get('email')
        
        if role and email:
            user = User(
                school_id=school_id,
                email=email,
                role=UserRole(role),
                staff_id=staff.id,
                is_active=True
            )
            user.set_password(request.form.get('password', 'changeme123'))
            db.session.add(user)
        
        db.session.commit()
        flash(f'Staff member {staff.full_name} added successfully!', 'success')
        return redirect(url_for('staff.view', id=staff.id))
    
    departments = Department.query.filter_by(school_id=current_user.school_id).all()
    
    return render_template('staff/add.html', departments=departments, roles=UserRole)


@staff_bp.route('/<int:id>')
@login_required
def view(id):
    """View staff profile."""
    staff = Staff.query.get_or_404(id)
    
    if staff.school_id != current_user.school_id:
        flash('Access denied.', 'error')
        return redirect(url_for('staff.index'))
    
    return render_template('staff/view.html', staff=staff)


@staff_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit(id):
    """Edit staff information."""
    staff = Staff.query.get_or_404(id)
    
    if staff.school_id != current_user.school_id:
        flash('Access denied.', 'error')
        return redirect(url_for('staff.index'))
    
    if request.method == 'POST':
        staff.first_name = request.form.get('first_name')
        staff.last_name = request.form.get('last_name')
        staff.other_names = request.form.get('other_names')
        staff.gender = Gender(request.form.get('gender'))
        
        dob_str = request.form.get('date_of_birth')
        if dob_str:
            staff.date_of_birth = date.fromisoformat(dob_str)
        
        staff.phone = request.form.get('phone')
        staff.email = request.form.get('email')
        staff.address = request.form.get('address')
        staff.city = request.form.get('city')
        staff.region = request.form.get('region')
        staff.position = request.form.get('position')
        staff.department_id = request.form.get('department_id', type=int) or None
        staff.qualification = request.form.get('qualification')
        
        db.session.commit()
        flash('Staff updated successfully!', 'success')
        return redirect(url_for('staff.view', id=staff.id))
    
    departments = Department.query.filter_by(school_id=current_user.school_id).all()
    
    return render_template('staff/edit.html', staff=staff, departments=departments)


@staff_bp.route('/<int:id>/toggle-status', methods=['POST'])
@admin_required
def toggle_status(id):
    """Toggle staff active status."""
    staff = Staff.query.get_or_404(id)
    
    staff.is_active = not staff.is_active
    
    # Also toggle user account if exists
    if staff.user:
        staff.user.is_active = staff.is_active
    
    db.session.commit()
    
    status = 'activated' if staff.is_active else 'deactivated'
    flash(f'Staff member {status}.', 'success')
    
    return redirect(url_for('staff.view', id=staff.id))
