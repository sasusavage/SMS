"""
/reports — report cards (Step 6).

HTML report card driven entirely by report_settings, plus an optional
WeasyPrint PDF export. The HTML always works (and is print-friendly via the
browser); PDF is used only if WeasyPrint and its system libraries are present,
otherwise the route explains how to enable it instead of crashing.

Access: school_admin and teachers (preview, including unpublished). The
student/parent portals (Step 7) will reuse build_report_card with
include_unpublished=False so only published results show.
"""
from flask import (
    Blueprint, render_template, request, abort, g, Response, flash, redirect,
    url_for,
)
from flask_login import login_required

from auth.security import require_role
from services import report_card
from services.report_card import ReportError

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.before_request
@login_required
@require_role('school_admin', 'teacher')
def _guard():
    if g.get('current_school_id') is None:
        abort(403)


def _build(student_id, term_id):
    try:
        return report_card.build_report_card(
            g.current_school_id, student_id, term_id, include_unpublished=True)
    except ReportError:
        abort(404)


@reports_bp.route('/report-card/<int:student_id>/<int:term_id>')
def report_card_view(student_id, term_id):
    data = _build(student_id, term_id)
    return render_template('reports/report_card.html', pdf=False, **data)


@reports_bp.route('/report-card/<int:student_id>/<int:term_id>.pdf')
def report_card_pdf(student_id, term_id):
    data = _build(student_id, term_id)
    html = render_template('reports/report_card.html', pdf=True, **data)

    try:
        from weasyprint import HTML
    except Exception:
        # WeasyPrint (or its system libs) not available — fall back gracefully.
        flash('PDF export is not enabled on this server. Use your browser\'s '
              'Print → Save as PDF on the report card page instead.', 'warning')
        return redirect(url_for('reports.report_card_view',
                                student_id=student_id, term_id=term_id))

    pdf_bytes = HTML(string=html, base_url=request.url_root).write_pdf()
    filename = f'report-{data["student"].admission_no}-{data["term"].name}.pdf'
    return Response(
        pdf_bytes, mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename="{filename}"'})
