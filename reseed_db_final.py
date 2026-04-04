"""
Final SaaS Production Reseed - SmartSchool 2026
Wipes all data and re-seeds with Multi-tenant SaaS structure for 3 Demo Schools.
"""
import os
import sys
import random
import uuid as uuid_pkg
from datetime import date, datetime
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import (
    db, School, AcademicYear, Term, Department, Class, Subject, ClassSubject,
    User, UserRole, Staff, Parent, Student, Gender, StudentStatus,
    ClassEnrollment, SubscriptionPlan, Subscription, Strand, SubStrand, init_db,
    SchoolSetting, FeeInvoice, Assessment, AICreditUsage, AIBotConfig, ModuleConfig,
    SchoolInsight, AICorrection, Product, ProductCategory, Order
)

def reseed():
    app = create_app('development')
    with app.app_context():
        print("--- PURGING DATABASE ---")
        from sqlalchemy import text
        db.session.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        db.session.commit()
        init_db(app)

        # 1. Plans
        plans = [
            SubscriptionPlan(name="Basic", price=Decimal('49.00'), student_limit=100, features={'core': True}),
            SubscriptionPlan(name="Standard", price=Decimal('149.00'), student_limit=500, features={'core': True, 'fees': True}),
            SubscriptionPlan(name="Premium", price=Decimal('499.00'), student_limit=5000, features={'all': True, 'ai': True})
        ]
        db.session.add_all(plans)
        db.session.flush()

        # 2. Super Admin
        sa_school = School(name="SmartSchool SaaS Office", email="superadmin@smartschool.com")
        db.session.add(sa_school); db.session.flush()
        sa_user = User(school_id=sa_school.id, email="superadmin@smartschool.com", role=UserRole.SUPER_ADMIN)
        sa_user.set_password("smart_saas_2026")
        db.session.add(sa_user)
        
        # Provision ModuleConfig for Super Admin School
        db.session.add(ModuleConfig(school_id=sa_school.id, is_ai_enabled=True, is_sms_enabled=True))

        # 3. Create 3 Demo Schools
        schools_data = [
            {"name": "Village Hope Basic", "plan": plans[0]},
            {"name": "Accra Standard Academy", "plan": plans[1]},
            {"name": "Elite Premium International", "plan": plans[2], "whatsapp": "WH-ELITE-PREM-2026"}
        ]

        for data in schools_data:
            sch = School(
                name=data["name"], 
                email=f"admin@{data['name'].lower().replace(' ', '')}.com",
                sms_credits=500 if "Premium" in data["name"] else 100
            )
            db.session.add(sch); db.session.flush()
            
            # Sub & Module Config
            db.session.add(Subscription(school_id=sch.id, plan_id=data["plan"].id, status='active'))
            
            m_cfg = ModuleConfig(
                school_id=sch.id,
                is_ai_enabled=("ai" in data["plan"].features or "all" in data["plan"].features),
                is_sms_enabled=True,
                is_finance_enabled=("fees" in data["plan"].features or "all" in data["plan"].features),
                is_predictive_ai_enabled=("all" in data["plan"].features),
                is_marketplace_enabled=True,
                is_pwa_enabled=True,
                is_voice_ai_enabled=("all" in data["plan"].features)
            )
            db.session.add(m_cfg)

            setting = SchoolSetting(
                school_id=sch.id, 
                sms_enabled=True, 
                sms_sender_id=sch.name[:11].replace(' ', ''),
                ai_bot_enabled=m_cfg.is_ai_enabled,
                whatsapp_business_id=data.get("whatsapp")
            )
            db.session.add(setting)
            
            if m_cfg.is_ai_enabled:
                db.session.add(AIBotConfig(school_id=sch.id, knowledge_base="Strict NaCCA grading enabled."))

            # Admin
            adm = User(school_id=sch.id, email=sch.email, role=UserRole.ADMIN)
            adm.set_password("admin123")
            db.session.add(adm)
            
            # Academic setup for Premium School
            if data["name"] == "Elite Premium International":
                ay = AcademicYear(school_id=sch.id, name="24/25", start_date=date(2024,9,1), end_date=date(2025,7,31), is_current=True)
                db.session.add(ay); db.session.flush()
                
                term = Term(school_id=sch.id, academic_year_id=ay.id, name="Term 1", term_number=1, start_date=date(2024,9,1), end_date=date(2024,12,15), is_current=True)
                db.session.add(term); db.session.flush()
                
                cls = Class(school_id=sch.id, name="Grade 5 Gold", level="Primary", grade_number=5, section="Gold", is_active=True)
                db.session.add(cls); db.session.flush()
                
                stu = Student(
                    school_id=sch.id, student_id="STU001", 
                    first_name="Sasu", last_name="Jnr", 
                    gender=Gender.MALE, date_of_birth=date(2015,5,20),
                    admission_date=date(2024,1,1)
                )
                db.session.add(stu); db.session.flush()
                
                # Seeding Elite Marketplace
                cat_uniform = ProductCategory(school_id=sch.id, name="Uniforms")
                db.session.add(cat_uniform); db.session.flush()
                
                db.session.add(Product(
                    school_id=sch.id, category_id=cat_uniform.id,
                    name="Lacoste School Shirt", description="High-quality breathable fabric.",
                    base_price=Decimal('50.00'), stock_quantity=100
                ))
                
                # Seeding Predictive Insight
                db.session.add(SchoolInsight(
                    school_id=sch.id, type='academic', 
                    entity_name="Grade 5 Gold",
                    insight_text="Math Performance Drop: Scores fell by 18% overall. Intervention recommended.",
                    severity='high'
                ))

        db.session.commit()
        print("SaaS Production Data Seeded Successfully!")

if __name__ == "__main__":
    reseed()
