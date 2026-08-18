"""
Payment model - represents one payment record.
Maps to the 'payments' table. Full payment recording (Module 8)
is built out in its own step.
"""

from datetime import datetime
from app import db


class Payment(db.Model):
    __tablename__ = "payments"

    payment_id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.session_id"), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.customer_id"), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.Enum("cash", "mobile_money", "membership"), nullable=False)
    receipt_number = db.Column(db.String(30), nullable=True)
    paid_at = db.Column(db.DateTime, default=datetime.utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)

    customer = db.relationship("Customer")
    session = db.relationship("Session")

    def __repr__(self):
        return f"<Payment {self.payment_id} GHS{self.amount}>"

    @staticmethod
    def generate_receipt_number():
        """
        Creates a simple sequential receipt number, e.g. RCT-000001.
        Based on the highest existing payment_id, so it never repeats.
        """
        last_payment = Payment.query.order_by(Payment.payment_id.desc()).first()
        next_number = (last_payment.payment_id + 1) if last_payment else 1
        return f"RCT-{next_number:06d}"
