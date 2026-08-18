"""
InventoryCategory model - admin-manageable grouping for inventory
items (Router, Access Point, Pole Mount, etc.). Seeded with the
standard ISP/Starlink-installer categories in
database/add_inventory_tables.sql; more can be added from the UI
without touching the database directly.
"""

from app import db


class InventoryCategory(db.Model):
    __tablename__ = "inventory_categories"

    category_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    items = db.relationship("InventoryItem", backref="category", lazy="dynamic")

    def __repr__(self):
        return f"<InventoryCategory {self.name}>"
