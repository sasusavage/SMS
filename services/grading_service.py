"""
NaCCA Grading & Assessment Service Layer
Centralizes all grading logic so routes stay thin.
"""
from flask import current_app
from models import db, Assessment, TerminalReport, ClassSubject, ClassEnrollment, AuditLog
from datetime import datetime


class GradingService:

    @staticmethod
    def get_narrative_comment(total_score):
        """Generates automated NaCCA narrative comments based on terminal performance."""
        if total_score >= 80:
            return ("Exceptional performance! The student has exceeded the core competencies "
                    "of the NaCCA standards. Keep up the high standard.")
        elif total_score >= 70:
            return ("Standard performance is excellent. Very proficient in the strands covered. "
                    "Showing strong critical thinking skills.")
        elif total_score >= 60:
            return ("Good progress. Approaching full proficiency in most strands. Continued "
                    "practice in sub-strands will solidify understanding.")
        elif total_score >= 50:
            return ("Fair performance. Showing a developing understanding of core concepts. "
                    "More focus on remedial work in specific sub-strands is needed.")
        else:
            return ("Performance is currently emerging. Intensive support and additional "
                    "strand-based exercises are required to bridge gaps.")

    @staticmethod
    def get_grade_remark(total_score):
        """Maps total score to NaCCA proficiency descriptor."""
        if total_score >= 80:
            return "Highly Proficient"
        elif total_score >= 70:
            return "Proficient"
        elif total_score >= 60:
            return "Approaching Proficiency"
        elif total_score >= 50:
            return "Developing"
        return "Emerging"

    @staticmethod
    def apply_grade(assessment, level='PRIMARY'):
        """
        Applies NaCCA grade and remark to an Assessment object in-place.
        Assumes assessment.total_score is already set.
        """
        grading_scale = current_app.config.get('NACCA_GRADING_SCALE', {}).get(level, {})

        assessment.grade_remark = GradingService.get_grade_remark(assessment.total_score)
        assessment.narrative_comment = GradingService.get_narrative_comment(assessment.total_score)

        for (min_score, max_score), (grade, _) in grading_scale.items():
            if min_score <= assessment.total_score <= max_score:
                assessment.grade = grade
                return

        assessment.grade = None

    @staticmethod
    def calculate_class_positions(class_subject_id, term_id):
        """
        Calculates per-subject class positions using dense ranking (ties share a rank).
        Updates Assessment.class_position in-place; caller must commit.
        """
        assessments = Assessment.query.filter_by(
            class_subject_id=class_subject_id,
            term_id=term_id
        ).order_by(Assessment.total_score.desc()).all()

        position = 1
        prev_score = None

        for i, assessment in enumerate(assessments):
            if prev_score is not None and assessment.total_score != prev_score:
                position = i + 1
            assessment.class_position = position
            prev_score = assessment.total_score

    @staticmethod
    def calculate_terminal_positions(class_id, term_id):
        """
        Calculates overall class positions for terminal reports.
        Updates TerminalReport.class_position in-place; caller must commit.
        """
        reports = TerminalReport.query.join(ClassEnrollment).filter(
            ClassEnrollment.class_id == class_id,
            TerminalReport.term_id == term_id
        ).order_by(TerminalReport.average_score.desc()).all()

        position = 1
        prev_score = None

        for i, report in enumerate(reports):
            if prev_score is not None and report.average_score != prev_score:
                position = i + 1
            report.class_position = position
            prev_score = report.average_score

    @staticmethod
    def record_assessment(school_id, user_id, data):
        """
        Records a single assessment score with automated NaCCA metadata.
        Returns (Assessment, error_string).
        """
        try:
            classwork = float(data.get('classwork_score', 0))
            homework = float(data.get('homework_score', 0))
            project = float(data.get('project_score', 0))
            exam = float(data.get('exam_score', 0))
            total = classwork + homework + project + exam

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
                recorded_by_id=user_id
            )
            GradingService.apply_grade(assessment, level=data.get('level', 'PRIMARY'))

            db.session.add(assessment)

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
