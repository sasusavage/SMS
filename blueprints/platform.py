"""
Platform (super admin) blueprint. Step 1 ships only the landing page; schools
list / suspend / subscriptions / metrics arrive in Step 8.
"""
from flask import Blueprint, render_template

from auth.security import platform_only

platform_bp = Blueprint('platform', __name__, url_prefix='/platform')


@platform_bp.route('/')
@platform_only
def index():
    from models.platform import School
    schools = School.query.order_by(School.created_at.desc()).all()
    return render_template('platform/index.html', schools=schools)
