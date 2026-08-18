"""
RCHMS - First-time setup script.
Run this ONCE to:
  1. Create any database tables that don't exist yet (safety net -
     you already created them via schema.sql in MySQL Workbench,
     this just double-checks).
  2. Create your first admin user so you can log in.

Run with: python setup_admin.py
"""

import getpass
from app import create_app, db
from app.models.user import User

app = create_app()

with app.app_context():
    # Make sure all tables exist (won't damage existing tables/data)
    db.create_all()

    print("=" * 50)
    print("RCHMS - Create Admin Account")
    print("=" * 50)

    existing = User.query.count()
    if existing > 0:
        print(f"There are already {existing} user(s) in the system.")
        proceed = input("Create another user anyway? (y/n): ").strip().lower()
        if proceed != "y":
            print("Cancelled.")
            exit()

    full_name = input("Full name: ").strip()
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("Passwords do not match. Please run the script again.")
        exit()

    if len(password) < 6:
        print("Password must be at least 6 characters. Please run the script again.")
        exit()

    new_user = User(full_name=full_name, username=username, role="admin")
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()

    print(f"\n✅ Admin user '{username}' created successfully.")
    print("You can now log in at http://localhost:5000/login")
