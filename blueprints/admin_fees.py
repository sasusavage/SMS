"""
/admin/fees — school fee invoicing (school_admin). Fee structures, invoice
generation, invoice list/detail, record manual payment.

Parent online payment of an invoice lives in the portal + billing webhook;
see /portal and services/billing.complete_fee_payment.
"""
from decimal import Decimal

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g, abort,
)
from flask_login import login_required, current_user

from extensions import db
from auth.security import require_role
from services.tenant import tenant_query, get_tenant_or_404
from services.audit import log_action
from services import fees as feesvc
from services.fees import FeeError
from models.fees import FeeStructure, Invoice
from models.config_tables import Level, Term, Class
from models.operational import Student

fees_bp = Blueprint('admin_fees', __name__, url_prefix='/admin/fees')


@fees_bp.before_request
@login_required
@require_role('school_admin')
def _guard():
    if g.get('current_school_id') is None:
        abort(403)


def _sid():
    return g.current_school_id


@fees_bp.route('/')
def index():
    sid = _sid()
    structures = tenant_query(FeeStructure).order_by(FeeStructure.term_id).all()
    levels = {l.id: l.name for l in tenant_query(Level).all()}
    terms = {t.id: t.name for t in tenant_query(Term).all()}
    return render_template('admin/fees/index.html', structures=structures,
                           levels=levels, terms=terms,
                           all_levels=tenant_query(Level).order_by(Level.sequence).all(),
                           all_terms=tenant_query(Term).order_by(Term.sequence).all())


@fees_bp.route('/structures', methods=['POST'])
def create_structure():
    try:
        feesvc.create_fee_structure(
            _sid(), name=request.form.get('name'),
            term_id=_int(request.form.get('term_id')),
            amount=request.form.get('amount') or 0,
            level_id=_int(request.form.get('level_id')))
        log_action('create', 'fee_structure')
        db.session.commit()
        flash('Fee added.', 'success')
    except FeeError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_fees.index'))


@fees_bp.route('/structures/<int:fee_id>/delete', methods=['POST'])
def delete_structure(fee_id):
    try:
        feesvc.delete_fee_structure(_sid(), fee_id)
        log_action('delete', 'fee_structure', fee_id)
        db.session.commit()
        flash('Fee removed.', 'info')
    except FeeError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_fees.index'))


@fees_bp.route('/generate', methods=['GET', 'POST'])
def generate():
    sid = _sid()
    classes = tenant_query(Class).order_by(Class.name).all()
    terms = tenant_query(Term).order_by(Term.sequence).all()
    if request.method == 'POST':
        class_id = _int(request.form.get('class_id'))
        term_id = _int(request.form.get('term_id'))
        try:
            out = feesvc.generate_invoices(sid, class_id, term_id)
            log_action('generate_invoices', 'class', class_id,
                       meta={'term_id': term_id, **out})
            db.session.commit()
            flash(f'Generated {out["created"]} invoice(s) '
                  f'({out["skipped"]} already existed).', 'success')
        except FeeError as e:
            db.session.rollback()
            flash(e.message, 'danger')
        return redirect(url_for('admin_fees.invoices'))
    return render_template('admin/fees/generate.html', classes=classes,
                           terms=terms)


@fees_bp.route('/invoices')
def invoices():
    sid = _sid()
    term_id = _int(request.args.get('term_id'))
    q = tenant_query(Invoice)
    if term_id:
        q = q.filter_by(term_id=term_id)
    rows = q.order_by(Invoice.id.desc()).all()
    students = {s.id: s for s in tenant_query(Student).all()}
    terms = {t.id: t.name for t in tenant_query(Term).all()}
    # balances
    paid = {inv.id: feesvc.amount_paid(sid, inv.id) for inv in rows}
    return render_template('admin/fees/invoices.html', invoices=rows,
                           students=students, terms=terms, paid=paid,
                           all_terms=tenant_query(Term).order_by(Term.sequence).all(),
                           selected_term=term_id)


@fees_bp.route('/invoices/<int:invoice_id>', methods=['GET', 'POST'])
def invoice_detail(invoice_id):
    sid = _sid()
    invoice = get_tenant_or_404(Invoice, invoice_id)
    if request.method == 'POST':
        try:
            feesvc.record_payment(
                sid, invoice_id, request.form.get('amount') or 0,
                method=request.form.get('method') or 'cash',
                recorded_by=current_user.id)
            log_action('record_payment', 'invoice', invoice_id)
            db.session.commit()
            flash('Payment recorded.', 'success')
        except FeeError as e:
            db.session.rollback()
            flash(e.message, 'danger')
        return redirect(url_for('admin_fees.invoice_detail', invoice_id=invoice_id))

    student = db.session.get(Student, invoice.student_id)
    paid = feesvc.amount_paid(sid, invoice_id)
    bal = Decimal(str(invoice.total_amount)) - paid
    return render_template('admin/fees/invoice_detail.html', invoice=invoice,
                           student=student, paid=paid, balance=bal)


@fees_bp.route('/invoices/<int:invoice_id>/receipt')
def receipt(invoice_id):
    """Printable invoice/receipt. ?pdf=1 renders a PDF via WeasyPrint (with a
    graceful fallback to the printable HTML if WeasyPrint isn't available)."""
    from flask import Response, request as _req
    from models.platform import School
    sid = _sid()
    invoice = get_tenant_or_404(Invoice, invoice_id)
    student = db.session.get(Student, invoice.student_id)
    school = db.session.get(School, sid)
    paid = feesvc.amount_paid(sid, invoice_id)
    bal = Decimal(str(invoice.total_amount)) - paid
    term = db.session.get(Term, invoice.term_id)
    html = render_template('admin/fees/receipt.html', invoice=invoice,
                           student=student, school=school, paid=paid,
                           balance=bal, term=term, pdf=bool(_req.args.get('pdf')))
    if _req.args.get('pdf'):
        try:
            from weasyprint import HTML
            pdf = HTML(string=html, base_url=_req.url_root).write_pdf()
            return Response(pdf, mimetype='application/pdf', headers={
                'Content-Disposition':
                    f'inline; filename="receipt-{invoice.id}.pdf"'})
        except Exception:
            flash('PDF export is not enabled on this server. Use your browser\'s '
                  'Print → Save as PDF instead.', 'warning')
            return redirect(url_for('admin_fees.receipt', invoice_id=invoice_id))
    return html


def _int(v):
    try:
        return int(v) if v not in (None, '') else None
    except (TypeError, ValueError):
        return None
