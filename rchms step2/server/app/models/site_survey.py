"""
SiteSurvey model - one site assessment per Starlink subscriber, done
before an installation is approved. Captures what a technician finds
on-site (roof type, obstruction level, etc.) so the installation job
can be planned and costed.
"""

from datetime import date
from app import db


class SiteSurvey(db.Model):
    __tablename__ = "site_surveys"

    survey_id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(
        db.Integer, db.ForeignKey("starlink_subscribers.subscriber_id"), nullable=False
    )
    surveyor_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    survey_date = db.Column(db.Date, nullable=False, default=date.today)
    gps_location = db.Column(db.String(100), nullable=True)
    roof_type = db.Column(db.String(50), nullable=True)
    mount_type = db.Column(db.String(50), nullable=True)
    obstruction_level = db.Column(
        db.Enum("none", "low", "medium", "high"), default="none", nullable=False
    )
    estimated_cable_length = db.Column(db.Numeric(6, 2), nullable=True)
    estimated_cost = db.Column(db.Numeric(10, 2), nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum("pending", "completed", "cancelled"), default="pending", nullable=False
    )
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    subscriber = db.relationship("StarlinkSubscriber")
    surveyor = db.relationship("User")

    def __repr__(self):
        return f"<SiteSurvey #{self.survey_id} subscriber={self.subscriber_id} ({self.status})>"
