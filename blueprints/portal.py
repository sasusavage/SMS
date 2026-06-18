"""
/portal — student + parent self-service portals (Step 7).

Students see ONLY their own data; parents see ONLY their linked children; and
ONLY published results. All view authorisation goes through
services.portal.assert_can_view, which raises PortalError -> 404 (never leaks
existence). Tenant scope is the user's own school (g.current_school_id).
"""
from flask import (
    Blueprint, render_template, request, abort, g, redirect, url_for,
)
from flask_login import login_required, current_user

from auth.security import require_role
from services import portal
from services.portal import PortalError

portal_bp = Blueprint('portal', __name__, url_prefix='/portal')


@portal_bp.before_request
@login_required
@require_role('student', 'parent')
def _guard():
    if g.get('current_school_id') is None:
        abort(403)


def _sid():
    return g.current_school_id


# ---------------------------------------------------------------------------
# Student portal
# ---------------------------------------------------------------------------
@portal_bp.route('/student')
def student_home():
    student = portal.student_for_user(_sid(), current_user.id)
    if student is None:
        # A student-role login with no linked Student record.
        return render_template('portal/no_student.html')
    overview = portal.student_overview(_sid(), student)
    return render_template('portal/student_home.html', **overview)


@portal_bp.route('/student/report/<int:term_id>')
def student_report(term_id):
    student = portal.student_for_user(_sid(), current_user.id)
    if student is None:
        abort(404)
    return _render_report(student.id, term_id)


# ---------------------------------------------------------------------------
# Parent portal (children switcher)
# ---------------------------------------------------------------------------
@portal_bp.route('/parent')
def parent_home():
    children = portal.children_for_parent(_sid(), current_user.id)
    # Which child is selected (defaults to the first).
    student_id = request.args.get('student_id', type=int)
    selected = None
    overview = None
    if children:
        if student_id is not None:
            selected = next((c for c in children if c.id == student_id), None)
        if selected is None:
            selected = children[0]
        overview = portal.student_overview(_sid(), selected)
    return render_template('portal/parent_home.html', children=children,
                           selected=selected, overview=overview)


@portal_bp.route('/parent/report/<int:student_id>/<int:term_id>')
def parent_report(student_id, term_id):
    try:
        portal.assert_can_view(_sid(), current_user, student_id)
    except PortalError:
        abort(404)
    return _render_report(student_id, term_id)


# ---------------------------------------------------------------------------
# Fees — parent/student view + pay invoices online
# ---------------------------------------------------------------------------
@portal_bp.route('/fees/<int:student_id>')
def fees(student_id):
    from services import fees as feesvc
    from models.config_tables import Term
    try:
        student = portal.assert_can_view(_sid(), current_user, student_id)
    except PortalError:
        abort(404)
    invoices = feesvc.student_invoices(_sid(), student_id)
    terms = {t.id: t.name for t in Term.query.filter_by(school_id=_sid()).all()}
    balances = {inv.id: feesvc.balance(_sid(), inv) for inv in invoices}
    return render_template('portal/fees.html', student=student,
                           invoices=invoices, terms=terms, balances=balances)


@portal_bp.route('/fees/<int:student_id>/pay/<int:invoice_id>', methods=['POST'])
def pay_invoice(student_id, invoice_id):
    from services import billing
    from services.billing import BillingError
    try:
        portal.assert_can_view(_sid(), current_user, student_id)
    except PortalError:
        abort(404)
    email = (getattr(current_user, 'email', '') or '').strip()
    callback = url_for('billing.callback', _external=True)
    try:
        out = billing.start_fee_checkout(_sid(), invoice_id, email, callback)
        return redirect(out['url'])
    except BillingError as e:
        flash(e.message, 'danger')
        return redirect(url_for('portal.fees', student_id=student_id))


# ---------------------------------------------------------------------------
# Shared report card render (published only)
# ---------------------------------------------------------------------------
def _render_report(student_id, term_id):
    # Re-check authorisation (defence in depth) and gather published data.
    try:
        portal.assert_can_view(_sid(), current_user, student_id)
    except PortalError:
        abort(404)
    from services.report_card import ReportError
    try:
        data = portal.report_card_published(_sid(), student_id, term_id)
    except ReportError:
        abort(404)
    # If nothing is published for this term, don't show a blank card.
    if not data['published']:
        abort(404)
    return render_template('reports/report_card.html', pdf=False, **data)
