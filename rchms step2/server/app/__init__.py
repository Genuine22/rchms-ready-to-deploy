"""
RCHMS - App Factory
This file creates and configures the Flask application.
It loads settings from the .env file, connects to MySQL,
and registers all the different parts (routes) of the system.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from dotenv import load_dotenv

# Load variables from the .env file (database password, secret key, etc.)
load_dotenv()

# These two objects are created here, but configured inside create_app().
# Other files (models, routes) import "db" and "login_manager" from here.
db = SQLAlchemy()
login_manager = LoginManager()

# This file lives in: server/app/__init__.py
# The templates and static folders live in: server/templates and server/static
# (one level up from this file, next to run.py) - so we must point Flask
# there explicitly instead of relying on its default (which looks inside
# the "app" package folder itself and would miss them).
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # -> server/
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
LOG_DIR = os.path.join(BASE_DIR, "logs")


def create_app():
    app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)

    # --- Error logging ---
    # With debug mode off (the normal day-to-day setting), errors no
    # longer show a full traceback in the browser. Instead they get
    # written here, to server/logs/error.log, so problems can still be
    # diagnosed later without exposing details to whoever is using the
    # browser at the time.
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "error.log"), maxBytes=1_000_000, backupCount=3
    )
    file_handler.setLevel(logging.ERROR)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s [in %(pathname)s:%(lineno)d]"
    ))
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.ERROR)

    # --- Basic configuration ---
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-change-me")

    db_user = os.getenv("DB_USER", "root")
    db_password = os.getenv("DB_PASSWORD", "")
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "3306")
    db_name = os.getenv("DB_NAME", "rchms_db")

    app.config["SQLALCHEMY_DATABASE_URI"] = (
        f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # --- Optional SSL for the DB connection ---
    # Local MySQL (on your own PC) doesn't need this. Managed free MySQL
    # hosts used with Render (e.g. Aiven) require an SSL connection.
    # Set DB_SSL_REQUIRED=true in the environment to turn it on, and
    # optionally DB_SSL_CA to the path of a downloaded CA certificate for
    # full verification (Aiven gives you one to download from its console).
    db_ssl_required = os.getenv("DB_SSL_REQUIRED", "false").strip().lower() == "true"
    if db_ssl_required:
        db_ssl_ca = os.getenv("DB_SSL_CA", "").strip()
        ssl_args = {"ca": db_ssl_ca} if db_ssl_ca else {}
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "connect_args": {"ssl": ssl_args}
        }

    # --- Connect extensions to this app ---
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"  # redirect here if not logged in
    login_manager.login_message = "Please log in to continue."

    # --- Make current_year available in every template (used by the footer) ---
    @app.context_processor
    def inject_current_year():
        from datetime import date
        return {"current_year": date.today().year}

    # --- Import models so SQLAlchemy knows about them ---
    from app.models.user import User
    from app.models.customer import Customer
    from app.models.computer import Computer
    from app.models.service import Service
    from app.models.session import Session
    from app.models.payment import Payment
    from app.models.print_job import PrintJob
    from app.models.starlink_subscriber import StarlinkSubscriber
    from app.models.starlink_plan import StarlinkPlan
    from app.models.starlink_subscription import StarlinkSubscription
    from app.models.starlink_payment import StarlinkPayment
    from app.models.site_survey import SiteSurvey
    from app.models.installation_job import InstallationJob
    from app.models.equipment_assignment import EquipmentAssignment
    from app.models.installation_report import InstallationReport
    from app.models.installation_activity import InstallationActivity
    from app.models.inventory_category import InventoryCategory
    from app.models.inventory_item import InventoryItem
    from app.models.inventory_transaction import InventoryTransaction
    from app.models.job_equipment_item import JobEquipmentLine
    from app.models.fault_ticket import FaultTicket
    from app.models.fault_ticket_activity import FaultTicketActivity
    from app.models.fault_ticket_attachment import FaultTicketAttachment
    from app.models.fault_ticket_equipment import FaultTicketEquipment


    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # --- Register routes (blueprints) ---
    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    from app.routes.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)

    from app.routes.customers import customers_bp
    app.register_blueprint(customers_bp)

    from app.routes.computers import computers_bp
    app.register_blueprint(computers_bp)

    from app.routes.sessions import sessions_bp
    app.register_blueprint(sessions_bp)

    from app.routes.payments import payments_bp
    app.register_blueprint(payments_bp)

    from app.routes.print_jobs import print_jobs_bp
    app.register_blueprint(print_jobs_bp)

    from app.routes.reports import reports_bp
    app.register_blueprint(reports_bp)

    from app.routes.starlink import starlink_bp
    app.register_blueprint(starlink_bp)

    from app.routes.installation import installation_bp
    app.register_blueprint(installation_bp)

    from app.routes.inventory import inventory_bp
    app.register_blueprint(inventory_bp)

    from app.routes.fault_tickets import fault_bp
    app.register_blueprint(fault_bp)



    from app.routes.notifications import notifications_bp
    app.register_blueprint(notifications_bp)

    from app.routes.services import services_bp
    app.register_blueprint(services_bp)

    # --- Friendly error pages ---
    # Without these, a crash shows a plain "Internal Server Error" page
    # with no styling and no guidance for the person using the system.
    from flask import render_template

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        # Make sure the real error gets written to logs/error.log even
        # though the person using the browser only sees a friendly page.
        app.logger.error(f"Server error: {error}", exc_info=True)
        return render_template("errors/500.html"), 500

    return app
