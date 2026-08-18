"""
FaultTicketEquipment model - replacement parts pulled from inventory
to resolve a fault ticket (e.g. a replacement router, a new pole
mount after storm damage). Same deduct/restore pattern as
JobEquipmentLine, so parts used on repairs also flow through
automatic inventory deduction - stock is only actually deducted when
the ticket is marked resolved/closed.
"""

from datetime import date
from app import db


class FaultTicketEquipment(db.Model):
    __tablename__ = "fault_ticket_equipment"

    ticket_equipment_id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(
        db.Integer, db.ForeignKey("fault_tickets.ticket_id", ondelete="CASCADE"), nullable=False
    )
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.item_id"), nullable=False)
    quantity_used = db.Column(db.Numeric(10, 2), nullable=False)
    deducted = db.Column(db.Boolean, nullable=False, default=False)
    restored = db.Column(db.Boolean, nullable=False, default=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    assigned_date = db.Column(db.Date, nullable=False, default=date.today)

    item = db.relationship("InventoryItem")
    assigner = db.relationship("User")

    def __repr__(self):
        return f"<FaultTicketEquipment ticket={self.ticket_id} item={self.item_id} qty={self.quantity_used}>"
