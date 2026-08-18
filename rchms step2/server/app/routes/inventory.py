"""
Inventory Management routes (Phase 2 of the Inventory module).

Replaces the old "Available Kits" placeholder card on the Starlink
Installation overview with a real warehouse inventory: stocked
items, categories, movement history, low-stock alerts, and reports -
plus the Equipment Assignment lines used by installation jobs (see
app/routes/installation.py for where those lines get created and
where automatic deduction/restoration on job completion/cancellation
happens).

Every quantity change goes through InventoryItem.apply_transaction()
so inventory_transactions always explains why quantity_in_stock is
what it is - see app/models/inventory_item.py.
"""

import csv
import io
from datetime import datetime, date, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request, Response
from flask_login import login_required, current_user
from sqlalchemy import func

from app import db
from app.models.inventory_category import InventoryCategory
from app.models.inventory_item import InventoryItem
from app.models.inventory_transaction import InventoryTransaction
from app.models.job_equipment_item import JobEquipmentLine
from app.models.fault_ticket_equipment import FaultTicketEquipment
from app.models.user import User
from app.reports.installation_pdf import table_report_pdf

inventory_bp = Blueprint("inventory", __name__, url_prefix="/inventory")


# ============================================================
# DASHBOARD
# ============================================================

@inventory_bp.route("/")
@login_required
def home():
    items = InventoryItem.query.all()

    total_items = len(items)
    by_status = {s: 0 for s in InventoryItem.STATUSES}
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1

    out_of_stock = [i for i in items if i.is_out_of_stock()]
    low_stock = [i for i in items if i.is_low_stock()]

    recent_activity = (
        InventoryTransaction.query.order_by(InventoryTransaction.created_at.desc()).limit(10).all()
    )

    return render_template(
        "inventory/home.html",
        total_items=total_items,
        by_status=by_status,
        out_of_stock=out_of_stock,
        low_stock=low_stock,
        recent_activity=recent_activity,
    )


# ============================================================
# ITEMS
# ============================================================

@inventory_bp.route("/items")
@login_required
def list_items():
    search = request.args.get("q", "").strip()
    category_id = request.args.get("category_id", type=int)
    status_filter = request.args.get("status", "").strip()
    stock_filter = request.args.get("stock", "").strip()  # 'low' or 'out'

    query = InventoryItem.query
    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                InventoryItem.item_name.ilike(like),
                InventoryItem.brand.ilike(like),
                InventoryItem.model.ilike(like),
                InventoryItem.serial_number.ilike(like),
                InventoryItem.asset_tag.ilike(like),
            )
        )
    if category_id:
        query = query.filter_by(category_id=category_id)
    if status_filter in InventoryItem.STATUSES:
        query = query.filter_by(status=status_filter)

    items = query.order_by(InventoryItem.item_name).all()
    if stock_filter == "low":
        items = [i for i in items if i.is_low_stock()]
    elif stock_filter == "out":
        items = [i for i in items if i.is_out_of_stock()]

    categories = InventoryCategory.query.order_by(InventoryCategory.name).all()
    return render_template(
        "inventory/list.html",
        items=items,
        categories=categories,
        search=search,
        category_id=category_id,
        status_filter=status_filter,
        stock_filter=stock_filter,
        statuses=InventoryItem.STATUSES,
    )


@inventory_bp.route("/items/new", methods=["GET", "POST"])
@login_required
def new_item():
    categories = InventoryCategory.query.filter_by(is_active=True).order_by(InventoryCategory.name).all()

    if request.method == "POST":
        category_id = request.form.get("category_id", type=int)
        item_name = request.form.get("item_name", "").strip()
        if not category_id or not item_name:
            flash("Category and item name are required.", "error")
            return redirect(url_for("inventory.new_item"))

        opening_qty = request.form.get("quantity_in_stock", type=float) or 0.0

        new_record = InventoryItem(
            category_id=category_id,
            item_name=item_name,
            brand=request.form.get("brand", "").strip() or None,
            model=request.form.get("model", "").strip() or None,
            serial_number=request.form.get("serial_number", "").strip() or None,
            asset_tag=request.form.get("asset_tag", "").strip() or None,
            qr_code=request.form.get("qr_code", "").strip() or None,
            unit=request.form.get("unit", "").strip() or "pcs",
            quantity_in_stock=0,  # set via the opening stock_in transaction below
            minimum_stock_level=request.form.get("minimum_stock_level", type=float) or 0,
            unit_cost=request.form.get("unit_cost", type=float),
            supplier=request.form.get("supplier", "").strip() or None,
            purchase_date=_parse_date(request.form.get("purchase_date")),
            warranty_expiry=_parse_date(request.form.get("warranty_expiry")),
            warehouse_location=request.form.get("warehouse_location", "").strip() or None,
            status=request.form.get("status") or "available",
            notes=request.form.get("notes", "").strip() or None,
        )
        db.session.add(new_record)
        db.session.flush()  # assigns item_id before we log the opening stock transaction

        if opening_qty > 0:
            new_record.apply_transaction(
                "stock_in", opening_qty, performed_by=current_user.user_id,
                notes="Opening stock on item creation.",
            )

        db.session.commit()
        flash(f"{new_record.item_name} added to inventory.", "success")
        return redirect(url_for("inventory.view_item", item_id=new_record.item_id))

    return render_template(
        "inventory/form.html", item=None, categories=categories, statuses=InventoryItem.STATUSES,
    )


@inventory_bp.route("/items/<int:item_id>")
@login_required
def view_item(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    transactions = (
        InventoryTransaction.query.filter_by(item_id=item_id)
        .order_by(InventoryTransaction.created_at.desc())
        .all()
    )
    return render_template("inventory/view.html", item=item, transactions=transactions)


@inventory_bp.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    categories = InventoryCategory.query.filter_by(is_active=True).order_by(InventoryCategory.name).all()

    if request.method == "POST":
        item.category_id = request.form.get("category_id", type=int) or item.category_id
        item.item_name = request.form.get("item_name", "").strip() or item.item_name
        item.brand = request.form.get("brand", "").strip() or None
        item.model = request.form.get("model", "").strip() or None
        item.serial_number = request.form.get("serial_number", "").strip() or None
        item.asset_tag = request.form.get("asset_tag", "").strip() or None
        item.qr_code = request.form.get("qr_code", "").strip() or None
        item.unit = request.form.get("unit", "").strip() or "pcs"
        item.minimum_stock_level = request.form.get("minimum_stock_level", type=float) or 0
        item.unit_cost = request.form.get("unit_cost", type=float)
        item.supplier = request.form.get("supplier", "").strip() or None
        item.purchase_date = _parse_date(request.form.get("purchase_date"))
        item.warranty_expiry = _parse_date(request.form.get("warranty_expiry"))
        item.warehouse_location = request.form.get("warehouse_location", "").strip() or None
        item.status = request.form.get("status") or item.status
        item.notes = request.form.get("notes", "").strip() or None
        db.session.commit()
        flash(f"{item.item_name} updated.", "success")
        return redirect(url_for("inventory.view_item", item_id=item.item_id))

    return render_template(
        "inventory/form.html", item=item, categories=categories, statuses=InventoryItem.STATUSES,
    )


@inventory_bp.route("/items/<int:item_id>/transaction", methods=["POST"])
@login_required
def item_transaction(item_id):
    """
    Generic stock-movement endpoint used by the action buttons on an
    item's detail page: Stock In, Mark Damaged, Mark Lost, Returned
    to Warehouse, or a manual Adjustment. This (and job completion/
    cancellation in installation.py) are the ONLY places
    quantity_in_stock ever changes.
    """
    item = InventoryItem.query.get_or_404(item_id)
    transaction_type = request.form.get("transaction_type")
    quantity = request.form.get("quantity", type=float)
    notes = request.form.get("notes", "").strip() or None

    if transaction_type not in InventoryTransaction.TYPES or transaction_type in ("deducted", "restored"):
        flash("Invalid stock action.", "error")
        return redirect(url_for("inventory.view_item", item_id=item_id))
    if quantity is None or quantity < 0:
        flash("Enter a valid quantity.", "error")
        return redirect(url_for("inventory.view_item", item_id=item_id))
    if transaction_type == "adjustment" and not notes:
        flash("An adjustment requires a note explaining the correction.", "error")
        return redirect(url_for("inventory.view_item", item_id=item_id))

    item.apply_transaction(
        transaction_type, quantity, performed_by=current_user.user_id, notes=notes,
    )
    db.session.commit()
    flash(f"Stock updated for {item.item_name}.", "success")
    return redirect(url_for("inventory.view_item", item_id=item_id))


# ============================================================
# CATEGORIES
# ============================================================

@inventory_bp.route("/categories", methods=["GET", "POST"])
@login_required
def list_categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Category name is required.", "error")
        elif InventoryCategory.query.filter_by(name=name).first():
            flash(f'"{name}" already exists.', "error")
        else:
            db.session.add(InventoryCategory(name=name))
            db.session.commit()
            flash(f'Category "{name}" added.', "success")
        return redirect(url_for("inventory.list_categories"))

    categories = InventoryCategory.query.order_by(InventoryCategory.name).all()
    item_counts = dict(
        db.session.query(InventoryItem.category_id, func.count(InventoryItem.item_id))
        .group_by(InventoryItem.category_id)
        .all()
    )
    return render_template("inventory/categories.html", categories=categories, item_counts=item_counts)


@inventory_bp.route("/categories/<int:category_id>/toggle", methods=["POST"])
@login_required
def toggle_category(category_id):
    category = InventoryCategory.query.get_or_404(category_id)
    category.is_active = not category.is_active
    db.session.commit()
    flash(f'"{category.name}" {"enabled" if category.is_active else "disabled"}.', "success")
    return redirect(url_for("inventory.list_categories"))


# ============================================================
# REPORTS
# ============================================================

REPORTS = {
    "stock": "Current Stock",
    "valuation": "Inventory Valuation",
    "issued": "Items Issued",
    "returned": "Items Returned",
    "damaged": "Damaged Equipment",
    "monthly-usage": "Monthly Usage",
    "most-used": "Most Used Equipment",
    "least-used": "Least Used Equipment",
    "movement": "Inventory Movement History",
}


def _report_rows(report_key):
    """Returns (columns, rows, summary) for one report key. Shared by the HTML, PDF and CSV views."""
    items = InventoryItem.query.order_by(InventoryItem.item_name).all()

    if report_key == "stock":
        columns = ["Item", "Category", "In Stock", "Available", "Min Level", "Status"]
        rows = [
            (i.item_name, i.category.name, f"{float(i.quantity_in_stock):g} {i.unit}",
             f"{i.available_quantity():g} {i.unit}", f"{float(i.minimum_stock_level):g}",
             i.status.title())
            for i in items
        ]
        summary = [f"Total items: {len(items)}"]

    elif report_key == "valuation":
        columns = ["Item", "Category", "In Stock", "Unit Cost", "Total Value"]
        rows, total_value = [], 0.0
        for i in items:
            cost = float(i.unit_cost or 0)
            value = float(i.quantity_in_stock) * cost
            total_value += value
            rows.append((i.item_name, i.category.name, f"{float(i.quantity_in_stock):g} {i.unit}",
                         f"{cost:,.2f}", f"{value:,.2f}"))
        summary = [f"Total inventory value: {total_value:,.2f}"]

    elif report_key in ("issued", "returned", "damaged"):
        type_map = {"issued": "deducted", "returned": "returned", "damaged": "damaged"}
        txns = (
            InventoryTransaction.query.filter_by(transaction_type=type_map[report_key])
            .order_by(InventoryTransaction.created_at.desc()).all()
        )
        columns = ["Date", "Item", "Quantity", "Job/Ticket", "By", "Notes"]
        rows = [
            (t.created_at.strftime("%d %b %Y"), t.item.item_name, f"{float(t.quantity):g} {t.item.unit}",
             (f"Job #{t.installation_id}" if t.installation_id else f"Ticket #{t.ticket_id}" if t.ticket_id else "-"),
             t.performer.full_name if t.performer else "-", t.notes or "-")
            for t in txns
        ]
        summary = [f"Total transactions: {len(txns)}"]

    elif report_key == "monthly-usage":
        today = date.today()
        start = today.replace(day=1)
        txns = (
            InventoryTransaction.query.filter(
                InventoryTransaction.transaction_type == "deducted",
                InventoryTransaction.created_at >= start,
            ).all()
        )
        usage = {}
        for t in txns:
            usage[t.item.item_name] = usage.get(t.item.item_name, 0) + float(t.quantity)
        columns = ["Item", "Quantity Used This Month"]
        rows = sorted(usage.items(), key=lambda r: -r[1])
        summary = [f"Month: {start.strftime('%B %Y')}", f"Items with usage: {len(rows)}"]

    elif report_key in ("most-used", "least-used"):
        txns = InventoryTransaction.query.filter_by(transaction_type="deducted").all()
        usage = {}
        for t in txns:
            usage[t.item.item_name] = usage.get(t.item.item_name, 0) + float(t.quantity)
        ordered = sorted(usage.items(), key=lambda r: r[1], reverse=(report_key == "most-used"))
        columns = ["Item", "Total Quantity Used (All Time)"]
        rows = ordered[:15]
        summary = [f"Showing top {len(rows)} of {len(usage)} items with recorded usage."]

    elif report_key == "movement":
        txns = InventoryTransaction.query.order_by(InventoryTransaction.created_at.desc()).limit(300).all()
        columns = ["Date", "Item", "Type", "Quantity", "Job/Ticket", "By"]
        rows = [
            (t.created_at.strftime("%d %b %Y %H:%M"), t.item.item_name, t.transaction_type.replace("_", " ").title(),
             f"{float(t.quantity):g} {t.item.unit}",
             (f"Job #{t.installation_id}" if t.installation_id else f"Ticket #{t.ticket_id}" if t.ticket_id else "-"),
             t.performer.full_name if t.performer else "-")
            for t in txns
        ]
        summary = [f"Showing latest {len(rows)} movements."]

    else:
        columns, rows, summary = [], [], []

    return columns, rows, summary


@inventory_bp.route("/reports")
@login_required
def reports_home():
    return render_template("inventory/reports_home.html", reports=REPORTS)


@inventory_bp.route("/reports/<report_key>")
@login_required
def report_view(report_key):
    if report_key not in REPORTS:
        flash("Unknown report.", "error")
        return redirect(url_for("inventory.reports_home"))
    columns, rows, summary = _report_rows(report_key)
    return render_template(
        "inventory/report_table.html",
        page_title=REPORTS[report_key], report_key=report_key,
        columns=columns, rows=rows, summary=summary,
    )


@inventory_bp.route("/reports/<report_key>/pdf")
@login_required
def report_pdf(report_key):
    if report_key not in REPORTS:
        flash("Unknown report.", "error")
        return redirect(url_for("inventory.reports_home"))
    columns, rows, summary = _report_rows(report_key)
    pdf_bytes = table_report_pdf(REPORTS[report_key], datetime.now().strftime("%d %b %Y"), columns, rows, summary)
    return Response(
        pdf_bytes, mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=inventory-{report_key}.pdf"},
    )


@inventory_bp.route("/reports/<report_key>/csv")
@login_required
def report_csv(report_key):
    if report_key not in REPORTS:
        flash("Unknown report.", "error")
        return redirect(url_for("inventory.reports_home"))
    columns, rows, summary = _report_rows(report_key)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows(rows)
    return Response(
        buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=inventory-{report_key}.csv"},
    )


@inventory_bp.route("/reports/<report_key>/excel")
@login_required
def report_excel(report_key):
    """
    Exports as an HTML table saved with an .xls extension - Excel
    opens this natively without needing an extra library added to
    requirements.txt. Good enough for "open in Excel and filter/sort";
    for anything beyond that, the CSV export is the more portable option.
    """
    if report_key not in REPORTS:
        flash("Unknown report.", "error")
        return redirect(url_for("inventory.reports_home"))
    columns, rows, summary = _report_rows(report_key)
    html = ["<table border='1'><tr>"] + [f"<th>{c}</th>" for c in columns] + ["</tr>"]
    for row in rows:
        html.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    html.append("</table>")
    return Response(
        "".join(html), mimetype="application/vnd.ms-excel",
        headers={"Content-Disposition": f"attachment; filename=inventory-{report_key}.xls"},
    )


# ============================================================
# HELPERS
# ============================================================

def _parse_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None
