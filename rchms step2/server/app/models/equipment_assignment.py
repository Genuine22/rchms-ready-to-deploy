"""
EquipmentAssignment model - the dish/router serials and mounting
details assigned to one installation job. Only meaningful attached to
a job, so it cascades if the parent job is ever deleted.
"""

from datetime import date
from app import db


class EquipmentAssignment(db.Model):
    __tablename__ = "equipment_assignments"

    equipment_assignment_id = db.Column(db.Integer, primary_key=True)
    installation_id = db.Column(
        db.Integer,
        db.ForeignKey("installation_jobs.installation_id", ondelete="CASCADE"),
        nullable=False,
    )
    dish_serial = db.Column(db.String(50), nullable=True)
    router_serial = db.Column(db.String(50), nullable=True)
    cable_length = db.Column(db.Numeric(6, 2), nullable=True)
    mount_type = db.Column(db.String(50), nullable=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    assigned_date = db.Column(db.Date, nullable=False, default=date.today)

    assigner = db.relationship("User")

    def __repr__(self):
        return f"<EquipmentAssignment #{self.equipment_assignment_id} installation={self.installation_id}>"
