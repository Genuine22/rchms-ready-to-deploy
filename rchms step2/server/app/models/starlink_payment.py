"""
StarlinkPayment model - a payment recorded against a Starlink
subscription. Separate from the cyber cafe Payment model.
"""

from datetime import datetime
from app import db


class StarlinkPayment(db.Model):
    __tablename__ = "starlink_payments"

    starlink_payment_id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(
        db.Integer, db.ForeignKey("starlink_subscriptions.subscription_id"), nullable=False
    )
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.Enum("cash", "mobile_money"), nullable=False)
    receipt_number = db.Column(db.String(30), nullable=True)
    paid_at = db.Column(db.DateTime, default=datetime.utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)

    subscription = db.relationship("StarlinkSubscription")

    def __repr__(self):
        return f"<StarlinkPayment {self.starlink_payment_id} GHS{self.amount}>"

    @staticmethod
    def generate_receipt_number():
        last = StarlinkPayment.query.order_by(StarlinkPayment.starlink_payment_id.desc()).first()
        next_number = (last.starlink_payment_id + 1) if last else 1
        return f"SLR-{next_number:06d}"
