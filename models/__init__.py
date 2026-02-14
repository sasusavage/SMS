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
    primary_color = db.Column(db.String(7), default='#4F46E5')  # Electric Indigo
    secondary_color = db.Column(db.String(7), default='#1E293B')  # Slate
    established_year = db.Column(db.Integer)
    school_type = db.Column(db.String(50))  # Primary, JHS, SHS, Combined
    is_active = db.Column(db.Boolean, default=True)
    
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
    )


# =============================================================================
# ASSESSMENTS & GRADES
# =============================================================================
class Assessment(db.Model, TimestampMixin):
    """Individual assessment records."""
    __tablename__ = 'assessments'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    class_subject_id = db.Column(db.Integer, db.ForeignKey('class_subjects.id', ondelete='CASCADE'), nullable=False)
    term_id = db.Column(db.Integer, db.ForeignKey('terms.id', ondelete='CASCADE'), nullable=False)
    
    # NaCCA Assessment Components
    classwork_score = db.Column(db.Float, default=0)  # Out of 30
    homework_score = db.Column(db.Float, default=0)   # Out of 10
    project_score = db.Column(db.Float, default=0)    # Out of 10
    exam_score = db.Column(db.Float, default=0)       # Out of 50
    
    # Calculated fields (stored for performance)
    total_score = db.Column(db.Float)  # Out of 100
    grade = db.Column(db.String(5))
    grade_remark = db.Column(db.String(50))
    class_position = db.Column(db.Integer)
    
    # Teacher remarks
    teacher_remarks = db.Column(db.Text)
    
    # Recording metadata
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'class_subject_id', 'term_id', name='uq_student_subject_term'),
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
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum(AttendanceStatus), nullable=False)
    remarks = db.Column(db.Text)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    
    __table_args__ = (
        db.UniqueConstraint('student_id', 'date', name='uq_student_date_attendance'),
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
    
    # Who recorded the payment
    received_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    received_by = db.relationship('User', backref='payments_received')


# =============================================================================
# NOTIFICATIONS & COMMUNICATIONS
# =============================================================================
class Notification(db.Model, TimestampMixin):
    """System notifications."""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50))  # fee, academic, attendance, system
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    link = db.Column(db.String(500))  # Optional link to relevant page
    
    user = db.relationship('User', backref='notifications')


# =============================================================================
# AUDIT LOG
# =============================================================================
class AuditLog(db.Model):
    """Audit trail for important actions."""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
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
# HELPER FUNCTIONS
# =============================================================================
def init_db(app):
    """Initialize database with app context."""
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")
