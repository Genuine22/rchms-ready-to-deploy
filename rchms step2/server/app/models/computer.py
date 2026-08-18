"""
Computer model - represents one physical PC in the hub (admin or client).
Maps to the 'computers' table. Full management features (Module 3)
are built out in a later step.
"""

from datetime import datetime
from app import db


class Computer(db.Model):
    __tablename__ = "computers"

    computer_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    computer_type = db.Column(db.Enum("browsing", "gaming"), default="browsing")
    ip_address = db.Column(db.String(45), nullable=True)
    status = db.Column(
        db.Enum("available", "in_use", "offline", "reserved"),
        default="available",
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Computer {self.name} ({self.status})>"
