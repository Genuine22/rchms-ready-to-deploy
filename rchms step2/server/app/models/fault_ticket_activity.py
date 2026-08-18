"""
FaultTicketActivity model - an append-only log of everything that
happens to one fault ticket (created, assigned, status changed,
photo uploaded, resolved, closed). Mirrors installation_activity
exactly, and powers the ticket's Timeline / audit trail.
"""

from app import db


class FaultTicketActivity(db.Model):
    __tablename__ = "fault_ticket_activity"

    activity_id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(
        db.Integer, db.ForeignKey("fault_tickets.ticket_id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    event_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    user = db.relationship("User")

    def __repr__(self):
        return f"<FaultTicketActivity {self.event_type} ticket={self.ticket_id}>"
