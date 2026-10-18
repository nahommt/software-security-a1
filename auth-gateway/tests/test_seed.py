import json
import sqlite3

import pytest

from app import seed
from app.users import UserStore


@pytest.fixture
def seed_env(tmp_path, keys, monkeypatch):
    passwords = {"alice": "alice-test-pw", "bob": "bob-test-pw", "dealer": "dealer-test-pw"}
    seed_file = tmp_path / "seed_users.json"
    seed_file.write_text(json.dumps(passwords))
    db_path = tmp_path / "auth.db"
    monkeypatch.setenv("SEED_USERS_FILE", str(seed_file))
    monkeypatch.setenv("AUTH_DB_PATH", str(db_path))
    monkeypatch.setenv("JWT_PRIVATE_KEY_FILE", keys["private_path"])
    monkeypatch.setenv("JWT_PUBLIC_KEY_FILE", keys["public_path"])
    return passwords, db_path, seed_file


def _users(db_path):
    return sqlite3.connect(db_path).execute("SELECT username, role FROM users ORDER BY username").fetchall()


def test_seed_creates_exactly_the_planned_accounts(seed_env):
    passwords, db_path, _ = seed_env
    seed.main()
    assert _users(db_path) == [("alice", "seller"), ("bob", "seller"), ("dealer", "dealer")]

    store = UserStore(str(db_path))
    for username, password in passwords.items():
        assert store.authenticate(username, password) is not None


def test_seed_stores_bcrypt_hashes_not_passwords(seed_env):
    passwords, db_path, _ = seed_env
    seed.main()
    hashes = [row[0] for row in sqlite3.connect(db_path).execute("SELECT password_hash FROM users")]
    for password_hash in hashes:
        assert password_hash.startswith(b"$2b$12$")
        assert all(password.encode() not in password_hash for password in passwords.values())


def test_seed_removes_other_accounts(seed_env):
    _, db_path, _ = seed_env
    store = UserStore(str(db_path))
    store.init_schema()
    store.upsert("mallory", "whatever", "dealer")
    seed.main()
    assert "mallory" not in [username for username, _ in _users(db_path)]


def test_seed_fails_when_password_missing(seed_env):
    _, _, seed_file = seed_env
    seed_file.write_text(json.dumps({"alice": "x", "bob": "y"}))
    with pytest.raises(SystemExit):
        seed.main()
