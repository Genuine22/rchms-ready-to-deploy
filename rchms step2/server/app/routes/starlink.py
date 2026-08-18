"""
Starlink Membership routes
A self-contained module, separate from the cyber cafe (customers,
sessions, payments, computers). Covers:
  - Subscribers (separate people list)
  - Plans (Weekly / Monthly / Occasion, admin-configurable)
  - Subscriptions (signup/renewal cycles, with auto-generated vouchers)
  - Payments (mark received, activates the subscription)
  - Renewals dashboard (subscriptions expiring soon)
  - Voucher lookup (a subscriber can check their own status)
"""

from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import or_

from app import db
from app.models.starlink_subscriber import StarlinkSubscriber
from app.models.starlink_plan import StarlinkPlan
from app.models.starlink_subscription import StarlinkSubscription
from app.models.starlink_payment import StarlinkPayment
from app.models.installation_activity import InstallationActivity
from app.models.fault_ticket import FaultTicket

starlink_bp = Blueprint("starlink", __name__, url_prefix="/starlink")


def _auto_expire_subscriptions():
    """
    Safety net: any subscription whose end date has passed gets marked
    'expired' (unless it's already cancelled). Called at the top of key
    pages so status is always current without needing a background job.
    """
    candidates = StarlinkSubscription.query.filter(
        StarlinkSubscription.status.in_(["active", "pending_payment"])
    ).all()
    changed = False
    for sub in candidates:
        if sub.is_expired():
            sub.status = "expired"
            changed = True
    if changed:
        db.session.commit()


# ============================================================
# DASHBOARD / HOME
# ============================================================

@starlink_bp.route("/")
@login_required
def home():
    """Starlink Membership overview: key stats and quick links."""
    _auto_expire_subscriptions()

    total_subscribers = StarlinkSubscriber.query.filter_by(is_active=True).count()
    active_subscriptions = StarlinkSubscription.query.filter_by(status="active").count()
    pending_payment = StarlinkSubscription.query.filter_by(status="pending_payment").count()

    expiring_soon = [
        sub
        for sub in StarlinkSubscription.query.filter_by(status="active").all()
        if sub.is_expiring_soon(within_days=3)
    ]
    expiring_soon.sort(key=lambda s: s.ends_at)

    today = date.today()
    revenue_today = sum(
        float(p.amount)
        for p in StarlinkPayment.query.filter(
            db.func.date(StarlinkPayment.paid_at) == today
        ).all()
    )

    return render_template(
        "starlink/home.html",
        total_subscribers=total_subscribers,
        active_subscriptions=active_subscriptions,
        pending_payment=pending_payment,
        expiring_soon=expiring_soon,
        revenue_today=revenue_today,
    )


# ============================================================
# SUBSCRIBERS
# ============================================================

@starlink_bp.route("/subscribers")
@login_required
def list_subscribers():
    """List/search Starlink subscribers."""
    search = request.args.get("q", "").strip()

    query = StarlinkSubscriber.query
    if search:
        query = query.filter(
            or_(
                StarlinkSubscriber.full_name.ilike(f"%{search}%"),
                StarlinkSubscriber.phone_number.ilike(f"%{search}%"),
                StarlinkSubscriber.location.ilike(f"%{search}%"),
            )
        )

    subscribers = query.order_by(StarlinkSubscriber.date_registered.desc()).all()
    return render_template("starlink/subscribers_list.html", subscribers=subscribers, search=search)


@starlink_bp.route("/subscribers/register", methods=["GET", "POST"])
@login_required
def register_subscriber():
    """Register a new Starlink subscriber (separate from cafe customers)."""
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        location = request.form.get("location", "").strip() or None

        if not full_name or not phone_number:
            flash("Full name and phone number are both required.", "error")
            return redirect(url_for("starlink.register_subscriber"))

        existing = StarlinkSubscriber.query.filter_by(phone_number=phone_number).first()
        if existing:
            flash(
                f"A subscriber with this phone number already exists: {existing.full_name}.",
                "error",
            )
            return redirect(url_for("starlink.register_subscriber"))

        new_subscriber = StarlinkSubscriber(
            full_name=full_name, phone_number=phone_number, location=location
        )
        db.session.add(new_subscriber)
        db.session.commit()

        flash(f"{full_name} registered as a Starlink subscriber.", "success")
        return redirect(url_for("starlink.view_subscriber", subscriber_id=new_subscriber.subscriber_id))

    return render_template("starlink/subscriber_register.html")


@starlink_bp.route("/subscribers/<int:subscriber_id>")
@login_required
def view_subscriber(subscriber_id):
    """Subscriber profile with their subscription history and installation timeline."""
    _auto_expire_subscriptions()
    subscriber = StarlinkSubscriber.query.get_or_404(subscriber_id)
    subscriptions = (
        StarlinkSubscription.query.filter_by(subscriber_id=subscriber_id)
        .order_by(StarlinkSubscription.created_at.desc())
        .all()
    )
    timeline = (
        InstallationActivity.query.filter_by(subscriber_id=subscriber_id)
        .order_by(InstallationActivity.created_at.desc())
        .all()
    )
    fault_tickets = (
        FaultTicket.query.filter_by(subscriber_id=subscriber_id)
        .order_by(FaultTicket.created_at.desc())
        .all()
    )
    return render_template(
        "starlink/subscriber_view.html",
        subscriber=subscriber,
        subscriptions=subscriptions,
        timeline=timeline,
        fault_tickets=fault_tickets,
    )


# ============================================================
# PLANS
# ============================================================

@starlink_bp.route("/plans")
@login_required
def list_plans():
    """Show all Starlink plans (admin-configurable)."""
    plans = StarlinkPlan.query.order_by(StarlinkPlan.plan_type, StarlinkPlan.duration_days).all()
    
    # Calculate usage counts for each plan
    usage_counts = {}
    active_usage_counts = {}
    
    for plan in plans:
        # Total subscriptions for this plan
        total = StarlinkSubscription.query.filter_by(plan_id=plan.plan_id).count()
        usage_counts[plan.plan_id] = total
        
        # Active/pending subscriptions for this plan
        active = StarlinkSubscription.query.filter(
            StarlinkSubscription.plan_id == plan.plan_id,
            StarlinkSubscription.status.in_(["active", "pending_payment"])
        ).count()
        active_usage_counts[plan.plan_id] = active
    
    return render_template(
        "starlink/plans_list.html", 
        plans=plans,
        usage_counts=usage_counts,
        active_usage_counts=active_usage_counts
    )


@starlink_bp.route("/plans/add", methods=["GET", "POST"])
@login_required
def add_plan():
    """Add a new Starlink plan."""
    if request.method == "POST":
        plan_name = request.form.get("plan_name", "").strip()
        plan_type = request.form.get("plan_type")
        duration_days = request.form.get("duration_days", type=int)
        data_allocation_gb = request.form.get("data_allocation_gb", type=float)
        price = request.form.get("price", type=float)

        if not all([plan_name, plan_type, duration_days, data_allocation_gb, price]):
            flash("All fields are required.", "error")
            return redirect(url_for("starlink.add_plan"))

        new_plan = StarlinkPlan(
            plan_name=plan_name,
            plan_type=plan_type,
            duration_days=duration_days,
            data_allocation_gb=data_allocation_gb,
            price=price,
        )
        db.session.add(new_plan)
        db.session.commit()

        flash(f"Plan '{plan_name}' added.", "success")
        return redirect(url_for("starlink.list_plans"))

    return render_template("starlink/plan_add.html")


@starlink_bp.route("/plans/<int:plan_id>/toggle-active", methods=["POST"])
@login_required
def toggle_plan_active(plan_id):
    """Activate/deactivate a plan (deactivated plans won't show when starting a new subscription)."""
    plan = StarlinkPlan.query.get_or_404(plan_id)
    plan.is_active = not plan.is_active
    db.session.commit()
    state = "activated" if plan.is_active else "deactivated"
    flash(f"'{plan.plan_name}' has been {state}.", "success")
    return redirect(url_for("starlink.list_plans"))


# ============================================================
# SUBSCRIPTIONS
# ============================================================

@starlink_bp.route("/subscriptions")
@login_required
def list_subscriptions():
    """Show all subscriptions, optionally filtered by status."""
    _auto_expire_subscriptions()
    status_filter = request.args.get("status", "").strip()

    query = StarlinkSubscription.query
    if status_filter in ("pending_payment", "active", "expired", "cancelled"):
        query = query.filter_by(status=status_filter)

    subscriptions = query.order_by(StarlinkSubscription.created_at.desc()).all()
    return render_template(
        "starlink/subscriptions_list.html", subscriptions=subscriptions, status_filter=status_filter
    )


@starlink_bp.route("/subscriptions/new", methods=["GET", "POST"])
@login_required
def new_subscription():
    """
    Sign a subscriber up for a plan. Generates a voucher code and
    calculates start/end dates. Starts as 'pending_payment' until
    the admin records payment (which activates it).
    """
    if request.method == "POST":
        subscriber_id = request.form.get("subscriber_id")
        plan_id = request.form.get("plan_id")
        start_date_str = request.form.get("start_date", "").strip()

        if not (subscriber_id and plan_id):
            flash("Please select a subscriber and a plan.", "error")
            return redirect(url_for("starlink.new_subscription"))

        subscriber = StarlinkSubscriber.query.get(subscriber_id)
        plan = StarlinkPlan.query.get(plan_id)

        if not (subscriber and plan):
            flash("Invalid selection. Please try again.", "error")
            return redirect(url_for("starlink.new_subscription"))

        try:
            start_date = (
                datetime.strptime(start_date_str, "%Y-%m-%d").date()
                if start_date_str
                else date.today()
            )
        except ValueError:
            start_date = date.today()

        end_date = StarlinkSubscription.calculate_end_date(start_date, plan)

        new_sub = StarlinkSubscription(
            subscriber_id=subscriber.subscriber_id,
            plan_id=plan.plan_id,
            voucher_code=StarlinkSubscription.generate_voucher_code(),
            starts_at=start_date,
            ends_at=end_date,
            data_allocation_gb=plan.data_allocation_gb,
            status="pending_payment",
            created_by=current_user.user_id,
        )
        db.session.add(new_sub)
        db.session.flush()  # assigns subscription_id without ending the transaction
        new_sub.voucher_username = StarlinkSubscription.generate_voucher_username(new_sub.subscription_id)
        db.session.commit()

        flash(
            f"Subscription created for {subscriber.full_name}. "
            f"Voucher: {new_sub.voucher_code}. Record payment to activate it.",
            "success",
        )
        return redirect(url_for("starlink.view_subscription", subscription_id=new_sub.subscription_id))

    subscribers = StarlinkSubscriber.query.filter_by(is_active=True).order_by(
        StarlinkSubscriber.full_name
    ).all()
    plans = StarlinkPlan.query.filter_by(is_active=True).order_by(
        StarlinkPlan.plan_type, StarlinkPlan.duration_days
    ).all()

    preselected_subscriber = request.args.get("subscriber_id", type=int)

    return render_template(
        "starlink/subscription_new.html",
        subscribers=subscribers,
        plans=plans,
        preselected_subscriber=preselected_subscriber,
        today=date.today().isoformat(),
    )


@starlink_bp.route("/subscriptions/<int:subscription_id>")
@login_required
def view_subscription(subscription_id):
    """View one subscription's details and payment history."""
    _auto_expire_subscriptions()
    subscription = StarlinkSubscription.query.get_or_404(subscription_id)
    payments = (
        StarlinkPayment.query.filter_by(subscription_id=subscription_id)
        .order_by(StarlinkPayment.paid_at.desc())
        .all()
    )
    total_paid = sum(float(p.amount) for p in payments)
    return render_template(
        "starlink/subscription_view.html",
        subscription=subscription,
        payments=payments,
        total_paid=total_paid,
    )


@starlink_bp.route("/subscriptions/<int:subscription_id>/cancel", methods=["POST"])
@login_required
def cancel_subscription(subscription_id):
    """Cancel a subscription (e.g. customer requested cancellation)."""
    subscription = StarlinkSubscription.query.get_or_404(subscription_id)
    subscription.status = "cancelled"
    db.session.commit()
    flash(f"Subscription {subscription.voucher_code} has been cancelled.", "success")
    return redirect(url_for("starlink.list_subscriptions"))


@starlink_bp.route("/subscriptions/<int:subscription_id>/renew", methods=["GET", "POST"])
@login_required
def renew_subscription(subscription_id):
    """
    Renew an existing subscription - creates a NEW subscription record
    (new voucher, new dates) for the same subscriber, optionally on the
    same or a different plan. Keeps full history rather than overwriting.
    """
    old_subscription = StarlinkSubscription.query.get_or_404(subscription_id)

    if request.method == "POST":
        plan_id = request.form.get("plan_id")
        plan = StarlinkPlan.query.get(plan_id)

        if not plan:
            flash("Please select a valid plan.", "error")
            return redirect(url_for("starlink.renew_subscription", subscription_id=subscription_id))

        # New cycle starts today (or the day after the old one ends, if
        # the old one hasn't expired yet - whichever is later).
        start_date = max(date.today(), old_subscription.ends_at + timedelta(days=1))
        end_date = StarlinkSubscription.calculate_end_date(start_date, plan)

        new_sub = StarlinkSubscription(
            subscriber_id=old_subscription.subscriber_id,
            plan_id=plan.plan_id,
            voucher_code=StarlinkSubscription.generate_voucher_code(),
            starts_at=start_date,
            ends_at=end_date,
            data_allocation_gb=plan.data_allocation_gb,
            status="pending_payment",
            created_by=current_user.user_id,
        )
        db.session.add(new_sub)
        db.session.flush()
        new_sub.voucher_username = StarlinkSubscription.generate_voucher_username(new_sub.subscription_id)
        db.session.commit()

        flash(
            f"Renewed for {old_subscription.subscriber.full_name}. "
            f"New voucher: {new_sub.voucher_code}. Record payment to activate it.",
            "success",
        )
        return redirect(url_for("starlink.view_subscription", subscription_id=new_sub.subscription_id))

    plans = StarlinkPlan.query.filter_by(is_active=True).order_by(
        StarlinkPlan.plan_type, StarlinkPlan.duration_days
    ).all()
    return render_template(
        "starlink/subscription_renew.html", subscription=old_subscription, plans=plans
    )


# ============================================================
# PAYMENTS
# ============================================================

@starlink_bp.route("/subscriptions/<int:subscription_id>/pay", methods=["GET", "POST"])
@login_required
def record_subscription_payment(subscription_id):
    """
    Record payment for a subscription. On success, activates the
    subscription (moves it from pending_payment to active).
    """
    subscription = StarlinkSubscription.query.get_or_404(subscription_id)

    if request.method == "POST":
        amount = request.form.get("amount", type=float)
        payment_method = request.form.get("payment_method")
        receipt_number = request.form.get("receipt_number", "").strip() or None

        if not (amount and payment_method):
            flash("Amount and payment method are required.", "error")
            return redirect(url_for("starlink.record_subscription_payment", subscription_id=subscription_id))

        if amount <= 0:
            flash("Amount must be greater than zero.", "error")
            return redirect(url_for("starlink.record_subscription_payment", subscription_id=subscription_id))

        new_payment = StarlinkPayment(
            subscription_id=subscription.subscription_id,
            amount=amount,
            payment_method=payment_method,
            receipt_number=receipt_number or StarlinkPayment.generate_receipt_number(),
            recorded_by=current_user.user_id,
        )
        db.session.add(new_payment)

        # Activate the subscription once payment is recorded.
        if subscription.status == "pending_payment":
            subscription.status = "active"

        db.session.commit()

        flash(
            f"Payment of GHS {amount:.2f} recorded ({new_payment.receipt_number}). "
            f"Subscription is now active.",
            "success",
        )
        return redirect(url_for("starlink.view_subscription", subscription_id=subscription_id))

    return render_template(
        "starlink/subscription_pay.html",
        subscription=subscription,
        suggested_amount=float(subscription.plan.price),
    )


# ============================================================
# RENEWALS DASHBOARD
# ============================================================

@starlink_bp.route("/renewals")
@login_required
def renewals_dashboard():
    """Subscriptions expiring within the next N days, for follow-up."""
    _auto_expire_subscriptions()

    within_days = request.args.get("days", default=3, type=int)

    active_subs = StarlinkSubscription.query.filter_by(status="active").all()
    expiring = [s for s in active_subs if s.is_expiring_soon(within_days=within_days)]
    expiring.sort(key=lambda s: s.ends_at)

    already_expired = (
        StarlinkSubscription.query.filter_by(status="expired")
        .order_by(StarlinkSubscription.ends_at.desc())
        .limit(30)
        .all()
    )

    return render_template(
        "starlink/renewals.html",
        expiring=expiring,
        already_expired=already_expired,
        within_days=within_days,
    )


# ============================================================
# VOUCHER LOOKUP (what a subscriber themselves can use to self-check)
# ============================================================

@starlink_bp.route("/voucher-lookup", methods=["GET", "POST"])
def voucher_lookup():
    """
    Public-facing lookup (no login required) - a subscriber can check
    their own subscription status using their voucher username, voucher
    password/code, or phone number. Intended to be shown on a simple
    kiosk/shared page, separate from the admin login.
    """
    result = None
    searched = False

    if request.method == "POST":
        query_value = request.form.get("query", "").strip()
        searched = True

        if query_value:
            normalized = query_value.upper()
            subscription = (
                StarlinkSubscription.query.filter(
                    or_(
                        StarlinkSubscription.voucher_code == normalized,
                        StarlinkSubscription.voucher_username == normalized,
                    )
                )
                .order_by(StarlinkSubscription.created_at.desc())
                .first()
            )

            if not subscription:
                subscriber = StarlinkSubscriber.query.filter_by(phone_number=query_value).first()
                if subscriber:
                    subscription = (
                        StarlinkSubscription.query.filter_by(subscriber_id=subscriber.subscriber_id)
                        .order_by(StarlinkSubscription.created_at.desc())
                        .first()
                    )

            if subscription and subscription.is_expired():
                subscription.status = "expired"
                db.session.commit()

            result = subscription

    return render_template("starlink/voucher_lookup.html", result=result, searched=searched)


# NEW ROUTES FOR STARLINK PLAN MANAGEMENT
@starlink_bp.route("/plans/<int:plan_id>/edit", methods=["POST"])
@login_required
def edit_plan(plan_id):
    """
    Edit an existing Starlink plan.
    """
    plan = StarlinkPlan.query.get_or_404(plan_id)
    
    plan_name = request.form.get("plan_name", "").strip()
    plan_type = request.form.get("plan_type", "").strip()
    duration_days = request.form.get("duration_days", "").strip()
    data_allocation_gb = request.form.get("data_allocation_gb", "").strip()
    price = request.form.get("price", "").strip()

    if not all([plan_name, plan_type, duration_days, data_allocation_gb, price]):
        flash("All fields are required.", "danger")
        return redirect(url_for("starlink.list_plans"))

    try:
        duration_days = int(duration_days)
        data_allocation_gb = float(data_allocation_gb)
        price = float(price)
        
        if plan_type not in ["weekly", "monthly", "occasion"]:
            flash("Invalid plan type.", "danger")
            return redirect(url_for("starlink.list_plans"))
        
        if duration_days <= 0 or data_allocation_gb < 0 or price < 0:
            flash("Duration must be positive; data and price must be non-negative.", "danger")
            return redirect(url_for("starlink.list_plans"))

        plan.plan_name = plan_name
        plan.plan_type = plan_type
        plan.duration_days = duration_days
        plan.data_allocation_gb = data_allocation_gb
        plan.price = price
        db.session.commit()
        flash(f"Plan '{plan_name}' updated successfully!", "success")
    except (ValueError, TypeError):
        flash("Invalid input. Please check your values.", "danger")
    except Exception as e:
        flash(f"Error updating plan: {str(e)}", "danger")
        db.session.rollback()

    return redirect(url_for("starlink.list_plans"))


@starlink_bp.route("/plans/<int:plan_id>/delete", methods=["POST"])
@login_required
def delete_plan(plan_id):
    """
    Delete a Starlink plan. Note: existing subscriptions using this plan 
    will not be affected; they'll just continue with their original plan data.
    """
    plan = StarlinkPlan.query.get_or_404(plan_id)
    
    try:
        plan_name = plan.plan_name
        db.session.delete(plan)
        db.session.commit()
        flash(f"Plan '{plan_name}' deleted successfully! Existing subscriptions are not affected.", "success")
    except Exception as e:
        flash(f"Error deleting plan: {str(e)}", "danger")
        db.session.rollback()

    return redirect(url_for("starlink.list_plans"))
