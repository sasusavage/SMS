"""
Student Management Services
Handles all business logic, database transactions, and audit logging for Students.
"""
from models import (
    db, Student, Parent, ClassEnrollment, 
    AcademicYear, StudentStatus, Gender, User, UserRole, AuditLog
)
from datetime import date, datetime
from flask import g
from werkzeug.security import generate_password_hash

class StudentService:
    
    @staticmethod
    def _log_action(school_id, user_id, action, entity_type, entity_id, old_values=None, new_values=None):
        """Helper to safely record audit logs within a school scope."""
        try:
            log = AuditLog(
                school_id=school_id,
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_values=old_values,
                new_values=new_values
            )
            db.session.add(log)
        except Exception:
            pass # Never let audit log failure break the main transaction

    @staticmethod
    def create_student_with_parent(school_id, user_id, data, current_academic_year=None):
        """Creates a parent, and student, and enrolls them if class provided."""
        try:
            # 1. Generate unique student ID
            count = Student.query.filter_by(school_id=school_id).count()
            student_id = f"STU{school_id:03d}{count + 1:04d}"
            
            # 2. Create Parent Record
            parent = Parent(
                school_id=school_id,
                father_name=data.get('father_name'),
                father_phone=data.get('father_phone'),
                father_occupation=data.get('father_occupation'),
                mother_name=data.get('mother_name'),
                mother_phone=data.get('mother_phone'),
                mother_occupation=data.get('mother_occupation'),
                guardian_name=data.get('guardian_name'),
                guardian_phone=data.get('guardian_phone'),
                guardian_relationship=data.get('guardian_relationship'),
                address=data.get('address'),
                city=data.get('city'),
                region=data.get('region'),
                primary_contact_phone=data.get('guardian_phone') or data.get('father_phone')
            )
            db.session.add(parent)
            db.session.flush() # Need parent id for student
            
            # 3. Create Student Record
            dob_str = data.get('date_of_birth')
            dob = date.fromisoformat(dob_str) if dob_str else None
            
            student = Student(
                school_id=school_id,
                parent_id=parent.id,
                student_id=student_id,
                first_name=data.get('first_name'),
                last_name=data.get('last_name'),
                other_names=data.get('other_names'),
                gender=Gender(data.get('gender')),
                date_of_birth=dob,
                nationality=data.get('nationality', 'Ghanaian'),
                place_of_birth=data.get('place_of_birth'),
                hometown=data.get('hometown'),
                religion=data.get('religion'),
                blood_group=data.get('blood_group'),
                allergies=data.get('allergies'),
                medical_conditions=data.get('medical_conditions'),
                admission_date=date.today(),
                previous_school=data.get('previous_school'),
                status=StudentStatus.ACTIVE
            )
            db.session.add(student)
            db.session.flush() # Need student id for enrollment & audit
            
            # 4. Optional class enrollment
            class_id = data.get('class_id')
            if class_id and str(class_id).isdigit() and current_academic_year:
                enrollment = ClassEnrollment(
                    student_id=student.id,
                    class_id=int(class_id),
                    academic_year_id=current_academic_year.id,
                    enrollment_date=date.today()
                )
                db.session.add(enrollment)
                
            # 5. Audit Logging
            StudentService._log_action(
                school_id=school_id,
                user_id=user_id,
                action='CREATE_STUDENT',
                entity_type='student',
                entity_id=student.id,
                new_values={
                    'full_name': student.full_name,
                    'student_id': student.student_id,
                    'class_id': class_id
                }
            )

            db.session.commit()
            return student, None
            
        except Exception as e:
            db.session.rollback()
            return None, str(e)


    @staticmethod
    def update_student(student_id, school_id, user_id, data):
        """Updates student and parent info."""
        try:
            student = Student.query.get(student_id)
            if not student or student.school_id != school_id:
                return None, "Student not found or access denied."
            
            # Old state for audit logging
            old_values = {
                'first_name': student.first_name,
                'last_name': student.last_name,
                'status': student.status.value
            }
            
            # Update student
            student.first_name = data.get('first_name')
            student.last_name = data.get('last_name')
            student.other_names = data.get('other_names')
            student.gender = Gender(data.get('gender'))
            
            dob_str = data.get('date_of_birth')
            if dob_str:
                student.date_of_birth = date.fromisoformat(dob_str)
            
            student.nationality = data.get('nationality')
            student.place_of_birth = data.get('place_of_birth')
            student.hometown = data.get('hometown')
            student.religion = data.get('religion')
            student.blood_group = data.get('blood_group')
            student.allergies = data.get('allergies')
            student.medical_conditions = data.get('medical_conditions')
            
            # Update parent info
            if student.parent:
                student.parent.father_name = data.get('father_name')
                student.parent.father_phone = data.get('father_phone')
                student.parent.mother_name = data.get('mother_name')
                student.parent.mother_phone = data.get('mother_phone')
                student.parent.guardian_name = data.get('guardian_name')
                student.parent.guardian_phone = data.get('guardian_phone')
                student.parent.address = data.get('address')
                
            # Audit log
            new_values = {
                'first_name': student.first_name,
                'last_name': student.last_name,
                'status': student.status.value
            }
            StudentService._log_action(school_id, user_id, 'UPDATE_STUDENT', 'student', student.id, old_values, new_values)

            db.session.commit()
            return student, None
            
        except Exception as e:
            db.session.rollback()
            return None, str(e)
            
            
    @staticmethod
    def enroll_student(student_id, class_id, current_academic_year, user_id):
        """Enrolls student in a class."""
        try:
            if not current_academic_year:
                return False, "No active academic year found."
                
            existing = ClassEnrollment.query.filter_by(
                student_id=student_id,
                academic_year_id=current_academic_year.id
            ).first()
            
            old_class = existing.class_id if existing else None
            
            if existing:
                existing.class_id = class_id
                action = 'UPDATE_ENROLLMENT'
            else:
                enrollment = ClassEnrollment(
                    student_id=student_id,
                    class_id=class_id,
                    academic_year_id=current_academic_year.id,
                    enrollment_date=date.today()
                )
                db.session.add(enrollment)
                action = 'CREATE_ENROLLMENT'
                
            StudentService._log_action(
                user_id, action, 'class_enrollment', student_id, 
                old_values={'class_id': old_class}, 
                new_values={'class_id': class_id}
            )
            
            db.session.commit()
            return True, None
            
        except Exception as e:
            db.session.rollback()
            return False, str(e)


    @staticmethod
    def create_parent_account(student_id, school_id, password, user_id):
        """Creates a login account for the parent."""
        try:
            student = Student.query.get(student_id)
            if not student or student.school_id != school_id or not student.parent:
                return False, "Invalid student or missing parent info."
                
            parent = student.parent
            if parent.user:
                return False, "Parent already has an account."
                
            if len(str(password)) < 6:
                return False, "Password must be at least 6 characters."

            # Generate email
            email = parent.father_email or parent.mother_email or parent.guardian_email
            if not email:
                phone = parent.primary_contact_phone or parent.father_phone or parent.mother_phone
                email = f"parent_{phone}@school.local"
            
            if User.query.filter_by(email=email).first():
                email = f"parent_{parent.id}@school.local"
            
            new_user = User(
                school_id=school_id,
                email=email,
                role=UserRole.PARENT,
                parent_id=parent.id
            )
            new_user.set_password(password)
            db.session.add(new_user)
            
            StudentService._log_action(user_id, 'CREATE_PARENT_ACCOUNT', 'user', None, new_values={'email': email})

            db.session.commit()
            return True, None
            
        except Exception as e:
            db.session.rollback()
            return False, str(e)
