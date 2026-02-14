"""
Authentication Routes
"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, UserRole

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    """Landing page - redirect based on auth status."""
    if current_user.is_authenticated:
        if current_user.role == UserRole.PARENT:
            return redirect(url_for('parent.dashboard'))
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Contact administrator.', 'error')
                return render_template('auth/login.html')
            
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            if user.role == UserRole.PARENT:
                return redirect(url_for('parent.dashboard'))
            return redirect(url_for('dashboard.index'))
        
        flash('Invalid email or password.', 'error')
    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout."""
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/parent-login', methods=['GET', 'POST'])
def parent_login():
    """Parent portal login using any registered phone number."""
    if current_user.is_authenticated:
        if current_user.role == UserRole.PARENT:
            return redirect(url_for('parent.dashboard'))
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        
        # Find parent by ANY of their phone numbers
        from models import Parent
        from sqlalchemy import or_
        
        parent = Parent.query.filter(
            or_(
                Parent.primary_contact_phone == phone,
                Parent.father_phone == phone,
                Parent.mother_phone == phone,
                Parent.guardian_phone == phone
            )
        ).first()
        
        if parent and parent.user:
            user = parent.user
            if user.check_password(password):
                if not user.is_active:
                    flash('Your account has been deactivated. Contact the school.', 'error')
                    return render_template('auth/parent_login.html')
                
                login_user(user)
                user.last_login = datetime.utcnow()
                db.session.commit()
                
                return redirect(url_for('parent.dashboard'))
        
        flash('Invalid phone number or password.', 'error')
    
    return render_template('auth/parent_login.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Password reset request."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        
        if user:
            # TODO: Implement email sending
            flash('Password reset instructions have been sent to your email.', 'success')
        else:
            flash('If an account exists with that email, reset instructions will be sent.', 'info')
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html')
