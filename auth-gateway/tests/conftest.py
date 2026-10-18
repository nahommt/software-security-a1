import json
import secrets

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.policy import DEALER, SELLER
from app.ratelimit import LoginRateLimiter


class FakeUpstream:
    def __init__(self):
        self.requests = []
        self.routes = {}

    def set(self, method, path, status_code=200, body=None, content=None, headers=None):
        self.routes[(method, path)] = (status_code, body, content, headers or {})

    def handler(self, request):
        self.requests.append(request)
        status_code, body, content, headers = self.routes.get(
            (request.method, request.url.path), (404, {"detail": "Not found"}, None, {})
        )
        if content is not None:
            return httpx.Response(status_code, content=content, headers=headers)
        return httpx.Response(status_code, content=json.dumps(body).encode(), headers={"content-type": "application/json", **headers})

    def reset(self):
        self.requests.clear()
        self.routes.clear()


def _write_key_pair(directory, name):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path = directory / f"{name}_private.pem"
    public_path = directory / f"{name}_public.pem"
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return key, private_path, public_path


@pytest.fixture(scope="session")
def keys(tmp_path_factory):
    directory = tmp_path_factory.mktemp("keys")
    key, private_path, public_path = _write_key_pair(directory, "gateway")
    other_key, _, _ = _write_key_pair(directory, "other")
    return {
        "private": key,
        "private_path": str(private_path),
        "public_path": str(public_path),
        "public_pem": public_path.read_bytes(),
        "other_private": other_key,
    }


@pytest.fixture(scope="session")
def passwords():
    return {name: secrets.token_urlsafe(16) for name in ("alice", "bob", "dealer")}


@pytest.fixture(scope="session")
def car_upstream():
    return FakeUpstream()


@pytest.fixture(scope="session")
def report_upstream():
    return FakeUpstream()


@pytest.fixture(autouse=True)
def _reset_upstreams(car_upstream, report_upstream):
    car_upstream.reset()
    report_upstream.reset()


@pytest.fixture(scope="session")
def app(keys, passwords, tmp_path_factory, car_upstream, report_upstream):
    settings = Settings(
        private_key_file=keys["private_path"],
        public_key_file=keys["public_path"],
        db_path=str(tmp_path_factory.mktemp("db") / "auth.db"),
    )
    app = create_app(
        settings,
        login_limiter=LoginRateLimiter(ip_limit=10**6, user_failure_limit=10**6),
        car_transport=httpx.MockTransport(car_upstream.handler),
        report_transport=httpx.MockTransport(report_upstream.handler),
    )
    app.state.users.upsert("alice", passwords["alice"], SELLER)
    app.state.users.upsert("bob", passwords["bob"], SELLER)
    app.state.users.upsert("dealer", passwords["dealer"], DEALER)
    return app


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)


@pytest.fixture
def login(client, passwords):
    def _login(username):
        response = client.post(
            "/login", json={"username": username, "password": passwords[username]}
        )
        assert response.status_code == 200
        return response.json()["access_token"]

    return _login
