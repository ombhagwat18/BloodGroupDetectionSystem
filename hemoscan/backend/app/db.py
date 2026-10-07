"""SQLite storage. Plain sqlite3 - no ORM needed for this size."""
import os
import sqlite3
import json
import time
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(os.environ.get("HEMOSCAN_DATA", Path(__file__).resolve().parent.parent / "data"))
DB_PATH = DATA_DIR / "hemoscan.db"
IMG_DIR = DATA_DIR / "scans"

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT NOT NULL,
    age INTEGER,
    sex TEXT,
    phone TEXT,
    blood_group TEXT,
    allergies TEXT DEFAULT '',
    conditions TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    sensor_slot INTEGER UNIQUE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER REFERENCES patients(id) ON DELETE SET NULL,
    device_id TEXT,
    predicted TEXT,
    confidence REAL,
    probs TEXT,
    quality REAL,
    quality_ok INTEGER DEFAULT 1,
    sensor_slot INTEGER,
    sensor_score INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    confirmed_group TEXT,
    mode TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    ip TEXT,
    fw TEXT,
    sensor_ok INTEGER DEFAULT 0,
    state TEXT DEFAULT 'idle',
    template_count INTEGER,
    last_seen REAL
);
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued',
    result TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scans_patient ON scans(patient_id);
CREATE INDEX IF NOT EXISTS idx_scans_created ON scans(created_at);
"""


def init():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        c.executescript(SCHEMA)


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def row(r):
    return dict(r) if r is not None else None


def scan_dict(r):
    d = dict(r)
    d["probs"] = json.loads(d["probs"]) if d.get("probs") else None
    d["quality_ok"] = bool(d.get("quality_ok"))
    d["image_url"] = "/api/scans/%d/image" % d["id"]
    return d


def now():
    return time.time()
