"""
Authentication routes - Module 1
Handles: secure login, logout, change password.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime

from app import db
from app.models.user import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # If already logged in, skip straight to the dashboard
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user is None or not user.check_password(password):
            flash("Incorrect username or password.", "error")
            return redirect(url_for("auth.login"))

        if not user.is_active:
            flash("This account has been disabled. Contact an administrator.", "error")
            return redirect(url_for("auth.login"))

        # Log the user in and record the login time
        login_user(user)
        user.last_login = datetime.utcnow()
        db.session.commit()

        first_name = user.full_name.split(' ')[0]
        flash(f"Welcome back, {first_name} 👋", "success")
        return redirect(url_for("dashboard.home"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_user.check_password(current_password):
            flash("Your current password is incorrect.", "error")
            return redirect(url_for("auth.change_password"))

        if len(new_password) < 6:
            flash("New password must be at least 6 characters long.", "error")
            return redirect(url_for("auth.change_password"))

        if new_password != confirm_password:
            flash("New password and confirmation do not match.", "error")
            return redirect(url_for("auth.change_password"))

        current_user.set_password(new_password)
        db.session.commit()
        flash("Password updated successfully.", "success")
        return redirect(url_for("dashboard.home"))

    return render_template("change_password.html")
