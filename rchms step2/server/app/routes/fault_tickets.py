"""
Fault Management / ISP Helpdesk routes (Phase 3).

Redesigns the old "Fault Reports" placeholder into a full ticketing
system for Starlink subscribers, in the style of an ISP helpdesk.

Deliberately reuses starlink_subscribers, installation_jobs, users
and the inventory module rather than introducing parallel tables:
  - "Customer" -> StarlinkSubscriber (existing)
  - "Assigned Technician" -> a users row, same pattern as
    InstallationJob.technician_id (_active_staff() from
    installation.py is reused directly below)
  - Parts used on a repair -> InventoryItem, through
    FaultTicketEquipment, with the same deduct/restore-on-status
    pattern as JobEquipmentLine for installations
    (see _sync_ticket_inventory below).

No new user role is introduced (kept Admin/Attendant only, per the
current phase) - the "Technician Interface" is just this same login
filtered down to "tickets assigned to me".
"""

import os
from datetime import datetime, date, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app import db
from app.models.fault_ticket import FaultTicket
from app.models.fault_ticket_activity import FaultTicketActivity
from app.models.fault_ticket_attachment import FaultTicketAttachment
from app.models.fault_ticket_equipment import FaultTicketEquipment
from app.models.inventory_item import InventoryItem
from app.models.starlink_subscriber import StarlinkSubscriber
from app.models.installation_job import InstallationJob
from app.models.user import User
from app.routes.installation import _active_staff

fault_bp = Blueprint("fault", __name__, url_prefix="/helpdesk")

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
CLOSED_STATUSES = ("resolved", "closed", "cancelled")


# ============================================================
# HELPERS
# ============================================================

def _log_ticket_activity(ticket_id, event_type, description, user_id=None):
    """
    Records one line on a ticket's audit trail / timeline. Committed
    on its own, deliberately separate from whatever action triggered
    it (same reasoning as installation._log_activity: a failed log
    write shouldn't be able to roll back the real action).
    """
    entry = FaultTicketActivity(
        ticket_id=ticket_id,
        user_id=user_id or (current_user.user_id if current_user.is_authenticated else None),
        event_type=event_type,
        description=description,
    )
    db.session.add(entry)
    db.session.commit()


def _sync_ticket_inventory(ticket, new_status, old_status, performed_by=None):
    """
    Automatic inventory deduction for parts used resolving a fault -
    the same rule as installations (see
    installation._sync_inventory_for_status), applied to
    FaultTicketEquipment instead of JobEquipmentLine.
    """
    if new_status == old_status:
        return

    if new_status in CLOSED_STATUSES and new_status != "cancelled" and old_status not in CLOSED_STATUSES:
        for line in ticket.equipment_used:
            if not line.deducted:
                line.item.apply_transaction(
                    "deducted", line.quantity_used, performed_by=performed_by,
                    ticket_id=ticket.ticket_id,
                    notes=f"Fault ticket {ticket.ticket_number} resolved.",
                )
                line.deducted = True

    elif new_status == "cancelled":
        for line in ticket.equipment_used:
            if line.deducted and not line.restored:
                line.item.apply_transaction(
                    "restored", line.quantity_used, performed_by=performed_by,
                    ticket_id=ticket.ticket_id,
                    notes=f"Fault ticket {ticket.ticket_number} cancelled.",
                )
                line.restored = True


def _allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


# ============================================================
# DASHBOARD
# ============================================================

@fault_bp.route("/")
@login_required
def home():
    today = date.today()
    month_start = today.replace(day=1)

    open_tickets = FaultTicket.query.filter_by(status="open").count()
    critical_tickets = FaultTicket.query.filter(
        FaultTicket.priority == "critical", FaultTicket.status.notin_(CLOSED_STATUSES)
    ).count()
    resolved_today = FaultTicket.query.filter(
        FaultTicket.status.in_(("resolved", "closed")),
        db.func.date(FaultTicket.actual_resolution) == today,
    ).count()
    pending_assignment = FaultTicket.query.filter(
        FaultTicket.assigned_technician_id.is_(None), FaultTicket.status.notin_(CLOSED_STATUSES)
    ).count()

    resolved_tickets = FaultTicket.query.filter(
        FaultTicket.actual_resolution.isnot(None)
    ).all()
    if resolved_tickets:
        total_hours = sum(
            (t.actual_resolution - t.created_at).total_seconds() / 3600 for t in resolved_tickets
        )
        avg_resolution_hours = round(total_hours / len(resolved_tickets), 1)
    else:
        avg_resolution_hours = None

    all_open = FaultTicket.query.filter(FaultTicket.status.notin_(CLOSED_STATUSES)).all()
    by_category, by_priority, by_region = {}, {}, {}
    for t in all_open:
        by_category[t.category] = by_category.get(t.category, 0) + 1
        by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
        region = (t.subscriber.location or "Unspecified") if t.subscriber else "Unspecified"
        by_region[region] = by_region.get(region, 0) + 1

    monthly_trend = []
    for i in range(5, -1, -1):
        m_start = (month_start.replace(day=1) - timedelta(days=1)).replace(day=1) if i else month_start
        # Simple 6-month rollup by calendar month
        year = month_start.year
        month = month_start.month - i
        while month <= 0:
            month += 12
            year -= 1
        count = FaultTicket.query.filter(
            db.extract("year", FaultTicket.created_at) == year,
            db.extract("month", FaultTicket.created_at) == month,
        ).count()
        monthly_trend.append((f"{year}-{month:02d}", count))

    recent_tickets = FaultTicket.query.order_by(FaultTicket.created_at.desc()).limit(8).all()

    return render_template(
        "fault/home.html",
        open_tickets=open_tickets,
        critical_tickets=critical_tickets,
        resolved_today=resolved_today,
        pending_assignment=pending_assignment,
        avg_resolution_hours=avg_resolution_hours,
        by_category=by_category,
        by_priority=by_priority,
        by_region=by_region,
        monthly_trend=monthly_trend,
        recent_tickets=recent_tickets,
    )


# ============================================================
# TICKETS
# ============================================================

@fault_bp.route("/tickets")
@login_required
def list_tickets():
    status_filter = request.args.get("status", "").strip()
    priority_filter = request.args.get("priority", "").strip()
    category_filter = request.args.get("category", "").strip()
    technician_id = request.args.get("technician_id", type=int)
    search = request.args.get("q", "").strip()

    query = FaultTicket.query
    if status_filter in FaultTicket.STATUSES:
        query = query.filter_by(status=status_filter)
    if priority_filter in FaultTicket.PRIORITIES:
        query = query.filter_by(priority=priority_filter)
    if category_filter in FaultTicket.CATEGORIES:
        query = query.filter_by(category=category_filter)
    if technician_id:
        query = query.filter_by(assigned_technician_id=technician_id)
    if search:
        like = f"%{search}%"
        query = query.join(StarlinkSubscriber).filter(
            db.or_(
                FaultTicket.ticket_number.ilike(like),
                StarlinkSubscriber.full_name.ilike(like),
                StarlinkSubscriber.phone_number.ilike(like),
            )
        )

    tickets = query.order_by(FaultTicket.created_at.desc()).all()
    staff = _active_staff()
    return render_template(
        "fault/tickets_list.html",
        tickets=tickets, staff=staff,
        status_filter=status_filter, priority_filter=priority_filter,
        category_filter=category_filter, technician_id=technician_id, search=search,
        statuses=FaultTicket.STATUSES, priorities=FaultTicket.PRIORITIES, categories=FaultTicket.CATEGORIES,
    )


@fault_bp.route("/tickets/new", methods=["GET", "POST"])
@login_required
def new_ticket():
    subscribers = StarlinkSubscriber.query.order_by(StarlinkSubscriber.full_name).all()
    staff = _active_staff()
    preselected_subscriber = request.args.get("subscriber_id", type=int)

    if request.method == "POST":
        subscriber_id = request.form.get("subscriber_id", type=int)
        if not subscriber_id:
            flash("A customer must be selected.", "error")
            return redirect(url_for("fault.new_ticket"))

        ticket = FaultTicket(
            subscriber_id=subscriber_id,
            installation_id=request.form.get("installation_id", type=int) or None,
            assigned_technician_id=request.form.get("assigned_technician_id", type=int) or None,
            category=request.form.get("category") or "other",
            priority=request.form.get("priority") or "medium",
            status="assigned" if request.form.get("assigned_technician_id") else "open",
            subject=request.form.get("subject", "").strip() or None,
            description=request.form.get("description", "").strip() or None,
            gps_location=request.form.get("gps_location", "").strip() or None,
            expected_resolution=_parse_datetime(request.form.get("expected_resolution")),
            created_by=current_user.user_id,
            ticket_number="TEMP",  # replaced below once we have the real ID
        )
        db.session.add(ticket)
        db.session.flush()
        ticket.ticket_number = FaultTicket.generate_ticket_number(ticket.ticket_id)
        db.session.commit()

        _log_ticket_activity(ticket.ticket_id, "created", f"Ticket {ticket.ticket_number} created")
        if ticket.assigned_technician_id:
            _log_ticket_activity(
                ticket.ticket_id, "assigned",
                f"Assigned to {ticket.technician.full_name}",
            )

        flash(f"Ticket {ticket.ticket_number} created.", "success")
        return redirect(url_for("fault.view_ticket", ticket_id=ticket.ticket_id))

    return render_template(
        "fault/ticket_form.html",
        subscribers=subscribers, staff=staff,
        categories=FaultTicket.CATEGORIES, priorities=FaultTicket.PRIORITIES,
        preselected_subscriber=preselected_subscriber,
    )


@fault_bp.route("/tickets/<int:ticket_id>")
@login_required
def view_ticket(ticket_id):
    ticket = FaultTicket.query.get_or_404(ticket_id)
    staff = _active_staff()
    items = InventoryItem.query.order_by(InventoryItem.item_name).all()
    return render_template(
        "fault/ticket_view.html",
        ticket=ticket, staff=staff, items=items, statuses=FaultTicket.STATUSES,
    )


@fault_bp.route("/tickets/<int:ticket_id>/assign", methods=["POST"])
@login_required
def assign_technician(ticket_id):
    ticket = FaultTicket.query.get_or_404(ticket_id)
    technician_id = request.form.get("assigned_technician_id", type=int)
    technician = User.query.get(technician_id) if technician_id else None

    ticket.assigned_technician_id = technician_id
    if ticket.status == "open" and technician_id:
        ticket.status = "assigned"
    db.session.commit()

    _log_ticket_activity(
        ticket.ticket_id, "assigned",
        f"Assigned to {technician.full_name}" if technician else "Technician unassigned",
    )
    flash("Technician updated.", "success")
    return redirect(url_for("fault.view_ticket", ticket_id=ticket_id))


@fault_bp.route("/tickets/<int:ticket_id>/status", methods=["POST"])
@login_required
def update_status(ticket_id):
    ticket = FaultTicket.query.get_or_404(ticket_id)
    new_status = request.form.get("status")
    resolution_notes = request.form.get("resolution_notes", "").strip()

    if new_status not in FaultTicket.STATUSES:
        flash("Invalid status.", "error")
        return redirect(url_for("fault.view_ticket", ticket_id=ticket_id))

    old_status = ticket.status
    ticket.status = new_status
    if new_status in ("resolved", "closed") and old_status not in ("resolved", "closed"):
        ticket.actual_resolution = datetime.utcnow()
    if resolution_notes:
        ticket.resolution_notes = resolution_notes

    _sync_ticket_inventory(ticket, new_status, old_status, performed_by=current_user.user_id)
    db.session.commit()

    _log_ticket_activity(
        ticket.ticket_id, "status_changed",
        f"Status changed from {old_status.replace('_',' ').title()} to {new_status.replace('_',' ').title()}",
    )
    flash(f"Ticket status updated to {new_status.replace('_',' ').title()}.", "success")
    return redirect(url_for("fault.view_ticket", ticket_id=ticket_id))


@fault_bp.route("/tickets/<int:ticket_id>/note", methods=["POST"])
@login_required
def add_note(ticket_id):
    ticket = FaultTicket.query.get_or_404(ticket_id)
    note = request.form.get("note", "").strip()
    if not note:
        flash("Write something before submitting a work note.", "error")
    else:
        _log_ticket_activity(ticket.ticket_id, "work_note", note)
        flash("Note added.", "success")
    return redirect(url_for("fault.view_ticket", ticket_id=ticket_id))


@fault_bp.route("/tickets/<int:ticket_id>/attachments", methods=["POST"])
@login_required
def upload_attachment(ticket_id):
    ticket = FaultTicket.query.get_or_404(ticket_id)
    file = request.files.get("photo")
    attachment_type = request.form.get("attachment_type", "photo_general")

    if not file or file.filename == "":
        flash("Choose a photo to upload.", "error")
        return redirect(url_for("fault.view_ticket", ticket_id=ticket_id))
    if not _allowed_image(file.filename):
        flash("Only image files (png, jpg, jpeg, gif, webp) are allowed.", "error")
        return redirect(url_for("fault.view_ticket", ticket_id=ticket_id))

    folder = os.path.join(current_app.static_folder, "uploads", "fault_tickets", str(ticket_id))
    os.makedirs(folder, exist_ok=True)
    filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secure_filename(file.filename)}"
    file.save(os.path.join(folder, filename))

    relative_path = f"uploads/fault_tickets/{ticket_id}/{filename}"
    attachment = FaultTicketAttachment(
        ticket_id=ticket_id, file_path=relative_path,
        attachment_type=attachment_type if attachment_type in FaultTicketAttachment.TYPES else "photo_general",
        caption=request.form.get("caption", "").strip() or None,
        uploaded_by=current_user.user_id,
    )
    db.session.add(attachment)
    db.session.commit()

    _log_ticket_activity(ticket.ticket_id, "attachment_uploaded", f"Uploaded {attachment.attachment_type.replace('_',' ')}")
    flash("Photo uploaded.", "success")
    return redirect(url_for("fault.view_ticket", ticket_id=ticket_id))


# ============================================================
# EQUIPMENT USED (parts consumed resolving the fault)
# ============================================================

@fault_bp.route("/tickets/<int:ticket_id>/equipment/add", methods=["POST"])
@login_required
def add_ticket_equipment(ticket_id):
    ticket = FaultTicket.query.get_or_404(ticket_id)
    item = InventoryItem.query.get_or_404(request.form.get("item_id", type=int))
    quantity = request.form.get("quantity", type=float)

    if not quantity or quantity <= 0:
        flash("Enter a quantity greater than zero.", "error")
    elif quantity > item.available_quantity():
        flash(
            f"Only {item.available_quantity():g} {item.unit} of {item.item_name} available.", "error",
        )
    else:
        line = FaultTicketEquipment(
            ticket_id=ticket_id, item_id=item.item_id, quantity_used=quantity,
            assigned_by=current_user.user_id,
        )
        db.session.add(line)
        db.session.commit()
        _log_ticket_activity(ticket_id, "equipment_used", f"Used {quantity:g} {item.unit} of {item.item_name}")
        flash(f"{item.item_name} added to this ticket.", "success")

    return redirect(url_for("fault.view_ticket", ticket_id=ticket_id))


@fault_bp.route("/tickets/<int:ticket_id>/equipment/<int:line_id>/remove", methods=["POST"])
@login_required
def remove_ticket_equipment(ticket_id, line_id):
    ticket = FaultTicket.query.get_or_404(ticket_id)
    line = FaultTicketEquipment.query.filter_by(ticket_equipment_id=line_id, ticket_id=ticket_id).first_or_404()

    if line.deducted and not line.restored:
        line.item.apply_transaction(
            "restored", line.quantity_used, performed_by=current_user.user_id,
            ticket_id=ticket_id, notes=f"Equipment line removed from ticket {ticket.ticket_number}.",
        )
        line.restored = True

    item_name = line.item.item_name
    db.session.delete(line)
    db.session.commit()
    _log_ticket_activity(ticket_id, "equipment_removed", f"Removed {item_name} from ticket")
    flash(f"{item_name} removed.", "success")
    return redirect(url_for("fault.view_ticket", ticket_id=ticket_id))


# ============================================================
# TECHNICIAN INTERFACE
# ============================================================

@fault_bp.route("/my-tickets")
@login_required
def technician_home():
    """
    'My Assigned Tickets' / "Today's Jobs" - no separate Technician
    role exists yet, so this simply shows whatever is assigned to the
    currently logged-in user (any admin/attendant can be a field
    technician on a ticket, same as on an installation job).
    """
    today = date.today()
    my_tickets = (
        FaultTicket.query.filter_by(assigned_technician_id=current_user.user_id)
        .filter(FaultTicket.status.notin_(("closed", "cancelled")))
        .order_by(FaultTicket.priority.desc(), FaultTicket.created_at)
        .all()
    )
    todays_jobs = [
        t for t in my_tickets
        if t.expected_resolution and t.expected_resolution.date() == today
    ]
    return render_template(
        "fault/technician_home.html", my_tickets=my_tickets, todays_jobs=todays_jobs,
    )


# ============================================================
# HELPERS
# ============================================================

def _parse_datetime(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None
