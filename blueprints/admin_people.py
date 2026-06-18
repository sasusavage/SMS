"""
/admin — people management (Step 3): users, students (+ CSV import),
parent-student links, teacher assignments. school_admin only, tenant-scoped.

Risky logic is delegated to services/people.py; routes handle HTTP, flash the
PeopleError.message, and audit. Cross-tenant access surfaces as 404 via
get_tenant_or_404 / the service's tenant-scoped getters.
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g, abort,
    session,
)
from flask_login import login_required

from extensions import db
from auth.security import require_role
from services.tenant import tenant_query, get_tenant_or_404
from services.audit import log_action
from services import people
from services.people import PeopleError
from models.enums import UserRole, StudentStatus
from models.operational import (
    User, Student, ParentStudent, TeacherAssignment,
)
from models.config_tables import Class, Subject, Term

people_bp = Blueprint('admin_people', __name__, url_prefix='/admin')


@people_bp.before_request
@login_required
@require_role('school_admin')
def _guard():
    if g.get('current_school_id') is None:
        abort(403)


def _sid():
    return g.current_school_id


def _commit_audit(action, entity, entity_id=None, meta=None):
    log_action(action, entity=entity, entity_id=entity_id, meta=meta)
    db.session.commit()


# ===========================================================================
# Users (teachers / parents)
# ===========================================================================
@people_bp.route('/users', methods=['GET', 'POST'])
def users():
    if request.method == 'POST':
        try:
            user, generated = people.create_user(
                _sid(), name=request.form.get('name'),
                email=request.form.get('email'),
                role=request.form.get('role'),
                password=request.form.get('password') or None,
                phone=request.form.get('phone'))
            _commit_audit('create', 'user', user.id)
            # Welcome email with login info (best-effort).
            from services import notify
            notify.notify_account_created(_sid(), user,
                                          plaintext_password=generated)
            if generated:
                flash(f'User created. Temporary password: {generated}', 'success')
            else:
                flash('User created.', 'success')
        except PeopleError as e:
            db.session.rollback()
            flash(e.message, 'danger')
        return redirect(url_for('admin_people.users'))

    # Only show teachers/parents/admins managed here (not students).
    managed = (tenant_query(User)
               .filter(User.role.in_([UserRole.teacher, UserRole.parent,
                                      UserRole.school_admin]))
               .order_by(User.name).all())
    return render_template('admin/people/users.html', users=managed,
                           roles=['teacher', 'parent', 'school_admin'])


@people_bp.route('/users/<int:user_id>/edit', methods=['POST'])
def edit_user(user_id):
    try:
        people.update_user(_sid(), user_id, name=request.form.get('name'),
                           email=request.form.get('email'),
                           phone=request.form.get('phone'))
        _commit_audit('edit', 'user', user_id)
        flash('User updated.', 'success')
    except PeopleError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_people.users'))


@people_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
def reset_password(user_id):
    try:
        new_pw = people.reset_password(_sid(), user_id,
                                       request.form.get('password') or None)
        _commit_audit('reset_password', 'user', user_id)
        flash(f'Password reset. New password: {new_pw}', 'success')
    except PeopleError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_people.users'))


@people_bp.route('/users/<int:user_id>/toggle-active', methods=['POST'])
def toggle_active(user_id):
    try:
        user = get_tenant_or_404(User, user_id)
        people.set_user_active(_sid(), user_id, not user.is_active)
        _commit_audit('toggle_active', 'user', user_id)
        flash('User updated.', 'info')
    except PeopleError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_people.users'))


# ===========================================================================
# Students
# ===========================================================================
@people_bp.route('/students', methods=['GET', 'POST'])
def students():
    classes = tenant_query(Class).order_by(Class.name).all()
    if request.method == 'POST':
        try:
            st = people.create_student(
                _sid(), admission_no=request.form.get('admission_no'),
                first_name=request.form.get('first_name'),
                last_name=request.form.get('last_name'),
                other_names=request.form.get('other_names'),
                gender=request.form.get('gender'),
                dob=people._parse_date(request.form.get('dob')),
                current_class_id=_int(request.form.get('current_class_id')),
                guardian_name=request.form.get('guardian_name'),
                guardian_phone=request.form.get('guardian_phone'))
            _commit_audit('create', 'student', st.id)
            flash('Student added.', 'success')
        except PeopleError as e:
            db.session.rollback()
            flash(e.message, 'danger')
        return redirect(url_for('admin_people.students'))

    all_students = (tenant_query(Student)
                    .order_by(Student.last_name, Student.first_name).all())
    return render_template('admin/people/students.html',
                           students=all_students, classes=classes,
                           StudentStatus=StudentStatus)


@people_bp.route('/students/<int:student_id>')
def student_detail(student_id):
    student = get_tenant_or_404(Student, student_id)
    classes = tenant_query(Class).order_by(Class.name).all()
    parents = (tenant_query(User).filter(User.role == UserRole.parent)
               .order_by(User.name).all())
    links = (tenant_query(ParentStudent)
             .filter_by(student_id=student_id).all())
    terms = tenant_query(Term).order_by(Term.sequence).all()
    return render_template('admin/people/student_detail.html',
                           student=student, classes=classes, parents=parents,
                           links=links, terms=terms)


@people_bp.route('/students/<int:student_id>/edit', methods=['POST'])
def edit_student(student_id):
    try:
        people.update_student(
            _sid(), student_id,
            admission_no=request.form.get('admission_no'),
            first_name=request.form.get('first_name'),
            last_name=request.form.get('last_name'),
            other_names=request.form.get('other_names'),
            gender=request.form.get('gender'),
            dob=people._parse_date(request.form.get('dob')),
            guardian_name=request.form.get('guardian_name'),
            guardian_phone=request.form.get('guardian_phone'))
        _commit_audit('edit', 'student', student_id)
        flash('Student details updated.', 'success')
    except PeopleError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_people.student_detail', student_id=student_id))


@people_bp.route('/students/<int:student_id>/photo', methods=['POST'])
def upload_student_photo(student_id):
    from services import uploads
    from services.uploads import UploadError
    student = get_tenant_or_404(Student, student_id)
    try:
        old = student.photo_path
        rel = uploads.save_upload(request.files.get('photo'), _sid(), 'photo',
                                  images_only=True)
        student.photo_path = rel
        _commit_audit('upload_photo', 'student', student_id)
        if old:
            uploads.delete_upload(old)
        flash('Photo updated.', 'success')
    except UploadError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_people.student_detail', student_id=student_id))


@people_bp.route('/students/<int:student_id>/transfer', methods=['POST'])
def transfer_student(student_id):
    try:
        people.transfer_student(_sid(), student_id,
                                _int(request.form.get('current_class_id')))
        _commit_audit('transfer', 'student', student_id)
        flash('Student class updated.', 'info')
    except PeopleError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_people.student_detail', student_id=student_id))


@people_bp.route('/students/<int:student_id>/status', methods=['POST'])
def student_status(student_id):
    try:
        people.set_student_status(_sid(), student_id,
                                  request.form.get('status'))
        _commit_audit('set_status', 'student', student_id)
        flash('Status updated.', 'info')
    except PeopleError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_people.student_detail', student_id=student_id))


# --- Parent linking (from the student detail page) -------------------------
@people_bp.route('/students/<int:student_id>/link-parent', methods=['POST'])
def link_parent(student_id):
    try:
        people.link_parent_student(
            _sid(), _int(request.form.get('parent_user_id')), student_id,
            request.form.get('relationship'))
        _commit_audit('link_parent', 'student', student_id)
        flash('Parent linked.', 'success')
    except PeopleError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_people.student_detail', student_id=student_id))


@people_bp.route('/parent-links/<int:link_id>/delete', methods=['POST'])
def unlink_parent(link_id):
    link = get_tenant_or_404(ParentStudent, link_id)
    student_id = link.student_id
    try:
        people.unlink_parent_student(_sid(), link_id)
        _commit_audit('unlink_parent', 'student', student_id)
        flash('Parent unlinked.', 'info')
    except PeopleError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_people.student_detail', student_id=student_id))


# --- CSV import: upload -> preview -> commit -------------------------------
@people_bp.route('/students/import', methods=['GET', 'POST'])
def import_students():
    classes = tenant_query(Class).order_by(Class.name).all()
    if request.method == 'POST':
        file = request.files.get('csv_file')
        class_id = _int(request.form.get('class_id'))
        if not file or not file.filename:
            flash('Please choose a CSV file.', 'danger')
            return redirect(url_for('admin_people.import_students'))
        try:
            text = file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            flash('File must be UTF-8 encoded CSV.', 'danger')
            return redirect(url_for('admin_people.import_students'))

        preview = people.parse_student_csv(_sid(), text, class_id)
        # Stash the raw text in the session so commit re-validates the same data.
        session['csv_import_text'] = text
        session['csv_import_class_id'] = class_id
        return render_template('admin/people/import_preview.html',
                               preview=preview, classes=classes,
                               class_id=class_id,
                               columns=people.CSV_COLUMNS)

    return render_template('admin/people/import_upload.html', classes=classes,
                           columns=people.CSV_COLUMNS)


@people_bp.route('/students/import/commit', methods=['POST'])
def import_students_commit():
    text = session.get('csv_import_text')
    class_id = session.get('csv_import_class_id')
    if not text:
        flash('Nothing to import — please upload a file first.', 'warning')
        return redirect(url_for('admin_people.import_students'))
    try:
        result = people.commit_student_csv(_sid(), text, class_id)
        _commit_audit('csv_import', 'student', None, meta=result)
        flash(f'Imported {result["imported"]} students '
              f'({result["skipped"]} skipped).', 'success')
    except PeopleError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    finally:
        session.pop('csv_import_text', None)
        session.pop('csv_import_class_id', None)
    return redirect(url_for('admin_people.students'))


# ===========================================================================
# Teacher assignments
# ===========================================================================
@people_bp.route('/assignments', methods=['GET', 'POST'])
def assignments():
    teachers = (tenant_query(User).filter(User.role == UserRole.teacher)
                .order_by(User.name).all())
    classes = tenant_query(Class).order_by(Class.name).all()
    subjects = tenant_query(Subject).order_by(Subject.name).all()
    terms = tenant_query(Term).order_by(Term.sequence).all()

    if request.method == 'POST':
        try:
            people.assign_teacher(
                _sid(), _int(request.form.get('teacher_user_id')),
                _int(request.form.get('class_id')),
                _int(request.form.get('subject_id')),
                _int(request.form.get('term_id')))
            _commit_audit('assign_teacher', 'teacher_assignment')
            flash('Teacher assigned.', 'success')
        except PeopleError as e:
            db.session.rollback()
            flash(e.message, 'danger')
        return redirect(url_for('admin_people.assignments'))

    all_assignments = tenant_query(TeacherAssignment).all()
    return render_template('admin/people/assignments.html',
                           assignments=all_assignments, teachers=teachers,
                           classes=classes, subjects=subjects, terms=terms)


@people_bp.route('/assignments/<int:assignment_id>/delete', methods=['POST'])
def delete_assignment(assignment_id):
    get_tenant_or_404(TeacherAssignment, assignment_id)
    try:
        people.unassign_teacher(_sid(), assignment_id)
        _commit_audit('unassign_teacher', 'teacher_assignment', assignment_id)
        flash('Assignment removed.', 'info')
    except PeopleError as e:
        db.session.rollback()
        flash(e.message, 'danger')
    return redirect(url_for('admin_people.assignments'))


def _int(v):
    try:
        return int(v) if v not in (None, '') else None
    except (TypeError, ValueError):
        return None
