"""
InventoryItem model - one stocked item/SKU in the warehouse (e.g.
"TP-Link CPE210 Access Point" or "30m outdoor Ethernet cable spool").

IMPORTANT: quantity_in_stock is a running total that must NEVER be
edited directly from a form. It only ever changes as the result of a
row written to inventory_transactions (stock in, deducted, restored,
damaged, lost, returned, adjustment) - see
InventoryItem.apply_transaction() below, which is the single place
that both writes the log entry and updates the total, inside one
atomic commit. This is what "inventory should not reduce manually"
means in practice: every quantity change is logged, and the log is
the reason the number moved.
"""

from app import db


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    STATUSES = ("available", "assigned", "installed", "damaged", "returned", "lost")

    item_id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("inventory_categories.category_id"), nullable=False)
    item_name = db.Column(db.String(150), nullable=False)
    brand = db.Column(db.String(100), nullable=True)
    model = db.Column(db.String(100), nullable=True)
    serial_number = db.Column(db.String(100), nullable=True, unique=True)
    asset_tag = db.Column(db.String(100), nullable=True, unique=True)
    qr_code = db.Column(db.String(150), nullable=True)
    unit = db.Column(db.String(20), nullable=False, default="pcs")  # pcs, meters, box, etc.
    quantity_in_stock = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    minimum_stock_level = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=True)
    supplier = db.Column(db.String(150), nullable=True)
    purchase_date = db.Column(db.Date, nullable=True)
    warranty_expiry = db.Column(db.Date, nullable=True)
    warehouse_location = db.Column(db.String(150), nullable=True)
    status = db.Column(db.Enum(*STATUSES), nullable=False, default="available")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    updated_at = db.Column(db.DateTime, server_default=db.func.now(), onupdate=db.func.now())

    transactions = db.relationship(
        "InventoryTransaction", backref="item", cascade="all, delete-orphan", lazy="dynamic"
    )

    def __repr__(self):
        return f"<InventoryItem {self.item_name} ({self.quantity_in_stock} {self.unit})>"

    # ------------------------------------------------------------
    # Stock math
    # ------------------------------------------------------------
    def reserved_quantity(self):
        """
        Quantity already earmarked (assigned but not yet deducted) on
        installation jobs or fault tickets that haven't been
        cancelled. Kept separate from quantity_in_stock so the
        physical stock count stays true until a job actually
        completes - this is only used to stop double-booking the
        same units on two jobs at once.
        """
        from app.models.job_equipment_item import JobEquipmentLine
        from app.models.fault_ticket_equipment import FaultTicketEquipment
        from app.models.installation_job import InstallationJob
        from app.models.fault_ticket import FaultTicket

        job_reserved = (
            db.session.query(db.func.coalesce(db.func.sum(JobEquipmentLine.quantity_assigned), 0))
            .join(InstallationJob, JobEquipmentLine.installation_id == InstallationJob.installation_id)
            .filter(
                JobEquipmentLine.item_id == self.item_id,
                JobEquipmentLine.deducted.is_(False),
                InstallationJob.status != "cancelled",
            )
            .scalar()
        )
        ticket_reserved = (
            db.session.query(db.func.coalesce(db.func.sum(FaultTicketEquipment.quantity_used), 0))
            .join(FaultTicket, FaultTicketEquipment.ticket_id == FaultTicket.ticket_id)
            .filter(
                FaultTicketEquipment.item_id == self.item_id,
                FaultTicketEquipment.deducted.is_(False),
                FaultTicket.status != "cancelled",
            )
            .scalar()
        )
        return float(job_reserved or 0) + float(ticket_reserved or 0)

    def available_quantity(self):
        """Stock physically on hand, minus anything already earmarked for a pending job/ticket."""
        return max(0.0, float(self.quantity_in_stock) - self.reserved_quantity())

    def is_out_of_stock(self):
        return float(self.quantity_in_stock) <= 0

    def is_low_stock(self):
        return float(self.quantity_in_stock) <= float(self.minimum_stock_level) and not self.is_out_of_stock()

    # ------------------------------------------------------------
    # The ONLY supported way to change quantity_in_stock.
    # ------------------------------------------------------------
    def apply_transaction(self, transaction_type, quantity, performed_by=None,
                           installation_id=None, ticket_id=None, notes=None):
        """
        Writes one inventory_transactions row and updates
        quantity_in_stock to match, as a single atomic unit (caller
        still owns the db.session.commit()). `quantity` is always a
        positive number; direction is decided here by transaction_type
        so the log always reads naturally (e.g. "deducted 2.00").
        """
        from app.models.inventory_transaction import InventoryTransaction

        quantity = float(quantity)
        increases = ("stock_in", "restored", "returned")
        decreases = ("deducted", "damaged", "lost")

        if transaction_type in increases:
            self.quantity_in_stock = float(self.quantity_in_stock) + quantity
        elif transaction_type in decreases:
            self.quantity_in_stock = max(0.0, float(self.quantity_in_stock) - quantity)
        elif transaction_type == "adjustment":
            # For manual corrections `quantity` is the new absolute total,
            # not a delta - the notes field should explain why.
            self.quantity_in_stock = quantity
        else:
            raise ValueError(f"Unknown inventory transaction type: {transaction_type}")

        entry = InventoryTransaction(
            item_id=self.item_id,
            transaction_type=transaction_type,
            quantity=quantity,
            installation_id=installation_id,
            ticket_id=ticket_id,
            performed_by=performed_by,
            notes=notes,
        )
        db.session.add(entry)
        return entry
