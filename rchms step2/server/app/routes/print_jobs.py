"""
Business Centre routes
Covers all six Business Centre services: printing, photocopying,
scanning, lamination, CV & cover letter writing, and document typing.
Kept simple: log the job type, customer, quantity, and amount - feeds
into the dashboard and reports.
"""

from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.models.print_job import PrintJob, JOB_TYPES
from app.models.customer import Customer

print_jobs_bp = Blueprint("print_jobs", __name__, url_prefix="/business-centre")


@print_jobs_bp.route("/")
@login_required
def home():
    """Business Centre landing page - a card per service category."""
    return render_template("print_jobs/home.html", job_types=JOB_TYPES)


@print_jobs_bp.route("/log", methods=["GET", "POST"])
@login_required
def log_print_job():
    """Log a Business Centre job (printing, photocopying, scanning,
    lamination, CV & cover letter writing, or document typing)."""
    if request.method == "POST":
        customer_id = request.form.get("customer_id") or None
        job_type = request.form.get("job_type")
        pages = request.form.get("pages", type=int) or 1
        amount = request.form.get("amount", type=float)

        if not job_type or job_type not in JOB_TYPES:
            flash("Please choose a valid service type.", "error")
            return redirect(url_for("print_jobs.log_print_job"))

        if amount is None:
            flash("Amount is required.", "error")
            return redirect(url_for("print_jobs.log_print_job", type=job_type))

        if amount < 0:
            flash("Amount cannot be negative.", "error")
            return redirect(url_for("print_jobs.log_print_job", type=job_type))

        new_job = PrintJob(
            customer_id=customer_id,
            job_type=job_type,
            pages=pages,
            amount=amount,
            recorded_by=current_user.user_id,
        )
        db.session.add(new_job)
        db.session.commit()

        flash(f"{JOB_TYPES[job_type]['label']} job logged (GHS {amount:.2f}).", "success")
        return redirect(url_for("print_jobs.list_print_jobs"))

    # Preselect a type when arriving from a Business Centre category
    # card or sidebar submenu link, e.g. /business-centre/log?type=lamination
    selected_type = request.args.get("type")
    if selected_type not in JOB_TYPES:
        selected_type = "printing"

    customers = Customer.query.filter_by(is_active=True).order_by(Customer.full_name).all()
    return render_template(
        "print_jobs/log.html",
        customers=customers,
        job_types=JOB_TYPES,
        selected_type=selected_type,
    )


@print_jobs_bp.route("/list")
@login_required
def list_print_jobs():
    """Show recent Business Centre jobs, optionally filtered by type
    and/or restricted to today (?today=1), used by the dashboard's
    "Business Centre Today" card."""
    selected_type = request.args.get("type")
    today_only = request.args.get("today") == "1"

    query = PrintJob.query
    if selected_type in JOB_TYPES:
        query = query.filter_by(job_type=selected_type)
    if today_only:
        query = query.filter(db.func.date(PrintJob.created_at) == date.today())

    jobs = query.order_by(PrintJob.created_at.desc()).limit(100).all()
    return render_template(
        "print_jobs/list.html",
        jobs=jobs,
        job_types=JOB_TYPES,
        selected_type=selected_type,
        today_only=today_only,
    )
