"""
StarlinkPlan model - a subscribable Starlink package
(e.g. "Monthly - 50GB"). Admin-configurable price, duration, and
data allocation.
"""

from app import db


class StarlinkPlan(db.Model):
    __tablename__ = "starlink_plans"

    plan_id = db.Column(db.Integer, primary_key=True)
    plan_name = db.Column(db.String(50), nullable=False)
    plan_type = db.Column(db.Enum("weekly", "monthly", "occasion"), nullable=False)
    duration_days = db.Column(db.Integer, nullable=False)
    data_allocation_gb = db.Column(db.Numeric(6, 2), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<StarlinkPlan {self.plan_name} GHS{self.price}>"
