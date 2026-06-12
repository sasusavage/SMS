"""
Tenant configuration tables — ALL carry school_id (via TenantMixin).

This is where the Configuration-over-Code principle lives: academic structure,
calendar, grading schemes, assessment composition and report options are all
rows here, defined per school. No curriculum constants in code.
"""
from sqlalchemy import (
    Integer, String, Boolean, Date, Numeric, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import mapped_column, relationship

from extensions import db
from models.mixins import TenantMixin


class AcademicYear(db.Model, TenantMixin):
    __tablename__ = 'academic_years'
    __table_args__ = (
        UniqueConstraint('school_id', 'name', name='uq_academic_year_name'),
    )

    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(50), nullable=False)  # "2025/2026"
    start_date = mapped_column(Date)
    end_date = mapped_column(Date)
    is_current = mapped_column(Boolean, default=False, nullable=False)

    terms = relationship('Term', back_populates='academic_year',
                         cascade='all, delete-orphan')


class Term(db.Model, TenantMixin):
    """Configurable count per school: 2 semesters, 3 terms, whatever."""
    __tablename__ = 'terms'
    __table_args__ = (
        UniqueConstraint('school_id', 'academic_year_id', 'sequence',
                         name='uq_term_sequence'),
    )

    id = mapped_column(Integer, primary_key=True)
    academic_year_id = mapped_column(
        Integer, ForeignKey('academic_years.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    name = mapped_column(String(50), nullable=False)  # "Term 1" / "Michaelmas"
    sequence = mapped_column(Integer, nullable=False)
    start_date = mapped_column(Date)
    end_date = mapped_column(Date)
    is_current = mapped_column(Boolean, default=False, nullable=False)

    academic_year = relationship('AcademicYear', back_populates='terms')


class LevelGroup(db.Model, TenantMixin):
    """e.g. "Primary", "JHS", "Lower Secondary", "Sixth Form"."""
    __tablename__ = 'level_groups'
    __table_args__ = (
        UniqueConstraint('school_id', 'name', name='uq_level_group_name'),
    )

    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(100), nullable=False)
    sequence = mapped_column(Integer, nullable=False, default=0)

    levels = relationship('Level', back_populates='level_group',
                          cascade='all, delete-orphan')


class Level(db.Model, TenantMixin):
    """e.g. "Basic 4", "Year 7", "IGCSE Year 1"."""
    __tablename__ = 'levels'
    __table_args__ = (
        UniqueConstraint('school_id', 'name', name='uq_level_name'),
    )

    id = mapped_column(Integer, primary_key=True)
    level_group_id = mapped_column(
        Integer, ForeignKey('level_groups.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    name = mapped_column(String(100), nullable=False)
    sequence = mapped_column(Integer, nullable=False, default=0)

    level_group = relationship('LevelGroup', back_populates='levels')
    classes = relationship('Class', back_populates='level',
                           cascade='all, delete-orphan')
    level_subjects = relationship('LevelSubject', back_populates='level',
                                  cascade='all, delete-orphan')


class Class(db.Model, TenantMixin):
    """Actual class/stream, e.g. "Basic 4 Gold", "Year 7B"."""
    __tablename__ = 'classes'
    __table_args__ = (
        UniqueConstraint('school_id', 'level_id', 'academic_year_id', 'name',
                         name='uq_class_name'),
    )

    id = mapped_column(Integer, primary_key=True)
    level_id = mapped_column(
        Integer, ForeignKey('levels.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    academic_year_id = mapped_column(
        Integer, ForeignKey('academic_years.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    name = mapped_column(String(100), nullable=False)
    class_teacher_id = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True,
    )

    level = relationship('Level', back_populates='classes')
    class_teacher = relationship('User', foreign_keys=[class_teacher_id])


class Subject(db.Model, TenantMixin):
    __tablename__ = 'subjects'
    __table_args__ = (
        UniqueConstraint('school_id', 'code', name='uq_subject_code'),
    )

    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(100), nullable=False)
    code = mapped_column(String(30))
    is_core = mapped_column(Boolean, default=True, nullable=False)

    level_subjects = relationship('LevelSubject', back_populates='subject',
                                  cascade='all, delete-orphan')


class LevelSubject(db.Model, TenantMixin):
    """Which subjects are offered at which level."""
    __tablename__ = 'level_subjects'
    __table_args__ = (
        UniqueConstraint('school_id', 'level_id', 'subject_id',
                         name='uq_level_subject'),
    )

    id = mapped_column(Integer, primary_key=True)
    level_id = mapped_column(
        Integer, ForeignKey('levels.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    subject_id = mapped_column(
        Integer, ForeignKey('subjects.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )

    level = relationship('Level', back_populates='level_subjects')
    subject = relationship('Subject', back_populates='level_subjects')


class GradingScheme(db.Model, TenantMixin):
    __tablename__ = 'grading_schemes'
    __table_args__ = (
        UniqueConstraint('school_id', 'name', name='uq_grading_scheme_name'),
    )

    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(100), nullable=False)  # "BECE Style"
    is_default = mapped_column(Boolean, default=False, nullable=False)

    boundaries = relationship('GradeBoundary', back_populates='scheme',
                              cascade='all, delete-orphan')


class GradeBoundary(db.Model, TenantMixin):
    """
    One band within a grading scheme. Non-overlap within a scheme is validated
    in the service layer (Step 2), not by a DB constraint.
    """
    __tablename__ = 'grade_boundaries'

    id = mapped_column(Integer, primary_key=True)
    grading_scheme_id = mapped_column(
        Integer, ForeignKey('grading_schemes.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    min_score = mapped_column(Numeric(5, 2), nullable=False)  # 80.00
    max_score = mapped_column(Numeric(5, 2), nullable=False)  # 100.00
    grade_label = mapped_column(String(20), nullable=False)   # "A1", "A*"
    remark = mapped_column(String(100))                       # "Excellent"
    grade_point = mapped_column(Numeric(4, 2))                # nullable
    is_pass = mapped_column(Boolean, default=True, nullable=False)

    scheme = relationship('GradingScheme', back_populates='boundaries')


class AssessmentComponent(db.Model, TenantMixin):
    """
    How a final score is composed per school, e.g. Class Score 40% + Exam 60%.
    Weights per level_group must sum to 100 — validated in the service layer.
    """
    __tablename__ = 'assessment_components'

    id = mapped_column(Integer, primary_key=True)
    name = mapped_column(String(100), nullable=False)  # "Class Score"
    weight_percent = mapped_column(Numeric(5, 2), nullable=False)
    # null = applies to all level groups
    applies_to_level_group_id = mapped_column(
        Integer, ForeignKey('level_groups.id', ondelete='CASCADE'),
        nullable=True, index=True,
    )

    applies_to_level_group = relationship('LevelGroup')


class ReportSettings(db.Model, TenantMixin):
    """Per-school report card options (one row per school)."""
    __tablename__ = 'report_settings'
    __table_args__ = (
        UniqueConstraint('school_id', name='uq_report_settings_school'),
    )

    id = mapped_column(Integer, primary_key=True)
    show_class_position = mapped_column(Boolean, default=True, nullable=False)
    show_grade_point = mapped_column(Boolean, default=False, nullable=False)
    show_skills_ratings = mapped_column(Boolean, default=False, nullable=False)
    teacher_comment_required = mapped_column(Boolean, default=True,
                                             nullable=False)
    head_comment_required = mapped_column(Boolean, default=True, nullable=False)
    next_term_begins_label = mapped_column(String(255))
