"""
Customer model - represents a registered hub customer.
Maps to the 'customers' table.
Full registration features (Module 2) are built out in the next step.
"""

from datetime import datetime
from app import db


class Customer(db.Model):
    __tablename__ = "customers"

    customer_id = db.Column(db.Integer, primary_key=True)
    membership_code = db.Column(db.String(20), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    date_registered = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<Customer {self.membership_code} {self.full_name}>"

    @staticmethod
    def generate_membership_code():
        """
        Creates the next membership code in sequence, e.g. RC-0001, RC-0002...
        Looks at the highest existing customer_id and adds 1, so codes never
        repeat even if customers are later deactivated.
        """
        last_customer = Customer.query.order_by(Customer.customer_id.desc()).first()
        next_number = (last_customer.customer_id + 1) if last_customer else 1
        return f"RC-{next_number:04d}"
