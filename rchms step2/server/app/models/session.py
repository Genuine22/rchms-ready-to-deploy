"""
Session model - represents one timed browsing/gaming session.
Maps to the 'sessions' table. This is the heart of the system
(Modules 4-7) and gets fully built out in its own step.
"""

from datetime import datetime
from app import db


class Session(db.Model):
    __tablename__ = "sessions"

    session_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.customer_id"), nullable=False)
    computer_id = db.Column(db.Integer, db.ForeignKey("computers.computer_id"), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey("services.service_id"), nullable=True)
    started_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    actual_end_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(
        db.Enum("active", "completed", "cancelled", "expired"), default="active"
    )
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)

    customer = db.relationship("Customer")
    computer = db.relationship("Computer")
    service = db.relationship("Service")

    def __repr__(self):
        return f"<Session {self.session_id} on {self.computer_id} - {self.status}>"

    def seconds_remaining(self):
        """
        How many seconds are left on this session right now.
        Returns 0 if time has already run out (never negative).
        """
        if self.status != "active":
            return 0
        remaining = (self.ends_at - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))

    def is_expired(self):
        """True if an active session's time has run out but hasn't been closed yet."""
        return self.status == "active" and self.seconds_remaining() <= 0
