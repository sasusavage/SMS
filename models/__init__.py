"""
NaCCA School Management System - Database Models
Comprehensive PostgreSQL Schema with Full Relational Integrity
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from enum import Enum
import uuid

db = SQLAlchemy()


# =============================================================================
# ENUMS
# =============================================================================
class UserRole(Enum):
    SUPER_ADMIN = 'super_admin'
    HEADTEACHER = 'headteacher'
    ADMIN = 'admin'
    TEACHER = 'teacher'
    ACCOUNTS_OFFICER = 'accounts_officer'
    PARENT = 'parent'


class Gender(Enum):
    MALE = 'male'
    FEMALE = 'female'


class PaymentMethod(Enum):
    CASH = 'cash'
    MOBILE_MONEY = 'mobile_money'
    BANK_TRANSFER = 'bank_transfer'
    ONLINE = 'online'


class PaymentStatus(Enum):
    PENDING = 'pending'
    COMPLETED = 'completed'
    PARTIAL = 'partial'
    FAILED = 'failed'
    REFUNDED = 'refunded'


class AttendanceStatus(Enum):
    PRESENT = 'present'
    ABSENT = 'absent'
    LATE = 'late'
    EXCUSED = 'excused'


class StudentStatus(Enum):
    ACTIVE = 'active'
    GRADUATED = 'graduated'
    TRANSFERRED = 'transferred'
    SUSPENDED = 'suspended'
    WITHDRAWN = 'withdrawn'


# =============================================================================
# BASE MIXIN
# =============================================================================
class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# =============================================================================
# SCHOOL & CONFIGURATION
# =============================================================================
class School(db.Model, TimestampMixin):
    """School information and branding."""
    __tablename__ = 'schools'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(200), nullable=False)
    motto = db.Column(db.String(300))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    region = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    website = db.Column(db.String(200))
    logo_url = db.Column(db.String(500))
    headteacher_signature_url = db.Column(db.String(500))
    primary_color = db.Column(db.String(7), default='#4F46E5')  # Electric Indigo
    secondary_color = db.Column(db.String(7), default='#1E293B')  # Slate
    established_year = db.Column(db.Integer)
    school_type = db.Column(db.String(50))  # Primary, JHS, SHS, Combined
    is_active = db.Column(db.Boolean, default=True)
    
    # SaaS Status & Suspension
    is_account_suspended = db.Column(db.Boolean, default=False)
    suspension_reason = db.Column(db.String(255))
    sms_credits = db.Column(db.Integer, default=100) # Pre-seeded credits
    
    # Relationships
    academic_years = db.relationship('AcademicYear', backref='school', lazy='dynamic')
    classes = db.relationship('Class', backref='school', lazy='dynamic')
    departments = db.relationship('Department', backref='school', lazy='dynamic')
    users = db.relationship('User', backref='school', lazy='dynamic')
    students = db.relationship('Student', backref='school', lazy='dynamic')
    fee_structures = db.relationship('FeeStructure', backref='school', lazy='dynamic')


class AcademicYear(db.Model, TimestampMixin):
    """Academic year management."""
    __tablename__ = 'academic_years'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(50), nullable=False)  # e.g., "2024/2025"
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_current = db.Column(db.Boolean, default=False)
    
    # Relationships
    terms = db.relationship('Term', backref='academic_year', lazy='dynamic', cascade='all, delete-orphan')
    class_enrollments = db.relationship('ClassEnrollment', backref='academic_year', lazy='dynamic')
    
    __table_args__ = (
        db.UniqueConstraint('school_id', 'name', name='uq_school_academic_year'),
    )


class Term(db.Model, TimestampMixin):
    """Academic terms within an academic year."""
    __tablename__ = 'terms'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(50), nullable=False)  # First Term, Second Term, Third Term
    term_number = db.Column(db.Integer, nullable=False)  # 1, 2, or 3
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_current = db.Column(db.Boolean, default=False)
    
    # Relationships
    assessments = db.relationship('Assessment', backref='term', lazy='dynamic')
    fee_invoices = db.relationship('FeeInvoice', backref='term', lazy='dynamic')
    
    __table_args__ = (
        db.UniqueConstraint('academic_year_id', 'term_number', name='uq_year_term'),
        db.CheckConstraint('term_number >= 1 AND term_number <= 3', name='chk_term_number'),
    )


# =============================================================================
# DEPARTMENTS & CLASSES
# =============================================================================
class Department(db.Model, TimestampMixin):
    """Academic departments (for JHS/SHS)."""
    __tablename__ = 'departments'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(10))
    description = db.Column(db.Text)
    head_of_department_id = db.Column(db.Integer, db.ForeignKey('staff.id', ondelete='SET NULL'))
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    subjects = db.relationship('Subject', backref='department', lazy='dynamic')
    
    __table_args__ = (
        db.UniqueConstraint('school_id', 'name', name='uq_school_department'),
    )


class Class(db.Model, TimestampMixin):
    """School classes/grades."""
    __tablename__ = 'classes'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # e.g., "Primary 6A"
    level = db.Column(db.String(50), nullable=False)  # Creche, KG, Primary, JHS, SHS
    grade_number = db.Column(db.Integer)  # 1-6 for Primary, 1-3 for JHS/SHS
    section = db.Column(db.String(10))  # A, B, C, etc.
    capacity = db.Column(db.Integer, default=40)
    class_teacher_id = db.Column(db.Integer, db.ForeignKey('staff.id', ondelete='SET NULL'))
    room_number = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    enrollments = db.relationship('ClassEnrollment', backref='class_', lazy='dynamic')
    subjects = db.relationship('ClassSubject', backref='class_', lazy='dynamic')
    fee_structures = db.relationship('FeeStructure', backref='class_', lazy='dynamic')
    
    __table_args__ = (
        db.UniqueConstraint('school_id', 'name', name='uq_school_class_name'),
        db.Index('idx_class_school_active', 'school_id', 'is_active'),
    )


class Subject(db.Model, TimestampMixin):
    """Academic subjects."""
    __tablename__ = 'subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'))
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20))
    description = db.Column(db.Text)
    is_core = db.Column(db.Boolean, default=True)  # Core vs Elective
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    class_subjects = db.relationship('ClassSubject', backref='subject', lazy='dynamic')
    
    __table_args__ = (
        db.UniqueConstraint('school_id', 'name', name='uq_school_subject'),
    )


class ClassSubject(db.Model, TimestampMixin):
    """Junction table linking classes to subjects with assigned teacher."""
    __tablename__ = 'class_subjects'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id', ondelete='CASCADE'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('staff.id', ondelete='SET NULL'))
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id', ondelete='CASCADE'), nullable=False)
    
    # NaCCA Assessment Weights
    classwork_weight = db.Column(db.Float, default=30.0)  # 30%
    homework_weight = db.Column(db.Float, default=10.0)   # 10%
    project_weight = db.Column(db.Float, default=10.0)    # 10%
    exam_weight = db.Column(db.Float, default=50.0)       # 50%
    
    # Relationships
    assessments = db.relationship('Assessment', backref='class_subject', lazy='dynamic')
    
    __table_args__ = (
        db.UniqueConstraint('class_id', 'subject_id', 'academic_year_id', name='uq_class_subject_year'),
    )


# =============================================================================
# NaCCA STRANDS & SUB-STRANDS
# =============================================================================
class Strand(db.Model, TimestampMixin):
    """NaCCA Strands (e.g., Number, Algebra)."""
    __tablename__ = 'strands'
    
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    sub_strands = db.relationship('SubStrand', backref='strand', lazy='dynamic', cascade='all, delete-orphan')


class SubStrand(db.Model, TimestampMixin):
    """NaCCA Sub-strands (e.g., Whole Numbers, Operations)."""
    __tablename__ = 'sub_strands'
    
    id = db.Column(db.Integer, primary_key=True)
    strand_id = db.Column(db.Integer, db.ForeignKey('strands.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(50))  # e.g., B6.1.1
    description = db.Column(db.Text)


# =============================================================================
# USERS & AUTHENTICATION
# =============================================================================
class User(db.Model, UserMixin, TimestampMixin):
    """User accounts for all roles."""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    
    # Profile link - polymorphic
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id', ondelete='SET NULL'))
    parent_id = db.Column(db.Integer, db.ForeignKey('parents.id', ondelete='SET NULL'))

    # 2FA (TOTP — Google Authenticator compatible)
    totp_secret  = db.Column(db.String(64))           # None = 2FA not set up
    totp_enabled = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def has_role(self, *roles):
        return self.role in roles
    
    def is_admin(self):
        return self.role in [UserRole.SUPER_ADMIN, UserRole.HEADTEACHER, UserRole.ADMIN]


# =============================================================================
# STAFF
# =============================================================================
class Staff(db.Model, TimestampMixin):
    """All school staff members."""
    __tablename__ = 'staff'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    staff_id = db.Column(db.String(50), unique=True, nullable=False)  # Employee ID
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    other_names = db.Column(db.String(100))
    gender = db.Column(db.Enum(Gender), nullable=False)
    date_of_birth = db.Column(db.Date)
    nationality = db.Column(db.String(50), default='Ghanaian')
    
    # Contact
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    region = db.Column(db.String(100))
    
    # Employment
    position = db.Column(db.String(100))  # Teacher, Headteacher, Admin, etc.
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'))
    qualification = db.Column(db.String(200))
    date_employed = db.Column(db.Date)
    salary = db.Column(db.Numeric(12, 2))
    bank_name = db.Column(db.String(100))
    bank_account = db.Column(db.String(50))
    
    # Document
    photo_url = db.Column(db.String(500))
    ghana_card_number = db.Column(db.String(20))
    ssnit_number = db.Column(db.String(20))
    
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    user = db.relationship('User', backref='staff_profile', uselist=False, foreign_keys='User.staff_id')
    class_teacher_of = db.relationship('Class', backref='class_teacher', foreign_keys='Class.class_teacher_id')
    taught_subjects = db.relationship('ClassSubject', backref='teacher', foreign_keys='ClassSubject.teacher_id')
    
    @property
    def full_name(self):
        parts = [self.first_name]
        if self.other_names:
            parts.append(self.other_names)
        parts.append(self.last_name)
        return ' '.join(parts)


# =============================================================================
# STUDENTS & PARENTS
# =============================================================================
class Parent(db.Model, TimestampMixin):
    """Parent/Guardian information."""
    __tablename__ = 'parents'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    
    # Father's Details
    father_name = db.Column(db.String(200))
    father_occupation = db.Column(db.String(100))
    father_phone = db.Column(db.String(20))
    father_email = db.Column(db.String(120))
    
    # Mother's Details
    mother_name = db.Column(db.String(200))
    mother_occupation = db.Column(db.String(100))
    mother_phone = db.Column(db.String(20))
    mother_email = db.Column(db.String(120))
    
    # Guardian's Details
    guardian_name = db.Column(db.String(200))
    guardian_relationship = db.Column(db.String(50))
    guardian_occupation = db.Column(db.String(100))
    guardian_phone = db.Column(db.String(20))
    guardian_email = db.Column(db.String(120))
    
    # Address (shared)
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    region = db.Column(db.String(100))
    
    # Portal Access
    primary_contact_phone = db.Column(db.String(20))  # Used for login
    
    # Relationships
    students = db.relationship('Student', backref='parent', lazy='dynamic')
    user = db.relationship('User', backref='parent_profile', uselist=False, foreign_keys='User.parent_id')


class Student(db.Model, TimestampMixin):
    """Student information."""
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('parents.id', ondelete='SET NULL'))
    
    # Identification
    student_id = db.Column(db.String(50), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    other_names = db.Column(db.String(100))
    gender = db.Column(db.Enum(Gender), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    nationality = db.Column(db.String(50), default='Ghanaian')
    place_of_birth = db.Column(db.String(100))
    hometown = db.Column(db.String(100))
    religion = db.Column(db.String(50))
    
    # Health
    blood_group = db.Column(db.String(5))
    allergies = db.Column(db.Text)
    medical_conditions = db.Column(db.Text)
    
    # Academic
    admission_date = db.Column(db.Date, nullable=False)
    admission_number = db.Column(db.String(50))
    previous_school = db.Column(db.String(200))
    status = db.Column(db.Enum(StudentStatus), default=StudentStatus.ACTIVE)
    
    # Documents
    photo_url = db.Column(db.String(500))
    birth_certificate_url = db.Column(db.String(500))
    
    # Relationships
    enrollments = db.relationship('ClassEnrollment', backref='student', lazy='dynamic')
    assessments = db.relationship('Assessment', backref='student', lazy='dynamic')
    attendance_records = db.relationship('Attendance', backref='student', lazy='dynamic')
    fee_invoices = db.relationship('FeeInvoice', backref='student', lazy='dynamic')
    
    @property
    def full_name(self):
        parts = [self.first_name]
        if self.other_names:
            parts.append(self.other_names)
        parts.append(self.last_name)
        return ' '.join(parts)
    
    @property
    def current_class(self):
        """Get student's current class enrollment."""
        from sqlalchemy import and_
        enrollment = self.enrollments.join(AcademicYear).filter(
            AcademicYear.is_current == True
        ).first()
        return enrollment.class_ if enrollment else None

    __table_args__ = (
        db.Index('idx_student_school_status', 'school_id', 'status'),
        db.Index('idx_student_school_parent', 'school_id', 'parent_id'),
    )


class ClassEnrollment(db.Model, TimestampMixin):
    """Student enrollment in classes per academic year."""
    __tablename__ = 'class_enrollments'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id', ondelete='CASCADE'), nullable=False)
    enrollment_date = db.Column(db.Date, default=date.today)
    is_promoted = db.Column(db.Boolean)  # Promotion status at end of year
    promotion_remarks = db.Column(db.Text)
    
    # student and class_ are provided via backrefs from Student.enrollments and Class.enrollments
    
    __table_args__ = (
        # A student can only be in one class per academic year
        db.UniqueConstraint('student_id', 'academic_year_id', name='uq_student_year_enrollment'),
        db.Index('idx_enrollment_class_year', 'class_id', 'academic_year_id'),
    )


# =============================================================================
# ASSESSMENTS & GRADES
# =============================================================================
class Assessment(db.Model, TimestampMixin):
    """Individual assessment records."""
    __tablename__ = 'assessments'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    class_subject_id = db.Column(db.Integer, db.ForeignKey('class_subjects.id', ondelete='CASCADE'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id', ondelete='CASCADE'), nullable=False)
    sub_strand_id = db.Column(db.Integer, db.ForeignKey('sub_strands.id', ondelete='SET NULL'))
    
    # NaCCA Assessment Components
    classwork_score = db.Column(db.Float, default=0)  # Out of 30
    homework_score = db.Column(db.Float, default=0)   # Out of 10
    project_score = db.Column(db.Float, default=0)    # Out of 10
    exam_score = db.Column(db.Float, default=0)       # Out of 50
    
    # Calculated fields (stored for performance)
    total_score = db.Column(db.Float)  # Out of 100
    grade = db.Column(db.String(5))
    grade_remark = db.Column(db.String(100)) # e.g. Highly Proficient
    narrative_comment = db.Column(db.Text)   # Automated NaCCA comment
    class_position = db.Column(db.Integer)
    
    # Teacher remarks
    teacher_remarks = db.Column(db.Text)
    
    # Recording metadata
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'class_subject_id', 'term_id', 'sub_strand_id', name='uq_student_subject_term_strand'),
        db.Index('idx_assessment_school_student', 'school_id', 'student_id'),
        # Performance index for the v_student_subject_performance view ranking
        db.Index('idx_assessment_ranking', 'school_id', 'class_subject_id', 'term_id', 'total_score'),
    )
    
    def calculate_total(self):
        """Calculate total score from components."""
        self.total_score = (
            (self.classwork_score or 0) + 
            (self.homework_score or 0) + 
            (self.project_score or 0) + 
            (self.exam_score or 0)
        )
        return self.total_score
    
    def calculate_grade(self, level='PRIMARY'):
        """Calculate grade based on NaCCA standards."""
        from flask import current_app
        
        if self.total_score is None:
            self.calculate_total()
        
        grading_scale = current_app.config.get('NACCA_GRADING_SCALE', {}).get(level, {})
        
        for (min_score, max_score), (grade, remark) in grading_scale.items():
            if min_score <= self.total_score <= max_score:
                self.grade = grade
                self.grade_remark = remark
                return self.grade
        
        return None


class TerminalReport(db.Model, TimestampMixin):
    """Terminal report summaries."""
    __tablename__ = 'terminal_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id', ondelete='CASCADE'), nullable=False)
    class_enrollment_id = db.Column(db.Integer, db.ForeignKey('class_enrollments.id', ondelete='CASCADE'), nullable=False)
    
    # Aggregated Scores
    total_marks = db.Column(db.Float)
    average_score = db.Column(db.Float)
    class_position = db.Column(db.Integer)
    class_size = db.Column(db.Integer)
    
    # Attendance
    total_days = db.Column(db.Integer)
    days_present = db.Column(db.Integer)
    days_absent = db.Column(db.Integer)
    
    # Conduct & Behavior
    conduct_grade = db.Column(db.String(50))
    attitude_grade = db.Column(db.String(50))
    interest_grade = db.Column(db.String(50))
    
    # Remarks
    class_teacher_remarks = db.Column(db.Text)
    headteacher_remarks = db.Column(db.Text)
    
    # Next Term
    next_term_begins = db.Column(db.Date)
    promotion_status = db.Column(db.String(50))  # Promoted, Repeated, etc.
    
    # Report Status
    is_published = db.Column(db.Boolean, default=False)
    published_at = db.Column(db.DateTime)
    
    # Relationships
    student = db.relationship('Student', foreign_keys=[student_id])
    term = db.relationship('Term', foreign_keys=[term_id])
    class_enrollment = db.relationship('ClassEnrollment', foreign_keys=[class_enrollment_id])
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'term_id', name='uq_student_term_report'),
    )


# =============================================================================
# ATTENDANCE
# =============================================================================
class Attendance(db.Model, TimestampMixin):
    """Daily attendance records."""
    __tablename__ = 'attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum(AttendanceStatus), nullable=False)
    remarks = db.Column(db.Text)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'date', name='uq_student_date_attendance'),
        db.Index('idx_attendance_school_student', 'school_id', 'student_id'),
    )


class StaffAttendance(db.Model, TimestampMixin):
    """Staff attendance records."""
    __tablename__ = 'staff_attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time_in = db.Column(db.Time)
    time_out = db.Column(db.Time)
    status = db.Column(db.Enum(AttendanceStatus), nullable=False)
    remarks = db.Column(db.Text)
    
    __table_args__ = (
        db.UniqueConstraint('staff_id', 'date', name='uq_staff_date_attendance'),
    )


# =============================================================================
# FEES & PAYMENTS
# =============================================================================
class FeeCategory(db.Model, TimestampMixin):
    """Fee categories/types."""
    __tablename__ = 'fee_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_recurring = db.Column(db.Boolean, default=True)  # Charged every term
    is_active = db.Column(db.Boolean, default=True)
    
    __table_args__ = (
        db.UniqueConstraint('school_id', 'name', name='uq_school_fee_category'),
        db.Index('idx_fee_category_school', 'school_id'),
    )


class FeeStructure(db.Model, TimestampMixin):
    """Fee structure per class and academic year."""
    __tablename__ = 'fee_structures'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id', ondelete='CASCADE'), nullable=False)
    fee_category_id = db.Column(db.Integer, db.ForeignKey('fee_categories.id', ondelete='CASCADE'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    term_applicable = db.Column(db.Integer)  # 1, 2, 3 or NULL for annual fees
    
    # Relationships
    fee_category = db.relationship('FeeCategory', backref='fee_structures')
    academic_year = db.relationship('AcademicYear', backref='fee_structures')
    
    __table_args__ = (
        db.UniqueConstraint('class_id', 'academic_year_id', 'fee_category_id', 'term_applicable', 
                          name='uq_class_year_fee_term'),
    )


class FeeInvoice(db.Model, TimestampMixin):
    """Fee invoices generated for students."""
    __tablename__ = 'fee_invoices'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id', ondelete='CASCADE'), nullable=False)
    
    # Amounts
    total_amount = db.Column(db.Numeric(12, 2), nullable=False)
    discount_amount = db.Column(db.Numeric(12, 2), default=0)
    amount_paid = db.Column(db.Numeric(12, 2), default=0)
    balance = db.Column(db.Numeric(12, 2), nullable=False)
    
    # Dates
    issue_date = db.Column(db.Date, default=date.today)
    due_date = db.Column(db.Date)
    
    status = db.Column(db.Enum(PaymentStatus), default=PaymentStatus.PENDING)
    notes = db.Column(db.Text)
    
    # Relationships
    items = db.relationship('FeeInvoiceItem', backref='invoice', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='invoice', lazy='dynamic')

    __table_args__ = (
        db.Index('idx_invoice_school_term', 'school_id', 'term_id'),
        db.Index('idx_invoice_school_student', 'school_id', 'student_id'),
        db.Index('idx_invoice_school_status', 'school_id', 'status'),
    )

    def update_balance(self):
        """Recalculate balance after payment."""
        self.balance = self.total_amount - self.discount_amount - self.amount_paid
        if self.balance <= 0:
            self.status = PaymentStatus.COMPLETED
            self.balance = 0
        elif self.amount_paid > 0:
            self.status = PaymentStatus.PARTIAL


class FeeInvoiceItem(db.Model, TimestampMixin):
    """Line items in a fee invoice."""
    __tablename__ = 'fee_invoice_items'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('fee_invoices.id', ondelete='CASCADE'), nullable=False)
    fee_category_id = db.Column(db.Integer, db.ForeignKey('fee_categories.id', ondelete='SET NULL'))
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)


class Payment(db.Model, TimestampMixin):
    """Payment transactions."""
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    receipt_number = db.Column(db.String(50), unique=True, nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey('fee_invoices.id', ondelete='CASCADE'), nullable=False)
    
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_method = db.Column(db.Enum(PaymentMethod), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Payment Details
    transaction_reference = db.Column(db.String(100))  # For mobile money/bank transfers
    payer_name = db.Column(db.String(200))
    payer_phone = db.Column(db.String(20))
    
    status = db.Column(db.Enum(PaymentStatus), default=PaymentStatus.COMPLETED)
    notes = db.Column(db.Text)
    
    received_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    received_by = db.relationship('User', backref='payments_received')


class Expense(db.Model, TimestampMixin):
    """School operational expenses."""
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id', ondelete='CASCADE'))
    category = db.Column(db.String(50), nullable=False) # Salary, Utilities, Stationery, Fuel, Maintenance
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    description = db.Column(db.Text)
    expense_date = db.Column(db.Date, default=date.today)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    
    school = db.relationship('School', backref='expenses')
    recorder = db.relationship('User', backref='expenses_recorded')


# =============================================================================
# NOTIFICATIONS & COMMUNICATIONS
# =============================================================================
# (Removed legacy Notification model - merged into upgraded multi-tenant version below)


# =============================================================================
# AUDIT LOG
# =============================================================================
class AuditLog(db.Model):
    """Audit trail for important actions."""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    old_values = db.Column(db.JSON)
    new_values = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    
    user = db.relationship('User', backref='audit_logs')


# =============================================================================
# SaaS SUBSCRIPTIONS
# =============================================================================
class SubscriptionPlan(db.Model, TimestampMixin):
    """SaaS Subscription Tiers (Basic, Pro, Enterprise)."""
    __tablename__ = 'subscription_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    student_limit = db.Column(db.Integer, default=100)
    features = db.Column(db.JSON) # List of enabled modules
    is_active = db.Column(db.Boolean, default=True)


class Subscription(db.Model, TimestampMixin):
    """Schools' specific subscription status."""
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey('subscription_plans.id'), nullable=False)
    start_date = db.Column(db.Date, default=date.today)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='active') # active, expired, cancelled
    
    school = db.relationship('School', backref=db.backref('subscription', uselist=False))
    plan = db.relationship('SubscriptionPlan')


# =============================================================================
# HELPER FUNCTIONS & DATABASE VIEWS
# =============================================================================

class SubjectPerformanceView(db.Model):
    """SQLAlchemy Mapping for the Subject Performance View"""
    __tablename__ = 'v_student_subject_performance'
    __table_args__ = {'info': {'is_view': True}}
    
    # SQLAlchemy requires a primary key even for views.
    # assessment_id is unique per term/student/subject combo.
    assessment_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer)
    school_id = db.Column(db.Integer)
    term_id = db.Column(db.Integer)
    class_id = db.Column(db.Integer)
    subject_id = db.Column(db.Integer)
    
    class_score = db.Column(db.Float)
    exam_score = db.Column(db.Float)
    total_score = db.Column(db.Float)
    nacca_grade = db.Column(db.String(50))
    subject_position = db.Column(db.Integer)


class TerminalReportView(db.Model):
    """SQLAlchemy Mapping for the Aggregated Terminal Report Materialized View."""
    __tablename__ = 'v_student_terminal_reports'
    __table_args__ = {'info': {'is_view': True}}

    # Composite PK needed for the view mapping
    student_id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer)   # included in the MV SELECT for tenant scoping
    class_id = db.Column(db.Integer)
    academic_year_id = db.Column(db.Integer)

    subjects_taken = db.Column(db.Integer)
    total_marks = db.Column(db.Float)
    average_score = db.Column(db.Float)
    class_position = db.Column(db.Integer)
    class_size = db.Column(db.Integer)


class SchoolSetting(db.Model, TimestampMixin):
    """Global school configurations to toggle SaaS features."""
    __tablename__ = 'school_settings'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    sms_enabled = db.Column(db.Boolean, default=True)
    whatsapp_enabled = db.Column(db.Boolean, default=False)
    whatsapp_business_id = db.Column(db.String(100), unique=True) # For routing webhooks
    api_key_sms = db.Column(db.String(255))  # Arkesel/Hubtel API Key
    sms_sender_id = db.Column(db.String(11))
    
    # AI Specific Settings
    ai_bot_enabled = db.Column(db.Boolean, default=False)
    ai_bot_name = db.Column(db.String(50), default='Sasu Jnr')


class NotificationType(Enum):
    SMS = 'sms'
    SYSTEM = 'system'
    BOTH = 'both'


class NotificationCategory(Enum):
    ATTENDANCE = 'attendance'
    FINANCE = 'finance'
    ACADEMIC = 'academic'
    GENERAL = 'general'


class Notification(db.Model, TimestampMixin):
    """Multi-tenant notification history for parents and staff."""
    __tablename__ = 'notifications'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.Enum(NotificationType), default=NotificationType.SYSTEM)
    category = db.Column(db.Enum(NotificationCategory), default=NotificationCategory.GENERAL)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    link = db.Column(db.String(500))  # Optional link to relevant page
    
    user = db.relationship('User', backref='notifications')


# =============================================================================
# AI & AGENTIC AGENTS
# =============================================================================
class AISession(db.Model, TimestampMixin):
    """WhatsApp conversation context for multi-tenant AI."""
    __tablename__ = 'ai_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False) # The parent/staff phone
    history = db.Column(db.JSON, default=list) # [{role: user, content: ...}]
    last_interaction = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Feedback Loop (NEW)
    last_interaction_id = db.Column(db.String(50)) # Tracking individual prompt/response
    user_feedback = db.Column(db.String(20)) # 'good', 'bad', None

    __table_args__ = (db.UniqueConstraint('school_id', 'phone_number', name='_school_phone_uc'),)


class AIBotConfig(db.Model, TimestampMixin):
    """School-specific AI personality and knowledge base."""
    __tablename__ = 'ai_bot_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), unique=True, nullable=False)
    system_prompt_override = db.Column(db.Text)
    knowledge_base = db.Column(db.Text) # JSON or Raw Text for specific school rules
    model_name = db.Column(db.String(50), default='llama3-8b-8192')
    temperature = db.Column(db.Float, default=0.7)
    
    school = db.relationship('School', backref=db.backref('ai_config', uselist=False))


class SupportTicket(db.Model, TimestampMixin):
    """AI-generated or Parent-initiated support inquiries."""
    __tablename__ = 'support_tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(200))
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='open') # open, resolved, pending
    priority = db.Column(db.String(20), default='normal')


class AICreditUsage(db.Model, TimestampMixin):
    """Track Groq/AI API usage per school for SaaS billing."""
    __tablename__ = 'ai_credit_usage'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    tokens_used = db.Column(db.Integer, default=0)
    interaction_type = db.Column(db.String(50)) # whatsapp, web_chat
    cost_estimated = db.Column(db.Float, default=0.0)


class ModuleConfig(db.Model, TimestampMixin):
    """Granular feature flags per school/tenant."""
    __tablename__ = 'module_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), unique=True, nullable=False)
    
    is_ai_enabled = db.Column(db.Boolean, default=True)
    is_sms_enabled = db.Column(db.Boolean, default=True)
    is_finance_enabled = db.Column(db.Boolean, default=True)
    is_qr_scanner_enabled = db.Column(db.Boolean, default=False)
    is_report_designer_enabled = db.Column(db.Boolean, default=True)
    is_predictive_ai_enabled = db.Column(db.Boolean, default=False)
    is_marketplace_enabled = db.Column(db.Boolean, default=False)
    is_pwa_enabled = db.Column(db.Boolean, default=True) # Enabled by default for all tiers
    is_voice_ai_enabled = db.Column(db.Boolean, default=False) # Elite/Premium only
    
    school = db.relationship('School', backref=db.backref('module_config', uselist=False))


class SchoolInsight(db.Model, TimestampMixin):
    """Identified academic or attendance 'Outliers' per school."""
    __tablename__ = 'school_insights'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    
    type = db.Column(db.String(50)) # 'attendance_drop', 'grade_dip', 'enrollment_spike'
    entity_name = db.Column(db.String(100)) # e.g., 'Grade 5 Red'
    insight_text = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20), default='medium') # low, medium, high
    is_active = db.Column(db.Boolean, default=True)


class AICorrection(db.Model, TimestampMixin):
    """Learning feedback for the AI agent."""
    __tablename__ = 'ai_corrections'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    
    original_prompt = db.Column(db.Text)
    wrong_response = db.Column(db.Text)
    correction_reason = db.Column(db.Text, nullable=False)
    is_applied = db.Column(db.Boolean, default=True)


# =============================================================================
# DIGITAL MARKETPLACE (ELITE TIER)
# =============================================================================
class ProductCategory(db.Model, TimestampMixin):
    """Categories for school items (Uniforms, Books, etc)."""
    __tablename__ = 'product_categories'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)


class Product(db.Model, TimestampMixin):
    """Items for sale in the school marketplace."""
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('product_categories.id', ondelete='CASCADE'), nullable=False)
    
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    base_price = db.Column(db.Numeric(10, 2), nullable=False)
    stock_quantity = db.Column(db.Integer, default=0)
    image_url = db.Column(db.String(500))
    is_active = db.Column(db.Boolean, default=True)


class Order(db.Model, TimestampMixin):
    """Customer orders (Parents/Staff)."""
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.Enum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_method = db.Column(db.Enum(PaymentMethod), default=PaymentMethod.ONLINE)
    paystack_ref = db.Column(db.String(100))
    is_delivered = db.Column(db.Boolean, default=False)
    
    items = db.relationship('OrderItem', backref='order', lazy=True)


class OrderItem(db.Model):
    """Individual items within an order."""
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)


def init_db(app):
    """Initialize database within app context.
    Avoid double init_app(app) as it's already done in create_app.
    """
    with app.app_context():
        db.create_all()
        
        from sqlalchemy import text
        
        # 1. Subject-Level Performance View
        sql_subject_view = (
            "DROP VIEW IF EXISTS v_student_subject_performance CASCADE; "
            "DROP TABLE IF EXISTS v_student_subject_performance CASCADE; "
            "CREATE VIEW v_student_subject_performance AS "
            "SELECT "
            "a.id AS assessment_id, "
            "s.id AS student_id, "
            "a.school_id, "
            "a.term_id, "
            "ce.class_id, "
            "cs.subject_id, "
            "(COALESCE(a.classwork_score, 0) + COALESCE(a.homework_score, 0) + COALESCE(a.project_score, 0)) AS class_score, "
            "COALESCE(a.exam_score, 0) AS exam_score, "
            "(COALESCE(a.classwork_score, 0) + COALESCE(a.homework_score, 0) + COALESCE(a.project_score, 0) + COALESCE(a.exam_score, 0)) AS total_score, "
            "CASE "
            "WHEN (COALESCE(a.classwork_score, 0) + COALESCE(a.homework_score, 0) + COALESCE(a.project_score, 0) + COALESCE(a.exam_score, 0)) >= 80 THEN 'Highly Proficient' "
            "WHEN (COALESCE(a.classwork_score, 0) + COALESCE(a.homework_score, 0) + COALESCE(a.project_score, 0) + COALESCE(a.exam_score, 0)) >= 70 THEN 'Proficient' "
            "WHEN (COALESCE(a.classwork_score, 0) + COALESCE(a.homework_score, 0) + COALESCE(a.project_score, 0) + COALESCE(a.exam_score, 0)) >= 60 THEN 'Approaching Proficiency' "
            "WHEN (COALESCE(a.classwork_score, 0) + COALESCE(a.homework_score, 0) + COALESCE(a.project_score, 0) + COALESCE(a.exam_score, 0)) >= 50 THEN 'Developing' "
            "ELSE 'Emerging' "
            "END AS nacca_grade, "
            "RANK() OVER (PARTITION BY a.school_id, ce.class_id, a.term_id, cs.subject_id ORDER BY (COALESCE(a.classwork_score, 0) + COALESCE(a.homework_score, 0) + COALESCE(a.project_score, 0) + COALESCE(a.exam_score, 0)) DESC) AS subject_position "
            "FROM assessments a "
            "JOIN students s ON a.student_id = s.id "
            "JOIN class_subjects cs ON a.class_subject_id = cs.id "
            "JOIN class_enrollments ce ON s.id = ce.student_id AND cs.class_id = ce.class_id AND cs.academic_year_id = ce.academic_year_id "
        )
        
        # 2. Terminal Report Aggregation (MATERIALIZED VIEW for SCALE)
        sql_terminal_view = (
            "DROP VIEW IF EXISTS v_student_terminal_reports CASCADE; "
            "DROP MATERIALIZED VIEW IF EXISTS v_student_terminal_reports CASCADE; "
            "CREATE MATERIALIZED VIEW v_student_terminal_reports AS "
            "WITH student_totals AS ( "
            "SELECT "
            "s.id AS student_id, "
            "s.school_id, "
            "a.term_id, "
            "ce.class_id, "
            "ce.academic_year_id, "
            "COUNT(a.id) AS subjects_taken, "
            "SUM(COALESCE(a.classwork_score, 0) + COALESCE(a.homework_score, 0) + COALESCE(a.project_score, 0) + COALESCE(a.exam_score, 0)) AS total_marks, "
            "AVG(COALESCE(a.classwork_score, 0) + COALESCE(a.homework_score, 0) + COALESCE(a.project_score, 0) + COALESCE(a.exam_score, 0)) AS average_score "
            "FROM students s "
            "JOIN class_enrollments ce ON s.id = ce.student_id "
            "JOIN class_subjects cs ON ce.class_id = cs.class_id AND ce.academic_year_id = cs.academic_year_id "
            "JOIN assessments a ON s.id = a.student_id AND cs.id = a.class_subject_id "
            "GROUP BY s.id, s.school_id, a.term_id, ce.class_id, ce.academic_year_id "
            ") "
            "SELECT *, "
            "RANK() OVER (PARTITION BY school_id, class_id, term_id ORDER BY total_marks DESC) AS class_position, "
            "COUNT(*) OVER (PARTITION BY school_id, class_id, term_id) AS class_size "
            "FROM student_totals; "
            "CREATE UNIQUE INDEX idx_mv_terminal_student_term ON v_student_terminal_reports (student_id, term_id);"
            "CREATE INDEX idx_mv_terminal_class_term ON v_student_terminal_reports (school_id, class_id, term_id);"
        )
        
        # Execute views separately and safely
        for view_sql in [sql_subject_view, sql_terminal_view]:
            for stmt in view_sql.split(';'):
                if stmt.strip():
                    try:
                        db.session.execute(text(stmt + ';'))
                        db.session.commit()
                    except Exception as e:
                        db.session.rollback()
                        print(f"Schema Setup (Minor): Skipping {stmt.split()[:3]}... due to {str(e)[:50]}")
        
        # System Initialization Audit Log
        try:
            init_log = AuditLog(
                action='SYSTEM_INITIALIZATION',
                entity_type='database',
                new_values={'status': 'schema_ready', 'timestamp': str(datetime.utcnow())}
            )
            db.session.add(init_log)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Audit Log Warning: Could not record system initialization: {e}")
        
        print("Database tables and NaCCA PostgreSQL Views created successfully!")


def refresh_terminal_reports():
    """Refresh the Materialized View for terminal reports concurrently."""
    from sqlalchemy import text
    try:
        # CONCURRENTLY requires a unique index (which we created)
        db.session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY v_student_terminal_reports;"))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # Fallback to standard refresh if concurrent fails (e.g. no index or first time)
        db.session.execute(text("REFRESH MATERIALIZED VIEW v_student_terminal_reports;"))
        db.session.commit()
        print(f"MV Refresh Warning: {e}")

