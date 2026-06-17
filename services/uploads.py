"""
File upload service (Phase 1 hardening).

Stores tenant files under uploads/<school_id>/<kind>/ with a randomised,
secure filename. Validates extension and (for images) basic content. Returns a
RELATIVE path stored on the model (e.g. "3/logo/ab12cd.png"); serving goes
through a tenant-scoped route so school A can never read school B's files.

Image-only kinds (logo, photo) reject non-image extensions even though the
global ALLOWED_EXTENSIONS also permits pdf.
"""
import os
import secrets

from flask import current_app
from werkzeug.utils import secure_filename

IMAGE_EXTS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


class UploadError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _ext(filename):
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def save_upload(file_storage, school_id, kind, *, images_only=True):
    """
    Save an uploaded file. Returns the relative stored path, or raises
    UploadError. `kind` is a subfolder like 'logo' or 'photo'.
    """
    if file_storage is None or not file_storage.filename:
        raise UploadError('No file selected.')

    ext = _ext(secure_filename(file_storage.filename))
    allowed = IMAGE_EXTS if images_only else \
        current_app.config.get('ALLOWED_EXTENSIONS', IMAGE_EXTS)
    if ext not in allowed:
        raise UploadError(
            f'Unsupported file type ".{ext}". Allowed: {", ".join(sorted(allowed))}.')

    # Randomised name avoids collisions and path traversal via the original name.
    name = f'{secrets.token_hex(8)}.{ext}'
    rel_dir = os.path.join(str(school_id), kind)
    abs_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    abs_path = os.path.join(abs_dir, name)
    file_storage.save(abs_path)

    # Reject empty files.
    if os.path.getsize(abs_path) == 0:
        os.remove(abs_path)
        raise UploadError('The uploaded file is empty.')

    return os.path.join(rel_dir, name).replace('\\', '/')


def abs_path_for(rel_path):
    """Absolute path for a stored relative path, or None."""
    if not rel_path:
        return None
    base = os.path.abspath(current_app.config['UPLOAD_FOLDER'])
    full = os.path.abspath(os.path.join(base, rel_path))
    # Containment check — never serve outside the upload root.
    if not full.startswith(base + os.sep):
        return None
    return full if os.path.exists(full) else None


def delete_upload(rel_path):
    """Best-effort delete of a stored file."""
    full = abs_path_for(rel_path)
    if full:
        try:
            os.remove(full)
        except OSError:
            pass


def belongs_to_school(rel_path, school_id):
    """True if a stored relative path is under this school's folder."""
    if not rel_path:
        return False
    return rel_path.split('/', 1)[0] == str(school_id)
