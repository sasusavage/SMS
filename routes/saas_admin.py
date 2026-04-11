"""
SaaS Admin Routes — Platform Owner Only
Handles the global SmartSchool control panel.
Only accessible to UserRole.SUPER_ADMIN.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from models import db, UserRole, Student, StudentStatus, Payment, PaymentStatus, School, AICreditUsage, AuditLog, AISession, ModuleConfig

saas_admin_bp = Blueprint('saas_admin', __name__, url_prefix='/saas-admin')


def _require_super_admin():
    """Returns a redirect response if the current user is not SUPER_ADMIN, else None."""
    if current_user.role != UserRole.SUPER_ADMIN:
        flash('Unauthorized. Platform Owner access only.', 'error')
        return redirect(url_for('dashboard.index'))
    return None


@saas_admin_bp.route('/')
@saas_admin_bp.route('/dashboard')
@login_required
def dashboard():
    """Global SaaS platform control panel."""
    guard = _require_super_admin()
    if guard:
        return guard

    stats = {
        'total_schools': School.query.count(),
        'active_students': Student.query.filter_by(status=StudentStatus.ACTIVE).count(),
        'platform_total_revenue': db.session.query(func.sum(Payment.amount)).filter(
            Payment.status == PaymentStatus.COMPLETED
        ).scalar() or 0,
        'remaining_sms_credits': 12500,
        'ai_tokens_today': db.session.query(func.sum(AICreditUsage.tokens_used)).scalar() or 0,
        'system_health': '99.9%'
    }

    ai_top_consumers = db.session.query(
        School.name,
        func.sum(AICreditUsage.tokens_used)
    ).join(AICreditUsage).group_by(School.name).all()

    schools_full = School.query.order_by(School.name).all()

    return render_template('dashboard/super_admin.html',
        stats=stats,
        ai_usage=ai_top_consumers,
        schools_full=schools_full
    )


@saas_admin_bp.route('/onboard', methods=['POST'])
@login_required
def onboard_school():
    """Quick onboarding for new school tenants."""
    guard = _require_super_admin()
    if guard:
        return guard

    name = request.form.get('name')
    email = request.form.get('email')
    school_type = request.form.get('school_type', 'Private')

    if not name or not email:
        flash('School Name and Email are required.', 'error')
        return redirect(url_for('saas_admin.dashboard'))

    new_school = School(name=name, email=email, school_type=school_type, is_active=True)
    db.session.add(new_school)
    db.session.flush()

    config = ModuleConfig(
        school_id=new_school.id,
        is_ai_enabled=True,
        is_sms_enabled=True,
        is_finance_enabled=True
    )
    db.session.add(config)
    db.session.commit()

    flash(f'School "{name}" onboarded successfully! Elite Tier modules initialized.', 'success')
    return redirect(url_for('saas_admin.dashboard'))


@saas_admin_bp.route('/audit-logs')
@login_required
def audit_logs():
    """Platform-wide security ledger."""
    guard = _require_super_admin()
    if guard:
        return guard

    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template('admin/audit_logs.html', logs=logs)


@saas_admin_bp.route('/ai-conversations')
@login_required
def ai_conversations():
    """Audit AI chats across all schools."""
    guard = _require_super_admin()
    if guard:
        return guard

    sessions = AISession.query.order_by(AISession.last_interaction.desc()).limit(100).all()
    stats = {'total_chats': AISession.query.count()}
    return render_template('admin/ai_conversations.html', sessions=sessions, stats=stats)


@saas_admin_bp.route('/toggle-module/<int:school_id>/<string:module_field>', methods=['POST'])
@login_required
def toggle_module(school_id, module_field):
    """Toggle Elite Tier modules for a specific school."""
    if current_user.role != UserRole.SUPER_ADMIN:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    config = ModuleConfig.query.filter_by(school_id=school_id).first()
    if not config:
        config = ModuleConfig(school_id=school_id)
        db.session.add(config)

    current_val = getattr(config, module_field, False)
    setattr(config, module_field, not current_val)
    db.session.commit()

    return jsonify({'success': True, 'new_state': not current_val})


@saas_admin_bp.route('/suspend/<int:school_id>', methods=['POST'])
@login_required
def suspend_school(school_id):
    """Suspend a school's access."""
    guard = _require_super_admin()
    if guard:
        return guard

    school = School.query.get_or_404(school_id)
    reason = request.form.get('reason', 'Suspended by platform administrator.')
    school.is_account_suspended = True
    school.suspension_reason = reason
    db.session.commit()
    flash(f'"{school.name}" has been suspended.', 'warning')
    return redirect(url_for('saas_admin.dashboard'))


@saas_admin_bp.route('/reinstate/<int:school_id>', methods=['POST'])
@login_required
def reinstate_school(school_id):
    """Reinstate a suspended school."""
    guard = _require_super_admin()
    if guard:
        return guard

    school = School.query.get_or_404(school_id)
    school.is_account_suspended = False
    school.suspension_reason = None
    db.session.commit()
    flash(f'"{school.name}" has been reinstated.', 'success')
    return redirect(url_for('saas_admin.dashboard'))
