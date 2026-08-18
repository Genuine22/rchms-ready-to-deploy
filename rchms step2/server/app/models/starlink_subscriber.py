"""
StarlinkSubscriber model - a person/home subscribed to Starlink internet
through the hub. Deliberately SEPARATE from the cyber cafe Customer
model, since Starlink subscribers may never visit the cafe at all.
"""

from datetime import datetime
from app import db


class StarlinkSubscriber(db.Model):
    __tablename__ = "starlink_subscribers"

    subscriber_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False, unique=True)
    location = db.Column(db.String(150), nullable=True)
    date_registered = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<StarlinkSubscriber {self.full_name} ({self.phone_number})>"
