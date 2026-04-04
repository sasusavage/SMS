# NaCCA School Management System

A production-grade school management solution for Ghanaian schools following **NaCCA standards**, refactored for scale, performance, and full mobile responsiveness.

## Key Refactor Features (Production Ready)

- **Architecture:** Transitioned from a "fat route" system to a **Service Layer** architecture for better maintainability.
- **Performance:** Complex grading and ranking logic moved to **PostgreSQL Database Views** (`v_student_subject_performance` and `v_student_terminal_reports`) using high-performance window functions.
- **Mobile Responsive:** Full mobile-first design implemented with vanilla CSS, including a toggleable sidebar and adaptive grids.
- **Audit Logging:** Built-in system to track critical actions (student creation, updates, etc.) via the `AuditLog` model.
- **RBAC:** Granular Role-Based Access Control enforcing strict permissions across all modules.
- **Smart Notification Hub:** Multi-channel alerting (SMS/WhatsApp) for student arrival, fee reminders, and terminal report releases.
- **QR Attendance Engine:** Automated morning roll-call system using browser-based QR scanning and CR80-standard secure ID card generation.

## Core Modules

- **NaCCA Academic Logic** - Automatic grading and descriptors based on latest NaCCA assessment standards.
- **Financial Engine** - Fee structures, automated invoice generation, and payment tracking.
- **Parent Portal** - Secure access for parents to view student performance, attendance notifications, and fees.
- **ID Card Infrastructure** - Bulk generation of secure, QR-coded student ID cards for automated check-ins.
- **Attendance Scanner** - Web-based scanning interface for teachers to track arrivals via smartphone.

## Tech Stack

- **Backend:** Python / Flask (Framework: Antigravity-style architecture)
- **Database:** PostgreSQL (with complex SQL Views and Multi-tenant partitioning)
- **Frontend:** Vanilla HTML5, CSS3 (Modern Glassmorphism aesthetics), JavaScript (ES6+), Html5-QRCode
- **PDF Generation:** WeasyPrint (Print-ready ID Cards and Terminal Reports)
- **Messaging:** Arkesel SMS Gateway Integration

## Project Structure

```
School/
├── app.py                 # Main Entry Point & Flask Factory
├── config.py              # Central Configuration (RBAC & Environment)
├── reseed_db_final.py     # Final Production Seeder & View Creator
├── models/
│   └── __init__.py        # Database Models & SQL View Definitions
├── services/              # Business Logic Layer (Clean Architecture)
│   ├── student_service.py # Core student business logic
│   └── notification_service.py # SMS & In-App Alerting
├── utils/                 # Utility Services
│   ├── sms_provider.py    # Arkesel API Wrapper
│   ├── qr_generator.py    # Secure QR payload generation
│   └── ...
├── routes/                # Blueprint Route Handlers (Slim Routes)
│   ├── api.py             # AJAX & Scanner Endpoints
│   ├── students.py        # Student module (inc. ID Cards)
│   └── ...
```

---

Built for **NaCCA Excellence** - Modern, High-Performance, and Mobile-First.

### Prerequisites

- Python 3.10+
- PostgreSQL 14+
- `pip`

### Setup

1. **Clone and navigate to the project:**
   ```bash
   git clone <repo-url>
   cd School
   ```

2. **Initialize Environment:**
   Create a `.env` file in the root directory:
   ```env
   FLASK_CONFIG=development
   SECRET_KEY=your-secret-key
   DATABASE_URL=postgresql://user:password@localhost:5432/schooldb
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Production Refactor Reset (Recommended):**
   To ensure the database schema and PostgreSQL views are correctly initialized, run the final reseed script:
   ```bash
   python reseed_db_final.py
   ```

5. **Run the application:**
   ```bash
   python app.py
   ```

## Production Credentials (Default)

**Password for all accounts:** `admin123`

| Role | Email |
|------|-------|
| **Super Admin** | `superadmin@school.com` |
| **Headteacher** | `headteacher@school.com` |
| **Admin** | `admin@school.com` |
| **Teacher** | `teacher@school.com` |
| **Accounts** | `accounts@school.com` |
| **Parent** | `parent@school.com` |

## Project Structure

```
School/
├── app.py                 # Main Entry Point & Flask Factory
├── config.py              # Central Configuration (RBAC & Environment)
├── reseed_db_final.py     # Final Production Seeder & View Creator
├── models/
│   └── __init__.py        # Database Models & SQL View Definitions
├── services/              # Business Logic Layer (Clean Architecture)
│   └── student_service.py # Core student business logic
├── routes/                # Blueprint Route Handlers (Slim Routes)
│   ├── students.py        # Student module
│   ├── reports.py         # NaCCA Reporting module (PDFs)
│   └── ...
├── templates/             # Premium Glassmorphism UI
│   ├── base.html          # Global Shell
│   └── layouts/           # Dashboard Shells
└── static/
    ├── css/
    │   └── main.css       # Full Responsive Design System
    └── js/
        └── main.js        # Core Interaction Logic
```

## SaaS Platform Tiers

The system is designed for multi-tenant scalability with three primary subscription tiers:

- **Basic:** Core academic & attendance modules for small schools (Up to 200 students).
- **Pro:** Adds Financial Engine, Paystack integration, and Automated Report Cards.
- **Enterprise:** Full suite including Bulk Importers, QR ID Card Infrastructure, and Multi-campus support.

## Security & Compliance

### Ghana Data Protection Act (DPA)
The platform is engineered to comply with the **Ghana Data Protection Act (Act 843)**:
- **Privacy Mode:** Advanced masking of student/parent PII (Personally Identifiable Information) for non-administrative staff.
- **Audit Trails:** Immutable logging of all sensitive actions (grade changes, fee deletions, user access).
- **Data Isolation:** Strict multi-tenant partitioning ensures school data never leaks between instances.

---

Built for **NaCCA Excellence** - Modern, High-Performance, and Mobile-First.
