"""
Notification Hub Service
Manages In-App notifications and SMS automated triggers.
"""
from models import (
    db, Notification, NotificationType, NotificationCategory,
    User, UserRole, Student, Parent, SchoolSetting
)
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

        if notify_type in [NotificationType.SMS, NotificationType.BOTH]:
            # Resolve the phone number for this user
            user = User.query.get(user_id)
            if user and user.role == UserRole.PARENT and user.parent_id:
                parent = Parent.query.get(user.parent_id)
                if parent:
                    phone = (parent.primary_contact_phone
                             or parent.father_phone
                             or parent.mother_phone)
                    if phone:
                        SMSProvider.send_sms(school_id, phone, message)
            elif user and user.staff_id:
                staff = user.staff_profile
                if staff and staff.phone:
                    SMSProvider.send_sms(school_id, staff.phone, message)

        return new_notif

    @staticmethod
    def trigger_attendance_alert(student_id, status_name, time=None):
        """Sends an instant arrival/absence SMS to the student's parent."""
        student = Student.query.get(student_id)
        if not student or not student.parent:
            return

        # Locate the parent's User account via the backref
        parent = student.parent
        parent_user = parent.user  # User.parent_profile backref (uselist=False)
        if not parent_user:
            return

        msg = f"Your ward, {student.first_name}, has been marked as '{status_name}'"
        msg += f" at {time}." if time else " today."

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
        """Sends a debt collection SMS/notification to the parent."""
        from models import FeeInvoice
        invoice = FeeInvoice.query.get(invoice_id)
        if not invoice or not invoice.student:
            return

        student = invoice.student
        if not student.parent or not student.parent.user:
            return

        parent_user = student.parent.user
        msg = (
            f"Fee Reminder: GHS {invoice.balance:,.2f} balance for your ward, "
            f"{student.first_name}, is outstanding for {invoice.term.name}. "
            f"Please settle to avoid disruption."
        )

        NotificationService.create_notification(
            school_id=invoice.school_id,
            user_id=parent_user.id,
            title="School Fee Statement",
            message=msg,
            category=NotificationCategory.FINANCE,
            notify_type=NotificationType.BOTH
        )
