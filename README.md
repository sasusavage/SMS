# NaCCA School Management System

A production-grade school management solution for Ghanaian schools following **NaCCA standards**, refactored for scale, performance, and full mobile responsiveness.

## Key Refactor Features (Production Ready)

- **Architecture:** Transitioned from a "fat route" system to a **Service Layer** architecture for better maintainability.
- **Performance:** Complex grading and ranking logic moved to **PostgreSQL Database Views** (`v_student_subject_performance` and `v_student_terminal_reports`) using high-performance window functions.
- **Mobile Responsive:** Full mobile-first design implemented with vanilla CSS, including a toggleable sidebar and adaptive grids.
- **Audit Logging:** Built-in system to track critical actions (student creation, updates, etc.) via the `AuditLog` model.
- **RBAC:** Granular Role-Based Access Control enforcing strict permissions across all modules.

## Features

- **NaCCA Academic Logic** - Automatic grading and descriptors based on latest NaCCA assessment standards.
- **Financial Engine** - Fee structures, automated invoice generation, and payment tracking.
- **Parent Portal** - Secure access for parents to view student performance, attendance, and attendance reports.
- **Terminal Reports** - Instant generation of terminal reports with class rankings and subject-level positions.

## Tech Stack

- **Backend:** Python / Flask (Framework: Antigravity-style architecture)
- **Database:** PostgreSQL (with complex SQL Views)
- **Frontend:** Vanilla HTML5, CSS3 (Modern Glassmorphism aesthetics), JavaScript (ES6+)

## Installation

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

## NaCCA Terminal Report Engine

The system uses two primary PostgreSQL views for reporting:
1. `v_student_subject_performance`: Calculates 50/50 weighting, subject ranking, and grade descriptors per student per subject.
2. `v_student_terminal_reports`: Aggregates totals, averages, and calculates "Position in Class" using SQL `RANK()` functions.

---

Built for **NaCCA Excellence** - Modern, High-Performance, and Mobile-First.
