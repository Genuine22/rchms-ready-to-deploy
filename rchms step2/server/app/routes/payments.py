"""
Payment routes - Module 8
Handles: recording payments (cash, mobile money, membership), linked to
a session or standalone (e.g. for printing/photocopying), and viewing
the day's payment list.
"""

from datetime import datetime, date
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.models.payment import Payment
from app.models.customer import Customer
from app.models.session import Session

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")


@payments_bp.route("/")
@login_required
def list_payments():
    """Show today's payments by default, with a simple date filter."""
    selected_date = request.args.get("date", "").strip()

    if selected_date:
        try:
            filter_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        except ValueError:
            filter_date = date.today()
    else:
        filter_date = date.today()

    payments = (
        Payment.query.filter(db.func.date(Payment.paid_at) == filter_date)
        .order_by(Payment.paid_at.desc())
        .all()
    )
    total = sum(float(p.amount) for p in payments)

    return render_template(
        "payments/list.html",
        payments=payments,
        total=total,
        filter_date=filter_date.isoformat(),
    )


@payments_bp.route("/record", methods=["GET", "POST"])
@login_required
def record_payment():
    """
    Record a standalone payment (e.g. for printing/photocopying) not
    tied to a timed session. For session payments, use record_for_session
    below, which pre-fills the customer and a suggested amount.
    """
    if request.method == "POST":
        customer_id = request.form.get("customer_id")
        amount = request.form.get("amount", type=float)
        payment_method = request.form.get("payment_method")
        receipt_number = request.form.get("receipt_number", "").strip() or None
        session_id = request.form.get("session_id") or None

        if not (customer_id and amount and payment_method):
            flash("Customer, amount, and payment method are required.", "error")
            return redirect(url_for("payments.record_payment"))

        if amount <= 0:
            flash("Amount must be greater than zero.", "error")
            return redirect(url_for("payments.record_payment"))

        new_payment = Payment(
            customer_id=customer_id,
            session_id=session_id,
            amount=amount,
            payment_method=payment_method,
            receipt_number=receipt_number or Payment.generate_receipt_number(),
            recorded_by=current_user.user_id,
        )
        db.session.add(new_payment)
        db.session.commit()

        flash(f"Payment of GHS {amount:.2f} recorded ({new_payment.receipt_number}).", "success")
        return redirect(url_for("payments.list_payments"))

    customers = Customer.query.filter_by(is_active=True).order_by(Customer.full_name).all()
    return render_template("payments/record.html", customers=customers, session=None)


@payments_bp.route("/record-for-session/<int:session_id>", methods=["GET", "POST"])
@login_required
def record_for_session(session_id):
    """
    Record a payment for a specific session, pre-filling the customer
    and suggesting the service's price as the amount.
    """
    session = Session.query.get_or_404(session_id)

    if request.method == "POST":
        amount = request.form.get("amount", type=float)
        payment_method = request.form.get("payment_method")
        receipt_number = request.form.get("receipt_number", "").strip() or None

        if not (amount and payment_method):
            flash("Amount and payment method are required.", "error")
            return redirect(url_for("payments.record_for_session", session_id=session_id))

        if amount <= 0:
            flash("Amount must be greater than zero.", "error")
            return redirect(url_for("payments.record_for_session", session_id=session_id))

        new_payment = Payment(
            customer_id=session.customer_id,
            session_id=session.session_id,
            amount=amount,
            payment_method=payment_method,
            receipt_number=receipt_number or Payment.generate_receipt_number(),
            recorded_by=current_user.user_id,
        )
        db.session.add(new_payment)
        db.session.commit()

        flash(f"Payment of GHS {amount:.2f} recorded ({new_payment.receipt_number}).", "success")
        return redirect(url_for("sessions.view_session", session_id=session_id))

    customers = [session.customer]
    return render_template(
        "payments/record.html",
        customers=customers,
        session=session,
        suggested_amount=float(session.service.price) if session.service else 0.0,
    )
