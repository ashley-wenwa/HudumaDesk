"""Huduma Desk - a small public service request system.

Citizens register, report local problems and follow their progress.
Admins triage requests and see simple analytics.
"""
import csv
import io
import logging
import os
import random
import secrets
import sqlite3
import uuid
from functools import wraps

import click
from markupsafe import Markup
from flask import (Flask, Response, abort, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import db
from notifications import send_status_update

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
CATEGORIES = ["Streetlight", "Water", "Garbage collection", "Roads", "Drainage", "Other"]
STATUSES = ["Pending", "In Progress", "Resolved"]
ALLOWED_IMAGE_TYPES = {"png", "jpg", "jpeg", "gif", "webp"}
PER_PAGE = 10

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
    DATABASE=os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "huduma.sqlite3")),
    UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads")),
    MAX_CONTENT_LENGTH=4 * 1024 * 1024,  # 4 MB upload cap
)
app.teardown_appcontext(db.close_db)


# --------------------------------------------------------------------------
# Request lifecycle: current user, CSRF protection, template globals
# --------------------------------------------------------------------------
@app.before_request
def load_user():
    user_id = session.get("user_id")
    g.user = db.query("SELECT * FROM users WHERE id = ?", (user_id,), one=True) if user_id else None


@app.before_request
def protect_from_csrf():
    if request.method == "POST":
        sent = request.form.get("_csrf", "")
        if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
            abort(400, "Invalid or missing form token. Reload the page and try again.")


@app.context_processor
def template_globals():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    field = Markup('<input type="hidden" name="_csrf" value="%s">') % session["_csrf"]
    return {"csrf_field": lambda: field, "CATEGORIES": CATEGORIES, "STATUSES": STATUSES}


@app.errorhandler(413)
def file_too_large(_e):
    flash("That image is larger than 4 MB. Choose a smaller file.", "error")
    return redirect(url_for("submit_request"))


# --------------------------------------------------------------------------
# Access control
# --------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# --------------------------------------------------------------------------
# Shared helpers: pagination, filters, map coordinates
# --------------------------------------------------------------------------
def paginate(select, source, args, order):
    """Return (rows, paging) for one page of `select source ORDER BY order`."""
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    total = db.query(f"SELECT COUNT(*) AS n {source}", args, one=True)["n"]
    pages = max(1, -(-total // PER_PAGE))
    page = min(page, pages)
    rows = db.query(f"{select} {source} ORDER BY {order} LIMIT ? OFFSET ?",
                    [*args, PER_PAGE, (page - 1) * PER_PAGE])
    return rows, {"page": page, "pages": pages, "total": total}


def request_filters():
    """Read the dashboard filters from the query string; return (WHERE clause, args, filters)."""
    filters = {
        "status": request.args.get("status", ""),
        "category": request.args.get("category", ""),
        "q": request.args.get("q", "").strip(),
    }
    clauses, args = [], []
    if filters["status"] in STATUSES:
        clauses.append("r.status = ?")
        args.append(filters["status"])
    if filters["category"] in CATEGORIES:
        clauses.append("r.category = ?")
        args.append(filters["category"])
    if filters["q"]:
        clauses.append("(r.location LIKE ? OR r.description LIKE ?)")
        args += [f"%{filters['q']}%"] * 2
    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), args, filters


def parse_coordinates(form):
    """Read the optional map pin. Returns (lat, lng) or (None, None); raises ValueError if invalid."""
    raw_lat, raw_lng = form.get("latitude", "").strip(), form.get("longitude", "").strip()
    if not raw_lat and not raw_lng:
        return None, None
    try:
        lat, lng = float(raw_lat), float(raw_lng)
    except ValueError:
        raise ValueError("The map pin is not valid. Click the map again.")
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("The map pin is outside the valid range. Click the map again.")
    return lat, lng


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------
@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard" if g.user["role"] == "admin" else "my_requests"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        errors = []
        if not name:
            errors.append("Enter your full name.")
        if "@" not in email:
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Use a password with at least 8 characters.")
        if password != request.form.get("confirm", ""):
            errors.append("The two passwords do not match.")
        if not errors:
            try:
                db.execute("INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                           (name, email, generate_password_hash(password)))
            except sqlite3.IntegrityError:
                errors.append("An account with that email already exists.")
            else:
                flash("Account created. You can log in now.", "success")
                return redirect(url_for("login"))
        for error in errors:
            flash(error, "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = db.query("SELECT * FROM users WHERE email = ?", (email,), one=True)
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("index"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# --------------------------------------------------------------------------
# Citizen features
# --------------------------------------------------------------------------
def save_image(file_storage):
    """Store an uploaded image under a random name; return it, or None if no file."""
    if not file_storage or not file_storage.filename:
        return None
    extension = secure_filename(file_storage.filename).rsplit(".", 1)[-1].lower()
    if extension not in ALLOWED_IMAGE_TYPES:
        raise ValueError("Upload a PNG, JPG, GIF or WEBP image.")
    filename = f"{uuid.uuid4().hex}.{extension}"
    file_storage.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    return filename


@app.route("/requests/new", methods=["GET", "POST"])
@login_required
def submit_request():
    if request.method == "POST":
        category = request.form.get("category", "")
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        errors = []
        if category not in CATEGORIES:
            errors.append("Choose a category.")
        if not location:
            errors.append("Say where the problem is.")
        if len(description) < 10:
            errors.append("Describe the problem in at least 10 characters.")
        image = None
        lat = lng = None
        try:
            lat, lng = parse_coordinates(request.form)
        except ValueError as exc:
            errors.append(str(exc))
        if not errors:
            try:
                image = save_image(request.files.get("image"))
            except ValueError as exc:
                errors.append(str(exc))
        if not errors:
            request_id = db.execute(
                "INSERT INTO requests (user_id, category, location, latitude, longitude,"
                " description, image_filename) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (g.user["id"], category, location, lat, lng, description, image))
            db.execute("INSERT INTO status_history (request_id, status, note) VALUES (?, 'Pending', ?)",
                       (request_id, "Request received"))
            flash(f"Request #{request_id} submitted. We will update its status here.", "success")
            return redirect(url_for("request_detail", request_id=request_id))
        for error in errors:
            flash(error, "error")
    return render_template("submit.html", form=request.form)


@app.route("/my-requests")
@login_required
def my_requests():
    rows, paging = paginate("SELECT r.*", "FROM requests r WHERE r.user_id = ?",
                            [g.user["id"]], "r.created_at DESC, r.id DESC")
    return render_template("my_requests.html", requests=rows, paging=paging)


@app.route("/requests/<int:request_id>")
@login_required
def request_detail(request_id):
    row = db.query(
        "SELECT r.*, u.full_name, u.email FROM requests r JOIN users u ON u.id = r.user_id WHERE r.id = ?",
        (request_id,), one=True)
    if row is None:
        abort(404)
    if g.user["role"] != "admin" and row["user_id"] != g.user["id"]:
        abort(403)
    history = db.query("SELECT * FROM status_history WHERE request_id = ? ORDER BY id", (request_id,))
    return render_template("request_detail.html", req=row, history=history)


@app.route("/uploads/<filename>")
@login_required
def uploaded_file(filename):
    owner = db.query("SELECT user_id FROM requests WHERE image_filename = ?", (filename,), one=True)
    if owner is None:
        abort(404)
    if g.user["role"] != "admin" and owner["user_id"] != g.user["id"]:
        abort(403)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# --------------------------------------------------------------------------
# Admin features
# --------------------------------------------------------------------------
@app.route("/admin")
@admin_required
def dashboard():
    where, args, filters = request_filters()
    rows, paging = paginate("SELECT r.*, u.full_name",
                            f"FROM requests r JOIN users u ON u.id = r.user_id {where}",
                            args, "r.created_at DESC, r.id DESC")

    by_status = {s: 0 for s in STATUSES}
    for row in db.query("SELECT status, COUNT(*) AS n FROM requests GROUP BY status"):
        by_status[row["status"]] = row["n"]
    total = sum(by_status.values())
    stats = {
        "total": total,
        "open": by_status["Pending"] + by_status["In Progress"],
        "resolved": by_status["Resolved"],
        "by_status": by_status,
        "resolution_rate": round(100 * by_status["Resolved"] / total) if total else 0,
        "by_category": db.query(
            "SELECT category, COUNT(*) AS n, SUM(status = 'Resolved') AS resolved"
            " FROM requests GROUP BY category ORDER BY n DESC"),
    }
    return render_template("dashboard.html", requests=rows, stats=stats,
                           filters=filters, paging=paging)


def csv_safe(value):
    """Stop spreadsheet apps from running user text as a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@app.route("/admin/export.csv")
@admin_required
def export_csv():
    """Download the requests matching the current dashboard filters."""
    where, args, _ = request_filters()
    rows = db.query(
        "SELECT r.id, r.created_at, r.category, r.location, r.latitude, r.longitude, r.description,"
        " r.status, r.updated_at, u.full_name, u.email"
        f" FROM requests r JOIN users u ON u.id = r.user_id {where} ORDER BY r.id", args)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "Submitted", "Category", "Location", "Latitude", "Longitude",
                     "Description", "Status", "Last updated", "Citizen", "Email"])
    for row in rows:
        writer.writerow([csv_safe(v) for v in tuple(row)])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=service-requests.csv"})


@app.post("/admin/requests/<int:request_id>/status")
@admin_required
def update_status(request_id):
    new_status = request.form.get("status", "")
    note = request.form.get("note", "").strip()
    if new_status not in STATUSES:
        abort(400, "Unknown status.")
    current = db.query(
        "SELECT r.status, r.category, u.full_name, u.email FROM requests r"
        " JOIN users u ON u.id = r.user_id WHERE r.id = ?", (request_id,), one=True)
    if current is None:
        abort(404)
    db.execute("UPDATE requests SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
               (new_status, request_id))
    db.execute("INSERT INTO status_history (request_id, status, note) VALUES (?, ?, ?)",
               (request_id, new_status, note or None))
    if new_status != current["status"] or note:
        send_status_update(current["email"], current["full_name"], request_id,
                           current["category"], new_status, note)
    flash(f"Request #{request_id} marked {new_status}.", "success")
    return redirect(url_for("request_detail", request_id=request_id))


# --------------------------------------------------------------------------
# CLI: flask --app app init-db | seed-demo
# --------------------------------------------------------------------------
@app.cli.command("init-db")
@click.option("--force", is_flag=True, help="Erase an existing database and start again.")
def init_db_command(force):
    """Create tables and an admin account. Refuses to overwrite an existing database."""
    if os.path.exists(app.config["DATABASE"]) and not force:
        raise click.ClickException("A database already exists. Re-run with --force to erase it.")
    db.init_db()
    email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
    password = os.environ.get("ADMIN_PASSWORD", "admin12345")
    db.execute("INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
               ("Administrator", email, generate_password_hash(password)))
    click.echo(f"Database ready. Admin login: {email} / {password}")


@app.cli.command("seed-demo")
def seed_demo_command():
    """Add a demo citizen and sample requests so the dashboard has data."""
    random.seed(7)
    citizen = db.execute("INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                         ("Amina Otieno", "citizen@example.com", generate_password_hash("citizen12345")))
    places = ["Kilimani Rd", "Kahawa West", "Githurai 45", "Lang'ata Rd", "Umoja 1", "Ruaka Town"]
    problems = {
        "Streetlight": "Streetlight has been off for a week and the road is unsafe at night.",
        "Water": "No water supply since Monday; neighbours report the same.",
        "Garbage collection": "Rubbish has not been collected for two weeks and is overflowing.",
        "Roads": "Large pothole near the junction is damaging vehicles.",
        "Drainage": "Blocked drain floods the street whenever it rains.",
    }
    for i in range(14):
        category = random.choice(list(problems))
        status = random.choices(STATUSES, weights=[4, 3, 5])[0]
        rid = db.execute(
            "INSERT INTO requests (user_id, category, location, latitude, longitude, description,"
            " status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', ?))",
            (citizen, category, random.choice(places), -1.2864 + random.uniform(-0.06, 0.06),
             36.8172 + random.uniform(-0.06, 0.06), problems[category], status, f"-{i} days"))
        db.execute("INSERT INTO status_history (request_id, status, note) VALUES (?, 'Pending', 'Request received')",
                   (rid,))
    click.echo("Demo data added. Citizen login: citizen@example.com / citizen12345")


if __name__ == "__main__":
    app.run(debug=True)
