"""Smoke tests covering the core flows. Run with: python -m pytest  (or python test_app.py)"""
import io
import os
import re
import tempfile

import app as app_module
import db


def make_client():
    tmp = tempfile.mkdtemp()
    app_module.app.config.update(TESTING=True, DATABASE=os.path.join(tmp, "t.sqlite3"), UPLOAD_FOLDER=tmp)
    with app_module.app.app_context():
        db.init_db()
        db.execute("INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, 'admin')",
                   ("Admin", "a@x.com", app_module.generate_password_hash("adminpass1")))
    return app_module.app.test_client()


def db_insert(location):
    with app_module.app.app_context():
        db.execute("INSERT INTO requests (user_id, category, location, description) VALUES (1, 'Roads', ?, 'Pothole')",
                   (location,))


def token(client, path):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)


def post(client, path, page, **data):
    return client.post(path, data={"_csrf": token(client, page), **data}, content_type="multipart/form-data",
                       follow_redirects=True)


def test_full_flow():
    c = make_client()
    assert b"Account created" in post(c, "/register", "/register", full_name="Wanjiru K", email="w@x.com",
                                      password="password1", confirm="password1").data
    assert b"already exists" in post(c, "/register", "/register", full_name="Dup", email="w@x.com",
                                     password="password1", confirm="password1").data
    post(c, "/login", "/login", email="w@x.com", password="password1")
    assert c.get("/admin").status_code == 403  # citizens cannot open the dashboard

    r = post(c, "/requests/new", "/requests/new", category="Water", location="Kahawa West",
             description="No water for three days", latitude="-1.2921", longitude="36.8219", image=(io.BytesIO(b"\x89PNG fake"), "leak.png"))
    assert b"Request #1 submitted" in r.data and b"leak.png" not in r.data
    assert b"map pin is not valid" in post(c, "/requests/new", "/requests/new", category="Water", location="x",
                                           description="valid description", latitude="abc", longitude="1").data
    assert b"Choose a category" in post(c, "/requests/new", "/requests/new", category="", location="x",
                                        description="too short").data
    assert c.post("/requests/new", data={}).status_code == 400  # CSRF enforced

    c.post("/logout", data={"_csrf": token(c, "/my-requests")})
    post(c, "/login", "/login", email="a@x.com", password="adminpass1")
    assert b"Open" in c.get("/admin").data
    post(c, "/admin/requests/1/status", "/requests/1", status="Resolved", note="Pipe repaired")
    page = c.get("/requests/1").get_data(as_text=True)
    assert "Pipe repaired" in page and "badge-resolved" in page and 'data-lat="-1.2921"' in page

    csv_text = c.get("/admin/export.csv?status=Resolved").get_data(as_text=True)
    assert "Kahawa West" in csv_text and c.get("/admin/export.csv?status=Pending").get_data(as_text=True).count("\n") == 1

    # pagination: 12 more requests -> 13 total -> 2 pages of 10
    for i in range(12):
        db_insert(f"Spot {i}")
    assert "Page 1 of 2" in c.get("/admin").get_data(as_text=True)
    assert "Page 2 of 2" in c.get("/admin?page=2").get_data(as_text=True)
    assert c.get("/admin?page=999").status_code == 200  # out-of-range page is clamped


if __name__ == "__main__":
    test_full_flow()
    print("All tests passed")
