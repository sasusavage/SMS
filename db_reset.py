"""
Destructive DB reset — drops the entire public schema, then leaves the DB empty
so the next `flask db upgrade` rebuilds it from scratch.

GUARDED: only runs when DB_RESET=1 is set in the environment. This prevents an
accidental wipe on a normal deploy. Intended for the FIRST clean deploy when the
database is in an inconsistent state (tables exist but Alembic has no version
record).

Used by start.sh before migrations when DB_RESET=1.
"""
import os
import sys

from sqlalchemy import text

from app import create_app
from extensions import db


def main():
    if os.environ.get('DB_RESET') != '1':
        print('  DB_RESET not set — skipping destructive reset.')
        return
    app = create_app()
    with app.app_context():
        print('  DB_RESET=1 — dropping and recreating public schema...')
        with db.engine.begin() as conn:
            conn.execute(text('DROP SCHEMA public CASCADE'))
            conn.execute(text('CREATE SCHEMA public'))
        print('  public schema reset to empty.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f'  DB reset failed: {exc}', file=sys.stderr)
        sys.exit(1)
