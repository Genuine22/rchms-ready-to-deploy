"""
Customer routes - Module 2
Handles: registering customers, listing/searching them, viewing a single
customer's profile (with usage history), and editing/deactivating records.
"""

from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import or_

from app import db
from app.models.customer import Customer
from app.models.session import Session
from app.models.payment import Payment

customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


@customers_bp.route("/")
@login_required
def list_customers():
    """Show all customers, with optional search by name, phone, or membership code.
    Also supports ?registered=today to show only customers added today
    (used by the dashboard's "New Customers Today" card)."""
    search = request.args.get("q", "").strip()
    registered_filter = request.args.get("registered", "").strip().lower()

    query = Customer.query
    if search:
        query = query.filter(
            or_(
                Customer.full_name.ilike(f"%{search}%"),
                Customer.phone_number.ilike(f"%{search}%"),
                Customer.membership_code.ilike(f"%{search}%"),
            )
        )
    if registered_filter == "today":
        query = query.filter(db.func.date(Customer.date_registered) == date.today())

    customers = query.order_by(Customer.date_registered.desc()).all()
    return render_template(
        "customers/list.html",
        customers=customers,
        search=search,
        registered_filter=registered_filter,
    )


@customers_bp.route("/register", methods=["GET", "POST"])
@login_required
def register():
    """Register a new customer and auto-assign a membership ID."""
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone_number = request.form.get("phone_number", "").strip()

        # --- Basic validation ---
        if not full_name or not phone_number:
            flash("Full name and phone number are both required.", "error")
            return redirect(url_for("customers.register"))

        if len(phone_number) < 9:
            flash("Please enter a valid phone number.", "error")
            return redirect(url_for("customers.register"))

        # Avoid duplicate registrations of the same phone number
        existing = Customer.query.filter_by(phone_number=phone_number).first()
        if existing:
            flash(
                f"A customer with this phone number already exists: "
                f"{existing.full_name} ({existing.membership_code}).",
                "error",
            )
            return redirect(url_for("customers.register"))

        new_customer = Customer(
            full_name=full_name,
            phone_number=phone_number,
            membership_code=Customer.generate_membership_code(),
        )
        db.session.add(new_customer)
        db.session.commit()

        flash(
            f"Customer registered successfully. Membership ID: {new_customer.membership_code}",
            "success",
        )
        return redirect(url_for("customers.list_customers"))

    return render_template("customers/register.html")


@customers_bp.route("/<int:customer_id>")
@login_required
def view_customer(customer_id):
    """Show one customer's profile and their session/payment history."""
    customer = Customer.query.get_or_404(customer_id)

    sessions = (
        Session.query.filter_by(customer_id=customer_id)
        .order_by(Session.started_at.desc())
        .limit(50)
        .all()
    )
    payments = (
        Payment.query.filter_by(customer_id=customer_id)
        .order_by(Payment.paid_at.desc())
        .limit(50)
        .all()
    )

    return render_template(
        "customers/view.html", customer=customer, sessions=sessions, payments=payments
    )


@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_customer(customer_id):
    """Edit a customer's name or phone number."""
    customer = Customer.query.get_or_404(customer_id)

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone_number = request.form.get("phone_number", "").strip()

        if not full_name or not phone_number:
            flash("Full name and phone number are both required.", "error")
            return redirect(url_for("customers.edit_customer", customer_id=customer_id))

        customer.full_name = full_name
        customer.phone_number = phone_number
        db.session.commit()

        flash("Customer details updated.", "success")
        return redirect(url_for("customers.view_customer", customer_id=customer_id))

    return render_template("customers/edit.html", customer=customer)


@customers_bp.route("/<int:customer_id>/toggle-active", methods=["POST"])
@login_required
def toggle_active(customer_id):
    """Activate or deactivate a customer record (soft-delete, keeps history)."""
    customer = Customer.query.get_or_404(customer_id)
    customer.is_active = not customer.is_active
    db.session.commit()

    state = "activated" if customer.is_active else "deactivated"
    flash(f"{customer.full_name} has been {state}.", "success")
    return redirect(url_for("customers.list_customers"))
