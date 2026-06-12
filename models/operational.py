"""
Tenant operational tables — ALL carry school_id (via TenantMixin), except
audit_logs whose school_id is nullable (platform-level actions have none).

`User` is the Flask-Login identity for in-school accounts. Super admins are a
SEPARATE table (platform_users) and are NOT represented here — that keeps the
cross-tenant boundary clean: a row in `users` always belongs to exactly one
school.
"""
from sqlalchemy import (
    Integer, String, Text, Boolean, Date, DateTime, Numeric,
    Enum as SAEnum, ForeignKey, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import mapped_column, relationship
from flask_login import UserMixin

from extensions import db
from models.enums import UserRole, StudentStatus, AttendanceStatus
from models.mixins import TenantMixin, TimestampMixin, utcnow


class User(db.Model, TenantMixin, TimestampMixin, UserMixin):
    """
    In-school user. email is unique PER SCHOOL (not globally) so two different
    schools can both have admin@example.com.
    """
    __tablename__ = 'users'
    __table_args__ = (
        UniqueConstraint('school_id', 'email', name='uq_user_email_per_school'),
    )

    id = mapped_column(Integer, primary_key=True)
    email = mapped_column(String(255), nullable=False, index=True)
    password_hash = mapped_column(String(255), nullable=False)
    name = mapped_column(String(255), nullable=False)
    role = mapped_column(SAEnum(UserRole, name='user_role'), nullable=False)
    phone = mapped_column(String(50))
    is_active = mapped_column(Boolean, default=True, nullable=False)

    school = relationship('School', back_populates='users')

    # Flask-Login identity must be globally unique. Plain integer PK works
    # because PKs are unique across the shared table. Tenant isolation is
    # enforced at query time via g.current_school_id, not via the login id.
    def get_id(self):
        return f'user:{self.id}'

    def __repr__(self):
        return f'<User {self.email} ({self.role}) school={self.school_id}>'


class Student(db.Model, TenantMixin, TimestampMixin):
    __tablename__ = 'students'
    __table_args__ = (
        UniqueConstraint('school_id', 'admission_no',
                         name='uq_student_admission_no'),
    )

    id = mapped_column(Integer, primary_key=True)
    user_id = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True,
    )  # young students may have no login
    admission_no = mapped_column(String(50), nullable=False)
    first_name = mapped_column(String(100), nullable=False)
    last_name = mapped_column(String(100), nullable=False)
    other_names = mapped_column(String(100))
    gender = mapped_column(String(20))
    dob = mapped_column(Date)
    photo_path = mapped_column(String(500))
    current_class_id = mapped_column(
        Integer, ForeignKey('classes.id', ondelete='SET NULL'), nullable=True,
        index=True,
    )
    date_admitted = mapped_column(Date)
    guardian_name = mapped_column(String(255))
    guardian_phone = mapped_column(String(50))
    status = mapped_column(
        SAEnum(StudentStatus, name='student_status'),
        nullable=False, default=StudentStatus.active,
    )

    current_class = relationship('Class', foreign_keys=[current_class_id])
    user = relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<Student {self.admission_no} {self.first_name} {self.last_name}>'


class ParentStudent(db.Model, TenantMixin):
    """Many-to-many: one parent (user) -> many students."""
    __tablename__ = 'parent_students'
    __table_args__ = (
        UniqueConstraint('school_id', 'parent_user_id', 'student_id',
                         name='uq_parent_student'),
    )

    id = mapped_column(Integer, primary_key=True)
    parent_user_id = mapped_column(
        Integer, ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    student_id = mapped_column(
        Integer, ForeignKey('students.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    relationship_label = mapped_column('relationship', String(50))  # "Mother"

    parent = relationship('User', foreign_keys=[parent_user_id])
    student = relationship('Student', foreign_keys=[student_id])


class TeacherAssignment(db.Model, TenantMixin):
    """Which teacher teaches which subject in which class, for a term."""
    __tablename__ = 'teacher_assignments'
    __table_args__ = (
        UniqueConstraint('school_id', 'teacher_user_id', 'class_id',
                         'subject_id', 'term_id',
                         name='uq_teacher_assignment'),
    )

    id = mapped_column(Integer, primary_key=True)
    teacher_user_id = mapped_column(
        Integer, ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    class_id = mapped_column(
        Integer, ForeignKey('classes.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    subject_id = mapped_column(
        Integer, ForeignKey('subjects.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    term_id = mapped_column(
        Integer, ForeignKey('terms.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )

    teacher = relationship('User', foreign_keys=[teacher_user_id])
    klass = relationship('Class', foreign_keys=[class_id])
    subject = relationship('Subject', foreign_keys=[subject_id])
    term = relationship('Term', foreign_keys=[term_id])


class AttendanceRecord(db.Model, TenantMixin):
    __tablename__ = 'attendance_records'
    __table_args__ = (
        UniqueConstraint('school_id', 'student_id', 'date',
                         name='uq_attendance_per_day'),
    )

    id = mapped_column(Integer, primary_key=True)
    student_id = mapped_column(
        Integer, ForeignKey('students.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    class_id = mapped_column(
        Integer, ForeignKey('classes.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    date = mapped_column(Date, nullable=False, index=True)
    status = mapped_column(
        SAEnum(AttendanceStatus, name='attendance_status'), nullable=False,
    )
    marked_by = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True,
    )


class AssessmentScore(db.Model, TenantMixin):
    """Raw component scores entered by teachers."""
    __tablename__ = 'assessment_scores'
    __table_args__ = (
        UniqueConstraint('school_id', 'student_id', 'subject_id', 'term_id',
                         'assessment_component_id', name='uq_assessment_score'),
    )

    id = mapped_column(Integer, primary_key=True)
    student_id = mapped_column(
        Integer, ForeignKey('students.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    class_id = mapped_column(
        Integer, ForeignKey('classes.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    subject_id = mapped_column(
        Integer, ForeignKey('subjects.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    term_id = mapped_column(
        Integer, ForeignKey('terms.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    assessment_component_id = mapped_column(
        Integer, ForeignKey('assessment_components.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    score = mapped_column(Numeric(5, 2), nullable=False)  # 0–100
    entered_by = mapped_column(
        Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True,
    )
    entered_at = mapped_column(DateTime(timezone=True), default=utcnow,
                               nullable=False)


class TermResult(db.Model, TenantMixin):
    """
    Computed: weighted total + grade snapshot. grade_label/remark are snapshot
    at computation time and never re-derived (boundaries may change later).
    is_published gates visibility to students/parents.
    """
    __tablename__ = 'term_results'
    __table_args__ = (
        UniqueConstraint('school_id', 'student_id', 'subject_id', 'term_id',
                         name='uq_term_result'),
    )

    id = mapped_column(Integer, primary_key=True)
    student_id = mapped_column(
        Integer, ForeignKey('students.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    class_id = mapped_column(
        Integer, ForeignKey('classes.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    subject_id = mapped_column(
        Integer, ForeignKey('subjects.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    term_id = mapped_column(
        Integer, ForeignKey('terms.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    total_score = mapped_column(Numeric(6, 2))
    grade_label = mapped_column(String(20))
    remark = mapped_column(String(100))
    is_pass = mapped_column(Boolean)
    class_position = mapped_column(Integer, nullable=True)
    is_published = mapped_column(Boolean, default=False, nullable=False,
                                 index=True)
    computed_at = mapped_column(DateTime(timezone=True), default=utcnow)


class ReportComment(db.Model, TenantMixin):
    __tablename__ = 'report_comments'
    __table_args__ = (
        UniqueConstraint('school_id', 'student_id', 'term_id',
                         name='uq_report_comment'),
    )

    id = mapped_column(Integer, primary_key=True)
    student_id = mapped_column(
        Integer, ForeignKey('students.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    term_id = mapped_column(
        Integer, ForeignKey('terms.id', ondelete='CASCADE'),
        nullable=False, index=True,
    )
    teacher_comment = mapped_column(Text)
    head_comment = mapped_column(Text)
    attendance_present = mapped_column(Integer)
    attendance_total = mapped_column(Integer)


class AuditLog(db.Model, TimestampMixin):
    """
    Audit trail. school_id is NULLABLE because platform-level actions (super
    admin) have no tenant. Does NOT use TenantMixin for that reason.
    """
    __tablename__ = 'audit_logs'

    id = mapped_column(Integer, primary_key=True)
    school_id = mapped_column(
        Integer, ForeignKey('schools.id', ondelete='SET NULL'),
        nullable=True, index=True,
    )
    user_id = mapped_column(Integer, nullable=True)  # users.id OR platform_users.id
    action = mapped_column(String(100), nullable=False)
    entity = mapped_column(String(100))
    entity_id = mapped_column(Integer)
    meta = mapped_column(JSONB)
