"""
Database Seeder - Create initial data for testing
"""
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import (
    db, School, AcademicYear, Term, Department, Class, Subject, ClassSubject,
    User, UserRole, Staff, Parent, Student, Gender, StudentStatus,
    FeeCategory, FeeStructure, ClassEnrollment
)


def seed_database():
    """Create seed data for the database."""
    app = create_app('development')
    
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        
        # Check if already seeded
        if School.query.first():
            print("Database already seeded. Skipping...")
            return
        
        print("Seeding database with initial data...")
        
        # =====================================================
        # 1. CREATE SCHOOL
        # =====================================================
        school = School(
            name="Sasu Academy",
            motto="Excellence Through Knowledge",
            address="123 Education Lane",
            city="Accra",
            region="Greater Accra",
            phone="+233 24 123 4567",
            email="info@sasuacademy.edu.gh",
            website="www.sasuacademy.edu.gh",
            primary_color="#4F46E5",
            secondary_color="#1E293B",
            established_year=2010,
            school_type="Combined"
        )
        db.session.add(school)
        db.session.flush()
        
        print(f"Created school: {school.name}")
        
        # =====================================================
        # 2. CREATE ACADEMIC YEAR & TERMS
        # =====================================================
        current_year = AcademicYear(
            school_id=school.id,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_current=True
        )
        db.session.add(current_year)
        db.session.flush()
        
        terms = [
            Term(academic_year_id=current_year.id, name="First Term", term_number=1,
                 start_date=date(2025, 9, 1), end_date=date(2025, 12, 20), is_current=True),
            Term(academic_year_id=current_year.id, name="Second Term", term_number=2,
                 start_date=date(2026, 1, 10), end_date=date(2026, 4, 10)),
            Term(academic_year_id=current_year.id, name="Third Term", term_number=3,
                 start_date=date(2026, 5, 1), end_date=date(2026, 7, 31)),
        ]
        db.session.add_all(terms)
        
        print(f"Created academic year: {current_year.name} with 3 terms")
        
        # =====================================================
        # 3. CREATE DEPARTMENTS
        # =====================================================
        departments = [
            Department(school_id=school.id, name="Sciences", code="SCI"),
            Department(school_id=school.id, name="Arts", code="ART"),
            Department(school_id=school.id, name="Languages", code="LANG"),
            Department(school_id=school.id, name="Mathematics", code="MATH"),
        ]
        db.session.add_all(departments)
        db.session.flush()
        
        print(f"Created {len(departments)} departments")
        
        # =====================================================
        # 4. CREATE SUBJECTS
        # =====================================================
        subjects = [
            Subject(school_id=school.id, name="English Language", code="ENG", is_core=True),
            Subject(school_id=school.id, name="Mathematics", code="MATH", is_core=True),
            Subject(school_id=school.id, name="Integrated Science", code="SCI", is_core=True),
            Subject(school_id=school.id, name="Social Studies", code="SOC", is_core=True),
            Subject(school_id=school.id, name="Ghanaian Language (Twi)", code="TWI", is_core=True),
            Subject(school_id=school.id, name="French", code="FRE", is_core=False),
            Subject(school_id=school.id, name="ICT", code="ICT", is_core=True),
            Subject(school_id=school.id, name="Creative Arts", code="CRA", is_core=True),
            Subject(school_id=school.id, name="Religious & Moral Education", code="RME", is_core=True),
            Subject(school_id=school.id, name="Physical Education", code="PE", is_core=False),
        ]
        db.session.add_all(subjects)
        db.session.flush()
        
        print(f"Created {len(subjects)} subjects")
        
        # =====================================================
        # 5. CREATE CLASSES
        # =====================================================
        classes = [
            # Primary
            Class(school_id=school.id, name="Primary 1A", level="Primary", grade_number=1, section="A", capacity=35),
            Class(school_id=school.id, name="Primary 2A", level="Primary", grade_number=2, section="A", capacity=35),
            Class(school_id=school.id, name="Primary 3A", level="Primary", grade_number=3, section="A", capacity=35),
            Class(school_id=school.id, name="Primary 4A", level="Primary", grade_number=4, section="A", capacity=35),
            Class(school_id=school.id, name="Primary 5A", level="Primary", grade_number=5, section="A", capacity=35),
            Class(school_id=school.id, name="Primary 6A", level="Primary", grade_number=6, section="A", capacity=35),
            # JHS
            Class(school_id=school.id, name="JHS 1A", level="JHS", grade_number=1, section="A", capacity=40),
            Class(school_id=school.id, name="JHS 2A", level="JHS", grade_number=2, section="A", capacity=40),
            Class(school_id=school.id, name="JHS 3A", level="JHS", grade_number=3, section="A", capacity=40),
        ]
        db.session.add_all(classes)
        db.session.flush()
        
        print(f"Created {len(classes)} classes")
        
        # =====================================================
        # 6. CREATE STAFF & USERS
        # =====================================================
        # Headteacher
        head_staff = Staff(
            school_id=school.id, staff_id="STF0001", first_name="Kwame", last_name="Asante",
            gender=Gender.MALE, position="Headteacher", phone="0241234567",
            email="headteacher@sasuacademy.edu.gh", date_employed=date(2010, 1, 15)
        )
        db.session.add(head_staff)
        db.session.flush()
        
        head_user = User(
            school_id=school.id, email="headteacher@sasuacademy.edu.gh",
            role=UserRole.HEADTEACHER, staff_id=head_staff.id
        )
        head_user.set_password("admin123")
        db.session.add(head_user)
        
        # Admin
        admin_staff = Staff(
            school_id=school.id, staff_id="STF0002", first_name="Ama", last_name="Mensah",
            gender=Gender.FEMALE, position="Administrator", phone="0242345678",
            email="admin@sasuacademy.edu.gh", date_employed=date(2015, 3, 1)
        )
        db.session.add(admin_staff)
        db.session.flush()
        
        admin_user = User(
            school_id=school.id, email="admin@sasuacademy.edu.gh",
            role=UserRole.ADMIN, staff_id=admin_staff.id
        )
        admin_user.set_password("admin123")
        db.session.add(admin_user)
        
        # Teacher
        teacher_staff = Staff(
            school_id=school.id, staff_id="STF0003", first_name="Kofi", last_name="Owusu",
            gender=Gender.MALE, position="Class Teacher", phone="0243456789",
            email="teacher@sasuacademy.edu.gh", date_employed=date(2018, 9, 1)
        )
        db.session.add(teacher_staff)
        db.session.flush()
        
        teacher_user = User(
            school_id=school.id, email="teacher@sasuacademy.edu.gh",
            role=UserRole.TEACHER, staff_id=teacher_staff.id
        )
        teacher_user.set_password("teacher123")
        db.session.add(teacher_user)
        
        # Accounts Officer
        accounts_staff = Staff(
            school_id=school.id, staff_id="STF0004", first_name="Abena", last_name="Darko",
            gender=Gender.FEMALE, position="Accounts Officer", phone="0244567890",
            email="accounts@sasuacademy.edu.gh", date_employed=date(2020, 1, 15)
        )
        db.session.add(accounts_staff)
        db.session.flush()
        
        accounts_user = User(
            school_id=school.id, email="accounts@sasuacademy.edu.gh",
            role=UserRole.ACCOUNTS_OFFICER, staff_id=accounts_staff.id
        )
        accounts_user.set_password("accounts123")
        db.session.add(accounts_user)
        
        # Assign class teacher
        classes[5].class_teacher_id = teacher_staff.id  # Primary 6A
        
        print("Created 4 staff members with user accounts")
        
        # =====================================================
        # 7. CREATE FEE CATEGORIES
        # =====================================================
        fee_categories = [
            FeeCategory(school_id=school.id, name="Tuition Fee", is_recurring=True),
            FeeCategory(school_id=school.id, name="Examination Fee", is_recurring=True),
            FeeCategory(school_id=school.id, name="ICT Fee", is_recurring=True),
            FeeCategory(school_id=school.id, name="PTA Dues", is_recurring=True),
            FeeCategory(school_id=school.id, name="Development Levy", is_recurring=False),
        ]
        db.session.add_all(fee_categories)
        db.session.flush()
        
        print(f"Created {len(fee_categories)} fee categories")
        
        # =====================================================
        # 8. CREATE FEE STRUCTURES
        # =====================================================
        for cls in classes:
            base_tuition = 500 if 'Primary' in cls.name else 800
            
            structures = [
                FeeStructure(school_id=school.id, class_id=cls.id, academic_year_id=current_year.id,
                            fee_category_id=fee_categories[0].id, amount=Decimal(base_tuition), term_applicable=None),
                FeeStructure(school_id=school.id, class_id=cls.id, academic_year_id=current_year.id,
                            fee_category_id=fee_categories[1].id, amount=Decimal('50'), term_applicable=None),
                FeeStructure(school_id=school.id, class_id=cls.id, academic_year_id=current_year.id,
                            fee_category_id=fee_categories[2].id, amount=Decimal('30'), term_applicable=None),
            ]
            db.session.add_all(structures)
        
        print("Created fee structures for all classes")
        
        # =====================================================
        # 9. CREATE SAMPLE STUDENTS WITH PARENT ACCOUNTS
        # =====================================================
        sample_students = [
            {"first_name": "Kweku", "last_name": "Appiah", "gender": Gender.MALE, "dob": date(2015, 3, 15)},
            {"first_name": "Adwoa", "last_name": "Boateng", "gender": Gender.FEMALE, "dob": date(2015, 7, 22)},
            {"first_name": "Yaw", "last_name": "Frimpong", "gender": Gender.MALE, "dob": date(2014, 11, 8)},
            {"first_name": "Akosua", "last_name": "Osei", "gender": Gender.FEMALE, "dob": date(2015, 1, 30)},
            {"first_name": "Kofi", "last_name": "Mensah", "gender": Gender.MALE, "dob": date(2014, 9, 5)},
        ]
        
        parent_users = []  # Store parent user info for printing
        
        for i, data in enumerate(sample_students):
            parent_email = f"parent{i+1}@sasuacademy.edu.gh"
            
            parent = Parent(
                school_id=school.id,
                father_name=f"Mr. {data['last_name']}",
                father_phone=f"024{i+1}000000",
                father_email=parent_email,
                mother_name=f"Mrs. {data['last_name']}",
                mother_phone=f"024{i+1}111111",
                address="123 Main Street, Accra",
                primary_contact_phone=f"024{i+1}000000"
            )
            db.session.add(parent)
            db.session.flush()
            
            # Create parent user account for login
            parent_user = User(
                school_id=school.id,
                email=parent_email,
                role=UserRole.PARENT,
                parent_id=parent.id
            )
            parent_user.set_password("parent123")
            db.session.add(parent_user)
            
            parent_users.append(f"Parent {i+1}: {parent_email} / parent123 (child: {data['first_name']} {data['last_name']})")
            
            student = Student(
                school_id=school.id,
                parent_id=parent.id,
                student_id=f"STU001{i+1:04d}",
                first_name=data['first_name'],
                last_name=data['last_name'],
                gender=data['gender'],
                date_of_birth=data['dob'],
                admission_date=date(2024, 9, 1),
                nationality="Ghanaian",
                status=StudentStatus.ACTIVE
            )
            db.session.add(student)
            db.session.flush()
            
            # Enroll in Primary 6A
            enrollment = ClassEnrollment(
                student_id=student.id,
                class_id=classes[5].id,  # Primary 6A
                academic_year_id=current_year.id,
                enrollment_date=date(2024, 9, 1)
            )
            db.session.add(enrollment)
        
        print(f"Created {len(sample_students)} sample students with parent accounts")
        
        # =====================================================
        # 10. ASSIGN SUBJECTS TO CLASS
        # =====================================================
        for subj in subjects[:7]:  # Core subjects
            cs = ClassSubject(
                class_id=classes[5].id,  # Primary 6A
                subject_id=subj.id,
                teacher_id=teacher_staff.id,
                academic_year_id=current_year.id
            )
            db.session.add(cs)
        
        print("Assigned subjects to Primary 6A")
        
        # Commit all changes
        db.session.commit()
        
        print("\n" + "="*50)
        print("DATABASE SEEDED SUCCESSFULLY!")
        print("="*50)
        print("\nStaff Login credentials:")
        print("-" * 30)
        print("Headteacher: headteacher@sasuacademy.edu.gh / admin123")
        print("Admin:       admin@sasuacademy.edu.gh / admin123")
        print("Teacher:     teacher@sasuacademy.edu.gh / teacher123")
        print("Accounts:    accounts@sasuacademy.edu.gh / accounts123")
        print("\n" + "-"*30)
        print("Parent Login credentials:")
        print("-" * 30)
        for pu in parent_users:
            print(pu)
        print("="*50)


if __name__ == '__main__':
    seed_database()
