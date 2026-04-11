"""
File Upload Utility — persistent local storage (Coolify-compatible).

Set UPLOAD_FOLDER env var in Coolify to your persistent volume path (e.g. /data/uploads).
Files are served via /uploads/<path> route registered in app.py.
"""
import os
import uuid as _uuid
from flask import current_app

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_DOC_EXTENSIONS   = {'pdf'}
ALLOWED_ALL              = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_DOC_EXTENSIONS


def _ext(filename: str) -> str:
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def allowed_image(filename: str) -> bool:
    return _ext(filename) in ALLOWED_IMAGE_EXTENSIONS


def allowed_any(filename: str) -> bool:
    return _ext(filename) in ALLOWED_ALL


def save_upload(file, subfolder: str = 'general') -> str | None:
    """
    Save an uploaded FileStorage object to persistent storage.

    Returns the public URL path (/uploads/<subfolder>/<uuid>.<ext>),
    or None if the file is invalid / missing.
    """
    if not file or not file.filename:
        return None
    if not allowed_any(file.filename):
        return None

    ext = _ext(file.filename)
    filename = f"{_uuid.uuid4().hex}.{ext}"

    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(upload_dir, exist_ok=True)

    file.save(os.path.join(upload_dir, filename))
    return f"/uploads/{subfolder}/{filename}"


def delete_upload(url_path: str) -> None:
    """Delete a previously saved upload given its URL path."""
    if not url_path or not url_path.startswith('/uploads/'):
        return
    rel = url_path[len('/uploads/'):]
    abs_path = os.path.join(current_app.config['UPLOAD_FOLDER'], rel)
    try:
        if os.path.isfile(abs_path):
            os.remove(abs_path)
    except OSError:
        pass
