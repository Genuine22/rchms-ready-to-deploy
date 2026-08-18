"""
Dashboard routes - Module 9
The main "what's happening right now" view: today's customers,
today's revenue, computer status breakdown, gaming/internet session
counts, and printing stats.
"""

from datetime import date
from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user

from app import db
from app.models.customer import Customer
from app.models.computer import Computer
from app.models.session import Session
from app.models.payment import Payment
from app.models.print_job import PrintJob
from app.models.service import Service
from app.routes.sessions import _auto_close_expired_sessions

dashboard_bp = Blueprint("dashboard", __name__)


def _gather_dashboard_stats():
    """
    Shared logic for computing dashboard numbers. Used by both the
    full-page render (on first load) and the JSON refresh endpoint
    (for the silent auto-refresh, so the numbers stay current without
    a visible page reload/flash).
    """
    _auto_close_expired_sessions()

    today = date.today()

    new_customers_today = Customer.query.filter(
        db.func.date(Customer.date_registered) == today
    ).count()

    todays_payments = Payment.query.filter(db.func.date(Payment.paid_at) == today).all()
    todays_print_jobs = PrintJob.query.filter(db.func.date(PrintJob.created_at) == today).all()
    revenue_from_payments = sum(float(p.amount) for p in todays_payments)
    revenue_from_printing = sum(float(j.amount) for j in todays_print_jobs)
    total_revenue_today = revenue_from_payments + revenue_from_printing

    all_computers = Computer.query.all()
    computers_available = sum(1 for c in all_computers if c.status == "available")
    computers_in_use = sum(1 for c in all_computers if c.status == "in_use")
    computers_offline = sum(1 for c in all_computers if c.status == "offline")
    computers_reserved = sum(1 for c in all_computers if c.status == "reserved")

    active_sessions = (
        Session.query.join(Service).filter(Session.status == "active").all()
    )
    internet_sessions_active = sum(
        1 for s in active_sessions if s.service.service_category == "internet"
    )
    gaming_sessions_active = sum(
        1 for s in active_sessions if s.service.service_category == "gaming"
    )

    sessions_today = Session.query.filter(
        db.func.date(Session.started_at) == today
    ).count()

    printing_jobs_today = len(todays_print_jobs)
    printing_pages_today = sum(j.pages for j in todays_print_jobs)

    return {
        "new_customers_today": new_customers_today,
        "total_revenue_today": total_revenue_today,
        "revenue_from_payments": revenue_from_payments,
        "revenue_from_printing": revenue_from_printing,
        "computers_available": computers_available,
        "computers_in_use": computers_in_use,
        "computers_offline": computers_offline,
        "computers_reserved": computers_reserved,
        "total_computers": len(all_computers),
        "internet_sessions_active": internet_sessions_active,
        "gaming_sessions_active": gaming_sessions_active,
        "sessions_today": sessions_today,
        "printing_jobs_today": printing_jobs_today,
        "printing_pages_today": printing_pages_today,
    }


@dashboard_bp.route("/")
@login_required
def home():
    stats = _gather_dashboard_stats()
    return render_template("dashboard.html", user=current_user, stats=stats)


@dashboard_bp.route("/stats")
@login_required
def stats_json():
    """
    JSON endpoint polled quietly in the background by the dashboard
    page every 30 seconds, so numbers stay current WITHOUT a visible
    page reload/flash. See the script at the bottom of dashboard.html.
    """
    return jsonify(_gather_dashboard_stats())
