"""
Computer management routes - Module 3
Handles: listing all computers with live status, adding new computers,
renaming them, changing their type, marking them offline/available,
and removing them.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required

from app import db
from app.models.computer import Computer
from app.models.session import Session

computers_bp = Blueprint("computers", __name__, url_prefix="/computers")


@computers_bp.route("/")
@login_required
def list_computers():
    """Show every computer and its current status. Supports
    ?status=available|in_use|reserved|offline to narrow the list,
    used by the dashboard's Hub Signal cards."""
    status_filter = request.args.get("status", "").strip().lower()

    query = Computer.query
    if status_filter in ("available", "in_use", "reserved", "offline"):
        query = query.filter_by(status=status_filter)

    computers = query.order_by(Computer.name.asc()).all()
    return render_template(
        "computers/list.html", computers=computers, status_filter=status_filter
    )


@computers_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_computer():
    """Add a new computer to the hub."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        computer_type = request.form.get("computer_type", "browsing")
        ip_address = request.form.get("ip_address", "").strip() or None

        if not name:
            flash("Computer name is required (e.g. 'PC 6').", "error")
            return redirect(url_for("computers.add_computer"))

        existing = Computer.query.filter_by(name=name).first()
        if existing:
            flash(f"A computer named '{name}' already exists.", "error")
            return redirect(url_for("computers.add_computer"))

        new_computer = Computer(
            name=name,
            computer_type=computer_type,
            ip_address=ip_address,
            status="available",
        )
        db.session.add(new_computer)
        db.session.commit()

        flash(f"'{name}' has been added.", "success")
        return redirect(url_for("computers.list_computers"))

    return render_template("computers/add.html")


@computers_bp.route("/<int:computer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_computer(computer_id):
    """Rename a computer, change its type, or update its IP address."""
    computer = Computer.query.get_or_404(computer_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        computer_type = request.form.get("computer_type", "browsing")
        ip_address = request.form.get("ip_address", "").strip() or None

        if not name:
            flash("Computer name is required.", "error")
            return redirect(url_for("computers.edit_computer", computer_id=computer_id))

        # Make sure no other computer already has this name
        duplicate = Computer.query.filter(
            Computer.name == name, Computer.computer_id != computer_id
        ).first()
        if duplicate:
            flash(f"Another computer is already named '{name}'.", "error")
            return redirect(url_for("computers.edit_computer", computer_id=computer_id))

        computer.name = name
        computer.computer_type = computer_type
        computer.ip_address = ip_address
        db.session.commit()

        flash("Computer details updated.", "success")
        return redirect(url_for("computers.list_computers"))

    return render_template("computers/edit.html", computer=computer)


@computers_bp.route("/<int:computer_id>/set-status", methods=["POST"])
@login_required
def set_status(computer_id):
    """
    Manually change a computer's status - mainly used to mark a PC
    'offline' (e.g. it's broken) or back to 'available'.
    Status changes to 'in_use' normally happen automatically when a
    session starts (Module 4), not from here.
    """
    computer = Computer.query.get_or_404(computer_id)
    new_status = request.form.get("status")

    if new_status not in ("available", "offline", "reserved"):
        flash("Invalid status.", "error")
        return redirect(url_for("computers.list_computers"))

    # Don't allow marking a PC offline/available if it's mid-session;
    # that should be ended properly through the session controls instead.
    active_session = Session.query.filter_by(
        computer_id=computer_id, status="active"
    ).first()
    if active_session:
        flash(
            f"'{computer.name}' has an active session. End the session first.",
            "error",
        )
        return redirect(url_for("computers.list_computers"))

    computer.status = new_status
    db.session.commit()

    flash(f"'{computer.name}' marked as {new_status}.", "success")
    return redirect(url_for("computers.list_computers"))


@computers_bp.route("/<int:computer_id>/delete", methods=["POST"])
@login_required
def delete_computer(computer_id):
    """Remove a computer entirely. Blocked if it has session history,
    to avoid breaking historical reports - offline is recommended instead."""
    computer = Computer.query.get_or_404(computer_id)

    has_history = Session.query.filter_by(computer_id=computer_id).first()
    if has_history:
        flash(
            f"'{computer.name}' has session history and cannot be deleted. "
            f"Mark it 'offline' instead if it's no longer in use.",
            "error",
        )
        return redirect(url_for("computers.list_computers"))

    name = computer.name
    db.session.delete(computer)
    db.session.commit()

    flash(f"'{name}' has been removed.", "success")
    return redirect(url_for("computers.list_computers"))
