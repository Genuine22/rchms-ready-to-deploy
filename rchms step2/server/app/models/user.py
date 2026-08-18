"""
User model - represents an administrator/attendant who can log into RCHMS.
Maps to the 'users' table created in schema.sql.
"""

from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("admin", "attendant"), nullable=False, default="attendant")
    is_active_flag = db.Column("is_active", db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    # --- Flask-Login required property ---
    # Flask-Login already provides "is_active" via UserMixin, but our DB
    # column is also named is_active, so we map the DB column to
    # is_active_flag above and override the property here to use it.
    @property
    def is_active(self):
        return self.is_active_flag

    # --- Password helpers ---
    def set_password(self, raw_password):
        """Hash and store a new password. Never store plain text passwords."""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        """Check a typed password against the stored hash."""
        return check_password_hash(self.password_hash, raw_password)

    # Flask-Login needs get_id() to return a string
    def get_id(self):
        return str(self.user_id)

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
