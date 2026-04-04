"""
NaCCA Grading & Assessment Services
Handles calculation of scores, grades, and automated narrative comments.
"""
from models import db, Assessment, AuditLog, SubStrand
from datetime import datetime

class GradingService:
    
    @staticmethod
    def get_narrative_comment(total_score):
        """Generates automated NaCCA comments based on terminal performance."""
        if total_score >= 80:
            return "Exceptional performance! The student has exceeded the core competencies of the NaCCA standards. Keep up the high standard."
        elif total_score >= 70:
            return "Standard performance is excellent. Very proficient in the strands covered. Showing strong critical thinking skills."
        elif total_score >= 60:
            return "Good progress. Approaching full proficiency in most strands. Continued practice in sub-strands will solidify understanding."
        elif total_score >= 50:
            return "Fair performance. Showing a developing understanding of core concepts. More focus on remedial work in specific sub-strands is needed."
        else:
            return "Performance is currently emerging. Intensive support and additional strand-based exercises are required to bridge gaps."

    @staticmethod
    def record_assessment(school_id, user_id, data):
        """Records an assessment score with automated NaCCA metadata."""
        try:
            # 1. Standardize scores (COALESCE to 0)
            classwork = float(data.get('classwork_score', 0))
            homework = float(data.get('homework_score', 0))
            project = float(data.get('project_score', 0))
            exam = float(data.get('exam_score', 0))
            
            # 50/50 Weighting logic is already in the view, but we store raw components
            total = classwork + homework + project + exam
            
            # 2. Get automated comment
            narrative = GradingService.get_narrative_comment(total)
            
            # 3. Create assessment
            assessment = Assessment(
                school_id=school_id,
                student_id=data.get('student_id'),
                class_subject_id=data.get('class_subject_id'),
                term_id=data.get('term_id'),
                sub_strand_id=data.get('sub_strand_id'),
                classwork_score=classwork,
                homework_score=homework,
                project_score=project,
                exam_score=exam,
                total_score=total,
                narrative_comment=narrative,
                recorded_by_id=user_id
            )
            
            # 4. NaCCA Descriptors
            if total >= 80: assessment.grade_remark = "Highly Proficient"
            elif total >= 70: assessment.grade_remark = "Proficient"
            elif total >= 60: assessment.grade_remark = "Approaching Proficiency"
            elif total >= 50: assessment.grade_remark = "Developing"
            else: assessment.grade_remark = "Emerging"
            
            db.session.add(assessment)
            
            # 5. Audit Log
            log = AuditLog(
                school_id=school_id,
                user_id=user_id,
                action='RECORD_ASSESSMENT',
                entity_type='assessment',
                new_values={'total_score': total, 'student_id': data.get('student_id')}
            )
            db.session.add(log)
            
            db.session.commit()
            return assessment, None
            
        except Exception as e:
            db.session.rollback()
            return None, str(e)
