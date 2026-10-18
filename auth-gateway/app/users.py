import sqlite3

import bcrypt

from app.policy import ROLES

BCRYPT_ROUNDS = 12
MAX_PASSWORD_BYTES = 72

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash BLOB NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('seller', 'dealer'))
)
"""


class UserStore:
    def __init__(self, db_path):
        self._db_path = db_path
        self._dummy_hash = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt(BCRYPT_ROUNDS))

    def _connect(self):
        return sqlite3.connect(self._db_path)

    def init_schema(self):
        with self._connect() as conn:
            conn.execute(SCHEMA)

    def remove_all_except(self, usernames):
        placeholders = ", ".join("?" for _ in usernames)
        with self._connect() as conn:
            conn.execute(f"DELETE FROM users WHERE username NOT IN ({placeholders})", list(usernames))

    def upsert(self, username, password, role):
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS))
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?) "
                "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash, role = excluded.role",
                (username, password_hash, role),
            )

    def authenticate(self, username, password):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash, role FROM users WHERE username = ?", (username,)
            ).fetchone()
        password_bytes = password.encode()
        if row is None:
            bcrypt.checkpw(password_bytes, self._dummy_hash)
            return None
        password_hash, role = row
        if not bcrypt.checkpw(password_bytes, password_hash):
            return None
        return role
