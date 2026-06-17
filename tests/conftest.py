"""
Pytest fixtures — Step 1.

Uses a file-based SQLite database so the suite runs anywhere (the production
PostgreSQL host is only reachable from inside Coolify). Models are written to
be portable (JSONB->JSON variant), so the schema creates cleanly on SQLite.

Env vars are set BEFORE importing the app so config picks them up at import.
"""
import os
import tempfile

# Must be set before `app`/`config` import so the testing config uses SQLite,
# not the real Postgres. A temp file (not :memory:) keeps one shared DB across
# the multiple connections Flask-SQLAlchemy may open in a request.
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix='.sqlite')
os.close(_DB_FD)
os.environ['SECRET_KEY'] = 'test-secret'
os.environ['TEST_DATABASE_URL'] = f'sqlite+pysqlite:///{_DB_PATH}'
os.environ['DATABASE_URL'] = f'sqlite+pysqlite:///{_DB_PATH}'

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from extensions import db as _db  # noqa: E402


@pytest.fixture()
def app():
    app = create_app('testing')
    # SQLite doesn't accept the pool options tuned for Postgres.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {}
    app.config['WTF_CSRF_ENABLED'] = False
    # Uploads go to a throwaway temp dir, not the repo's uploads/ folder.
    upload_dir = tempfile.mkdtemp(prefix='sb-uploads-')
    app.config['UPLOAD_FOLDER'] = upload_dir
    with app.app_context():
        _db.drop_all()
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()
    import shutil
    shutil.rmtree(upload_dir, ignore_errors=True)


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def client(app):
    return app.test_client()


def pytest_unconfigure(config):
    try:
        os.unlink(_DB_PATH)
    except OSError:
        pass
