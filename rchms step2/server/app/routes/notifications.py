"""
Notifications
A small, real (not decorative) notification feed for the header bell.
Pulls together things that genuinely need the admin's attention right
now:
  - Sessions ending within the next 5 minutes (cafe side)
  - Starlink subscriptions expiring within 3 days
  - Starlink subscriptions awaiting payment
  - Installation jobs approved but not yet scheduled
  - Installation jobs scheduled for today
  - Installation jobs installed and ready to activate
  - Fault tickets still open/unassigned, critical, or overdue
  - Inventory items low on stock or out of stock

This intentionally does NOT store notifications in the database - it
computes them fresh each time from data that already exists (sessions,
subscriptions, installation jobs, fault tickets, inventory), so
there's nothing to mark as read/unread or clean up. The bell always
reflects "what needs attention right now" - so rather than firing a
one-off "ticket created!" or "status changed!" event that could be
missed, a thing simply shows up here for as long as it's actually
sitting in a state that needs someone to act on it, and drops off the
moment it moves on (e.g. a critical ticket stops appearing the moment
it's resolved - there's no separate "resolved" notification to also
fire and later dismiss).
"""

from datetime import date
from flask import Blueprint, jsonify, url_for
from flask_login import login_required

from app.models.session import Session
from app.models.starlink_subscription import StarlinkSubscription
from app.models.installation_job import InstallationJob
from app.models.fault_ticket import FaultTicket
from app.models.inventory_item import InventoryItem

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


def _gather_notifications():
    items = []

    # --- Cafe sessions ending soon ---
    active_sessions = Session.query.filter_by(status="active").all()
    for s in active_sessions:
        remaining = s.seconds_remaining()
        if 0 < remaining <= 300:
            items.append({
                "id": f"session_ending-{s.session_id}",
                "type": "session_ending",
                "icon": "timer",
                "color": "danger",
                "title": f"{s.computer.name} ending soon",
                "detail": f"{s.customer.full_name} - {remaining // 60}:{remaining % 60:02d} left",
                "url": f"/sessions/{s.session_id}",
            })

    # --- Starlink subscriptions expiring soon ---
    active_subs = StarlinkSubscription.query.filter_by(status="active").all()
    for sub in active_subs:
        if sub.is_expiring_soon(within_days=3):
            days = sub.days_remaining()
            items.append({
                "id": f"subscription_expiring-{sub.subscription_id}",
                "type": "subscription_expiring",
                "icon": "satellite-dish",
                "color": "warning",
                "title": f"{sub.subscriber.full_name}'s plan expiring",
                "detail": f"{sub.plan.plan_name} - {days} day{'s' if days != 1 else ''} left",
                "url": f"/starlink/subscriptions/{sub.subscription_id}",
            })

    # --- Starlink subscriptions awaiting payment ---
    pending_subs = StarlinkSubscription.query.filter_by(status="pending_payment").all()
    for sub in pending_subs:
        items.append({
            "id": f"subscription_pending-{sub.subscription_id}",
            "type": "subscription_pending",
            "icon": "banknote",
            "color": "warning",
            "title": f"{sub.subscriber.full_name} - payment pending",
            "detail": f"{sub.plan.plan_name} - voucher {sub.voucher_code}",
            "url": f"/starlink/subscriptions/{sub.subscription_id}",
        })

    # --- Installation jobs approved but not yet scheduled ---
    approved_jobs = InstallationJob.query.filter_by(status="approved").all()
    for job in approved_jobs:
        items.append({
            "id": f"installation_needs_scheduling-{job.installation_id}",
            "type": "installation_needs_scheduling",
            "icon": "calendar-clock",
            "color": "warning",
            "title": f"{job.subscriber.full_name} needs scheduling",
            "detail": "Survey approved - not yet scheduled for install",
            "url": url_for("installation.view_job", job_id=job.installation_id),
        })

    # --- Installation jobs scheduled for today ---
    today = date.today()
    scheduled_today = InstallationJob.query.filter_by(status="scheduled").all()
    for job in scheduled_today:
        if job.installation_date == today:
            tech = job.technician.full_name if job.technician else "no technician assigned"
            items.append({
                "id": f"installation_today-{job.installation_id}",
                "type": "installation_today",
                "icon": "hard-hat",
                "color": "warning",
                "title": f"{job.subscriber.full_name} - installation today",
                "detail": f"Technician: {tech}",
                "url": url_for("installation.view_job", job_id=job.installation_id),
            })

    # --- Installation jobs installed and ready to activate ---
    in_progress_jobs = InstallationJob.query.filter_by(status="in_progress").all()
    for job in in_progress_jobs:
        items.append({
            "id": f"installation_ready_to_activate-{job.installation_id}",
            "type": "installation_ready_to_activate",
            "icon": "zap",
            "color": "warning",
            "title": f"{job.subscriber.full_name} ready to activate",
            "detail": "Dish installed - awaiting activation",
            "url": url_for("installation.view_job", job_id=job.installation_id),
        })

    # --- Fault tickets: critical & still unresolved ---
    critical_tickets = FaultTicket.query.filter(
        FaultTicket.priority == "critical",
        FaultTicket.status.notin_(("resolved", "closed", "cancelled")),
    ).all()
    for t in critical_tickets:
        items.append({
            "id": f"fault_critical-{t.ticket_id}",
            "type": "fault_critical",
            "icon": "alert-octagon",
            "color": "danger",
            "title": f"Critical: {t.ticket_number}",
            "detail": f"{t.subscriber.full_name} - {t.category.replace('_', ' ').title()}",
            "url": url_for("fault.view_ticket", ticket_id=t.ticket_id),
        })

    # --- Fault tickets: open and not yet assigned to a technician ---
    unassigned_tickets = FaultTicket.query.filter(
        FaultTicket.status == "open", FaultTicket.assigned_technician_id.is_(None)
    ).all()
    for t in unassigned_tickets:
        items.append({
            "id": f"fault_unassigned-{t.ticket_id}",
            "type": "fault_unassigned",
            "icon": "life-buoy",
            "color": "warning",
            "title": f"{t.ticket_number} needs a technician",
            "detail": f"{t.subscriber.full_name} - {t.category.replace('_', ' ').title()}",
            "url": url_for("fault.view_ticket", ticket_id=t.ticket_id),
        })

    # --- Fault tickets: overdue past their expected resolution ---
    open_tickets = FaultTicket.query.filter(
        FaultTicket.status.notin_(("resolved", "closed", "cancelled"))
    ).all()
    for t in open_tickets:
        if t.is_overdue():
            items.append({
                "id": f"fault_overdue-{t.ticket_id}",
                "type": "fault_overdue",
                "icon": "clock-alert",
                "color": "danger",
                "title": f"{t.ticket_number} is overdue",
                "detail": f"{t.subscriber.full_name} - expected by {t.expected_resolution.strftime('%d %b, %H:%M')}",
                "url": url_for("fault.view_ticket", ticket_id=t.ticket_id),
            })

    # --- Inventory: out of stock ---
    for i in InventoryItem.query.all():
        if i.is_out_of_stock():
            items.append({
                "id": f"inventory_out-{i.item_id}",
                "type": "inventory_out_of_stock",
                "icon": "package-x",
                "color": "danger",
                "title": f"{i.item_name} out of stock",
                "detail": f"{i.category.name}",
                "url": url_for("inventory.view_item", item_id=i.item_id),
            })
        elif i.is_low_stock():
            items.append({
                "id": f"inventory_low-{i.item_id}",
                "type": "inventory_low_stock",
                "icon": "package-minus",
                "color": "warning",
                "title": f"{i.item_name} running low",
                "detail": f"{i.quantity_in_stock:g} {i.unit} left - minimum is {i.minimum_stock_level:g}",
                "url": url_for("inventory.view_item", item_id=i.item_id),
            })

    return items


@notifications_bp.route("/feed")
@login_required
def feed():
    """JSON feed polled by the header bell every 20 seconds."""
    items = _gather_notifications()
    return jsonify({"count": len(items), "items": items})
