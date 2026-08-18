"""
FaultTicketAttachment model - photos (general, before/after) and a
digital sign-off signature attached to a fault ticket, uploaded from
the technician interface.
"""

from app import db


class FaultTicketAttachment(db.Model):
    __tablename__ = "fault_ticket_attachments"

    TYPES = ("photo_before", "photo_after", "photo_general", "signature", "other")

    attachment_id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(
        db.Integer, db.ForeignKey("fault_tickets.ticket_id", ondelete="CASCADE"), nullable=False
    )
    file_path = db.Column(db.String(255), nullable=False)
    attachment_type = db.Column(db.Enum(*TYPES), nullable=False, default="photo_general")
    caption = db.Column(db.String(255), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    uploaded_at = db.Column(db.DateTime, server_default=db.func.now())

    uploader = db.relationship("User")

    def __repr__(self):
        return f"<FaultTicketAttachment {self.attachment_type} ticket={self.ticket_id}>"
