"""
NaCCA Terminal Report Services
Handles generation of PDF reports with subject positioning and performance trends.
"""
from flask import render_template
import os
from models import db, Student, Term, School, Attendance, AttendanceStatus
from sqlalchemy import text
from decimal import Decimal
from datetime import datetime

# Choose best available PDF engine
PDF_ENGINE = None
try:
    from weasyprint import HTML
    test_html = HTML(string="<p></p>") # Test if libraries are actually loadable
    PDF_ENGINE = 'weasyprint'
except (ImportError, OSError):
    try:
        from xhtml2pdf import pisa
        PDF_ENGINE = 'xhtml2pdf'
    except (ImportError, Exception):
        PDF_ENGINE = None

class ReportService:
    
    @staticmethod
    def get_student_performance(student_id, term_id):
        """Fetches detailed performance data from PostgreSQL views."""
        # 1. Terminal Summary (Class Position, average)
        sql_summary = text("SELECT * FROM v_student_terminal_reports WHERE student_id = :sid AND term_id = :tid")
        summary = db.session.execute(sql_summary, {"sid": student_id, "tid": term_id}).fetchone()
        
        # 2. Subject Breakdown
        sql_subjects = text("SELECT * FROM v_student_subject_performance WHERE student_id = :sid AND term_id = :tid")
        subjects = db.session.execute(sql_subjects, {"sid": student_id, "tid": term_id}).fetchall()
        
        return summary, subjects

    @staticmethod
    def get_performance_trend(student_id, current_term_id):
        """Retrieves average scores over the last 3 terms for trending."""
        sql_trend = text("""
            SELECT t.name, r.average_score 
            FROM v_student_terminal_reports r
            JOIN terms t ON r.term_id = t.id
            WHERE r.student_id = :sid
            ORDER BY t.start_date DESC
            LIMIT 3
        """)
        results = db.session.execute(sql_trend, {"sid": student_id}).fetchall()
        # Return in forward chronological order for the chart
        return sorted(results, key=lambda x: x[0])

    @staticmethod
    def generate_terminal_pdf(student_id, term_id):
        """Generates a NaCCA-compliant PDF report."""
        student = Student.query.get(student_id)
        term = Term.query.get(term_id)
        school = School.query.get(student.school_id)
        
        summary, subjects = ReportService.get_student_performance(student_id, term_id)
        trend = ReportService.get_performance_trend(student_id, term_id)
        
        # Attendance stats — scoped to the term's date range
        total_days = (
            Attendance.query
            .filter_by(school_id=school.id, student_id=student_id)
            .filter(Attendance.date >= term.start_date, Attendance.date <= term.end_date)
            .count()
        )
        present_days = (
            Attendance.query
            .filter_by(school_id=school.id, student_id=student_id,
                       status=AttendanceStatus.PRESENT)
            .filter(Attendance.date >= term.start_date, Attendance.date <= term.end_date)
            .count()
        )
        
        html_content = render_template(
            'reports/terminal_report.html',
            student=student,
            term=term,
            school=school,
            summary=summary,
            subjects=subjects,
            trend=trend,
            attendance={'total': total_days, 'present': present_days},
            now=datetime.now()
        )
        
        # Generate PDF
        output_path = f"/tmp/report_{student_id}_{term_id}.pdf"
        if PDF_ENGINE == 'weasyprint':
            HTML(string=html_content).write_pdf(output_path)
        elif PDF_ENGINE == 'xhtml2pdf':
            with open(output_path, "wb") as f:
                pisa.CreatePDF(html_content, dest=f)
        else:
            raise Exception("No PDF engine found. Please install WeasyPrint or xhtml2pdf.")
            
        return output_path
