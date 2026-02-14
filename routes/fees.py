"""
Fees and Payments Management Routes
"""
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, g
from flask_login import login_required, current_user
from datetime import date, datetime
from decimal import Decimal

from models import (
    db, FeeCategory, FeeStructure, FeeInvoice, FeeInvoiceItem, Payment,
    Student, Class, ClassEnrollment, PaymentMethod, PaymentStatus
)
from app import accounts_required, admin_required

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
    
    # Get stats
    all_invoices = FeeInvoice.query.join(Student).filter(Student.school_id == current_user.school_id)
    if g.current_term:
        all_invoices = all_invoices.filter(FeeInvoice.term_id == g.current_term.id)
    
    total_expected = sum(float(inv.total_amount or 0) for inv in all_invoices.all())
    total_collected = sum(float(inv.amount_paid or 0) for inv in all_invoices.all())
    total_outstanding = sum(float(inv.balance or 0) for inv in all_invoices.all())
    
    classes = Class.query.filter_by(school_id=current_user.school_id, is_active=True).all()
    
    return render_template('fees/invoices.html', 
        invoices=invs,
        total_expected=total_expected,
        total_collected=total_collected,
        total_outstanding=total_outstanding,
        classes=classes
    )


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
