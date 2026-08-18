"""
Session routes - Modules 4, 5, 6, 7
The heart of RCHMS: starting timed sessions, showing a live countdown,
auto-ending sessions when time runs out, and handling both browsing
and gaming the same way (they use the same engine, just different
service categories).
"""

from datetime import datetime, timedelta, date
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.models.session import Session
from app.models.customer import Customer
from app.models.computer import Computer
from app.models.service import Service

sessions_bp = Blueprint("sessions", __name__, url_prefix="/sessions")


def _auto_close_expired_sessions():
    """
    Safety net: find any 'active' session whose time has already run out
    (e.g. the admin's browser was closed when it hit zero) and mark it
    'expired', freeing up the computer. Called at the top of key pages
    so the system self-heals even if no one was watching the timer.
    """
    expired = Session.query.filter_by(status="active").all()
    for session in expired:
        if session.is_expired():
            session.status = "expired"
            session.actual_end_at = session.ends_at
            if session.computer:
                session.computer.status = "available"
    db.session.commit()


@sessions_bp.route("/")
@login_required
def list_sessions():
    """
    Show all currently active sessions (the main 'what's happening now' view).
    Module 7: supports filtering by category via ?category=gaming or
    ?category=internet so the admin can see gaming-only activity separately.
    """
    _auto_close_expired_sessions()

    category = request.args.get("category", "").strip().lower()

    query = Session.query.filter_by(status="active")
    if category in ("internet", "gaming"):
        query = query.join(Service).filter(Service.service_category == category)

    active_sessions = query.order_by(Session.ends_at.asc()).all()
    return render_template(
        "sessions/list.html", sessions=active_sessions, category=category
    )


@sessions_bp.route("/active.json")
@login_required
def active_sessions_json():
    """
    JSON version of the active sessions list, polled quietly every few
    seconds by the Sessions page so the "Time Left" column counts down
    smoothly in the browser (every single second) instead of relying on
    a slow, flickering full-page reload every 15 seconds.
    """
    _auto_close_expired_sessions()

    category = request.args.get("category", "").strip().lower()
    query = Session.query.filter_by(status="active")
    if category in ("internet", "gaming"):
        query = query.join(Service).filter(Service.service_category == category)

    active_sessions = query.order_by(Session.ends_at.asc()).all()

    return jsonify([
        {
            "session_id": s.session_id,
            "computer_name": s.computer.name,
            "customer_name": s.customer.full_name,
            "service_name": s.service.service_name if s.service else "Deleted package",
            "started_at": s.started_at.strftime("%I:%M %p"),
            "ends_at": s.ends_at.strftime("%I:%M %p"),
            "seconds_remaining": s.seconds_remaining(),
        }
        for s in active_sessions
    ])


@sessions_bp.route("/today")
@login_required
def today_sessions():
    """
    Dashboard drill-down: every session that started today, regardless
    of status (active, completed, expired, cancelled) - not just the
    ones still running. Most recent first.
    """
    _auto_close_expired_sessions()

    today = date.today()
    todays_sessions = (
        Session.query.filter(db.func.date(Session.started_at) == today)
        .order_by(Session.started_at.desc())
        .all()
    )
    return render_template(
        "sessions/today.html", sessions=todays_sessions, today=today
    )


@sessions_bp.route("/gaming")
@login_required
def gaming_dashboard():
    """
    Module 7: Gaming-specific view. Shows gaming computers (with live
    status) side by side with currently active gaming sessions, so the
    admin can manage the gaming area at a glance.
    """
    _auto_close_expired_sessions()

    gaming_computers = Computer.query.filter_by(computer_type="gaming").order_by(
        Computer.name
    ).all()
    gaming_sessions = (
        Session.query.join(Service)
        .filter(Session.status == "active", Service.service_category == "gaming")
        .order_by(Session.ends_at.asc())
        .all()
    )
    gaming_services = Service.query.filter_by(
        service_category="gaming"
    ).order_by(Service.is_active.desc(), Service.duration_minutes).all()

    # Session counts per package: total (informational) and active
    # (this is the only one that actually blocks deletion now - a
    # package with only finished history can be deleted freely; its
    # old sessions just lose the direct link to it).
    service_ids = [s.service_id for s in gaming_services]
    usage_counts = {}
    active_usage_counts = {}
    if service_ids:
        rows = (
            Session.query.filter(Session.service_id.in_(service_ids))
            .order_by(Session.started_at.desc())
            .all()
        )
        for sess in rows:
            usage_counts[sess.service_id] = usage_counts.get(sess.service_id, 0) + 1
            if sess.status == "active":
                active_usage_counts[sess.service_id] = active_usage_counts.get(sess.service_id, 0) + 1

    return render_template(
        "sessions/gaming.html",
        computers=gaming_computers,
        sessions=gaming_sessions,
        services=gaming_services,
        usage_counts=usage_counts,
        active_usage_counts=active_usage_counts,
    )


@sessions_bp.route("/start", methods=["GET", "POST"])
@login_required
def start_session():
    """
    Module 4: Start a new timed session.
    Admin picks customer -> computer -> service package -> Start.
    """
    if request.method == "POST":
        customer_id = request.form.get("customer_id")
        computer_id = request.form.get("computer_id")
        service_id = request.form.get("service_id")

        if not (customer_id and computer_id and service_id):
            flash("Please select a customer, computer, and package.", "error")
            return redirect(url_for("sessions.start_session"))

        customer = Customer.query.get(customer_id)
        computer = Computer.query.get(computer_id)
        service = Service.query.get(service_id)

        if not (customer and computer and service):
            flash("Invalid selection. Please try again.", "error")
            return redirect(url_for("sessions.start_session"))

        if computer.status != "available":
            flash(f"'{computer.name}' is not available right now.", "error")
            return redirect(url_for("sessions.start_session"))

        if not service.duration_minutes:
            flash("This service package has no time duration set.", "error")
            return redirect(url_for("sessions.start_session"))

        started_at = datetime.utcnow()
        ends_at = started_at + timedelta(minutes=service.duration_minutes)

        new_session = Session(
            customer_id=customer.customer_id,
            computer_id=computer.computer_id,
            service_id=service.service_id,
            started_at=started_at,
            ends_at=ends_at,
            status="active",
            created_by=current_user.user_id,
        )
        computer.status = "in_use"

        db.session.add(new_session)
        db.session.commit()

        flash(
            f"Session started for {customer.full_name} on {computer.name} "
            f"({service.service_name}).",
            "success",
        )
        return redirect(url_for("sessions.view_session", session_id=new_session.session_id))

    # GET: show the start-session form
    customers = Customer.query.filter_by(is_active=True).order_by(Customer.full_name).all()
    computers = Computer.query.filter_by(status="available").order_by(Computer.name).all()
    services = Service.query.filter_by(is_active=True).order_by(
        Service.service_category, Service.duration_minutes
    ).all()

    # Allow preselecting a computer via ?computer_id=5 (handy link from Computers page)
    preselected_computer = request.args.get("computer_id", type=int)

    return render_template(
        "sessions/start.html",
        customers=customers,
        computers=computers,
        services=services,
        preselected_computer=preselected_computer,
    )


@sessions_bp.route("/<int:session_id>")
@login_required
def view_session(session_id):
    """
    Module 5: Live countdown view for a single session.
    This page polls the server (via /sessions/<id>/status) every few
    seconds to update the remaining time without a full page reload.
    """
    _auto_close_expired_sessions()
    session = Session.query.get_or_404(session_id)
    return render_template("sessions/view.html", session=session)


@sessions_bp.route("/<int:session_id>/status")
@login_required
def session_status(session_id):
    """
    Module 5/6: JSON endpoint the countdown page polls repeatedly.
    Returns remaining seconds and whether the session has expired.
    This is also the same shape of data a client-PC agent (Module 6)
    would poll to know when to lock the screen.
    """
    session = Session.query.get_or_404(session_id)

    if session.status == "active" and session.is_expired():
        session.status = "expired"
        session.actual_end_at = session.ends_at
        if session.computer:
            session.computer.status = "available"
        db.session.commit()

    return jsonify(
        {
            "session_id": session.session_id,
            "status": session.status,
            "seconds_remaining": session.seconds_remaining(),
            "warning": session.status == "active" and session.seconds_remaining() <= 300,
        }
    )


@sessions_bp.route("/agent-status/<string:computer_name>")
def agent_status(computer_name):
    """
    Module 6: Endpoint used by the CLIENT PC AGENT (not the admin browser).
    No login required here on purpose - the client agent is a background
    program on a customer PC, not a logged-in admin, and it only ever
    reads status for the one computer name it's configured with.

    Given a computer name (e.g. "PC 1"), find that computer and report:
      - whether it currently has an active session
      - how many seconds remain
      - whether it should show a warning or lock the screen now

    Important: the admin's own countdown page (session_status, above)
    also polls and can flip a session from "active" to "expired" on its
    own. If that happens first, a plain "status=active" lookup here
    would find nothing and the agent would never learn the session just
    ended - missing its one chance to trigger the screen lock. To avoid
    that race, we also check for a session that expired moments ago
    (within EXPIRY_GRACE_SECONDS) and still report it as freshly expired
    here, even if another request already marked it "expired" first.
    """
    EXPIRY_GRACE_SECONDS = 20

    computer = Computer.query.filter_by(name=computer_name).first()

    if not computer:
        return jsonify({"error": "unknown_computer", "message": f"No computer named '{computer_name}'"}), 404

    session = Session.query.filter_by(computer_id=computer.computer_id, status="active").first()

    if not session:
        # No active session - but check if one on this computer ended
        # VERY recently, so we can still tell the agent "you just expired"
        # even if the admin page's poll already closed it out first.
        recently_ended = (
            Session.query.filter_by(computer_id=computer.computer_id)
            .filter(Session.status.in_(["expired", "completed"]))
            .order_by(Session.session_id.desc())
            .first()
        )
        if recently_ended and recently_ended.actual_end_at:
            seconds_since_end = (datetime.utcnow() - recently_ended.actual_end_at).total_seconds()
            if 0 <= seconds_since_end <= EXPIRY_GRACE_SECONDS and recently_ended.status == "expired":
                return jsonify(
                    {
                        "computer": computer.name,
                        "has_session": False,
                        "status": "expired",
                        "seconds_remaining": 0,
                        "warning": False,
                        "expired": True,
                    }
                )

        return jsonify(
            {
                "computer": computer.name,
                "has_session": False,
                "status": "idle",
                "seconds_remaining": 0,
                "warning": False,
                "expired": False,
            }
        )

    if session.is_expired():
        session.status = "expired"
        session.actual_end_at = session.ends_at
        computer.status = "available"
        db.session.commit()
        return jsonify(
            {
                "computer": computer.name,
                "has_session": False,
                "status": "expired",
                "seconds_remaining": 0,
                "warning": False,
                "expired": True,
            }
        )

    remaining = session.seconds_remaining()
    return jsonify(
        {
            "computer": computer.name,
            "has_session": True,
            "status": "active",
            "customer_name": session.customer.full_name,
            "service_name": session.service.service_name if session.service else "Deleted package",
            "seconds_remaining": remaining,
            "warning": remaining <= 300,
            "expired": False,
        }
    )


@sessions_bp.route("/<int:session_id>/end", methods=["POST"])
@login_required
def end_session(session_id):
    """
    Module 6: Manually end a session early (e.g. customer leaves before
    their time is up). Frees the computer immediately.
    """
    session = Session.query.get_or_404(session_id)

    if session.status != "active":
        flash("This session has already ended.", "error")
        return redirect(url_for("sessions.list_sessions"))

    session.status = "completed"
    session.actual_end_at = datetime.utcnow()
    if session.computer:
        session.computer.status = "available"
    db.session.commit()

    flash(f"Session on {session.computer.name} has been ended.", "success")
    return redirect(url_for("sessions.list_sessions"))


@sessions_bp.route("/<int:session_id>/extend", methods=["POST"])
@login_required
def extend_session(session_id):
    """
    Bonus convenience: add extra minutes to a running session
    (e.g. customer pays for 30 more minutes mid-session).
    """
    session = Session.query.get_or_404(session_id)

    if session.status != "active":
        flash("This session is not active.", "error")
        return redirect(url_for("sessions.list_sessions"))

    extra_minutes = request.form.get("extra_minutes", type=int)
    if not extra_minutes or extra_minutes <= 0:
        flash("Enter a valid number of minutes to add.", "error")
        return redirect(url_for("sessions.view_session", session_id=session_id))

    session.ends_at = session.ends_at + timedelta(minutes=extra_minutes)
    db.session.commit()

    flash(f"Added {extra_minutes} minutes to the session.", "success")
    return redirect(url_for("sessions.view_session", session_id=session_id))


# NEW ROUTES FOR GAMING PACKAGE MANAGEMENT
@sessions_bp.route("/package/add", methods=["POST"])
@login_required
def add_gaming_package():
    """
    Add a new gaming package (service).
    """
    service_name = request.form.get("service_name", "").strip()
    duration_minutes = request.form.get("duration_minutes", "").strip()
    price = request.form.get("price", "").strip()

    if not service_name or not duration_minutes or not price:
        flash("All fields are required.", "danger")
        return redirect(url_for("sessions.gaming_dashboard"))

    try:
        duration_minutes = int(duration_minutes)
        price = float(price)
        
        if duration_minutes <= 0 or price < 0:
            flash("Duration must be positive and price must be non-negative.", "danger")
            return redirect(url_for("sessions.gaming_dashboard"))

        new_service = Service(
            service_name=service_name,
            service_category="gaming",
            duration_minutes=duration_minutes,
            price=price,
            is_active=True
        )
        db.session.add(new_service)
        db.session.commit()
        flash(f"Package '{service_name}' added successfully!", "success")
    except (ValueError, TypeError):
        flash("Invalid input. Please check your values.", "danger")
    except Exception as e:
        flash(f"Error adding package: {str(e)}", "danger")
        db.session.rollback()

    return redirect(url_for("sessions.gaming_dashboard"))


@sessions_bp.route("/package/<int:service_id>/edit", methods=["POST"])
@login_required
def edit_gaming_package(service_id):
    """
    Edit an existing gaming package.
    """
    service = Service.query.get(service_id)
    if not service or service.service_category != "gaming":
        flash("Package not found.", "danger")
        return redirect(url_for("sessions.gaming_dashboard"))

    service_name = request.form.get("service_name", "").strip()
    duration_minutes = request.form.get("duration_minutes", "").strip()
    price = request.form.get("price", "").strip()

    if not service_name or not duration_minutes or not price:
        flash("All fields are required.", "danger")
        return redirect(url_for("sessions.gaming_dashboard"))

    try:
        duration_minutes = int(duration_minutes)
        price = float(price)
        
        if duration_minutes <= 0 or price < 0:
            flash("Duration must be positive and price must be non-negative.", "danger")
            return redirect(url_for("sessions.gaming_dashboard"))

        service.service_name = service_name
        service.duration_minutes = duration_minutes
        service.price = price
        db.session.commit()
        flash(f"Package '{service_name}' updated successfully!", "success")
    except (ValueError, TypeError):
        flash("Invalid input. Please check your values.", "danger")
    except Exception as e:
        flash(f"Error updating package: {str(e)}", "danger")
        db.session.rollback()

    return redirect(url_for("sessions.gaming_dashboard"))


@sessions_bp.route("/package/<int:service_id>/toggle-active", methods=["POST"])
@login_required
def toggle_gaming_package_active(service_id):
    """Activate/deactivate a gaming package (deactivated packages won't show when starting a new session)."""
    service = Service.query.get(service_id)
    if not service or service.service_category != "gaming":
        flash("Package not found.", "danger")
        return redirect(url_for("sessions.gaming_dashboard"))

    service.is_active = not service.is_active
    db.session.commit()
    state = "activated" if service.is_active else "deactivated"
    flash(f"'{service.service_name}' has been {state}.", "success")
    return redirect(url_for("sessions.gaming_dashboard"))


@sessions_bp.route("/package/<int:service_id>/delete", methods=["POST"])
@login_required
def delete_gaming_package(service_id):
    """
    Delete a gaming package. Past sessions that used it keep their
    record but their service_id is cleared (shows as "Deleted
    package" in history) instead of blocking the delete - only a
    currently active session stops the delete, since that session is
    still relying on the package's price/duration right now.
    """
    service = Service.query.get(service_id)
    if not service or service.service_category != "gaming":
        flash("Package not found.", "danger")
        return redirect(url_for("sessions.gaming_dashboard"))

    active_count = Session.query.filter_by(service_id=service.service_id, status="active").count()
    if active_count:
        flash(
            f"'{service.service_name}' has {active_count} active session running right now, "
            f"so it can't be deleted. Wait for the session to finish, or deactivate the package "
            f"so it stops appearing for new sessions.",
            "danger",
        )
        return redirect(url_for("sessions.gaming_dashboard"))

    try:
        service_name = service.service_name
        db.session.delete(service)
        db.session.commit()
        flash(f"Package '{service_name}' deleted successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(
            f"Error deleting package: {str(e)}. If this mentions a foreign key constraint, "
            f"run database/allow_delete_used_packages_plans.sql against your database, then try again.",
            "danger",
        )

    return redirect(url_for("sessions.gaming_dashboard"))
