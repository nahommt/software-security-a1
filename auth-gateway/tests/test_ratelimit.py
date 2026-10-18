import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.ratelimit import LoginRateLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def limited_client(app, clock):
    limiter = LoginRateLimiter(ip_limit=10, ip_window=60, user_failure_limit=5, user_window=300, clock=clock)
    original = app.state.login_limiter
    app.state.login_limiter = limiter
    yield TestClient(app)
    app.state.login_limiter = original


def _login(client, username, password):
    return client.post("/login", json={"username": username, "password": password})


def test_failed_logins_for_user_are_limited(limited_client, passwords):
    for _ in range(5):
        assert _login(limited_client, "alice", "wrong").status_code == 401
    response = _login(limited_client, "alice", passwords["alice"])
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


def test_user_limit_expires_after_window(limited_client, passwords, clock):
    for _ in range(5):
        _login(limited_client, "bob", "wrong")
    clock.now += 301
    assert _login(limited_client, "bob", passwords["bob"]).status_code == 200


def test_successful_login_resets_failures(limited_client, passwords):
    for _ in range(4):
        _login(limited_client, "alice", "wrong")
    assert _login(limited_client, "alice", passwords["alice"]).status_code == 200
    for _ in range(4):
        assert _login(limited_client, "alice", "wrong").status_code == 401


def test_attempts_per_ip_are_limited_across_users(limited_client, clock):
    for i in range(10):
        _login(limited_client, f"user{i}", "wrong")
    assert _login(limited_client, "dealer", "wrong").status_code == 429
    clock.now += 61
    assert _login(limited_client, "dealer", "wrong").status_code == 401


def test_limited_request_does_not_check_password(limited_client, app, monkeypatch):
    for _ in range(5):
        _login(limited_client, "alice", "wrong")
    calls = []
    monkeypatch.setattr(app.state.users, "authenticate", lambda *args: calls.append(args))
    assert _login(limited_client, "alice", "wrong").status_code == 429
    assert calls == []


def test_default_limiter_is_enabled(keys, tmp_path):
    settings = Settings(
        private_key_file=keys["private_path"],
        public_key_file=keys["public_path"],
        db_path=str(tmp_path / "auth.db"),
    )
    client = TestClient(create_app(settings))
    statuses = [_login(client, "alice", "wrong").status_code for _ in range(11)]
    assert statuses[-1] == 429
