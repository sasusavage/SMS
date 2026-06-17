"""
People service (Step 3) — users, students, parent links, teacher assignments.

All risky logic (per-school uniqueness, CSV validate→preview→commit, linking,
assignment uniqueness, promote/transfer) lives here, not in routes. Every
function is tenant-scoped via an explicit school_id argument and never reads or
writes across schools.

Raises PeopleError (UI-safe .message) on validation problems.
"""
import csv
import io
import secrets
from datetime import datetime

from extensions import db
from auth.security import hash_password
from models.enums import UserRole, StudentStatus
from models.operational import (
    User, Student, ParentStudent, TeacherAssignment,
)
from models.config_tables import Class, Subject, Term


class PeopleError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# Users (teachers / parents / admins)
# ---------------------------------------------------------------------------
def email_taken(school_id, email, exclude_user_id=None):
    q = User.query.filter(
        User.school_id == school_id,
        db.func.lower(User.email) == email.strip().lower(),
    )
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    return q.first() is not None


def create_user(school_id, *, name, email, role, password=None, phone=None):
    """
    Create an in-school user. `role` may be a UserRole or its string value.
    Returns (user, generated_password). If password is None a random one is
    generated and returned so the admin can hand it to the user.
    """
    email = (email or '').strip().lower()
    name = (name or '').strip()
    if not name:
        raise PeopleError('Name is required.')
    if not email:
        raise PeopleError('Email is required.')
    role = _coerce_role(role)
    if email_taken(school_id, email):
        raise PeopleError(f'A user with email {email} already exists in this school.')

    generated = None
    if not password:
        generated = secrets.token_urlsafe(8)
        password = generated
    elif len(password) < 8:
        raise PeopleError('Password must be at least 8 characters.')

    user = User(school_id=school_id, name=name, email=email, role=role,
                phone=(phone or '').strip() or None,
                password_hash=hash_password(password), is_active=True)
    db.session.add(user)
    db.session.flush()
    return user, generated


def reset_password(school_id, user_id, new_password=None):
    """Reset a user's password (tenant-scoped). Returns the new password."""
    user = _get_user(school_id, user_id)
    if not new_password:
        new_password = secrets.token_urlsafe(8)
    elif len(new_password) < 8:
        raise PeopleError('Password must be at least 8 characters.')
    user.password_hash = hash_password(new_password)
    db.session.flush()
    return new_password


def set_user_active(school_id, user_id, active):
    user = _get_user(school_id, user_id)
    user.is_active = bool(active)
    db.session.flush()
    return user


def update_user(school_id, user_id, *, name=None, email=None, phone=None):
    """Edit a user's name/email/phone (tenant-scoped). Email unique per school."""
    user = _get_user(school_id, user_id)
    if email is not None:
        email = email.strip().lower()
        if not email:
            raise PeopleError('Email is required.')
        if email_taken(school_id, email, exclude_user_id=user_id):
            raise PeopleError(f'A user with email {email} already exists in this school.')
        user.email = email
    if name is not None:
        if not name.strip():
            raise PeopleError('Name is required.')
        user.name = name.strip()
    if phone is not None:
        user.phone = phone.strip() or None
    db.session.flush()
    return user


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------
def admission_no_taken(school_id, admission_no, exclude_student_id=None):
    q = Student.query.filter(
        Student.school_id == school_id,
        Student.admission_no == admission_no.strip(),
    )
    if exclude_student_id is not None:
        q = q.filter(Student.id != exclude_student_id)
    return q.first() is not None


def create_student(school_id, *, admission_no, first_name, last_name,
                   other_names=None, gender=None, dob=None,
                   current_class_id=None, guardian_name=None,
                   guardian_phone=None, date_admitted=None):
    admission_no = (admission_no or '').strip()
    if not admission_no:
        raise PeopleError('Admission number is required.')
    if not (first_name or '').strip() or not (last_name or '').strip():
        raise PeopleError('First and last name are required.')
    if admission_no_taken(school_id, admission_no):
        raise PeopleError(
            f'Admission number "{admission_no}" already exists in this school.')
    if current_class_id is not None:
        _get_class(school_id, current_class_id)  # tenant check

    student = Student(
        school_id=school_id, admission_no=admission_no,
        first_name=first_name.strip(), last_name=last_name.strip(),
        other_names=(other_names or '').strip() or None,
        gender=(gender or '').strip() or None, dob=dob,
        current_class_id=current_class_id,
        guardian_name=(guardian_name or '').strip() or None,
        guardian_phone=(guardian_phone or '').strip() or None,
        date_admitted=date_admitted, status=StudentStatus.active,
    )
    db.session.add(student)
    db.session.flush()
    return student


def update_student(school_id, student_id, *, admission_no=None,
                   first_name=None, last_name=None, other_names=None,
                   gender=None, dob=None, guardian_name=None,
                   guardian_phone=None):
    """Edit a student's core fields (tenant-scoped). Only provided fields change."""
    student = _get_student(school_id, student_id)
    if admission_no is not None:
        admission_no = admission_no.strip()
        if not admission_no:
            raise PeopleError('Admission number is required.')
        if admission_no_taken(school_id, admission_no,
                              exclude_student_id=student_id):
            raise PeopleError(
                f'Admission number "{admission_no}" already exists in this school.')
        student.admission_no = admission_no
    if first_name is not None:
        if not first_name.strip():
            raise PeopleError('First name is required.')
        student.first_name = first_name.strip()
    if last_name is not None:
        if not last_name.strip():
            raise PeopleError('Last name is required.')
        student.last_name = last_name.strip()
    if other_names is not None:
        student.other_names = other_names.strip() or None
    if gender is not None:
        student.gender = gender.strip() or None
    if dob is not None:
        student.dob = dob
    if guardian_name is not None:
        student.guardian_name = guardian_name.strip() or None
    if guardian_phone is not None:
        student.guardian_phone = guardian_phone.strip() or None
    db.session.flush()
    return student


def transfer_student(school_id, student_id, new_class_id):
    """Move a student to another class (must belong to same school)."""
    student = _get_student(school_id, student_id)
    if new_class_id is not None:
        _get_class(school_id, new_class_id)
    student.current_class_id = new_class_id
    db.session.flush()
    return student


def set_student_status(school_id, student_id, status):
    student = _get_student(school_id, student_id)
    student.status = _coerce_student_status(status)
    db.session.flush()
    return student


# ---------------------------------------------------------------------------
# CSV bulk import: parse -> validate -> preview -> commit
# ---------------------------------------------------------------------------
CSV_COLUMNS = ['admission_no', 'first_name', 'last_name', 'other_names',
               'gender', 'dob', 'guardian_name', 'guardian_phone']
CSV_REQUIRED = ['admission_no', 'first_name', 'last_name']


def parse_student_csv(school_id, file_text, class_id=None):
    """
    Parse + validate a CSV. Returns a preview dict:
        {
          'rows':   [{'row': n, 'data': {...}, 'errors': [..]}, ...],
          'valid':  int,   # rows with no errors
          'invalid': int,
          'headers_ok': bool,
          'header_error': str | None,
        }
    Does NOT write anything — commit happens separately after the admin
    reviews the preview.
    """
    preview = {'rows': [], 'valid': 0, 'invalid': 0,
               'headers_ok': True, 'header_error': None}
    try:
        reader = csv.DictReader(io.StringIO(file_text))
    except Exception:
        preview['headers_ok'] = False
        preview['header_error'] = 'Could not read the CSV file.'
        return preview

    headers = [h.strip() for h in (reader.fieldnames or [])]
    missing = [c for c in CSV_REQUIRED if c not in headers]
    if missing:
        preview['headers_ok'] = False
        preview['header_error'] = (
            'Missing required column(s): ' + ', '.join(missing) +
            '. Expected columns: ' + ', '.join(CSV_COLUMNS))
        return preview

    # admission numbers already in the DB for this school
    existing = {
        a for (a,) in Student.query
        .with_entities(Student.admission_no)
        .filter(Student.school_id == school_id).all()
    }
    seen_in_file = set()

    for i, raw in enumerate(reader, start=1):
        data = {c: (raw.get(c) or '').strip() for c in CSV_COLUMNS}
        errors = []
        adm = data['admission_no']
        if not adm:
            errors.append('admission_no is required')
        if not data['first_name']:
            errors.append('first_name is required')
        if not data['last_name']:
            errors.append('last_name is required')
        if adm and adm in existing:
            errors.append(f'admission_no "{adm}" already exists')
        if adm and adm in seen_in_file:
            errors.append(f'admission_no "{adm}" is duplicated in the file')
        if adm:
            seen_in_file.add(adm)
        if data['dob'] and _parse_date(data['dob']) is None:
            errors.append('dob must be YYYY-MM-DD')

        preview['rows'].append({'row': i, 'data': data, 'errors': errors})
        if errors:
            preview['invalid'] += 1
        else:
            preview['valid'] += 1

    return preview


def commit_student_csv(school_id, file_text, class_id=None):
    """
    Re-validate and commit ONLY the valid rows. Returns
    {'imported': int, 'skipped': int}. Aborts (raises) if headers are invalid.
    """
    preview = parse_student_csv(school_id, file_text, class_id)
    if not preview['headers_ok']:
        raise PeopleError(preview['header_error'])
    if class_id is not None:
        _get_class(school_id, class_id)

    imported = 0
    for row in preview['rows']:
        if row['errors']:
            continue
        d = row['data']
        student = Student(
            school_id=school_id, admission_no=d['admission_no'],
            first_name=d['first_name'], last_name=d['last_name'],
            other_names=d['other_names'] or None,
            gender=d['gender'] or None,
            dob=_parse_date(d['dob']) if d['dob'] else None,
            guardian_name=d['guardian_name'] or None,
            guardian_phone=d['guardian_phone'] or None,
            current_class_id=class_id, status=StudentStatus.active,
        )
        db.session.add(student)
        imported += 1
    db.session.flush()
    return {'imported': imported, 'skipped': preview['invalid']}


# ---------------------------------------------------------------------------
# Parent–student linking
# ---------------------------------------------------------------------------
def link_parent_student(school_id, parent_user_id, student_id,
                        relationship_label=None):
    parent = _get_user(school_id, parent_user_id)
    if parent.role != UserRole.parent:
        raise PeopleError('That user is not a parent.')
    _get_student(school_id, student_id)  # tenant check
    existing = ParentStudent.query.filter_by(
        school_id=school_id, parent_user_id=parent_user_id,
        student_id=student_id).first()
    if existing:
        raise PeopleError('This parent is already linked to that student.')
    link = ParentStudent(school_id=school_id, parent_user_id=parent_user_id,
                         student_id=student_id,
                         relationship_label=(relationship_label or '').strip() or None)
    db.session.add(link)
    db.session.flush()
    return link


def unlink_parent_student(school_id, link_id):
    link = ParentStudent.query.filter_by(school_id=school_id, id=link_id).first()
    if link is None:
        raise PeopleError('Link not found.')
    db.session.delete(link)
    db.session.flush()


# ---------------------------------------------------------------------------
# Teacher assignments
# ---------------------------------------------------------------------------
def assign_teacher(school_id, teacher_user_id, class_id, subject_id, term_id):
    teacher = _get_user(school_id, teacher_user_id)
    if teacher.role != UserRole.teacher:
        raise PeopleError('That user is not a teacher.')
    _get_class(school_id, class_id)
    _get_subject(school_id, subject_id)
    _get_term(school_id, term_id)
    existing = TeacherAssignment.query.filter_by(
        school_id=school_id, teacher_user_id=teacher_user_id,
        class_id=class_id, subject_id=subject_id, term_id=term_id).first()
    if existing:
        raise PeopleError('That teacher is already assigned to this '
                          'class/subject/term.')
    ta = TeacherAssignment(school_id=school_id, teacher_user_id=teacher_user_id,
                           class_id=class_id, subject_id=subject_id,
                           term_id=term_id)
    db.session.add(ta)
    db.session.flush()
    return ta


def unassign_teacher(school_id, assignment_id):
    ta = TeacherAssignment.query.filter_by(
        school_id=school_id, id=assignment_id).first()
    if ta is None:
        raise PeopleError('Assignment not found.')
    db.session.delete(ta)
    db.session.flush()


# ---------------------------------------------------------------------------
# Tenant-scoped getters (raise PeopleError if not in this school)
# ---------------------------------------------------------------------------
def _get_user(school_id, user_id):
    obj = User.query.filter_by(school_id=school_id, id=user_id).first()
    if obj is None:
        raise PeopleError('User not found.')
    return obj


def _get_student(school_id, student_id):
    obj = Student.query.filter_by(school_id=school_id, id=student_id).first()
    if obj is None:
        raise PeopleError('Student not found.')
    return obj


def _get_class(school_id, class_id):
    obj = Class.query.filter_by(school_id=school_id, id=class_id).first()
    if obj is None:
        raise PeopleError('Class not found.')
    return obj


def _get_subject(school_id, subject_id):
    obj = Subject.query.filter_by(school_id=school_id, id=subject_id).first()
    if obj is None:
        raise PeopleError('Subject not found.')
    return obj


def _get_term(school_id, term_id):
    obj = Term.query.filter_by(school_id=school_id, id=term_id).first()
    if obj is None:
        raise PeopleError('Term not found.')
    return obj


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _coerce_role(role):
    if isinstance(role, UserRole):
        return role
    try:
        return UserRole(role)
    except ValueError:
        raise PeopleError(f'Invalid role: {role!r}.')


def _coerce_student_status(status):
    if isinstance(status, StudentStatus):
        return status
    try:
        return StudentStatus(status)
    except ValueError:
        raise PeopleError(f'Invalid status: {status!r}.')


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        return None
