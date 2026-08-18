"""
FaultTicket model - one fault/support ticket raised against a
Starlink subscriber's connection. This is the core record behind the
redesigned Fault Reports / ISP Helpdesk section.

Deliberately reuses starlink_subscribers, installation_jobs and
users rather than introducing parallel customer/technician tables -
"Assigned Technician" is just a users row, exactly like
installation_jobs.technician_id already works. No new role is added
for this (kept Admin/Attendant only for now, per the current phase).
"""

from datetime import datetime
from app import db


class FaultTicket(db.Model):
    __tablename__ = "fault_tickets"

    CATEGORIES = (
        "no_internet", "slow_internet", "router_offline", "starlink_offline",
        "dish_misalignment", "cable_damage", "power_failure", "high_latency",
        "packet_loss", "wifi_coverage", "hardware_failure", "billing_issue",
        "configuration_issue", "installation_problem", "other",
    )
    PRIORITIES = ("low", "medium", "high", "critical")
    STATUSES = (
        "open", "assigned", "in_progress", "waiting_customer",
        "waiting_parts", "resolved", "closed", "cancelled",
    )

    ticket_id = db.Column(db.Integer, primary_key=True)
    ticket_number = db.Column(db.String(20), nullable=False, unique=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey("starlink_subscribers.subscriber_id"), nullable=False)
    installation_id = db.Column(
        db.Integer, db.ForeignKey("installation_jobs.installation_id", ondelete="SET NULL"), nullable=True
    )
    assigned_technician_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    category = db.Column(db.Enum(*CATEGORIES), nullable=False, default="other")
    priority = db.Column(db.Enum(*PRIORITIES), nullable=False, default="medium")
    status = db.Column(db.Enum(*STATUSES), nullable=False, default="open")
    subject = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=True)
    gps_location = db.Column(db.String(100), nullable=True)
    expected_resolution = db.Column(db.DateTime, nullable=True)
    actual_resolution = db.Column(db.DateTime, nullable=True)
    resolution_notes = db.Column(db.Text, nullable=True)
    equipment_used_notes = db.Column(db.Text, nullable=True)
    signature_path = db.Column(db.String(255), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    subscriber = db.relationship("StarlinkSubscriber")
    installation = db.relationship("InstallationJob")
    technician = db.relationship("User", foreign_keys=[assigned_technician_id])
    creator = db.relationship("User", foreign_keys=[created_by])
    activity = db.relationship(
        "FaultTicketActivity", backref="ticket", cascade="all, delete-orphan",
        order_by="FaultTicketActivity.created_at",
    )
    attachments = db.relationship(
        "FaultTicketAttachment", backref="ticket", cascade="all, delete-orphan"
    )
    equipment_used = db.relationship(
        "FaultTicketEquipment", backref="ticket", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<FaultTicket {self.ticket_number} ({self.status})>"

    @staticmethod
    def generate_ticket_number(ticket_id):
        """
        Builds the human-facing ticket number directly from the row's
        own ID (e.g. ticket_id=123 -> "TCK-000123"), same approach as
        StarlinkSubscription.generate_voucher_username - call after a
        db.session.flush() so ticket_id is already assigned.
        """
        return f"TCK-{ticket_id:06d}"

    def is_overdue(self):
        """True if this ticket is still open and past its expected resolution time."""
        if self.status in ("resolved", "closed", "cancelled") or not self.expected_resolution:
            return False
        return datetime.utcnow() > self.expected_resolution
