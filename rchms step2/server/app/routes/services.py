"""
Services page - a public-facing overview of everything the hub offers.
Accessible to any logged-in user from the topbar Services button.
"""

from flask import Blueprint, render_template
from flask_login import login_required

services_bp = Blueprint("services", __name__, url_prefix="/services")


@services_bp.route("/")
@login_required
def services_page():
    return render_template("services.html")
