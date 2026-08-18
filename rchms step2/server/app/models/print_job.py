"""
PrintJob model - represents one Business Centre job: printing,
photocopying, scanning, lamination, CV & cover letter writing, or
document typing. Maps to the 'print_jobs' table.
Used for Module 9 (dashboard stats) and Module 10 (reports).
"""

from datetime import datetime
from app import db

# Every job type the Business Centre offers, plus the label used for
# the "how many" field on the log form (since "pages" doesn't quite
# fit lamination or CV writing) and the lucide icon shown for it.
JOB_TYPES = {
    "printing":        {"label": "Printing",                 "unit": "Pages",     "icon": "printer"},
    "photocopying":    {"label": "Photocopying",              "unit": "Pages",     "icon": "copy"},
    "scanning":        {"label": "Scanning",                  "unit": "Pages",     "icon": "scan-line"},
    "lamination":      {"label": "Lamination",                "unit": "Items",     "icon": "layers"},
    "cv_writing":      {"label": "CV & Cover Letter Writing",  "unit": "Documents", "icon": "file-text"},
    "document_typing": {"label": "Document Typing",            "unit": "Pages",     "icon": "keyboard"},
}


class PrintJob(db.Model):
    __tablename__ = "print_jobs"

    print_job_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.customer_id"), nullable=True)
    job_type = db.Column(
        db.Enum(*JOB_TYPES.keys(), name="job_type"), nullable=False
    )
    pages = db.Column(db.Integer, nullable=False, default=1)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)

    customer = db.relationship("Customer")

    @property
    def type_label(self):
        return JOB_TYPES.get(self.job_type, {}).get("label", self.job_type.title())

    @property
    def type_unit(self):
        return JOB_TYPES.get(self.job_type, {}).get("unit", "Pages")

    @property
    def type_icon(self):
        return JOB_TYPES.get(self.job_type, {}).get("icon", "file")

    def __repr__(self):
        return f"<PrintJob {self.job_type} x{self.pages}>"
