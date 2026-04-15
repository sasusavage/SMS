"""
SaaS Admin Routes — Platform Owner Only
Handles the global SmartSchool control panel.
Only accessible to UserRole.SUPER_ADMIN.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
from sqlalchemy import func
from models import db, UserRole, Student, StudentStatus, Payment, PaymentStatus, School, AICreditUsage, AuditLog, AISession, ModuleConfig, SubscriptionPlan, Subscription

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
    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.price).all()

    # Per-school student counts
    student_counts = dict(
        db.session.query(Student.school_id, func.count(Student.id))
        .filter(Student.status == StudentStatus.ACTIVE)
        .group_by(Student.school_id)
        .all()
    )

    return render_template('dashboard/super_admin.html',
        stats=stats,
        ai_usage=ai_top_consumers,
        schools_full=schools_full,
        plans=plans,
        student_counts=student_counts,
    )


@saas_admin_bp.route('/onboard', methods=['POST'])
@login_required
def onboard_school():
    """Quick onboarding for new school tenants."""
    guard = _require_super_admin()
    if guard:
        return guard

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    school_type = request.form.get('school_type', 'Private')
    plan_id = request.form.get('plan_id', type=int)
    city = request.form.get('city', '').strip() or None
    region = request.form.get('region', '').strip() or None
    phone = request.form.get('phone', '').strip() or None

    if not name or not email:
        flash('School Name and Email are required.', 'error')
        return redirect(request.referrer or url_for('saas_admin.dashboard'))

    new_school = School(name=name, email=email, school_type=school_type,
                        city=city, region=region, phone=phone, is_active=True)
    db.session.add(new_school)
    db.session.flush()

    config = ModuleConfig(
        school_id=new_school.id,
        is_ai_enabled=True,
        is_sms_enabled=True,
        is_finance_enabled=True
    )
    db.session.add(config)

    if plan_id:
        from datetime import date
        sub = Subscription(school_id=new_school.id, plan_id=plan_id, status='active',
                           end_date=date.today().replace(year=date.today().year + 1))
        db.session.add(sub)

    db.session.commit()

    flash(f'School "{name}" onboarded successfully!', 'success')
    return redirect(url_for('saas_admin.schools_list'))


@saas_admin_bp.route('/schools')
@login_required
def schools_list():
    """Full paginated list of all schools with search."""
    guard = _require_super_admin()
    if guard:
        return guard

    q = request.args.get('q', '').strip()
    query = School.query
    if q:
        query = query.filter(School.name.ilike(f'%{q}%'))
    schools = query.order_by(School.name).all()
    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.price).all()
    student_counts = dict(
        db.session.query(Student.school_id, func.count(Student.id))
        .filter(Student.status == StudentStatus.ACTIVE)
        .group_by(Student.school_id).all()
    )
    return render_template('saas_admin/schools_list.html',
        schools=schools, plans=plans, student_counts=student_counts, q=q)


@saas_admin_bp.route('/revenue')
@login_required
def revenue():
    """Platform revenue breakdown per school and per plan."""
    guard = _require_super_admin()
    if guard:
        return guard

    # Revenue per school
    school_revenue = db.session.query(
        School.name,
        func.coalesce(func.sum(Payment.amount), 0).label('total')
    ).outerjoin(Payment, Payment.school_id == School.id) \
     .filter((Payment.status == PaymentStatus.COMPLETED) | (Payment.id == None)) \
     .group_by(School.id, School.name) \
     .order_by(func.sum(Payment.amount).desc().nullslast()) \
     .all()

    # Revenue per plan
    plan_revenue = db.session.query(
        SubscriptionPlan.name,
        func.count(Subscription.id).label('schools'),
        func.coalesce(func.sum(SubscriptionPlan.price), 0).label('arr')
    ).outerjoin(Subscription, Subscription.plan_id == SubscriptionPlan.id) \
     .filter((Subscription.status == 'active') | (Subscription.id == None)) \
     .group_by(SubscriptionPlan.id, SubscriptionPlan.name, SubscriptionPlan.price) \
     .all()

    total_revenue = db.session.query(func.sum(Payment.amount)).filter(
        Payment.status == PaymentStatus.COMPLETED).scalar() or 0
    total_arr = sum(r.arr for r in plan_revenue)

    return render_template('saas_admin/revenue.html',
        school_revenue=school_revenue, plan_revenue=plan_revenue,
        total_revenue=total_revenue, total_arr=total_arr)


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


@saas_admin_bp.route('/school/<int:school_id>')
@login_required
def school_detail(school_id):
    """Per-school detail view — users, students, subscription, modules."""
    guard = _require_super_admin()
    if guard:
        return guard

    from models import User, AcademicYear
    school = School.query.get_or_404(school_id)
    users = User.query.filter_by(school_id=school_id).order_by(User.role).all()
    student_count = Student.query.filter_by(school_id=school_id, status=StudentStatus.ACTIVE).count()
    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.price).all()
    ai_tokens = db.session.query(func.sum(AICreditUsage.tokens_used)).filter_by(school_id=school_id).scalar() or 0
    recent_logs = AuditLog.query.filter_by(school_id=school_id).order_by(AuditLog.timestamp.desc()).limit(20).all()
    return render_template('saas_admin/school_detail.html',
        school=school, users=users, student_count=student_count,
        plans=plans, ai_tokens=ai_tokens, recent_logs=recent_logs)


@saas_admin_bp.route('/assign-plan/<int:school_id>', methods=['POST'])
@login_required
def assign_plan(school_id):
    """Change or assign a subscription plan for a school."""
    guard = _require_super_admin()
    if guard:
        return guard

    from datetime import date
    plan_id = request.form.get('plan_id', type=int)
    if not plan_id:
        flash('No plan selected.', 'error')
        return redirect(url_for('saas_admin.school_detail', school_id=school_id))

    plan = SubscriptionPlan.query.get_or_404(plan_id)
    sub = Subscription.query.filter_by(school_id=school_id).first()
    if sub:
        sub.plan_id = plan_id
        sub.status = 'active'
        sub.end_date = date.today().replace(year=date.today().year + 1)
    else:
        sub = Subscription(school_id=school_id, plan_id=plan_id, status='active',
                           end_date=date.today().replace(year=date.today().year + 1))
        db.session.add(sub)
    db.session.commit()
    flash(f'Plan updated to {plan.name}.', 'success')
    return redirect(url_for('saas_admin.school_detail', school_id=school_id))


# =============================================================================
# IMPERSONATION — Enter any school as its headteacher (no password needed)
# =============================================================================

@saas_admin_bp.route('/enter-school/<int:school_id>', methods=['POST'])
@login_required
def enter_school(school_id):
    """Super Admin enters a school's dashboard context without a password."""
    guard = _require_super_admin()
    if guard:
        return guard

    from models import User
    school = School.query.get_or_404(school_id)

    # Find the headteacher or first admin of the school
    from models import UserRole as UR
    staff_user = (
        User.query.filter_by(school_id=school_id, role=UR.HEADTEACHER, is_active=True).first()
        or User.query.filter_by(school_id=school_id, role=UR.ADMIN, is_active=True).first()
        or User.query.filter_by(school_id=school_id, is_active=True).first()
    )

    if not staff_user:
        flash(f'No active users found in {school.name}.', 'error')
        return redirect(url_for('saas_admin.school_detail', school_id=school_id))

    # Save the super admin's real user id so we can exit later
    session['impersonating_school_id'] = school_id
    session['impersonating_school_name'] = school.name
    session['real_user_id'] = current_user.id

    from flask_login import login_user
    login_user(staff_user)
    flash(f'You are now viewing {school.name} as {staff_user.role.value}. Click "Exit School" to return.', 'info')
    return redirect(url_for('dashboard.index'))


@saas_admin_bp.route('/exit-school')
def exit_school():
    """Return from impersonation back to the Super Admin account."""
    real_user_id = session.pop('real_user_id', None)
    session.pop('impersonating_school_id', None)
    session.pop('impersonating_school_name', None)

    if real_user_id:
        from models import User
        from flask_login import login_user
        real_user = User.query.get(real_user_id)
        if real_user:
            login_user(real_user)
            flash('You have exited the school and returned to your Super Admin account.', 'success')
            return redirect(url_for('saas_admin.dashboard'))

    # Fallback — just logout
    from flask_login import logout_user
    logout_user()
    return redirect(url_for('auth.login'))
