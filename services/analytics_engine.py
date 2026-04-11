from datetime import date, timedelta
from sqlalchemy import func
from models import db, School, Attendance, AttendanceStatus, Assessment, SchoolInsight, Class, Subject, ClassSubject

def run_midnight_analytics():
    """Scan all schools for academic and behavioral patterns."""
    schools = School.query.filter_by(is_active=True).all()
    for school in schools:
        generate_school_insights(school.id)

def generate_school_insights(school_id):
    """Detect outliers and save as insights for a specific school."""
    # Deactivate old insights to keep context fresh
    SchoolInsight.query.filter_by(school_id=school_id).update({"is_active": False})
    
    detect_attendance_outliers(school_id)
    detect_academic_outliers(school_id)
    
    db.session.commit()

def detect_attendance_outliers(school_id):
    """Find classes with attendance > 15% below school average."""
    today = date.today()
    last_week = today - timedelta(days=7)
    
    # 1. Get average attendance for the whole school this week
    avg_total = db.session.query(func.count(Attendance.id)).filter(
        Attendance.school_id == school_id,
        Attendance.date >= last_week,
        Attendance.status == AttendanceStatus.PRESENT
    ).scalar() or 0
    
    enrollment_total = db.session.query(func.count(Attendance.id)).filter(
        Attendance.school_id == school_id,
        Attendance.date >= last_week
    ).scalar() or 1
    
    school_avg_rate = (avg_total / enrollment_total) * 100
    
    # 2. Check each class
    classes = Class.query.filter_by(school_id=school_id).all()
    for cls in classes:
        cls_present = db.session.query(func.count(Attendance.id)).filter(
            Attendance.class_id == cls.id,
            Attendance.date >= last_week,
            Attendance.status == AttendanceStatus.PRESENT
        ).scalar() or 0
        
        cls_total = db.session.query(func.count(Attendance.id)).filter(
            Attendance.class_id == cls.id,
            Attendance.date >= last_week
        ).scalar() or 1
        
        cls_rate = (cls_present / cls_total) * 100
        
        if cls_rate < (school_avg_rate - 15):
            insight = SchoolInsight(
                school_id=school_id,
                type='attendance_drop',
                entity_name=cls.name,
                insight_text=f"Attendance in {cls.name} is {cls_rate:.1f}%, which is significantly below the school average of {school_avg_rate:.1f}%.",
                severity='high' if cls_rate < 50 else 'medium'
            )
            db.session.add(insight)

def detect_academic_outliers(school_id):
    """Identify subjects where the class average is below 50% (Developing/Emerging)."""
    # Using the last 30 days of assessments
    last_month = date.today() - timedelta(days=30)
    
    results = db.session.query(
        Class.name.label('class_name'),
        Subject.name.label('subject_name'),
        func.avg(
            Assessment.classwork_score + Assessment.homework_score +
            Assessment.project_score + Assessment.exam_score
        ).label('avg_score')
    ).join(ClassSubject, Assessment.class_subject_id == ClassSubject.id) \
     .join(Subject, ClassSubject.subject_id == Subject.id) \
     .join(Class, ClassSubject.class_id == Class.id) \
     .filter(
         Assessment.school_id == school_id,
         Assessment.created_at >= last_month
     ) \
     .group_by(Class.name, Subject.name).all()
     
    for res in results:
        if res.avg_score < 60: # Below "Approaching Proficiency"
            insight = SchoolInsight(
                school_id=school_id,
                type='grade_dip',
                entity_name=f"{res.class_name} - {res.subject_name}",
                insight_text=f"The average score for {res.subject_name} in {res.class_name} is {res.avg_score:.1f}. This signals a potential learning gap in this subject.",
                severity='high' if res.avg_score < 40 else 'medium'
            )
            db.session.add(insight)
