"""
InstallationReport model - the completion/handover report for one
installation job: measured speeds, installer notes, and who signed
off on-site. One-to-one with InstallationJob.
"""

from app import db


class InstallationReport(db.Model):
    __tablename__ = "installation_reports"

    report_id = db.Column(db.Integer, primary_key=True)
    installation_id = db.Column(
        db.Integer,
        db.ForeignKey("installation_jobs.installation_id", ondelete="CASCADE"),
        nullable=False,
    )
    download_speed = db.Column(db.Numeric(6, 2), nullable=True)  # Mbps
    upload_speed = db.Column(db.Numeric(6, 2), nullable=True)    # Mbps
    latency = db.Column(db.Integer, nullable=True)               # ms
    installer_notes = db.Column(db.Text, nullable=True)
    completion_date = db.Column(db.Date, nullable=True)
    customer_name = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return f"<InstallationReport #{self.report_id} installation={self.installation_id}>"
