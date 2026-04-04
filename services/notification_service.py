"""
Notification Hub Service
Manages In-App notifications and SMS automated triggers.
"""
from models import db, Notification, NotificationType, NotificationCategory, User, Student, Parent, SchoolSetting
from utils.sms_provider import SMSProvider
from datetime import datetime

class NotificationService:
    
    @staticmethod
    def create_notification(school_id, user_id, title, message, 
                            category=NotificationCategory.GENERAL, 
                            notify_type=NotificationType.SYSTEM):
        """Creates an in-app notification and optionally sends an SMS."""
        new_notif = Notification(
            school_id=school_id,
            user_id=user_id,
            title=title,
            message=message,
            type=notify_type,
            category=category
        )
        db.session.add(new_notif)
        db.session.commit()
        
        # Trigger SMS if requested
        if notify_type in [NotificationType.SMS, NotificationType.BOTH]:
            user = User.query.get(user_id)
            if user and user.phone:
                SMSProvider.send_sms(school_id, user.phone, message)
            elif user and user.role == "parent":
                # If we have parent role, check father/mother phone
                parent = Parent.query.filter_by(user_id=user_id).first()
                if parent:
                    # Prefer father's phone or mother's
                    phone = parent.father_phone or parent.mother_phone
                    if phone:
                        SMSProvider.send_sms(school_id, phone, message)

        return new_notif

    @staticmethod
    def trigger_attendance_alert(student_id, status_name, time=None):
        """Sends an instant arrival/absence SMS to the parent."""
        student = Student.query.get(student_id)
        if not student or not student.parent:
            return
            
        parent_user = User.query.filter_by(id=student.parent.user_id).first()
        if not parent_user:
            return
            
        msg = f"Your ward, {student.first_name}, has been marked as '{status_name}'"
        if time:
            msg += f" at {time}."
        else:
            msg += f" today."
            
        NotificationService.create_notification(
            school_id=student.school_id,
            user_id=parent_user.id,
            title=f"Attendance Alert: {student.first_name}",
            message=msg,
            category=NotificationCategory.ATTENDANCE,
            notify_type=NotificationType.BOTH
        )

    @staticmethod
    def trigger_fee_reminder(invoice_id):
        """Sends a debt collection SMS to the parent."""
        from models import FeeInvoice
        invoice = FeeInvoice.query.get(invoice_id)
        if not invoice or not invoice.student:
            return
            
        student = invoice.student
        parent_user = User.query.filter_by(id=student.parent.user_id).first() if student.parent else None
        if not parent_user:
            return
            
        msg = f"Fee Reminder: GHS {invoice.balance:,.2f} balance for your ward, {student.first_name}, is outstanding for {invoice.term.name}. Keep balance paid to avoid disruptions."
        
        NotificationService.create_notification(
            school_id=invoice.school_id,
            user_id=parent_user.id,
            title="School Fee Statement",
            message=msg,
            category=NotificationCategory.FINANCE,
            notify_type=NotificationType.BOTH
        )
