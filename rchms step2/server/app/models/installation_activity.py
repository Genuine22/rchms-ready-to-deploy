"""
InstallationActivity model - an append-only log of installation events
for a subscriber (survey created, job approved/scheduled/activated/
completed/cancelled, equipment assigned, report filed). Powers the
Timeline shown on a member's profile page.

Deliberately simple: no updates, only inserts. Nothing here computes
"what's true right now" (that's what the other tables are for) - this
only remembers "what happened, and when."
"""

from app import db


class InstallationActivity(db.Model):
    __tablename__ = "installation_activity"

    activity_id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(
        db.Integer, db.ForeignKey("starlink_subscribers.subscriber_id", ondelete="CASCADE"),
        nullable=False,
    )
    installation_id = db.Column(
        db.Integer, db.ForeignKey("installation_jobs.installation_id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    subscriber = db.relationship("StarlinkSubscriber")
    installation = db.relationship("InstallationJob")

    def __repr__(self):
        return f"<InstallationActivity {self.event_type} subscriber={self.subscriber_id}>"
