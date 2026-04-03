"""
RESEED DATABASE - Final Production-Ready Script
Wipes all data and re-seeds with fresh credentials.
"""
import os
import sys
from datetime import date, datetime
from decimal import Decimal

from dotenv import load_dotenv
load_dotenv()

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import (
    db, School, AcademicYear, Term, Department, Class, Subject, ClassSubject,
    User, UserRole, Staff, Parent, Student, Gender, StudentStatus,
    FeeCategory, FeeStructure, ClassEnrollment, init_db
)

def fix_url(url):
    if url and url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql://', 1)
    return url

def reseed():
    """Drops all tables/views and recreates everything from scratch."""
    app = create_app('development')
    app.config['SQLALCHEMY_DATABASE_URI'] = fix_url(app.config.get('SQLALCHEMY_DATABASE_URI', ''))
    
    with app.app_context():
        print("--- [WARNING] PURGING DATABASE ---")
        from sqlalchemy import text
        try:
            # Drop everything in public schema (including views, types, tables)
            db.session.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
            db.session.commit()
            print("Database purged (CASCADE).")
        except Exception as e:
            db.session.rollback()
            print(f"Purge failed: {e}")
            # Fallback to standard drop_all if cascade fails
            db.drop_all()
        
        # init_db(app) also runs db.create_all() and creates views
        init_db(app)
        
        print("\n--- Seeding New School & Configuration ---")
        school = School(
            name="NaCCA Excellence International",
            motto="Education for the Future",
            address="P.O. Box GP 123, Accra Ghana",
            city="Accra",
            region="Greater Accra",
            phone="+233 50 000 0000",
            email="contact@school.com",
            website="www.school.com",
            primary_color="#4F46E5",
            secondary_color="#1E293B",
            established_year=2024,
            school_type="Combined"
        )
        db.session.add(school)
        db.session.flush()
        
        # Academic Year
        ay = AcademicYear(
            school_id=school.id,
            name="2024/2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 7, 31),
            is_current=True
        )
        db.session.add(ay)
        db.session.flush()
        
        # Terms
        term1 = Term(academic_year_id=ay.id, name="First Term", term_number=1,
                    start_date=date(2024, 9, 1), end_date=date(2025, 12, 15), is_current=True)
        db.session.add(term1)
        db.session.flush()

        # Departments
        sc_dept = Department(school_id=school.id, name="Science & Math", code="SCM")
        db.session.add(sc_dept)
        db.session.flush()

        classes = [
            Class(school_id=school.id, name="Primary 6", level="Primary", grade_number=6, section="A", capacity=40),
            Class(school_id=school.id, name="JHS 1", level="JHS", grade_number=1, section="A", capacity=40)
        ]
        db.session.add_all(classes)
        db.session.flush()

        print("\n--- Seeding Users with Requested Credentials ---")
        
        # Password for all: admin123
        passwd = "admin123"

        def create_staff_user(first, last, email, role, pos):
            staff = Staff(
                school_id=school.id, staff_id=f"STF-{first[0]}{last[0]}-{role}01".upper(),
                first_name=first, last_name=last, gender=Gender.MALE, position=pos,
                email=email, date_employed=date(2024, 1, 1)
            )
            db.session.add(staff)
            db.session.flush()
            
            user = User(school_id=school.id, email=email, role=role, staff_id=staff.id)
            user.set_password(passwd)
            db.session.add(user)
            return staff, user

        # 1. Super Admin
        create_staff_user("Super", "Admin", "superadmin@school.com", UserRole.SUPER_ADMIN, "System Owner")
        
        # 2. Headteacher
        create_staff_user("Kofi", "Annan", "headteacher@school.com", UserRole.HEADTEACHER, "Headteacher")
        
        # 3. Admin
        create_staff_user("James", "Bond", "admin@school.com", UserRole.ADMIN, "Admin Assistant")
        
        # 4. Teacher
        teacher_staff, _ = create_staff_user("Nana", "Yaw", "teacher@school.com", UserRole.TEACHER, "Class Teacher")
        
        # 5. Accounts
        create_staff_user("Mary", "Jane", "accounts@school.com", UserRole.ACCOUNTS_OFFICER, "Accounts Officer")
        
        # 6. Parent
        parent = Parent(
            school_id=school.id, father_name="Mr. Parent", primary_contact_phone="0501112223",
            father_email="parent@school.com", mother_name="Mrs. Parent"
        )
        db.session.add(parent)
        db.session.flush()
        
        parent_user = User(school_id=school.id, email="parent@school.com", role=UserRole.PARENT, parent_id=parent.id)
        parent_user.set_password(passwd)
        db.session.add(parent_user)
        
        # Assign teacher to Primary 6
        classes[0].class_teacher_id = teacher_staff.id

        # Sample Student
        stu = Student(
            school_id=school.id, parent_id=parent.id, student_id="STU001",
            first_name="Junior", last_name="Parent", gender=Gender.MALE,
            date_of_birth=date(2013, 5, 20), admission_date=date(2024, 9, 1),
            status=StudentStatus.ACTIVE
        )
        db.session.add(stu)
        db.session.flush()
        
        # Enrollment
        db.session.add(ClassEnrollment(
            student_id=stu.id, class_id=classes[0].id, academic_year_id=ay.id, 
            enrollment_date=date(2024, 9, 1)
        ))

        db.session.commit()
        
        print("\n" + "="*60)
        print("DATABASE RESEEDED SUCCESSFULLY")
        print("="*60)
        print(f"URL: {app.config['SQLALCHEMY_DATABASE_URI']}")
        print("\nCREDENTIALS (Password for all: admin123):")
        print("1. Super Admin:  superadmin@school.com")
        print("2. Headteacher:  headteacher@school.com")
        print("3. Admin:        admin@school.com")
        print("4. Teacher:      teacher@school.com")
        print("5. Accounts:     accounts@school.com")
        print("6. Parent:       parent@school.com")
        print("="*60)

if __name__ == "__main__":
    reseed()
