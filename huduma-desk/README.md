# Huduma Desk: Public Service Request System

A small eCitizen-style web app. Citizens report local problems (broken streetlights, water
issues, uncollected garbage) and follow each request until it is resolved. Administrators triage
requests and see simple analytics.

Built with **Python, Flask and SQLite**. The only dependency is Flask.

## Features

| Requirement | Where it lives |
|---|---|
| Citizen registration and login | `/register`, `/login` (passwords hashed, sessions, role-based access) |
| Submit a request (category, location, description, optional image) | `/requests/new` |
| Admin dashboard | `/admin` (all requests, filter by status and category, search) |
| Status tracking: Pending, In Progress, Resolved | Admin updates status on the request page; citizens see it on `/my-requests` |
| Basic analytics: open vs resolved | Summary cards and bar charts on `/admin` |

**Bonus features**

- Email notification to the citizen whenever an admin changes the status or adds a note (see Email below)
- Optional map pin: citizens click a map (or use their current location) and admins see the pin on the request
- CSV export of the requests matching the current dashboard filters
- Pagination (10 per page) on the dashboard and on My requests
- Status history timeline on every request, with an optional admin note shown to the citizen
- Search and filters on the admin dashboard
- Resolution rate and per-category breakdown (resolved / total)
- CSRF protection on every form, and uploaded images are only visible to their owner and admins
- Image uploads are type-checked, size-capped (4 MB) and stored under random filenames
- `seed-demo` command that fills the app with sample data
- Automated smoke test covering the full citizen-to-admin flow, including pagination, CSV export and map pins

## Setup

Requires Python 3.9 or newer.

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

flask --app app init-db           # creates the database and an admin account
flask --app app seed-demo         # optional: sample requests and a demo citizen
flask --app app run
```

Open http://127.0.0.1:5000.

| Role | Email | Password |
|---|---|---|
| Admin | `admin@example.com` | `admin12345` |
| Citizen (after `seed-demo`) | `citizen@example.com` | `citizen12345` |

Set `ADMIN_EMAIL` and `ADMIN_PASSWORD` before `init-db` to choose your own admin credentials.
`init-db` refuses to run if a database already exists. Add `--force` to erase it and start again.
The schema includes map coordinates, so if you ran an earlier version, run `init-db --force` again.
In production, set a strong `SECRET_KEY` environment variable and run behind a proper WSGI server.

## Email notifications

By default the email text is written to the console log and nothing is sent, so the app works with no setup.
To send real email, set these environment variables before starting the app:

| Variable | Purpose |
|---|---|
| `MAIL_SERVER`, `MAIL_PORT` | SMTP host and port (default port 587, with STARTTLS) |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | SMTP login, if your server needs one |
| `MAIL_FROM` | Sender address |

A failed send is logged and never blocks the admin's status update.

## Map

The map uses Leaflet and OpenStreetMap tiles, loaded from the internet. If they cannot load, the map hides
itself and the form still works, since the pin is optional.

## Deployment settings

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Required in production. Signs login sessions. |
| `DATABASE_PATH` | Where the SQLite file lives (default: next to `app.py`) |
| `UPLOAD_FOLDER` | Where uploaded images are stored (default: `uploads/`) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Used by `init-db` when it creates the admin account |

Both the database and the upload folder must be on storage that survives restarts.
Start command for hosts that need one: `gunicorn app:app`.

## Running the tests

```bash
python test_app.py
```

## Project structure

```
app.py            Routes, access control, CSRF, CLI commands
db.py             SQLite connection and query helpers
notifications.py  Status-change emails (SMTP or console log)
schema.sql        Tables: users, requests, status_history
templates/        Jinja2 pages (base layout + one template per screen)
static/style.css  All styling, no framework
static/map.js     Leaflet map: pick a pin / show a pin
uploads/          Uploaded images (not committed)
test_app.py       End-to-end smoke test
```

## Design decisions

- **Plain SQL with `sqlite3`** keeps the data layer easy to read and needs no setup. Every query is parameterised.
- **Two roles** (`citizen`, `admin`) are enforced by the `login_required` and `admin_required` decorators, and a citizen can only open their own requests.
- **A separate `status_history` table** records every change, so citizens can see progress and admins keep an audit trail.
- **Statuses can be set to any value** by an admin, so a mistaken click is easy to correct.
- **Almost no JavaScript.** Charts are CSS bars; the only script is the optional map pin.
- **CSV export escapes formulas**, so a request starting with `=` cannot run as a spreadsheet formula.

## Known limitations and next steps

- Image validation checks the file extension only; a production version should also inspect file contents.
- No password reset yet.
- Email is sent inside the request, so a slow SMTP server delays the page. A task queue would fix that.
- Moving to PostgreSQL and a hosted file store would be the next step for real deployment.
