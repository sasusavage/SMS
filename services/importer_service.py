"""
Importer Service for bulk uploading Students and Staff via CSV.
Handles validation, database insertion, and audit logging.
"""
import csv
import io
from datetime import datetime
from models import db, Student, Staff, Parent, Gender, User, UserRole, AuditLog, StudentStatus
from werkzeug.security import generate_password_hash

class ImporterService:
    
    @staticmethod
    def import_students(school_id, user_id, file_content):
        """Processes a CSV file to bulk create students."""
        try:
            stream = io.StringIO(file_content.decode('utf-8'))
            reader = csv.DictReader(stream)
            count = 0
            errors = []
            
            for row in reader:
                try:
                    # Basic validation
                    if not row.get('first_name') or not row.get('last_name'):
                        errors.append(f"Row {count+1}: Missing name.")
                        continue
                    
                    # 1. Create Parent if phone provided
                    parent = None
                    parent_phone = row.get('parent_phone')
                    if parent_phone:
                        parent = Parent.query.filter_by(school_id=school_id, primary_contact_phone=parent_phone).first()
                        if not parent:
                            parent = Parent(
                                school_id=school_id,
                                father_name=row.get('father_name', 'N/A'),
                                primary_contact_phone=parent_phone
                            )
                            db.session.add(parent)
                            db.session.flush()

                    # 2. Create Student
                    student = Student(
                        school_id=school_id,
                        parent_id=parent.id if parent else None,
                        student_id=row.get('student_id', f"STU-{datetime.now().strftime('%y')}{count:04d}"),
                        first_name=row.get('first_name'),
                        last_name=row.get('last_name'),
                        gender=Gender(row.get('gender', 'male').lower()),
                        date_of_birth=datetime.strptime(row.get('dob', '2010-01-01'), '%Y-%m-%d').date(),
                        admission_date=datetime.strptime(row.get('admission_date', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d').date(),
                        status=StudentStatus.ACTIVE
                    )
                    db.session.add(student)
                    count += 1
                    
                except Exception as e:
                    errors.append(f"Row {count+1}: {str(e)}")
            
            # Audit Log
            log = AuditLog(
                school_id=school_id,
                user_id=user_id,
                action='BULK_IMPORT_STUDENTS',
                entity_type='student',
                new_values={'count': count, 'errors': len(errors)}
            )
            db.session.add(log)
            db.session.commit()
            return count, errors
            
        except Exception as e:
            db.session.rollback()
            return 0, [str(e)]

    @staticmethod
    def import_staff(school_id, user_id, file_content):
        """Processes a CSV file to bulk create staff and user accounts."""
        try:
            stream = io.StringIO(file_content.decode('utf-8'))
            reader = csv.DictReader(stream)
            count = 0
            errors = []
            
            for row in reader:
                try:
                    email = row.get('email')
                    if not email:
                        errors.append(f"Row {count+1}: Missing email.")
                        continue
                    
                    if User.query.filter_by(email=email).first():
                        errors.append(f"Row {count+1}: Email already exists.")
                        continue

                    # 1. Create Staff Profile
                    staff = Staff(
                        school_id=school_id,
                        staff_id=row.get('staff_id', f"STA-{count:03d}"),
                        first_name=row.get('first_name'),
                        last_name=row.get('last_name'),
                        gender=Gender(row.get('gender', 'male').lower()),
                        email=email,
                        position=row.get('position', 'Teacher')
                    )
                    db.session.add(staff)
                    db.session.flush()

                    # 2. Create User Account
                    user = User(
                        school_id=school_id,
                        email=email,
                        password_hash=generate_password_hash('password123'),
                        role=UserRole(row.get('role', 'teacher').lower()),
                        staff_id=staff.id
                    )
                    db.session.add(user)
                    count += 1
                    
                except Exception as e:
                    errors.append(f"Row {count+1}: {str(e)}")
            
            # Audit Log
            log = AuditLog(
                school_id=school_id,
                user_id=user_id,
                action='BULK_IMPORT_STAFF',
                entity_type='staff',
                new_values={'count': count, 'errors': len(errors)}
            )
            db.session.add(log)
            db.session.commit()
            return count, errors
            
        except Exception as e:
            db.session.rollback()
            return 0, [str(e)]
