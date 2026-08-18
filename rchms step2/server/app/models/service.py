"""
Service model - represents a purchasable time package
(e.g. "Browsing - 1 Hour"). Maps to the 'services' table.
"""

from app import db


class Service(db.Model):
    __tablename__ = "services"

    service_id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String(50), nullable=False)
    service_category = db.Column(
        db.Enum("internet", "gaming", "printing", "other"), nullable=False
    )
    duration_minutes = db.Column(db.Integer, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<Service {self.service_name} GHS{self.price}>"
