"""
SchoolBrain models package.

Import order matters for SQLAlchemy relationship resolution and Alembic
autogenerate: importing this package registers every model on `db.metadata`.
"""
from extensions import db  # noqa: F401

# Enums
from models.enums import (  # noqa: F401
    SchoolStatus, UserRole, StudentStatus, AttendanceStatus,
)

# Mixins
from models.mixins import TenantMixin, TimestampMixin  # noqa: F401

# Platform tables (no school_id)
from models.platform import (  # noqa: F401
    School, Plan, Subscription, PlatformUser, Payment,
)

# Tenant configuration tables
from models.config_tables import (  # noqa: F401
    AcademicYear, Term, LevelGroup, Level, Class, Subject, LevelSubject,
    GradingScheme, GradeBoundary, AssessmentComponent, ReportSettings,
)

# Tenant operational tables
from models.operational import (  # noqa: F401
    User, Student, ParentStudent, TeacherAssignment, AttendanceRecord,
    AssessmentScore, TermResult, ReportComment, AuditLog,
)

# Notification / settings tables (Phase 2)
from models.notifications import (  # noqa: F401
    SchoolNotificationSettings, PlatformSetting, NotificationLog,
)

# Fee invoicing tables (Phase 2)
from models.fees import (  # noqa: F401
    FeeStructure, Invoice, InvoiceItem, FeePayment,
)

# Timetabling tables (Phase 3)
from models.timetable import (  # noqa: F401
    Period, TimetableSlot,
)

__all__ = [
    'db',
    'SchoolStatus', 'UserRole', 'StudentStatus', 'AttendanceStatus',
    'TenantMixin', 'TimestampMixin',
    'School', 'Plan', 'Subscription', 'PlatformUser', 'Payment',
    'AcademicYear', 'Term', 'LevelGroup', 'Level', 'Class', 'Subject',
    'LevelSubject', 'GradingScheme', 'GradeBoundary', 'AssessmentComponent',
    'ReportSettings',
    'User', 'Student', 'ParentStudent', 'TeacherAssignment',
    'AttendanceRecord', 'AssessmentScore', 'TermResult', 'ReportComment',
    'AuditLog',
    'SchoolNotificationSettings', 'PlatformSetting', 'NotificationLog',
    'FeeStructure', 'Invoice', 'InvoiceItem', 'FeePayment',
    'Period', 'TimetableSlot',
]
