"""
Reports routes - Module 10
Generates: daily revenue report, customer list, most-used computer,
most popular package, and total sessions - all with a date range filter.
"""

from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func

from app import db
from app.models.customer import Customer
from app.models.computer import Computer
from app.models.service import Service
from app.models.session import Session
from app.models.payment import Payment
from app.models.print_job import PrintJob

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


def _parse_date_range():
    """
    Reads ?from=YYYY-MM-DD&to=YYYY-MM-DD from the query string.
    Defaults to the last 7 days (including today) if not provided
    or invalid.
    """
    today = date.today()
    default_from = today - timedelta(days=6)

    from_str = request.args.get("from", "").strip()
    to_str = request.args.get("to", "").strip()

    try:
        from_date = datetime.strptime(from_str, "%Y-%m-%d").date() if from_str else default_from
    except ValueError:
        from_date = default_from

    try:
        to_date = datetime.strptime(to_str, "%Y-%m-%d").date() if to_str else today
    except ValueError:
        to_date = today

    if from_date > to_date:
        from_date, to_date = to_date, from_date

    return from_date, to_date


@reports_bp.route("/")
@login_required
def reports_home():
    """Landing page with links to each report and the shared date range picker."""
    from_date, to_date = _parse_date_range()
    return render_template(
        "reports/home.html", from_date=from_date.isoformat(), to_date=to_date.isoformat()
    )


@reports_bp.route("/daily-revenue")
@login_required
def daily_revenue():
    """
    Daily revenue report: total revenue per day (sessions + printing)
    within the selected date range.
    """
    from_date, to_date = _parse_date_range()

    payments = (
        Payment.query.filter(
            db.func.date(Payment.paid_at) >= from_date,
            db.func.date(Payment.paid_at) <= to_date,
        ).all()
    )
    print_jobs = (
        PrintJob.query.filter(
            db.func.date(PrintJob.created_at) >= from_date,
            db.func.date(PrintJob.created_at) <= to_date,
        ).all()
    )

    # Build a day-by-day breakdown
    daily_totals = {}
    current = from_date
    while current <= to_date:
        daily_totals[current] = {"payments": 0.0, "printing": 0.0}
        current += timedelta(days=1)

    for p in payments:
        day = p.paid_at.date()
        if day in daily_totals:
            daily_totals[day]["payments"] += float(p.amount)

    for j in print_jobs:
        day = j.created_at.date()
        if day in daily_totals:
            daily_totals[day]["printing"] += float(j.amount)

    rows = [
        {
            "date": day,
            "payments": totals["payments"],
            "printing": totals["printing"],
            "total": totals["payments"] + totals["printing"],
        }
        for day, totals in sorted(daily_totals.items())
    ]
    grand_total = sum(r["total"] for r in rows)

    return render_template(
        "reports/daily_revenue.html",
        rows=rows,
        grand_total=grand_total,
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
    )


@reports_bp.route("/customers")
@login_required
def customer_list_report():
    """Full customer list with registration date and active status."""
    customers = Customer.query.order_by(Customer.date_registered.desc()).all()
    return render_template("reports/customers.html", customers=customers)


@reports_bp.route("/usage")
@login_required
def usage_report():
    """
    Most-used computer, most popular package, and total sessions
    within the selected date range.
    """
    from_date, to_date = _parse_date_range()

    sessions = (
        Session.query.filter(
            db.func.date(Session.started_at) >= from_date,
            db.func.date(Session.started_at) <= to_date,
        ).all()
    )
    total_sessions = len(sessions)

    # --- Most used computer ---
    computer_counts = {}
    for s in sessions:
        name = s.computer.name if s.computer else "Unknown"
        computer_counts[name] = computer_counts.get(name, 0) + 1
    computer_ranking = sorted(computer_counts.items(), key=lambda x: x[1], reverse=True)

    # --- Most popular package ---
    package_counts = {}
    for s in sessions:
        name = s.service.service_name if s.service else "Unknown"
        package_counts[name] = package_counts.get(name, 0) + 1
    package_ranking = sorted(package_counts.items(), key=lambda x: x[1], reverse=True)

    return render_template(
        "reports/usage.html",
        total_sessions=total_sessions,
        computer_ranking=computer_ranking,
        package_ranking=package_ranking,
        from_date=from_date.isoformat(),
        to_date=to_date.isoformat(),
    )
