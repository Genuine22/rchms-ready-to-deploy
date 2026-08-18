"""
Starlink Installation routes.

This is a NEW module, separate from the existing Starlink Membership
module (app/routes/starlink.py). Membership handles subscriber
signup/vouchers/renewals for people who already have a working
connection. Installation handles the physical field-work side: survey
a site, install the dish/router, and track the job through to
activation - for schools, clinics, small businesses, and individual
homes.

Phase 1 - navigation scaffolding (sidebar + placeholder pages).
Phase 2 - the 4 database tables (site_surveys, installation_jobs,
          equipment_assignments, installation_reports).
Phase 3 (this update) - "smart" routes used by the buttons on a
          subscriber's Member Details page. Each button doesn't just
          link to a blank form - it looks up whether a record already
          exists for that subscriber/job and jumps straight to it,
          only falling back to a fresh form when there's nothing yet.
          This is also where the underlying create/view pages for
          surveys, jobs, equipment and reports are first built.
"""

from datetime import date
import calendar
from calendar import monthrange
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, Response
from flask_login import login_required, current_user
from sqlalchemy import extract

from app import db
from app.models.starlink_subscriber import StarlinkSubscriber
from app.models.site_survey import SiteSurvey
from app.models.installation_job import InstallationJob
from app.models.equipment_assignment import EquipmentAssignment
from app.models.installation_report import InstallationReport
from app.models.installation_activity import InstallationActivity
from app.models.user import User
from app.models.inventory_item import InventoryItem
from app.models.job_equipment_item import JobEquipmentLine
from app.models.fault_ticket import FaultTicket
from app.reports import installation_pdf

installation_bp = Blueprint("installation", __name__, url_prefix="/installation")


# Central place to describe each section still WITHOUT a real page of
# its own, so the sidebar and the placeholder view stay in sync. Once
# a section is built for real it should be removed from here and given
# its own route/template.
SECTIONS = {}


def _active_staff():
    return User.query.filter_by(is_active_flag=True).order_by(User.full_name).all()


def _log_activity(subscriber_id, event_type, description, installation_id=None):
    """
    Records one line on a member's Timeline. Called right alongside
    the db.session.commit() for whatever just happened - deliberately
    NOT batched into that same commit, so a failed log write (which
    shouldn't really ever happen) can't take down the real operation.
    """
    entry = InstallationActivity(
        subscriber_id=subscriber_id,
        installation_id=installation_id,
        event_type=event_type,
        description=description,
    )
    db.session.add(entry)
    db.session.commit()


# Order used to work out how far along the linear part of the workflow
# a job is. "cancelled" is deliberately excluded - it can happen from
# any state, so it's handled as a special banner instead of a tracker
# position.
STATUS_RANK = {
    "pending": 0,
    "approved": 1,
    "scheduled": 2,
    "in_progress": 3,
    "activated": 4,
    "completed": 5,
}

# (key, label, icon) for each step shown in the progress tracker.
# "Survey" and "Equipment" aren't job statuses - they're driven by
# whether a survey is linked / equipment has been assigned - so they
# sit alongside the status-driven steps rather than coming from
# STATUS_RANK directly.
TRACKER_STEPS = [
    ("survey", "Survey", "map-pin"),
    ("approved", "Approved", "check-circle"),
    ("equipment", "Equipment", "package"),
    ("scheduled", "Scheduled", "calendar-days"),
    ("installing", "Installing", "hard-hat"),
    ("activated", "Activated", "zap"),
    ("completed", "Completed", "flag"),
]


def _build_tracker(job):
    """
    Returns the list of tracker steps (each with done/current flags)
    plus an overall progress percentage, for the Phase 4 progress
    tracker shown at the top of a job's detail page.
    """
    rank = STATUS_RANK.get(job.status, -1)

    done_map = {
        "survey": job.survey_id is not None,
        "approved": rank >= 1,
        "equipment": len(job.equipment) > 0,
        "scheduled": rank >= 2,
        "installing": rank >= 3,
        "activated": rank >= 4,
        "completed": rank >= 5,
    }

    steps = []
    first_incomplete_marked = False
    for key, label, icon in TRACKER_STEPS:
        done = done_map[key]
        is_current = (not done) and (not first_incomplete_marked) and job.status != "cancelled"
        if is_current:
            first_incomplete_marked = True
        steps.append({"key": key, "label": label, "icon": icon, "done": done, "current": is_current})

    completed_count = sum(1 for s in steps if s["done"])
    progress_percent = round((completed_count / len(steps)) * 100)

    return steps, progress_percent


def _sync_inventory_for_status(job, new_status, old_status, performed_by=None):
    """
    The heart of "automatic inventory deduction" (Feature 1). Called
    any time a job's status changes - never call
    InventoryItem.apply_transaction() directly from a route for this
    purpose, so this stays the single place the rule lives.

      - Reaching "completed" for the first time deducts every
        equipment line assigned to the job that hasn't been deducted
        yet.
      - Moving to "cancelled" restores every line that HAD been
        deducted (i.e. the job was completed, then reversed) but not
        yet restored. Lines that were only ever assigned and never
        deducted need no restoration - the stock was never actually
        removed (see InventoryItem.reserved_quantity(), which stops
        counting a line the moment its job is cancelled).

    Runs as part of the same request as the status change; the
    caller still owns the final db.session.commit() so the status
    update and every stock movement land in one transaction.
    """
    if new_status == old_status:
        return

    if new_status == "completed":
        for line in job.equipment_lines:
            if not line.deducted:
                line.item.apply_transaction(
                    "deducted", line.quantity_assigned, performed_by=performed_by,
                    installation_id=job.installation_id,
                    notes=f"Installation #{job.installation_id} completed.",
                )
                line.deducted = True

    elif new_status == "cancelled":
        for line in job.equipment_lines:
            if line.deducted and not line.restored:
                line.item.apply_transaction(
                    "restored", line.quantity_assigned, performed_by=performed_by,
                    installation_id=job.installation_id,
                    notes=f"Installation #{job.installation_id} cancelled/reversed.",
                )
                line.restored = True


# ============================================================
# OVERVIEW / PLACEHOLDERS
# ============================================================

@installation_bp.route("/")
@login_required
def home():
    """
    Starlink Installation overview: dashboard cards for what needs
    attention right now, plus links into every section.
    """
    today = date.today()

    pending_surveys = SiteSurvey.query.filter_by(status="pending").count()
    scheduled_installations = InstallationJob.query.filter_by(status="scheduled").count()
    pending_activation = InstallationJob.query.filter_by(status="in_progress").count()
    completed_today = InstallationReport.query.filter(
        InstallationReport.completion_date == today
    ).count()
    available_kits = InventoryItem.query.filter_by(status="available").count()
    low_stock_count = len([i for i in InventoryItem.query.all() if i.is_low_stock() or i.is_out_of_stock()])
    open_fault_tickets = FaultTicket.query.filter(FaultTicket.status.notin_(("resolved", "closed", "cancelled"))).count()

    return render_template(
        "installation/home.html",
        sections=SECTIONS,
        pending_surveys=pending_surveys,
        scheduled_installations=scheduled_installations,
        pending_activation=pending_activation,
        completed_today=completed_today,
        available_kits=available_kits,
        low_stock_count=low_stock_count,
        open_fault_tickets=open_fault_tickets,
    )


@installation_bp.route("/section/<section>")
@login_required
def section_placeholder(section):
    """Shared placeholder view for sections that don't have a real page yet."""
    info = SECTIONS.get(section)
    if not info:
        abort(404)
    return render_template("installation/coming_soon.html", section=info)


@installation_bp.route("/schedule")
@login_required
def schedule():
    """
    Calendar view of upcoming site surveys and installation jobs,
    filterable by technician. "Upcoming" means still pending action -
    surveys not yet done, and jobs scheduled or currently in progress
    (completed/cancelled work isn't something to schedule around).
    """
    today = date.today()
    month = request.args.get("month", type=int) or today.month
    year = request.args.get("year", type=int) or today.year
    technician_id = request.args.get("technician_id", type=int)

    first_day = date(year, month, 1)
    days_in_month = monthrange(year, month)[1]
    last_day = date(year, month, days_in_month)

    surveys_q = SiteSurvey.query.filter(
        SiteSurvey.survey_date.between(first_day, last_day), SiteSurvey.status == "pending"
    )
    jobs_q = InstallationJob.query.filter(
        InstallationJob.installation_date.between(first_day, last_day),
        InstallationJob.status.in_(("scheduled", "in_progress")),
    )
    if technician_id:
        surveys_q = surveys_q.filter(SiteSurvey.surveyor_id == technician_id)
        jobs_q = jobs_q.filter(InstallationJob.technician_id == technician_id)

    events_by_day = {d: [] for d in range(1, days_in_month + 1)}
    for s in surveys_q.all():
        events_by_day[s.survey_date.day].append({"type": "survey", "obj": s})
    for j in jobs_q.all():
        events_by_day[j.installation_date.day].append({"type": "job", "obj": j})
    # Highest-priority items first within a day so they're never buried.
    priority_rank = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    for day_events in events_by_day.values():
        day_events.sort(key=lambda e: priority_rank.get(getattr(e["obj"], "priority", "normal"), 2))

    weeks = calendar.Calendar(firstweekday=6).monthdayscalendar(year, month)

    prev_month, prev_year = (12, year - 1) if month == 1 else (month - 1, year)
    next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)

    return render_template(
        "installation/schedule.html",
        weeks=weeks, events_by_day=events_by_day,
        month=month, year=year, month_name=first_day.strftime("%B"),
        staff=_active_staff(), technician_id=technician_id,
        prev_month=prev_month, prev_year=prev_year,
        next_month=next_month, next_year=next_year,
        today=today,
    )


# ============================================================
# LIST VIEWS - what the dashboard cards link into. Kept simple
# (no search yet) since their main job right now is being a
# click-through destination for the dashboard counts.
# ============================================================

@installation_bp.route("/surveys")
@login_required
def list_surveys():
    status_filter = request.args.get("status", "").strip()
    query = SiteSurvey.query
    if status_filter in ("pending", "completed", "cancelled"):
        query = query.filter_by(status=status_filter)
    surveys = query.order_by(SiteSurvey.created_at.desc()).all()
    return render_template("installation/surveys_list.html", surveys=surveys, status_filter=status_filter)


@installation_bp.route("/jobs")
@login_required
def list_jobs():
    status_filter = request.args.get("status", "").strip()
    query = InstallationJob.query
    if status_filter in InstallationJob.STATUSES:
        query = query.filter_by(status=status_filter)
    jobs = query.order_by(InstallationJob.created_at.desc()).all()
    return render_template(
        "installation/jobs_list.html", jobs=jobs, status_filter=status_filter, statuses=InstallationJob.STATUSES
    )


# ============================================================
# SMART ENTRY POINTS - these are what the Member Details page
# buttons link to. Each one looks up the subscriber's existing
# record and jumps straight to it; only falls back to "create new"
# when nothing exists yet. No re-searching for the member.
# ============================================================

@installation_bp.route("/subscribers/<int:subscriber_id>/survey")
@login_required
def subscriber_survey(subscriber_id):
    """Site Survey button: go to this subscriber's latest survey, or start one."""
    StarlinkSubscriber.query.get_or_404(subscriber_id)
    survey = (
        SiteSurvey.query.filter_by(subscriber_id=subscriber_id)
        .order_by(SiteSurvey.created_at.desc())
        .first()
    )
    if survey:
        return redirect(url_for("installation.view_survey", survey_id=survey.survey_id))
    return redirect(url_for("installation.new_survey", subscriber_id=subscriber_id))


@installation_bp.route("/subscribers/<int:subscriber_id>/job")
@login_required
def subscriber_job(subscriber_id):
    """Installation Job button: go to this subscriber's latest job, or start one."""
    StarlinkSubscriber.query.get_or_404(subscriber_id)
    job = (
        InstallationJob.query.filter_by(subscriber_id=subscriber_id)
        .order_by(InstallationJob.created_at.desc())
        .first()
    )
    if job:
        return redirect(url_for("installation.view_job", job_id=job.installation_id))
    return redirect(url_for("installation.new_job", subscriber_id=subscriber_id))


@installation_bp.route("/subscribers/<int:subscriber_id>/equipment")
@login_required
def subscriber_equipment(subscriber_id):
    """Assign Equipment button: needs an installation job to hang off first."""
    StarlinkSubscriber.query.get_or_404(subscriber_id)
    job = (
        InstallationJob.query.filter_by(subscriber_id=subscriber_id)
        .order_by(InstallationJob.created_at.desc())
        .first()
    )
    if not job:
        flash("Start an installation job for this member before assigning equipment.", "error")
        return redirect(url_for("starlink.view_subscriber", subscriber_id=subscriber_id))
    return redirect(url_for("installation.job_equipment", job_id=job.installation_id))


@installation_bp.route("/subscribers/<int:subscriber_id>/report")
@login_required
def subscriber_report(subscriber_id):
    """Installation Report button: needs an installation job to hang off first."""
    StarlinkSubscriber.query.get_or_404(subscriber_id)
    job = (
        InstallationJob.query.filter_by(subscriber_id=subscriber_id)
        .order_by(InstallationJob.created_at.desc())
        .first()
    )
    if not job:
        flash("Start an installation job for this member before adding a report.", "error")
        return redirect(url_for("starlink.view_subscriber", subscriber_id=subscriber_id))
    return redirect(url_for("installation.job_report", job_id=job.installation_id))


# ============================================================
# SITE SURVEYS
# ============================================================

@installation_bp.route("/surveys/new", methods=["GET", "POST"])
@login_required
def new_survey():
    subscriber_id = request.args.get("subscriber_id", type=int) or request.form.get(
        "subscriber_id", type=int
    )
    subscriber = StarlinkSubscriber.query.get_or_404(subscriber_id) if subscriber_id else None
    if not subscriber:
        flash("Select a member to survey first.", "error")
        return redirect(url_for("starlink.list_subscribers"))

    if request.method == "POST":
        survey_date_str = request.form.get("survey_date", "").strip()
        try:
            survey_date = (
                date.fromisoformat(survey_date_str) if survey_date_str else date.today()
            )
        except ValueError:
            survey_date = date.today()

        new_record = SiteSurvey(
            subscriber_id=subscriber.subscriber_id,
            surveyor_id=request.form.get("surveyor_id", type=int) or None,
            survey_date=survey_date,
            gps_location=request.form.get("gps_location", "").strip() or None,
            roof_type=request.form.get("roof_type", "").strip() or None,
            mount_type=request.form.get("mount_type", "").strip() or None,
            obstruction_level=request.form.get("obstruction_level") or "none",
            estimated_cable_length=request.form.get("estimated_cable_length", type=float),
            estimated_cost=request.form.get("estimated_cost", type=float),
            remarks=request.form.get("remarks", "").strip() or None,
            status=request.form.get("status") or "pending",
        )
        db.session.add(new_record)
        db.session.commit()
        _log_activity(
            subscriber.subscriber_id,
            "survey_created",
            "Site survey created" + (f" ({new_record.status})" if new_record.status != "pending" else ""),
        )
        flash(f"Site survey saved for {subscriber.full_name}.", "success")
        return redirect(url_for("installation.view_survey", survey_id=new_record.survey_id))

    return render_template(
        "installation/survey_form.html",
        subscriber=subscriber,
        staff=_active_staff(),
        today=date.today().isoformat(),
    )


@installation_bp.route("/surveys/<int:survey_id>")
@login_required
def view_survey(survey_id):
    survey = SiteSurvey.query.get_or_404(survey_id)
    return render_template("installation/survey_view.html", survey=survey)


@installation_bp.route("/surveys/<int:survey_id>/pdf")
@login_required
def survey_pdf(survey_id):
    survey = SiteSurvey.query.get_or_404(survey_id)
    pdf_bytes = installation_pdf.survey_pdf(survey)
    filename = f"site-survey-{survey.subscriber.full_name.replace(' ', '-').lower()}-{survey.survey_id}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ============================================================
# INSTALLATION JOBS
# ============================================================

@installation_bp.route("/jobs/new", methods=["GET", "POST"])
@login_required
def new_job():
    subscriber_id = request.args.get("subscriber_id", type=int) or request.form.get(
        "subscriber_id", type=int
    )
    subscriber = StarlinkSubscriber.query.get_or_404(subscriber_id) if subscriber_id else None
    if not subscriber:
        flash("Select a member to create an installation job for first.", "error")
        return redirect(url_for("starlink.list_subscribers"))

    latest_survey = (
        SiteSurvey.query.filter_by(subscriber_id=subscriber.subscriber_id)
        .order_by(SiteSurvey.created_at.desc())
        .first()
    )

    if request.method == "POST":
        installation_date_str = request.form.get("installation_date", "").strip()
        try:
            installation_date = (
                date.fromisoformat(installation_date_str) if installation_date_str else None
            )
        except ValueError:
            installation_date = None

        new_record = InstallationJob(
            subscriber_id=subscriber.subscriber_id,
            survey_id=request.form.get("survey_id", type=int) or None,
            technician_id=request.form.get("technician_id", type=int) or None,
            installation_date=installation_date,
            status=request.form.get("status") or "pending",
            priority=request.form.get("priority") or "normal",
            notes=request.form.get("notes", "").strip() or None,
        )
        db.session.add(new_record)
        db.session.commit()
        _log_activity(
            subscriber.subscriber_id,
            "job_created",
            "Installation job created",
            installation_id=new_record.installation_id,
        )
        if new_record.status != "pending":
            _log_activity(
                subscriber.subscriber_id,
                f"job_{new_record.status}",
                f"Installation {new_record.status.replace('_', ' ')}",
                installation_id=new_record.installation_id,
            )
        flash(f"Installation job created for {subscriber.full_name}.", "success")
        return redirect(url_for("installation.view_job", job_id=new_record.installation_id))

    return render_template(
        "installation/job_form.html",
        subscriber=subscriber,
        latest_survey=latest_survey,
        staff=_active_staff(),
        statuses=InstallationJob.STATUSES,
        priorities=InstallationJob.PRIORITIES,
        today=date.today().isoformat(),
    )


@installation_bp.route("/jobs/<int:job_id>")
@login_required
def view_job(job_id):
    job = InstallationJob.query.get_or_404(job_id)
    tracker_steps, progress_percent = _build_tracker(job)
    return render_template(
        "installation/job_view.html",
        job=job,
        statuses=InstallationJob.STATUSES,
        tracker_steps=tracker_steps,
        progress_percent=progress_percent,
    )


@installation_bp.route("/jobs/<int:job_id>/status", methods=["POST"])
@login_required
def update_job_status(job_id):
    """Quick status change from the job detail page (the tracker on the same page reflects it instantly on reload)."""
    job = InstallationJob.query.get_or_404(job_id)
    new_status = request.form.get("status")
    if new_status not in InstallationJob.STATUSES:
        flash("Invalid status.", "error")
    else:
        old_status = job.status
        job.status = new_status
        _sync_inventory_for_status(job, new_status, old_status, performed_by=current_user.user_id)
        db.session.commit()
        if new_status != old_status:
            _log_activity(
                job.subscriber_id,
                f"job_{new_status}",
                f"Installation {new_status.replace('_', ' ')}",
                installation_id=job.installation_id,
            )
        flash(f"Installation status updated to '{new_status.replace('_', ' ').title()}'.", "success")
    return redirect(url_for("installation.view_job", job_id=job_id))


# ============================================================
# EQUIPMENT ASSIGNMENTS
# ============================================================

@installation_bp.route("/jobs/<int:job_id>/equipment")
@login_required
def job_equipment(job_id):
    """Shows the most recent equipment assignment for this job, or sends you to assign one."""
    job = InstallationJob.query.get_or_404(job_id)
    assignment = (
        EquipmentAssignment.query.filter_by(installation_id=job_id)
        .order_by(EquipmentAssignment.assigned_date.desc())
        .first()
    )
    if not assignment:
        return redirect(url_for("installation.new_equipment", job_id=job_id))
    return render_template("installation/equipment_view.html", job=job, assignment=assignment)


@installation_bp.route("/jobs/<int:job_id>/equipment/new", methods=["GET", "POST"])
@login_required
def new_equipment(job_id):
    job = InstallationJob.query.get_or_404(job_id)

    if request.method == "POST":
        assigned_date_str = request.form.get("assigned_date", "").strip()
        try:
            assigned_date = (
                date.fromisoformat(assigned_date_str) if assigned_date_str else date.today()
            )
        except ValueError:
            assigned_date = date.today()

        new_record = EquipmentAssignment(
            installation_id=job.installation_id,
            dish_serial=request.form.get("dish_serial", "").strip() or None,
            router_serial=request.form.get("router_serial", "").strip() or None,
            cable_length=request.form.get("cable_length", type=float),
            mount_type=request.form.get("mount_type", "").strip() or None,
            assigned_by=request.form.get("assigned_by", type=int) or current_user.user_id,
            assigned_date=assigned_date,
        )
        db.session.add(new_record)
        db.session.commit()
        _log_activity(
            job.subscriber_id,
            "equipment_assigned",
            "Equipment assigned"
            + (f" (dish {new_record.dish_serial})" if new_record.dish_serial else ""),
            installation_id=job.installation_id,
        )
        flash(f"Equipment assigned for {job.subscriber.full_name}'s installation.", "success")
        return redirect(url_for("installation.job_equipment", job_id=job.installation_id))

    return render_template(
        "installation/equipment_form.html",
        job=job,
        staff=_active_staff(),
        today=date.today().isoformat(),
    )


# ============================================================
# INVENTORY EQUIPMENT LINES (Feature 1 - Equipment Assignment page)
# This is deliberately separate from the /equipment routes above:
# those cover the single dish/router serial + mount type recorded
# per job (equipment_assignments table, unchanged). This section is
# the multi-item "pick from inventory with a quantity" list
# (job_equipment_lines) that drives automatic stock deduction when
# the job is completed - see _sync_inventory_for_status() above.
# ============================================================

@installation_bp.route("/jobs/<int:job_id>/inventory-equipment")
@login_required
def job_equipment_lines(job_id):
    job = InstallationJob.query.get_or_404(job_id)
    items = InventoryItem.query.order_by(InventoryItem.item_name).all()
    return render_template(
        "installation/inventory_equipment.html", job=job, items=items,
    )


@installation_bp.route("/jobs/<int:job_id>/inventory-equipment/add", methods=["POST"])
@login_required
def add_job_equipment_line(job_id):
    job = InstallationJob.query.get_or_404(job_id)
    item = InventoryItem.query.get_or_404(request.form.get("item_id", type=int))
    quantity = request.form.get("quantity", type=float)

    if not quantity or quantity <= 0:
        flash("Enter a quantity greater than zero.", "error")
    elif quantity > item.available_quantity():
        flash(
            f"Only {item.available_quantity():g} {item.unit} of {item.item_name} available - "
            f"cannot assign {quantity:g}.", "error",
        )
    else:
        line = JobEquipmentLine(
            installation_id=job.installation_id,
            item_id=item.item_id,
            quantity_assigned=quantity,
            assigned_by=current_user.user_id,
        )
        db.session.add(line)
        db.session.commit()
        _log_activity(
            job.subscriber_id, "equipment_line_assigned",
            f"Assigned {quantity:g} {item.unit} of {item.item_name}",
            installation_id=job.installation_id,
        )
        flash(f"{item.item_name} assigned to this job.", "success")

    return redirect(url_for("installation.job_equipment_lines", job_id=job_id))


@installation_bp.route("/jobs/<int:job_id>/inventory-equipment/<int:line_id>/remove", methods=["POST"])
@login_required
def remove_job_equipment_line(job_id, line_id):
    job = InstallationJob.query.get_or_404(job_id)
    line = JobEquipmentLine.query.filter_by(job_equipment_id=line_id, installation_id=job_id).first_or_404()

    if line.deducted and not line.restored:
        # Stock already left the warehouse for this line - removing
        # the assignment must give it back, same as a cancellation would.
        line.item.apply_transaction(
            "restored", line.quantity_assigned, performed_by=current_user.user_id,
            installation_id=job.installation_id,
            notes=f"Equipment line removed from installation #{job.installation_id}.",
        )
        line.restored = True

    item_name = line.item.item_name
    db.session.delete(line)
    db.session.commit()
    _log_activity(
        job.subscriber_id, "equipment_line_removed", f"Removed {item_name} from equipment assignment",
        installation_id=job.installation_id,
    )
    flash(f"{item_name} removed from this job's equipment.", "success")
    return redirect(url_for("installation.job_equipment_lines", job_id=job_id))


# ============================================================
# INSTALLATION REPORTS
# ============================================================

@installation_bp.route("/jobs/<int:job_id>/report")
@login_required
def job_report(job_id):
    """Shows this job's completion report, or sends you to create one."""
    job = InstallationJob.query.get_or_404(job_id)
    if not job.report:
        return redirect(url_for("installation.new_report", job_id=job_id))
    return render_template("installation/report_view.html", job=job, report=job.report)


@installation_bp.route("/jobs/<int:job_id>/report/pdf")
@login_required
def installation_report_pdf(job_id):
    job = InstallationJob.query.get_or_404(job_id)
    if not job.report:
        flash("File the installation report before downloading a PDF.", "error")
        return redirect(url_for("installation.job_report", job_id=job_id))
    pdf_bytes = installation_pdf.installation_report_pdf(job)
    filename = f"installation-report-{job.subscriber.full_name.replace(' ', '-').lower()}-{job.installation_id}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@installation_bp.route("/jobs/<int:job_id>/report/new", methods=["GET", "POST"])
@login_required
def new_report(job_id):
    job = InstallationJob.query.get_or_404(job_id)
    if job.report:
        # Already exists - go to the view instead of making a duplicate.
        return redirect(url_for("installation.job_report", job_id=job_id))

    if request.method == "POST":
        completion_date_str = request.form.get("completion_date", "").strip()
        try:
            completion_date = (
                date.fromisoformat(completion_date_str) if completion_date_str else date.today()
            )
        except ValueError:
            completion_date = date.today()

        new_record = InstallationReport(
            installation_id=job.installation_id,
            download_speed=request.form.get("download_speed", type=float),
            upload_speed=request.form.get("upload_speed", type=float),
            latency=request.form.get("latency", type=int),
            installer_notes=request.form.get("installer_notes", "").strip() or None,
            completion_date=completion_date,
            customer_name=request.form.get("customer_name", "").strip() or job.subscriber.full_name,
        )
        db.session.add(new_record)
        # Completing the report is a natural signal the job is done -
        # mirrors it on the job itself if it isn't marked so already.
        old_status = job.status
        if job.status not in ("completed", "activated"):
            job.status = "completed"
            _sync_inventory_for_status(job, job.status, old_status, performed_by=current_user.user_id)
        db.session.commit()
        _log_activity(
            job.subscriber_id,
            "report_filed",
            "Installation report filed",
            installation_id=job.installation_id,
        )
        if job.status != old_status:
            _log_activity(
                job.subscriber_id,
                f"job_{job.status}",
                f"Installation {job.status.replace('_', ' ')}",
                installation_id=job.installation_id,
            )
        flash(f"Installation report saved for {job.subscriber.full_name}.", "success")
        return redirect(url_for("installation.job_report", job_id=job.installation_id))

    return render_template(
        "installation/report_form.html", job=job, today=date.today().isoformat()
    )


# ============================================================
# AGGREGATE REPORTS (Phase 7)
# Daily/Monthly Installations, Technician Performance, and an
# estimated Revenue Report. Each has an HTML view (for browsing)
# and a matching /pdf route (for the "Download PDF" button) built
# from the exact same data, via the _rows helpers below.
# ============================================================

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _parse_report_date(param_name, default=None):
    raw = request.args.get(param_name, "").strip()
    if not raw:
        return default or date.today()
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return default or date.today()


def _daily_installations_rows(day):
    jobs = (
        InstallationJob.query.filter(InstallationJob.installation_date == day)
        .order_by(InstallationJob.installation_id)
        .all()
    )
    columns = ["Member", "Status", "Technician", "Priority"]
    rows = [
        (
            j.subscriber.full_name,
            j.status.replace("_", " ").title(),
            j.technician.full_name if j.technician else "Not assigned",
            j.priority.title(),
        )
        for j in jobs
    ]
    summary = [f"Total installations scheduled for {day.strftime('%d %b %Y')}: {len(jobs)}"]
    return columns, rows, summary, jobs


def _monthly_installations_rows(year, month):
    jobs = (
        InstallationJob.query.filter(
            extract("year", InstallationJob.installation_date) == year,
            extract("month", InstallationJob.installation_date) == month,
        )
        .order_by(InstallationJob.installation_date)
        .all()
    )
    columns = ["Date", "Member", "Status", "Technician"]
    rows = [
        (
            j.installation_date.strftime("%d %b") if j.installation_date else "-",
            j.subscriber.full_name,
            j.status.replace("_", " ").title(),
            j.technician.full_name if j.technician else "Not assigned",
        )
        for j in jobs
    ]
    status_counts = {}
    for j in jobs:
        status_counts[j.status] = status_counts.get(j.status, 0) + 1
    summary = [f"Total installations in {MONTH_NAMES[month]} {year}: {len(jobs)}"]
    summary += [
        f"{status.replace('_', ' ').title()}: {count}" for status, count in sorted(status_counts.items())
    ]
    return columns, rows, summary, jobs


def _technician_performance_rows():
    technicians = User.query.filter_by(is_active_flag=True).order_by(User.full_name).all()
    columns = ["Technician", "Total Jobs", "Completed", "Activated", "Cancelled", "Completion Rate"]
    rows = []
    for tech in technicians:
        jobs = InstallationJob.query.filter_by(technician_id=tech.user_id).all()
        if not jobs:
            continue
        total = len(jobs)
        completed = sum(1 for j in jobs if j.status == "completed")
        activated = sum(1 for j in jobs if j.status == "activated")
        cancelled = sum(1 for j in jobs if j.status == "cancelled")
        rate = f"{round((completed + activated) / total * 100)}%" if total else "-"
        rows.append((tech.full_name, total, completed, activated, cancelled, rate))
    summary = [f"Technicians with at least one assigned job: {len(rows)}"]
    return columns, rows, summary


def _revenue_rows(year=None, month=None):
    """
    Estimated installation revenue, based on site_surveys.estimated_cost
    for jobs that reached activated/completed. This is an ESTIMATE, not
    an actual payment record - there's no installation billing table
    yet (StarlinkPayment only covers subscription vouchers).
    """
    query = InstallationJob.query.filter(InstallationJob.status.in_(("activated", "completed")))
    if year and month:
        query = query.filter(
            extract("year", InstallationJob.installation_date) == year,
            extract("month", InstallationJob.installation_date) == month,
        )
    jobs = query.order_by(InstallationJob.installation_date).all()

    columns = ["Date", "Member", "Status", "Estimated Cost (GHS)"]
    rows = []
    total = 0.0
    for j in jobs:
        cost = float(j.survey.estimated_cost) if j.survey and j.survey.estimated_cost is not None else 0.0
        total += cost
        rows.append((
            j.installation_date.strftime("%d %b %Y") if j.installation_date else "-",
            j.subscriber.full_name,
            j.status.title(),
            f"{cost:,.2f}" if cost else "-",
        ))
    summary = [
        f"Jobs counted: {len(jobs)}",
        f"Estimated total: GHS {total:,.2f}",
        "Figures are based on site survey cost estimates, not recorded payments.",
    ]
    return columns, rows, summary


@installation_bp.route("/reports")
@login_required
def reports_home():
    return render_template("installation/reports_home.html")


@installation_bp.route("/reports/daily")
@login_required
def daily_installations_report():
    day = _parse_report_date("date")
    columns, rows, summary, jobs = _daily_installations_rows(day)
    return render_template(
        "installation/report_table.html",
        page_title="Daily Installations",
        subtitle=day.strftime("%d %b %Y"),
        columns=columns,
        rows=rows,
        summary=summary,
        pdf_url=url_for("installation.daily_installations_pdf", date=day.isoformat()),
        filter_type="daily",
        selected_date=day.isoformat(),
    )


@installation_bp.route("/reports/daily/pdf")
@login_required
def daily_installations_pdf():
    day = _parse_report_date("date")
    columns, rows, summary, jobs = _daily_installations_rows(day)
    pdf_bytes = installation_pdf.table_report_pdf(
        "Daily Installations", day.strftime("%d %b %Y"), columns, rows, summary
    )
    filename = f"daily-installations-{day.isoformat()}.pdf"
    return Response(
        pdf_bytes, mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@installation_bp.route("/reports/monthly")
@login_required
def monthly_installations_report():
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month
    columns, rows, summary, jobs = _monthly_installations_rows(year, month)
    return render_template(
        "installation/report_table.html",
        page_title="Monthly Installations",
        subtitle=f"{MONTH_NAMES[month]} {year}",
        columns=columns,
        rows=rows,
        summary=summary,
        pdf_url=url_for("installation.monthly_installations_pdf", year=year, month=month),
        filter_type="monthly",
        selected_year=year,
        selected_month=month,
        month_names=MONTH_NAMES,
    )


@installation_bp.route("/reports/monthly/pdf")
@login_required
def monthly_installations_pdf():
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month
    columns, rows, summary, jobs = _monthly_installations_rows(year, month)
    pdf_bytes = installation_pdf.table_report_pdf(
        "Monthly Installations", f"{MONTH_NAMES[month]} {year}", columns, rows, summary
    )
    filename = f"monthly-installations-{year}-{month:02d}.pdf"
    return Response(
        pdf_bytes, mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@installation_bp.route("/reports/technician")
@login_required
def technician_performance_report():
    columns, rows, summary = _technician_performance_rows()
    return render_template(
        "installation/report_table.html",
        page_title="Technician Performance",
        subtitle="All time",
        columns=columns,
        rows=rows,
        summary=summary,
        pdf_url=url_for("installation.technician_performance_pdf"),
        filter_type=None,
    )


@installation_bp.route("/reports/technician/pdf")
@login_required
def technician_performance_pdf():
    columns, rows, summary = _technician_performance_rows()
    pdf_bytes = installation_pdf.table_report_pdf(
        "Technician Performance", "All time", columns, rows, summary
    )
    return Response(
        pdf_bytes, mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=technician-performance.pdf"},
    )


@installation_bp.route("/reports/revenue")
@login_required
def revenue_report():
    today = date.today()
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    columns, rows, summary = _revenue_rows(year, month)
    subtitle = f"{MONTH_NAMES[month]} {year}" if year and month else "All time (estimated)"
    return render_template(
        "installation/report_table.html",
        page_title="Revenue Report (Estimated)",
        subtitle=subtitle,
        columns=columns,
        rows=rows,
        summary=summary,
        pdf_url=url_for("installation.revenue_pdf", year=year or "", month=month or ""),
        filter_type="monthly_optional",
        selected_year=year or today.year,
        selected_month=month or today.month,
        month_names=MONTH_NAMES,
    )


@installation_bp.route("/reports/revenue/pdf")
@login_required
def revenue_pdf():
    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    columns, rows, summary = _revenue_rows(year, month)
    subtitle = f"{MONTH_NAMES[month]} {year}" if year and month else "All time (estimated)"
    pdf_bytes = installation_pdf.table_report_pdf("Revenue Report (Estimated)", subtitle, columns, rows, summary)
    filename = f"revenue-report-{year or 'all'}-{month or 'all'}.pdf"
    return Response(
        pdf_bytes, mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
