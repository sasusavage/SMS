"""
/media — serve tenant-uploaded files, tenant-scoped.

A logged-in user can only fetch files under their OWN school's folder (or, for
super admins, any). Prevents school A from reading school B's logos/photos by
guessing paths. Files are served from outside the app's static dir.
"""
import os

from flask import Blueprint, abort, send_file, g
from flask_login import login_required, current_user

from services import uploads
from auth.security import is_platform_user

media_bp = Blueprint('media', __name__, url_prefix='/media')


@media_bp.route('/<path:rel_path>')
@login_required
def serve(rel_path):
    # Resolve to an absolute path inside the upload root (containment-checked).
    full = uploads.abs_path_for(rel_path)
    if full is None:
        abort(404)
    # Tenant scoping: only your own school's files (super admins: any).
    if not is_platform_user():
        sid = g.get('current_school_id')
        if sid is None or not uploads.belongs_to_school(rel_path, sid):
            abort(404)
    return send_file(full)
