"""
Report Generation Routes
Handles individual and bulk PDF report downloads.
"""
from flask import Blueprint, send_file, flash, redirect, url_for, g, request
from flask_login import login_required, current_user
from services.report_service import ReportService
from models import Student, ClassEnrollment, Term
import os
from pypdf import PdfWriter

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')
from models import Class, Term, AcademicYear, db
from flask import render_template

@reports_bp.route('/')
@login_required
def index():
    """Report selection dashboard."""
    classes = Class.query.filter_by(school_id=current_user.school_id, is_active=True).all()
    current_year = AcademicYear.query.filter_by(school_id=current_user.school_id, is_current=True).first()
    terms = []
    if current_year:
        terms = Term.query.filter_by(academic_year_id=current_year.id).all()
    
    return render_template('reports/index.html', classes=classes, terms=terms)

@reports_bp.route('/student/<int:student_id>/term/<int:term_id>/download')
@login_required
def download_student_report(student_id, term_id):
    """Downloads a single student's terminal report."""
    student = Student.query.get_or_404(student_id)
    if student.school_id != current_user.school_id:
        flash('Access Denied.', 'error')
        return redirect(url_for('dashboard.index'))
    
    try:
        pdf_path = ReportService.generate_terminal_pdf(student_id, term_id)
        # Re-attach professional filename
        t = Term.query.get(term_id)
        term_name = t.name.replace(" ", "_") if t else "term"
        filename = f"Report_{student.full_name.replace(' ', '_')}_{term_name}.pdf"
        return send_file(pdf_path, as_attachment=True, download_name=filename)
    except Exception as e:
        flash(f'Error generating report: {str(e)}', 'error')
        return redirect(request.referrer or url_for('dashboard.index'))

@reports_bp.route('/bulk/class/<int:class_id>/term/<int:term_id>')
@login_required
def bulk_generate_reports(class_id, term_id):
    """Merges all terminal reports for a whole class into a single PDF."""
    try:
        # 1. Get all students enrolled in this class for the current academic year
        enrollments = ClassEnrollment.query.filter_by(
            class_id=class_id, 
            academic_year_id=g.current_academic_year.id if g.current_academic_year else 0
        ).all()
        
        if not enrollments:
            flash('No students found in this class.', 'warning')
            return redirect(request.referrer)
        
        writer = PdfWriter()
        pdf_paths = []
        
        # 2. Generate each individual report
        for enrollment in enrollments:
            try:
                path = ReportService.generate_terminal_pdf(enrollment.student_id, term_id)
                writer.append(path)
                pdf_paths.append(path)
            except Exception as e:
                print(f"Skipping student {enrollment.student_id} due to error: {e}")
                continue # Skip if one fails, to keep bulk moving
        
        # 3. Final Merger
        if not pdf_paths:
            flash('Failed to generate any reports for this class.', 'error')
            return redirect(request.referrer)
            
        output_path = f"/tmp/bulk_class_{class_id}_{term_id}.pdf"
        with open(output_path, "wb") as f:
            writer.write(f)
        writer.close()
        
        # 4. Clean up temp files
        for p in pdf_paths:
            if os.path.exists(p): os.remove(p)
            
        return send_file(output_path, as_attachment=True, download_name=f"Bulk_Reports_Class_{class_id}.pdf")
        
    except Exception as e:
        flash(f'Bulk generation failed: {str(e)}', 'error')
        return redirect(request.referrer)
