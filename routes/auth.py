"""
Authentication Routes
"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, UserRole

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    """Landing page - show index for unauthenticated users."""
    if current_user.is_authenticated:
        if current_user.role == UserRole.PARENT:
            return redirect(url_for('parent.dashboard'))
        if current_user.role == UserRole.SUPER_ADMIN:
            return redirect(url_for('saas_admin.dashboard'))
        return redirect(url_for('dashboard.index'))
    return render_template('index.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login."""
    if current_user.is_authenticated:
        if current_user.role == UserRole.SUPER_ADMIN:
            return redirect(url_for('saas_admin.dashboard'))
        if current_user.role == UserRole.PARENT:
            return redirect(url_for('parent.dashboard'))
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

            # 2FA gate — redirect to verify step if enabled
            if user.totp_enabled and user.totp_secret:
                session['2fa_pending_user_id'] = user.id
                session['2fa_remember'] = bool(remember)
                return redirect(url_for('auth.verify_2fa'))

            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()

            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)

            if user.role == UserRole.PARENT:
                return redirect(url_for('parent.dashboard'))
            if user.role == UserRole.SUPER_ADMIN:
                return redirect(url_for('saas_admin.dashboard'))
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


# =============================================================================
# 2FA — TOTP (Google Authenticator)
# =============================================================================

@auth_bp.route('/2fa/setup', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    """Admin/Headteacher 2FA enrollment."""
    if current_user.role not in [UserRole.HEADTEACHER, UserRole.ADMIN, UserRole.SUPER_ADMIN]:
        flash('2FA setup is for admin accounts only.', 'error')
        return redirect(url_for('dashboard.index'))

    import pyotp, qrcode, io, base64

    if request.method == 'POST':
        token = request.form.get('token', '').strip()
        secret = request.form.get('secret', '').strip()

        totp = pyotp.TOTP(secret)
        if totp.verify(token, valid_window=1):
            current_user.totp_secret = secret
            current_user.totp_enabled = True
            db.session.commit()
            flash('Two-factor authentication is now enabled!', 'success')
            return redirect(url_for('dashboard.index'))
        else:
            flash('Invalid code — please try again.', 'error')
            # Fall through to re-render with the same secret

    # Generate a new secret (GET) or reuse submitted secret on failed verify
    secret = request.form.get('secret') or pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    issuer = 'SmartSchool'
    label  = current_user.email
    uri    = totp.provisioning_uri(name=label, issuer_name=issuer)

    # Build QR code as base64 PNG
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render_template('auth/setup_2fa.html', secret=secret, qr_b64=qr_b64)


@auth_bp.route('/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    """Disable 2FA for the current user after confirming password."""
    password = request.form.get('password', '')
    if not current_user.check_password(password):
        flash('Incorrect password.', 'error')
        return redirect(url_for('auth.setup_2fa'))

    current_user.totp_secret  = None
    current_user.totp_enabled = False
    db.session.commit()
    flash('Two-factor authentication has been disabled.', 'warning')
    return redirect(url_for('dashboard.index'))


@auth_bp.route('/2fa/verify', methods=['GET', 'POST'])
def verify_2fa():
    """Step-2 of login: verify TOTP code."""
    pending_id = session.get('2fa_pending_user_id')
    if not pending_id:
        return redirect(url_for('auth.login'))

    user = User.query.get(pending_id)
    if not user:
        session.pop('2fa_pending_user_id', None)
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        import pyotp
        token = request.form.get('token', '').strip()
        totp  = pyotp.TOTP(user.totp_secret)

        if totp.verify(token, valid_window=1):
            session.pop('2fa_pending_user_id', None)
            login_user(user, remember=session.pop('2fa_remember', False))
            user.last_login = datetime.utcnow()
            db.session.commit()

            if user.role == UserRole.PARENT:
                return redirect(url_for('parent.dashboard'))
            if user.role == UserRole.SUPER_ADMIN:
                return redirect(url_for('saas_admin.dashboard'))
            return redirect(url_for('dashboard.index'))

        flash('Invalid or expired code. Please try again.', 'error')

    return render_template('auth/verify_2fa.html')
