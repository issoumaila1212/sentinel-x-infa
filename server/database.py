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
    conn = connect()
    with conn:
        conn.execute(
            "INSERT INTO readings (device, temperature, humidity, gas, presence, distance) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (r["device"], r["temperature"], r["humidity"], r["gas"],
             int(bool(r["presence"])), r.get("distance")),
        )
    conn.close()