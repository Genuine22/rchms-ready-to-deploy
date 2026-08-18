"""
StarlinkSubscription model - one signup/renewal cycle for a subscriber.
Tracks the voucher login (username + password, like a real WiFi
voucher/captive-portal credential), start/end dates, data allocation
copied from the plan at signup time, and status (pending_payment /
active / expired / cancelled).
"""

import random
import string
from datetime import datetime, date, timedelta
from app import db


class StarlinkSubscription(db.Model):
    __tablename__ = "starlink_subscriptions"

    subscription_id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(
        db.Integer, db.ForeignKey("starlink_subscribers.subscriber_id"), nullable=False
    )
    plan_id = db.Column(db.Integer, db.ForeignKey("starlink_plans.plan_id"), nullable=True)
    # The voucher login, issued like a real Starlink-reseller / WiFi
    # captive-portal voucher: a short username (e.g. SL0042) plus a
    # password-style access code (e.g. X7K2P9). voucher_code is kept as
    # the column name for the password half so existing data/lookups by
    # voucher_code keep working unchanged.
    voucher_username = db.Column(db.String(20), unique=True, nullable=True)
    voucher_code = db.Column(db.String(20), unique=True, nullable=False)
    starts_at = db.Column(db.Date, nullable=False)
    ends_at = db.Column(db.Date, nullable=False)
    data_allocation_gb = db.Column(db.Numeric(6, 2), nullable=False)
    status = db.Column(
        db.Enum("pending_payment", "active", "expired", "cancelled"),
        default="pending_payment",
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)

    subscriber = db.relationship("StarlinkSubscriber")
    plan = db.relationship("StarlinkPlan")

    def __repr__(self):
        return f"<StarlinkSubscription {self.voucher_username}/{self.voucher_code} ({self.status})>"

    @staticmethod
    def generate_voucher_username(subscription_id):
        """
        Creates the voucher username directly from this subscription's
        own ID, e.g. subscription_id=42 -> "SL0042". Takes the ID as a
        parameter (rather than querying for "highest existing + 1")
        because by the time this is called the row already exists
        (after a db.session.flush()), so querying for the max would
        incorrectly include this row itself.
        """
        return f"SL{subscription_id:04d}"

    @staticmethod
    def generate_voucher_code():
        """
        Creates a random, easy-to-read access code/password, e.g.
        X7K2P9. Excludes confusing characters (0/O, 1/I) since this gets
        handed to a customer to type back in later. Retries on the
        rare chance of a collision with an existing code.
        """
        safe_chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        while True:
            code = "".join(random.choices(safe_chars, k=6))
            exists = StarlinkSubscription.query.filter_by(voucher_code=code).first()
            if not exists:
                return code

    def days_remaining(self):
        """How many full days are left until this subscription ends (0 if expired)."""
        remaining = (self.ends_at - date.today()).days
        return max(0, remaining)

    def is_expired(self):
        """True if an active/pending subscription's end date has passed."""
        return self.status in ("active", "pending_payment") and date.today() > self.ends_at

    def is_expiring_soon(self, within_days=3):
        """True if this subscription is active and ends within the next N days."""
        return self.status == "active" and 0 <= self.days_remaining() <= within_days

    @staticmethod
    def calculate_end_date(start_date, plan):
        """Given a start date and a StarlinkPlan, compute the end date."""
        return start_date + timedelta(days=plan.duration_days)
