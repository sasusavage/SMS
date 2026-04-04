from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Student, Parent, Class, AcademicYear, User, UserRole, Gender
import pandas as pd
import os
import uuid
from werkzeug.utils import secure_filename

migration_bp = Blueprint('migration', __name__, url_prefix='/migration')

UPLOAD_FOLDER = 'uploads/migrations'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@migration_bp.route('/war-room', methods=['GET', 'POST'])
@login_required
def war_room():
    if not current_user.is_admin():
        flash("Unauthorized access.", "error")
        return redirect(url_for('dashboard.index'))
    
    return render_template('admin/migration_war_room.html')

@migration_bp.route('/upload-stage', methods=['POST'])
@login_required
def upload_stage():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    try:
        # Read headers only
        if filename.endswith('.csv'):
            df = pd.read_csv(filepath, nrows=0)
        else:
            df = pd.read_excel(filepath, nrows=0)
        
        headers = df.columns.tolist()
        return jsonify({
            "filepath": filepath,
            "headers": headers,
            "db_fields": [
                "student_id", "first_name", "last_name", "other_names", 
                "gender", "date_of_birth", "admission_date", "parent_phone",
                "class_name"
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@migration_bp.route('/process', methods=['POST'])
@login_required
def process_migration():
    data = request.json
    filepath = data.get('filepath')
    mapping = data.get('mapping') # {db_field: excel_header}
    
    if not filepath or not mapping:
        return jsonify({"error": "Missing data"}), 400
    
    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
        
        # Simple importer logic (In production, this would be a background task)
        success_count = 0
        errors = []
        
        # We need current academic year for mapping students to classes
        ay = AcademicYear.query.filter_by(school_id=current_user.school_id, is_current=True).first()
        
        for index, row in df.iterrows():
            try:
                # Map fields
                s_id = str(row.get(mapping.get('student_id')))
                f_name = str(row.get(mapping.get('first_name')))
                l_name = str(row.get(mapping.get('last_name')))
                
                # Check if exists
                if Student.query.filter_by(school_id=current_user.school_id, student_id=s_id).first():
                    continue
                
                new_student = Student(
                    school_id=current_user.school_id,
                    student_id=s_id,
                    first_name=f_name,
                    last_name=l_name,
                    gender=Gender.MALE if 'M' in str(row.get(mapping.get('gender'))).upper() else Gender.FEMALE,
                    date_of_birth=pd.to_datetime(row.get(mapping.get('date_of_birth'))).date() if mapping.get('date_of_birth') else date(2010,1,1),
                    admission_date=date.today()
                )
                db.session.add(new_student)
                success_count += 1
            except Exception as e:
                errors.append(f"Row {index+1}: {str(e)}")
        
        db.session.commit()
        return jsonify({"success": True, "count": success_count, "errors": errors})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
