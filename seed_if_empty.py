"""
Deploy-time conditional seed.

Runs the full seed ONLY when the database has no schools yet (first deploy).
On subsequent deploys it no-ops, so existing tenant data is never touched.
Safe to call on every Coolify deploy.
"""
from app import create_app
from extensions import db
from models.platform import School


def main():
    app = create_app()
    with app.app_context():
        existing = db.session.query(School.id).first()
        if existing is not None:
            print("  Database already has schools — skipping seed.")
            return
    # Empty DB: run the full seed (it manages its own app context).
    print("  Empty database detected — seeding demo data...")
    import seed
    seed.main()


if __name__ == '__main__':
    main()
