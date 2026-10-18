import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ALL_USER_SCOPES = "cars:create cars:read valuations:create valuations:read reports:read"
JOB_SCOPES = "cars:read valuations:read reports:create"
ROLES = {"alice": "seller", "bob": "seller", "dealer": "dealer"}

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


@pytest.fixture(scope="session")
def keys(tmp_path_factory):
    directory = tmp_path_factory.mktemp("keys")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_path = directory / "public.pem"
    public_path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return {"private": key, "other": other, "public_path": str(public_path)}


@pytest.fixture
def client(keys, tmp_path):
    settings = Settings(
        public_key_file=keys["public_path"],
        db_path=str(tmp_path / "car.db"),
        images_dir=str(tmp_path / "images"),
    )
    return TestClient(create_app(settings))


def _sign(claims, key):
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256")


@pytest.fixture
def service_token(keys):
    def _token(username, scope=ALL_USER_SCOPES, key=None, **overrides):
        now = int(time.time())
        claims = {
            "iss": "auth-gateway",
            "aud": "car-service",
            "token_use": "service",
            "sub": username,
            "role": ROLES.get(username, "seller"),
            "scope": scope,
            "iat": now,
            "exp": now + 60,
            "jti": uuid.uuid4().hex,
        }
        claims.update(overrides)
        return _sign(claims, key or keys["private"])

    return _token


@pytest.fixture
def job_token(keys):
    def _token(owner, car_id, job_id=None, scope=JOB_SCOPES, key=None, drop=(), **overrides):
        now = int(time.time())
        claims = {
            "iss": "auth-gateway",
            "aud": "car-service",
            "token_use": "job",
            "sub": owner,
            "car_id": car_id,
            "job_id": job_id or uuid.uuid4().hex,
            "scope": scope,
            "iat": now,
            "exp": now + 120,
            "jti": uuid.uuid4().hex,
        }
        claims.update(overrides)
        for claim in drop:
            claims.pop(claim)
        return _sign(claims, key or keys["private"])

    return _token


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def as_user(client, service_token):
    def _request(username, method, path, **kwargs):
        headers = {**auth(service_token(username)), **kwargs.pop("headers", {})}
        return client.request(method, path, headers=headers, **kwargs)

    return _request


@pytest.fixture
def make_car(as_user):
    def _make(owner, make="Volvo", model="V70"):
        response = as_user(
            owner,
            "POST",
            "/cars",
            json={"make": make, "model": model, "year": 2015, "mileage": 120000, "description": "Test"},
        )
        assert response.status_code == 201
        return response.json()

    return _make
