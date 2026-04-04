"""
Fees and Payments Management Routes
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, g
from flask_login import login_required, current_user
from datetime import date, datetime
from decimal import Decimal

from models import (
    db, FeeCategory, FeeStructure, FeeInvoice, FeeInvoiceItem, Payment,
    Student, Class, ClassEnrollment, PaymentMethod, PaymentStatus, Expense
)
from app import accounts_required, admin_required
from services.payment_service import PaymentService

fees_bp = Blueprint('fees', __name__, url_prefix='/fees')


@fees_bp.route('/categories')
@accounts_required
def categories():
    cats = FeeCategory.query.filter_by(school_id=current_user.school_id, is_active=True).all()
    return render_template('fees/categories.html', categories=cats)


@fees_bp.route('/categories/add', methods=['POST'])
@admin_required
def add_category():
    cat = FeeCategory(
        school_id=current_user.school_id,
        name=request.form.get('name'),
        description=request.form.get('description'),
        is_recurring=request.form.get('is_recurring') == 'true',
        is_active=True
    )
    db.session.add(cat)
    db.session.commit()
    flash(f'Fee category "{cat.name}" added!', 'success')
    return redirect(url_for('fees.categories'))


@fees_bp.route('/structure')
@accounts_required
def structure():
    classes = Class.query.filter_by(school_id=current_user.school_id, is_active=True).all()
    cats = FeeCategory.query.filter_by(school_id=current_user.school_id, is_active=True).all()
    return render_template('fees/structure.html', classes=classes, categories=cats)


@fees_bp.route('/invoices')
@accounts_required
def invoices():
    page = request.args.get('page', 1, type=int)
    query = FeeInvoice.query.join(Student).filter(Student.school_id == current_user.school_id)
    if g.current_term:
        query = query.filter(FeeInvoice.term_id == g.current_term.id)
    invs = query.order_by(FeeInvoice.created_at.desc()).paginate(page=page, per_page=25)
    
    # Use PaymentService for metrics
    metrics, _ = PaymentService.get_finance_analytics(current_user.school_id)
    
    return render_template('fees/invoices.html', 
        invoices=invs,
        metrics=metrics,
        classes=classes
    )


# --- EXPENSES ---
@fees_bp.route('/expenses')
@accounts_required
def expenses():
    page = request.args.get('page', 1, type=int)
    exps = Expense.query.filter_by(school_id=current_user.school_id)\
        .order_by(Expense.expense_date.desc()).paginate(page=page, per_page=25)
    
    metrics, _ = PaymentService.get_finance_analytics(current_user.school_id)
    return render_template('fees/expenses.html', expenses=exps, metrics=metrics)


@fees_bp.route('/expenses/add', methods=['GET', 'POST'])
@accounts_required
def add_expense():
    if request.method == 'POST':
        exp = Expense(
            school_id=current_user.school_id,
            category=request.form.get('category'),
            amount=Decimal(request.form.get('amount', '0')),
            description=request.form.get('description'),
            expense_date=datetime.strptime(request.form.get('date'), '%Y-%m-%d').date(),
            recorded_by_id=current_user.id
        )
        db.session.add(exp)
        db.session.commit()
        flash('Expense recorded successfully!', 'success')
        return redirect(url_for('fees.expenses'))
    
    categories = ['Salary', 'Utilities', 'Stationery', 'Fuel', 'Maintenance', 'Canteen', 'Other']
    return render_template('fees/add_expense.html', categories=categories, today_date=date.today().isoformat())


@fees_bp.route('/invoices/<int:id>')
@accounts_required
def view_invoice(id):
    inv = FeeInvoice.query.get_or_404(id)
    return render_template('fees/view_invoice.html', invoice=inv)


@fees_bp.route('/payments')
@accounts_required
def payments():
    page = request.args.get('page', 1, type=int)
    query = Payment.query.join(FeeInvoice).join(Student).filter(Student.school_id == current_user.school_id)
    pays = query.order_by(Payment.payment_date.desc()).paginate(page=page, per_page=25)
    return render_template('fees/payments.html', payments=pays)


@fees_bp.route('/payments/record', methods=['GET', 'POST'])
@accounts_required
def record_payment():
    if request.method == 'POST':
        inv_id = request.form.get('invoice_id', type=int)
        inv = FeeInvoice.query.get_or_404(inv_id)
        if inv.student.school_id != current_user.school_id:
            flash('Access denied.', 'error')
            return redirect(url_for('fees.payments'))
            
        amt = Decimal(request.form.get('amount', '0'))
        
        if amt <= 0 or amt > inv.balance:
            flash('Invalid amount.', 'error')
            return redirect(url_for('fees.record_payment'))
        
        count = Payment.query.count()
        rcpt = f"RCT-{datetime.now().strftime('%Y%m%d')}-{count + 1:04d}"
        
        pay = Payment(
            receipt_number=rcpt, invoice_id=inv.id, amount=amt,
            payment_method=PaymentMethod(request.form.get('payment_method')),
            payment_date=datetime.now(), 
            payer_name=request.form.get('payer_name'),
            status=PaymentStatus.COMPLETED, received_by_id=current_user.id
        )
        db.session.add(pay)
        inv.amount_paid += amt
        inv.update_balance()
        db.session.commit()
        flash(f'Payment recorded!', 'success')
        return redirect(url_for('fees.view_invoice', id=inv.id))
    
    return render_template('fees/record_payment.html', payment_methods=PaymentMethod)


@fees_bp.route('/invoices/<int:id>/remind')
@accounts_required
def send_reminder(id):
    """Sends a fee reminder SMS to the parent."""
    from services.notification_service import NotificationService
    NotificationService.trigger_fee_reminder(id)
    flash('Fee reminder SMS sent successfully!', 'success')
    return redirect(request.referrer or url_for('fees.invoices'))

@fees_bp.route('/payments/<int:id>/delete', methods=['POST'])
@admin_required
def delete_payment(id):
    """Deletes a payment record and reconciles the invoice balance."""
    from models import AuditLog
    pay = Payment.query.get_or_404(id)
    inv = pay.invoice
    
    if pay.school_id != current_user.school_id:
        flash('Access denied.', 'error')
        return redirect(url_for('fees.payments'))
        
    old_amount = float(pay.amount)
    ref = pay.reference or pay.receipt_number
    
    # 1. Audit Log
    log = AuditLog(
        school_id=current_user.school_id,
        user_id=current_user.id,
        action='DELETE_PAYMENT',
        entity_type='payment',
        entity_id=pay.id,
        old_values={'amount': old_amount, 'reference': ref}
    )
    db.session.add(log)
    
    # 2. Reconcile Invoice
    inv.amount_paid -= Decimal(str(old_amount))
    inv.update_balance()
    
    # 3. Delete Payment
    db.session.delete(pay)
    db.session.commit()
    
    flash('Payment deleted and invoice balance reconciled.', 'warning')
    return redirect(url_for('fees.payments'))

@fees_bp.route('/debtors')
@accounts_required
def debtors():
    if not g.current_term:
        return redirect(url_for('fees.invoices'))
    debs = FeeInvoice.query.join(Student).filter(
        Student.school_id == current_user.school_id,
        FeeInvoice.term_id == g.current_term.id,
        FeeInvoice.balance > 0
    ).order_by(FeeInvoice.balance.desc()).all()
    return render_template('fees/debtors.html', debtors=debs, total_debt=sum(float(d.balance) for d in debs))
