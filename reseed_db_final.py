"""
SmartSchool SaaS — Production Reseed v3.0
Creates three-tier demo tenants (Basic / Standard / Elite) with full mock data.

WARNING: Drops and recreates the public schema. Never run on production data.
"""
import os
import sys
import random
import uuid as uuid_pkg
from datetime import date, datetime, timedelta
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import (
    db, School, AcademicYear, Term, Department, Class, Subject, ClassSubject,
    User, UserRole, Staff, Parent, Student, Gender, StudentStatus,
    ClassEnrollment, SubscriptionPlan, Subscription, SchoolSetting,
    FeeCategory, FeeStructure, FeeInvoice, FeeInvoiceItem, Payment,
    PaymentMethod, PaymentStatus, Assessment, TerminalReport,
    Attendance, AttendanceStatus, Expense,
    AICreditUsage, AIBotConfig, ModuleConfig, SchoolInsight, AICorrection,
    Product, ProductCategory, AuditLog, init_db
)

# ---------------------------------------------------------------------------
# Mock data pools
# ---------------------------------------------------------------------------
FIRST_NAMES_M = ["Kwame", "Kofi", "Yaw", "Kweku", "Nana", "Ato", "Ebo", "Kojo",
                  "Fiifi", "Nii", "Sasu", "Ama", "Abena", "Adjoa", "Akua"]
FIRST_NAMES_F = ["Ama", "Abena", "Adjoa", "Akua", "Efua", "Araba", "Adwoa", "Afia",
                  "Maame", "Serwaa", "Yaa", "Gifty", "Grace", "Patience", "Naomi"]
LAST_NAMES    = ["Mensah", "Asante", "Boateng", "Owusu", "Amoah", "Darko", "Frimpong",
                  "Antwi", "Osei", "Ofori", "Sarpong", "Acheampong", "Appiah", "Bonsu"]
REGIONS       = ["Greater Accra", "Ashanti", "Eastern", "Western", "Central",
                  "Northern", "Volta", "Brong-Ahafo"]
CITIES        = ["Accra", "Kumasi", "Cape Coast", "Takoradi", "Tamale", "Ho", "Sunyani"]

def rname(gender=None):
    """Generate a random Ghanaian name."""
    if gender == Gender.FEMALE or (gender is None and random.random() > 0.5):
        return random.choice(FIRST_NAMES_F), random.choice(LAST_NAMES), Gender.FEMALE
    return random.choice(FIRST_NAMES_M), random.choice(LAST_NAMES), Gender.MALE

def rand_phone():
    return f"02{random.randint(0,9)}{random.randint(1000000,9999999)}"

def rand_dob(min_age=5, max_age=18):
    years_ago = random.randint(min_age, max_age)
    return date.today().replace(year=date.today().year - years_ago) - timedelta(days=random.randint(0, 364))


# ---------------------------------------------------------------------------
def reseed():
    app = create_app('development')
    with app.app_context():
        print("=== PURGING DATABASE ===")
        from sqlalchemy import text
        db.session.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        db.session.commit()
        init_db(app)

        # ----------------------------------------------------------------
        # 1. Subscription Plans
        # ----------------------------------------------------------------
        plan_basic = SubscriptionPlan(
            name="Basic", price=Decimal('49.00'), student_limit=100,
            features={'core': True, 'reports': True}
        )
        plan_standard = SubscriptionPlan(
            name="Standard", price=Decimal('149.00'), student_limit=500,
            features={'core': True, 'reports': True, 'fees': True, 'sms': True}
        )
        plan_elite = SubscriptionPlan(
            name="Elite", price=Decimal('499.00'), student_limit=5000,
            features={'all': True, 'ai': True, 'marketplace': True,
                      'predictive': True, 'voice': True}
        )
        db.session.add_all([plan_basic, plan_standard, plan_elite])
        db.session.flush()

        # ----------------------------------------------------------------
        # 2. Super Admin (platform owner)
        # ----------------------------------------------------------------
        sa_school = School(
            name="SmartSchool SaaS HQ",
            email="superadmin@smartschool.com",
            motto="Powering Ghanaian Education",
            school_type="SaaS Platform"
        )
        db.session.add(sa_school)
        db.session.flush()
        sa_user = User(school_id=sa_school.id, email="superadmin@smartschool.com",
                       role=UserRole.SUPER_ADMIN)
        sa_user.set_password("smart_saas_2026")
        db.session.add(sa_user)
        db.session.add(ModuleConfig(school_id=sa_school.id, is_ai_enabled=True,
                                     is_sms_enabled=True, is_finance_enabled=True))
        db.session.flush()

        # ----------------------------------------------------------------
        # 3. Provision three demo schools
        # ----------------------------------------------------------------
        demo_schools = [
            {
                "name": "Village Hope Basic School",
                "city": "Kumasi", "region": "Ashanti",
                "plan": plan_basic, "tier": "basic",
                "student_count": 60,
                "levels": ["Primary"],
                "admin_email": "admin@villagehope.edu.gh",
                "whatsapp_id": None,
            },
            {
                "name": "Accra Standard Academy",
                "city": "Accra", "region": "Greater Accra",
                "plan": plan_standard, "tier": "standard",
                "student_count": 180,
                "levels": ["Primary", "JHS"],
                "admin_email": "admin@accrastandard.edu.gh",
                "whatsapp_id": None,
            },
            {
                "name": "Elite Premier International School",
                "city": "Accra", "region": "Greater Accra",
                "plan": plan_elite, "tier": "elite",
                "student_count": 350,
                "levels": ["Kindergarten", "Primary", "JHS", "SHS"],
                "admin_email": "admin@elitepremier.edu.gh",
                "whatsapp_id": "WH-ELITE-PREM-2026",
            },
        ]

        for sd in demo_schools:
            print(f"\n--- Seeding: {sd['name']} ({sd['tier'].upper()}) ---")
            _seed_school(db, sd)

        db.session.commit()
        print("\n=== SmartSchool SaaS Production Seed Complete! ===")
        _print_credentials()


# ---------------------------------------------------------------------------
def _seed_school(db, sd):
    """Fully provision a single school tenant."""
    plan = sd["plan"]
    features = plan.features

    school = School(
        name=sd["name"],
        email=sd["admin_email"],
        city=sd["city"],
        region=sd["region"],
        phone=rand_phone(),
        motto=f"Excellence through {sd['tier'].title()} Education",
        school_type=" & ".join(sd["levels"]),
        established_year=random.randint(1990, 2010),
        sms_credits=500 if sd["tier"] == "elite" else 100,
    )
    db.session.add(school)
    db.session.flush()

    # Subscription
    db.session.add(Subscription(school_id=school.id, plan_id=plan.id, status='active',
                                 end_date=date.today().replace(year=date.today().year + 1)))

    # Module Config
    mc = ModuleConfig(
        school_id=school.id,
        is_ai_enabled="ai" in features or "all" in features,
        is_sms_enabled="sms" in features or "all" in features,
        is_finance_enabled="fees" in features or "all" in features,
        is_qr_scanner_enabled="all" in features,
        is_predictive_ai_enabled="predictive" in features or "all" in features,
        is_marketplace_enabled="marketplace" in features or "all" in features,
        is_voice_ai_enabled="voice" in features or "all" in features,
        is_pwa_enabled=True,
    )
    db.session.add(mc)

    # School Settings
    db.session.add(SchoolSetting(
        school_id=school.id,
        sms_enabled=mc.is_sms_enabled,
        sms_sender_id=school.name[:11].replace(' ', ''),
        ai_bot_enabled=mc.is_ai_enabled,
        whatsapp_business_id=sd.get("whatsapp_id"),
        whatsapp_enabled=sd.get("whatsapp_id") is not None,
    ))

    if mc.is_ai_enabled:
        db.session.add(AIBotConfig(
            school_id=school.id,
            knowledge_base=(
                "NaCCA grading enabled. Parent portal available via WhatsApp. "
                "Fee payments via Paystack. Voice notes supported in English, Twi, Pidgin."
            ),
            model_name="llama3-70b-8192",
            temperature=0.6,
        ))

    # Admin + Headteacher users
    admin_user = User(school_id=school.id, email=sd["admin_email"], role=UserRole.ADMIN)
    admin_user.set_password("admin123")
    db.session.add(admin_user)

    ht_email = f"headteacher@{sd['admin_email'].split('@')[1]}"
    ht_user = User(school_id=school.id, email=ht_email, role=UserRole.HEADTEACHER)
    ht_user.set_password("head123")
    db.session.add(ht_user)

    db.session.flush()

    # Academic Year & 3 Terms
    ay = AcademicYear(school_id=school.id, name="2024/2025",
                      start_date=date(2024, 9, 1), end_date=date(2025, 7, 31),
                      is_current=True)
    db.session.add(ay)
    db.session.flush()

    terms = [
        Term(school_id=school.id, academic_year_id=ay.id,
             name="First Term", term_number=1,
             start_date=date(2024, 9, 2), end_date=date(2024, 12, 13),
             is_current=True),
        Term(school_id=school.id, academic_year_id=ay.id,
             name="Second Term", term_number=2,
             start_date=date(2025, 1, 13), end_date=date(2025, 4, 4)),
        Term(school_id=school.id, academic_year_id=ay.id,
             name="Third Term", term_number=3,
             start_date=date(2025, 4, 28), end_date=date(2025, 7, 25)),
    ]
    for t in terms:
        db.session.add(t)
    db.session.flush()
    current_term = terms[0]

    # Departments
    dept_map = {}
    for dept_name in ["Academic", "Mathematics", "Languages", "Sciences", "Humanities"]:
        d = Department(school_id=school.id, name=dept_name, code=dept_name[:3].upper())
        db.session.add(d)
        dept_map[dept_name] = d
    db.session.flush()

    # Subjects
    core_subjects_data = [
        ("English Language", "ENG", "Languages"),
        ("Mathematics", "MATH", "Mathematics"),
        ("Integrated Science", "SCI", "Sciences"),
        ("Social Studies", "SOC", "Humanities"),
        ("Religious & Moral Education", "RME", "Academic"),
        ("Creative Arts", "ARTS", "Academic"),
        ("Computing / ICT", "ICT", "Sciences"),
    ]
    subjects = []
    for sname, scode, dept_name in core_subjects_data:
        s = Subject(school_id=school.id, name=sname, code=scode,
                    department_id=dept_map[dept_name].id, is_core=True)
        db.session.add(s)
        subjects.append(s)
    db.session.flush()

    # Classes by level
    level_class_map = {
        "Kindergarten": [("KG 1", 1), ("KG 2", 2)],
        "Primary": [(f"Primary {i}", i) for i in range(1, 7)],
        "JHS": [(f"JHS {i}", i) for i in range(1, 4)],
        "SHS": [(f"SHS {i}", i) for i in range(1, 4)],
    }

    all_classes = []
    for level in sd["levels"]:
        for cname, gnum in level_class_map.get(level, []):
            cls = Class(school_id=school.id, name=cname, level=level,
                        grade_number=gnum, section="A", capacity=40)
            db.session.add(cls)
            all_classes.append((cls, level))
    db.session.flush()

    # Staff: at least 1 teacher per 2 classes
    staff_list = []
    accounts_user = None
    num_teachers = max(5, len(all_classes) // 2 + 2)
    for i in range(num_teachers):
        fn, ln, gender = rname()
        staff = Staff(
            school_id=school.id,
            staff_id=f"{school.id:02d}-TCH-{i+1:03d}",
            first_name=fn, last_name=ln, gender=gender,
            position="Teacher",
            date_of_birth=rand_dob(25, 55),
            date_employed=date(random.randint(2010, 2023), random.randint(1, 12), 1),
            phone=rand_phone(), qualification="Bachelor of Education",
            is_active=True,
        )
        db.session.add(staff)
        staff_list.append(staff)
    db.session.flush()

    # Assign class teachers
    for idx, (cls, _) in enumerate(all_classes):
        cls.class_teacher_id = staff_list[idx % len(staff_list)].id

    # Create teacher user accounts
    for i, staff in enumerate(staff_list[:3]):
        teach_email = f"teacher{i+1}@{sd['admin_email'].split('@')[1]}"
        tu = User(school_id=school.id, email=teach_email, role=UserRole.TEACHER,
                  staff_id=staff.id)
        tu.set_password("teacher123")
        db.session.add(tu)

    # Accounts Officer
    acc_fn, acc_ln, acc_gender = rname()
    acc_staff = Staff(
        school_id=school.id,
        staff_id=f"{school.id:02d}-ACC-001",
        first_name=acc_fn, last_name=acc_ln, gender=acc_gender,
        position="Accounts Officer",
        date_of_birth=rand_dob(28, 50),
        date_employed=date(2020, 1, 15),
        phone=rand_phone(), qualification="HND Accounting",
        is_active=True,
    )
    db.session.add(acc_staff)
    db.session.flush()
    acc_email = f"accounts@{sd['admin_email'].split('@')[1]}"
    acc_user = User(school_id=school.id, email=acc_email,
                    role=UserRole.ACCOUNTS_OFFICER, staff_id=acc_staff.id)
    acc_user.set_password("accounts123")
    db.session.add(acc_user)
    db.session.flush()

    # Class-Subject assignments
    class_subjects_map = {}  # (class_id, subject_id) -> ClassSubject
    for cls, level in all_classes:
        for subj in subjects[:5]:  # assign first 5 core subjects to every class
            teacher = random.choice(staff_list)
            cs = ClassSubject(
                school_id=school.id,
                class_id=cls.id,
                subject_id=subj.id,
                teacher_id=teacher.id,
                academic_year_id=ay.id,
            )
            db.session.add(cs)
            class_subjects_map[(cls.id, subj.id)] = cs
    db.session.flush()

    # Fee Categories
    fee_tuition = FeeCategory(school_id=school.id, name="Tuition", is_recurring=True)
    fee_books   = FeeCategory(school_id=school.id, name="Books & Materials", is_recurring=False)
    fee_uniform = FeeCategory(school_id=school.id, name="Uniform", is_recurring=False)
    fee_pta     = FeeCategory(school_id=school.id, name="PTA Levy", is_recurring=True)
    db.session.add_all([fee_tuition, fee_books, fee_uniform, fee_pta])
    db.session.flush()

    # Fee Structures per class
    tuition_amounts = {"Kindergarten": 600, "Primary": 800, "JHS": 1000, "SHS": 1400}
    for cls, level in all_classes:
        base = tuition_amounts.get(level, 800)
        for cat, amt in [
            (fee_tuition, base),
            (fee_books, base * 0.15),
            (fee_uniform, base * 0.10),
            (fee_pta, 50),
        ]:
            fs = FeeStructure(
                school_id=school.id, class_id=cls.id,
                academic_year_id=ay.id, fee_category_id=cat.id,
                amount=Decimal(str(round(amt, 2)))
            )
            db.session.add(fs)
    db.session.flush()

    # Students + Parents + Enrollments + Invoices + Assessments + Attendance
    invoice_counter = 1
    students_created = []
    for cls_idx, (cls, level) in enumerate(all_classes):
        per_class = max(5, sd["student_count"] // len(all_classes))
        per_class = min(per_class, 40)

        for _ in range(per_class):
            # Parent
            pfn, pln, pgender = rname(Gender.FEMALE)
            parent = Parent(
                school_id=school.id,
                mother_name=f"{pfn} {pln}",
                mother_phone=rand_phone(),
                primary_contact_phone=rand_phone(),
                region=random.choice(REGIONS),
                city=random.choice(CITIES),
            )
            db.session.add(parent)
            db.session.flush()

            # Student
            sfn, sln, sgender = rname()
            stu_id = f"{school.id:02d}-{cls.id:03d}-{len(students_created)+1:04d}"
            stu = Student(
                school_id=school.id,
                parent_id=parent.id,
                student_id=stu_id,
                first_name=sfn, last_name=sln, gender=sgender,
                date_of_birth=rand_dob(5, 20),
                nationality="Ghanaian",
                admission_date=date(random.randint(2018, 2024), 9, 1),
                status=StudentStatus.ACTIVE,
            )
            db.session.add(stu)
            db.session.flush()
            students_created.append(stu)

            # Enroll
            enrollment = ClassEnrollment(
                student_id=stu.id, class_id=cls.id,
                academic_year_id=ay.id, enrollment_date=date(2024, 9, 2)
            )
            db.session.add(enrollment)
            db.session.flush()

            # Invoice
            total_fees = Decimal('0')
            invoice_items_data = []
            for cat, amt_mult in [
                (fee_tuition, tuition_amounts.get(level, 800)),
                (fee_books,   tuition_amounts.get(level, 800) * 0.15),
                (fee_pta,     50),
            ]:
                amt = Decimal(str(round(amt_mult, 2)))
                total_fees += amt
                invoice_items_data.append((cat, amt))

            inv_num = f"INV-{school.id:02d}-{invoice_counter:05d}"
            invoice_counter += 1
            paid_frac = random.choice([0, 0, 0.5, 1.0])  # ~33% fully paid
            amount_paid = round(total_fees * Decimal(str(paid_frac)), 2)
            balance = total_fees - amount_paid
            inv_status = (PaymentStatus.COMPLETED if balance == 0
                          else (PaymentStatus.PARTIAL if amount_paid > 0
                                else PaymentStatus.PENDING))

            invoice = FeeInvoice(
                school_id=school.id,
                invoice_number=inv_num,
                student_id=stu.id,
                term_id=current_term.id,
                total_amount=total_fees,
                amount_paid=amount_paid,
                balance=balance,
                status=inv_status,
                issue_date=date(2024, 9, 2),
                due_date=date(2024, 10, 31),
            )
            db.session.add(invoice)
            db.session.flush()

            for cat, amt in invoice_items_data:
                db.session.add(FeeInvoiceItem(
                    invoice_id=invoice.id,
                    fee_category_id=cat.id,
                    description=cat.name,
                    amount=amt,
                ))

            if amount_paid > 0:
                import uuid as _u
                db.session.add(Payment(
                    receipt_number=f"REC-{_u.uuid4().hex[:8].upper()}",
                    invoice_id=invoice.id,
                    amount=amount_paid,
                    payment_method=random.choice([PaymentMethod.CASH,
                                                   PaymentMethod.MOBILE_MONEY]),
                    payment_date=datetime(2024, 9, random.randint(3, 30)),
                    payer_name=parent.mother_name,
                    payer_phone=parent.primary_contact_phone,
                    status=PaymentStatus.COMPLETED,
                ))

            # Assessments (for first 5 subjects mapped to this class)
            for subj in subjects[:5]:
                cs = class_subjects_map.get((cls.id, subj.id))
                if not cs:
                    continue
                cw = round(random.uniform(15, 30), 1)
                hw = round(random.uniform(5, 10), 1)
                proj = round(random.uniform(5, 10), 1)
                exam = round(random.uniform(20, 50), 1)
                total = cw + hw + proj + exam

                assess = Assessment(
                    school_id=school.id,
                    student_id=stu.id,
                    class_subject_id=cs.id,
                    term_id=current_term.id,
                    classwork_score=cw,
                    homework_score=hw,
                    project_score=proj,
                    exam_score=exam,
                    total_score=total,
                    grade_remark=_grade_remark(total),
                    narrative_comment=_narrative(total),
                )
                _apply_nacca_grade(assess, level)
                db.session.add(assess)

            # Attendance — last 30 school days
            school_day = date(2024, 9, 2)
            for _ in range(30):
                school_day += timedelta(days=1)
                while school_day.weekday() >= 5:  # skip weekends
                    school_day += timedelta(days=1)
                if school_day > date.today():
                    break
                status = random.choices(
                    [AttendanceStatus.PRESENT, AttendanceStatus.ABSENT,
                     AttendanceStatus.LATE],
                    weights=[85, 10, 5]
                )[0]
                db.session.add(Attendance(
                    school_id=school.id,
                    student_id=stu.id,
                    class_id=cls.id,
                    date=school_day,
                    status=status,
                ))

    # Expenses
    expense_categories = ["Salary", "Utilities", "Stationery", "Maintenance", "Fuel"]
    for cat in expense_categories:
        for month in range(9, 13):  # Sep–Dec 2024
            db.session.add(Expense(
                school_id=school.id,
                academic_year_id=ay.id,
                category=cat,
                amount=Decimal(str(round(random.uniform(500, 5000), 2))),
                description=f"{cat} for {date(2024, month, 1).strftime('%B %Y')}",
                expense_date=date(2024, month, random.randint(1, 28)),
            ))

    # Elite-only extras
    if sd["tier"] == "elite":
        _seed_elite_extras(db, school, sd)

    db.session.flush()
    print(f"  ✓ {len(students_created)} students | {num_teachers} teachers | invoices seeded")


def _seed_elite_extras(db, school, sd):
    """Marketplace + AI Insights + Corrections for Elite tier."""
    # Marketplace
    cat_uniform = ProductCategory(school_id=school.id, name="Uniforms", description="Official school uniforms")
    cat_books   = ProductCategory(school_id=school.id, name="Textbooks", description="NaCCA-approved textbooks")
    cat_sports  = ProductCategory(school_id=school.id, name="Sports Gear", description="PE equipment")
    db.session.add_all([cat_uniform, cat_books, cat_sports])
    db.session.flush()

    products = [
        Product(school_id=school.id, category_id=cat_uniform.id,
                name="School Polo Shirt (House Colours)", base_price=Decimal('55.00'),
                stock_quantity=200, description="Breathable polyester blend.", is_active=True),
        Product(school_id=school.id, category_id=cat_uniform.id,
                name="School Khaki Trousers", base_price=Decimal('70.00'),
                stock_quantity=150, description="Tailored fit.", is_active=True),
        Product(school_id=school.id, category_id=cat_books.id,
                name="Mathematics Textbook Gr6", base_price=Decimal('35.00'),
                stock_quantity=80, description="NaCCA 2024 edition.", is_active=True),
        Product(school_id=school.id, category_id=cat_books.id,
                name="Integrated Science Gr6", base_price=Decimal('30.00'),
                stock_quantity=60, description="NaCCA 2024 edition.", is_active=True),
        Product(school_id=school.id, category_id=cat_sports.id,
                name="Football (Size 4)", base_price=Decimal('45.00'),
                stock_quantity=20, description="Official size.", is_active=True),
    ]
    db.session.add_all(products)

    # AI School Insights
    insights = [
        SchoolInsight(school_id=school.id, type='attendance_drop',
                      entity_name="JHS 2A",
                      insight_text="Attendance in JHS 2A dropped 22% this week — 6 students absent 3+ days.",
                      severity='high', is_active=True),
        SchoolInsight(school_id=school.id, type='grade_dip',
                      entity_name="Primary 5 Gold",
                      insight_text="Mathematics scores fell by 18% term-on-term. Sub-strands: Fractions & Decimals.",
                      severity='medium', is_active=True),
        SchoolInsight(school_id=school.id, type='top_performer',
                      entity_name="Sasu Mensah",
                      insight_text="Top performer in SHS 1: 94% average across all 7 subjects.",
                      severity='low', is_active=True),
        SchoolInsight(school_id=school.id, type='fee_arrears',
                      entity_name="Collection Rate",
                      insight_text="Fee collection at 68% — 32 students have outstanding balances > GHS 500.",
                      severity='high', is_active=True),
    ]
    db.session.add_all(insights)

    # AI Corrections (learning feedback)
    db.session.add(AICorrection(
        school_id=school.id,
        original_prompt="What is Kofi's grade?",
        wrong_response="I'm sorry, I don't have access to grades.",
        correction_reason="Bot should use the explain_nacca_grade tool instead of declining.",
        is_applied=True,
    ))

    # AI Credit Usage history
    for days_ago in range(14):
        db.session.add(AICreditUsage(
            school_id=school.id,
            tokens_used=random.randint(500, 3000),
            interaction_type=random.choice(["whatsapp", "web_chat"]),
        ))

    # Audit Log samples
    db.session.add(AuditLog(
        school_id=school.id,
        action='SYSTEM_INITIALIZATION',
        entity_type='database',
        new_values={'status': 'seeded', 'tier': 'elite',
                    'timestamp': str(datetime.utcnow())}
    ))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _grade_remark(total):
    if total >= 80: return "Highly Proficient"
    if total >= 70: return "Proficient"
    if total >= 60: return "Approaching Proficiency"
    if total >= 50: return "Developing"
    return "Emerging"

def _narrative(total):
    if total >= 80:
        return "Exceptional performance! Exceeding NaCCA core competencies. Keep it up."
    if total >= 70:
        return "Excellent work. Very proficient across covered strands."
    if total >= 60:
        return "Good progress. Approaching full proficiency. Continued practice recommended."
    if total >= 50:
        return "Developing understanding of core concepts. More practice needed."
    return "Emerging. Intensive support and strand-based exercises required."

_NACCA_PRIMARY = {
    (80, 100): '1', (70, 79): '2', (60, 69): '3', (50, 59): '4',
    (40, 49): '5', (30, 39): '6', (25, 29): '7', (20, 24): '8', (0, 19): '9',
}
_NACCA_JHS = {
    (80, 100): '1', (70, 79): '2', (60, 69): '3', (55, 59): '4',
    (50, 54): '5', (45, 49): '6', (40, 44): '7', (35, 39): '8', (0, 34): '9',
}

def _apply_nacca_grade(assess, level):
    scale = _NACCA_JHS if level in ('JHS', 'SHS') else _NACCA_PRIMARY
    total = assess.total_score or 0
    for (lo, hi), grade in scale.items():
        if lo <= total <= hi:
            assess.grade = grade
            return
    assess.grade = '9'


def _print_credentials():
    print("\n" + "="*60)
    print("DEMO CREDENTIALS")
    print("="*60)
    rows = [
        ("Super Admin",  "superadmin@smartschool.com",          "smart_saas_2026"),
        ("Basic Admin",  "admin@villagehope.edu.gh",            "admin123"),
        ("Std Admin",    "admin@accrastandard.edu.gh",          "admin123"),
        ("Elite Admin",  "admin@elitepremier.edu.gh",           "admin123"),
        ("Teacher",      "teacher1@elitepremier.edu.gh",        "teacher123"),
        ("Accounts",     "accounts@elitepremier.edu.gh",        "accounts123"),
        ("Headteacher",  "headteacher@elitepremier.edu.gh",     "head123"),
    ]
    for role, email, pw in rows:
        print(f"  {role:<14} {email:<42} {pw}")
    print("="*60 + "\n")


if __name__ == "__main__":
    reseed()
