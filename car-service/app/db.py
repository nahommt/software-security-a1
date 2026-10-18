import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS cars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    year INTEGER NOT NULL,
    mileage INTEGER NOT NULL,
    description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    car_id INTEGER NOT NULL REFERENCES cars(id),
    content_type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS valuations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER NOT NULL REFERENCES cars(id),
    dealer TEXT NOT NULL,
    price INTEGER NOT NULL,
    comment TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    car_id INTEGER NOT NULL REFERENCES cars(id),
    job_id TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CarStore:
    def __init__(self, db_path):
        self._db_path = db_path

    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self):
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def reset(self):
        with self._connect() as conn:
            conn.executescript(
                "DELETE FROM reports; DELETE FROM valuations; DELETE FROM images; DELETE FROM cars;"
                "DELETE FROM sqlite_sequence;"
            )

    def _car_dict(self, conn, row):
        car = dict(row)
        car["images"] = [
            r["id"]
            for r in conn.execute("SELECT id FROM images WHERE car_id = ? ORDER BY rowid", (row["id"],))
        ]
        return car

    def create_car(self, owner, make, model, year, mileage, description):
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO cars (owner, make, model, year, mileage, description) VALUES (?, ?, ?, ?, ?, ?)",
                (owner, make, model, year, mileage, description),
            )
            row = conn.execute("SELECT * FROM cars WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return self._car_dict(conn, row)

    def get_car(self, car_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cars WHERE id = ?", (car_id,)).fetchone()
            return None if row is None else self._car_dict(conn, row)

    def list_cars(self, owner=None, make=None):
        query = "SELECT * FROM cars WHERE 1 = 1"
        params = []
        if owner is not None:
            query += " AND owner = ?"
            params.append(owner)
        if make is not None:
            query += f" AND make = '{make}'"
        query += " ORDER BY id"
        with self._connect() as conn:
            return [self._car_dict(conn, row) for row in conn.execute(query, params)]

    def add_image(self, image_id, car_id, content_type):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO images (id, car_id, content_type) VALUES (?, ?, ?)",
                (image_id, car_id, content_type),
            )

    def get_image(self, car_id, image_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, content_type FROM images WHERE id = ? AND car_id = ?", (image_id, car_id)
            ).fetchone()
            return None if row is None else dict(row)

    def create_valuation(self, car_id, dealer, price, comment, timestamp=None):
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO valuations (car_id, dealer, price, comment, timestamp) VALUES (?, ?, ?, ?, ?)",
                (car_id, dealer, price, comment, timestamp or _now()),
            )
            return dict(conn.execute("SELECT * FROM valuations WHERE id = ?", (cursor.lastrowid,)).fetchone())

    def list_valuations(self, car_id):
        with self._connect() as conn:
            return [
                dict(row)
                for row in conn.execute("SELECT * FROM valuations WHERE car_id = ? ORDER BY id", (car_id,))
            ]

    def create_report(self, car_id, job_id, content):
        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO reports (car_id, job_id, content, created_at) VALUES (?, ?, ?, ?)",
                    (car_id, job_id, content, _now()),
                )
            except sqlite3.IntegrityError:
                return None
            return dict(conn.execute("SELECT * FROM reports WHERE id = ?", (cursor.lastrowid,)).fetchone())

    def list_reports(self, car_id):
        with self._connect() as conn:
            return [
                dict(row)
                for row in conn.execute("SELECT * FROM reports WHERE car_id = ? ORDER BY id", (car_id,))
            ]

    def get_report(self, report_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
            return None if row is None else dict(row)
