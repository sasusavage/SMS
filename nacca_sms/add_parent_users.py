"""
Add Parent User Accounts to Existing Database
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from models import db, User, UserRole, Parent

def add_parent_users():
    """Add user accounts for existing parents."""
    app = create_app('development')
    
    with app.app_context():
        # Get all parents that don't have user accounts
        parents = Parent.query.all()
        
        added_count = 0
        for i, parent in enumerate(parents):
            # Check if user already exists for this parent
            existing_user = User.query.filter_by(parent_id=parent.id).first()
            if existing_user:
                print(f"Parent {parent.id} already has user: {existing_user.email}")
                continue
            
            # Create email from father_email or generate one
            email = parent.father_email or parent.mother_email or f"parent{parent.id}@sasuacademy.edu.gh"
            
            # Check if email already used
            if User.query.filter_by(email=email).first():
                email = f"parent{parent.id}@sasuacademy.edu.gh"
                if User.query.filter_by(email=email).first():
                    print(f"Could not create user for parent {parent.id}, email conflict")
                    continue
            
            user = User(
                school_id=parent.school_id,
                email=email,
                role=UserRole.PARENT,
                parent_id=parent.id
            )
            user.set_password("parent123")
            db.session.add(user)
            added_count += 1
            print(f"Created user: {email} / parent123")
        
        db.session.commit()
        print(f"\nAdded {added_count} parent user accounts.")
        print("\nAll parent logins use password: parent123")


if __name__ == '__main__':
    add_parent_users()
