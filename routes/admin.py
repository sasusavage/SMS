"""
Standard Admin Routes for bulk tools and configuration.
"""
from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app import admin_required
from services.importer_service import ImporterService
import os

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_data():
    if request.method == 'POST':
        import_type = request.form.get('import_type')
        file = request.files.get('file')
        
        if not file or file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('admin.import_data'))
            
        if not file.filename.endswith('.csv'):
            flash('Please upload a CSV file.', 'error')
            return redirect(url_for('admin.import_data'))
            
        file_content = file.read()
        
        if import_type == 'students':
            count, errors = ImporterService.import_students(current_user.school_id, current_user.id, file_content)
            if count > 0:
                flash(f'Successfully imported {count} students!', 'success')
            if errors:
                for error in errors[:10]: # Limit flash messages
                    flash(error, 'warning')
                    
        elif import_type == 'staff':
            count, errors = ImporterService.import_staff(current_user.school_id, current_user.id, file_content)
            if count > 0:
                flash(f'Successfully imported {count} staff members!', 'success')
            if errors:
                for error in errors[:10]:
                    flash(error, 'warning')
                    
        return redirect(url_for('admin.import_data'))
        
    return render_template('admin/import.html')

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    from models import SchoolSetting, db
    settings = SchoolSetting.query.filter_by(school_id=current_user.school_id).first()
    
    if request.method == 'POST':
        if not settings:
            settings = SchoolSetting(school_id=current_user.school_id)
            db.session.add(settings)
            
        settings.sms_enabled = request.form.get('sms_enabled') == 'on'
        settings.privacy_mode_enabled = request.form.get('privacy_mode_enabled') == 'on'
        settings.api_key_sms = request.form.get('api_key_sms')
        settings.sms_sender_id = request.form.get('sms_sender_id')
        
        # New AI Toggles
        settings.ai_bot_enabled = request.form.get('ai_bot_enabled') == 'on'
        settings.whatsapp_business_id = request.form.get('whatsapp_business_id')
        
        db.session.commit()
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('admin.settings'))
        
    return render_template('admin/settings.html', settings=settings)

@admin_bp.route('/ai/conversations')
@login_required
@admin_required
def ai_conversations():
    """Monitor AI interactions across the school."""
    from models import AISession
    sessions = AISession.query.filter_by(school_id=current_user.school_id).order_by(AISession.last_interaction.desc()).all()
    return render_template('admin/ai_monitor.html', sessions=sessions)

@admin_bp.route('/support-contact')
def support_contact():
    """Landing page for suspended or restricted accounts."""
    return render_template('admin/support_contact.html')

@admin_bp.route('/suspend/<int:school_id>', methods=['POST'])
@login_required
@admin_required
def suspend_school(school_id):
    """SaaS Admin Kill-Switch."""
    from models import School
    school = School.query.get_or_404(school_id)
    school.is_account_suspended = not school.is_account_suspended
    school.suspension_reason = request.form.get('reason') or "Administrative Suspension"
    
    from models import db
    db.session.commit()
    return redirect(url_for('dashboard.super_admin'))
