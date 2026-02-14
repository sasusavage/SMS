# NaCCA School Management System

A comprehensive school management solution for Ghanaian schools following **NaCCA standards**.

## Features

- **Role-Based Access Control (RBAC)** - Headteachers, Admins, Teachers, Accounts Officers, and Parents
- **NaCCA Academic Logic** - Automatic grading based on NaCCA assessment standards
- **Financial Engine** - Fee structures, invoice generation, payment tracking
- **Parent Portal** - Secure read-only access for parents
- **Terminal Reports** - Generate and publish student reports

## Tech Stack

- **Backend:** Python / Flask
- **Database:** PostgreSQL
- **Frontend:** Vanilla HTML5, CSS3, JavaScript (ES6+)

## Installation

### Prerequisites

- Python 3.10+
- PostgreSQL 13+
- pip (Python package manager)

### Setup

1. **Clone and navigate to the project:**
   ```bash
   cd nacca_sms
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure database:**
   
   Create a PostgreSQL database named `nacca_sms`:
   ```sql
   CREATE DATABASE nacca_sms;
   ```
   
   Update the database connection in `config.py` if needed:
   ```python
   SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:password@localhost:5432/nacca_sms'
   ```

5. **Seed the database:**
   ```bash
   python seed.py
   ```

6. **Run the application:**
   ```bash
   python app.py
   ```

7. **Access the application:**
   
   Open [http://localhost:5000](http://localhost:5000) in your browser.

## Default Login Credentials

| Role | Email | Password |
|------|-------|----------|
| Headteacher | headteacher@sasuacademy.edu.gh | admin123 |
| Admin | admin@sasuacademy.edu.gh | admin123 |
| Teacher | teacher@sasuacademy.edu.gh | teacher123 |
| Accounts | accounts@sasuacademy.edu.gh | accounts123 |

## Project Structure

```
nacca_sms/
├── app.py                 # Main Flask application
├── config.py              # Configuration settings
├── seed.py                # Database seeder
├── requirements.txt       # Python dependencies
├── models/
│   └── __init__.py        # Database models
├── routes/
│   ├── auth.py            # Authentication routes
│   ├── dashboard.py       # Dashboard routes
│   ├── students.py        # Student management
│   ├── staff.py           # Staff management
│   ├── classes.py         # Classes & subjects
│   ├── assessments.py     # NaCCA assessments
│   ├── fees.py            # Fee management
│   ├── reports.py         # PDF reports
│   ├── parent_portal.py   # Parent access
│   └── api.py             # API endpoints
├── templates/
│   ├── base.html
│   ├── layouts/
│   ├── auth/
│   ├── dashboard/
│   ├── students/
│   └── errors/
└── static/
    ├── css/
    │   └── main.css       # Custom CSS
    └── js/
        └── main.js        # JavaScript utilities
```

## NaCCA Grading Scales

### Primary School (Grades 1-6)
| Score Range | Grade | Remark |
|-------------|-------|--------|
| 80-100 | 1 | Highest |
| 70-79 | 2 | Higher |
| 60-69 | 3 | High |
| 50-59 | 4 | High Average |
| 40-49 | 5 | Average |
| 30-39 | 6 | Low Average |
| 25-29 | 7 | Below Average |
| 20-24 | 8 | Low |
| 0-19 | 9 | Very Low |

### JHS
| Score Range | Grade | Remark |
|-------------|-------|--------|
| 80-100 | 1 | Excellent |
| 70-79 | 2 | Very Good |
| 60-69 | 3 | Good |
| 55-59 | 4 | Credit |
| 50-54 | 5 | Credit |
| 45-49 | 6 | Credit |
| 40-44 | 7 | Pass |
| 35-39 | 8 | Pass |
| 0-34 | 9 | Fail |

## Production Deployment

For VPS deployment:

1. Use **Gunicorn** as the WSGI server:
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 app:create_app()
   ```

2. Set environment variables:
   ```bash
   export FLASK_CONFIG=production
   export SECRET_KEY=your-secure-secret-key
   export DATABASE_URL=postgresql://user:pass@host:5432/dbname
   ```

3. Use **Nginx** as a reverse proxy.

4. Enable HTTPS with **Let's Encrypt**.

## License

MIT License - See LICENSE file for details.

---

Built with "Sasu Labs" Aesthetic - Modern, high-contrast, professional design.
