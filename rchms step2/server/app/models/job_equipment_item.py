"""
JobEquipmentLine model - the Equipment Assignment page's content:
which inventory items, and how much of each, are earmarked for one
installation job (e.g. 1 Starlink Kit, 1 Router, 2 Access Points,
30m Ethernet Cable).

Deliberately a NEW, separate table from equipment_assignments (which
already exists and records the single dish/router serial + mount
type for a job). This table is the multi-line, inventory-linked list
that automatic deduction reads from - it doesn't replace or
duplicate equipment_assignments, it adds the piece that was missing.

Lifecycle:
  - Row created when an installer assigns equipment on the job's
    Equipment Assignment page (deducted=False, restored=False).
  - When the job is marked "completed", every undeducted line for
    that job gets a matching InventoryTransaction("deducted") and
    deducted flips to True (see routes/installation.py).
  - If the job is later cancelled/reversed, or the equipment is
    returned, a matching InventoryTransaction("restored") is written
    and restored flips to True, so the same line is never restored
    twice.
"""

from datetime import date
from app import db


class JobEquipmentLine(db.Model):
    __tablename__ = "job_equipment_lines"

    job_equipment_id = db.Column(db.Integer, primary_key=True)
    installation_id = db.Column(
        db.Integer, db.ForeignKey("installation_jobs.installation_id", ondelete="CASCADE"), nullable=False
    )
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.item_id"), nullable=False)
    quantity_assigned = db.Column(db.Numeric(10, 2), nullable=False)
    deducted = db.Column(db.Boolean, nullable=False, default=False)
    restored = db.Column(db.Boolean, nullable=False, default=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    assigned_date = db.Column(db.Date, nullable=False, default=date.today)

    installation = db.relationship("InstallationJob", backref=db.backref(
        "equipment_lines", cascade="all, delete-orphan"
    ))
    item = db.relationship("InventoryItem")
    assigner = db.relationship("User")

    def __repr__(self):
        return f"<JobEquipmentLine job={self.installation_id} item={self.item_id} qty={self.quantity_assigned}>"
