"""
InventoryTransaction model - the append-only movement log for
inventory_items. Every stock change (received, deducted on
completion, restored on cancellation, damaged, lost, returned, or a
manual admin adjustment) is one row here.

This table IS the audit trail and is also the source of every
inventory report (Current Stock, Inventory Valuation, Items Issued,
Items Returned, Damaged Equipment, Monthly Usage, Most/Least Used,
Inventory Movement History) - none of those reports need their own
table, they're all just different slices of this one.

Rows are only ever created through InventoryItem.apply_transaction()
so the log and the running quantity_in_stock total can never drift
apart.
"""

from app import db


class InventoryTransaction(db.Model):
    __tablename__ = "inventory_transactions"

    TYPES = ("stock_in", "deducted", "restored", "damaged", "lost", "returned", "adjustment")

    transaction_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.item_id"), nullable=False)
    transaction_type = db.Column(db.Enum(*TYPES), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    installation_id = db.Column(
        db.Integer, db.ForeignKey("installation_jobs.installation_id", ondelete="SET NULL"), nullable=True
    )
    ticket_id = db.Column(
        db.Integer, db.ForeignKey("fault_tickets.ticket_id", ondelete="SET NULL"), nullable=True
    )
    performed_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    installation = db.relationship("InstallationJob")
    ticket = db.relationship("FaultTicket")
    performer = db.relationship("User")

    def __repr__(self):
        return f"<InventoryTransaction {self.transaction_type} item={self.item_id} qty={self.quantity}>"
