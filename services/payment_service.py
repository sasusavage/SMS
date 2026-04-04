"""
Financial & Payment Services
Handles Paystack webhooks, automated receipt triggers, and financial metrics.
"""
from models import db, Payment, FeeInvoice, PaymentStatus, AuditLog, Expense, PaymentMethod
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import func

class PaymentService:
    
    @staticmethod
    def handle_paystack_webhook(school_id, data):
        """Processes successful Paystack transaction data."""
        try:
            event = data.get('event')
            if event != 'charge.success':
                return False, f"Unsupported event: {event}"
            
            payload = data.get('data')
            reference = payload.get('reference')
            amount_kobo = payload.get('amount')
            amount_ghs = Decimal(amount_kobo) / 100
            
            # Metadata must contain student_id and invoice_id
            metadata = payload.get('metadata', {})
            student_id = metadata.get('student_id')
            invoice_id = metadata.get('invoice_id')
            user_id = metadata.get('user_id') # If payment initiated by a user
            
            if not student_id or not invoice_id:
                return False, "Missing student/invoice metadata."
            
            # 1. Update Invoice
            invoice = FeeInvoice.query.get(invoice_id)
            if not invoice or invoice.school_id != school_id:
                return False, "Invoice not found."
            
            # Prevent double processing
            existing_payment = Payment.query.filter_by(reference=reference).first()
            if existing_payment:
                return True, "Payment already recorded."
            
            # 2. Record Payment
            payment = Payment(
                school_id=school_id,
                invoice_id=invoice.id,
                amount=amount_ghs,
                payment_method=PaymentMethod.ONLINE,
                reference=reference,
                payer_name=payload.get('customer', {}).get('email'),
                payer_phone=payload.get('customer', {}).get('phone'),
                received_by_id=user_id,
                status=PaymentStatus.COMPLETED,
                notes=f"Paystack Ref: {reference}"
            )
            db.session.add(payment)
            
            # 3. Update Invoice Balance
            invoice.amount_paid += amount_ghs
            invoice.update_balance()
            
            # 4. Audit Log
            log = AuditLog(
                school_id=school_id,
                user_id=user_id,
                action='PAYSTACK_PAYMENT_SUCCESS',
                entity_type='payment',
                new_values={'amount': float(amount_ghs), 'reference': reference}
            )
            db.session.add(log)
            
            db.session.commit()
            
            # TODO: Trigger SMS Receipt here (Task 4)
            return True, None
            
        except Exception as e:
            db.session.rollback()
            return False, str(e)

    @staticmethod
    def get_finance_analytics(school_id, academic_year_id=None):
        """Calculates core financial KPIs for the dashboard."""
        try:
            # 1. Total Income (Completed Payments)
            income_query = db.session.query(func.sum(Payment.amount)).filter(
                Payment.school_id == school_id,
                Payment.status == PaymentStatus.COMPLETED
            )
            total_income = income_query.scalar() or Decimal('0.00')
            
            # 2. Total Expenses
            expense_query = db.session.query(func.sum(Expense.amount)).filter(
                Expense.school_id == school_id
            )
            total_expenses = expense_query.scalar() or Decimal('0.00')
            
            # 3. Outstanding Fees (Unpaid Balance)
            outstanding_query = db.session.query(func.sum(FeeInvoice.balance)).filter(
                FeeInvoice.school_id == school_id,
                FeeInvoice.status != PaymentStatus.COMPLETED
            )
            total_outstanding = outstanding_query.scalar() or Decimal('0.00')
            
            return {
                'total_income': total_income,
                'total_expenses': total_expenses,
                'outstanding_fees': total_outstanding,
                'net_balance': total_income - total_expenses
            }, None
        except Exception as e:
            return None, str(e)
