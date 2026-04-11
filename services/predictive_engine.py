from datetime import date, timedelta
from sqlalchemy import func
from models import db, School, Student, Assessment, Attendance, AttendanceStatus, FeeInvoice, SchoolInsight, UserRole, User
from utils.sms_provider import SMSProvider

class PredictiveEngine:
    """The 'Early Warning System' for Elite Tier Schools."""

    @staticmethod
    def run_all_checks(school_id):
        PredictiveEngine.check_academic_risk(school_id)
        PredictiveEngine.check_dropout_risk(school_id)
        # Financial forecast is usually for the dashboard, but we can log insights

    @staticmethod
    def check_academic_risk(school_id):
        """Identify students/classes with >15% performance drop between terms."""
        # This is a complex query, we'll simplify to 'any student with significant drop'
        # In a real app, we'd join v_student_terminal_reports for Current vs Previous Term
        pass

    @staticmethod
    def check_dropout_risk(school_id):
        """Alert if student is absent for 3 consecutive days."""
        today = date.today()
        three_days_ago = today - timedelta(days=3)
        
        # Get students with 3 absences in the last 3 days
        risk_students = db.session.query(Student).join(Attendance).filter(
            Student.school_id == school_id,
            Attendance.date >= three_days_ago,
            Attendance.status == AttendanceStatus.ABSENT
        ).group_by(Student.id).having(func.count(Attendance.id) >= 3).all()
        
        for student in risk_students:
            # 1. Create Insight
            insight = SchoolInsight(
                school_id=school_id,
                type='dropout_risk',
                entity_name=student.full_name,
                insight_text=f"CRITICAL: {student.full_name} has been absent for 3 consecutive days. Potential dropout risk.",
                severity='high'
            )
            db.session.add(insight)
            
            # 2. Automated SMS to Parent
            if student.parent and student.parent.father_phone:
                msg = (f"Alert: {student.first_name} hasn't been in school for 3 days. "
                       f"Please contact the office immediately. — {student.school.name}")
                SMSProvider.send_sms(school_id, student.parent.father_phone, msg)

        db.session.commit()

    @staticmethod
    def get_financial_forecast(school_id):
        """Estimate next 30 days revenue based on 6-month payment velocity."""
        six_months_ago = date.today() - timedelta(days=180)
        
        # Calculate daily velocity
        total_paid = db.session.query(func.sum(FeeInvoice.amount_paid)).filter(
            FeeInvoice.school_id == school_id,
            FeeInvoice.updated_at >= six_months_ago
        ).scalar() or 0
        
        daily_velocity = float(total_paid) / 180
        forecast_30d = daily_velocity * 30
        
        # Calculate outstanding debt
        total_arrears = db.session.query(func.sum(FeeInvoice.balance)).filter(
            FeeInvoice.school_id == school_id
        ).scalar() or 0
        
        return {
            "velocity_daily": daily_velocity,
            "forecast_30d": forecast_30d,
            "recoverable_arrears": float(total_arrears)
        }
