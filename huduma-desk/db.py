"""Thin SQLite helpers: one connection per request, plain SQL, no ORM."""
import sqlite3

from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, args=(), one=False):
    rows = get_db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    """Run a write statement, commit, and return the new row id."""
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    return cur.lastrowid


def init_db():
    with current_app.open_resource("schema.sql") as f:
        get_db().executescript(f.read().decode("utf-8"))
