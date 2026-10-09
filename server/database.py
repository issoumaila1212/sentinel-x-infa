import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "..", "data", "sensors.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    device      TEXT NOT NULL,
    temperature REAL,
    humidity    REAL,
    gas         INTEGER,
    presence    INTEGER,
    distance    REAL
);
CREATE INDEX IF NOT EXISTS idx_readings_device_ts ON readings(device, ts);

CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    device       TEXT,
    source       TEXT,
    level        TEXT,
    message      TEXT,
    score        REAL,
    acknowledged INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('user', 'admin', 'superadmin')),
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    username TEXT,
    ip       TEXT,
    action   TEXT NOT NULL,
    success  INTEGER NOT NULL DEFAULT 1,
    detail   TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ip_ts ON audit_log(ip, ts);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = connect()
    conn.executescript(SCHEMA)
    conn.close()


def insert_reading(r):
    # A node may have only some of the sensors: missing values are stored as NULL.
    presence = r.get("presence")
    gas = r.get("gas")
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO readings (device, temperature, humidity, gas, presence, distance) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (r["device"], r.get("temperature"), r.get("humidity"),
             None if gas is None else int(gas),
             None if presence is None else int(bool(presence)),
             r.get("distance")),
        )
    conn.close()


def insert_alert(device, source, level, message, score=None):
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO alerts (device, source, level, message, score) VALUES (?, ?, ?, ?, ?)",
            (device, source, level, message, score),
        )
    conn.close()
