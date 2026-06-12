"""
Enumerations used by the models.

These are NOT curriculum-specific — they are structural roles/statuses that
apply to every school regardless of curriculum. Grade labels, term names,
level names etc. are data, never enums.
"""
import enum


class SchoolStatus(str, enum.Enum):
    trial = 'trial'
    active = 'active'
    suspended = 'suspended'


class UserRole(str, enum.Enum):
    school_admin = 'school_admin'
    teacher = 'teacher'
    student = 'student'
    parent = 'parent'


class StudentStatus(str, enum.Enum):
    active = 'active'
    graduated = 'graduated'
    withdrawn = 'withdrawn'


class AttendanceStatus(str, enum.Enum):
    present = 'present'
    absent = 'absent'
    late = 'late'
    excused = 'excused'
