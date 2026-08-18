"""
InstallationJob model - one installation attempt for a Starlink
subscriber. This is the record the Phase 4 progress tracker walks
through: pending -> approved -> scheduled -> in_progress -> activated
-> completed (or cancelled at any point before completion).

Note on ordering: "activated" comes before "completed" here (the dish
goes live, THEN the paperwork/handover report closes the job out) -
matching how installation_reports.new_report marks a job "completed"
once its report is filed. The set of enum values in the database
migration is unchanged; only this list's order (used for dropdowns
and the progress tracker) reflects it.
"""

from app import db


class InstallationJob(db.Model):
    __tablename__ = "installation_jobs"

    STATUSES = ("pending", "approved", "scheduled", "in_progress", "activated", "completed", "cancelled")
    PRIORITIES = ("low", "normal", "high", "urgent")

    installation_id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(
        db.Integer, db.ForeignKey("starlink_subscribers.subscriber_id"), nullable=False
    )
    survey_id = db.Column(
        db.Integer, db.ForeignKey("site_surveys.survey_id", ondelete="SET NULL"), nullable=True
    )
    technician_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=True)
    installation_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.Enum(*STATUSES), default="pending", nullable=False)
    priority = db.Column(db.Enum(*PRIORITIES), default="normal", nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    subscriber = db.relationship("StarlinkSubscriber")
    survey = db.relationship("SiteSurvey")
    technician = db.relationship("User")
    equipment = db.relationship(
        "EquipmentAssignment", backref="installation", cascade="all, delete-orphan"
    )
    report = db.relationship(
        "InstallationReport", backref="installation", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<InstallationJob #{self.installation_id} subscriber={self.subscriber_id} ({self.status})>"
