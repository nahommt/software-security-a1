import secrets

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.policy import DEALER, SELLER


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
def app(keys, passwords, tmp_path_factory):
    settings = Settings(
        private_key_file=keys["private_path"],
        public_key_file=keys["public_path"],
        db_path=str(tmp_path_factory.mktemp("db") / "auth.db"),
    )
    app = create_app(settings)
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
