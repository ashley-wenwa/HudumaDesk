DROP TABLE IF EXISTS status_history;
DROP TABLE IF EXISTS requests;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'citizen' CHECK (role IN ('citizen', 'admin')),
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE requests (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id),
    category       TEXT NOT NULL,
    location       TEXT NOT NULL,
    latitude       REAL,
    longitude      REAL,
    description    TEXT NOT NULL,
    image_filename TEXT,
    status         TEXT NOT NULL DEFAULT 'Pending'
                   CHECK (status IN ('Pending', 'In Progress', 'Resolved')),
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE status_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    status     TEXT NOT NULL,
    note       TEXT,
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_requests_user   ON requests(user_id);
CREATE INDEX idx_requests_status ON requests(status);
